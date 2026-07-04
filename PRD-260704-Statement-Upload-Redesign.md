# PRD — Statement Upload Flow Redesign

**Date:** 2026-07-04
**Author:** Shan Sebastian (with Claude Code)
**Status:** Draft — pending implementation

---

## 1. Problem

The current statement upload flow has three friction points, observed during real monthly use:

1. **No coverage visibility.** There is no way to see at a glance which statements have been uploaded per account per month. Example: "CC Jenius June is uploaded, but has CC Maybank June been done?" requires scanning the flat upload list on the Statements page, per account, and mentally diffing against the calendar.

2. **Painful crosschecking.** Verifying that Claude extracted the transactions correctly requires alt-tabbing between Tally and the PDF open in Adobe Acrobat, comparing line by line. The uploaded file is discarded server-side after extraction, so the app itself can never show it.

3. **The review total never matches the statement.** The review header shows `23 transactions · Rp 9.464.354`, computed as the sum of **all** DB rows — including negative rows like card payments (`PAYMENT FROM IBS −13.919.826`) and refunds. This number matches nothing printed on the statement, so it provides no confidence signal; the only way to verify is issue 2's line-by-line crosscheck.

### Current-state facts (from code exploration)

- Duplicate detection already keys on `(account_id, statement_month)` (`check_duplicate`, `db.py`), and `GET /api/statements` already returns every upload's `statement_month` and `staged_count`, grouped by account. A coverage matrix needs **no new data model**.
- `POST /api/upload` reads the file into memory, sends it to Claude, and discards it. The `uploads` table stores only the filename string. A review reopened later via Statements → "Review →" has no file available.
- The review modal is a full-screen overlay (`position:fixed; inset:0`) with a ~700px-wide table — ample room for a split layout.
- The Upload view is a 3-step wizard (`#view-upload`): account picker, drop zone (+ PDF password row), Analyze button, plus a duplicate-warning card. All of its JS (`doUpload`, `onFileSelect`, drag/drop handlers, `confirmDuplicate`) is reusable as-is.

---

## 2. Goals

- Answer "which statement am I missing?" in one glance, from a single page.
- Crosscheck extracted rows against the source document **without leaving Tally**.
- Make the review total self-explanatory and automatically verified against the statement's printed figures.

## 3. Non-goals

- Permanent statement archive (files are deleted once the review is resolved).
- Multi-file / batch upload.
- Coverage tracking for cash accounts (manual entry only, no statements exist).
- Changing the extraction quality itself (prompt content beyond the new summary fields).

---

## 4. Feature 1 — Kill the Upload page; Statements becomes the upload hub

### 4.1 Behaviour

- The **Upload nav item and `#view-upload` are removed**. `navigate()` drops to five views: Dashboard, Transactions, Settlements, Accounts, Statements.
- The Statements page gains a **coverage matrix** at the top:
  - **Rows:** all credit and debit accounts (cash accounts excluded).
  - **Columns:** fixed rolling window of the **last 6 calendar months**, current month included, newest on the right.
  - **Cell states:**

    | State | Condition | Visual | Click action |
    |---|---|---|---|
    | Uploaded | upload exists for `(account, month)`, `staged_count = 0` | ✓ check, muted/success styling | scroll to / highlight that upload's row in the list below |
    | Pending review | upload exists, `staged_count > 0` | ⏳ badge, warning styling | open the review modal (`openReviewModal(upload_id)`) |
    | Missing | no upload for `(account, month)` | empty cell with subtle `+` on hover | open the upload modal with the account preselected |

- **Upload becomes a modal**, reusing the existing wizard verbatim (account select, drop zone, PDF password row, status/error states, duplicate-warning card). Launched from:
  - any **missing cell** (account preselected; the expected month is shown as a hint — the actual month is still derived from the PDF as today), or
  - a general **"Upload statement"** button in the Statements page header (no preselection).
- After a successful upload the modal transitions to the review flow exactly as today ("Review now →"), and the matrix + list refresh on close.

### 4.2 Notes & edge cases

- Month attribution stays exactly as today: `statement_month` derived from the billing date / printed period, never from the upload date. A Maybank statement billed 11/06 covering mid-May→mid-June fills the **June** cell.
- If the derived month differs from the cell the user clicked (e.g. clicked "June", PDF turns out to be May's), no error — the upload lands in its true month and the clicked cell simply stays missing. The success state should surface the derived month so this is noticeable.
- Accounts created mid-window show missing cells for months before they existed; acceptable for a fixed 6-month window (explicitly chosen over per-account start dates).
- Multiple uploads in one `(account, month)` (duplicate override path): cell counts as Uploaded/Pending based on the most recent upload; the list below remains the source of detail.

### 4.3 Implementation surface

- `templates/index.html` only: remove nav item + view, add matrix rendering in `loadStatements()` (all data already present in the `/api/statements` response), re-home the upload wizard markup into a modal overlay. **No backend changes.**

---

## 5. Feature 2 — Side-by-side document pane in the review modal

### 5.1 Behaviour

- The review modal body splits into two panes:
  - **Left (~55%):** the existing staged-transactions table, unchanged behaviour (inline edit, delete, Real? checkbox, CR context section for debit).
  - **Right (~45%):** the uploaded document — PDF rendered via `<embed>`/`<iframe>` (native browser viewer gives scroll + zoom for free), images via `<img>`.
- The pane is **collapsible** (toggle in the modal header); collapsed state gives the table full width, matching today's layout.
- Works both in the **immediate post-upload review** and when **reopening from Statements** ("Review →") — which requires server-side persistence.

### 5.2 File lifecycle: persist until confirmed

- On `save_staged()`, write the file to `data/statements/<upload_id>.<ext>` (`ext` ∈ pdf/jpg/jpeg/png). The `data/` directory is already gitignored.
- Store the **decrypted** bytes for password-protected PDFs (BCA-style), so the browser can render them without prompting.
- New endpoint: `GET /api/uploads/<id>/file` — serves the file with the correct `Content-Type`; **404 if absent**.
- **Delete the file** in both `confirm_upload()` and `discard_upload()`. No archive is kept — the file exists only while a review is pending.
- The duplicate-override path (`POST /api/upload/confirm` → `save_staged`) must persist the file identically.

### 5.3 Edge cases

- **File missing** (uploads confirmed before this feature, or file manually deleted): the pane shows a quiet "document no longer available" placeholder, or auto-collapses. Never an error state.
- Orphan cleanup: on `init_db()` (startup), delete any `data/statements/*` file whose `upload_id` has no staged rows — covers crashes between confirm and file deletion.
- 20 MB max upload already enforced (`MAX_CONTENT_LENGTH`); no additional size handling needed.

### 5.4 Implementation surface

- `db.py`: file write in `save_staged`, file delete in `confirm_upload` / `discard_upload`, startup orphan sweep.
- `app.py`: pass (decrypted) bytes + extension into `save_staged`; new `GET /api/uploads/<id>/file` route.
- `templates/index.html`: split layout in `renderReviewContent()`, collapse toggle, missing-file placeholder.

---

## 6. Feature 3 — Reconciliation header (the statement equation)

### 6.1 Extraction changes

Both prompts additionally extract the statement's **printed summary figures** (nullable — some statements may not print them legibly):

| Account type | Fields |
|---|---|
| Credit (`build_extraction_prompt`) | `previous_balance`, `total_payments_credits`, `total_new_transactions`, `new_balance` (total tagihan) |
| Debit (`build_debit_extraction_prompt`) | `opening_balance`, `total_credits`, `total_debits`, `closing_balance` |

Stored as new nullable columns on the `uploads` table (via the existing `ALTER TABLE` migration pattern in `init_db()`), returned by `GET /api/uploads/<id>/staged`.

### 6.2 Review header redesign

Replace the single misleading sum with a **reconciliation panel**:

1. **Subtotal breakdown** (always shown, even when printed figures are missing):
   - **Purchases** — sum of positive DB rows
   - **Refunds/credits** — sum of negative DB rows *excluding* card payments
   - **Payments** — the payment rows (e.g. `PAYMENT FROM IBS`), listed but visually set apart as "not an expense"
2. **Printed-total check** (when extracted): extracted purchases+refunds sum vs printed `total_new_transactions` → **✓ match** (green) or **⚠ Rp Δ** (amber, showing the exact delta so the missing/extra row is easy to hunt).
3. **Full equation line** (when all figures extracted):
   - Credit: `previous_balance − payments + new transactions = new_balance` — each term shows printed value; the equation result is checked against printed `new_balance`.
   - Debit: `opening_balance + credits − debits = closing_balance`, with extracted DB/CR row sums checked against printed `total_debits` / `total_credits`.
4. **Tolerance:** Rp 1 for rounding. Anything larger is a mismatch.
5. **Degradation:** if Claude can't find printed figures, the panel shows the subtotal breakdown only — no false "match" claims.

Distinguishing a "payment" row from a "refund" row (both negative): payment rows are the ones the extraction already flags `is_real_expense = false` with payment-like descriptions; the PRD accepts the heuristic *negative + not-real-expense = payment or refund, grouped together* if per-row payment tagging proves unreliable — the equation check still works since payments come from the printed figure, not row classification.

### 6.3 Implementation surface

- `app.py`: prompt schema additions (both builders), parse + pass summary fields through to `save_staged`.
- `db.py`: `uploads` columns + migration, include fields in `get_staged` response.
- `templates/index.html`: reconciliation panel in `renderReviewContent()` replacing the current one-line total.

---

## 7. Success criteria

1. From the Statements page, a missing statement (e.g. CC Maybank June) is identifiable **in one glance** with zero clicks; uploading it takes ≤ 2 clicks from that observation.
2. A full statement review (23 rows) is completed **without opening Acrobat once**.
3. On a correctly extracted statement, the review header shows a **green match** against the printed total — verification takes seconds, not a line-by-line pass. On a bad extraction, the shown delta narrows the hunt.
4. No statement PDFs accumulate on disk: `data/statements/` is empty whenever no review is pending.

## 8. Open questions

1. Should the Uploaded ✓ cell open a read-only view of confirmed transactions for that statement (filtered Transactions view) instead of just scrolling to the list row?
2. Rolling window length: 6 months confirmed for v1 — revisit whether older gaps matter once habit forms.
3. For debit statements with running-balance columns, should the extraction also verify per-row against the running balance (stronger check, more prompt complexity)? Deferred.

## 9. Rollout / sequencing

Independent, in value order:
1. **Feature 1** (frontend-only, no backend risk) —
2. **Feature 3** (prompt + schema + header) —
3. **Feature 2** (file persistence + split pane).

Each ships with its own commit; existing tests must pass (`pytest`), plus new `db.py` tests for file lifecycle (Feature 2) and migration columns (Feature 3).
