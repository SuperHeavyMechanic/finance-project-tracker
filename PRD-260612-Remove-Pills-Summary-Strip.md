# PRD-260612: Remove Dashboard Month Pills + Summary Strip

> **Task 1 of 2.** Ships independently and first. Companion: `PRD-260612-Dashboard-Delta-Budget-Cards.md` (Task 2, later), which adds the replacement cards (month delta + budget vs actual). This task is **pure removal, frontend-only** — no schema changes, no new routes, nothing added.

## Problem

The top of the Dashboard (month pills + summary strip: total card, biggest purchase, top-3 categories) duplicates information the stacked trend chart already shows — month totals are drawn above each bar by `stackTotalsPlugin`, and category composition is visible in the bar segments and breakdown panel. With only ~4 months of data, the chart itself acts as the month selector, so a pill-driven single-month summary adds nothing. The strip is also half-broken: `selectDashMonth` drops `tx_count` and `biggest` and refetches the API redundantly.

## Goals

- The dashboard opens directly on the trend chart + breakdown panel, with no duplicate layer above them.
- Dead/broken UI (`selectDashMonth`, pill row) is deleted, not preserved.
- Zero backend changes — this ships from `templates/index.html` alone.

## Non-Goals

- Adding anything in the strip's place — the month-delta card and budget-vs-actual card are **Task 2** (see companion PRD).
- Settlement status or ideal-source split on the dashboard (ruled out in discovery).
- Any change to the trend chart, `stackTotalsPlugin`, owner tabs, or the breakdown panel — **explicitly untouched**.
- API or schema changes. `summary.biggest` / `summary.top_categories` / `summary.total` / `summary.tx_count` remain in the `/api/dashboard` payload (merely unused after this task); backend cleanup is deferred to Task 2's backend pass.

## User Stories

- As Shan, I want the dashboard free of the month pills and duplicate summary cards so that the trend chart is the single source for per-month totals and composition.

## Functional Requirements

1. Remove the month-pill row: the `#dash-months` div from the dashboard markup and the pill-building block in `loadDashboard()`. (Generic `.month-pill` / `.month-pills` CSS may remain; touch CSS only if it becomes dashboard-dead.)
2. Delete the `selectDashMonth` function and the `dashMonth` state variable entirely.
3. Remove the summary strip: the `#dash-summary` div from the dashboard markup, the `renderSummary` function, and its call in `loadDashboard()`.
4. `loadDashboard()` after this task: one `/api/dashboard` fetch → `renderTrend(data.trend)`. Nothing else.
5. Owner tabs continue to work exactly as today (re-run `loadDashboard()` filtered by `ideal_paid_by`).
6. Layout: the trend chart + breakdown panel row moves up to sit directly under the owner tabs, with sensible spacing — no orphaned empty grid.

## Edge Cases & Error States

- **No data at all** (fresh DB): unchanged behaviour — `get_dashboard_data` synthesises empty months and the chart renders empty; nothing above it to break.
- No other new edge cases: this change removes states, it does not add any.

## Data Model Changes

None.

## API Changes

None. (The `summary` object in `/api/dashboard` becomes unconsumed; removal from the payload and from `get_dashboard_data` is deferred to Task 2, which reworks that response anyway.)

## Acceptance Criteria

1. Dashboard renders with no month pills and no summary cards; the chart row sits directly under the owner tabs.
2. `selectDashMonth`, `dashMonth`, `renderSummary`, `#dash-months`, and `#dash-summary` no longer appear in `templates/index.html`.
3. Owner tab switching still reloads the chart, filtered by `ideal_paid_by`.
4. Clicking a bar segment still opens the breakdown panel with inline edit working.
5. Network panel shows a single `/api/dashboard` call on dashboard load and per tab switch — same as before.
6. Trend chart (including `stackTotalsPlugin` month totals) renders identically to before the change.
7. `pytest` passes unchanged (no backend was touched).

## Open Questions

None.
