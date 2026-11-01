# PRD — Delete an Uploaded Statement

**Date:** 2026-11-01
**Author:** Shan Sebastian (with Claude Code)
**Status:** Implemented 2026-11-01

---

## 1. Problem

A confirmed statement cannot be removed. If an extraction went wrong (wrong account picked, wrong month, bad parse, test upload), the only recourse today is deleting its transactions one by one on the Transactions page. Even then the `uploads` row survives, so:

- the Statements list keeps showing it (e.g. `BNI · 20-Apr-26` with `Rp 0,00` extracted),
- the coverage matrix keeps that `(account, month)` cell green,
- a re-upload of the correct PDF trips the duplicate warning.

Pending (unconfirmed) uploads already have **Discard**; confirmed ones have nothing — the **Status** column is empty for them.

### Current-state facts (from code)

- `transactions.upload_id REFERENCES uploads(id)` with **no `ON DELETE` clause**, and `get_db()` runs `PRAGMA foreign_keys = ON`. A plain `DELETE FROM uploads WHERE id=?` on a confirmed upload therefore **fails with an IntegrityError** today. Child rows must be deleted first, in the same SQL transaction. (SQLite cannot add `ON DELETE CASCADE` without rebuilding the table — not worth it.)
- `discard_upload(upload_id)` deletes staged rows, the upload row and the stored file. It works only because pending uploads have no confirmed transactions yet.
- `DELETE /api/uploads/<id>` is wired to `discard_upload`.
- Manually-added transactions have `upload_id IS NULL` and are never linked to a statement.
- `get_statements()` already returns `active_count` / `active_total` per upload (the "Active" column).

---

## 2. Goals

- Delete any statement — pending or confirmed — from the Statements page in one action.
- Deleting a statement removes **every transaction linked to it** (`transactions.upload_id = id`), its staged rows and its stored file, atomically.
- Show exactly what will be lost before confirming, including anything that touches Settlements.
- After deletion the slot is clean: coverage cell reverts to missing, re-upload works with no duplicate warning.

## 3. Non-goals

- Soft delete / trash / restore.
- "Delete statement but keep its transactions" (detach by nulling `upload_id`). See Open question 2.
- Bulk delete of several statements at once.
- Changing the schema to `ON DELETE CASCADE`.
- Fixing the related pre-existing behaviour of account deletion.

---

## 4. Behaviour

### 4.1 Entry point

- Statements page, each upload row, **Status** column:
  - **Confirmed row:** a small danger-outline `Delete` button (currently the cell is empty).
  - **Pending row:** keep `Pending Review` + `Review →`; add the same `Delete` button. For pending rows this does what Discard does today.
- No new button inside the review modal — it already has Discard.

### 4.2 Confirmation

Native `confirm()`, matching every other destructive action in the app (`deleteTx`, discard, delete account). Message built from the row's data:

```
Delete statement BNI · 20-Apr-26?

This permanently removes 41 transactions (Rp 8.941.246) from Tally,
including any edits you made to their category or source.

⚠ 3 of them are already settled — they will disappear from settlement history.
⚠ 2 have an outstanding settlement — those amounts will drop out of Settlements.

This cannot be undone.
```

- Settlement lines appear only when their count > 0.
- Pending upload with 0 confirmed rows: short form — "Discard this pending upload? N staged transactions will be removed."

### 4.3 After delete

- `loadStatements()` re-runs: row disappears, coverage cell becomes `+` (missing). It does **not** revert to blue "entered manually" — `save_staged()` already cleared that marker when the upload landed; that is acceptable.
- Toast: "Statement deleted · 41 transactions removed". No Undo (see §6).
- Other views (Dashboard, Transactions, Settlements) reflect the change next time they load; they fetch on `navigate()`.

---

## 5. Implementation plan

### 5.1 `db.py`

New `delete_upload(upload_id)` replaces `discard_upload` (keep `discard_upload` as a one-line alias, or update its single caller and test):

```python
def delete_upload(upload_id):
    conn = get_db()
    c = conn.cursor()
    tx_count = c.execute('DELETE FROM transactions WHERE upload_id=?', (upload_id,)).rowcount
    c.execute('DELETE FROM staged_transactions WHERE upload_id=?', (upload_id,))
    c.execute('DELETE FROM uploads WHERE id=?', (upload_id,))
    conn.commit()
    conn.close()
    _delete_statement_file(upload_id)
    return tx_count
```

- Order matters (children before parent) because of the FK.
- One connection, one commit ⇒ atomic. File removal only after commit.
- **Pre-delete backup (first step, before any DELETE):** copy `DB_PATH` to `data/backups/finance-<YYYY-MM-DD_HHMMSS>-before-delete-upload-<id>.db`, then prune so only the newest 10 backups remain. Use `sqlite3`'s `conn.backup()` rather than a raw file copy so the snapshot is consistent. Backups dir derives from `DB_PATH`'s folder so tests write under `tmp_path`. If the backup fails, abort the delete and return an error.

`get_statements()` adds two counts per upload for the confirm message:

```sql
COALESCE(SUM(CASE WHEN t.settled = 1 THEN 1 ELSE 0 END), 0) AS settled_count,
COALESCE(SUM(CASE WHEN t.settled = 0 AND t.ideal_paid_by IS NOT NULL
                   AND t.ideal_paid_by != t.paid_by THEN 1 ELSE 0 END), 0) AS outstanding_settle_count
```

(Outstanding definition matches `get_settlements()`: `ideal_paid_by ≠ paid_by`.)

### 5.2 `app.py`

- `DELETE /api/uploads/<id>` calls `delete_upload`, returns `{ok: true, deleted_count: n}`.
- 404 if the upload id does not exist (today it silently returns ok).

### 5.3 `templates/index.html`

- `loadStatements()` row template: render the `Delete` button in the Status cell.
- New `deleteStatement(uploadId)`: looks up the upload in the cached statements data, builds the confirm message (§4.2), calls `DELETE`, toasts, reloads statements. If the upload id is in `pendingUploadId` / `_reviewCtx`, clear them.
- Existing review-modal `discardUpload()` keeps working unchanged against the same route.

### 5.4 Tests (`tests/test_db.py`)

- Confirmed upload: `delete_upload` removes all its transactions, the upload row; returns count.
- Manual transactions (`upload_id NULL`) and other uploads' transactions untouched.
- Pending upload: staged rows + upload removed (existing discard behaviour preserved).
- Stored file removed for pending upload.
- A backup file exists after delete and opens with the pre-delete row counts; only the newest 10 are kept.
- After delete, `check_duplicate(account_id, month)` is False.
- Settled / outstanding transactions are deleted too; `get_statements()` counts are correct beforehand.
- API: `DELETE /api/uploads/<id>` returns `deleted_count`; unknown id ⇒ 404.

### 5.5 Docs

Update `CLAUDE.md`: `delete_upload` in db.py list, the `data/backups/` folder + manual restore steps, route table row for `DELETE /api/uploads/<id>`, Upload & Staging Flow note.

---

## 6. Implications & considerations

| Area | Impact | Decision |
|---|---|---|
| **Settled transactions** | Deleting removes rows already reimbursed; Settlements history loses them. Money already moved between Shan and Janice in real life. | Allow, but warn with the count. See Open question 1. |
| **Outstanding settlements** | Matrix totals drop; a debt may look cleared when it is not. | Warn with the count. Re-uploading recreates rows with default `ideal_paid_by` = account owner, so prior source edits must be redone. |
| **User edits lost** | Category, Actual/Ideal Source, real-expense flag, description/amount edits on those rows vanish. Re-upload gives fresh Claude extraction. | Stated in confirm text. |
| **Rows already deleted by hand** (the `(-1)` in Active) | Already gone — no effect. | — |
| **Dashboard / budget** | Month totals and MoM delta change; budget card may change if it was the household latest month. | Expected. |
| **Coverage matrix** | Cell returns to missing (`+`), not to manual-blue. | Acceptable; user can re-mark manually. |
| **Duplicate detection** | Slot is free; re-upload is clean. Primary use case: "delete bad extraction, upload again". | Intended. |
| **Irreversibility** | Hard delete. No undo: the Dashboard 5s undo pattern replays single-row PATCHes and cannot restore dozens of deleted rows + an upload. | Confirm dialog with counts is the safety net. See Open question 3. |
| **Atomicity / FK** | Partial failure must not leave orphan transactions or an upload with no rows. | Single SQL transaction, children first. |
| **Stale client state** | `selectedTxIds`, `_settleByMonth`, `_dashData` may hold deleted ids until next load. | Each view refetches on `navigate()`; the delete happens on Statements, so no cross-view stale writes. |
| **CSV export by `upload_id`** | Returns empty after delete. | Expected. |

---

## 7. Open questions

1. ~~**Settled rows — warn or block?**~~ **Decided (2026-11-01): warn.** Deletion is allowed; the confirm dialog states the settled count.
2. ~~**Detach option?**~~ **Decided (2026-11-01): no.** The dialog offers only confirm full delete / cancel.
3. ~~**Safety backup?**~~ **Decided (2026-11-01): back-office backup only.** Every delete snapshots the DB first (see §5.1); keep the newest 10. There is **no restore entry point in the app** — no button, no route, no UI mention. Restore is manual:
   1. Stop the app.
   2. `cp data/backups/<chosen-backup>.db data/finance.db`
   3. Start the app.

   Restoring rewinds the **whole** database to that moment, so any work done after that delete is lost too.

---

## 8. Acceptance criteria

- [ ] Every row on the Statements page has a `Delete` action.
- [ ] Confirm dialog shows transaction count, total, and settled / outstanding-settlement counts when non-zero.
- [ ] Confirming removes the upload, all linked transactions, staged rows and stored file in one atomic operation.
- [ ] Manual transactions and other statements' transactions are untouched.
- [ ] Coverage cell for that `(account, month)` shows missing afterwards; re-uploading the same PDF gives no duplicate warning.
- [ ] Cancelling the dialog changes nothing.
- [ ] Review-modal Discard still works.
- [ ] Each delete writes a backup to `data/backups/` first; only the newest 10 are kept; a failed backup aborts the delete.
- [ ] Tests in §5.4 pass; `CLAUDE.md` updated.
