# ── CATEGORY OVERRIDES ──────────────────────────────────────────────────────
# Applied post-extraction by apply_rules(). Add keyword → category mappings here.
# GLOBAL_RULES apply to every account. ACCOUNT_RULES are per-bank and override global.

GLOBAL_RULES = {
    'openai': 'OTHERS',
    'chatgpt': 'OTHERS',
    'anthropic': 'OTHERS',
    'claude.ai': 'OTHERS',
}

ACCOUNT_RULES = {
    'BNI': {},
    'Mandiri': {},
    'Jenius': {},
    'BCA': {},
    'Maybank': {},
}

# ── PER-BANK EXTRACTION NOTES ────────────────────────────────────────────────
# Injected into the Claude prompt before the output schema.
# Describe bank-specific quirks: date formats, description patterns, sections to skip, etc.
# Keyed by bank name substring (case-insensitive match against account name).

BANK_NOTES = {
    'BCA': """\
BCA Rekening Tahapan — bank-specific extraction notes:
- QR transactions (TRSF E-BANKING DEBIT QR): merchant name is the text after "00000.00" in the raw description
- E-banking transfers (TRSF E-BANKING DB, TRSF E-BANKING CR, BI-FAST): combine the counterparty name and the free-text note into one readable description
- Poket Valas: ignore all rows in any section where MATA UANG ≠ IDR
- BIAYA ADM: extract as DB, category OTHERS, is_real_expense true""",

    'BNI': """\
BNI credit card — bank-specific extraction notes:
- statement_date: use the billing/due date printed on the statement header, converting to DD/MM/YYYY format (e.g. "20/05/2026")""",
    'Mandiri': "",
    'Jenius': "",

    'HSBC': """\
HSBC credit card — bank-specific extraction notes:
- The text is printed with most spaces removed; insert spaces so descriptions read normally (e.g. "SHOPEEjakartaID" → "SHOPEE Jakarta")
- Each row starts with two dates run together, both DDMON with no year: first "Tanggal Pembukuan" (posted), then "Tanggal Transaksi" (transaction). "21SEP20SEP" = posted 21 Sep, transacted 20 Sep. Always use the SECOND one (Tanggal Transaksi)
- date: convert to DD/MM/YYYY. The year is the statement_date's year, except when the month is later than the statement_date's month — then it is the previous year (a DEC row on a JAN statement)
- statement_date: the "Tanggal Cetak Tagihan" — the first date in the header, printed like "20OCT2026" — converted to DD/MM/YYYY (e.g. "20/10/2026"). Do NOT use "Tanggal Jatuh Tempo" (the second header date, the payment due date)
- Amounts use a comma as the THOUSANDS separator: "1,000,000" is one million rupiah, "992,500" is 992500. There are no decimals
- Amounts ending in "CR" are credits (payments, fee waivers, refunds): make the amount NEGATIVE and set is_real_expense false. Example: "3,126,382CR" → -3126382
- The 16-digit card number and the cardholder's name may be glued in front of a description (e.g. "<card number><CARDHOLDER NAME>AnnualFeeWaiveRetentionProg"); drop them and keep only the description ("Annual Fee Waive Retention Prog")
- Skip the "Total Credit used as of Last Statement" row and the "*****TRANSACTION SUMMARY*****" block — they are not transactions""",

    'UOB': """\
UOB credit card (TMRW) — bank-specific extraction notes:
- Each row has two dates, DD MON with no year and Indonesian month abbreviations (JAN, FEB, MAR, APR, MEI, JUN, JUL, AGS/AGU, SEP, OKT, NOP, DES): first "Tanggal Transaksi" (transaction), then "Tanggal Pembukuan" (posted). Always use the FIRST one (Tanggal Transaksi)
- date: convert to DD/MM/YYYY. The year is the statement_date's year, except when the month is later than the statement_date's month — then it is the previous year
- statement_date: the "Tanggal Pencetakan" value in the header (e.g. "18 OKT 2026"), converted to DD/MM/YYYY ("18/10/2026"). Do NOT use "Tanggal Jatuh Tempo" (payment due date)
- Amounts use a comma as the THOUSANDS separator: "299,376" is 299376. There are no decimals
- Payments and credits (rows marked CR, or "PEMBAYARAN" rows) get a NEGATIVE amount and is_real_expense false
- Skip "TAGIHAN BULAN LALU", "SUB TOTAL TAGIHAN BULAN INI" and "TOTAL TAGIHAN ... BULAN INI" rows — they are balances, not transactions
- Description: merchant name only; strip the trailing city (e.g. "GRANDLUCKY PIK JAKARTA UTARA" → "GRANDLUCKY PIK")""",

    'Maybank': """\
Maybank credit card — bank-specific extraction notes:
- Dates are printed as DD-MM-YY (e.g. "23-04-26"); keep this exact format in the date field — do NOT convert
- The transaction table has two date columns: "Tgl. Transaksi" (transaction date) and "Tgl. Tercatat" (posted date). Always use "Tgl. Transaksi" as the date field
- statement_date: use the "Tgl. Cetak" (tanggal cetak / statement print date) value from the statement header, converting from DD-MM-YY to DD/MM/YYYY (e.g. "20-06-26" → "20/06/2026"). Do NOT use "Tgl. Jatuh Tempo" (payment due date) — it falls in the following month and mislabels the statement
- Skip the "BALANCE OF LAST MONTH" row — it is not a transaction
- Rows with "CR" at the end of the amount are refunds or credits; set transaction_type = "CR", is_real_expense = false for all CR rows
- Payment rows (e.g. "PAYMENT FROM IBS") are transaction_type = "CR", is_real_expense = false
- Description: use the merchant name only; strip trailing city, location, and currency code (e.g. "JAKARTA BARAT ID", "Internet SG")""",
}


def _match_bank(account_name: str, table: dict):
    name_upper = account_name.upper()
    for key, val in table.items():
        if key.upper() in name_upper:
            return val
    return None


def get_rules_for_account(account_name: str) -> dict:
    return _match_bank(account_name, ACCOUNT_RULES) or {}


def build_bank_notes(account_name: str) -> str:
    notes = _match_bank(account_name, BANK_NOTES)
    return notes if notes else ''


def apply_rules(transactions: list, account_name: str) -> list:
    card_rules = get_rules_for_account(account_name)
    for t in transactions:
        desc_lower = (t.get('description') or '').lower()
        for kw, cat in GLOBAL_RULES.items():
            if kw in desc_lower:
                t['category'] = cat
                break
        for kw, cat in card_rules.items():
            if kw in desc_lower:
                t['category'] = cat
                break
    return transactions


def build_rules_prompt(account_name: str) -> str:
    card_rules = get_rules_for_account(account_name)
    combined = {**GLOBAL_RULES, **card_rules}
    if not combined:
        return ''
    lines = [
        f'- If description contains "{kw}" (case-insensitive), category must be "{cat}"'
        for kw, cat in combined.items()
    ]
    return 'Category overrides (apply these first, they take priority over your own judgment):\n' + '\n'.join(lines)
