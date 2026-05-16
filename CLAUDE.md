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
pip3 install flask anthropic python-dotenv pypdf
```

## Environment

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

Three Python files + one HTML file. No build step.

**`db.py`** — all database logic (SQLite via `sqlite3`). Key functions:
- `init_db()` — called at app startup; creates tables, runs schema migrations, seeds the 3 initial accounts if empty, and runs a data migration to re-derive `statement_month` from `statement_date` for all existing uploads
- `save_upload(account_id, filename, transactions, statement_date)` — derives `statement_month` from `statement_date` (billing date) if available, else falls back to `_dominant_month`; inserts upload + transactions; defaults `paid_by` to the account owner
- `get_transactions_by_ids(ids)` — fetches specific transactions by ID list, used for selective CSV export
- `parse_date(s)` — normalises Indonesian bank date formats (DD/MM/YYYY, DD-Mon-YY, ISO) to YYYY-MM-DD
- `update_transaction` — allowed fields: `category`, `is_real_expense`, `paid_by`, `ideal_paid_by`, `settled`, `settled_date`, `amount`

**`rules.py`** — category override rules applied during upload extraction:
- `GLOBAL_RULES` — keyword → category mappings that apply to every card (e.g. `openai` → `OTHERS`)
- `ACCOUNT_RULES` — per-bank overrides keyed by bank name substring (currently empty, kept as template)
- To enable/disable rules: comment/uncomment 3 lines in `app.py` — the import, `build_rules_prompt(account_name)` in the extraction call, and `apply_rules(extracted, account_name)` after extraction

**`app.py`** — Flask routes only; no business logic. Key behaviours:
- PDF decryption (`pypdf`) before sending to Claude
- `build_extraction_prompt()` constructs the Claude prompt; optionally injects rules via `build_rules_prompt()`
- Claude returns `{statement_date, transactions[]}`; `statement_date` drives `statement_month` (not dominant tx month)
- Duplicate detection: checks by `(account_id, statement_month)`, returns `{duplicate: true}` so frontend can confirm
- `_csv_date` / `_csv_month` — format YYYY-MM-DD / YYYY-MM to DD-Mmm-YY / Mmm-YY for CSV output

**`templates/index.html`** — single-file SPA (~1000 lines). Vanilla JS + Chart.js (CDN). Five views rendered client-side via `navigate(view)`: Dashboard, Transactions, Settlements, Accounts, Upload. Key frontend state: `allAccounts`, `txRows`, `selectedTxIds` (Set), `dashOwner`, `dashMonth`.

## Data Model

Three tables in `data/finance.db` (gitignored):

- **accounts** — seeded at startup via `SEED_ACCOUNTS` in `db.py`; `owner` is SHAN, JANICE, or JOINT
- **uploads** — one row per statement file; `statement_month` (YYYY-MM) is derived from `statement_date` (billing date, stored in original format); schema additions via `ALTER TABLE` in `init_db`
- **transactions** — key editable fields: `is_real_expense`, `paid_by` (actual payment source), `ideal_paid_by` (intended payment source), `settled`; `date_parsed` (YYYY-MM-DD) used for all queries

## Date & Statement Naming Convention

All dates displayed as **DD-Mmm-YY** (e.g. `20-Apr-26`). Functions:
- `fmtDate(date_parsed)` in JS — formats YYYY-MM-DD for transaction date column
- `fmtMonth(ym)` in JS — formats YYYY-MM for statement month labels
- `stmtRef(bank, statement_date, statement_month)` in JS — renders the clickable statement badge; prefers `statement_date` (DD-Mmm-YY) over `statement_month` (Mmm-YY)

Statement month is always derived from the **billing date** on the PDF, not the dominant transaction date inside it.

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/accounts` | All accounts with tx_count and last_upload |
| POST | `/api/upload` | Extract + save; returns `{duplicate:true}` if month exists |
| POST | `/api/upload/confirm` | Force-save a duplicate upload |
| GET | `/api/transactions` | Filterable list (owner, month, account_id, category, is_real_expense, unsettled, q) |
| PATCH | `/api/transactions/<id>` | Update category, is_real_expense, paid_by, ideal_paid_by, settled, settled_date, amount |
| DELETE | `/api/transactions/<id>` | Delete a transaction |
| GET | `/api/dashboard` | Trend + summary scoped to months with actual data |
| GET | `/api/settlements` | Transactions where paid_by ≠ account owner |
| GET | `/api/statements` | All uploads grouped by account |
| GET | `/api/export` | CSV download; accepts `ids=1,2,3` for selective export or filter params for bulk |

## CSV Export Format

Columns map to spreadsheet columns B–K:
`Date · Category · Expense Items Detail · Amount (Rp) · Real expenses? · Paid By · Actual Source · Ideal Source · Settled? · Card / Statement`

Foreign currency amounts are formatted as `IDR_amount (CURRENCY original_amount)`.

## Key Constraints

- Max upload: 20 MB (`MAX_CONTENT_LENGTH`)
- Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png`
- Claude model pinned to `claude-sonnet-4-6` in `app.py`
- 14 categories (all-caps) defined in both `app.py` (`CATEGORIES`) and `templates/index.html` (`CATEGORIES` + `CAT_CLASS` + `CAT_COLORS`) — must stay in sync
- Owners hardcoded: SHAN, JANICE, JOINT — not user-configurable via UI
- Accounts backend-seeded in `db.py:SEED_ACCOUNTS` — no add/edit UI

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
