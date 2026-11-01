# PRD — Transactions Filter Bar Redesign

**Date:** 2026-11-01
**Author:** Shan Sebastian (with Claude Code)
**Status:** Draft — pending implementation

**Source material:** `filter redesign supporting docs/`
- `Transactions Filter Bar — Build Spec.md` — the design brief ("Direction A")
- `transactions-filter-direction-a.html` — static reference build of the bar, popover, chips and summary

This PRD adapts that spec to Tally's real data model and existing screen. Where they differ, **this PRD wins**; every deviation is listed in §9.

---

## 1. Problem

The Transactions filter bar (`#view-transactions`, `templates/index.html`) has 9 filters as equal-weight `<select>`s across two wrapping rows:

- Nothing signals which filters matter for the three real jobs: **reconcile** a statement, **settle up**, **find** one transaction.
- Several controls show a value but not what they filter ("Real / Non", "Settled / All").
- Asking "which rows were paid from the wrong source?" needs two dropdowns and mental comparison.
- After filtering there is no count, total or summary of what is active.

### Current-state facts (from code)

| Control (`id`) | UI label | Filters on | API param |
|---|---|---|---|
| `tx-search` | Search… | `t.description LIKE` | `q` |
| `tx-month` | All Months | `substr(t.date_parsed,1,7)` | `month` |
| `tx-category` | All Categories | `t.category` | `category` |
| `tx-real` | Real / Non | `t.is_real_expense` | `is_real_expense` |
| `tx-owner` | Paid By | **`a.owner`** (account owner) | `owner` |
| `tx-paid-by` | Actual Source | `t.paid_by` | `paid_by` |
| `tx-ideal-paid-by` | Ideal Source | `t.ideal_paid_by` | `ideal_paid_by` |
| `tx-settled` | Settled / All | `t.settled` | `settled` |
| `tx-upload` | All Statements | `t.upload_id` | `upload_id` |

- Every change calls `loadTransactions()`, which refetches `GET /api/transactions` server-side. Search fires on every keystroke (no debounce).
- `allTxRows` already holds the unfiltered set (loaded in `loadTxFilters()`); it feeds the month list and `allUploads` (statement labels like `CC - Mandiri Visa Golf Shan · 11-Sep-26`).
- The app has no URL routing; `navigate(view)` swaps views in place.
- "Paid By" vs `paid_by`: the label "Paid By" filters account ownership, while the `paid_by` column is surfaced as "Actual Source". Kept as-is by decision (§8 Q4) — see §9.

---

## 2. Goals

- Make the three jobs fast: primary controls for reconcile (Period, Statement, Status) and find (Search) in one row; everything else one click away.
- Every control names the field it filters.
- One-click "wrong source only" view for settling up.
- Always show what you're looking at: count, total, settle-up net, active hidden filters.
- Filtered views survive reload and can be bookmarked.

## 3. Non-goals

- **Table changes.** Columns, inline editing, bulk selection/action bar, sorting stay exactly as they are.
- **Export changes.** `Export CSV` button and its modal stay as they are.
- **Renaming the who-paid fields.** "Paid By", "Actual Source", "Ideal Source" keep today's names.
- New visual tokens. Tally's `DESIGN-SYSTEM.md` variables are used, not the spec's hex values.
- Mobile layout (desktop app; the row just wraps when narrow).
- Changing any existing filter's data logic.

---

## 4. Filter model

| Filter | Label | Values | Default | Control | Placement |
|---|---|---|---|---|---|
| Search | Search | Free text — description, or an amount (see §5.6) | Empty | Text input with search icon | Primary row |
| Month | Period | "All time" + months with data, newest first | **Latest month with data** | Dropdown button "Period · Oct 2026" | Primary row |
| Statement | Statement | "Any" + one option per upload (existing `allUploads` labels) | Any | Dropdown button "Statement · Any" | Primary row |
| Settled | Status | All · Unsettled · Settled | All | 3-segment toggle | Primary row |
| Category | Category | "Any category" + `CATEGORIES` | Any | Select | More filters › What |
| Real / Non | Type | All · Real spend · Transfers & adjustments | All | 3-segment toggle + hint | More filters › What |
| Account owner | **Paid By** | Anyone · SHAN · JANICE · JOINT | Anyone | 4-segment toggle | More filters › Who paid & from where |
| `paid_by` | **Actual Source** | "Any" + SHAN · JANICE · JOINT | Any | Select | More filters › Who paid & from where |
| `ideal_paid_by` | **Ideal Source** | "Any" + SHAN · JANICE · JOINT | Any | Select | More filters › Who paid & from where |
| *(new)* | Wrong source only | On / off | Off | Checkbox card + hint | More filters › Who paid & from where |

Copy:
- Type hint: "Real spend is money that left the household. Moves between your own accounts count as transfers."
- Wrong source hint: "Actual Source differs from Ideal Source — these are what needs settling."
- Type values map 1:1 to today's `is_real_expense` = 1 / 0.

**Wrong source only** = `ideal_paid_by IS NOT NULL AND ideal_paid_by != paid_by` — the exact predicate `get_settlements()` uses, so this view and the Settlements page always agree.

---

## 5. Behaviour

### 5.1 Layout (top to bottom)

1. **Header** — unchanged: "Transactions", `+ Add`, `Export CSV`.
2. **Filter card, primary row** — Search (grows, min 280px) · Period · Statement · Status · **More filters** (with count badge of active hidden filters).
3. **Chips row** — only when ≥1 hidden filter is active. Dashed top divider, label "ALSO FILTERING", one chip per active hidden filter ("Type: Real spend ×", "Paid By: SHAN ×", "Wrong source only ×"), **Clear all** right-aligned.
4. **Summary line** (outside the card) — "**5** of 318 transactions · Total **Rp 2.140.000**", plus an amber settle-up line when relevant (§5.5).
5. **Table** — unchanged.

### 5.2 Primary row

- Dropdown buttons always render muted field name + value ("Period · Oct 2026"). Implemented as buttons opening a small listbox menu; the Period and Statement menus can be long, so they scroll (max-height) and support type-ahead or arrow keys.
- A primary control whose value ≠ its default gets the active style (accent border + accent-soft fill). Note: Period's default is "latest month with data", so picking "All time" makes it active.
- Search, Period, Statement, Status apply immediately. Search is debounced 250ms.

### 5.3 Statement overrides Period

- Picking a statement shows exactly that upload's transactions (`upload_id` only — **no** month filter is sent, because credit-card cycles span two calendar months).
- The Period button becomes disabled and reads "Period · from statement".
- Setting Statement back to Any re-enables Period and restores its previous value.

### 5.4 More filters popover

- ~440px wide, anchored under More filters, right-aligned to the card. `role="dialog"`, focus moves in on open, Tab is trapped, focus returns to More filters on close.
- Sections: **What** (Category, Type) and **Who paid & from where** (Paid By toggle; Actual Source and Ideal Source selects side by side; Wrong source only card, accent-tinted when on).
- Footer: "Reset these" (resets only popover filters, still pending) and primary "Show N transactions" with a live count.
- **Applies on confirm only.** Edits are a draft; the live count is fetched for the draft. Esc, ×, or clicking outside closes **without** applying.

### 5.5 Summary line

- "**N** of **T** transactions" — N = filtered rows, T = `allTxRows.length`.
- "Total **Rp X**" — **net sum of all filtered rows**, negatives included (ties to what an export of the same rows would sum to).
- Settle-up line, amber, only when the filtered rows contain unsettled wrong-source rows (`settled = 0` and wrong-source predicate). Nets per pair the same way the Settlements page does: `ideal_paid_by` owes `paid_by`; opposite directions between the same two parties cancel. One clause per non-zero pair, e.g. "JOINT owes SHAN **Rp 2.140.000** · JANICE owes SHAN **Rp 120.000**".
- Right side: current sort ("Sorted by date ↓"), reflecting `txSortKey` / `txSortDir`.
- Recomputed on every results change, including after inline edits (`patchTx`) and deletes.

### 5.6 Search

- Matches description (today's behaviour).
- **New:** if the query, after stripping `.`, `,`, spaces and an `Rp` prefix, is all digits, also match rows whose rounded absolute amount contains those digits (so "642500", "642.500" and "Rp 642.500" all find Rp 642.500). Server-side, in `get_transactions`.
- No "note" search — Tally has no note field.

### 5.7 Chips, Clear all, Reset these

- Chips mirror **hidden** filters only; primary-row filters already show their value.
- Removing a chip clears that filter and refetches immediately.
- **Clear all** resets every filter (primary + hidden) to its default, so Period goes back to the latest month with data, not All time. Hidden when everything is at default. It replaces today's `clearFilters()` button.

### 5.8 URL state

- Every non-default filter is written to the query string with `history.replaceState`: `?view=transactions&period=2026-10&statement=41&status=unsettled&q=superindo&category=GROCERIES&type=real&owner=SHAN&actual=JOINT&ideal=SHAN&wrong=1`.
- `period=all` encodes "All time" (since the default is not All time).
- On page load, if `view=transactions` is present, open Transactions with those filters. Unknown/invalid values (e.g. a deleted statement id) fall back to the default silently.
- Leaving the Transactions view clears the query string, so other views don't carry stale params.

### 5.9 Empty state

- Zero results: table body shows "No transactions match these filters" plus a **Clear all** button.
- **Nice-to-have:** if removing exactly one active filter would bring results back, name it ("Remove *Type: Real spend* to see 12"). Implemented by one count request per active filter; skip if it adds noticeable lag.

### 5.10 Accessibility

- Real `button` / `select` / `input` elements throughout; segmented toggles use `aria-pressed`; chip remove buttons carry `aria-label="Remove <filter> filter"`; popover as in §5.4.
- Control height follows existing Tally controls (not the spec's 44px); hit area ≥ 32px.

---

## 6. Implementation plan

### 6.1 `db.py` — `get_transactions()`

- New `wrong_source=False` param ⇒ `AND t.ideal_paid_by IS NOT NULL AND t.ideal_paid_by != t.paid_by`.
- Search: add the amount match from §5.6 alongside the description `LIKE` (`OR CAST(ABS(ROUND(t.amount)) AS INTEGER) LIKE ?`).
- Nothing else changes.

### 6.2 `app.py` — `GET /api/transactions`

- Accept `wrong_source=1` and pass it through.

### 6.3 `templates/index.html`

- Replace the two `.filter-row`s in `#view-transactions` with the filter card (primary row, chips row, popover) and a summary line between card and table.
- Introduce one filter state object (`txFilters`) with a `TX_FILTER_DEFAULTS` table; controls render from it rather than reading DOM values. `loadTransactions()` builds params from `txFilters`.
- Popover keeps a separate draft copy; "Show N" commits it.
- Helpers: `renderTxFilterBar()`, `renderTxChips()`, `renderTxSummary()`, `txFiltersToUrl()` / `txFiltersFromUrl()`.
- `loadTxFilters()` keeps building months and `allUploads` from `allTxRows`, and now also sets the Period default.
- Styles: new classes (`.tx-filter-card`, `.seg`, `.ctl`, `.chip`, `.tx-popover`, `.tx-summary`) using existing tokens (`--accent`, `--accent-soft`, `--accent-soft-border`, `--line`, `--line-strong`, `--ink-2`/`--ink-3`, warning tokens for amber, `--r-*` radii).
- Remove the now-unused `.filter-tag` row markup and old `clearFilters()`; leave `.filter-select` (used elsewhere, e.g. export modal).

### 6.4 Tests (`tests/test_db.py`)

- `wrong_source=True` returns only rows with `ideal_paid_by` set and ≠ `paid_by`; NULL `ideal_paid_by` excluded.
- Amount search: "642500", "642.500", "Rp 642.500" match a 642500 row; a text query still matches description only.
- API: `GET /api/transactions?wrong_source=1` filters correctly.

### 6.5 Docs

`CLAUDE.md`: Transactions filter state (`txFilters`), URL params, `wrong_source` in the `/api/transactions` route row.

---

## 7. Implications & considerations

| Area | Impact | Handling |
|---|---|---|
| Default Period changes from All Months to latest month | Opening Transactions shows less than today. Searching for an old transaction needs Period → All time. | Period button is active-styled and the summary says "N of T", so the hidden rest is obvious. Search could auto-widen to All time — **not** done, to keep behaviour predictable. |
| "Unsettled" is broad | `settled` defaults to 0, so Unsettled includes every row that never needed settling. | Unchanged data logic, per spec. For settle-up use Status = Unsettled + Wrong source only (or the Settlements page). |
| Popover applies on confirm, rest is instant | Two behaviours in one card. | Matches the spec; "Show N" makes the pending state explicit. |
| Live count in popover | One API call per draft change. | Local server, small data — fine. Debounce select changes 150ms. |
| Inline edits change filter membership | Editing Ideal Source on a "Wrong source only" view can make the row no longer match. | Keep today's behaviour (row stays until next refetch) but recompute the summary line from the current rows. |
| Bulk selection across filter changes | `selectedTxIds` may hold rows no longer visible. | Unchanged from today. |
| URL state with no router | First use of query params in the app. | Scoped to Transactions (`view=transactions`); cleared on leaving the view. |
| Export unaffected | Export still offers selected / by statement, not "current view". | Decided (§8 Q7). Can be revisited. |

---

## 8. Decisions (2026-11-01)

1. **Table scope:** filters only; table untouched.
2. **Statement vs Period:** statement overrides; Period disabled, reads "from statement".
3. **Default Period:** latest month with data.
4. **Who-paid labels:** keep today's names — Paid By (account owner), Actual Source (`paid_by`), Ideal Source (`ideal_paid_by`).
5. **Visuals:** Tally design tokens and control sizes; spec provides layout/structure only.
6. **Total:** net sum of all filtered rows.
7. **Export:** unchanged.

---

## 9. Deviations from the build spec

| Spec says | This PRD | Why |
|---|---|---|
| Partner | JANICE | Real owner name in Tally. |
| "Paid by" / "Paid from (actual)" / "Should come from" | Paid By / Actual Source / Ideal Source | Decision 4. |
| Statement locks Period to its calendar month | Statement overrides Period; no month filter sent | Card cycles span two months (Decision 2). |
| Period defaults to current month | Latest month with data | Current month is usually empty (Decision 3). |
| Search description, note, amount | Description + amount | No note field exists. |
| Header "Export N rows", export filtered rows | Export unchanged | Decision 7. |
| Table: 8 read-only columns, status pill | Existing table unchanged | Decision 1. |
| Spec hex tokens, 44px controls | `DESIGN-SYSTEM.md` tokens, existing control sizes | Decision 5. |

---

## 10. Acceptance criteria

- [ ] Primary row holds exactly: Search, Period, Statement, Status, More filters — in that order.
- [ ] Every dropdown button shows field name + value; non-default controls are active-styled.
- [ ] Category, Type, Paid By, Actual Source, Ideal Source and Wrong source only live in the popover.
- [ ] More filters badge = number of active hidden filters; chips row lists them; each chip removes its filter.
- [ ] Wrong source only returns exactly the rows the Settlements page considers (`ideal_paid_by` set and ≠ `paid_by`).
- [ ] Picking a statement shows all its rows regardless of month; Period shows "from statement" and is restored on Any.
- [ ] Transactions opens on the latest month with data.
- [ ] Summary shows filtered count of total, net total, and a settle-up line that matches the Settlements page for the same rows; all update on filter change and inline edit.
- [ ] Amount search finds a row by "642500", "642.500" or "Rp 642.500".
- [ ] Popover: live "Show N", applies only on confirm; Esc / × / outside click discard; Reset these resets only popover fields; focus trapped and returned.
- [ ] Clear all resets everything to defaults and is hidden at defaults.
- [ ] Filters persist in the URL and survive reload; leaving Transactions clears the query string.
- [ ] Table, inline editing, bulk actions and Export behave exactly as before.
- [ ] Existing filters' results are unchanged for the same inputs; tests in §6.4 pass.
