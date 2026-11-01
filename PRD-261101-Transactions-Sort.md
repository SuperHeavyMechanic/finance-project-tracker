# PRD — Transactions Sort Control

**Date:** 2026-11-01
**Author:** Shan Sebastian (with Claude Code)
**Status:** Draft — pending implementation

---

## 1. Problem

Since the filter-bar redesign (`PRD-261101-Transactions-Filter-Redesign.md`), sorting on Transactions feels missing:

- Clicking a column header still sorts (`txSort(key)` on Date, Category, Expense Items Detail, Amount, Account, Statement Date), but nothing on screen says so — no arrow, no active-column styling. Every `th` already has `cursor: pointer`, so sortable and non-sortable headers look the same.
- The only hint is plain text at the right of the summary line ("Sorted by date, oldest first"). It is not clickable.
- The page opens **oldest first**, so the latest transactions are at the bottom of a long list.

### Current-state facts (from code)

- State: `txSortKey = 'date_parsed'`, `txSortDir = -1`; sorting is client-side in `renderTxTable()` over `txRows`.
- The comparator is `av < bv ? txSortDir : …`, so `txSortDir = -1` means **ascending**. The naming is inverted relative to convention and caused the "oldest first" default.
- `txSort(key)`: same key flips direction; a new key starts at `-1` (ascending).
- No tie-breaker: rows with equal values keep the API's order (`date_parsed DESC, id DESC`), so same-day rows flip unpredictably when the direction changes.
- `txSortLabel()` renders the "Sorted by …" text in `renderTxSummary()`.

---

## 2. Goals

- A visible, obvious **Sort** control in the summary line, matching the mockup.
- Open on **Newest first**.
- Header-click sorting stays, now with a visible ▲/▼ indicator, and always agrees with the Sort control.
- Stable, predictable order for ties.

## 3. Non-goals

- Persisting the sort (URL or storage). Every visit to Transactions, and every reload, starts on Newest first. **Clear all** does not touch the sort.
- Server-side sorting or multi-column sort.
- Sort on other pages (Dashboard category panel has its own Amount / Date / A–Z pills).

---

## 4. Behaviour

### 4.1 Sort control

- Replaces the "Sorted by …" text at the right end of the summary line (`#tx-summary`).
- Look (from the mockup): a bordered control, sort icon (↓↑), muted label "Sort", the current option, chevron. Same height, border, radius and active/focus treatment as the filter-bar controls (`.tx-ctl`), Tally tokens.
- Implemented as a **native `<select>`** styled to that look (the mockup shows the native macOS menu with a ✓ on the current option). Keyboard and screen-reader support come for free; label via `aria-label="Sort transactions"`.
- Options, in order:

  | Option | Key | Direction |
  |---|---|---|
  | Newest first *(default)* | `date_parsed` | descending |
  | Oldest first | `date_parsed` | ascending |
  | Amount: high to low | `amount` | descending |
  | Amount: low to high | `amount` | ascending |
  | Category A–Z | `category` | ascending |

- Choosing an option re-sorts immediately (no refetch).

### 4.2 Column headers

- Header clicks keep working on the same six columns.
- **First click** on a column: Date and Amount sort descending (newest / largest first); text columns (Category, Expense Items Detail, Account, Statement Date) sort ascending (A–Z, oldest statement first). **Clicking again** flips the direction.
- The active column shows ▲ (ascending) or ▼ (descending) after its label and carries `aria-sort="ascending|descending"`. Sortable headers get a sortable class; non-sortable headers (checkbox, Real?, Paid By, Actual/Ideal Source, Settled?, actions) lose `cursor: pointer`.
- **Sync with the control:** after a header click, the Sort control shows the matching option when one exists (e.g. Amount ▼ → "Amount: high to low"). When the header sort has no matching option (Category Z–A, Expense Items Detail, Account, Statement Date), the control shows a temporary extra option naming it — e.g. "Account A–Z", "Category Z–A" — selected and listed last. It disappears once a standard option is chosen.

### 4.3 Ordering rules

- One direction convention: `txSortDir = 1` ascending, `-1` descending (fix the inverted comparator).
- Tie-breakers, applied in order after the chosen key: `date_parsed` descending, then `id` descending. So same-day rows always list the most recently added first, and equal amounts list newest first.
- Missing values (no date, no category, no statement) always sort **last**, in either direction.
- Amount sorts by signed value: "high to low" puts the largest charges first and refunds/payments (negative) last.

### 4.4 Reset

- `initTransactions()` (every navigation to Transactions) and page load reset to Newest first.
- Filter changes, Clear all, inline edits and deletes keep the current sort.

---

## 5. Implementation plan

All in `templates/index.html`; no backend change.

- **State:** keep `txSortKey`, redefine `txSortDir` as `1` = ascending / `-1` = descending; default `date_parsed` / `-1`. Add `TX_SORT_OPTIONS` (value → key, dir, label) and `TX_SORT_FIRST_DIR` (key → first-click direction).
- **Comparator** in `renderTxTable()`: compare by key with the corrected direction, missing values last, then the tie-breakers in §4.3.
- **`txSort(key)`** (header click): same key flips; new key takes `TX_SORT_FIRST_DIR[key]`; then `renderTxTable()`.
- **`setTxSort(value)`** (control change): set key/dir from `TX_SORT_OPTIONS`; `renderTxTable()`.
- **`renderTxSortControl()`**, called from `renderTxSummary()`: renders the `<select>`, marks the current option, adds the temporary custom option when needed. Replaces `txSortLabel()` text output (the label function is reused to name the custom option).
- **Header indicator:** `renderTxTable()` updates the six sortable `th`s — arrow span + `aria-sort` on the active one, cleared on the rest. Header markup gets `class="th-sort"` and `data-sort-key`; CSS limits `cursor: pointer` / hover to `.th-sort` within the Transactions table.
- **Reset:** `initTransactions()` sets `txSortKey = 'date_parsed'; txSortDir = -1` before loading.
- **CSS:** `.tx-sort` (wrapper with icon + "Sort" label + transparent full-size `<select>` overlay, or a styled select with `appearance: none` and a background chevron), reusing `.tx-ctl` tokens.

### Docs

`CLAUDE.md` Transactions Filter Bar section: sort control, header sync, direction convention, tie-breakers, no persistence.

---

## 6. Implications & considerations

| Area | Impact | Handling |
|---|---|---|
| Default flips to newest first | Users reading top-to-bottom in statement order now see the reverse. | "Oldest first" is one click away; matches the mockup and most finance apps. |
| `txSortDir` meaning flips | Any code reading `txSortDir` with the old meaning breaks. | Only `renderTxTable`, `txSort` and `txSortLabel` read it — all rewritten together. |
| Not persisted | A deep link with filters opens on Newest first, not the sort you had. | Decided (§3). |
| Native select styling | The open menu uses the OS look (as in the mockup), not Tally's custom Period/Statement menus. | Accepted for accessibility and simplicity. |
| Inline edits | Editing an amount or category doesn't move the row until the next re-render. | Same as today; avoids rows jumping under the cursor. |

---

## 7. Decisions (2026-11-01)

1. **Default:** Newest first.
2. **Options:** the mockup's five.
3. **Headers:** keep header sorting, add ▲/▼, keep the control in sync (custom option for header-only sorts).
4. **Persistence:** none — every visit starts on Newest first.

---

## 8. Acceptance criteria

- [ ] Summary line shows a Sort control (icon, "Sort", current option, chevron) instead of "Sorted by …" text.
- [ ] Transactions opens on Newest first; navigating away and back, or reloading, resets to it.
- [ ] Each of the five options orders the table as named.
- [ ] Header clicks sort, show ▲/▼ and `aria-sort` on the active column only, and update the Sort control (custom option when no standard one matches).
- [ ] First click: Date / Amount descending, text columns ascending; second click flips.
- [ ] Same-day rows are ordered newest-added first; empty values sort last in both directions.
- [ ] Changing filters, Clear all, inline edits and deletes keep the current sort.
- [ ] Non-sortable headers no longer show a pointer cursor.
