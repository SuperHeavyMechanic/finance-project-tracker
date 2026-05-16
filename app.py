import os
import base64
import json
import io
import csv
from flask import Flask, request, jsonify, render_template, Response
from dotenv import load_dotenv
import anthropic
import pypdf

from db import (init_db, get_accounts, save_upload, check_duplicate,
                get_transactions, update_transaction, delete_transaction,
                get_dashboard_data, get_settlements, get_statements,
                parse_date, _dominant_month)
# from rules import apply_rules, build_rules_prompt  # disabled; see rules.py to re-enable

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CATEGORIES = [
    "HOUSEHOLD & UTILITIES", "GROCERIES", "TRANSPORTATION", "ENTERTAINMENT",
    "SHOPPING", "HEALTHCARE", "DEBT REPAYMENT", "SAVINGS", "F&B",
    "OTHERS", "FAMILY", "VACATION", "BOOZE", "EDUCATION",
]

def build_extraction_prompt(rules_section=''):
    rules_block = f'\n\n{rules_section}' if rules_section else ''
    return f"""You are a financial data extraction assistant. Analyze this credit card statement and extract every transaction line item.{rules_block}

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

init_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/accounts')
def api_accounts():
    return jsonify(get_accounts())


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
        password = request.form.get('password', '')
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                if not password:
                    return jsonify({'error': 'This PDF is password-protected. Please enter the password.'}), 400
                if reader.decrypt(password) == pypdf.PasswordType.NOT_DECRYPTED:
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
    elif fname_lower.endswith('.png'):
        media_type = 'image/png'
    else:
        return jsonify({'error': 'Unsupported file type. Please upload a PDF, JPG, or PNG.'}), 400

    encoded = base64.standard_b64encode(file_bytes).decode('utf-8')
    if media_type == 'application/pdf':
        content_block = {'type': 'document', 'source': {'type': 'base64', 'media_type': media_type, 'data': encoded}}
    else:
        content_block = {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': encoded}}

    all_accounts = get_accounts()
    account_name = next((a['name'] for a in all_accounts if a['id'] == account_id), '')
    prompt_text = build_extraction_prompt()  # build_rules_prompt(account_name) disabled

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
            statement_date = parsed.get('statement_date')

        # apply_rules(extracted, account_name)  # disabled; see rules.py to re-enable
        for t in extracted:
            t['date_parsed'] = parse_date(t.get('date', ''))

        stmt_month = _dominant_month(extracted)
        if stmt_month and check_duplicate(account_id, stmt_month):
            return jsonify({
                'duplicate': True,
                'statement_month': stmt_month,
                'statement_date': statement_date,
                'transactions': extracted,
                'count': len(extracted),
            })

        upload_id, stmt_month = save_upload(account_id, filename, extracted, statement_date=statement_date)
        return jsonify({'success': True, 'upload_id': upload_id, 'count': len(extracted), 'statement_month': stmt_month})

    except json.JSONDecodeError as e:
        return jsonify({'error': f'Failed to parse extracted data: {e}'}), 500
    except anthropic.APIError as e:
        return jsonify({'error': f'API error: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload/confirm', methods=['POST'])
def api_upload_confirm():
    data = request.json or {}
    upload_id, stmt_month = save_upload(
        data['account_id'], data.get('filename', 'statement'), data.get('transactions', []),
        statement_date=data.get('statement_date'),
    )
    return jsonify({'success': True, 'upload_id': upload_id, 'count': len(data.get('transactions', [])), 'statement_month': stmt_month})


@app.route('/api/transactions')
def api_transactions():
    is_real = request.args.get('is_real_expense')
    rows = get_transactions(
        owner=request.args.get('owner'),
        month=request.args.get('month'),
        account_id=request.args.get('account_id'),
        category=request.args.get('category'),
        is_real_expense=None if is_real is None else (is_real == '1'),
        unsettled=request.args.get('unsettled') == '1',
        search=request.args.get('q'),
    )
    return jsonify(rows)


@app.route('/api/transactions/<int:tx_id>', methods=['PATCH'])
def api_update_tx(tx_id):
    update_transaction(tx_id, request.json or {})
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


@app.route('/api/export')
def api_export():
    rows = get_transactions(
        owner=request.args.get('owner'),
        month=request.args.get('month'),
        account_id=request.args.get('account_id'),
        category=request.args.get('category'),
        search=request.args.get('q'),
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Description', 'Amount (IDR)', 'Currency', 'Orig Amount', 'Orig Currency',
                'Category', 'Account', 'Owner', 'Real Expense', 'Paid By', 'Settled'])
    for r in rows:
        w.writerow([
            r['date'], r['description'], r['amount'], r['currency'],
            r['original_amount'] or '', r['original_currency'] or '',
            r['category'], r['account_name'], r['account_owner'],
            'Yes' if r['is_real_expense'] else 'No',
            r['paid_by'], 'Yes' if r['settled'] else 'No',
        ])
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=transactions.csv'})


if __name__ == '__main__':
    app.run(debug=True, port=8080)
