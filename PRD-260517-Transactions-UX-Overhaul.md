# PRD-260517: Transactions Page UX Overhaul

## Overview

This iteration overhauled the Transactions view across four areas:
1. A two-row filter bar covering all filterable dimensions
2. A distinct "select" mode with visual row highlighting and a floating bulk-action bar
3. A guided two-step Export modal replacing the old inline export button
4. Table ergonomics — frozen header/columns and full-screen width

---

## Feature 1 — Expanded Filter Bar

### Problem
The previous filter bar only exposed five dimensions (search, owner, month, account, category, real/non). Seven additional dimensions were filterable in the backend but had no UI controls.

### What We Built
A two-row filter section, permanently visible above the table, labeled **"Filter"** to clearly distinguish it from the selection controls.

| Row | Controls |
|-----|----------|
| Primary | Search · Month · Category · Real / Non · **Clear All** |
| Secondary | Paid By (card owner) · Actual Source · Ideal Source · Settled / All · Card Statement |

**Clear All** resets every filter and re-fetches.

### Backend Changes
New query parameters added to `GET /api/transactions` (and the underlying `get_transactions()` in `db.py`):

| Param | Field | Values |
|-------|-------|--------|
| `paid_by` | `transactions.paid_by` | SHAN / JANICE / JOINT |
| `ideal_paid_by` | `transactions.ideal_paid_by` | SHAN / JANICE / JOINT |
| `settled` | `transactions.settled` | `1` (settled) / `0` (unsettled) |
| `upload_id` | `transactions.upload_id` | specific statement upload ID |

`GET /api/export` also accepts `upload_id` for statement-scoped CSV exports.

### Design Decisions
- **Card Statement filter** (upload_id) replaces the old "Select by statement…" dropdown that previously lived in the page header and did double duty as both a filter and a selection trigger. Separating filter and select concerns was the primary motivation.
- The **Owner filter** is labelled "Paid By" in the UI to match the column header name.
- Filter state survives re-renders; row selection is independent and persists across filter changes.

---

## Feature 2 — Selection UX & Floating Action Bar

### Problem
Checkboxes existed but selected rows were visually indistinct, and the only action available was export (reached via the export button changing its label). There was no bulk-delete or bulk-reassign capability.

### What We Built

#### 2a — Selected row highlight
Checked rows receive a **blue tint background** (`#eff6ff`) and a **3 px solid blue left border** (`#0071e3`), making the selection queue immediately visible while scrolling.

#### 2b — Floating action bar
A pill-shaped bar slides up from the bottom of the viewport whenever ≥ 1 row is selected. It dismisses automatically when the selection is cleared.

**Bar contents:**
```
[N selected]  [Reassign category ▾]  |  [Delete]  |  [✕ Clear]
```

| Action | Behaviour |
|--------|-----------|
| **Reassign category** | Dropdown of all 14 categories. Selecting one immediately patches all checked rows via parallel PATCH requests; local cache updated; table re-renders. Dropdown resets to placeholder after apply. |
| **Delete** | `confirm()` prompt: "Permanently delete N transactions? This cannot be undone." On confirm, parallel DELETE requests; rows removed from local cache; selection cleared. |
| **Clear** | Clears `selectedTxIds` Set and re-renders without making any API calls. |

### Out of Scope
- Bulk edit of amount, paid_by, or settled status (single-row inline editing remains for these)
- Undo / soft delete

---

## Feature 3 — Export Modal (Two-Step Flow)

### Problem
The old Export CSV button changed its label to "Export N selected" when rows were checked, and fell back to exporting the current filter set when nothing was selected. The two modes were not clearly presented, and there was no preview before downloading.

### What We Built
A dedicated **Export CSV** button (always visible, top-right of the Transactions header) opens a modal with two steps.

#### Step 1 — Choose scope
Two options presented as clickable cards:

| Option | Availability | Behaviour |
|--------|-------------|-----------|
| **Export selected (N items)** | Active only when ≥ 1 row is checked; greyed out otherwise | Proceeds directly to Step 2 using `selectedTxIds` |
| **Export by card statement** | Always available | Shows a dropdown of all statements; selecting one proceeds to Step 2 for that upload |

#### Step 2 — Preview
Before downloading, the user sees:
- **Summary strip**: item count · date range · total IDR amount
- **Mini-table**: first 10 rows (Date, Category, Description, Amount), with a "…and N more" footer if the set exceeds 10

Action buttons:
- **← Back** — returns to Step 1
- **Download CSV** — triggers the actual download, then closes the modal

#### Download mechanics
| Scope | API call |
|-------|---------|
| Selected rows | `GET /api/export?ids=1,2,3,…` |
| Card statement | `GET /api/export?upload_id=N` |

### Design Decisions
- Preview data is drawn from `allTxRows` (the full unfiltered transaction cache fetched at page init), so the statement preview is accurate even when other filters are active.
- The modal closes on backdrop click.

---

## Feature 4 — Table Ergonomics

### Problem
On wider screens the table was capped at 1200 px, leaving significant horizontal space unused. On long transaction lists, scrolling past the header row meant losing column context. Scrolling right caused the row identifier columns (date, description, amount) to disappear.

### What We Built

#### 4a — Full-screen width
`main` max-width raised from **1200 px → 1600 px**. The table fills the additional horizontal space naturally.

#### 4b — Frozen header row
`thead th` is `position: sticky; top: 0` within the `.tx-scroll` scroll container. Column headers remain visible when scrolling through long transaction lists.

The `.tx-scroll` container has `max-height: calc(100vh - 260px)` and `overflow: auto`, keeping the filter bar and page title always above the scroll zone.

#### 4c — Frozen columns (Checkbox → Amount)
The first five columns are `position: sticky` with cumulative `left` offsets:

| Col | Content | `left` offset |
|-----|---------|--------------|
| 1 | Checkbox | 0 |
| 2 | Date | 40 px |
| 3 | Category | 136 px |
| 4 | Expense Items Detail | 276 px |
| 5 | Amount (Rp) | 496 px |

A **2 px border-right** on column 5 marks the boundary between the frozen and scrollable zones.

**Background handling:** sticky cells receive explicit `#fff` backgrounds (overridden to `#fafafa` on hover and `#eff6ff` on selection via `!important`) so they correctly cover content scrolling behind them.

---

## Feature 5 — CSV Export Format Fixes

Two fixes applied to all CSV exports (`GET /api/export`):

| Fix | Before | After |
|-----|--------|-------|
| Foreign currency | `87293.0 (USD 5.0)` | `87293` |
| Decimal amounts | `69000.0` | `69000` |

Amount is now `int(round(r['amount']))` — IDR only, no decimals.

Additionally, exported rows are **sorted ascending by date** (`date_parsed` ASC, `id` ASC as tiebreaker), regardless of the descending sort used in the UI.

---

## Files Changed

| File | Changes |
|------|---------|
| `db.py` | `get_transactions()` — added `paid_by`, `ideal_paid_by`, `settled`, `upload_id` filter params |
| `app.py` | `/api/transactions` — passes new params through; `/api/export` — adds `upload_id` support, rounds amount to int, sorts rows ascending |
| `templates/index.html` | Two-row filter bar; floating action bar; export modal; frozen header/columns; full-width layout; bulk delete + reassign JS |
