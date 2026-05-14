# PRD-260514: Transaction Editing, Statement Traceability & Per-Card Rules

## Overview

This iteration adds three enhancements to the Finance Project Tracker:
1. Full edit and delete control over individual transactions
2. Statement-level traceability — both at the transaction row and as a dedicated recap tab
3. A per-card categorization rules system that overrides Claude's default judgment

---

## Feature 1 — Transaction Editing & Removal

### Problem
Currently, users can toggle `is_real_expense` but cannot correct a wrong amount or permanently remove a transaction that should not exist in the system.

### What We're Building
- **Edit amount**: Any transaction's IDR amount can be updated inline in the Transactions table
- **Hard delete**: A transaction can be permanently removed from the database. This is a destructive action and must be confirmed before executing.

### Behaviour
- Editing amount updates the `amount` field in the `transactions` table
- Deleting a transaction removes the row entirely — it is not a soft delete
- Deletion requires a confirmation prompt ("Are you sure you want to remove this transaction? This cannot be undone.")
- Both actions are accessible from the existing row action controls in the Transactions view

### Out of Scope
- Bulk edit or bulk delete
- Soft delete / undo functionality

---

## Feature 2 — Statement Traceability

### Problem
Transactions in the system have no visible link to the statement they came from. There is no way to quickly verify whether all transactions from a given statement have been captured and are accounted for.

### What We're Building

#### 2a — Transaction-level source label
Each transaction row in the Transactions table gets a new field showing its source statement, formatted as:

> **CC [BANK NAME] - [STATEMENT DATE]**
> e.g., "CC Mandiri - 15 Jan 2025"

The bank name is derived from the account name. The statement date is the full date (not month only) stored at upload time.

#### 2b — New "Statements" tab
A dedicated tab listing every upload in the system, serving as a quick audit reference against the physical PDF.

**Columns per row:**
| Field | Notes |
|-------|-------|
| Statement Reference | CC [BANK NAME] - [STATEMENT DATE] |
| Filename | Original uploaded filename |
| Upload Date | When the file was processed |
| Extracted (original) | # transactions + total IDR amount at time of upload — **primary, highlighted** |
| Active (current) | # transactions + total IDR amount currently in system (after edits/deletions) — secondary, dimmed |

The original extracted figures are the highlight — they represent what was pulled from the statement. The active figures give a quick sense of what has changed since.

### Behaviour
- The Statements tab is read-only — no actions from this view
- Rows are sorted by upload date, newest first
- If original and active counts/amounts match, no visual distinction is needed. If they differ (transactions were deleted or amounts edited), the active figures are shown in a dimmed/secondary style to indicate divergence

### Out of Scope
- "Mark as reviewed" or any explicit sign-off workflow (may be considered in a future iteration)
- Filtering or searching within the Statements tab

---

## Feature 3 — Per-Card Categorization Rules

### Problem
The current system uses a single universal extraction prompt for all cards. Merchants like "GRAB" get inconsistent categories depending on which card they appear on, with no way to enforce card-specific logic.

### What We're Building
A `rules.py` file containing per-account keyword-to-category mappings. These rules are injected into the Claude extraction prompt at upload time (scoped to the account being processed) and also applied as a post-processing override after Claude returns results.

### Rules Format
```python
ACCOUNT_RULES = {
    "Mandiri": {
        "GRAB": "F&B",
        "GOJEK": "F&B",
    },
    "BCA": {
        "GRAB": "TRANSPORTATION",
        "GOJEK": "TRANSPORTATION",
    },
}
```

Keys are account name substrings (case-insensitive match against the account name in the database). Values are merchant keyword → category mappings.

### Matching Logic
- **Merchant matching**: substring/keyword match, case-insensitive (e.g., rule "GRAB" matches "GRAB-82731-JKT", "GRABFOOD*ORDER")
- **Account matching**: substring match against account name (e.g., "Mandiri" matches "Mandiri Debit", "Mandiri CC")
- More specific rules should be listed first within each account block to prevent shorter keywords from shadowing longer ones

### Application Logic
Rules are applied in two stages:

1. **At extraction time**: The relevant account's rules are appended to the Claude prompt as explicit instructions before Claude processes the statement. This improves raw output quality.
2. **Post-extraction override**: After Claude returns results, a Python function iterates every transaction and forcibly applies matching rules — overriding Claude's category assignment. This guarantees rules always win.

### Conflict Resolution
Rules always take precedence over Claude's judgment. If Claude assigns "TRANSPORTATION" to a GRAB transaction on a Mandiri statement, the post-processing step will override it to "F&B".

### Updating Rules
Rules are updated by editing `rules.py` directly. No UI is provided in this iteration. Changes take effect on the next upload.

### Out of Scope
- A UI for managing rules
- Retroactive re-categorization of existing transactions when rules are changed
- Rules stored in the database (deferred — required if a UI is added later)

---

## Data Model Changes

| Change | Details |
|--------|---------|
| `transactions` table | No schema change needed; `upload_id` FK already exists |
| `uploads` table | Confirm `statement_date` (full date, not just month) is stored; add if missing |
| New `rules.py` | New file at project root; not a DB change |
| Statements API | New `GET /api/statements` endpoint returning upload list with original + active counts/amounts |

---

## API Changes

| Method | Path | Purpose |
|--------|------|---------|
| DELETE | `/api/transactions/<id>` | Hard delete a transaction |
| PATCH | `/api/transactions/<id>` | Extended to include `amount` as an editable field (already exists, just adding amount) |
| GET | `/api/statements` | Returns all uploads with original + active transaction counts and totals |

---

## Decisions

1. **Statement date** — the billing cycle end date as detected from the PDF, not the upload date. This requires extending the current `_dominant_month` logic to extract a full date.
2. **Statements tab layout** — grouped by card, with each card's uploads listed chronologically beneath it.
