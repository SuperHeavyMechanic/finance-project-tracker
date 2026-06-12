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
