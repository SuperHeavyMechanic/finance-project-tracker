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
- **Name** — user-defined label (e.g. "Mandiri Credit", "BCA Debit", "GoPay")
- **Bank** — optional bank name for display
- **Type** — Credit Card / Debit Card / E-Wallet

When uploading a statement, the user picks from this saved list via a dropdown. This tags every extracted transaction with the correct account.

---

## 6. Upload Flow (v2)

```
1. Select account from dropdown (from saved accounts list)
2. Drop or choose PDF / JPG / PNG
3. Enter password if the PDF is protected
4. Click "Analyze"
5. Claude extracts transactions → saved to local database
6. User sees a confirmation: "47 transactions added from Mandiri Credit – April 2025"
7. Duplicate detection: if same account + overlapping dates already exist, warn the user
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
| name | text | e.g. "Mandiri Credit" |
| bank | text | e.g. "Bank Mandiri" |
| type | text | Credit / Debit / E-Wallet |
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
| account_id | FK → accounts | |
| date | text | original format from statement |
| date_parsed | date | normalized YYYY-MM-DD for sorting/filtering |
| description | text | merchant/payee |
| amount | real | positive = charge, negative = refund/credit |
| currency | text | IDR, USD, SGD, etc. |
| category | text | one of 12 categories |
| created_at | datetime | |

**Storage:** SQLite, single file `data/finance.db` — local only, never committed to git.

---

## 9. Views / Pages

### 9.1 Dashboard (default view)
- **6-month trend chart** — bar or line chart, one bar per month, broken down by category (stacked)
- **Monthly summary cards** — for the selected month: total spent, top 3 categories, number of transactions, biggest single purchase
- **Month selector** — click any month to update the summary cards
- Default: current month selected, last 6 months shown in chart

### 9.2 Transactions
- Full table of all transactions (sortable, filterable)
- **Filters:** month, account, category, search by description
- Editable category (same as v1)
- CSV export button (exports current filtered view)

### 9.3 Accounts
- List of saved accounts with name, bank, type, transaction count
- Add / edit / delete accounts
- "Last uploaded" date per account

### 9.4 Upload
- Can be a modal or a dedicated page
- Account picker (dropdown from saved accounts)
- File drop zone
- Password field (appears only for PDFs)
- Analyze button
- Upload confirmation with transaction count

---

## 10. Navigation

Simple top navigation bar:
```
[Dashboard]  [Transactions]  [Accounts]  [Upload Statement]
```

---

## 11. Categories (unchanged from v1)

1. Dining & Restaurants  
2. Groceries  
3. Transportation  
4. Travel  
5. Entertainment  
6. Shopping  
7. Healthcare  
8. Subscriptions  
9. Utilities & Bills  
10. Home & Services  
11. Personal Care  
12. Other  

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
