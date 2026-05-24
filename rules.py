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

    'BNI': "",
    'Mandiri': "",
    'Jenius': "",

    'Maybank': """\
Maybank credit card — bank-specific extraction notes:
- Dates are printed as DD-MM-YY (e.g. "23-04-26"); keep this exact format in the date field — do NOT convert
- The transaction table has two date columns: "Tgl. Transaksi" (transaction date) and "Tgl. Tercatat" (posted date). Always use "Tgl. Transaksi" as the date field
- statement_date: use the "Tgl. Jatuh Tempo" (due date) value from the statement header, converting from DD-MM-YY to DD/MM/YYYY (e.g. "04-06-26" → "04/06/2026")
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
