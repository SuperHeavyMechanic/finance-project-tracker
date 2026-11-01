# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./start.sh       # preferred — sets Python 3.9 PATH and starts Flask on port 8080
python3 app.py   # alternative
```

Open at **http://localhost:8080**. Port 5000 is avoided (macOS AirPlay conflict).

`launch_app.sh` is a double-click entry point (wrapped as `Tally.app` via `osacompile`, kept outside the repo on the Desktop): checks if port 8080 is already listening before starting `python3 app.py` in the background, then `open`s the browser. Safe to invoke repeatedly — it won't spawn duplicate servers.

Install dependencies:
```bash
pip3 install flask anthropic python-dotenv pypdf pytest
```

## Running Tests

```bash
pytest                        # run all tests
pytest tests/test_db.py -v    # verbose output
pytest -k "TestParseDate"     # run a single test class
```

Tests point `db.DB_PATH` at a throwaway file under pytest's `tmp_path` via `monkeypatch` — `data/finance.db` is never touched. Two fixtures, both in `tests/test_db.py` (there is no `conftest.py`): `fresh_db` for direct db-layer calls, and `client` for Flask test-client calls against the real routes (`TestManualCoverageApi`, `TestBudgetApi`). `db.DB_PATH` is the single switch for which database the whole app talks to — reassigning it before importing `app` is also how to run the server against a copy of the real DB.

## Environment

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

Three modules at the repo root — `app.py` (routes), `db.py` (all SQL), `rules.py` (prompt
customisation) — plus one HTML file. No build step. `static/` holds the favicon/app-icon
assets Flask serves at `/static/*` (default Flask static config, no custom wiring in `app.py`).
`branding/` holds two standalone icon-generation scripts that the app never imports.

**`db.py`** — all database logic (SQLite via `sqlite3`). Key functions:
- `init_db()` — creates tables, runs `ALTER TABLE` migrations, seeds missing accounts from `SEED_ACCOUNTS` (per-account upsert by `bank + last_four`); also sweeps orphaned statement files from `data/statements/`
- `save_staged(account_id, filename, transactions, statement_date, summary, file_bytes, file_ext)` — creates the upload record and writes transactions to `staged_transactions`; this is the main upload path. `summary` = printed statement figures (generic keys `prev_balance/credits_total/debits_total/new_balance`); `file_bytes`+`file_ext` persist the (decrypted) source document to `data/statements/<upload_id>.<ext>` while the review is pending
- `confirm_upload(upload_id)` — inserts only `transaction_type='DB'` staged rows into `transactions`, then deletes all staged rows for that upload **and the stored statement file**
- `delete_upload(upload_id)` — removes a statement entirely, pending or confirmed: its confirmed `transactions` (by `upload_id`), staged rows, the upload record **and the stored statement file**. Snapshots the DB first via `_backup_db()` (see **Backups**). Deletes children before the parent because `foreign_keys = ON` and the FKs have no `ON DELETE`. Returns the confirmed-row count, or `None` for an unknown id
- `get_upload_file(upload_id)` — returns `(path, ext)` for a pending upload's stored document, or None
- `mark_manual_coverage(account_id, month)` / `unmark_manual_coverage(account_id, month)` / `get_manual_coverage()` — CRUD on the `manual_coverage` table (`(account_id, month)` composite PK). Purely a user-declared bookkeeping flag for the Statements coverage matrix ("I entered this manually"), not tied to any actual transactions. Automatically cleared by `save_staged()` the moment a real upload lands on the same `(account_id, statement_month)` slot
- `get_staged(upload_id)` — returns staged rows joined with account info (includes `account_type`)
- `parse_date(s, ref_date=None)` — normalises bank date formats to YYYY-MM-DD: DD/MM/YYYY, DD-MM-YY, ISO, and month names abbreviated or full, English or Indonesian, with or without separators (`20-Apr-26`, `18 OKT 2026`, `20OCT2026`, `24 Agustus 2026`). Year-less rows (`20SEP`, `09 OKT`, `16/09`) take the year from `ref_date` (the parsed statement date; previous year if the month is later) — the upload route passes it. Unknown month names return None
- `create_transaction(fields)` — direct insert into `transactions` (manual entry, no upload/staging)
- `create_account / update_account / delete_account` — full account CRUD
- `update_transaction(tx_id, fields)` — allowed fields defined by `_ALLOWED_TX_FIELDS` frozenset: `category`, `is_real_expense`, `paid_by`, `ideal_paid_by`, `settled`, `settled_date`, `amount`, `date_parsed`, `description`
- `update_account(acc_id, fields)` — allowed fields defined by `_ALLOWED_ACCOUNT_FIELDS` frozenset
- `update_staged(tx_id, fields)` — allowed fields defined by `_ALLOWED_STAGED_FIELDS` frozenset
- `bulk_settle_transactions(ids, settled_date)` — marks a list of transaction IDs as `settled=1` with the given date in one query
- `get_setting(key)` / `set_setting(key, value)` — generic key-value store (`settings` table); the household monthly budget lives under key `monthly_budget`
- `get_settlements()` — returns transactions matching `_SETTLEMENT_PREDICATE`: `ideal_paid_by IS NOT NULL AND ideal_paid_by != paid_by AND is_real_expense=1 AND amount>0` (Ideal Source ≠ Actual Source, real-spend charges only); **not** `paid_by != account_owner`. The same predicate backs the Transactions `wrong_source` filter and the summary line's "X owes Y", so all three agree

The three `_ALLOWED_*` frozensets at module level are the authoritative whitelist for which columns each update function may touch. Never use f-string SQL outside these functions.

**`rules.py`** — three layers of extraction customisation:
- `GLOBAL_RULES` — keyword → category mappings applied to every account post-extraction
- `ACCOUNT_RULES` — per-bank keyword → category overrides (bank name substring key)
- `BANK_NOTES` — per-bank free-text notes injected into the Claude prompt before the output schema; describes bank-specific quirks (date formats, how to parse descriptions, sections to skip). Entries exist for BCA (debit), BNI, Maybank, HSBC and UOB; keys match as a case-insensitive substring of the account name. Add new bank patterns here first.
- `build_bank_notes(account_name)` / `build_rules_prompt(account_name)` — produce the injected text blocks

**`app.py`** — Flask routes only; no business logic. Key behaviours:
- `_file_magic_matches(file_bytes, media_type)` — validates file content against magic bytes before processing; rejects files whose content doesn't match their extension
- `build_extraction_prompt(rules_section, bank_notes)` — credit card prompt
- `build_debit_extraction_prompt(rules_section, bank_notes)` — debit/bank prompt; generic structure, bank-specific quirks come from `bank_notes`
- `period_to_statement_date(period_str)` — converts "APRIL 2026" → "30/04/2026" (last calendar day of period)
- Upload route branches on `account.account_type`: `debit` uses debit prompt + extracts `period` field; `credit` uses credit prompt + extracts `statement_date`; `cash` accounts are not intended for PDF upload (manual entry only)
- PDF decryption: tries empty-string password first before prompting user (handles BCA-style "encrypted with no password" PDFs)
- Duplicate detection runs before staging; returns `{duplicate:true}` with in-memory transactions so frontend can confirm
- All write endpoints that accept `category` validate it against the `CATEGORIES` list before calling db functions

**`templates/index.html`** — single-file SPA (~3900 lines). Vanilla JS, no chart library (the trend is drawn with CSS flex bars; Chart.js was removed). Five views via `navigate(view)` (Dashboard, Transactions, Settlements, Accounts, Statements — uploading lives in a modal on Statements). Key frontend state: `allAccounts`, `txRows`, `allTxRows`, `selectedTxIds` (Set), `selectedStagedIds` (Set), `_reviewCtx`, `pendingUploadId`, `pendingDuplicate`, `settleOwnerFilter`, `pendingSettleIds`, `_settleByMonth`, `_settleMonths`, `_stmtUploads` (Statements delete lookup). Transactions filter state: `txFilters`, `txMoreDraft`, `txMonths`, `txDefaultPeriod`, `txMenuKind`. Dashboard state: `dashOwner`, `_dashData`, `dashMonth`, `dashCat`, `dashRows`, `dashChecked` (Set), `dashSort`, `dashQuery`, `dashEditId`, `dashHoverCat`, `dashBulkCat`, `_dashUndo`.

## Data Model

Six tables in `data/finance.db` (gitignored):

- **`accounts`** — seeded from `SEED_ACCOUNTS` (5 accounts: 2 credit, 1 debit, 2 cash); also manageable via UI CRUD. `owner` ∈ {SHAN, JANICE, JOINT}; `account_type` ∈ {credit, debit, cash}
- **`uploads`** — one row per statement; `statement_month` (YYYY-MM) derived from `statement_date` (billing date in **original PDF format**, not ISO); survives confirm, deleted on discard. Also holds the printed summary figures (`summary_prev_balance`, `summary_credits_total`, `summary_debits_total`, `summary_new_balance` — credit: prev balance / payments+credits / new transactions / total tagihan; debit: opening / mutasi kredit / mutasi debet / closing) and `stored_ext` (extension of the persisted source file in `data/statements/`, NULL once confirmed/discarded)
- **`staged_transactions`** — pure buffer; holds extracted rows pending review; cleared entirely on every confirm or discard; `transaction_type` ∈ {DB, CR} (CR rows shown for context in debit review but never confirmed)
- **`transactions`** — confirmed rows only; never contains staged or CR data; all downstream views read only this table. `upload_id` is NULL for manually-added transactions.
- **`settings`** — generic key-value store; currently holds `monthly_budget` (household-level IDR integer as text; absence = no target set)
- **`manual_coverage`** — `(account_id, month)` composite PK; marks a Statements coverage-matrix cell as "entered manually" instead of via upload. No FK to transactions — it's a declared checklist state, cleared automatically the moment a real statement is staged for that slot

## Upload & Staging Flow

Uploading starts from the **Statements page**: the coverage matrix at the top (rows = credit/debit
accounts, columns = last 6 calendar months) shows four states per cell — ✓ green uploaded, ✓ blue
entered manually, ⏳ pending review, `+` missing (legend above the matrix). A pending cell opens
the review modal directly; an uploaded cell scroll-flashes to that upload's row in the list below.
A **missing or manually-entered cell** opens the small chooser modal (`#coverage-choice-modal`,
`openCoverageChoice(accountId, month, isManual)`):
- from missing → "Upload a statement" (→ `openUploadModal(accountId, month)`) or "I entered this
  manually" (→ `POST /api/manual-coverage`, marks the cell blue)
- from manually-entered → "Upload a statement instead" (same upload modal, re-clickable to change
  your mind) or "Remove manual entry" (→ `DELETE /api/manual-coverage/<account_id>/<month>`, reverts
  to missing)

The manual flag is purely declarative bookkeeping — it doesn't check for actual transactions. It's
cleared automatically by `save_staged()` the instant a real statement is staged for that same
`(account_id, statement_month)` slot, so choosing "upload instead" and completing a real upload
naturally replaces the blue check with the green one on next load.

```
POST /api/upload
  → validate file magic bytes + decrypt PDF (_read_validated_file)
  → Claude extracts (credit or debit prompt + bank_notes + rules) incl. printed summary figures
  → check_duplicate(account_id, stmt_month)
      if duplicate → return {duplicate:true, transactions, summary} (not staged yet)
  → save_staged() → staged_transactions + uploads record + file to data/statements/<id>.<ext>
  → return {staged:true, upload_id}

Frontend opens review modal (immediate after upload, or via Statements "Review →" / ⏳ cell)
  Reconciliation panel at top: extracted subtotals vs printed statement figures
  (✓ match / ⚠ delta badges, Rp 1 tolerance); updates live on inline edits
  Side-by-side document pane (right, ~45%): GET /api/uploads/<id>/file in <embed>/<img>;
  toggled via "Hide/Show statement"; absent when no stored file (pre-feature uploads)
  Review: inline edit category/description/amount/real, delete rows
  Confirm → POST /api/uploads/<id>/confirm → confirm_upload() → DB rows → transactions; file deleted
  Discard → DELETE /api/uploads/<id> → delete_upload() → upload + staged + file deleted

POST /api/upload/confirm  (duplicate override path)
  → same as above but skips duplicate check; calls save_staged() directly.
  Multipart (frontend re-attaches the file so it can be persisted) or plain JSON (no file stored)

POST /api/transactions  (manual entry path)
  → direct insert into transactions; no upload record, no staging
```

Statement files live only while a review is pending — `data/statements/` is empty whenever
nothing is awaiting review (confirm/discard delete the file; `init_db()` sweeps orphans).

Any statement row on the Statements page — pending or confirmed — has a **trash-icon** button
(`deleteStatement(uploadId)`). The native confirm spells out the transaction count/total and,
when non-zero, how many rows are settled (`settled_count`) or have an outstanding settlement
(`outstanding_settle_count`) — both returned per upload by `get_statements()`. Confirming calls
the same `DELETE /api/uploads/<id>` as review-modal Discard, removing every linked transaction;
the coverage cell reverts to missing and the slot no longer trips duplicate detection.

### Backups

`delete_upload()` copies the whole DB (`sqlite3` `backup()`) to
`data/backups/finance-<timestamp>-before-delete-upload-<id>.db` before deleting anything; only
the newest `BACKUPS_KEPT` (10) are kept. A failed backup aborts the delete. There is **no
in-app restore** by design — to roll back: stop the app, `cp data/backups/<file>.db
data/finance.db`, start the app. That rewinds the entire DB, including anything done after
that delete. The backups dir derives from `DB_PATH`, so tests write under `tmp_path`.

## Settlement Logic

Settlement is needed when **`ideal_paid_by ≠ paid_by`** (Ideal Source ≠ Actual Source). This is distinct from `paid_by ≠ account_owner`.

- `ideal_paid_by` = who *should* pay for the transaction
- `paid_by` = who *actually* paid (Actual Source)
- When they differ, `ideal_paid_by` owes `paid_by` a reimbursement

The Settlements view Outstanding tab renders a **matrix table** (rows = debtor direction, columns = months). Clicking an amount cell opens a sticky 40% right-panel (`#settle-detail-pane`) showing that cell's transactions with inline editing. Key functions: `showSettleDetail(dir, month)` — populates the detail pane and highlights the clicked cell; `toggleSdEdit(id)` / `saveSdEdit(id, dir, month)` — inline edit form that PATCHes `/api/transactions/<id>` then reloads. Module-level `_settleByMonth` and `_settleMonths` cache the last API response so the detail pane can re-render without a new fetch. `POST /api/settlements/settle` bulk-settles a list of IDs with a given date.

## Prompt Architecture (three layers, all in `rules.py` + `app.py`)

| Layer | Source | Purpose |
|---|---|---|
| Prompt structure | `app.py` `build_*_prompt()` | Output schema, field definitions, general rules |
| Bank notes | `rules.py` `BANK_NOTES` | Bank-specific parsing quirks injected before schema |
| Category overrides | `rules.py` `ACCOUNT_RULES` / `GLOBAL_RULES` | Keyword → category mappings, injected + applied post-extraction |

To handle a new bank's quirks: add an entry to `BANK_NOTES` in `rules.py`. Only change `app.py` prompts for structural changes that affect all banks.

When writing a bank note:
- Tell Claude to output `date` and `statement_date` as **DD/MM/YYYY**, saying which date column is the transaction date and which header date is the statement (print) date, not the due date. The credit prompt otherwise keeps the printed format, and year-less formats only parse because `parse_date` falls back to the statement year
- Spell out the number format (e.g. comma = thousands separator) and how credits are marked (`CR` suffix → negative amount, `is_real_expense` false)
- **Never paste card numbers, account numbers or cardholder names from a real statement** — `rules.py` is pushed to GitHub. Use placeholders like `<card number>`
- Sample PDFs live in `statement_samples/` (gitignored, often password-protected). To check a note, decrypt with `pypdf` and read the text, or run the file through `POST /api/upload` with `db.DB_PATH` pointed at a copy of the DB — an existing `(account, month)` returns `{duplicate:true}` with the extracted rows and stages nothing

## Date & Statement Naming Convention

All dates displayed as **DD-Mmm-YY** (e.g. `20-Apr-26`).
- `fmtDate(date_parsed)` — formats YYYY-MM-DD → DD-Mmm-YY
- `fmtDateObj(d)` — formats a JS Date object → DD-Mmm-YY (shared helper)
- `parseStatementDateLabel(statementDate, statementMonth)` — handles raw PDF date formats (DD/MM/YYYY, DD-MM-YYYY, ISO, and month-name forms like `20OCT2026` / `18 OKT 2026` / `24 Agustus 2026` via `STMT_MONTH_NAME_RE` + `STMT_MONTH_MAP`, which mirror `db._MONTH_MAP`) and YYYY-MM month strings; falls back to last day of month when only month is available
- `stmtRef(bank, statement_date, statement_month)` — renders statement badge using `parseStatementDateLabel`

`statement_date` in the DB is stored in the **original PDF format** (e.g. `"11/04/2026"`), not ISO. Always use `parseStatementDateLabel` to display it, never `fmtDate` directly.

Statement month is derived from the **billing date** on the PDF (credit) or the **last day of
the printed period** (debit). Only when that date is missing or unparseable does it fall back to
`_dominant_month(transactions)` — the most common month among the extracted rows. Treat that
fallback as a symptom: if a statement lands in the wrong month, the bank's date format probably
needs a `BANK_NOTES` entry rather than a fix downstream.

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/accounts` | All accounts with tx_count, last_upload, account_type |
| POST | `/api/accounts` | Create account |
| PATCH | `/api/accounts/<id>` | Update account (name, owner, bank, last_four, account_type) |
| DELETE | `/api/accounts/<id>` | Delete account (transactions preserved, lose account link) |
| POST | `/api/upload` | Extract → stage; returns `{duplicate:true}` or `{staged:true, upload_id}` |
| POST | `/api/upload/confirm` | Force-stage a duplicate (skips duplicate check); multipart with file, or JSON |
| GET | `/api/uploads/<id>/staged` | Staged rows for review (includes account_type, summary_*, stored_ext) |
| GET | `/api/uploads/<id>/file` | Serve the stored statement document; 404 once confirmed/discarded |
| GET | `/api/manual-coverage` | All `(account_id, month)` manual-entry markers |
| POST | `/api/manual-coverage` | Mark a cell as entered manually: `{account_id, month}` (month = YYYY-MM) |
| DELETE | `/api/manual-coverage/<account_id>/<month>` | Remove a manual-entry marker |
| PATCH | `/api/staged/<id>` | Edit staged row (category, description, amount, is_real_expense) |
| DELETE | `/api/staged/<id>` | Remove single staged row |
| POST | `/api/uploads/<id>/confirm` | Confirm: DB staged rows → transactions, clear staged |
| DELETE | `/api/uploads/<id>` | Delete a statement (pending or confirmed): backup DB, then remove linked transactions + staged rows + upload record + file; returns `{ok, deleted_count}`, 404 if unknown |
| GET | `/api/transactions` | Filterable list (owner, month, account_id, category, is_real_expense, settled, paid_by, ideal_paid_by, upload_id, q, wrong_source). `q` matching only an amount ("642.500", "Rp 642.500") also matches rows with that exact rounded absolute amount; `wrong_source=1` applies `_SETTLEMENT_PREDICATE` (identical to `get_settlements()`) |
| POST | `/api/transactions` | Manual entry: direct insert, no upload_id |
| PATCH | `/api/transactions/<id>` | Update any allowed field (see `_ALLOWED_TX_FIELDS` in db.py) |
| DELETE | `/api/transactions/<id>` | Delete a confirmed transaction |
| GET | `/api/dashboard` | Trend + summary scoped to months with actual data; `owner` filter applies to `t.ideal_paid_by`, not `a.owner`; also returns `budget` (null when unset) and household-scoped `household_latest_month`/`household_latest_total` for the budget card |
| PUT | `/api/budget` | Set household monthly target: `{amount: <positive int>}`; 400 otherwise; stored via `set_setting('monthly_budget', …)` |
| GET | `/api/settlements` | Transactions where `ideal_paid_by IS NOT NULL AND ideal_paid_by != paid_by` |
| POST | `/api/settlements/settle` | Bulk-settle a list of transaction IDs: `{ids: [...], settled_date: "YYYY-MM-DD"}` |
| GET | `/api/statements` | Uploads grouped by account; includes staged_count for pending-review detection |
| GET | `/api/export` | CSV download; `ids=1,2,3` for selected rows, `upload_id=N` for full statement |

## Key Constraints

- Max upload: 20 MB (`MAX_CONTENT_LENGTH`)
- Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png` — validated by both extension and magic bytes
- Claude model pinned to `claude-sonnet-4-6` in `app.py`
- 14 categories (all-caps) defined in both `app.py` (`CATEGORIES`) and `templates/index.html` (`CATEGORIES` + `CAT_CLASS` + `CAT_COLORS`) — must stay in sync; validated server-side on all write endpoints
- Owners: SHAN, JANICE, JOINT — hardcoded in UI dropdowns (filter bars, modals, action bar); not derived from DB
- Actual Source (`paid_by`) values: SHAN, JANICE, JOINT — CASH is an account type, not a paid_by value
- CSV `Amount` column: IDR integer only (`int(round(amount))`), no foreign currency, no decimals; rows sorted ascending by date
- `allAccounts` is refreshed from the API every time `loadAccounts()` runs — the Add Transaction modal always reflects the current account list
- Dashboard `owner` tab filters by `t.ideal_paid_by` (Ideal Source), **not** by `a.owner` (account ownership) — this applies to both the trend (`get_dashboard_data` in `db.py`) and the category panel (`loadBreakdown` in `index.html`, which passes `ideal_paid_by=` to `/api/transactions`)
- Dashboard layout is a full-height two-pane workspace (see **Dashboard Layout** below), not stacked summary cards
- Settlements detail pane: `showSettleDetail(dir, month)` renders cell-level transactions in the right panel; `toggleSdEdit(id)` / `saveSdEdit(id, dir, month)` provide the same inline-edit pattern scoped to the settlements context
- Dashboard head strip: `renderDeltaStat` (focused month total + MoM delta, respects owner tab) and `renderTargetStat` (budget vs actual with mid-month pace tick; **household-only and pinned to `household_latest_month`** — it ignores both the owner tab and the focused month, so its label spells out which month it refers to, plus a `Household` pill on non-ALL tabs); inline target editing via `toggleBudgetEdit`/`saveBudget` → `PUT /api/budget`

## Transactions Filter Bar

Built from `PRD-261101-Transactions-Filter-Redesign.md` (design source: `filter redesign supporting docs/`). One state object, `txFilters`
(defaults from `txFilterDefaults()`), drives the controls, the API params (`txParams`) and the
URL. Primary row: Search (250ms debounce) · Period · Statement · Status · More filters.
Hidden filters (`TX_HIDDEN_KEYS`: category, real, owner, actual, ideal, wrong) live in the
`#tx-more` popover, edited as a draft (`txMoreDraft`) that applies only on "Show N
transactions"; Esc / × / outside click discard it. Active hidden filters show as chips.

- **Real spend?** (All · Yes · No, URL `real=yes|no`) filters `is_real_expense`, i.e. the table's Real? column
- **Labels keep today's names**: "Paid By" filters `a.owner` (account owner, API `owner`),
  "Actual Source" = `paid_by`, "Ideal Source" = `ideal_paid_by`
- **Period** defaults to the latest month with data (`txDefaultPeriod`), `'all'` = All time
- **Statement overrides Period**: only `upload_id` is sent (card cycles span two months);
  the Period button is disabled and reads "from statement"
- **URL state**: non-default filters go into `?view=transactions&…` via `replaceState`;
  `boot()` deep-links into Transactions; `navigate()` to any other view clears the query
- **Summary line** (`renderTxSummary`): count of `allTxRows`, net total, per-direction
  "X owes Y" for unsettled wrong-source rows (same rule as Settlements); re-rendered by
  `renderTxTable()` and by `patchTx` after inline edits
- Table, inline editing, bulk actions and Export are unchanged by the redesign

## Dashboard Layout

Two panes side by side, each `calc(100vh - 170px)` tall, stacking below 1040px. The head
strip carries the title, owner tabs and the month-total / target readout (the summary cards
are gone). Selecting a month or a category anywhere drives the right pane.

**Left — trend (`renderTrend`, `#trend-card`)**: the last `DASH_MONTHS_SHOWN` (3) months of
`/api/dashboard?months=6` as CSS flex stacked bars — no chart library. Segments are `<div>`s
in `CATEGORIES` order inside a `column-reverse` flex column, sized by `flex-basis` percentage.
The clickable category legend sits below. `initDashEvents()` attaches one delegated
click/mousemove/mouseleave listener set to `#trend-card` (the card element survives every
`innerHTML` re-render); segments and legend items carry `data-cat` / `data-month`.
Hover highlight is applied in place by `applyDashHighlight()` rather than by re-rendering, so
a mousemove never rebuilds the element under the cursor. `showDashTip()` positions the fixed
`#dash-tip` tooltip.

**Right — category panel (`loadBreakdown` → `renderBreakdown`, `#breakdown-panel`)**: sticky,
tinted throughout with `color-mix()` on the selected category's `CAT_COLORS` hue so the chart
selection and the list read as one object. Month + category pills, `↑`/`↓` category nav,
then a `SEARCH` box and a `SORT BY` pill group (Amount / Date / A–Z) as two labelled
sections, then a scrolling grid (checkbox · date · description · Actual Source ·
amount · % · edit). `toggleBpEdit(id)` opens an inline form editing description / amount /
category / Actual Source (`paid_by`); `saveBpEdit(id)` PATCHes `/api/transactions/<id>`.
Checking rows reveals a dark bulk bar whose "Move to" applies a category to every selected row
via parallel PATCHes (`applyBpBulk`). Every mutation raises a 5s toast with **Undo**, which
replays the pre-change field snapshot held in `_dashUndo` back through the same PATCH route.

`↑`/`↓` cycle categories (by descending amount within the focused month) whenever the
dashboard is the active view, no modal is open, and focus is not in a form field.

The design reference this was built from is `docs/Tally Dashboard.html` (a bundled Claude
Design prototype; its real source is the `__bundler/template` script tag inside it).

## Branding

The product-facing name is **Tally** (page `<title>`, header logo, favicon/app icon) —
distinct from the repo/folder name and the "finance tracker" language used throughout
this file and the PRDs, which describe the project, not the brand. Icon source files
(`make_icon.py`, `make_favicons.py`, the 1024px master PNG, `.iconset`/`.icns`) live in
`branding/` for regenerating assets if the palette or mark changes; the design tokens
they pull from are documented in `DESIGN-SYSTEM.md`.

## Agent Team Roles

Reusable agent definitions live in `.claude/agents/`:
- `ui-designer.md` — reviews and redesigns views in `templates/index.html`; knows existing CSS patterns and component conventions
- `design-system.md` — owns `DESIGN-SYSTEM.md` (tokens, components, motion rules) and applies it to `templates/index.html`; grounded in the Emil Kowalski design-engineering skill
- `product-manager.md` — sharpens feature requests into PRDs via structured discovery; specialises in the Settlement feature and the `paid_by` / `ideal_paid_by` data model

Agent teams are enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`.

## Git & GitHub Workflow

After every set of changes, commit locally **and** push to GitHub.

**Remote:** `https://github.com/SuperHeavyMechanic/finance-project-tracker.git`

**Commit message rules:**
- Summary line ≤ 50 chars, imperative mood
- Always append: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

```bash
git add <specific files>
git commit -m "..."
git push origin main
```

Never use `git add .` or `git add -A` — `.env` and `data/` must never be committed.
