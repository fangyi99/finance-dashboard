"""
Tests for the sandbox dataset (app/demo/data.py). No database needed.

Run from your backend folder:   python tests/test_demo_data.py
"""
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.demo.data import ACCOUNTS, BUDGETS, SALARY, generate, ground_truth  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   -> {detail}")


TREE = {"Groceries", "Dining", "Delivery", "Transport", "Healthcare & Wellness", "Housing & Utilities", "Telco", "Shopping",
        "Entertainment", "Income", "Own Accounts", "Friends & Family", "Savings & Investments", "Uncategorized"}
TODAY = date(2026, 10, 17)
d = generate(TODAY)

print("SHAPE")
check("a realistic amount of data: a few hundred rows over four months", 250 <= len(d.rows) <= 450, len(d.rows))
check("the window runs from the 1st of three months ago to yesterday", d.start == date(2026, 7, 1) and d.end == date(2026, 10, 16), (d.start, d.end))
check("no row is dated before the window, today, or in the future", all(d.start <= r.day <= d.end for r in d.rows))
check("three accounts, one for each import method", {a.source for a in d.accounts} == {"pdf_import", "csv_import", "stripe"} and len(d.accounts) == 3)
check("every row belongs to a real account", {r.account for r in d.rows} <= {a.key for a in ACCOUNTS})
check("the rows come out in date order", [r.day for r in d.rows] == sorted(r.day for r in d.rows))
check("no row appears twice (same account, day, text and amount)", len({(r.account, r.day, r.description, r.amount) for r in d.rows}) == len(d.rows))
check("amounts are exact cents and never zero", all(r.amount == r.amount.quantize(Decimal("0.01")) and r.amount != 0 for r in d.rows))
check("five budgets, one of them for all spending", len(BUDGETS) == 5 and sum(b.category is None for b in BUDGETS) == 1)

print("\nTHE LABELS (what each row SHOULD be, written independently of the engine)")
cats = Counter(r.true_category for r in d.rows)
check("every label is a category in the default tree, or Travel (which the tree doesn't have yet)", set(cats) <= TREE | {"Travel"}, set(cats) - TREE)
check("the main categories all appear, so every chart has something to show", {"Groceries", "Dining", "Transport", "Delivery", "Shopping", "Entertainment", "Housing & Utilities", "Telco", "Income", "Own Accounts", "Friends & Family", "Savings & Investments", "Healthcare & Wellness"} <= set(cats), set(cats))
check("it includes the awkward cases on purpose: cash, an airline, hawker PayNow, PayLah top-ups", cats["Uncategorized"] >= 3 and cats["Travel"] == 1 and any("TAN AH KOW" in r.description for r in d.rows) and any("PAYLAH" in r.description.upper() for r in d.rows))
positive = {"income", "interest", "reimbursement"}
negative = {"purchase", "person_payment", "bill", "cash"}
check("income-like rows are money in; spending-like rows are money out", all((r.amount > 0) == (r.true_type in positive) for r in d.rows if r.true_type in positive | negative), [r for r in d.rows if r.true_type in positive | negative and (r.amount > 0) != (r.true_type in positive)][:2])
check("a Stripe row is always a payment received, filed as Income", all(r.forced_category == "Income" and r.amount > 0 for r in d.rows if r.account == "stripe") and sum(r.account == "stripe" for r in d.rows) > 0)
check("only Stripe rows are filed directly; everything else goes through the categoriser", all((r.forced_category is not None) == (r.account == "stripe") for r in d.rows))

print("\nTHE POSB LINES LOOK LIKE YOUR REAL STATEMENT")
card = [r for r in d.rows if r.description.startswith("Debit Card Transaction")]
check("card lines follow the real shape: label, merchant, card date, masked card, 15-digit reference", all(re.fullmatch(r"Debit Card Transaction .+ \d{2}[A-Z]{3} XXXX-XXXX-XXXX-\d{4} \d{15}", r.description) for r in card), [r.description for r in card if not re.fullmatch(r"Debit Card Transaction .+ \d{2}[A-Z]{3} XXXX-XXXX-XXXX-\d{4} \d{15}", r.description)][:2])
check("the card date is the day BEFORE the bank posts it, as on your statement", all(r.day - timedelta(days=1) == date(r.day.year if not (r.day.month == 1 and r.day.day == 1) else r.day.year - 1, (r.day - timedelta(days=1)).month, int(r.description.split()[-3][:2])) for r in card[:40] if r.description.split()[-3][2:] in ("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")))
check("transfers carry a TF reference like your PayLah line", all(re.search(r"TF\d{18}$", r.description) for r in d.rows if "TOP-UP TO PAYLAH" in r.description))
check("there are all four of your real statement labels", all(any(r.description.startswith(p) for r in d.rows) for p in ("Debit Card Transaction", "Funds Transfer", "FAST Payment / Receipt", "Salary")))

print("\nTHE STORY HOLDS TOGETHER")
by_text = defaultdict(list)
for r in d.rows:
    for key in ("RENT", "NETFLIX", "SPOTIFY", "SP SERVICES", "SINGTEL", "AIA SINGAPORE", "MOOMOO", "Salary"):
        if key in r.description:
            by_text[key].append(r)
check("every monthly bill and subscription occurs at least three times (enough for recurring detection)", all(len(by_text[k]) >= 3 for k in by_text) and len(by_text) == 8, {k: len(v) for k, v in by_text.items()})
check("they recur about a month apart", all(26 <= (b.day - a.day).days <= 35 for k, rs in by_text.items() for a, b in zip(rs, rs[1:])))
posb_out = {r.day: r for r in d.rows if r.account == "posb" and r.description.startswith("Funds Transfer TO: DEMO USER")}
ocbc_in = {r.day for r in d.rows if r.account == "ocbc" and "FROM: DEMO USER" in r.description}
check("every transfer to your other account arrives there the next day (so the pairing has something to find)", all(day + timedelta(days=1) in ocbc_in for day in posb_out), (sorted(posb_out), sorted(ocbc_in)))
running = {a.key: a.opening_balance for a in d.accounts}
lowest = {k: v for k, v in running.items()}
for r in d.rows:
    running[r.account] += r.amount
    lowest[r.account] = min(lowest[r.account], running[r.account])
check("no account ever goes overdrawn", all(v >= 0 for v in lowest.values()), lowest)
spend = defaultdict(Decimal)
for r in d.rows:
    if r.day.month == 9 and r.amount < 0 and r.account == "posb" and r.true_category not in ("Own Accounts",):
        spend[r.true_category] += -r.amount
ratios = {b.name: spend[b.category] / b.amount for b in BUDGETS if b.category}
check("over a full month the budget screen shows every state: one exceeded, one comfortable", any(v > 1 for v in ratios.values()) and any(v < Decimal("0.7") for v in ratios.values()), {k: f"{v:.0%}" for k, v in ratios.items()})
check("...but not everything is blown: most budgets hold", sum(v <= 1 for v in ratios.values()) >= 2, {k: f"{v:.0%}" for k, v in ratios.items()})
income = sum(r.amount for r in d.rows if r.day.month == 9 and r.account == "posb" and r.true_category == "Income")
check("September's salary is there", income >= SALARY, income)

print("\nIT STAYS DETERMINISTIC, AND SURVIVES EVERY CALENDAR EDGE")
check("generating twice gives identical data", generate(TODAY).rows == generate(TODAY).rows)
check("the same month gives the same rows on different days (only newer days are added)", all(r in generate(date(2026, 10, 25)).rows for r in generate(date(2026, 10, 20)).rows))
check("ground_truth() matches the rows one-to-one", len(ground_truth(TODAY)) == len(d.rows) and set(ground_truth(TODAY)[0]) == {"account", "description", "amount", "true_category", "true_type"})
for label, today in [("a new year (January: three months back is last year)", date(2026, 1, 5)), ("the 1st of a month (the current month is empty)", date(2026, 3, 1)),
                     ("a leap day", date(2028, 2, 29)), ("the 31st", date(2026, 5, 31)), ("the last day of the year", date(2026, 12, 31)), ("the 30th, after a 31-day month", date(2026, 9, 30))]:
    try:
        g = generate(today)
        ok = len(g.rows) > 150 and all(g.start <= r.day <= g.end for r in g.rows) and g.end == today - timedelta(days=1)
        check(f"works on {label}: {today}", ok, (len(g.rows), g.start, g.end))
    except Exception as e:  # noqa: BLE001
        check(f"works on {label}: {today}", False, repr(e))
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)