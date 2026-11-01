# Transactions Filter Bar — Build Spec

Nov 1, 2026 · @Shan

## Context and goals

Rebuild the Transactions filter bar as Direction A: four primary controls in one row, the rest behind a **More filters** popover, and every active hidden filter shown as a removable chip. Visual reference: [Transactions Filter Redesign canvas](https://claude.ai/artifact/Ummk8KmAV7rfHDmFuYujFs) (artboards A and A-open).

The screen is a desktop-only household finance dashboard for two people (Shan and Partner) with three accounts: Shan's, Partner's and Joint. It serves three jobs, in this order of weight:

1. **Reconcile** a bank statement against recorded transactions.
2. **Settle up**: find payments made from the wrong account and see who owes whom.
3. **Find** one specific transaction.

Problems with the current bar this spec fixes:

- All 9 filters have equal weight across two wrapping rows, so nothing signals which ones matter.
- Several controls show a value but not what they filter ("Real / Non", "Settled / All", "Paid By").
- "Actual Source" vs "Ideal Source" is jargon, and the most useful question it answers ("was this paid from the wrong account?") needs two dropdowns to ask.
- There is no result count, total or summary of active filters, so after filtering you can't tell what you're looking at.

## Filter model

Keep all 9 existing filters and their data logic; change labels, control types and placement only. One new derived filter, **Wrong source only**, is added.

| Current label | New label | Values | Default | Control | Placement |
| --- | --- | --- | --- | --- | --- |
| Search… | Search | Free text: description, note, amount | Empty | Text input with search icon | Primary row |
| All Months | Period | Month list, newest first; "All time" | Current month | Dropdown button, shows "Period · Oct 2026" | Primary row |
| All Statements | Statement | "Any" + one option per statement, e.g. "Joint · Oct 2026" | Any | Dropdown button, shows "Statement · Any" | Primary row |
| Settled / All | Status | All · Unsettled · Settled | All | 3-segment toggle | Primary row |
| All Categories | Category | "Any category" + categories | Any | Select | More filters › What |
| Real / Non | Type | All · Real spend · Transfers & adjustments | All | 3-segment toggle + one-line hint | More filters › What |
| Paid By | Paid by | Anyone · Shan · Partner · Joint | Anyone | 4-segment toggle | More filters › Who paid & from where |
| Actual Source | Paid from (actual) | "Any account" + Shan · Partner · Joint | Any | Select | More filters › Who paid & from where |
| Ideal Source | Should come from | "Any account" + Shan · Partner · Joint | Any | Select | More filters › Who paid & from where |
| *(new)* | Wrong source only | On / off; true when actual ≠ should-come-from | Off | Checkbox card with hint | More filters › Who paid & from where |

Type hint copy: "Real spend is money that left the household. Moves between your own accounts count as transfers." Wrong-source hint: "Paid from a different account than it should have been — these are what needs settling."

**Statement sets Period.** Picking a statement sets Period to that statement's date range and locks the Period button, which then reads "Period · from statement" (e.g. Statement "Joint · Oct 2026" → 1–31 Oct 2026). Setting Statement back to Any unlocks Period and restores the value it had before.

## Layout

The page stacks four bands top to bottom: header, filter card, result summary, table. Max content width 1360 px, centred, 24 px side padding.

1. **Header row.** "Transactions" (36 px, bold) left; **+ Add** (primary) and **Export N rows** (secondary) right. The export label shows the filtered row count.
2. **Filter card, primary row.** One flex row, wraps if narrow, 8 px gap, in this order:
   - Search, grows to fill (min 280 px).
   - Period button.
   - Statement button.
   - Status segmented toggle.
   - **More filters** button with a count badge of active hidden filters.
3. **Filter card, chips row.** Shown only when at least one More-filters filter is active. Dashed top divider; label "Also filtering"; one chip per active hidden filter, e.g. "Type: Real spend ×", "Paid by: Shan ×", "Wrong source only ×"; **Clear all** text button right-aligned.
4. **Result summary line** (outside the card): "**5** of 318 transactions · Total **Rp 2.140.000**" and, when any filtered rows are unsettled with a wrong source, a settle-up line in amber: "Joint owes Shan **Rp 2.140.000**". Sort indicator right.
5. **Table.** Columns: Date · Description · Category · Paid by · Source (actual → should be) · Statement · Amount (right-aligned, tabular numerals) · Status pill. A wrong-source cell renders as "Shan → Joint" in amber bold; a matching source shows one account name.

**More filters popover.** 440 px wide, anchored below the More filters button, right-aligned to the card. Sections:

- Header: "More filters" + close (×).
- **What**: Category select; Type segmented toggle + hint.
- **Who paid & from where**: Paid by segmented toggle; Paid from and Should come from selects side by side; Wrong source only checkbox card (green tint when on).
- Footer: "Reset these" text button left (resets only the popover's filters); primary button "Show N transactions" right, with a live count.

## Behavior and states

- **Labels always name the field.** Every dropdown button renders as muted field name + value ("Period · Oct 2026"), never the value alone.
- **Active styling.** A primary control whose value differs from its default gets a green border and light green fill. More filters gets the same style plus its badge when any hidden filter is active.
- **Chips mirror hidden filters only.** Primary-row filters already show their value, so they never appear as chips. Removing a chip clears that one filter and updates results immediately.
- **Clear all** resets every filter, primary and hidden, to its default. It is hidden when everything is at default.
- **Popover applies on confirm.** Changes inside More filters preview the count on the button ("Show N transactions") and apply on click. Esc or × closes without applying. Clicking outside closes without applying.
- **Instant elsewhere.** Search (debounced 250 ms), Period, Statement and Status apply immediately.
- **URL state.** Every non-default filter is written to the query string (e.g. `?period=2026-10&status=unsettled&paidBy=shan&wrongSource=1`) so a filtered view can be bookmarked and survives reload.
- **Summary updates with the results.** Count, total and settle-up line recompute on every change. The settle-up line nets wrong-source unsettled amounts per account pair, e.g. paid from Shan, should be Joint → "Joint owes Shan".
- **Export respects filters.** Export CSV exports exactly the filtered rows; the button label carries the count.
- **Empty state.** Zero results: replace the table with "No transactions match these filters" plus a **Clear all** button and, if one filter alone would bring results back, a hint naming it.
- **Keyboard and access.** All controls are real `button`, `select`, `input` elements; segmented toggles use `aria-pressed`; the popover is a `role="dialog"` that traps focus and returns it to More filters on close; chip remove buttons carry `aria-label="Remove <filter> filter"`. Minimum control height 44 px.

## Visual tokens

Taken from the current Transactions screen; reuse the app's existing variables where they already exist. Font: the current system sans (-apple-system, Helvetica Neue, Arial).

| Token | Value | Use |
| --- | --- | --- |
| Page background | #F4F2EE | Cream page ground |
| Surface | #FFFFFF | Filter card, table, popover |
| Border | #E6E1D8 | Cards, table dividers |
| Control border | #D8D3C9 | Inputs, buttons, toggles |
| Text | #1F1E1B | Body, values, selected segment fill |
| Muted text | #6E6A62 | Field names, table headers, hints (5.3:1 on white) |
| Accent | #2F7A5B | + Add, More filters badge, links, Clear all |
| Accent tint | #EEF5F1 / border #CFE3D8 | Active controls, chips, wrong-source checkbox card |
| Warning text | #8A4B0F | Wrong-source cells, settle-up line, Unsettled pill |
| Warning tint | #FBEFDC | Unsettled pill, settle-up background |
| Radius | 10 px controls · 16 px cards · 999 px chips |  |
| Control height | 44 px (chips 32 px) |  |
| Section labels | 12 px, semibold, uppercase, 0.08em tracking | "Also filtering", popover groups |

Currency renders as "Rp 2.140.000" (Indonesian thousands separator, no decimals).

## Acceptance checklist

- [ ] Primary row holds exactly: Search, Period, Statement, Status, More filters, in that order.
- [ ] Every dropdown button shows field name + value.
- [ ] Category, Type, Paid by, Paid from, Should come from and Wrong source only live in the More filters popover.
- [ ] More filters badge counts active hidden filters; chips row lists them and each chip removes its filter.
- [ ] Wrong source only returns rows where actual source ≠ should-come-from.
- [ ] Summary shows the filtered count, total amount and settle-up line, and all three update with filters.
- [ ] Export label and output match the filtered rows.
- [ ] Filters persist in the URL and survive reload; picking a statement sets and locks Period to its date range.
- [ ] Clear all resets everything; Reset these resets only the popover.
- [ ] Empty state, focus trap, Esc to close and 44 px targets all work.
- [ ] Colors match the Visual tokens table; existing data logic is unchanged.
