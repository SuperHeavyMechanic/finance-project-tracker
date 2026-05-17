# PRD-260517: Upload Review & Staging Layer

## Overview

This iteration introduces a mandatory review step between upload and commit for all statement types. Extracted transactions land in a temporary staging table first. The user reviews, edits, and deletes rows in isolation before confirming — only then do transactions enter the main table. This also lays the groundwork for debit card statement support, which requires seeing both Money Out (DB) and Money In (CR) before deciding what to keep.

---

## Background & Design Decisions

### Why a separate `staged_transactions` table

Three reasons drove this over adding a `status` column to `transactions`:

1. **Contract integrity.** `transactions` is read by every part of the app — dashboard, settlements, export, statements. A separate table makes it physically impossible for unconfirmed data to appear in any of those views. A status filter can be forgotten; a wrong table cannot.

2. **Lifecycle mismatch.** Staged rows are temporary (hours to days). Confirmed rows are permanent. CR rows from debit statements are staged for review but never confirmed — they exist purely as context. These are different things and belong in different tables.

3. **Schema fit.** Staged rows do not need `settled`, `settled_date`, `paid_by`, `ideal_paid_by` — those fields are only meaningful after confirmation. Forcing nulls into those columns on every staged row is noise.

The staged table is a **pure buffer**: after every confirm or discard, all staged rows for that upload are deleted. At any given time it only holds rows from uploads currently pending review.

### Account type

A new `account_type` field (`'credit'` or `'debit'`) is added to `accounts`. This drives:
- Which Claude extraction prompt to use
- Whether the review screen shows one section (credit) or two (debit: Money Out / Money In)
- Whether CR rows are extracted at all

### Statement date for debit statements

Credit card statements have an explicit billing date extracted by Claude. Debit (bank) statements have a PERIODE field (e.g. "APRIL 2026") but no single billing date. The statement date for debit uploads is derived as the **last calendar day of the period** (April 2026 → 2026-04-30). Claude extracts the period; the backend computes the last day.

---

## Feature 1 — Staged Transactions Table

### Schema

```sql
CREATE TABLE staged_transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id        INTEGER NOT NULL REFERENCES uploads(id),
    account_id       INTEGER NOT NULL REFERENCES accounts(id),
    date             TEXT,
    date_parsed      TEXT,
    description      TEXT,
    amount           REAL,
    category         TEXT,
    is_real_expense  INTEGER DEFAULT 1,
    transaction_type TEXT DEFAULT 'DB',   -- 'DB' (outgoing) or 'CR' (incoming)
    original_currency TEXT,
    original_amount  REAL
);
```

`transaction_type` is only meaningful for debit account uploads. Credit card rows always use `'DB'`.

### Lifecycle

```
Upload → staged_transactions (both DB + CR for debit; all rows for credit)
       ↓ Confirm
         INSERT DB rows → transactions  (with defaults: paid_by = account owner, settled = 0)
         DELETE all staged rows for upload_id
       ↓ Discard
         DELETE all staged rows for upload_id
         DELETE uploads record
```

After either action, `staged_transactions` is empty for that upload. The `uploads` record survives confirm (audit trail in Statements view) but is deleted on discard (as if the upload never happened).

---

## Feature 2 — Account Type

### Schema change

```sql
ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'credit';
```

Existing seeded accounts are credit cards — default `'credit'` covers them. New debit accounts are seeded or added with `account_type = 'debit'`.

`SEED_ACCOUNTS` in `db.py` is updated to include `account_type` per account.

---

## Feature 3 — Upload Flow Changes

### Current flow
`POST /api/upload` → Claude extracts → `save_upload()` → rows written to `transactions` → success response with count.

### New flow
`POST /api/upload` → Claude extracts → `save_staged()` → rows written to `staged_transactions` → success response with staged count + `upload_id` (used to open the review screen).

The upload success message changes from:
> ✓ 28 transactions added · Apr-26

To:
> ✓ 28 transactions staged · Review now →

Clicking "Review now" opens the review screen for that upload.

### Claude extraction — debit vs credit

The extraction prompt is branched by `account_type`:

**Credit card prompt (unchanged):** extracts transactions (all are expenses), returns `statement_date` and `transactions[]`.

**Debit card prompt (new):** extracts all rows (DB and CR), returns:
```json
{
  "period": "APRIL 2026",
  "transactions": [
    {
      "date": "01/04",
      "description": "Arya valet",
      "amount": 30000,
      "transaction_type": "DB",
      "category": "TRANSPORTATION",
      "is_real_expense": true
    },
    {
      "date": "03/04",
      "description": "Transfer from FAHMIANDINI KHOIRU – Keg Azana 1 s.d 3 April",
      "amount": 560000,
      "transaction_type": "CR",
      "category": "OTHERS",
      "is_real_expense": false
    }
  ]
}
```

**Debit extraction rules given to Claude:**
- Extract ALL rows including incoming transfers (CR) — they are shown in review for context
- `transaction_type`: `'DB'` for debit/outgoing, `'CR'` for credit/incoming
- Ignore Poket Valas pages (sections where MATA UANG ≠ IDR)
- For QR transactions: merchant name is the text after `00000.00` in the description
- For e-banking transfers: combine the free-text note and counterparty name into a readable description
- `BIAYA ADM` rows: extract as DB, category OTHERS, is_real_expense true
- `statement_date`: return the period string only (e.g. `"APRIL 2026"`); backend computes last day
- Default `is_real_expense`:
  - DB rows: Claude judges based on description (most are true; large round-number self-transfers are false)
  - CR rows: always false

---

## Feature 4 — Review Screen

### Trigger
Opens immediately after a successful upload via a modal overlay. Also accessible from the Statements tab: pending uploads show a **"Pending Review"** badge and a **"Review →"** button — this handles cases where the user navigated away before confirming.

### Credit card review (single section)

```
┌─ Review: CC BCA · Apr-26 ─────────────────────────────────┐
│  28 transactions · Rp 4,250,000 total                      │
│                                                            │
│  [editable table]                                          │
│  Date | Category | Description | Amount | Real? | [✕]      │
│  ...                                                       │
│                                                            │
│  [Discard upload]              [Confirm — add to tracker →]│
└────────────────────────────────────────────────────────────┘
```

### Debit card review (two sections)

```
┌─ Review: BCA Debit · Apr-26 ──────────────────────────────┐
│                                                            │
│  ▼ Money Out (DB) — 32 transactions · Rp 20,034,009       │
│  [editable table — same columns as credit review]          │
│  Date | Category | Description | Amount | Real? | [✕]      │
│  ...                                                       │
│                                                            │
│  ▼ Money In (CR) — 17 transactions · Rp 15,884,681        │
│  [read-only table — for reference only, not confirmed]     │
│  Date | Description | Amount                               │
│  ...                                                       │
│                                                            │
│  [Discard upload]        [Confirm — add DB to tracker →]   │
└────────────────────────────────────────────────────────────┘
```

### Editable fields in review

Per staged row (DB section):
- **Category** — dropdown (same 14 categories)
- **Description** — inline text edit
- **Amount** — inline numeric edit
- **Real?** — checkbox
- **Delete row** — removes from staged_transactions immediately (no undo)

CR section is read-only. It is shown for context (to understand what money came in during the period) but cannot be edited or confirmed.

### Confirm action

**Credit:** all staged rows for `upload_id` are inserted into `transactions`, then deleted from `staged_transactions`.

**Debit:** only `transaction_type = 'DB'` staged rows are inserted into `transactions`. All staged rows (both DB and CR) are then deleted from `staged_transactions`.

On insert into `transactions`, defaults applied:
- `paid_by` = account owner
- `settled` = 0
- `settled_date` = NULL
- `ideal_paid_by` = NULL

### Discard action

Confirmation prompt: "Discard this upload? All staged transactions will be deleted and the upload will be removed. This cannot be undone."

On confirm:
- DELETE all staged rows for `upload_id`
- DELETE the `uploads` record

The upload disappears entirely — no trace in the Statements view.

---

## API Changes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/upload` | Now saves to `staged_transactions` instead of `transactions`; returns `upload_id` |
| GET | `/api/uploads/<id>/staged` | Returns staged transactions for a given upload (both DB and CR) |
| PATCH | `/api/staged/<tx_id>` | Edit a staged row (category, description, amount, is_real_expense) |
| DELETE | `/api/staged/<tx_id>` | Delete a single staged row |
| POST | `/api/uploads/<id>/confirm` | Confirms staged upload: inserts DB rows to transactions, clears staged |
| DELETE | `/api/uploads/<id>` | Discards staged upload: deletes staged rows + upload record |

Existing `/api/transactions` and all downstream routes are unchanged — they only read confirmed `transactions`.

---

## Data Model Summary

| Change | Detail |
|--------|--------|
| New table | `staged_transactions` — temporary buffer, auto-cleared on confirm/discard |
| `accounts` | Add `account_type TEXT DEFAULT 'credit'` |
| `uploads` | No schema change; gains a pending state (rows exist but no confirmed transactions yet) |
| `transactions` | No schema change; remains clean confirmed-only data |

---

## Out of Scope

- Editing staged transactions in bulk (single-row inline editing only)
- Re-opening review after confirming (once confirmed, edit via main Transactions view)
- Importing debit CR transactions as negative-amount entries
- UI for adding/editing accounts (accounts remain backend-seeded)
- Rules engine applied to debit extraction (can be added in a future iteration)
