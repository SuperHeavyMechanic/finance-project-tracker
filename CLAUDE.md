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

Four Python files + one HTML file. No build step.

**`db.py`** — all database logic (SQLite via `sqlite3`). Key functions:
- `init_db()` — creates tables, runs `ALTER TABLE` migrations, seeds missing accounts from `SEED_ACCOUNTS` (per-account upsert by bank + last_four, not "seed if empty")
- `save_staged(account_id, filename, transactions, statement_date)` — creates the upload record and writes transactions to `staged_transactions`; this is the main upload path
- `confirm_upload(upload_id)` — inserts only `transaction_type='DB'` staged rows into `transactions`, then deletes all staged rows for that upload
- `discard_upload(upload_id)` — deletes all staged rows + the upload record entirely
- `get_staged(upload_id)` — returns staged rows joined with account info (includes `account_type`)
- `parse_date(s)` — normalises Indonesian bank date formats (DD/MM/YYYY, DD-Mon-YY, ISO) to YYYY-MM-DD
- `save_upload()` — legacy function still in code but not called by any route; staging path replaced it

**`rules.py`** — three layers of extraction customisation:
- `GLOBAL_RULES` — keyword → category mappings applied to every account post-extraction
- `ACCOUNT_RULES` — per-bank keyword → category overrides (bank name substring key)
- `BANK_NOTES` — per-bank free-text notes injected into the Claude prompt before the output schema; describes bank-specific quirks (date formats, how to parse descriptions, sections to skip). BCA debit notes live here. Add new bank patterns here first.
- `build_bank_notes(account_name)` / `build_rules_prompt(account_name)` — produce the injected text blocks

**`app.py`** — Flask routes only; no business logic. Key behaviours:
- `build_extraction_prompt(rules_section, bank_notes)` — credit card prompt
- `build_debit_extraction_prompt(rules_section, bank_notes)` — debit/bank prompt; generic structure, bank-specific quirks come from `bank_notes`
- `period_to_statement_date(period_str)` — converts "APRIL 2026" → "30/04/2026" (last calendar day of period)
- Upload route branches on `account.account_type`: debit uses debit prompt + extracts `period` field; credit uses credit prompt + extracts `statement_date`
- PDF decryption: tries empty-string password first before prompting user (handles BCA-style "encrypted with no password" PDFs)
- Duplicate detection runs before staging; returns `{duplicate:true}` with in-memory transactions so frontend can confirm

**`templates/index.html`** — single-file SPA (~1350 lines). Vanilla JS + Chart.js (CDN). Six views via `navigate(view)`. Key frontend state: `allAccounts`, `txRows`, `selectedTxIds` (Set), `pendingUploadId`, `pendingDuplicate`.

## Data Model

Four tables in `data/finance.db` (gitignored):

- **`accounts`** — seeded from `SEED_ACCOUNTS`; `owner` ∈ {SHAN, JANICE, JOINT}; `account_type` ∈ {credit, debit} drives prompt branching and review UI layout
- **`uploads`** — one row per statement; `statement_month` (YYYY-MM) derived from `statement_date` (billing date in original format); survives confirm, deleted on discard
- **`staged_transactions`** — pure buffer; holds extracted rows pending review; cleared entirely on every confirm or discard; `transaction_type` ∈ {DB, CR} (CR rows shown for context in debit review but never confirmed)
- **`transactions`** — confirmed rows only; never contains staged or CR data; all downstream views read only this table

## Upload & Staging Flow

```
POST /api/upload
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
```

## Prompt Architecture (three layers, all in `rules.py` + `app.py`)

| Layer | Source | Purpose |
|---|---|---|
| Prompt structure | `app.py` `build_*_prompt()` | Output schema, field definitions, general rules |
| Bank notes | `rules.py` `BANK_NOTES` | Bank-specific parsing quirks injected before schema |
| Category overrides | `rules.py` `ACCOUNT_RULES` / `GLOBAL_RULES` | Keyword → category mappings, injected + applied post-extraction |

To handle a new bank's quirks: add an entry to `BANK_NOTES` in `rules.py`. Only change `app.py` prompts for structural changes that affect all banks.

## Date & Statement Naming Convention

All dates displayed as **DD-Mmm-YY** (e.g. `20-Apr-26`).
- `fmtDate(date_parsed)` — formats YYYY-MM-DD
- `fmtMonth(ym)` — formats YYYY-MM
- `stmtRef(bank, statement_date, statement_month)` — renders statement badge; prefers `statement_date` over `statement_month`

Statement month is always derived from the **billing date** on the PDF (credit) or the **last day of the printed period** (debit), never from the dominant transaction date.

## API Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/accounts` | All accounts with tx_count, last_upload, account_type |
| POST | `/api/upload` | Extract → stage; returns `{duplicate:true}` or `{staged:true, upload_id}` |
| POST | `/api/upload/confirm` | Force-stage a duplicate (skips duplicate check) |
| GET | `/api/uploads/<id>/staged` | Staged rows for review (includes account_type for layout) |
| PATCH | `/api/staged/<id>` | Edit staged row (category, description, amount, is_real_expense) |
| DELETE | `/api/staged/<id>` | Remove single staged row |
| POST | `/api/uploads/<id>/confirm` | Confirm: DB staged rows → transactions, clear staged |
| DELETE | `/api/uploads/<id>` | Discard: delete staged rows + upload record |
| GET | `/api/transactions` | Filterable list (owner, month, account_id, category, is_real_expense, settled, paid_by, ideal_paid_by, upload_id, q) |
| PATCH | `/api/transactions/<id>` | Update category, is_real_expense, paid_by, ideal_paid_by, settled, settled_date, amount |
| DELETE | `/api/transactions/<id>` | Delete a confirmed transaction |
| GET | `/api/dashboard` | Trend + summary scoped to months with actual data |
| GET | `/api/settlements` | Transactions where paid_by ≠ account owner |
| GET | `/api/statements` | Uploads grouped by account; includes staged_count for pending-review detection |
| GET | `/api/export` | CSV download; `ids=1,2,3` for selected rows, `upload_id=N` for full statement |

## Key Constraints

- Max upload: 20 MB (`MAX_CONTENT_LENGTH`)
- Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png`
- Claude model pinned to `claude-sonnet-4-6` in `app.py`
- 14 categories (all-caps) defined in both `app.py` (`CATEGORIES`) and `templates/index.html` (`CATEGORIES` + `CAT_CLASS` + `CAT_COLORS`) — must stay in sync
- Owners hardcoded: SHAN, JANICE, JOINT — not user-configurable via UI
- Accounts are backend-seeded in `db.py:SEED_ACCOUNTS` (4 accounts: 3 credit, 1 BCA debit) — no add/edit UI
- CSV `Amount` column: IDR integer only (`int(round(amount))`), no foreign currency, no decimals; rows sorted ascending by date

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
