# System Audit — 30 May 2026

Conducted via codebase exploration (FE + BE pre-audit) ahead of full agent team review.

---

## What the app is

A personal finance tracker for Shan & Janice. It reads bank statements (PDF/image) using Claude AI, extracts transactions, lets you review and confirm them, then tracks spending across accounts, categories, and owners.

Three layers:
- **Backend** — Python/Flask server that talks to the database, calls Claude AI, and handles file uploads
- **Frontend** — A single large webpage (~2,000 lines) that shows everything: charts, tables, filters, upload flow
- **Database** — SQLite (a simple file-based database) storing all transactions, accounts, and statements

---

## Fixes needed, by priority

### 🔴 Critical — Could cause real damage

**1. A loophole in how we save edits to the database**
When you edit a transaction (change a category, amount, etc.), the app builds the save instruction by piecing together text. If that instruction isn't built carefully, someone could send a crafted request that tricks the database into doing something unintended — like deleting everything or reading data it shouldn't.

*Risk today:* Low (single user, local app). *Risk if app goes online or is shared:* High — this is the first thing an attacker would try.

*Fix:* Rewrite the two "save edit" functions to use a safer, more rigid approach. No behaviour change for normal use.

---

**2. Anyone could upload a fake file disguised as a PDF**
The app only checks the file's *name* (e.g., "statement.pdf"). It doesn't look inside the file to confirm it really is a PDF. A malicious file named "statement.pdf" could be something else entirely.

*Fix:* Add a check that peeks inside the file's actual content (not just the name) to confirm it's really a PDF or image before processing it.

---

**3. The category field accepts any value, even nonsense**
When editing a transaction's category, the server saves whatever it receives — even if it's not one of the 14 valid categories (GROCERIES, TRANSPORT, etc.).

*Fix:* Add a simple check: "Is this in our list of 14 categories? If not, reject it." Prevents corrupted data and broken charts.

---

### 🟡 High — Causing friction or fragility today

**4. The database has no shortcuts for common lookups**
Every time you filter transactions by month, account, or owner, the database reads every single row to find matches — like searching a filing cabinet by reading every folder instead of using tabs.

*Right now:* Fine. *With years of data:* Filters and the dashboard will feel sluggish.

*Fix:* Add "index tabs" to the database for the columns you filter on most (date, account, who paid). Makes lookups instant.

---

**5. When something breaks, there's no record of what happened**
If the Claude AI call fails, a PDF doesn't parse, or a database error occurs — the app either shows a generic error or fails silently. No log, no trail.

*Risk:* You might have missing or incorrect transactions without realising it.

*Fix:* Add a simple log system — like a diary the app keeps automatically. Errors get recorded with details so problems can be diagnosed.

---

**6. Two almost-identical blocks of code do the same job**
The instructions Claude receives to extract credit card statements vs. debit statements are written as two completely separate text blocks — even though they're 80% the same.

*Risk:* If you want to change how extraction works, you have to update it in two places. Forgetting one causes inconsistent behaviour across account types.

*Fix:* Write the shared part once, add the small differences on top for each account type.

---

**7. The search box calls the server on every single letter you type**
Type "groceries" = 9 separate server requests. Wasteful and can make search feel laggy.

*Fix:* Add a tiny 0.3-second pause after you stop typing before it actually searches. Standard behaviour on every modern search box.

---

**8. Special characters in a description could break the page display**
If a transaction description contains characters like `<`, `>`, or `"` (which can appear in some bank exports), the page could display incorrectly or, in the worst case, run unintended instructions in the browser.

*Risk:* Real — bank statement descriptions aren't always clean text.

*Fix:* Make sure every piece of text from the database is "cleaned" before being shown on screen, so special characters display as text rather than being acted on.

---

**9. Three copy-pasted functions that do essentially the same thing**
The bulk-edit actions (reassign category, reassign who paid, reassign who *should* pay) are three separate blocks of nearly identical code.

*Risk:* If a bug is found in one, it needs to be fixed in three places. One will inevitably be missed.

*Fix:* Write one shared function and call it three times with different inputs.

---

### 🟢 Medium — Makes future development easier

**10. No automated tests exist**
There's no way to quickly check after a change whether anything broke. Every change has to be manually tested by using the app.

*Risk:* As the app grows, gaps in manual testing appear. A test for "does uploading a statement correctly save only debit rows?" takes 30 seconds to run automatically vs. 5 minutes manually.

*Fix:* Add a small test file covering the most critical behaviours (date parsing, upload confirmation, duplicate detection).

---

**11. The code doesn't label what type of data each function expects**
Python functions don't say "I expect a number here" or "this returns a list of transactions." Other tools — including future Claude sessions — have to guess.

*Fix:* Add labels to function definitions. No behaviour change — purely makes the code easier to work with correctly in future.

---

## Summary table

| # | Fix | Why it matters | Priority |
|---|---|---|---|
| 1 | Database save loophole | Security risk | 🔴 Critical |
| 2 | Fake file upload accepted | Security risk | 🔴 Critical |
| 3 | Invalid category accepted | Data corruption | 🔴 Critical |
| 4 | No database shortcuts | Future slowness | 🟡 High |
| 5 | No error logs | Can't diagnose problems | 🟡 High |
| 6 | Duplicate AI prompt code | Inconsistency risk | 🟡 High |
| 7 | Search fires every keystroke | Wasteful, laggy | 🟡 High |
| 8 | Special chars break display | Display/security risk | 🟡 High |
| 9 | Copy-pasted bulk functions | Bug propagation | 🟡 High |
| 10 | No automated tests | Slow, unreliable QA | 🟢 Medium |
| 11 | No data type labels | Future maintenance | 🟢 Medium |

---

## Tech stack verdict

**Keep Python/Flask.** No need to switch. The Claude AI integration, database logic, and rule engine are all well-suited to Python. The main improvements needed are modernisation within the existing stack — better error handling, safer database queries, and a cleaner frontend structure — not a rebuild.

The frontend (the webpage) is the most cluttered part. It works, but at 2,000+ lines in a single file it's becoming hard to maintain. No need to switch to React or similar — but extracting repeated patterns and splitting responsibilities would make a meaningful difference.
