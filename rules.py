ACCOUNT_RULES = {
    'BNI': {
        'grab': 'TRANSPORTATION',
        'gojek': 'TRANSPORTATION',
        'tokopedia': 'SHOPPING',
        'shopee': 'SHOPPING',
        'netflix': 'ENTERTAINMENT',
        'spotify': 'ENTERTAINMENT',
        'indomaret': 'GROCERIES',
        'alfamart': 'GROCERIES',
    },
    'Mandiri': {
        'grab': 'F&B',
        'gojek': 'F&B',
        'tokopedia': 'SHOPPING',
        'shopee': 'SHOPPING',
        'netflix': 'ENTERTAINMENT',
    },
    'Jenius': {
        'grab': 'TRANSPORTATION',
        'gojek': 'TRANSPORTATION',
    },
}


def get_rules_for_account(account_name: str) -> dict:
    name_upper = account_name.upper()
    for bank_key, rules in ACCOUNT_RULES.items():
        if bank_key.upper() in name_upper:
            return rules
    return {}


def apply_rules(transactions: list, account_name: str) -> list:
    rules = get_rules_for_account(account_name)
    if not rules:
        return transactions
    for t in transactions:
        desc_lower = (t.get('description') or '').lower()
        for merchant_kw, category in rules.items():
            if merchant_kw in desc_lower:
                t['category'] = category
                break
    return transactions


def build_rules_prompt(account_name: str) -> str:
    rules = get_rules_for_account(account_name)
    if not rules:
        return ''
    lines = [
        f'- If description contains "{kw}" (case-insensitive), category must be "{cat}"'
        for kw, cat in rules.items()
    ]
    return 'Card-specific category overrides (apply these first, they take priority):\n' + '\n'.join(lines)
