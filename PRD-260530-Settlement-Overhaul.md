# PRD-260530: Settlement View Overhaul

## Problem

The Settlements view has two distinct problems that make it unreliable for day-to-day use.

First, the view has no high-level summary of what is owed. It jumps straight to individual transaction rows grouped by month and direction, which requires the user to mentally total up amounts across cards to understand the net picture. There is no single answer to "how much does SHAN owe JANICE right now?"

Second, the Settled History section lives on the same page as the outstanding Settlement Needs section with no meaningful separation. Users cannot tell at a glance whether they are looking at something that still needs action or something already resolved. This creates confusion and erodes trust in the view.

Third, JOINT is treated as a transparent pass-through in the current balance banner rather than as a genuine third settlement party. When `paid_by=JOINT` and `ideal_paid_by=SHAN`, the joint account fronted money that SHAN must repay — this is a real settlement obligation that should appear in the outstanding balance summary, not be silently dropped.

## Goals

- Users can see the total outstanding amount owed per direction at a glance, without scrolling or mental arithmetic.
- Users can clearly distinguish between "things that need action" and "things already resolved."
- The balance summary correctly reflects all three possible parties (SHAN, JANICE, JOINT) as settlement peers.

## Non-Goals

- Partial settling of individual transactions within a direction-card. The existing "Settle this" button settles the entire direction-card for a month; this behaviour is not changing.
- User-editable settlement date. The settlement date remains today's date at time of clicking.
- Un-settle flow. Reversing a settlement is still done via the Transactions view.
- Any changes to the underlying settlement trigger logic (`ideal_paid_by IS NOT NULL AND ideal_paid_by != paid_by`).
- Layout and visual design decisions for the separation of outstanding vs. history sections — these are deferred to the UI designer. This PRD defines what information belongs in each section and the rules that govern it; not how it looks.

## User Stories

- As Shan or Janice, I want to see a summary of every outstanding settlement obligation (per direction) so I know exactly what needs to be paid without reading individual transactions.
- As Shan or Janice, I want the balance summary to include obligations involving the JOINT account so nothing is hidden.
- As Shan or Janice, I want outstanding settlement needs and settled history to be clearly separated so I can focus on what still needs action.

## Functional Requirements

**Balance Summary**

1. The balance summary must display one line per outstanding settlement direction. A direction is defined as a unique `(ideal_paid_by, paid_by)` pair across all unsettled transactions (i.e. `settled=0`).

2. Valid directions include any combination of SHAN, JANICE, and JOINT. All six permutations are possible: SHAN→JANICE, JANICE→SHAN, SHAN→JOINT, JOINT→SHAN, JANICE→JOINT, JOINT→JANICE. Only directions that have at least one unsettled transaction with `amount > 0` must appear.

3. Each direction line must display: the from-party, the to-party, and the total outstanding amount (sum of `amount` for all unsettled transactions matching that direction, across all months).

4. Directions are not netted against each other. If SHAN→JANICE is Rp 500,000 and JANICE→SHAN is Rp 200,000, both lines appear separately. The summary does not collapse them into a net Rp 300,000 SHAN→JANICE figure.

5. If there are no unsettled transactions at all, the balance summary must display a clear "all settled" state.

6. The balance summary must reflect only unsettled transactions. Settled transactions must not affect any total in the summary.

**Outstanding Section**

7. The outstanding section lists only transactions where `settled=0`, `ideal_paid_by IS NOT NULL`, `ideal_paid_by != paid_by`, `is_real_expense=1`, and `amount > 0`. This is the existing `get_settlements()` filter; no change to the query.

8. Transactions in the outstanding section remain grouped by transaction month first, then by direction within each month. This grouping is unchanged.

9. The existing owner-filter tabs (All / SHAN owes / JANICE owes) must be extended to include a **JOINT owes** tab. The filter applies to the outstanding section only.

10. "SHAN owes" tab must show directions where `ideal_paid_by=SHAN` (i.e. SHAN→JANICE and SHAN→JOINT). "JANICE owes" tab must show directions where `ideal_paid_by=JANICE`. The new "JOINT owes" tab must show directions where `ideal_paid_by=JOINT`.

**Settled History Section**

11. The settled history section must be visually and structurally separated from the outstanding section. The exact mechanism (tab, separate panel, divider, distinct background) is left to the UI designer.

12. The settled history section lists only transactions where `settled=1`. These transactions must not appear anywhere in the outstanding section or balance summary.

13. Within the settled history section, transactions must be grouped by the month of `settled_date` (not `date_parsed`). Within each settled-month group, transactions must be further grouped by direction (the same `ideal_paid_by→paid_by` key used in the outstanding section). This direction-level grouping is currently missing from the history section and must be added.

14. Each direction group in history must show: the direction label, the total amount for that direction in that settled month, and the `settled_date`.

## Edge Cases & Error States

- A transaction where `ideal_paid_by=JOINT` and `paid_by=SHAN` (JOINT owes SHAN): must appear in the outstanding section as a JOINT→SHAN card and as a JOINT→SHAN line in the balance summary. The "JOINT owes" filter tab must reveal it.
- A transaction where `settled=1` but `settled_date` is NULL (possible from manual edits via the Transactions view): group it under an "Unknown date" bucket in the history section rather than crashing or silently dropping it.
- A month/direction card where all matching transactions sum to zero after filtering: the card must not render. The existing `amount > 0` filter in `get_settlements()` handles this at the row level, but the frontend grouping logic must also suppress any direction card whose computed total is zero or less.
- When an owner-filter tab is active and no outstanding transactions match that filter: display an explicit "No outstanding settlements" message in the outstanding section rather than a blank area.
- The balance summary totals must be derived from the same `/api/settlements` payload already fetched for the page. No additional API call is permitted for the balance summary.

## Data Model Changes

None. All required data (`settled`, `settled_date`, `ideal_paid_by`, `paid_by`, `amount`, `is_real_expense`, `date_parsed`) already exists on the `transactions` table.

## API Changes

None required. The existing `GET /api/settlements` endpoint already returns all settlement-eligible transactions (both settled and unsettled) with the fields needed to compute direction groupings, balance totals, and history. The frontend derives all views from this single payload.

If at implementation time a field is found to be missing from the payload, the engineer should add it to the `SELECT` in `get_settlements()` in `db.py` — not create a new endpoint.

## Open Questions

- Should the balance summary also appear in a condensed form on the Dashboard? Not scoped here; raise as a separate request if needed.
- The "JOINT owes" tab label may be ambiguous since JOINT is an account rather than a person. The UI designer should consider whether the label needs a tooltip or alternate wording.

---

**Key files for the engineer and UI designer:**

- `templates/index.html` — `loadSettlements()` (around line 1429), `openSettleModal()` (around line 2070), `setSettleTab()` (around line 1422), and `.settle-*` CSS classes (around lines 170–182)
- `db.py` — `get_settlements()` (line 421) and `bulk_settle_transactions()` (line 435)
- `app.py` — `api_settlements()` (line 331) and `api_settle_batch()` (line 336)
