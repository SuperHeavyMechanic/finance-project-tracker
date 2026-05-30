# PRD — Settlement Feature Overhaul
**Date:** 30 May 2026  
**Status:** Draft

---

## Problem

The current Settlements view is a flat, unsorted table. It has two issues:

1. **Wrong logic**: It shows transactions where the payer differs from the account owner — but the correct rule is: settlement is needed when the *Ideal Source* (who should pay) differs from the *Actual Source* (who actually paid).
2. **No structure**: There's no grouping by month, no totals per person, and no confirmation step — settling a batch of transactions means ticking boxes one by one.

This makes it hard to answer the practical question: "How much does SHAN owe JANICE this month, and how do I settle it in one go?"

---

## Goal

A Settlements view that:
- Shows who owes whom, how much, and for which month
- Lets you settle an entire group of transactions in one confirmed action
- Keeps a history of past settlements for crosschecking

---

## Settlement Rule

A transaction needs settlement when:
> **Ideal Source ≠ Actual Source**

Examples:
- Ideal = SHAN, Actual = JANICE → SHAN owes JANICE (Janice fronted it, Shan should pay back)
- Ideal = JANICE, Actual = SHAN → JANICE owes SHAN
- Ideal = Actual → no settlement needed (already correctly attributed)

---

## User Stories

**As SHAN**, I want to see all months where I owe JANICE money, with the total per month, so I know exactly what to transfer.

**As SHAN**, I want to settle a month's worth of transactions in one action — not tick each row individually.

**As SHAN or JANICE**, I want to look back at past settlements and see when they were settled and which transactions were included.

---

## Feature Design

### View Layout

```
[ Balance Banner ]          ← overall net: who owes whom and how much

[ ALL ]  [ SHAN owes ]  [ JANICE owes ]   ← filter tabs

── Outstanding ──────────────────────────────────

  April 2026
  ┌─────────────────────────────────────────────┐
  │ SHAN → JANICE                  Rp 1.250.000 │
  │ 15-Apr  Grab              TRANSPORTATION  45k│
  │ 18-Apr  Indomaret         GROCERIES      200k│
  │ ...                                         │
  │                          [ Settle this ]     │
  └─────────────────────────────────────────────┘

  March 2026
  ┌─────────────────────────────────────────────┐
  │ JANICE → SHAN                  Rp 320.000   │
  │ ...                                         │
  │                          [ Settle this ]     │
  └─────────────────────────────────────────────┘

── Settled History ──────────────────────────────
  ▶ February 2026 — settled 28-Feb-26
  ▶ January 2026  — settled 31-Jan-26
```

### Settle Flow

1. Click **[Settle this]** on a month+direction card
2. A confirmation modal appears:
   - Title: "Settle: SHAN → JANICE · April 2026"
   - Body: list of the transactions, total amount, settlement date (today, editable)
   - Buttons: Cancel / Confirm Settle
3. On confirm: all transactions in that card are marked settled with the chosen date
4. Card disappears from Outstanding, appears in Settled History

### Balance Banner

Shows the net across all outstanding (unsettled) transactions:
- "SHAN owes JANICE — Rp 930.000" (blue)
- "JANICE owes SHAN — Rp 450.000" (pink)
- "All settled ✓" (green)

### Filter Tabs

- **ALL** — show both SHAN owes and JANICE owes cards
- **SHAN owes** — show only cards where Ideal Source = SHAN
- **JANICE owes** — show only cards where Ideal Source = JANICE

### Settled History

- Collapsed by default (click to expand)
- Each entry shows: month settled, settlement date, total amount settled, expandable transaction list
- Greyed out / lower visual weight

---

## What Changes

| Layer | Change |
|---|---|
| Database | Fix settlement query (ideal ≠ actual, not payer ≠ account owner) |
| Database | New `bulk_settle_transactions(ids, date)` function |
| API | New `POST /api/settlements/settle` endpoint |
| Frontend | New Settlements view layout (grouped cards, history) |
| Frontend | New settlement confirmation modal |
| Frontend | Owner filter tabs |
| Tests | 2 new tests for bulk settle |

---

## Out of Scope

- Settling across multiple months in one action (settle per month only)
- Push notifications or reminders
- Integration with bank transfer apps
- JOINT account settlement logic (only SHAN ↔ JANICE for now)

---

## Success Criteria

- [ ] Outstanding transactions are grouped by month, then by direction (who owes whom)
- [ ] Each card shows the correct transactions (ideal ≠ actual, real expense, positive amount)
- [ ] Totals per card are correct
- [ ] Filter tabs correctly hide/show the right cards
- [ ] Balance banner reflects the correct net under the new logic
- [ ] Settle confirmation modal shows the right info and settles on confirm
- [ ] Settled transactions appear in history (collapsed)
- [ ] `pytest` passes (all existing + 2 new bulk settle tests)
