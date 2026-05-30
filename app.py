import os
import base64
import json
import io
import csv
import calendar
from flask import Flask, request, jsonify, render_template, Response
from dotenv import load_dotenv
import anthropic
import pypdf

from db import (init_db, get_accounts, create_account, update_account, delete_account,
                save_upload, save_staged, check_duplicate,
                get_transactions, get_transactions_by_ids, update_transaction, delete_transaction,
                create_transaction, get_staged, update_staged, delete_staged_tx, confirm_upload,
                discard_upload, get_dashboard_data, get_settlements, get_statements,
                parse_date, _dominant_month)
from rules import apply_rules, build_rules_prompt, build_bank_notes

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CATEGORIES = [
    "HOUSEHOLD & UTILITIES", "GROCERIES", "TRANSPORTATION", "ENTERTAINMENT",
    "SHOPPING", "HEALTHCARE", "DEBT REPAYMENT", "SAVINGS", "F&B",
    "OTHERS", "FAMILY", "VACATION", "BOOZE", "EDUCATION",
]

INDO_MONTHS = {
    'JANUARI': 1, 'FEBRUARI': 2, 'MARET': 3, 'APRIL': 4, 'MEI': 5, 'JUNI': 6,
    'JULI': 7, 'AGUSTUS': 8, 'SEPTEMBER': 9, 'OKTOBER': 10, 'NOVEMBER': 11, 'DESEMBER': 12,
    'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'MAY': 5, 'JUNE': 6,
    'JULY': 7, 'AUGUST': 8, 'OCTOBER': 10, 'DECEMBER': 12,
}

def _file_magic_matches(file_bytes, media_type):
    if media_type == 'application/pdf':
        return file_bytes[:4] == b'%PDF'
    if media_type == 'image/jpeg':
        return file_bytes[:3] == b'\xff\xd8\xff'
    if media_type == 'image/png':
        return file_bytes[:8] == b'\x89PNG\r\n\x1a\n'
    return False

def period_to_statement_date(period_str):
    parts = (period_str or '').upper().strip().split()
    if len(parts) == 2:
        m = INDO_MONTHS.get(parts[0])
        try:
            y = int(parts[1])
        except ValueError:
            return None
        if m and y:
            last_day = calendar.monthrange(y, m)[1]
            return f"{last_day:02d}/{m:02d}/{y}"
    return None

def build_extraction_prompt(rules_section='', bank_notes=''):
    notes_block = f'\n\n{bank_notes}' if bank_notes else ''
    rules_block = f'\n\n{rules_section}' if rules_section else ''
    return f"""You are a financial data extraction assistant. Analyze this credit card statement and extract every transaction line item.{notes_block}{rules_block}

Return a JSON object with exactly two top-level fields:
- statement_date: the billing cycle end date or statement date as printed on the statement (keep original format), or null if not found
- transactions: an array of objects with these exact fields:
  - date: transaction date string (keep original format from statement)
  - description: merchant/payee name, clean and readable
  - amount: numeric IDR amount. For foreign currency transactions, use the IDR equivalent shown on the statement. Positive = charge, negative = refund/credit. No symbols or commas.
  - currency: always "IDR"
  - original_amount: if the transaction was originally in a foreign currency, the original numeric amount; otherwise null
  - original_currency: if foreign currency, the 3-letter currency code (e.g. "USD", "SGD"); otherwise null
  - category: one of exactly {json.dumps(CATEGORIES)}
  - is_real_expense: true for actual purchases and expenses. false for: credit card payments, internal transfers, balance payments, auto-debit to own savings.

Rules:
- Extract every transaction line — skip headers, subtotals, opening/closing balances
- Return ONLY the raw JSON object, no markdown fences, no explanation

Example:
{{
  "statement_date": "31/10/2024",
  "transactions": [
    {{"date": "01/10/2024", "description": "GRAB", "amount": 45000, "currency": "IDR", "original_amount": null, "original_currency": null, "category": "TRANSPORTATION", "is_real_expense": true}},
    {{"date": "02/10/2024", "description": "NETFLIX", "amount": 154000, "currency": "IDR", "original_amount": 9.99, "original_currency": "USD", "category": "ENTERTAINMENT", "is_real_expense": true}},
    {{"date": "28/10/2024", "description": "PAYMENT RECEIVED", "amount": -5000000, "currency": "IDR", "original_amount": null, "original_currency": null, "category": "OTHERS", "is_real_expense": false}}
  ]
}}"""

def build_debit_extraction_prompt(rules_section='', bank_notes=''):
    notes_block = f'\n\n{bank_notes}' if bank_notes else ''
    rules_block = f'\n\n{rules_section}' if rules_section else ''
    return f"""You are a financial data extraction assistant. Analyze this debit/bank statement and extract every transaction.{notes_block}{rules_block}

Return a JSON object with exactly two top-level fields:
- period: the statement period as printed (e.g. "APRIL 2026")
- transactions: an array of objects with these exact fields:
  - date: transaction date as DD/MM/YYYY — use the year from the period (e.g. "01/04/2026" for APRIL 2026)
  - description: clean, readable merchant/payee name
  - amount: positive numeric IDR amount. No symbols or commas.
  - transaction_type: "DB" for debit/outgoing, "CR" for credit/incoming
  - category: one of exactly {json.dumps(CATEGORIES)}
  - is_real_expense: true for actual expenses. false for: large round-number self-transfers, all CR rows (always false for CR).

Rules:
- Extract ALL rows including incoming (CR) transfers — they are shown in review for context only
- Return ONLY the raw JSON object, no markdown fences, no explanation

Example:
{{
  "period": "APRIL 2026",
  "transactions": [
    {{"date": "01/04/2026", "description": "Arya valet", "amount": 30000, "transaction_type": "DB", "category": "TRANSPORTATION", "is_real_expense": true}},
    {{"date": "03/04/2026", "description": "Transfer from FAHMIANDINI KHOIRU – Keg Azana 1 s.d 3 April", "amount": 560000, "transaction_type": "CR", "category": "OTHERS", "is_real_expense": false}}
  ]
}}"""

init_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/accounts')
def api_accounts():
    return jsonify(get_accounts())

@app.route('/api/accounts', methods=['POST'])
def api_create_account():
    data = request.json or {}
    if not data.get('name') or not data.get('owner'):
        return jsonify({'error': 'name and owner are required'}), 400
    acc_id = create_account(data)
    return jsonify({'ok': True, 'id': acc_id})

@app.route('/api/accounts/<int:acc_id>', methods=['PATCH'])
def api_update_account(acc_id):
    update_account(acc_id, request.json or {})
    return jsonify({'ok': True})

@app.route('/api/accounts/<int:acc_id>', methods=['DELETE'])
def api_delete_account(acc_id):
    delete_account(acc_id)
    return jsonify({'ok': True})


@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    account_id = request.form.get('account_id')
    if not account_id:
        return jsonify({'error': 'No account selected'}), 400
    account_id = int(account_id)

    filename = file.filename or ''
    file_bytes = file.read()
    fname_lower = filename.lower()

    if fname_lower.endswith('.pdf'):
        media_type = 'application/pdf'
        if not _file_magic_matches(file_bytes, media_type):
            return jsonify({'error': 'File content does not match its extension.'}), 400
        password = request.form.get('password', '')
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                if reader.decrypt(password or '') == pypdf.PasswordType.NOT_DECRYPTED:
                    if not password:
                        return jsonify({'error': 'This PDF is password-protected. Please enter the password.'}), 400
                    return jsonify({'error': 'Incorrect PDF password.'}), 400
                writer = pypdf.PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                buf = io.BytesIO()
                writer.write(buf)
                file_bytes = buf.getvalue()
        except pypdf.errors.PdfReadError as e:
            return jsonify({'error': f'Could not read PDF: {e}'}), 400
    elif fname_lower.endswith(('.jpg', '.jpeg')):
        media_type = 'image/jpeg'
        if not _file_magic_matches(file_bytes, media_type):
            return jsonify({'error': 'File content does not match its extension.'}), 400
    elif fname_lower.endswith('.png'):
        media_type = 'image/png'
        if not _file_magic_matches(file_bytes, media_type):
            return jsonify({'error': 'File content does not match its extension.'}), 400
    else:
        return jsonify({'error': 'Unsupported file type. Please upload a PDF, JPG, or PNG.'}), 400

    encoded = base64.standard_b64encode(file_bytes).decode('utf-8')
    if media_type == 'application/pdf':
        content_block = {'type': 'document', 'source': {'type': 'base64', 'media_type': media_type, 'data': encoded}}
    else:
        content_block = {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': encoded}}

    all_accounts = get_accounts()
    account = next((a for a in all_accounts if a['id'] == account_id), {})
    account_name = account.get('name', '')
    account_type = account.get('account_type', 'credit')

    bank_notes = build_bank_notes(account_name)
    if account_type == 'debit':
        prompt_text = build_debit_extraction_prompt(build_rules_prompt(account_name), bank_notes)
    else:
        prompt_text = build_extraction_prompt(build_rules_prompt(account_name), bank_notes)

    try:
        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=8192,
            messages=[{'role': 'user', 'content': [content_block, {'type': 'text', 'text': prompt_text}]}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        if isinstance(parsed, list):
            extracted = parsed
            statement_date = None
        else:
            extracted = parsed.get('transactions', [])
            if account_type == 'debit':
                period = parsed.get('period')
                statement_date = period_to_statement_date(period) if period else None
            else:
                statement_date = parsed.get('statement_date')

        apply_rules(extracted, account_name)
        for t in extracted:
            t['date_parsed'] = parse_date(t.get('date', ''))

        parsed_sd = parse_date(statement_date) if statement_date else None
        stmt_month = parsed_sd[:7] if parsed_sd else _dominant_month(extracted)
        if stmt_month and check_duplicate(account_id, stmt_month):
            return jsonify({
                'duplicate': True,
                'statement_month': stmt_month,
                'statement_date': statement_date,
                'transactions': extracted,
                'count': len(extracted),
            })

        upload_id, stmt_month = save_staged(account_id, filename, extracted, statement_date=statement_date)
        return jsonify({'success': True, 'staged': True, 'upload_id': upload_id, 'count': len(extracted), 'statement_month': stmt_month})

    except json.JSONDecodeError as e:
        return jsonify({'error': f'Failed to parse extracted data: {e}'}), 500
    except anthropic.APIError as e:
        return jsonify({'error': f'API error: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload/confirm', methods=['POST'])
def api_upload_confirm():
    data = request.json or {}
    upload_id, stmt_month = save_staged(
        data['account_id'], data.get('filename', 'statement'), data.get('transactions', []),
        statement_date=data.get('statement_date'),
    )
    return jsonify({'success': True, 'staged': True, 'upload_id': upload_id, 'count': len(data.get('transactions', [])), 'statement_month': stmt_month})


@app.route('/api/transactions')
def api_transactions():
    is_real = request.args.get('is_real_expense')
    settled_val = request.args.get('settled')
    rows = get_transactions(
        owner=request.args.get('owner'),
        month=request.args.get('month'),
        account_id=request.args.get('account_id'),
        category=request.args.get('category'),
        is_real_expense=None if is_real is None else (is_real == '1'),
        unsettled=request.args.get('unsettled') == '1',
        search=request.args.get('q'),
        paid_by=request.args.get('paid_by'),
        ideal_paid_by=request.args.get('ideal_paid_by'),
        settled=None if settled_val is None else (settled_val == '1'),
        upload_id=request.args.get('upload_id'),
    )
    return jsonify(rows)


@app.route('/api/transactions', methods=['POST'])
def api_create_tx():
    data = request.json or {}
    if not data.get('account_id') or not data.get('date_parsed') or data.get('amount') is None:
        return jsonify({'error': 'account_id, date_parsed, and amount are required'}), 400
    if 'category' in data and data['category'] not in CATEGORIES:
        return jsonify({'error': f"Invalid category '{data['category']}'"}), 400
    tx_id = create_transaction(data)
    return jsonify({'ok': True, 'id': tx_id})


@app.route('/api/transactions/<int:tx_id>', methods=['PATCH'])
def api_update_tx(tx_id):
    data = request.json or {}
    if 'category' in data and data['category'] not in CATEGORIES:
        return jsonify({'error': f"Invalid category '{data['category']}'"}), 400
    update_transaction(tx_id, data)
    return jsonify({'ok': True})


@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def api_delete_tx(tx_id):
    delete_transaction(tx_id)
    return jsonify({'ok': True})


@app.route('/api/dashboard')
def api_dashboard():
    return jsonify(get_dashboard_data(
        owner=request.args.get('owner'),
        months=int(request.args.get('months', 6)),
    ))


@app.route('/api/settlements')
def api_settlements():
    return jsonify(get_settlements())


@app.route('/api/statements')
def api_statements():
    return jsonify(get_statements())


def _csv_date(date_parsed):
    if not date_parsed:
        return ''
    parts = date_parsed.split('-')
    if len(parts) != 3:
        return date_parsed
    y, m, d = parts
    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    return f"{d}-{months[int(m)-1]}-{y[2:]}"

def _csv_month(ym):
    if not ym:
        return ''
    parts = ym.split('-')
    if len(parts) != 2:
        return ym
    y, m = parts
    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    return f"{months[int(m)-1]}-{y[2:]}"

@app.route('/api/export')
def api_export():
    ids_param = request.args.get('ids')
    if ids_param:
        ids = [int(i) for i in ids_param.split(',') if i.strip().isdigit()]
        rows = get_transactions_by_ids(ids)
    else:
        rows = get_transactions(
            owner=request.args.get('owner'),
            month=request.args.get('month'),
            account_id=request.args.get('account_id'),
            category=request.args.get('category'),
            search=request.args.get('q'),
            upload_id=request.args.get('upload_id'),
        )
    rows.sort(key=lambda r: (r.get('date_parsed') or '', r.get('id') or 0))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Category', 'Expense Items Detail', 'Amount (Rp)',
                'Real expenses?', 'Paid By', 'Actual Source', 'Ideal Source',
                'Settled?', 'Card / Statement'])
    for r in rows:
        amt_str = int(round(r['amount'])) if r['amount'] is not None else ''
        stmt = f"CC {(r['bank'] or '').upper()} · {_csv_month(r['upload_statement_month'])}"
        w.writerow([
            _csv_date(r['date_parsed']),
            r['category'],
            r['description'],
            amt_str,
            'YES' if r['is_real_expense'] else 'NO',
            r['account_owner'],
            r['paid_by'],
            r['ideal_paid_by'] or '',
            'YES' if r['settled'] else 'NO',
            stmt,
        ])
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=transactions.csv'})


@app.route('/api/uploads/<int:upload_id>/staged')
def api_get_staged(upload_id):
    return jsonify(get_staged(upload_id))


@app.route('/api/staged/<int:tx_id>', methods=['PATCH'])
def api_update_staged(tx_id):
    data = request.json or {}
    if 'category' in data and data['category'] not in CATEGORIES:
        return jsonify({'error': f"Invalid category '{data['category']}'"}), 400
    update_staged(tx_id, data)
    return jsonify({'ok': True})


@app.route('/api/staged/<int:tx_id>', methods=['DELETE'])
def api_delete_staged(tx_id):
    delete_staged_tx(tx_id)
    return jsonify({'ok': True})


@app.route('/api/uploads/<int:upload_id>/confirm', methods=['POST'])
def api_confirm_upload(upload_id):
    count = confirm_upload(upload_id)
    return jsonify({'ok': True, 'confirmed_count': count})


@app.route('/api/uploads/<int:upload_id>', methods=['DELETE'])
def api_discard_upload(upload_id):
    discard_upload(upload_id)
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(debug=True, port=8080)
