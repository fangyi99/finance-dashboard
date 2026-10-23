"""
The sandbox dataset, as DATA. Pure functions, no database: generate(today) returns a DemoData.

What it is: about four months of a believable Singapore salaried life across three accounts: a POSB
account written in the bank's real statement format, an OCBC savings account, and a Stripe account.
It's built relative to `today`, so it always looks current, and it's deterministic: the same month
gives the same rows, so tests and the ground-truth file are stable.

Every row carries `true_category`: the category it SHOULD have, written by hand here and independent
of the categorisation engine. That is what makes it usable to measure the engine (and, later, a trained
model) honestly. It deliberately includes things the engine can't place on its own: unfamiliar
merchants, a monthly allowance to a parent, a cash withdrawal, an airline in a category you don't have.

Formats marked ASSUMED are in the shape of your real statement lines but not copied from them
(the outgoing PayNow wording, GIRO lines): treat those as plausible, not as facts about your bank.
"""

import random
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
SEED = 2026
MONTHS_BACK = 3  # this month plus the three before it
CARD_LAST4 = "4821"
SALARY = Decimal("4300.00")


def cents(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass(frozen=True)
class DemoAccount:
    key: str
    display_name: str
    institution_name: str
    source: str
    currency: str
    opening_balance: Decimal


@dataclass(frozen=True)
class DemoRow:
    account: str
    day: date
    description: str
    amount: Decimal  # signed: negative = money out
    true_category: str  # a leaf name; "Travel" is not in the default tree yet
    true_type: str
    forced_category: Optional[str] = None  # set directly instead of by the engine (Stripe)


@dataclass(frozen=True)
class DemoBudget:
    name: str
    amount: Decimal
    category: Optional[str]  # None = all spending


@dataclass
class DemoData:
    accounts: List[DemoAccount]
    rows: List[DemoRow]
    budgets: List[DemoBudget]
    start: date
    end: date


ACCOUNTS = [
    DemoAccount("posb", "POSB My Account", "POSB", "pdf_import", "SGD", cents(4000)),
    DemoAccount("ocbc", "OCBC 360", "OCBC", "csv_import", "SGD", cents(9800)),
    DemoAccount("stripe", "Stripe (test mode)", "Stripe", "stripe", "SGD", cents(0)),
]
BUDGETS = [
    # Sized against what the app DISPLAYS, so the budget screen shows a mix: Delivery over, Groceries and Dining
    # nearly there, Transport comfortable. (Dining is set low because the app only counts spending it is sure
    # about, and some dining is still only a suggestion: about 40% of a month's real dining isn't counted yet.) (Partway through a month the bars are naturally partway too.)
    DemoBudget("Groceries", cents(460), "Groceries"),
    DemoBudget("Dining", cents(150), "Dining"),
    DemoBudget("Delivery", cents(90), "Delivery"),
    DemoBudget("Transport", cents(110), "Transport"),
    DemoBudget("Monthly spending", cents(4200), None),
]

GROCERIES = ["NTUC FAIRPRICE TAMPINES", "COLD STORAGE ORCHARD", "SHENG SIONG TAMPINES", "PRIME SUPERMARKET SINGAPO"]
DINING_KNOWN = ["KOPITIAM TAMPINES HUB", "MCDONALD'S TAMPINES", "STARBUCKS ION ORCHARD", "TOAST BOX NEX",
                "YA KUN KAYA TOAST", "KOUFU TAMPINES", "SUBWAY TAMPINES MALL"]
DINING_UNKNOWN = ["DIN TAI FUNG PARAGON", "BREADTALK TAMPINES", "SWENSENS NEX", "LIHO TEA TAMPINES", "OLD CHANG KEE"]
DELIVERY = ["GRABFOOD *ORDER", "FOODPANDA SINGAPORE", "DELIVEROO SG"]
SHOPPING_KNOWN = ["SHOPEE SINGAPORE", "LAZADA SINGAPORE", "UNIQLO TAMPINES", "DAISO TAMPINES", "DECATHLON SINGAPORE"]
SHOPPING_UNKNOWN = ["POPULAR BOOKSTORE NEX", "MR DIY TAMPINES", "MINISO TAMPINES"]
HEALTH = ["DR TAN FAMILY CLINIC", "WATSONS PERSONAL CARE", "GUARDIAN HEALTH BEAUTY", "RAFFLES MEDICAL"]


def _months(today: date):
    out = []
    for back in range(MONTHS_BACK, -1, -1):
        yy, mm = today.year, today.month - back
        while mm <= 0:
            mm, yy = mm + 12, yy - 1
        out.append((yy, mm))
    return out


def _day(y: int, m: int, d: int) -> date:
    return date(y, m, min(d, monthrange(y, m)[1]))


def generate(today: date) -> DemoData:
    end = today - timedelta(days=1)
    months = _months(today)
    start = date(months[0][0], months[0][1], 1)
    rng = random.Random(SEED)
    rows: List[DemoRow] = []

    def add(account, d, description, amount, category, type_, forced=None):
        if start <= d <= end:
            rows.append(DemoRow(account, d, description, cents(amount), category, type_, forced))

    def digits(n):
        return f"{rng.randrange(10 ** n):0{n}d}"

    def tf():
        return "TF" + digits(18)

    def fast_ref(d):
        return f"{d:%Y%m%d}SSPISGSGBRT{digits(7)}"

    def card(merchant, d):
        used = d - timedelta(days=1)  # the card is used the day before the bank posts it
        return f"Debit Card Transaction {merchant} {used.day:02d}{MONTHS[used.month - 1]} XXXX-XXXX-XXXX-{CARD_LAST4} {digits(15)}"

    def spread(y, m, count):
        return sorted(_day(y, m, rng.randint(1, 28)) for _ in range(count))

    order = 0
    for idx, (y, m) in enumerate(months):
        mon = MONTHS[m - 1]

        # ---- fixed monthly items on the POSB account ----------------------------------------------------
        d = _day(y, m, 1)
        add("posb", d, f"FAST Payment / Receipt TO: LIM KOK WEE RENT {mon} {fast_ref(d)} OTHER", -900, "Housing & Utilities", "person_payment")
        d = _day(y, m, 2)
        add("posb", d, f"FAST Payment / Receipt TO: TAN SIEW HONG ALLOWANCE {fast_ref(d)} OTHER", -300, "Friends & Family", "person_payment")
        d = _day(y, m, 3)
        add("posb", d, card("SPOTIFY SINGAPORE", d), -9.90, "Entertainment", "purchase")
        d = _day(y, m, 5)
        add("posb", d, f"Funds Transfer TO MOOMOO CASH {tf()}", -300, "Savings & Investments", "person_payment")
        d = _day(y, m, 8)
        add("posb", d, f"Funds Transfer GIRO SP SERVICES UTILITIES {digits(10)}", -rng.uniform(85, 125), "Housing & Utilities", "bill")  # ASSUMED
        d = _day(y, m, 10)
        add("posb", d, f"Cash Withdrawal {digits(8)},TAMPINES MALL", -100, "Uncategorized", "cash")
        d = _day(y, m, 12)
        add("posb", d, f"Funds Transfer GIRO SINGTEL MOBILE {digits(10)}", -48.90, "Telco", "bill")  # ASSUMED
        d = _day(y, m, 15)
        add("posb", d, card("NETFLIX.COM SINGAPORE", d), -19.98, "Entertainment", "purchase")
        d = _day(y, m, 20)
        add("posb", d, f"Funds Transfer GIRO AIA SINGAPORE PTE LTD {digits(10)}", -148.50, "Savings & Investments", "bill")  # ASSUMED
        d = _day(y, m, 25)
        add("posb", d, f"FAST Payment / Receipt TO: LIM MEI LING DINNER SPLIT {fast_ref(d)} OTHER", -35, "Dining", "person_payment")
        d = _day(y, m, 26)
        add("posb", d, f"FAST Payment / Receipt INCOMING PAYNOW REF {digits(7)} FROM: LIM MEI LING SEND BACK {fast_ref(d)} OTHER", 35, "Friends & Family", "reimbursement")
        d = _day(y, m, 27)
        add("posb", d, f"Salary ACME TECH PTE LTD {mon}{y}PAYROLL {digits(4)}", SALARY, "Income", "income")
        d = _day(y, m, 28)
        add("posb", d, f"Funds Transfer TO: DEMO USER {tf()}", -500, "Own Accounts", "own_transfer")
        add("ocbc", _day(y, m, 29), f"FAST Payment / Receipt PAYNOW FROM: DEMO USER {fast_ref(_day(y, m, 29))} OTHER", 500, "Own Accounts", "own_transfer")

        # ---- OCBC savings ---------------------------------------------------------------------------------
        add("ocbc", _day(y, m, 6), f"FAST Payment / Receipt TO: SYFE PTE LTD {fast_ref(_day(y, m, 6))} OTHER", -200, "Savings & Investments", "person_payment")
        add("ocbc", _day(y, m, 28), "Interest Earned", rng.uniform(9, 14), "Income", "interest")

        # ---- one-offs, spread over the months ------------------------------------------------------------
        if idx == 1:
            d = _day(y, m, 15)
            add("posb", d, f"FAST Payment / Receipt FROM: ACME TECH PTE LTD BONUS {fast_ref(d)} OTHER", 1200, "Income", "income")
            d = _day(y, m, 22)
            add("posb", d, f"FAST Payment / Receipt TO: CHEN XIN YI BIRTHDAY GIFT {fast_ref(d)} OTHER", -88, "Friends & Family", "person_payment")
        if idx == 2:
            d = _day(y, m, 12)
            add("posb", d, card("SCOOT 2312345678901 SG", d), -428.60, "Travel", "purchase")

        # ---- everyday spending on the POSB card ----------------------------------------------------------
        for d in spread(y, m, rng.randint(6, 8)):
            add("posb", d, card(rng.choice(GROCERIES), d), -rng.uniform(9, 95), "Groceries", "purchase")
        for d in spread(y, m, rng.randint(7, 9)):
            add("posb", d, card(rng.choice(DINING_KNOWN), d), -rng.uniform(3.6, 16.5), "Dining", "purchase")
        for d in spread(y, m, rng.randint(2, 4)):
            add("posb", d, card(rng.choice(DINING_UNKNOWN), d), -rng.uniform(6, 48), "Dining", "purchase")
        for d in spread(y, m, rng.randint(3, 5)):
            add("posb", d, card(rng.choice(DELIVERY), d), -rng.uniform(11, 34), "Delivery", "purchase")
        for d in spread(y, m, rng.randint(14, 18)):
            add("posb", d, f"FR035 BUS/MRT {digits(9)} {digits(4)}FR{digits(8)}", -rng.uniform(0.9, 2.6), "Transport", "purchase")
        for d in spread(y, m, rng.randint(2, 4)):
            add("posb", d, card("GRAB* RIDE", d), -rng.uniform(7, 22), "Transport", "purchase")
        for d in spread(y, m, rng.randint(0, 1)):
            add("posb", d, card("COMFORTDELGRO TAXI", d), -rng.uniform(12, 28), "Transport", "purchase")
        for d in spread(y, m, rng.randint(1, 2)):
            add("posb", d, card(rng.choice(HEALTH), d), -rng.uniform(8, 70), "Healthcare & Wellness", "purchase")
        for d in spread(y, m, rng.randint(2, 3)):
            add("posb", d, card(rng.choice(SHOPPING_KNOWN), d), -rng.uniform(12, 120), "Shopping", "purchase")
        for d in spread(y, m, rng.randint(1, 2)):
            add("posb", d, card(rng.choice(SHOPPING_UNKNOWN), d), -rng.uniform(8, 60), "Shopping", "purchase")
        d = _day(y, m, rng.randint(14, 24))
        add("posb", d, card("GOLDEN VILLAGE TAMPINES", d), -rng.uniform(14, 28), "Entertainment", "purchase")
        # hawker stalls paid by PayNow: small, repeated, to a person's name (ASSUMED outgoing wording)
        for d in spread(y, m, rng.randint(6, 8)):
            add("posb", d, f"FAST Payment / Receipt TO: TAN AH KOW {fast_ref(d)} OTHER", -rng.choice([4.0, 4.5, 5.0, 5.5]), "Dining", "person_payment")
        for d in spread(y, m, rng.randint(4, 5)):
            add("posb", d, f"FAST Payment / Receipt TO: ALI BIN HASSAN {fast_ref(d)} OTHER", -rng.choice([3.5, 4.0, 4.5]), "Dining", "person_payment")
        # PayLah top-ups: your own wallet
        for d in spread(y, m, rng.randint(5, 7)):
            add("posb", d, f"Funds Transfer TOP-UP TO PAYLAH! : xxxxxx XXXXXXXX {tf()}", -rng.choice([5, 10, 10, 15, 20]), "Own Accounts", "own_transfer")

        # ---- Stripe (test mode): customers paying for orders ---------------------------------------------
        for d in spread(y, m, rng.randint(3, 5)):
            order += 1
            add("stripe", d, f"Stripe payment: Order #{1000 + order}", rng.uniform(35, 180), "Income", "income", forced="Income")

    # the same row twice in one day would look like a bug in the demo
    seen, unique = set(), []
    for r in rows:
        key = (r.account, r.day, r.description, r.amount)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: (r.day, r.account, r.description))
    return DemoData(ACCOUNTS, unique, BUDGETS, start, end)


def ground_truth(today: date):
    """What each row SHOULD be, for measuring a categoriser. (No dates or references: those don't matter to it.)"""
    return [
        {"account": r.account, "description": r.description, "amount": str(r.amount),
         "true_category": r.true_category, "true_type": r.true_type}
        for r in generate(today).rows
    ]