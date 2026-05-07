# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./start.sh          # preferred — sets Python 3.9 PATH and starts Flask on port 8080
python3 app.py      # alternative
```

Open at **[http://localhost:8080](http://localhost:8080)**. Port 5000 is avoided intentionally (macOS AirPlay conflict).

Install dependencies:

```bash
pip3 install flask anthropic python-dotenv
```

## Environment

Copy `.env` and add your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

Single-file Flask backend (`app.py`) + single-page frontend (`templates/index.html`). No database — all state lives in the browser session.

**Request flow:**

1. User uploads a PDF/JPG/PNG via the frontend drag-and-drop zone
2. `POST /upload` in `app.py` base64-encodes the file and sends it to Claude (`claude-sonnet-4-6`) as a `document` block (PDF) or `image` block (JPG/PNG)
3. Claude returns a JSON array of transactions; the backend strips any markdown fences and parses it
4. The frontend renders a summary grid (spend by category) and a sortable/filterable transactions table

**Extraction prompt** (`EXTRACTION_PROMPT` in `app.py`): instructs Claude to return only a raw JSON array with fields `date`, `description`, `amount`, `category`. The 12 categories are hardcoded in `CATEGORIES`.

**Frontend** (`templates/index.html`): self-contained HTML/CSS/JS — no build step, no dependencies. All logic (search, sort, filter, category editing, CSV export) runs in vanilla JS against the in-memory `allTransactions` array.

## Custom Slash Commands

`.claude/commands/add-notion-task.md` — project-level command that creates a task in the user's Notion workspace. Prompts for Task name, Area, Project, and Due date, then calls the Notion MCP. A global version also exists at `~/.claude/commands/add-notion-task.md` with brainstorm + quick-capture modes.

## Git & GitHub Workflow

After every set of changes, commit locally **and** push to GitHub so there's always a saved version to revert to.

**Remote:** `https://github.com/SuperHeavyMechanic/finance-project-tracker.git`

**Commit message rules:**
- Summary line: 50 chars or less, imperative mood ("Add password support", not "Added password support")
- Body (optional): explain *why*, not what — one blank line after the summary
- Always append: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

**Workflow after every change:**
```bash
git add <specific files>
git commit -m "..."
git push origin main
```

Never use `git add .` or `git add -A` — stage files explicitly to avoid committing `.env` or other sensitive files.

## Key Constraints

- Max upload size: 20 MB (`MAX_CONTENT_LENGTH`)
- Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png` — validated in `upload()` before the API call
- Claude model is pinned to `claude-sonnet-4-6` in `app.py:104`
- `start.sh` explicitly exports `~/Library/Python/3.9/bin` to PATH because pip-installed Flask lives there on macOS system Python

