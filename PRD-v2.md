# Finance Tracker v2 — Product Requirements Document

**Date:** 2026-05-07  
**Status:** Planning  
**Repo:** https://github.com/SuperHeavyMechanic/finance-project-tracker

---

## 1. Problem Statement

v1 is a one-shot tool — upload a statement, view transactions, refresh the page and everything is gone. There is no memory, no history, and no way to compare spending across months or across different bank accounts. v2 turns it into a proper personal finance tracker: persistent, multi-account, and insightful.

---

## 2. Users

- **Primary:** One household (user + family members)  
- **Access:** Single shared account, no individual logins, no authentication required  
- **Usage pattern:** Upload 1–3 bank statements per month, review spending, export if needed

---

## 3. Goals for v2

| # | Goal |
|---|------|
| 1 | All transactions are saved persistently (survive refresh, browser close, restart) |
| 2 | Support multiple bank accounts — upload statements from each, view together |
| 3 | See 6-month spending trends by category |
| 4 | Generate a clean monthly summary (total spent, top categories, biggest purchases) |
| 5 | Export filtered transactions as CSV |

---

## 4. Out of Scope for v2

- User authentication / separate logins
- Budget limits or alerts
- PDF/report export
- Cloud sync or remote access
- Mobile app

---

## 5. Accounts Feature

Before uploading any statement, the user sets up their bank accounts once. Each account has:
- **Owner** — SHAN, JANICE, or JOINT (fixed, not user-configurable)
- **Name** — user-defined label (e.g. "Mandiri Credit", "BCA Debit", "GoPay")
- **Bank** — optional bank name for display
- **Type** — Credit Card / Debit Card / E-Wallet

Accounts are always tied to an owner. Initial account list:

| Owner | Name | Bank | Card Type | Last 4 |
|-------|------|------|-----------|--------|
| SHAN | CC BNI VISA GARUDA | BNI | Credit – Visa (Garuda co-brand) | 3738 |
| SHAN | CC MANDIRI VISA SIGNATURE | Mandiri | Credit – Visa Signature | 5856 |
| SHAN | CC JENIUS | Jenius (BTPN) | Credit | 9XXX |

JANICE's accounts to be added later.

When uploading, the user picks the account from a dropdown (accounts are grouped by owner). The owner field auto-fills based on the selected account but can be changed.

---

## 6. Upload Flow (v2)

```
1. Select bank account from dropdown (from saved accounts list)
2. Choose owner: SHAN / JANICE / JOINT (toggle / button group)
3. Drop or choose PDF / JPG / PNG
4. Enter password if the PDF is protected
5. Click "Analyze"
6. Claude extracts transactions → saved to local database
   User sees a confirmation:
   "47 transactions added — SHAN · Mandiri Credit · April 2025"
7. Duplicate detection: if the same owner + account + overlapping dates
   already exist in the database, show a warning before saving:
   "You've already uploaded Mandiri Credit for April 2025 (SHAN).
    Upload anyway and merge, or cancel?"
```

---

## 7. Currency Handling

- **Primary currency:** IDR (Indonesian Rupiah)
- **Multi-currency:** Transactions in other currencies (USD, SGD, MYR, etc.) are stored with their original amount and currency code
- **Display:** Show original currency (e.g. "USD 49.99") alongside IDR equivalent when available — Claude will extract what's on the statement
- **No forced conversion** — do not attempt live exchange rate lookups

---

## 8. Data Model

### accounts
| Field | Type | Notes |
|-------|------|-------|
| id | integer PK | |
| owner | text | "SHAN", "JANICE", or "JOINT" |
| name | text | e.g. "CC BNI VISA GARUDA" |
| bank | text | e.g. "BNI" |
| type | text | Credit / Debit / E-Wallet |
| last_four | text | last 4 digits of card, e.g. "3738" |
| created_at | datetime | |

### uploads
| Field | Type | Notes |
|-------|------|-------|
| id | integer PK | |
| account_id | FK → accounts | |
| filename | text | original file name |
| statement_month | text | YYYY-MM, parsed from transactions |
| uploaded_at | datetime | |
| transaction_count | integer | |

### transactions
| Field | Type | Notes |
|-------|------|-------|
| id | integer PK | |
| upload_id | FK → uploads | |
| account_id | FK → accounts | card the transaction appeared on |
| date | text | original format from statement |
| date_parsed | date | normalized YYYY-MM-DD for sorting/filtering |
| description | text | merchant/payee |
| amount | real | positive = charge, negative = refund/credit |
| currency | text | IDR, USD, SGD, etc. |
| category | text | one of the categories below |
| is_real_expense | integer | 1 = yes, 0 = no (e.g. internal transfers, bill payments) |
| paid_by | text | "SHAN", "JANICE", or "JOINT" — who actually paid |
| actual_account_id | FK → accounts | account that was actually charged (same as account_id in most cases) |
| ideal_account_id | FK → accounts | account that *should* have been used, if different |
| settled | integer | 1 = settled, 0 = not yet (only relevant when paid_by ≠ owner of account) |
| settled_date | date | date reimbursement was made, if settled |
| created_at | datetime | |

**Storage:** SQLite, single file `data/finance.db` — local only, never committed to git.

---

## 9. Views / Pages

### 9.1 Dashboard (default view)
- **Owner toggle** — SHAN / JANICE / JOINT / All (filters the entire dashboard)
- **6-month trend chart** — stacked bar chart, one bar per month, broken down by category
- **Monthly summary cards** — for the selected month: total spent, top 3 categories, number of transactions, biggest single purchase
- **Month selector** — click any month to update the summary cards
- Default: All view, current month selected, last 6 months shown in chart

### 9.2 Transactions
- Full table of all transactions (sortable, filterable)
- **Columns:** Date, Description, Category, Amount, Currency, Paid By, Account, Real Expense, Settled
- **Filters:** owner (SHAN / JANICE / JOINT / All), month, account, category, real expense only, unsettled only, search by description
- Editable fields inline: category, is_real_expense, paid_by, settled
- CSV export button (exports current filtered view)

### 9.3 Settlements (new)
- Shows only transactions where `paid_by` ≠ account owner — i.e. one person covered for another
- Columns: Date, Description, Amount, Paid By, Should Be Paid By, Settled?
- "Mark as settled" action per row or in bulk
- Running total: how much SHAN owes JANICE (or vice versa) across unsettled transactions

### 9.4 Accounts
- List of saved accounts grouped by owner (SHAN / JANICE)
- Add / edit / delete accounts — each account requires an owner
- "Last uploaded" date and transaction count per account

### 9.5 Upload
- Can be a modal or a dedicated page
- Step 1: Select bank account from dropdown
- Step 2: Owner toggle — SHAN or JANICE (pre-fills based on account, editable)
- Step 3: File drop zone
- Step 4: Password field (appears only for PDFs)
- Step 5: Analyze button
- Confirmation message + duplicate warning if applicable

---

## 10. Navigation

Simple top navigation bar:
```
[Dashboard]  [Transactions]  [Settlements]  [Accounts]  [Upload Statement]
```

---

## 11. Categories

1. HOUSEHOLD & UTILITIES  
2. GROCERIES  
3. TRANSPORTATION  
4. ENTERTAINMENT  
5. SHOPPING  
6. HEALTHCARE  
7. DEBT REPAYMENT  
8. SAVINGS  
9. F&B  
10. OTHERS  
11. FAMILY  
12. VACATION  
13. BOOZE  
14. EDUCATION  

---

## 12. Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | Python / Flask | Same as v1, no new dependencies |
| Database | SQLite | Local-only, zero config, single file |
| ORM | Raw SQL (sqlite3) | Simple enough, no extra library |
| Frontend | Vanilla HTML/CSS/JS | No build step, same as v1 |
| Charts | Chart.js (CDN) | Lightweight, no build step |
| PDF handling | pypdf | Already installed in v1 |
| AI | Claude claude-sonnet-4-6 | Same as v1 |

---

## 13. File Structure (v2)

```
/
├── app.py                  # Flask routes
├── db.py                   # Database setup and queries
├── start.sh
├── .env                    # ANTHROPIC_API_KEY (never committed)
├── data/
│   └── finance.db          # SQLite database (never committed)
└── templates/
    └── index.html          # Single-page app (multi-view via JS)
```

---

## 14. Claude Extraction Changes

The extraction prompt will be updated to also return:
- `currency` — the currency code of the amount (default `IDR` if not specified)
- `date` — always attempt to normalize to YYYY-MM-DD format

---

## 15. Data Safety

- `data/finance.db` added to `.gitignore` — local transactions never pushed to GitHub
- `.env` already in `.gitignore`
- No external API calls except to Anthropic for extraction

---

## 16. Open Questions (to decide before building)

| # | Question | Default if not answered |
|---|----------|------------------------|
| 1 | Should duplicate uploads (same account, same month) be blocked or just warned? | Warn, allow override |
| 2 | Should the app run on port 8080 still, or change? | Keep 8080 |
| 3 | Any categories to add or rename for IDR context? | Keep existing 12 |

---

## 17. Build Order (suggested)

1. Database schema + `db.py`  
2. Accounts page (CRUD) — no uploads yet  
3. Upload flow with account tagging → saves to DB  
4. Transactions view (reads from DB, filter/sort/export)  
5. Dashboard with 6-month chart + monthly summary  
6. Polish: navigation, empty states, error handling  
