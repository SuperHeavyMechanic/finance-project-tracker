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

Two Python files + one HTML file. No build step.

**`db.py`** — all database logic (SQLite via `sqlite3`). Key functions:
- `init_db()` — called at app startup; creates tables and seeds the 3 initial accounts if empty
- `save_upload(account_id, filename, transactions)` — inserts an upload record + all its transactions; defaults `paid_by` to the account's owner
- `get_dashboard_data(owner, months)` — queries the N most recent months that have real transaction data (not calendar months), returns trend + summary
- `parse_date(s)` — normalises Indonesian bank date formats (DD/MM/YYYY, DD-Mon-YY, ISO) to YYYY-MM-DD
- `_dominant_month(transactions)` — detects the statement month from a list of parsed transactions

**`app.py`** — Flask routes only; no business logic. Calls `db.py` functions and handles:
- PDF decryption (`pypdf`) before sending to Claude
- Claude extraction via `EXTRACTION_PROMPT` (returns raw JSON array)
- Duplicate detection: returns `{duplicate: true}` so the frontend can confirm before saving

**`templates/index.html`** — single-file SPA (~870 lines). Vanilla JS + Chart.js (CDN). Five views rendered client-side via `navigate(view)`: Dashboard, Transactions, Settlements, Accounts, Upload. State lives in JS variables (`allAccounts`, `txRows`, `dashOwner`, `dashMonth`). All data fetched from the REST API on each navigation.

## Data Model

Three tables in `data/finance.db` (gitignored):

- **accounts** — seeded at startup; `owner` is SHAN, JANICE, or JOINT
- **uploads** — one row per statement file; `statement_month` is YYYY-MM
- **transactions** — `is_real_expense`, `paid_by`, `settled` are the key editable fields; `date_parsed` is YYYY-MM-DD used for all queries

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/accounts` | All accounts with tx_count and last_upload |
| POST | `/api/upload` | Extract + save; returns `{duplicate:true}` if month exists |
| POST | `/api/upload/confirm` | Force-save a duplicate upload |
| GET | `/api/transactions` | Filterable list (owner, month, account_id, category, is_real_expense, unsettled, q) |
| PATCH | `/api/transactions/<id>` | Update category, is_real_expense, paid_by, settled, settled_date |
| GET | `/api/dashboard` | Trend + summary scoped to months with actual data |
| GET | `/api/settlements` | Transactions where paid_by ≠ account owner |
| GET | `/api/export` | CSV download of filtered transactions |

## Key Constraints

- Max upload: 20 MB (`MAX_CONTENT_LENGTH`)
- Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png`
- Claude model pinned to `claude-sonnet-4-6` in `app.py`
- 14 categories (all-caps) defined in both `app.py` (`CATEGORIES`) and `templates/index.html` (`CATEGORIES` + `CAT_CLASS` + `CAT_COLORS`)
- Owners are hardcoded: SHAN, JANICE, JOINT — not user-configurable via UI
- Accounts are backend-seeded in `db.py:SEED_ACCOUNTS` — no add/edit UI

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
