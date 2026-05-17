import sqlite3
import os
import re
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'finance.db')

SEED_ACCOUNTS = [
    {'owner': 'SHAN',  'name': 'CC BNI VISA GARUDA',        'bank': 'BNI',           'last_four': '3738', 'account_type': 'credit'},
    {'owner': 'SHAN',  'name': 'CC MANDIRI VISA SIGNATURE',  'bank': 'Mandiri',        'last_four': '5856', 'account_type': 'credit'},
    {'owner': 'JOINT', 'name': 'CC JENIUS',                  'bank': 'Jenius (BTPN)',  'last_four': '9XXX', 'account_type': 'credit'},
    {'owner': 'SHAN',  'name': 'BCA Rekening Tahapan',       'bank': 'BCA',            'last_four': '4980', 'account_type': 'debit'},
]

_MONTH_MAP = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'mei': '05', 'jun': '06', 'jul': '07',
    'aug': '08', 'agt': '08', 'sep': '09', 'oct': '10',
    'okt': '10', 'nov': '11', 'dec': '12', 'des': '12',
}

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    m = re.match(r'^(\d{1,2})[\s\-]([A-Za-z]{3})[\s\-](\d{2,4})$', s)
    if m:
        d, mon, y = m.groups()
        mo = _MONTH_MAP.get(mon.lower(), '01')
        y = ('20' + y) if len(y) == 2 else y
        return f"{y}-{mo}-{d.zfill(2)}"
    return None

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            owner        TEXT NOT NULL,
            name         TEXT NOT NULL,
            bank         TEXT,
            last_four    TEXT,
            account_type TEXT DEFAULT 'credit',
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS uploads (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id        INTEGER REFERENCES accounts(id),
            filename          TEXT,
            statement_month   TEXT,
            uploaded_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            transaction_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id         INTEGER REFERENCES uploads(id),
            account_id        INTEGER REFERENCES accounts(id),
            date              TEXT,
            date_parsed       DATE,
            description       TEXT,
            amount            REAL,
            currency          TEXT DEFAULT 'IDR',
            original_amount   REAL,
            original_currency TEXT,
            category          TEXT,
            is_real_expense   INTEGER DEFAULT 1,
            paid_by           TEXT,
            settled           INTEGER DEFAULT 0,
            settled_date      DATE,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS staged_transactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id        INTEGER NOT NULL REFERENCES uploads(id),
            account_id       INTEGER NOT NULL REFERENCES accounts(id),
            date             TEXT,
            date_parsed      TEXT,
            description      TEXT,
            amount           REAL,
            category         TEXT,
            is_real_expense  INTEGER DEFAULT 1,
            transaction_type TEXT DEFAULT 'DB',
            original_currency TEXT,
            original_amount  REAL
        );
    ''')
    for _col_sql in [
        "ALTER TABLE uploads ADD COLUMN statement_date TEXT",
        "ALTER TABLE uploads ADD COLUMN original_total_amount REAL DEFAULT 0",
        "ALTER TABLE transactions ADD COLUMN ideal_paid_by TEXT",
        "ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'credit'",
    ]:
        try:
            conn.execute(_col_sql)
        except Exception:
            pass
    conn.commit()

    # Migration: re-derive statement_month from statement_date for all existing uploads
    stale = conn.execute('SELECT id, statement_date FROM uploads WHERE statement_date IS NOT NULL').fetchall()
    for u in stale:
        parsed = parse_date(u['statement_date'])
        if parsed:
            conn.execute('UPDATE uploads SET statement_month=? WHERE id=?', (parsed[:7], u['id']))
    conn.commit()

    for a in SEED_ACCOUNTS:
        exists = conn.execute(
            'SELECT id FROM accounts WHERE bank=? AND last_four=?',
            (a['bank'], a['last_four'])
        ).fetchone()
        if not exists:
            conn.execute(
                'INSERT INTO accounts (owner, name, bank, last_four, account_type) VALUES (?,?,?,?,?)',
                (a['owner'], a['name'], a['bank'], a['last_four'], a.get('account_type', 'credit'))
            )
    conn.commit()
    conn.close()

def get_accounts():
    conn = get_db()
    rows = conn.execute('''
        SELECT a.*,
               COUNT(t.id)       AS tx_count,
               MAX(u.uploaded_at) AS last_upload
        FROM accounts a
        LEFT JOIN uploads u      ON u.account_id = a.id
        LEFT JOIN transactions t ON t.account_id = a.id
        GROUP BY a.id
        ORDER BY a.owner, a.name
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _dominant_month(transactions):
    dates = [t.get('date_parsed') for t in transactions if t.get('date_parsed')]
    if not dates:
        return None
    months = [d[:7] for d in dates]
    return max(set(months), key=months.count)

def check_duplicate(account_id, statement_month):
    if not statement_month:
        return False
    conn = get_db()
    exists = conn.execute(
        'SELECT id FROM uploads WHERE account_id=? AND statement_month=?',
        (account_id, statement_month)
    ).fetchone()
    conn.close()
    return exists is not None

def save_upload(account_id, filename, transactions, statement_date=None):
    conn = get_db()
    row = conn.execute('SELECT owner FROM accounts WHERE id=?', (account_id,)).fetchone()
    owner = row['owner'] if row else 'SHAN'
    parsed_sd = parse_date(statement_date) if statement_date else None
    stmt_month = parsed_sd[:7] if parsed_sd else _dominant_month(transactions)
    original_total = sum((t.get('amount') or 0) for t in transactions if (t.get('amount') or 0) > 0)

    c = conn.cursor()
    c.execute(
        'INSERT INTO uploads (account_id, filename, statement_month, transaction_count, statement_date, original_total_amount) VALUES (?,?,?,?,?,?)',
        (account_id, filename, stmt_month, len(transactions), statement_date, original_total)
    )
    upload_id = c.lastrowid

    for t in transactions:
        c.execute('''
            INSERT INTO transactions
              (upload_id, account_id, date, date_parsed, description,
               amount, currency, original_amount, original_currency,
               category, is_real_expense, paid_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            upload_id, account_id,
            t.get('date'), t.get('date_parsed'),
            t.get('description'),
            t.get('amount', 0),
            t.get('currency', 'IDR'),
            t.get('original_amount'),
            t.get('original_currency'),
            t.get('category', 'OTHERS'),
            1 if t.get('is_real_expense', True) else 0,
            owner,
        ))

    conn.commit()
    conn.close()
    return upload_id, stmt_month

def get_transactions(owner=None, month=None, account_id=None, category=None,
                     is_real_expense=None, unsettled=False, search=None,
                     paid_by=None, ideal_paid_by=None, settled=None, upload_id=None):
    conn = get_db()
    q = '''
        SELECT t.*, a.name AS account_name, a.owner AS account_owner, a.bank,
               u.statement_date, u.statement_month AS upload_statement_month, u.filename AS upload_filename
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN uploads u ON u.id = t.upload_id
        WHERE 1=1
    '''
    p = []
    if owner and owner != 'ALL':
        q += ' AND a.owner=?'; p.append(owner)
    if month:
        q += " AND substr(t.date_parsed,1,7)=?"; p.append(month)
    if account_id:
        q += ' AND t.account_id=?'; p.append(account_id)
    if category:
        q += ' AND t.category=?'; p.append(category)
    if is_real_expense is not None:
        q += ' AND t.is_real_expense=?'; p.append(1 if is_real_expense else 0)
    if unsettled:
        q += ' AND t.settled=0 AND t.paid_by != a.owner'
    if search:
        q += ' AND t.description LIKE ?'; p.append(f'%{search}%')
    if paid_by:
        q += ' AND t.paid_by=?'; p.append(paid_by)
    if ideal_paid_by:
        q += ' AND t.ideal_paid_by=?'; p.append(ideal_paid_by)
    if settled is not None:
        q += ' AND t.settled=?'; p.append(1 if settled else 0)
    if upload_id:
        q += ' AND t.upload_id=?'; p.append(int(upload_id))
    q += ' ORDER BY t.date_parsed DESC, t.id DESC'
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_transaction(tx_id, fields):
    allowed = {'category', 'is_real_expense', 'paid_by', 'ideal_paid_by', 'settled', 'settled_date', 'amount'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    conn = get_db()
    clause = ', '.join(f'{k}=?' for k in updates)
    conn.execute(f'UPDATE transactions SET {clause} WHERE id=?', list(updates.values()) + [tx_id])
    conn.commit()
    conn.close()

def get_transactions_by_ids(ids):
    if not ids:
        return []
    conn = get_db()
    placeholders = ','.join('?' * len(ids))
    rows = conn.execute(f'''
        SELECT t.*, a.name AS account_name, a.owner AS account_owner, a.bank,
               u.statement_date, u.statement_month AS upload_statement_month, u.filename AS upload_filename
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN uploads u ON u.id = t.upload_id
        WHERE t.id IN ({placeholders})
        ORDER BY t.date_parsed DESC, t.id DESC
    ''', ids).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_transaction(tx_id):
    conn = get_db()
    conn.execute('DELETE FROM transactions WHERE id=?', (tx_id,))
    conn.commit()
    conn.close()


def get_dashboard_data(owner=None, months=6):
    conn = get_db()

    of = "AND a.owner=?" if (owner and owner != 'ALL') else ""
    op = [owner] if (owner and owner != 'ALL') else []

    # Use the N most recent months that actually have data
    data_months = conn.execute(f'''
        SELECT DISTINCT substr(t.date_parsed,1,7) AS month
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.is_real_expense=1 AND t.amount>0 AND t.date_parsed IS NOT NULL {of}
        ORDER BY month DESC LIMIT ?
    ''', op + [months]).fetchall()

    if data_months:
        month_list = sorted(r['month'] for r in data_months)
    else:
        today = date.today()
        month_list = []
        for i in range(months - 1, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12; y -= 1
            month_list.append(f"{y}-{m:02d}")

    trend_rows = conn.execute(f'''
        SELECT substr(t.date_parsed,1,7) AS month, t.category, SUM(t.amount) AS total
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.is_real_expense=1 AND t.amount>0
          AND substr(t.date_parsed,1,7) IN ({','.join('?'*len(month_list))}) {of}
        GROUP BY month, t.category
    ''', month_list + op).fetchall()

    trend = {m: {} for m in month_list}
    for r in trend_rows:
        if r['month'] in trend:
            trend[r['month']][r['category']] = r['total']

    summary_month = month_list[-1]
    cat_rows = conn.execute(f'''
        SELECT t.category, SUM(t.amount) AS total, COUNT(*) AS cnt
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.is_real_expense=1 AND t.amount>0 AND substr(t.date_parsed,1,7)=? {of}
        GROUP BY t.category ORDER BY total DESC
    ''', [summary_month] + op).fetchall()

    biggest = conn.execute(f'''
        SELECT description, amount
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.is_real_expense=1 AND t.amount>0 AND substr(t.date_parsed,1,7)=? {of}
        ORDER BY t.amount DESC LIMIT 1
    ''', [summary_month] + op).fetchone()

    conn.close()
    return {
        'trend': [{'month': m, 'categories': trend[m]} for m in month_list],
        'summary': {
            'month': summary_month,
            'total': sum(r['total'] for r in cat_rows),
            'tx_count': sum(r['cnt'] for r in cat_rows),
            'biggest': dict(biggest) if biggest else None,
            'top_categories': [{'category': r['category'], 'total': r['total']} for r in cat_rows[:3]],
        },
    }

def get_settlements():
    conn = get_db()
    rows = conn.execute('''
        SELECT t.*, a.name AS account_name, a.owner AS account_owner
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        WHERE t.paid_by != a.owner AND t.is_real_expense=1 AND t.amount>0
        ORDER BY t.settled ASC, t.date_parsed DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_statements():
    conn = get_db()
    uploads = conn.execute('''
        SELECT u.id, u.account_id, u.filename, u.statement_month, u.statement_date,
               u.uploaded_at, u.transaction_count AS original_count,
               u.original_total_amount AS original_total,
               COUNT(t.id) AS active_count,
               COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0) AS active_total,
               (SELECT COUNT(*) FROM staged_transactions st WHERE st.upload_id = u.id) AS staged_count
        FROM uploads u
        LEFT JOIN transactions t ON t.upload_id = u.id
        GROUP BY u.id
        ORDER BY u.account_id, u.statement_month DESC
    ''').fetchall()
    accounts = conn.execute('SELECT * FROM accounts ORDER BY owner, name').fetchall()
    conn.close()

    acc_map = {a['id']: dict(a) for a in accounts}
    result = {}
    for u in uploads:
        u = dict(u)
        aid = u['account_id']
        if aid not in result:
            result[aid] = {'account': acc_map[aid], 'uploads': []}
        result[aid]['uploads'].append(u)
    return list(result.values())


def save_staged(account_id, filename, transactions, statement_date=None):
    conn = get_db()
    parsed_sd = parse_date(statement_date) if statement_date else None
    stmt_month = parsed_sd[:7] if parsed_sd else _dominant_month(transactions)
    original_total = sum(
        (t.get('amount') or 0) for t in transactions
        if (t.get('amount') or 0) > 0 and t.get('transaction_type', 'DB') == 'DB'
    )

    c = conn.cursor()
    c.execute(
        'INSERT INTO uploads (account_id, filename, statement_month, transaction_count, statement_date, original_total_amount) VALUES (?,?,?,?,?,?)',
        (account_id, filename, stmt_month, len(transactions), statement_date, original_total)
    )
    upload_id = c.lastrowid

    for t in transactions:
        c.execute('''
            INSERT INTO staged_transactions
              (upload_id, account_id, date, date_parsed, description,
               amount, category, is_real_expense, transaction_type,
               original_currency, original_amount)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            upload_id, account_id,
            t.get('date'), t.get('date_parsed'),
            t.get('description'),
            t.get('amount', 0),
            t.get('category', 'OTHERS'),
            1 if t.get('is_real_expense', True) else 0,
            t.get('transaction_type', 'DB'),
            t.get('original_currency'),
            t.get('original_amount'),
        ))

    conn.commit()
    conn.close()
    return upload_id, stmt_month


def get_staged(upload_id):
    conn = get_db()
    rows = conn.execute('''
        SELECT s.*, a.name AS account_name, a.owner AS account_owner, a.bank, a.account_type,
               u.statement_date, u.statement_month
        FROM staged_transactions s
        JOIN accounts a ON a.id = s.account_id
        JOIN uploads u ON u.id = s.upload_id
        WHERE s.upload_id=?
        ORDER BY s.transaction_type DESC, s.id ASC
    ''', (upload_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_staged(tx_id, fields):
    allowed = {'category', 'description', 'amount', 'is_real_expense'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    conn = get_db()
    clause = ', '.join(f'{k}=?' for k in updates)
    conn.execute(f'UPDATE staged_transactions SET {clause} WHERE id=?', list(updates.values()) + [tx_id])
    conn.commit()
    conn.close()


def delete_staged_tx(tx_id):
    conn = get_db()
    conn.execute('DELETE FROM staged_transactions WHERE id=?', (tx_id,))
    conn.commit()
    conn.close()


def confirm_upload(upload_id):
    conn = get_db()
    upload = conn.execute('SELECT account_id FROM uploads WHERE id=?', (upload_id,)).fetchone()
    if not upload:
        conn.close()
        return 0
    account = conn.execute('SELECT owner FROM accounts WHERE id=?', (upload['account_id'],)).fetchone()
    owner = account['owner'] if account else 'SHAN'

    staged = conn.execute(
        "SELECT * FROM staged_transactions WHERE upload_id=? AND transaction_type='DB'",
        (upload_id,)
    ).fetchall()

    c = conn.cursor()
    for t in staged:
        c.execute('''
            INSERT INTO transactions
              (upload_id, account_id, date, date_parsed, description,
               amount, currency, original_amount, original_currency,
               category, is_real_expense, paid_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            upload_id, t['account_id'],
            t['date'], t['date_parsed'],
            t['description'],
            t['amount'],
            'IDR',
            t['original_amount'],
            t['original_currency'],
            t['category'],
            t['is_real_expense'],
            owner,
        ))

    c.execute('UPDATE uploads SET transaction_count=? WHERE id=?', (len(staged), upload_id))
    c.execute('DELETE FROM staged_transactions WHERE upload_id=?', (upload_id,))
    conn.commit()
    conn.close()
    return len(staged)


def discard_upload(upload_id):
    conn = get_db()
    conn.execute('DELETE FROM staged_transactions WHERE upload_id=?', (upload_id,))
    conn.execute('DELETE FROM uploads WHERE id=?', (upload_id,))
    conn.commit()
    conn.close()
