GLOBAL_RULES = {
    'openai': 'OTHERS',
    'chatgpt': 'OTHERS',
    'anthropic': 'OTHERS',
    'claude.ai': 'OTHERS',
    'midjourney': 'OTHERS',
    'perplexity': 'OTHERS',
    'github copilot': 'OTHERS',
    'copilot': 'OTHERS',
}

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
    card_rules = get_rules_for_account(account_name)
    for t in transactions:
        desc_lower = (t.get('description') or '').lower()
        # Global rules first, then card-specific (card overrides global)
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
    combined = {**GLOBAL_RULES, **card_rules}  # card overrides global
    if not combined:
        return ''
    lines = [
        f'- If description contains "{kw}" (case-insensitive), category must be "{cat}"'
        for kw, cat in combined.items()
    ]
    return 'Card-specific category overrides (apply these first, they take priority):\n' + '\n'.join(lines)
