# PRD-260612: Dashboard Cards — Month Delta + Budget vs Actual

> **Task 2 of 2.** Builds on `PRD-260612-Remove-Pills-Summary-Strip.md` (Task 1), which must ship first — after Task 1 the dashboard top is empty; this task adds the two replacement cards. This is the only task of the two that touches the **DB schema and API** (breaking-change risk: migration required).

## Problem

After Task 1 the dashboard shows the trend chart and breakdown panel only. Two review questions remain unanswered on screen: "is this month unusual vs last?" (Shan eyeballs bar heights — nothing quantifies the change) and "are we on track against our monthly target?" (Shan and Janice have a monthly spending target, but the app has no concept of it — they hold it in their heads and compare manually).

## Goals

- The top of the dashboard surfaces only information the trend chart cannot: quantified month-over-month change, and progress against the household's monthly target including mid-month pace.
- The household target lives in the app, survives reloads, and is shared between both users' sessions.
- Setting or changing the target takes two clicks on the dashboard itself — no settings page.

## Non-Goals

- Per-category budgets.
- Per-person targets (the budget is a joint household number).
- Per-month budget history — changing the target applies to all months, past and future, in v1.
- Clearing a target once set (only unset → set and set → different value).
- A settings page or any budget UI outside the dashboard card.
- Settlement status or ideal-source split cards (ruled out in discovery).
- Any change to the trend chart, `stackTotalsPlugin`, owner tabs, or the breakdown panel — **explicitly untouched**.

## User Stories

- As Shan, I want to see this month's real-expense total with the change vs last month so that I can tell at a glance whether spending is drifting without eyeballing bar heights.
- As Shan or Janice, I want to see how much of our monthly target we've spent so far this month so that we can adjust behaviour mid-month, not after the fact.
- As Shan, I want to set or change the monthly target directly on the dashboard card so that I never need a settings page.
- As Janice, I want the target Shan set to appear in my browser too so that we're judging against the same number.

## Functional Requirements

### Shared

1. Reintroduce a two-card summary row (restored `#dash-summary` grid or equivalent) between the owner tabs and the chart row, rendering Card A and Card B side by side.
2. "Latest month" for both cards = the most recent month in the trend data returned by `/api/dashboard` (i.e. the most recent month with real-expense data), matching existing `get_dashboard_data` behaviour.
3. Both cards count real expenses only (`is_real_expense=1 AND amount>0`), consistent with all dashboard numbers.
4. Dashboard load and owner-tab switches continue to make a single `/api/dashboard` request.

### Card A — Latest Month Total + Delta

5. Shows: month label (`Jun-26` per the app's Mmm-YY convention), the month's real-expense total (exact Rp via `fmtAmount`), and transaction count.
6. Below the total, a delta line vs the immediately preceding month in the trend data: absolute Rp difference and percent, with direction indicator — e.g. `▲ Rp 412.000 (+13%) vs May-26` or `▼ Rp 210.000 (−6%) vs May-26`. Increase renders in the app's danger/red tone, decrease in success/green.
7. The delta compares against the preceding **trend month as returned by the API**; if that month is not calendar-adjacent (a data gap), still compare against it and label it honestly (`vs Mar-26`) — never against a synthetic zero month.
8. Card A **respects the active owner tab** (filtered by `ideal_paid_by`, as the dashboard does today): switching to SHAN shows Shan's ideal-source total and delta. All Card A data comes from the trend payload — no extra computation server-side beyond what exists.

### Card B — Budget vs Actual

9. A single household-level monthly target amount (IDR integer), one value applying to every month.
10. Shows, for the latest data month: `Rp <spent> of Rp <target>`, a horizontal progress bar (fill = spent ÷ target, width capped at 100%), and a status line:
    - Under target: `Rp <remaining> remaining`, bar in the accent colour.
    - At/over target: `Over by Rp <excess>` in the danger tone, bar full and red.
11. **Mid-month pace:** if the latest data month equals the current calendar month, render a thin vertical pace tick on the bar at `(today's day-of-month ÷ days in month)` and label the spent figure "spent so far". Fill ahead of the tick = spending faster than linear pace. For past (complete) months: no tick, no "so far" wording.
12. **Inline editing:** the card carries a pencil affordance. Clicking it swaps the card body for a numeric input (pre-filled with the current target) with Save/Cancel, following the existing inline-edit pattern (`toggleBpEdit`/`saveBpEdit` style): `toggleBudgetEdit()` / `saveBudget()`. Save PUTs the value then re-renders Card B only. Invalid input (empty, non-numeric, ≤ 0) disables Save.
13. **Household-only — Card B ignores the owner tab** and always shows household spend (ALL) vs target. Rationale: the target is a joint number agreed between two people; comparing one person's `ideal_paid_by` share against the whole-household target is a misleading fraction with no per-person target to anchor it. When a single-owner tab (SHAN/JANICE/JOINT) is active, the card shows a small `Household` caption so the scope is explicit.

## Edge Cases & Error States

- **No target set yet:** Card B renders an empty-state affordance — a `Set monthly target` button/link opening the same inline input as R12. No bar, no fake zero target.
- **Single data month:** Card A shows the total with no delta line (no `vs` row, no `+∞%`).
- **Prior month total is zero:** Card A shows absolute delta only, suppresses the percent (avoid divide-by-zero / `+∞%`).
- **Zero-spend latest month:** Card A shows `Rp 0`; Card B shows full remaining, bar empty.
- **Owner tab with no data in the latest month:** Card A shows `Rp 0` for that owner with delta from that owner's trend; Card B unaffected (household-only).
- **Target validation:** `PUT` with missing, non-integer, zero, or negative amount → `400`; clearing is unsupported in v1.
- **Latest data month is in the past** (no confirmed transactions yet this calendar month): both cards report that past month as complete — no pace tick, no "so far". Consistent with the dashboard anchoring to months that have data.
- **Spent exceeds target mid-month:** over state (R10) takes precedence; pace tick still drawn.
- **Concurrent edit:** last write wins; no locking needed for a two-person household.
- **No data at all** (fresh DB): Card A shows `Rp 0`, no delta; Card B shows the set-target affordance or `Rp 0 of Rp <target>`.

## Data Model Changes

**Schema change — migration required in `init_db()`:**

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

- Budget stored under key `monthly_budget`, value = IDR integer as text. Absence of the row = no target set.
- A generic key-value `settings` table is chosen over a dedicated `budgets` table deliberately: v1 holds exactly one scalar, and this gives future settings a home without further migrations. If v2 ever needs per-month or per-category budgets, that becomes a purpose-built table then.
- New `db.py` functions: `get_setting(key)` / `set_setting(key, value)` — parameterised SQL only, consistent with existing patterns (no f-string SQL).

## API Changes

1. **`GET /api/dashboard`** (modified):
   - Gains top-level `"budget": <int|null>` (null when unset).
   - When `owner != ALL`, additionally returns `"household_latest_total": <int>` — the unfiltered latest-month real-expense total — so Card B never needs a second fetch on tab switches. (Alternative rejected: a second filtered request per tab switch.)
   - Backend cleanup deferred from Task 1: the now-unconsumed `summary.biggest` and `summary.top_categories` (and their queries in `get_dashboard_data`) are removed. `summary.total` / `summary.tx_count` / `summary.month` remain for Card A.
2. **`PUT /api/budget`** (new):
   - Request: `{"amount": 15000000}`
   - Validation: required, integer, `> 0`; else `400 {"error": "..."}`.
   - Response: `200 {"budget": 15000000}`.
3. No other routes change.

## Acceptance Criteria

1. The summary row renders exactly two cards (Card A, Card B) between the owner tabs and the chart.
2. With ≥2 trend months, Card A shows a signed Rp and % delta vs the prior trend month; with 1 month, no delta line; with a zero prior month, absolute delta only.
3. Switching owner tabs updates Card A's total and delta; Card B's numbers never change and the `Household` caption appears on non-ALL tabs.
4. With no target set, Card B shows the "Set monthly target" affordance; entering `15000000` and saving persists across a full page reload and across browsers/sessions.
5. With a target set: an under-target month shows the remaining amount and a partial accent bar; an over-target month shows "Over by Rp X" and a full red bar.
6. When the latest data month is the current calendar month, the bar shows a pace tick at today's linear position and the label reads "spent so far"; for a past month, neither appears.
7. `PUT /api/budget` rejects missing, non-integer, zero, and negative amounts with 400.
8. Dashboard still makes a single `/api/dashboard` call on load and per tab switch.
9. Trend chart (including `stackTotalsPlugin`), owner tabs, and breakdown panel behave identically to post-Task-1 state.
10. New tests cover `get_setting`/`set_setting`, the `budget` and `household_latest_total` fields in the dashboard payload, and `PUT /api/budget` validation — using the in-memory DB fixture, never `data/finance.db`. All existing tests pass.

## Open Questions

None blocking. Deferred to v2 if ever requested: per-person targets, per-month target history, clearing a target, target change audit trail.
