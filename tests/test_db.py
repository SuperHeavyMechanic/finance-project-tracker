"""
Automated tests for the finance tracker.
Run from the project root with: pytest

Each test gets its own empty temporary database — your real data/finance.db
is never read or written during tests.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    """Redirect DB_PATH to a temp file and initialise a clean schema."""
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / "test.db"))
    db.init_db()


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Flask test client backed by a fresh temporary database."""
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / "test.db"))
    db.init_db()
    import app as flask_app
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as c:
        yield c


def _account(**kwargs):
    defaults = {
        'owner': 'SHAN', 'name': 'Test Card',
        'bank': 'TestBank', 'last_four': '9999', 'account_type': 'credit',
    }
    defaults.update(kwargs)
    return db.create_account(defaults)


def _tx(**kwargs):
    defaults = {
        'date': '01/04/2026', 'date_parsed': '2026-04-01',
        'description': 'Test transaction', 'amount': 50000,
        'category': 'GROCERIES', 'is_real_expense': True,
        'transaction_type': 'DB',
    }
    defaults.update(kwargs)
    return defaults


# ── parse_date ────────────────────────────────────────────────────────────────

class TestParseDate:
    """parse_date() must handle every date format that Indonesian banks produce."""

    def test_iso_passthrough(self):
        assert db.parse_date("2026-04-15") == "2026-04-15"

    def test_slash_dd_mm_yyyy(self):
        assert db.parse_date("15/04/2026") == "2026-04-15"

    def test_dash_dd_mm_yyyy(self):
        assert db.parse_date("15-04-2026") == "2026-04-15"

    def test_slash_dd_mm_yy(self):
        assert db.parse_date("15/04/26") == "2026-04-15"

    def test_dash_dd_mm_yy(self):
        assert db.parse_date("15-04-26") == "2026-04-15"

    def test_month_abbrev_apr(self):
        assert db.parse_date("15-Apr-26") == "2026-04-15"

    def test_month_abbrev_mei(self):
        # Indonesian May abbreviation
        assert db.parse_date("15-Mei-26") == "2026-05-15"

    def test_month_abbrev_agt(self):
        # Indonesian August abbreviation
        assert db.parse_date("15-Agt-26") == "2026-08-15"

    def test_month_abbrev_des(self):
        # Indonesian December abbreviation
        assert db.parse_date("31-Des-26") == "2026-12-31"

    def test_month_name_no_separator(self):
        # HSBC statement date
        assert db.parse_date("20OCT2026") == "2026-10-20"

    def test_month_name_spaces_indonesian(self):
        # UOB statement / due dates
        assert db.parse_date("18 OKT 2026") == "2026-10-18"
        assert db.parse_date("03 NOP 2026") == "2026-11-03"

    def test_full_indonesian_month_name(self):
        # Jenius statement date
        assert db.parse_date("24 Agustus 2026") == "2026-08-24"

    def test_unknown_month_returns_none(self):
        # Previously defaulted silently to January
        assert db.parse_date("15-Xyz-26") is None

    def test_year_less_needs_ref_date(self):
        assert db.parse_date("21SEP") is None

    def test_year_less_takes_statement_year(self):
        assert db.parse_date("21SEP", ref_date="2026-10-20") == "2026-09-21"
        assert db.parse_date("09 OKT", ref_date="2026-10-18") == "2026-10-09"

    def test_year_less_dd_mm(self):
        # Danamon rows
        assert db.parse_date("16/09", ref_date="2026-10-15") == "2026-09-16"
        assert db.parse_date("16/09") is None

    def test_year_less_rolls_back_across_new_year(self):
        assert db.parse_date("28DEC", ref_date="2027-01-20") == "2026-12-28"

    def test_empty_string_returns_none(self):
        assert db.parse_date("") is None

    def test_none_returns_none(self):
        assert db.parse_date(None) is None


# ── confirm_upload ─────────────────────────────────────────────────────────────

class TestConfirmUpload:
    """confirm_upload() must only promote DB rows — CR rows must be excluded."""

    def test_cr_rows_are_excluded(self, fresh_db):
        acc_id = _account()
        txs = [
            _tx(description='Coffee', transaction_type='DB'),
            _tx(description='Top-up received', amount=200000,
                is_real_expense=False, transaction_type='CR'),
        ]
        upload_id, _ = db.save_staged(acc_id, 'test.pdf', txs, statement_date='30/04/2026')
        count = db.confirm_upload(upload_id)

        assert count == 1
        confirmed = db.get_transactions()
        assert len(confirmed) == 1
        assert confirmed[0]['description'] == 'Coffee'

    def test_all_db_rows_are_saved(self, fresh_db):
        acc_id = _account()
        txs = [_tx(description='Grab'), _tx(description='Indomaret')]
        upload_id, _ = db.save_staged(acc_id, 'test.pdf', txs, statement_date='30/04/2026')
        count = db.confirm_upload(upload_id)

        assert count == 2
        assert len(db.get_transactions()) == 2

    def test_staged_rows_cleared_after_confirm(self, fresh_db):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        db.confirm_upload(upload_id)

        assert db.get_staged(upload_id) == []

    def test_returns_zero_for_missing_upload(self, fresh_db):
        assert db.confirm_upload(99999) == 0


# ── check_duplicate ────────────────────────────────────────────────────────────

class TestCheckDuplicate:
    """check_duplicate() must catch the same account+month, not over-block."""

    def test_same_account_same_month_is_duplicate(self, fresh_db):
        acc_id = _account()
        db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        assert db.check_duplicate(acc_id, '2026-04') is True

    def test_same_account_different_month_not_duplicate(self, fresh_db):
        acc_id = _account()
        db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        assert db.check_duplicate(acc_id, '2026-05') is False

    def test_different_account_same_month_not_duplicate(self, fresh_db):
        acc_a = _account(name='Card A', last_four='1111')
        acc_b = _account(name='Card B', last_four='2222')
        db.save_staged(acc_a, 'test.pdf', [_tx()], statement_date='30/04/2026')
        assert db.check_duplicate(acc_b, '2026-04') is False

    def test_no_uploads_returns_false(self, fresh_db):
        acc_id = _account()
        assert db.check_duplicate(acc_id, '2026-04') is False


# ── category validation ────────────────────────────────────────────────────────

class TestCategoryValidation:
    """
    The API must reject any category value not in the CATEGORIES list.
    These tests hit the Flask routes directly.
    """

    def test_invalid_category_rejected_on_tx_update(self, client):
        resp = client.patch('/api/transactions/1',
                            json={'category': 'NOT_REAL'},
                            content_type='application/json')
        assert resp.status_code == 400
        assert 'Invalid category' in resp.get_json()['error']

    def test_invalid_category_rejected_on_staged_update(self, client):
        resp = client.patch('/api/staged/1',
                            json={'category': 'FAKE_CAT'},
                            content_type='application/json')
        assert resp.status_code == 400
        assert 'Invalid category' in resp.get_json()['error']

    def test_valid_category_passes_validation(self, client):
        # Non-existent tx ID is fine here — we're only checking the category
        # check doesn't fire for a valid value (it would return ok regardless)
        resp = client.patch('/api/transactions/999999',
                            json={'category': 'GROCERIES'},
                            content_type='application/json')
        error = (resp.get_json() or {}).get('error', '')
        assert 'Invalid category' not in error

    def test_invalid_category_rejected_on_create(self, client):
        resp = client.post('/api/transactions',
                           json={
                               'account_id': 1,
                               'date_parsed': '2026-04-01',
                               'amount': 50000,
                               'category': 'NONSENSE',
                           },
                           content_type='application/json')
        assert resp.status_code == 400
        assert 'Invalid category' in resp.get_json()['error']


class TestStatementSummary:
    """save_staged() must persist printed summary figures; get_staged() must expose them."""

    def test_summary_roundtrip(self, fresh_db):
        acc_id = _account()
        summary = {'prev_balance': 5000000, 'credits_total': 5000000,
                   'debits_total': 4800000, 'new_balance': 4800000}
        upload_id, _ = db.save_staged(acc_id, 'test.pdf', [_tx()],
                                      statement_date='30/04/2026', summary=summary)
        rows = db.get_staged(upload_id)
        assert rows[0]['summary_prev_balance'] == 5000000
        assert rows[0]['summary_credits_total'] == 5000000
        assert rows[0]['summary_debits_total'] == 4800000
        assert rows[0]['summary_new_balance'] == 4800000

    def test_summary_defaults_to_null(self, fresh_db):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        rows = db.get_staged(upload_id)
        assert rows[0]['summary_prev_balance'] is None
        assert rows[0]['summary_new_balance'] is None


class TestStatementFileLifecycle:
    """Statement files persist only while a review is pending — deleted on confirm/discard."""

    def _stage_with_file(self):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 't.pdf', [_tx()], statement_date='30/04/2026',
                                      file_bytes=b'%PDF-fake', file_ext='pdf')
        return upload_id, db.statement_file_path(upload_id, 'pdf')

    def test_file_written_on_stage(self, fresh_db):
        upload_id, path = self._stage_with_file()
        assert os.path.exists(path)
        assert db.get_upload_file(upload_id) == (path, 'pdf')
        assert db.get_staged(upload_id)[0]['stored_ext'] == 'pdf'

    def test_file_deleted_on_confirm(self, fresh_db):
        upload_id, path = self._stage_with_file()
        db.confirm_upload(upload_id)
        assert not os.path.exists(path)
        assert db.get_upload_file(upload_id) is None

    def test_file_deleted_on_discard(self, fresh_db):
        upload_id, path = self._stage_with_file()
        db.delete_upload(upload_id)
        assert not os.path.exists(path)

    def test_no_file_when_none_given(self, fresh_db):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 't.pdf', [_tx()], statement_date='30/04/2026')
        assert db.get_upload_file(upload_id) is None

    def test_orphan_sweep_on_init(self, fresh_db):
        upload_id, pending_path = self._stage_with_file()
        stray = os.path.join(os.path.dirname(pending_path), '99999.pdf')
        with open(stray, 'wb') as f:
            f.write(b'%PDF-stray')
        db.init_db()
        assert not os.path.exists(stray)
        assert os.path.exists(pending_path)  # pending review must survive the sweep


class TestDeleteUpload:
    """delete_upload() removes a statement and every transaction linked to it."""

    def _confirmed(self, n=3, month='04'):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 't.pdf', [_tx() for _ in range(n)],
                                      statement_date=f'30/{month}/2026')
        db.confirm_upload(upload_id)
        return acc_id, upload_id

    def _tx_ids(self, upload_id):
        return [t['id'] for t in db.get_transactions(upload_id=upload_id)]

    def test_confirmed_upload_and_transactions_removed(self, fresh_db):
        acc_id, upload_id = self._confirmed(n=3)
        assert db.delete_upload(upload_id) == 3
        assert db.get_transactions(upload_id=upload_id) == []
        assert db.get_statements() == []

    def test_other_rows_untouched(self, fresh_db):
        acc_id, upload_id = self._confirmed(n=2)
        upload_b, _ = db.save_staged(acc_id, 'b.pdf', [_tx()], statement_date='31/05/2026')
        db.confirm_upload(upload_b)
        db.create_transaction({'account_id': acc_id, 'date_parsed': '2026-04-02',
                               'description': 'Manual', 'amount': 1000,
                               'category': 'GROCERIES', 'paid_by': 'SHAN'})
        db.delete_upload(upload_id)
        remaining = db.get_transactions()
        assert len(remaining) == 2
        assert {t['upload_id'] for t in remaining} == {upload_b, None}

    def test_pending_upload_removed(self, fresh_db):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 't.pdf', [_tx(), _tx()], statement_date='30/04/2026')
        assert db.delete_upload(upload_id) == 0
        assert db.get_staged(upload_id) == []
        assert db.get_statements() == []

    def test_slot_freed_for_reupload(self, fresh_db):
        acc_id, upload_id = self._confirmed()
        assert db.check_duplicate(acc_id, '2026-04')
        db.delete_upload(upload_id)
        assert not db.check_duplicate(acc_id, '2026-04')

    def test_unknown_upload_returns_none(self, fresh_db):
        assert db.delete_upload(9999) is None

    def test_settlement_counts_then_deleted(self, fresh_db):
        acc_id, upload_id = self._confirmed(n=3)
        a, b, _ = self._tx_ids(upload_id)
        db.update_transaction(a, {'settled': 1, 'settled_date': '2026-05-01'})
        db.update_transaction(b, {'ideal_paid_by': 'JANICE'})
        u = db.get_statements()[0]['uploads'][0]
        assert u['settled_count'] == 1
        assert u['outstanding_settle_count'] == 1
        assert db.delete_upload(upload_id) == 3
        assert db.get_settlements() == []

    def test_backup_written_with_pre_delete_state(self, fresh_db):
        import sqlite3
        acc_id, upload_id = self._confirmed(n=3)
        db.delete_upload(upload_id)
        backups = os.listdir(db._backups_dir())
        assert len(backups) == 1
        assert f'before-delete-upload-{upload_id}' in backups[0]
        conn = sqlite3.connect(os.path.join(db._backups_dir(), backups[0]))
        assert conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == 3
        conn.close()

    def test_only_newest_backups_kept(self, fresh_db):
        for _ in range(db.BACKUPS_KEPT + 2):
            _, upload_id = self._confirmed(n=1)
            db.delete_upload(upload_id)
        assert len(os.listdir(db._backups_dir())) == db.BACKUPS_KEPT


class TestDeleteUploadApi:
    def test_delete_returns_count(self, client):
        acc_id = _account()
        upload_id, _ = db.save_staged(acc_id, 't.pdf', [_tx(), _tx()], statement_date='30/04/2026')
        db.confirm_upload(upload_id)
        r = client.delete(f'/api/uploads/{upload_id}')
        assert r.status_code == 200
        assert r.get_json() == {'ok': True, 'deleted_count': 2}

    def test_unknown_id_404(self, client):
        assert client.delete('/api/uploads/9999').status_code == 404


class TestTransactionFilters:
    """get_transactions() filters added for the Transactions filter bar."""

    def _add(self, acc_id, **kw):
        fields = {'account_id': acc_id, 'date_parsed': '2026-10-01', 'description': 'Row',
                  'amount': 1000, 'category': 'GROCERIES', 'paid_by': 'SHAN'}
        fields.update(kw)
        db.create_transaction(fields)

    def test_wrong_source(self, fresh_db):
        acc_id = _account()
        self._add(acc_id, description='match', paid_by='SHAN', ideal_paid_by='JOINT')
        self._add(acc_id, description='same', paid_by='SHAN', ideal_paid_by='SHAN')
        self._add(acc_id, description='no ideal', paid_by='SHAN')
        rows = db.get_transactions(wrong_source=True)
        assert [r['description'] for r in rows] == ['match']

    def test_amount_search(self, fresh_db):
        acc_id = _account()
        self._add(acc_id, description='Superindo', amount=642500)
        self._add(acc_id, description='Other', amount=120000)
        for q in ('642500', '642.500', 'Rp 642.500', 'rp642,500'):
            assert [r['description'] for r in db.get_transactions(search=q)] == ['Superindo'], q

    def test_amount_search_matches_negative_rows(self, fresh_db):
        acc_id = _account()
        self._add(acc_id, description='Refund', amount=-642500)
        assert len(db.get_transactions(search='642.500')) == 1

    def test_text_search_is_description_only(self, fresh_db):
        acc_id = _account()
        self._add(acc_id, description='Superindo groceries', amount=642500)
        assert len(db.get_transactions(search='superindo')) == 1
        assert db.get_transactions(search='superindo 642') == []

    def test_wrong_source_api(self, client):
        acc_id = _account()
        self._add(acc_id, description='match', paid_by='SHAN', ideal_paid_by='JANICE')
        self._add(acc_id, description='same', paid_by='SHAN', ideal_paid_by='SHAN')
        rows = client.get('/api/transactions?wrong_source=1').get_json()
        assert [r['description'] for r in rows] == ['match']


class TestManualCoverage:
    """Manual coverage marks a (account, month) cell as 'entered by hand' —
    purely a bookkeeping flag, cleared automatically once a real upload lands there."""

    def test_mark_and_get(self, fresh_db):
        acc_id = _account()
        db.mark_manual_coverage(acc_id, '2026-06')
        rows = db.get_manual_coverage()
        assert rows == [{'account_id': acc_id, 'month': '2026-06'}]

    def test_mark_is_idempotent(self, fresh_db):
        acc_id = _account()
        db.mark_manual_coverage(acc_id, '2026-06')
        db.mark_manual_coverage(acc_id, '2026-06')
        assert len(db.get_manual_coverage()) == 1

    def test_unmark_removes_it(self, fresh_db):
        acc_id = _account()
        db.mark_manual_coverage(acc_id, '2026-06')
        db.unmark_manual_coverage(acc_id, '2026-06')
        assert db.get_manual_coverage() == []

    def test_unmark_missing_is_a_noop(self, fresh_db):
        acc_id = _account()
        db.unmark_manual_coverage(acc_id, '2026-06')  # must not raise
        assert db.get_manual_coverage() == []

    def test_cleared_when_real_upload_lands_on_same_slot(self, fresh_db):
        acc_id = _account()
        db.mark_manual_coverage(acc_id, '2026-04')
        db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        assert db.get_manual_coverage() == []

    def test_untouched_for_a_different_slot(self, fresh_db):
        acc_id = _account()
        db.mark_manual_coverage(acc_id, '2026-05')
        db.save_staged(acc_id, 'test.pdf', [_tx()], statement_date='30/04/2026')
        assert db.get_manual_coverage() == [{'account_id': acc_id, 'month': '2026-05'}]


class TestManualCoverageApi:
    def test_post_rejects_bad_month(self, client):
        resp = client.post('/api/manual-coverage', json={'account_id': 1, 'month': 'June-2026'},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_post_rejects_missing_account(self, client):
        resp = client.post('/api/manual-coverage', json={'month': '2026-06'},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_post_and_get_roundtrip(self, client):
        resp = client.post('/api/manual-coverage', json={'account_id': 1, 'month': '2026-06'},
                           content_type='application/json')
        assert resp.status_code == 200
        data = client.get('/api/manual-coverage').get_json()
        assert data == [{'account_id': 1, 'month': '2026-06'}]

    def test_delete_removes_it(self, client):
        client.post('/api/manual-coverage', json={'account_id': 1, 'month': '2026-06'},
                    content_type='application/json')
        resp = client.delete('/api/manual-coverage/1/2026-06')
        assert resp.status_code == 200
        assert client.get('/api/manual-coverage').get_json() == []


class TestSettings:
    def test_get_missing_setting_returns_none(self, fresh_db):
        assert db.get_setting('monthly_budget') is None

    def test_set_and_get_setting(self, fresh_db):
        db.set_setting('monthly_budget', '15000000')
        assert db.get_setting('monthly_budget') == '15000000'

    def test_set_setting_overwrites(self, fresh_db):
        db.set_setting('monthly_budget', '15000000')
        db.set_setting('monthly_budget', '20000000')
        assert db.get_setting('monthly_budget') == '20000000'


class TestBudgetApi:
    def test_dashboard_budget_null_when_unset(self, client):
        data = client.get('/api/dashboard').get_json()
        assert data['budget'] is None
        assert 'household_latest_total' in data
        assert 'household_latest_month' in data

    def test_put_budget_persists_to_dashboard(self, client):
        resp = client.put('/api/budget', json={'amount': 15000000},
                          content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['budget'] == 15000000
        data = client.get('/api/dashboard').get_json()
        assert data['budget'] == 15000000

    def test_put_budget_rejects_invalid_amounts(self, client):
        for payload in [{}, {'amount': 0}, {'amount': -5}, {'amount': 'abc'},
                        {'amount': 1.5}, {'amount': True}]:
            resp = client.put('/api/budget', json=payload,
                              content_type='application/json')
            assert resp.status_code == 400, f'payload {payload} should be rejected'
