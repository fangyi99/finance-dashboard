"""
Tests for the categorisation engine (app/classify). No database needed.

Run from your backend folder:   python tests/test_classify.py

Lines marked REAL came from your own statement. Lines marked ASSUMED are in the same shape but
invented, so treat those as the pipeline's expectations, not as facts about your bank.
"""

import csv
import os
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.classify import library as L  # noqa: E402
from app.classify.engine import Context, UserRule, decide  # noqa: E402
from app.classify.matching import best_match, build_index, find_phrase, tokenize  # noqa: E402
from app.classify.prepare import prepare  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   -> {detail}")


TREE = {
    "Groceries", "Dining", "Delivery", "Transport", "Healthcare & Wellness", "Housing & Utilities", "Telco",
    "Shopping", "Entertainment", "Income", "Own Accounts", "Friends & Family", "Savings & Investments", "Uncategorized",
}  # your tree today: note there is no Travel, Education, Fees or Cash


def run(description, amount, **ctx):
    ctx.setdefault("available_categories", TREE)
    return decide(prepare(description, amount), Context(**ctx))


# ---- the six lines from your statement ---------------------------------------------------------
REAL = {
    "card_supermarket": ("Debit Card Transaction PRIME SUPERMARKET SINGAPO 01SEP XXXX-XXXX-XXXX-XXXX 000003017336439", "-0.90"),
    "paylah_topup": ("Funds Transfer TOP-UP TO PAYLAH! : xxxxxx XXXXXXXX TF721191788421030460", "-1.50"),
    "card_airline": ("Debit Card Transaction ANAAIR 2052443178361 SG 07SEP 9999-9999-9999-9999 000003060423866", "-1393.10"),
    "fast_in_1000": ("FAST Payment / Receipt TRANSFER 20260912SSPISGSGBRT0036553 OTHER", "1000.00"),
    "paynow_in_memo": ("FAST Payment / Receipt INCOMING PAYNOW REF 9113502 FROM: XXXX XXXX XX SEND BACK XXXXX OTHER", "195.00"),
    "salary": ("Salary XXXXXXX GH SINGAPORE PTE LTD SEP2026PAYROLL 2609", "720.00"),
}

print("PREPARE: pulling facts out of your real lines")
f = prepare(*REAL["card_supermarket"])
check("the bank's type label is recognised", f.label == "debit card transaction" and f.channel == "card", (f.label, f.channel))
check("money out", f.direction == "out")
check("the merchant is clean: PRIME SUPERMARKET (country padding, card number, references gone)", f.merchant_text == "PRIME SUPERMARKET", f.merchant_text)
check("the date the CARD was used is kept apart: 01SEP", f.card_date == "01SEP", f.card_date)
check("the reference number is kept as a reference, not left in the merchant", f.references == ["000003017336439"] and "000003017336439" not in f.merchant_text, f.references)
check("the display name is tidy", f.clean_name == "Prime Supermarket", f.clean_name)
check("a learned rule would be keyed on the merchant", f.payee_key == "PRIME SUPERMARKET", f.payee_key)
f = prepare(*REAL["paylah_topup"])
check("TF is found as a REFERENCE PREFIX (glued to digits), and the reference is set aside", f.reference_prefixes == ["TF"] and f.references == ["TF721191788421030460"], (f.reference_prefixes, f.references))
check("'Funds Transfer' is the channel", f.channel == "transfer" and f.label == "funds transfer")
f = prepare(*REAL["card_airline"])
check("the 13-digit airline ticket number is set aside (and still available to rules)", "2052443178361" in f.long_numbers and f.merchant_text == "ANAAIR", (f.long_numbers, f.merchant_text))
f = prepare(*REAL["fast_in_1000"])
check("a FAST line with no payee yields no merchant words at all", f.merchant_text == "" and f.counterparty_text == "" and f.payee_key is None, (f.merchant_text, f.counterparty_text))
check("money in", f.direction == "in")
f = prepare(*REAL["paynow_in_memo"])
check("PayNow is detected; the sender is split from the line", f.paynow and f.channel == "fast" and f.counterparty_text.startswith("XXXX XXXX XX"), (f.paynow, f.counterparty_text))
check("the payee key stops where the memo begins ('SEND BACK')", f.payee_key == "XXXX XXXX XX", f.payee_key)
check("a fully masked name gives no display name", f.clean_name is None, f.clean_name)
f = prepare(*REAL["salary"])
check("'Salary' is the channel; 'PTE LTD' makes it business-like", f.channel == "salary" and f.business_like)
check("the country word inside a COMPANY name is NOT stripped (only card padding is)", "SINGAPORE" in f.merchant_text, f.merchant_text)

print("\nPREPARE: other shapes")
f = prepare("FR035 BUS/MRT 208057145 0352FR22317891", "-0.95")  # REAL, from an earlier statement
check("a bank code in place of a label (FR035) is recognised, and BUS/MRT is the merchant", f.channel == "code" and f.merchant_text == "BUS MRT", (f.channel, f.merchant_text))
f = prepare("Cash Withdrawal 07524465,KAKI BT STN", "-100.00")  # REAL, from an earlier statement
check("the mixed letter-and-digit reference is set aside too", "0352FR22317891" in prepare("FR035 BUS/MRT 208057145 0352FR22317891", "-0.95").references)
check("...but a merchant name glued to a number by punctuation is NOT destroyed (SHOPEE*123456789)", prepare("Debit Card Transaction SHOPEE*123456789 04SEP", "-23.90").merchant_text == "SHOPEE", prepare("Debit Card Transaction SHOPEE*123456789 04SEP", "-23.90").merchant_text)
check("Cash Withdrawal -> channel cash", f.channel == "cash" and f.label == "cash withdrawal")
f = prepare("TFR MYA 3311009 OCBC 360 (OWN ACCT)", "-1000.00")  # ASSUMED older prefix-first format
check("older format: 'TFR MYA' at the start -> own-transfer channel", f.channel == "own_transfer" and f.label is None, f.channel)
check("older format: 'PLPE' / 'LGP' / 'IPS' -> point of sale", all(prepare(f"{c} 123 SOME SHOP", "-5").channel == "pos" for c in ("PLPE", "LGP", "IPS")))
check("older format: 'TF' and 'TFR' are different codes, 'TFR MYA' is longest", prepare("TF 1 TO: A B", "-5").channel == "transfer" and prepare("TFR 1 TO: A B", "-5").channel == "transfer")
f = prepare("PAYNOW TRANSFER TO: LIM FOOD PTE LTD 53376430X", "-8.00")
check("a Singapore UEN is spotted (8 digits + letter)", f.uen == "53376430X", f.uen)
check("a company UEN is spotted (T08LL1234A)", prepare("PAYNOW 1 TO: ACME T08LL1234A", "-5").uen == "T08LL1234A")
check("references are NOT mistaken for UENs", prepare(*REAL["fast_in_1000"]).uen is None and prepare(*REAL["paylah_topup"]).uen is None)
check("an empty or missing description doesn't crash", prepare("", "-1").channel == "unknown" and prepare(None, "1").direction == "in")
check("the same words in any case and spacing give the same facts", prepare("debit  card   transaction  koufu   sg  03sep", "-4").merchant_text == "KOUFU")
check("money is read from a string or a Decimal alike", prepare("x", Decimal("-3.50")).amount == Decimal("-3.50") and prepare("x", "-3.50").direction == "out")

print("\nMATCHING: whole words, longest phrase first")
check("tokens ignore punctuation and case", tokenize("Toast Box @ NEX, MCDONALD'S") == ["TOAST", "BOX", "NEX", "MCDONALD", "S"])
check("a phrase must match WHOLE words: M1 is not M123", find_phrase(tokenize("M123 TRADING"), ["M1"]) is None and find_phrase(tokenize("M1 MOBILE"), ["M1"]) == 0)
check("AIA is not AIAS", find_phrase(tokenize("AIAS HAIR"), ["AIA"]) is None)
idx = build_index({"GRAB": "Transport", "GRABFOOD": "Delivery", "AMAZON": "Shopping", "AMAZON PRIME": "Entertainment"})
check("longest phrase wins: AMAZON PRIME beats AMAZON", best_match(tokenize("AMAZON PRIME SG"), idx)[1] == "Entertainment")
check("GRABFOOD is its own word and is never GRAB", best_match(tokenize("GRABFOOD ORDER"), idx)[1] == "Delivery" and best_match(tokenize("GRAB RIDE"), idx)[1] == "Transport")
rev = dict(reversed(list(idx.items())))
check("the answer does not depend on the ORDER the rules are listed in (today's matcher does)", best_match(tokenize("AMAZON PRIME SG"), build_index({"AMAZON PRIME": "Entertainment", "AMAZON": "Shopping"}))[1] == best_match(tokenize("AMAZON PRIME SG"), build_index({"AMAZON": "Shopping", "AMAZON PRIME": "Entertainment"}))[1])

print("\nLIBRARY: the rule data itself")
seen = defaultdict(set)
for category, phrases in L.all_merchants().items():
    for p in phrases:
        seen[tuple(tokenize(p))].add(category)
clashes = {" ".join(k): v for k, v in seen.items() if len(v) > 1}
check("no merchant phrase sits in two categories", not clashes, clashes)
check("every merchant category in MERCHANT_MAP exists in your tree", set(L.MERCHANT_MAP) <= TREE, set(L.MERCHANT_MAP) - TREE)
check("merchants for categories your tree lacks are kept apart (Travel only)", set(L.MERCHANTS_NEEDING_NEW_CATEGORY) == {"Travel"})
check("every keyword's category is in your tree, or is a known gap (Education)", {k.category for k in L.KEYWORDS} <= TREE | {"Education"}, {k.category for k in L.KEYWORDS} - TREE)
check("keyword directions and strengths are valid", all(k.direction in ("in", "out", "any") and 0 < k.strength < 1 for k in L.KEYWORDS))
check("no empty phrases anywhere", all(tokenize(p) for ps in L.all_merchants().values() for p in ps) and all(tokenize(k.phrase) for k in L.KEYWORDS))
check("your original 78 seed keywords are all still there", sum(len(v) for v in L.MERCHANT_MAP.values()) >= 78 and {"NTUC", "SP SERVICES", "KOPI TIAM", "AMAZON PRIME", "GRABFOOD", "M1"} <= {p for v in L.MERCHANT_MAP.values() for p in v})
check("bank labels are stored lower case; code prefixes upper case", all(k == k.lower() for k in L.BANK_LABELS) and all(t == t.upper() for p, _ in L.CODE_PREFIXES for t in p))

print("\nENGINE: your six real lines, in your tree as it is TODAY")
d = run(*REAL["card_supermarket"])
check("PRIME SUPERMARKET -> Groceries, assigned (a known merchant)", (d.status, d.category, d.source) == ("assigned", "Groceries", "hard_rule"), d)
d = run(*REAL["paylah_topup"])
check("a PayLah top-up -> Own Accounts, assigned: it's your own wallet", (d.status, d.category, d.type) == ("assigned", "Own Accounts", "own_transfer"), (d.status, d.category, d.type))
d = run(*REAL["card_airline"])
check("ANAAIR -> Travel, but only SUGGESTED: your tree has no Travel category", (d.status, d.category) == ("suggested", "Travel"), (d.status, d.category))
check("...and the reason is stated", any(e.signal == "missing_category" for e in d.evidence))
d = run(*REAL["fast_in_1000"])
check("an incoming FAST with no payee and no memo -> unknown (round amounts don't prove anything)", (d.status, d.category) == ("unknown", None), (d.status, d.category))
check("...but it's known to be an incoming transfer", d.type == "incoming_transfer")
d = run(*REAL["paynow_in_memo"])
check("incoming PayNow with 'SEND BACK' -> Friends & Family (a repayment, NOT income)", (d.status, d.category, d.type) == ("assigned", "Friends & Family", "reimbursement"), (d.status, d.category, d.type))
d = run(*REAL["salary"])
check("'Salary' -> Income, assigned, straight from the bank's own label", (d.status, d.category, d.source) == ("assigned", "Income", "hard_rule"), d)

print("\nENGINE: the same lines once the context is richer")
d = run(*REAL["paylah_topup"], user_rules=[UserRule("TOP UP TO PAYLAH", "Dining")])
check("YOUR rule files PayLah top-ups under Dining", (d.status, d.category, d.source) == ("assigned", "Dining", "user_rule"), d)
check("...yet it's still recorded as a transfer to your own wallet", d.type == "own_transfer", d.type)
d = run(*REAL["card_airline"], available_categories=TREE | {"Travel"})
check("once Travel exists, the airline is ASSIGNED", (d.status, d.category) == ("assigned", "Travel"), (d.status, d.category))
d = run(*REAL["fast_in_1000"], paired_own_account=True)
check("the $1,000 deposit, paired with an outflow in your other account -> Own Accounts, assigned", (d.status, d.category, d.source) == ("assigned", "Own Accounts", "pairing"), d)

print("\nENGINE: the known bugs in today's matcher")
check("AMAZON PRIME is Entertainment, not Shopping (was a certain mistake)", run("Debit Card Transaction AMAZON PRIME SG 05SEP", "-2.99").category == "Entertainment")
check("a plain AMAZON purchase is still Shopping", run("Debit Card Transaction AMAZON SG MKTPLACE 05SEP", "-30").category == "Shopping")
check("GRABFOOD is Delivery", run("Debit Card Transaction GRABFOOD *ORDER 04SEP", "-18.30").category == "Delivery")
check("GRAB is Transport", run("Debit Card Transaction GRAB* RIDE 04SEP", "-12.80").category == "Transport")
d = run("Debit Card Transaction M123 TRADING PTE LTD 06SEP", "-15")
check("M123 TRADING is NOT a telco (M1 matched it by prefix before)", d.category != "Telco" and d.status != "assigned", (d.category, d.status))
check("COLD STORAGE (two words) -> Groceries", run("Debit Card Transaction COLD STORAGE ORCHARD 20SEP", "-31.20").category == "Groceries")
check("SP SERVICES (two words) -> Housing & Utilities", run("Funds Transfer GIRO SP SERVICES UTILITIES 1234567890", "-96.40").category == "Housing & Utilities")
check("KOPITIAM written as one word -> Dining", run("Debit Card Transaction KOPITIAM TAMPINES HUB 02SEP", "-5.60").category == "Dining")
check("AIAS HAIR SALON is not an insurer (AIA matched it by prefix before)", run("Debit Card Transaction AIAS HAIR SALON 02SEP", "-40").category != "Savings & Investments")
check("MCDONALD'S -> Dining", run("Debit Card Transaction MCDONALD'S TAMPINES 12SEP", "-9.85").category == "Dining")

print("\nENGINE: direction matters")
check("SALARY on money OUT is not income (the seed lists SALARY as a merchant, which ignored direction)", run("Funds Transfer TO: AH BEE SALARY ADVANCE", "-200").category != "Income")
check("SALARY on money IN still is", run("FAST Payment / Receipt FROM: ACME PTE LTD SALARY", "3000").category == "Income")
check("RENT on money OUT -> Housing & Utilities", (lambda d: (d.status, d.category))(run("FAST Payment / Receipt TO: LIM KOK WEE RENT SEP", "-1800")) == ("assigned", "Housing & Utilities"))
check("RENT on money IN is not housing spending", run("FAST Payment / Receipt FROM: TAN AH BEE RENT SEP", "1800").category != "Housing & Utilities")
check("INTEREST on money in -> Income", run("Funds Transfer INTEREST CREDIT", "0.62").category == "Income")
check("INTEREST on money OUT (loan interest) is not income", run("Funds Transfer LOAN INTEREST", "-80").category != "Income")
check("a refund from a MERCHANT (money in) keeps that merchant's category", run("Debit Card Transaction SHOPEE REFUND 19SEP", "23.90").category == "Shopping")

print("\nENGINE: precedence")
d = run("Debit Card Transaction STARBUCKS ION 29SEP", "-7.90", user_rules=[UserRule("STARBUCKS", "Groceries")])
check("YOUR rule beats a known merchant", (d.category, d.source) == ("Groceries", "user_rule"), (d.category, d.source))
check("your rule matches whole words only: 'GRAB' does not catch 'GRABFOOD'", run("Debit Card Transaction GRABFOOD *ORDER 04SEP", "-18", user_rules=[UserRule("GRAB", "Transport")]).category == "Delivery")
d = run("Funds Transfer TO: DEMO USER", "-200", paired_own_account=True, user_rules=[UserRule("DEMO USER", "Friends & Family")])
check("your rule beats even own-account pairing (you're in charge)", d.category == "Friends & Family")
check("pairing beats a keyword", run("Funds Transfer TO: SELF RENT", "-500", paired_own_account=True).category == "Own Accounts")
d = run("TFR MYA 3311011 TO MOOMOO CASH (OWN ACCT)", "-300")
check("a known destination (MOOMOO) beats the generic self-transfer code", d.category == "Savings & Investments", d.category)
check("...but the self-transfer code alone is Own Accounts", run("TFR MYA 3311009 OCBC 360 (OWN ACCT)", "-1000").category == "Own Accounts")

print("\nENGINE: scoring, suggestions and the weak-signal cap")
d = run("FAST Payment / Receipt TO: LIM MEI LING DINNER SPLIT", "-35")
check("a meal word in a MEMO to a person is only medium evidence -> suggested Dining", (d.status, d.category) == ("suggested", "Dining") and abs(d.confidence - 0.60) < 1e-6, (d.status, d.category, d.confidence))
d = run("FAST Payment / Receipt TO: CHEN XIN YI BIRTHDAY GIFT", "-88")
check("GIFT to a person -> suggested Friends & Family", (d.status, d.category) == ("suggested", "Friends & Family"))
d = run("Debit Card Transaction DR LEE FAMILY CLINIC PTE LTD 11SEP", "-62")
check("a strong keyword (CLINIC) on a purchase -> assigned Healthcare", (d.status, d.category) == ("assigned", "Healthcare & Wellness"), (d.status, d.category))
d = run("Debit Card Transaction MEDICAL CAFE 11SEP", "-20")
check("two strong keywords for different categories: no clear lead -> only suggested", d.status == "suggested", (d.status, d.category, d.candidates))
d = run("Debit Card Transaction CLINIC CAFE 11SEP", "-20")
check("...but CLINIC is also a known merchant word, which outranks a keyword (a hard rule)", (d.status, d.category, d.source) == ("assigned", "Healthcare & Wellness", "hard_rule"), (d.status, d.category, d.source))
d = run("FAST Payment / Receipt TO: TAN AH KOW", "-4.50")
check("a small PayNow to a name, first time: not enough to even suggest", d.status == "unknown" and d.category is None, (d.status, d.category))
hist = {"TAN AH KOW": [Decimal("4.00"), Decimal("5.00")]}
d = run("FAST Payment / Receipt TO: TAN AH KOW", "-4.50", history=hist)
check("the third small payment to the same payee: suggested Dining", (d.status, d.category) == ("suggested", "Dining"), (d.status, d.category, d.confidence))
check("...but weak signals NEVER assign on their own, however many", d.status != "assigned" and d.confidence < 0.80)
d = run("FAST Payment / Receipt TO: TAN AH KOW", "-4.50", history={"TAN AH KOW": [Decimal("4"), Decimal("30"), Decimal("5")]})
check("repeat payments that aren't all small don't count as a hawker pattern", d.status == "unknown", (d.status, d.category))
d = run("FAST Payment / Receipt TO: LIM KOK WEE", "-200")
check("a round amount to a person is only a hint, and not enough to suggest", d.status == "unknown", (d.status, d.category))
d = run("Debit Card Transaction AH HUAT TRADING 10SEP", "-36")
check("an unexplained purchase gets a LOW-confidence default suggestion, never an assignment", (d.status, d.category, d.source) == ("suggested", "Shopping", "default") and d.confidence < 0.3, (d.status, d.category, d.source))
check("the default is only for purchases: an unexplained incoming transfer gets none", run("FAST Payment / Receipt FROM: SOMEONE", "50").status == "unknown")
d = run("Cash Withdrawal 07524465,KAKI BT STN", "-100")
check("a cash withdrawal has no category in your tree: unknown, but typed as cash", (d.status, d.type) == ("unknown", "cash"), (d.status, d.type))
d = run("Funds Transfer TO: SITI AMINAH TUITION FEE", "-240")
check("TUITION points at 'Education', which you don't have: suggested, with the gap stated", (d.status, d.category) == ("suggested", "Education") and any(e.signal == "missing_category" for e in d.evidence))

print("\nENGINE: honesty about its own decisions")
decisions = [run(d_, a_) for d_, a_ in REAL.values()]
check("every decision that picked a category says why", all(x.evidence for x in decisions if x.category))
check("an unknown decision claims no evidence and no confidence", all(not x.evidence and x.confidence == 0 for x in decisions if x.status == "unknown"))
check("confidence is always between 0 and 1", all(0 <= x.confidence <= 1 for x in decisions))
check("only 'assigned' decisions are ever meant to count toward budgets (statuses are one of three)", {x.status for x in decisions} <= {"assigned", "suggested", "unknown"})

print("\nSWEEP: 49 synthetic scenarios (my invention, in the older code-first format: a stress test, not a fact)")
key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples", "mock_expected_categories.csv")
if os.path.exists(key_path):
    rows = list(csv.DictReader(open(key_path, encoding="utf-8")))
    for r in rows:
        r["amt"] = Decimal(r["amount"])
    paired = lambda r: any(o["statement"] != r["statement"] and o["date"] == r["date"] and o["amt"] == -r["amt"] for o in rows)  # noqa: E731
    history, results = defaultdict(list), []
    for r in sorted(rows, key=lambda r: r["date"]):
        f = prepare(r["description"], r["amt"])
        d = decide(f, Context(user_rules=[UserRule("PAYLAH TOP UP", "Dining")], paired_own_account=paired(r), history=dict(history), available_categories=TREE))
        results.append((r, d))
        if r["amt"] < 0 and f.payee_key:
            history[f.payee_key].append(abs(r["amt"]))
    wrong = [(r["description"][:45], d.category, r["true_category"]) for r, d in results if d.status == "assigned" and (d.category or "Uncategorized") != r["true_category"]]
    check("NO assigned category contradicts the key (a wrong assignment pollutes budgets)", not wrong, wrong)
    agree = sum(d.status == r["expected_status"] for r, d in results)
    check(f"statuses agree with the key on at least 44 of {len(results)} (the rest are deliberate differences)", agree >= 44, agree)
    check("everything the key calls 'assigned' is assigned or only held back by a missing category", all(d.status == "assigned" or any(e.signal == "missing_category" for e in d.evidence) for r, d in results if r["expected_status"] == "assigned"), [(r["description"][:40], d.status) for r, d in results if r["expected_status"] == "assigned" and d.status != "assigned"])
else:
    print("  (samples/mock_expected_categories.csv not found: sweep skipped)")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)