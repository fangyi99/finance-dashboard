"""
The rule libraries, as DATA. Nothing in here makes a decision: engine.py does, by reading these.
Keeping the rules separate means adding a merchant, a keyword or a bank's label is a one-line
change with no logic to get wrong, and every rule can be tested on its own.

Matching is always by WHOLE WORD (or whole phrase), longest phrase first. "M1" matches the word
M1 and never "M123"; "AMAZON PRIME" beats "AMAZON"; "GRABFOOD" beats "GRAB".

Category names are the LEAF names of your category tree (Dining, not Food > Dining).
"""

from typing import NamedTuple

# ---------------------------------------------------------------------------------------------
# 1. Known merchants and billers.  category -> phrases.
#    The first block is the keyword list that was in seed.py, unchanged; seed.py now imports it
#    from here. Additions are at the end of each category's list and marked.
# ---------------------------------------------------------------------------------------------
MERCHANT_MAP = {'Groceries': ['NTUC',
               'FAIRPRICE',
               'COLD STORAGE',
               'SHENG SIONG',
               'GIANT SUPERMARKET',
               'DON DON DONKI',
               'REDMART'],
 'Dining': ['KOPI TIAM', 'FOOD JUNCTION', 'MCDONALD', 'TOAST BOX', 'YAKUN', 'STARBUCKS'],
 'Delivery': ['GRABFOOD', 'DELIVEROO', 'FOODPANDA'],
 'Transport': ['SIMPLYGO', 'TRANSITLINK', 'GRAB', 'COMFORTDELGRO', 'TADA'],
 'Healthcare & Wellness': ['HOSPITAL',
                           'CLINIC',
                           'POLYCLINIC',
                           'WATSONS',
                           'GUARDIAN',
                           'RAFFLES MEDICAL',
                           'MINMED',
                           'DENTAL',
                           'FACIAL',
                           'MASSAGE',
                           'HAIRCUT',
                           'SALON'],
 'Housing & Utilities': ['SP SERVICES',
                         'SP GROUP',
                         'TEMBUSU',
                         'KEPPEL ELECTRIC',
                         'GENECO',
                         'HDB',
                         'MORTGAGE',
                         'CONDO',
                         'MAINTENANCE',
                         'IKEA'],
 'Telco': ['SINGTEL', 'STARHUB', 'M1', 'SIMBA', 'MYREPUBLIC', 'GIGA', 'GOMO', 'CIRCLES.LIFE'],
 'Shopping': ['LAZADA', 'SHOPEE', 'AMAZON', 'UNIQLO', 'TAOBAO', 'SHEIN', 'COURTS'],
 'Savings & Investments': ['AIA',
                           'PRUDENTIAL',
                           'GREAT EASTERN',
                           'MANULIFE',
                           'INCOME INSURANCE',
                           'SINGLIFE',
                           'MOOMOO',
                           'TIGER BROKERS',
                           'SYFE',
                           'STASHAWAY',
                           'ENDOWUS',
                           'INTERACTIVE BROKERS',
                           'POEMS'],
 'Entertainment': ['NETFLIX',
                   'SPOTIFY',
                   'DISNEY PLUS',
                   'DISNEY+',
                   'YOUTUBE PREMIUM',
                   'AMAZON PRIME'],
 'Income': ['SALARY']}

# Additions to existing categories (brands that are unambiguous on their own).
_ADDITIONS = {
    "Groceries": ["PRIME SUPERMARKET", "MUSTAFA"],
    "Dining": ["KOUFU", "FOOD REPUBLIC", "FOODFARE", "KOPITIAM", "YA KUN", "SUBWAY", "KFC", "BURGER KING", "PIZZA HUT", "DOMINO", "DOMINOS"],
    "Transport": ["SHELL", "ESSO", "CALTEX", "SPC", "PARKING SG", "BLUESG", "GOJEK", "LTA", "ERP"],
    "Housing & Utilities": ["TOWN COUNCIL", "MCST"],
    "Shopping": ["ZALORA", "DECATHLON", "DAISO"],
    "Entertainment": ["GOLDEN VILLAGE", "SHAW THEATRES"],
}
for _category, _phrases in _ADDITIONS.items():
    MERCHANT_MAP[_category] = MERCHANT_MAP[_category] + [p for p in _phrases if p not in MERCHANT_MAP[_category]]

# Merchants that belong to a category your tree doesn't have yet. The engine knows about them, but
# the seed does not load them (there is nowhere to put them), and a decision in one of these
# categories is only ever a SUGGESTION until the category exists.
MERCHANTS_NEEDING_NEW_CATEGORY = {
    "Travel": [
        "SINGAPORE AIRLINES", "SCOOT", "JETSTAR", "AIRASIA", "CATHAY PACIFIC", "EMIRATES", "QATAR AIRWAYS",
        "ANAAIR", "ANA AIR", "AGODA", "BOOKING COM", "TRIP COM", "KLOOK", "EXPEDIA", "AIRBNB", "CHANGI AIRPORT",
    ],
}


def all_merchants() -> dict:
    merged = {category: list(phrases) for category, phrases in MERCHANT_MAP.items()}
    for category, phrases in MERCHANTS_NEEDING_NEW_CATEGORY.items():
        merged.setdefault(category, []).extend(phrases)
    return merged


# ---------------------------------------------------------------------------------------------
# 2. Direction-aware keywords. A keyword counts only when the money moves the way it implies:
#    SALARY only on money IN, RENT only on money OUT.
#    strength: 0.80 = strong (can decide on its own), 0.60 = medium (suggests; needs a second clue)
# ---------------------------------------------------------------------------------------------
class Keyword(NamedTuple):
    phrase: str
    category: str
    direction: str  # "in", "out" or "any"
    strength: float


_S, _M = 0.80, 0.60
KEYWORDS = [
    # food and drink
    Keyword("SUPERMARKET", "Groceries", "out", _S), Keyword("MINIMART", "Groceries", "out", _S), Keyword("MINI MART", "Groceries", "out", _S),
    Keyword("KOPI", "Dining", "out", _S), Keyword("KOPITIAM", "Dining", "out", _S), Keyword("COFFEE", "Dining", "out", _S),
    Keyword("CAFE", "Dining", "out", _S), Keyword("RESTAURANT", "Dining", "out", _S), Keyword("BAKERY", "Dining", "out", _S),
    Keyword("NOODLE", "Dining", "out", _S), Keyword("NOODLES", "Dining", "out", _S), Keyword("SUSHI", "Dining", "out", _S),
    Keyword("RAMEN", "Dining", "out", _S), Keyword("BBQ", "Dining", "out", _S), Keyword("DIM SUM", "Dining", "out", _S),
    Keyword("HAWKER", "Dining", "out", _S), Keyword("FOOD COURT", "Dining", "out", _S), Keyword("CANTEEN", "Dining", "out", _S),
    Keyword("BUBBLE TEA", "Dining", "out", _S), Keyword("PIZZA", "Dining", "out", _S),
    # a meal word in a MEMO is only medium evidence: the payee may be a friend
    Keyword("DINNER", "Dining", "out", _M), Keyword("LUNCH", "Dining", "out", _M), Keyword("BREAKFAST", "Dining", "out", _M),
    # health
    Keyword("CLINIC", "Healthcare & Wellness", "out", _S), Keyword("DENTAL", "Healthcare & Wellness", "out", _S),
    Keyword("PHARMACY", "Healthcare & Wellness", "out", _S), Keyword("MEDICAL", "Healthcare & Wellness", "out", _S),
    # housing, transport
    Keyword("RENT", "Housing & Utilities", "out", _S),
    Keyword("BUS MRT", "Transport", "out", _S), Keyword("PARKING", "Transport", "out", _S), Keyword("TAXI", "Transport", "out", _S),
    # money in
    Keyword("SALARY", "Income", "in", _S), Keyword("PAYROLL", "Income", "in", _S), Keyword("BONUS", "Income", "in", _S),
    Keyword("PENSION", "Income", "in", _S), Keyword("INTEREST", "Income", "in", _S), Keyword("DIVIDEND", "Income", "in", _S),
    # people
    Keyword("GIFT", "Friends & Family", "out", _M),
    # categories your tree doesn't have yet (suggestions only until it does)
    Keyword("TUITION", "Education", "out", _S),
]

# Words that say "I'm sending your money back": on an INCOMING payment from a person this is a
# repayment between people, not income.
REIMBURSEMENT_PHRASES = ["SEND BACK", "SENT BACK", "PAY BACK", "PAYBACK", "REPAY", "REPAYMENT", "REIMBURSE", "REFUND", "RETURN"]

# ---------------------------------------------------------------------------------------------
# 3. The bank's own transaction-type labels: the first line of a transaction.
#    seen=True means the label appeared on a real statement; False means assumed (check it).
# ---------------------------------------------------------------------------------------------
BANK_LABELS = {
    "debit card transaction": {"channel": "card", "seen": True},
    "funds transfer": {"channel": "transfer", "seen": True},
    "fast payment / receipt": {"channel": "fast", "seen": True},
    "salary": {"channel": "salary", "seen": True},
    "cash withdrawal": {"channel": "cash", "seen": True},
    "interest earned": {"channel": "interest", "seen": False},
}

# A short code in place of a label, such as "FR035" in "FR035 BUS/MRT ..." (seen on a real statement).
BANK_CODE_PATTERN = r"[A-Z]{2}\d{3}"

# Older format (some banks print a code and a reference number instead of a label), tried only when
# no label matched. (tokens at the start of the text) -> channel
CODE_PREFIXES = [
    (("TFR", "MYA"), "own_transfer"),
    (("TFR",), "transfer"), (("TF",), "transfer"),
    (("PLPE",), "pos"), (("LGP",), "pos"), (("IPS",), "pos"), (("NETS",), "pos"),
    (("GIRO",), "giro"), (("FAST",), "fast"), (("ATM",), "cash"), (("INT",), "interest"), (("FEE",), "fee"),
]

# ---------------------------------------------------------------------------------------------
# 4. Small lists the extraction and the engine use
# ---------------------------------------------------------------------------------------------
# Words in a payee/merchant that make it look like a registered business.
BUSINESS_WORDS = {
    "PTE", "LTD", "LLP", "ENTERPRISE", "ENTERPRISES", "TRADING", "SERVICES", "SDN", "BHD", "CO", "COMPANY",
    "CAFE", "RESTAURANT", "STORE", "MART", "SHOP", "BAKERY", "CLINIC", "STALL",
}

# Words that carry no meaning about WHAT was bought.
NOISE_WORDS = {"OTHER", "TRANSFER", "INCOMING", "PAYNOW", "REF", "PAYMENT", "FAST", "RECEIPT"}
TRAILING_COUNTRY = {"SG", "SGP", "SINGAPO", "SINGAPOR", "SINGAPORE"}  # the padding at the end of a card merchant

# Wallets the user tops up: money that stays theirs.
OWN_WALLET_PHRASES = ["TOP UP TO PAYLAH", "TOPUP TO PAYLAH", "PAYLAH TOP UP"]

# Where the money lands if no rule has anything to say about a PURCHASE: a suggestion, never a fact.
DEFAULT_PURCHASE_SUGGESTION = "Shopping"