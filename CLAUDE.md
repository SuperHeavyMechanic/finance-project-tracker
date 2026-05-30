# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./start.sh       # preferred — sets Python 3.9 PATH and starts Flask on port 8080
python3 app.py   # alternative
```

Open at **http://localhost:8080**. Port 5000 is avoided (macOS AirPlay conflict).

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

Tests use an in-memory SQLite DB via `monkeypatch` on `db.DB_PATH` — `data/finance.db` is never touched. All test fixtures are in `tests/test_db.py`.

## Environment

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

Four Python files + one HTML file. No build step.

**`db.py`** — all database logic (SQLite via `sqlite3`). Key functions:
- `init_db()` — creates tables, runs `ALTER TABLE` migrations, seeds missing accounts from `SEED_ACCOUNTS` (per-account upsert by `bank + last_four`).
- `save_staged(account_id, filename, transactions, statement_date)` — creates the upload record and writes transactions to `staged_transactions`; this is the main upload path
- `confirm_upload(upload_id)` — inserts only `transaction_type='DB'` staged rows into `transactions`, then deletes all staged rows for that upload
- `discard_upload(upload_id)` — deletes all staged rows + the upload record entirely
- `get_staged(upload_id)` — returns staged rows joined with account info (includes `account_type`)
- `parse_date(s)` — normalises Indonesian bank date formats (DD/MM/YYYY, DD-Mon-YY, ISO) to YYYY-MM-DD
- `create_transaction(fields)` — direct insert into `transactions` (manual entry, no upload/staging)
- `create_account / update_account / delete_account` — full account CRUD
- `update_transaction(tx_id, fields)` — allowed fields defined by `_ALLOWED_TX_FIELDS` frozenset: `category`, `is_real_expense`, `paid_by`, `ideal_paid_by`, `settled`, `settled_date`, `amount`, `date_parsed`, `description`
- `update_account(acc_id, fields)` — allowed fields defined by `_ALLOWED_ACCOUNT_FIELDS` frozenset
- `update_staged(tx_id, fields)` — allowed fields defined by `_ALLOWED_STAGED_FIELDS` frozenset
- `bulk_settle_transactions(ids, settled_date)` — marks a list of transaction IDs as `settled=1` with the given date in one query
- `get_settlements()` — returns transactions where `ideal_paid_by IS NOT NULL AND ideal_paid_by != paid_by` (Ideal Source ≠ Actual Source); **not** `paid_by != account_owner`

The three `_ALLOWED_*` frozensets at module level are the authoritative whitelist for which columns each update function may touch. Never use f-string SQL outside these functions.

**`rules.py`** — three layers of extraction customisation:
- `GLOBAL_RULES` — keyword → category mappings applied to every account post-extraction
- `ACCOUNT_RULES` — per-bank keyword → category overrides (bank name substring key)
- `BANK_NOTES` — per-bank free-text notes injected into the Claude prompt before the output schema; describes bank-specific quirks (date formats, how to parse descriptions, sections to skip). BCA debit notes live here. Add new bank patterns here first.
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

**`templates/index.html`** — single-file SPA (~2100 lines). Vanilla JS + Chart.js (CDN). Six views via `navigate(view)`. Key frontend state: `allAccounts`, `txRows`, `allTxRows`, `selectedTxIds` (Set), `pendingUploadId`, `pendingDuplicate`, `dashOwner`, `dashMonth`, `settleOwnerFilter`, `pendingSettleIds`.

## Data Model

Four tables in `data/finance.db` (gitignored):

- **`accounts`** — seeded from `SEED_ACCOUNTS` (6 accounts: 3 credit, 1 debit, 2 cash); also manageable via UI CRUD. `owner` ∈ {SHAN, JANICE, JOINT}; `account_type` ∈ {credit, debit, cash}
- **`uploads`** — one row per statement; `statement_month` (YYYY-MM) derived from `statement_date` (billing date in **original PDF format**, not ISO); survives confirm, deleted on discard
- **`staged_transactions`** — pure buffer; holds extracted rows pending review; cleared entirely on every confirm or discard; `transaction_type` ∈ {DB, CR} (CR rows shown for context in debit review but never confirmed)
- **`transactions`** — confirmed rows only; never contains staged or CR data; all downstream views read only this table. `upload_id` is NULL for manually-added transactions.

## Upload & Staging Flow

```
POST /api/upload
  → validate file magic bytes
  → Claude extracts (credit or debit prompt + bank_notes + rules)
  → check_duplicate(account_id, stmt_month)
      if duplicate → return {duplicate:true, transactions} (not staged yet)
  → save_staged() → staged_transactions + uploads record
  → return {staged:true, upload_id}

Frontend opens review modal (immediate after upload, or via Statements "Review →")
  Review: inline edit category/description/amount/real, delete rows
  Confirm → POST /api/uploads/<id>/confirm → confirm_upload() → DB rows → transactions
  Discard → DELETE /api/uploads/<id> → discard_upload() → upload + staged deleted

POST /api/upload/confirm  (duplicate override path)
  → same as above but skips duplicate check; calls save_staged() directly

POST /api/transactions  (manual entry path)
  → direct insert into transactions; no upload record, no staging
```

## Settlement Logic

Settlement is needed when **`ideal_paid_by ≠ paid_by`** (Ideal Source ≠ Actual Source). This is distinct from `paid_by ≠ account_owner`.

- `ideal_paid_by` = who *should* pay for the transaction
- `paid_by` = who *actually* paid (Actual Source)
- When they differ, `ideal_paid_by` owes `paid_by` a reimbursement

The Settlements view groups outstanding transactions by month, then by direction (e.g. SHAN→JANICE). `POST /api/settlements/settle` bulk-settles a list of IDs with a given date.

## Prompt Architecture (three layers, all in `rules.py` + `app.py`)

| Layer | Source | Purpose |
|---|---|---|
| Prompt structure | `app.py` `build_*_prompt()` | Output schema, field definitions, general rules |
| Bank notes | `rules.py` `BANK_NOTES` | Bank-specific parsing quirks injected before schema |
| Category overrides | `rules.py` `ACCOUNT_RULES` / `GLOBAL_RULES` | Keyword → category mappings, injected + applied post-extraction |

To handle a new bank's quirks: add an entry to `BANK_NOTES` in `rules.py`. Only change `app.py` prompts for structural changes that affect all banks.

## Date & Statement Naming Convention

All dates displayed as **DD-Mmm-YY** (e.g. `20-Apr-26`).
- `fmtDate(date_parsed)` — formats YYYY-MM-DD → DD-Mmm-YY
- `fmtDateObj(d)` — formats a JS Date object → DD-Mmm-YY (shared helper)
- `parseStatementDateLabel(statementDate, statementMonth)` — handles raw PDF date formats (DD/MM/YYYY or ISO) and YYYY-MM month strings; falls back to last day of month when only month is available
- `stmtRef(bank, statement_date, statement_month)` — renders statement badge using `parseStatementDateLabel`

`statement_date` in the DB is stored in the **original PDF format** (e.g. `"11/04/2026"`), not ISO. Always use `parseStatementDateLabel` to display it, never `fmtDate` directly.

Statement month is always derived from the **billing date** on the PDF (credit) or the **last day of the printed period** (debit), never from the dominant transaction date.

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/accounts` | All accounts with tx_count, last_upload, account_type |
| POST | `/api/accounts` | Create account |
| PATCH | `/api/accounts/<id>` | Update account (name, owner, bank, last_four, account_type) |
| DELETE | `/api/accounts/<id>` | Delete account (transactions preserved, lose account link) |
| POST | `/api/upload` | Extract → stage; returns `{duplicate:true}` or `{staged:true, upload_id}` |
| POST | `/api/upload/confirm` | Force-stage a duplicate (skips duplicate check) |
| GET | `/api/uploads/<id>/staged` | Staged rows for review (includes account_type for layout) |
| PATCH | `/api/staged/<id>` | Edit staged row (category, description, amount, is_real_expense) |
| DELETE | `/api/staged/<id>` | Remove single staged row |
| POST | `/api/uploads/<id>/confirm` | Confirm: DB staged rows → transactions, clear staged |
| DELETE | `/api/uploads/<id>` | Discard: delete staged rows + upload record |
| GET | `/api/transactions` | Filterable list (owner, month, account_id, category, is_real_expense, settled, paid_by, ideal_paid_by, upload_id, q) |
| POST | `/api/transactions` | Manual entry: direct insert, no upload_id |
| PATCH | `/api/transactions/<id>` | Update any allowed field (see `_ALLOWED_TX_FIELDS` in db.py) |
| DELETE | `/api/transactions/<id>` | Delete a confirmed transaction |
| GET | `/api/dashboard` | Trend + summary scoped to months with actual data; `owner` filter applies to `t.ideal_paid_by`, not `a.owner` |
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
- Dashboard `owner` tab filters by `t.ideal_paid_by` (Ideal Source), **not** by `a.owner` (account ownership) — this applies to both the trend chart (`get_dashboard_data` in `db.py`) and the category breakdown panel (`loadBreakdown` in `index.html`, which passes `ideal_paid_by=` to `/api/transactions`)
- Dashboard breakdown panel: `loadBreakdown(month, category)` fetches transactions and renders per-item bars + Actual Source badge; `toggleBpEdit(id)` / `saveBpEdit(id, month, origCategory)` handle inline editing that PATCHes directly to `/api/transactions/<id>`
- Chart totals: `stackTotalsPlugin` (defined inline in `renderTrend`) draws the month total above each stacked bar using Chart.js `afterDatasetsDraw`

## Agent Team Roles

Reusable agent definitions live in `.claude/agents/`:
- `ui-designer.md` — reviews and redesigns views in `templates/index.html`; knows existing CSS patterns and component conventions
- `frontend-specialist.md` — implements FE changes; checks for XSS escaping, DRY violations, debouncing
- `backend-specialist.md` — implements BE changes; enforces parameterised SQL, category validation, file magic checks, DB indexes
- `qa-specialist.md` — reviews data integrity and adds tests; always uses `:memory:` DB fixture, never touches `data/finance.db`

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
