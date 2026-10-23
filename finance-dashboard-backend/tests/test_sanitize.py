"""
Tests for the sanitiser (app/sanitize.py): what it removes, what it must keep, and that it never changes what the
categoriser decides. No database needed.

Run from your backend folder:   python tests/test_sanitize.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["PAYEE_KEY"] = "test-key-one"

from app import sanitize as S  # noqa: E402
from app.classify.engine import Context, decide  # noqa: E402
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


TREE = {"Groceries", "Dining", "Delivery", "Transport", "Healthcare & Wellness", "Housing & Utilities", "Telco", "Shopping",
        "Entertainment", "Income", "Own Accounts", "Friends & Family", "Savings & Investments", "Uncategorized"}
L = S.clean_lines

print("YOUR REAL STATEMENT (as the parser reads it, line by line)")
check("a PayLah top-up loses its reference, and the dangling colon", L(["Funds Transfer", "TOP-UP TO PAYLAH! : TF721191788421030460"]) == "Funds Transfer TOP-UP TO PAYLAH!")
check("...whichever prefix the reference has (PLPE too)", L(["Funds Transfer", "TOP-UP TO PAYLAH! : PLPE4624805523045114"]) == "Funds Transfer TOP-UP TO PAYLAH!")
check("a FAST reference with a date and letters in it is gone", L(["FAST Payment / Receipt", "TRANSFER", "20260912SSPISGSGBRT0036553", "OTHER"]) == "FAST Payment / Receipt TRANSFER OTHER")
check("a card line loses the masked card number and the 15-digit reference but keeps the merchant and card date", L(["Debit Card Transaction", "PRIME SUPERMARKET SINGAPO 01SEP", "XXXX-XXXX-XXXX-XXXX", "000003017336439"]) == "Debit Card Transaction PRIME SUPERMARKET SINGAPO 01SEP")
check("an airline ticket number goes, the airline stays", L(["Debit Card Transaction", "ANAAIR 2052443178361 SG 07SEP", "9999-9999-9999-9999", "000003060423866"]) == "Debit Card Transaction ANAAIR SG 07SEP")
check("a foreign-currency purchase keeps its USD amount (harmless) and loses its long numbers", L(["Debit Card Transaction", "EXPEDIA 73543031466600 SE USA 12SEP USD860.57", "000003079819565"]) == "Debit Card Transaction EXPEDIA SE USA 12SEP USD860.57")
check("the university stays (an organisation, and what the categoriser reads); its two reference numbers go", L(["FAST Payment / Receipt", "PAYNOW TRANSFER 5065060", "TO: NANYANG TECHNOLOGICAL UNIVERSIT", "QRDNTU2692980", "OTHER"]) == "FAST Payment / Receipt PAYNOW TRANSFER TO: NANYANG TECHNOLOGICAL UNIVERSIT OTHER")
check("'TO: LAPTOP' stays: it's an everyday word, not a person", L(["FAST Payment / Receipt", "PAYNOW TRANSFER 6231700", "TO: LAPTOP", "OTHER"]) == "FAST Payment / Receipt PAYNOW TRANSFER TO: LAPTOP OTHER")
check("a masked name carries nothing and is dropped; the memo after it stays", L(["FAST Payment / Receipt", "INCOMING PAYNOW REF 9113502", "FROM: XXXX XXXX XX", "SEND BACK XXXXX", "OTHER"]) == "FAST Payment / Receipt INCOMING PAYNOW REF FROM: SEND BACK XXXXX OTHER")
check("a sender who is only a reference loses it", L(["FAST Payment / Receipt", "INCOMING PAYNOW REF 9865436", "FROM: 20260923TRBUSGSGBRT9865436", "OTHER"]) == "FAST Payment / Receipt INCOMING PAYNOW REF FROM: OTHER")
for same in ("Payments / Collections via GIRO GOV GOV OTHER", "Salary SUSHIRO GH SINGAPORE PTE LTD SEP2026PAYROLL 2609", "Interest Earned"):
    check(f"unchanged, as it should be: {same[:44]}", S.clean_text(same) == same, S.clean_text(same))

print("\nPERSONAL DATA THAT WOULD HAVE BEEN STORED (unredacted-style lines)")
secrets_in = ["TAN AH KOW", "LIM MEI LING", "91234567", "9123 4567", "123-45678-9", "012-345678-001", "S1234567D", "tan@mail.com", "TF721191788421030460"]
lines = [
    ["FAST Payment / Receipt", "PAYNOW TRANSFER 1234567", "TO: TAN AH KOW", "OTHER"],
    ["FAST Payment / Receipt", "INCOMING PAYNOW REF 9113502", "FROM: LIM MEI LING", "SEND BACK", "OTHER"],
    ["Funds Transfer", "TOP-UP TO PAYLAH! : 91234567", "TF721191788421030460"],
    ["Funds Transfer", "TOP-UP TO PAYLAH! : 9123 4567"],
    ["Funds Transfer", "TO: 123-45678-9 OCBC", "REF 012-345678-001"],
    ["Cheque", "NRIC S1234567D tan@mail.com"],
]
out = [L(x) for x in lines]
check("no name, phone number, account number, NRIC, email or reference survives anywhere", not any(s.lower() in o.lower() for s in secrets_in for o in out), [o for o in out if any(s.lower() in o.lower() for s in secrets_in)])
check("a name becomes one code word: PAYEE + initials + six letters", re.search(r"TO: PAYEETAK[A-Z]{6} OTHER$", out[0]) is not None, out[0])
check("the memo on its own line survives a redacted name ('SEND BACK')", "SEND BACK" in out[1] and re.search(r"FROM: PAYEELML[A-Z]{6} SEND BACK", out[1]), out[1])
check("a phone number in any format is gone, '+65' and spaces included", S.clean_text("TOP-UP TO PAYLAH! : +65 9123 4567") == "TOP-UP TO PAYLAH!" and S.clean_text("Transfer 6591234567") == "Transfer")
check("dashed account numbers go, and a masked card with dashes too", S.clean_text("TO 123-45678-9 OCBC") == "TO OCBC" and S.clean_text("CARD XXXX-XXXX-XXXX-1234 SHOP") == "CARD SHOP")

print("\nWHAT MUST SURVIVE")
check("a business registration number (UEN) is public and kept", "53376430X" in S.clean_text("PAYNOW TO: LIM FOOD PTE LTD 53376430X") and "T08LL1234A" in S.clean_text("ACME T08LL1234A"))
check("short numbers are kept: store numbers and a payroll month", S.clean_text("STORE 123 SEP2026PAYROLL 2609") == "STORE 123 SEP2026PAYROLL 2609")
check("a date written dd-mm-yyyy is not mistaken for an account number", S.clean_text("RENT 01-09-2026") == "RENT 01-09-2026")
check("hyphens inside words are untouched (7-ELEVEN, TOP-UP)", S.clean_text("7-ELEVEN TOP-UP") == "7-ELEVEN TOP-UP")
check("a merchant glued to its number keeps the merchant: SHOPEE*123456789", S.clean_text("SHOPEE*123456789 04SEP") == "SHOPEE 04SEP", S.clean_text("SHOPEE*123456789 04SEP"))
check("organisations are kept: PTE LTD, a known merchant, a school", all(S.clean_lines(["TO: " + n]) == "TO: " + n for n in ("ACME TECH PTE LTD", "NTUC FAIRPRICE", "GRAB", "RAFFLES GIRLS SCHOOL")))
check("everyday words are kept as labels, not treated as people", all(S.clean_lines(["TO: " + n]) == "TO: " + n for n in ("RENT", "DINNER SPLIT", "BIRTHDAY GIFT", "ALLOWANCE")))

print("\nTHE CODE")
a, b, c, d = (S.pseudonym(n) for n in ("TAN AH KOW", "tan  ah-kow", "Tan Ah Kow", "LIM MEI LING"))
check("the same person always gets the same code, whatever the capitalisation, spacing or punctuation", a == b == c, (a, b, c))
check("different people get different codes", a != d)
check("it is ONE word of letters only (so it can't look like a merchant, and recurring detection keeps it)", re.fullmatch(r"[A-Z]+", a) is not None and " " not in a, a)
os.environ["PAYEE_KEY"] = "a-different-key"; e = S.pseudonym("TAN AH KOW"); os.environ["PAYEE_KEY"] = "test-key-one"
check("the code depends on your secret key, so it can't be rebuilt from a list of names without it", e != a)
check("initials are recognisable but the name isn't recoverable", a.startswith("PAYEETAK") and "KOW" not in a and "AH" not in a[8:])
check("is_pseudonym recognises codes and nothing else", S.is_pseudonym(a) and not S.is_pseudonym("PAYEES") and not S.is_pseudonym("PAYEE") and not S.is_pseudonym("PAYLAH") and not S.is_pseudonym("TAK"))
check("a code reads as initials plus a short tag when shown to you", S.payee_label(a) == f"T.A.K. · {a[-6:-2]}" and S.payee_label("LIM KOK WEE") is None and S.payee_label(None) is None, S.payee_label(a))
S.KEEP_INITIALS = False; plain = S.pseudonym("TAN AH KOW"); S.KEEP_INITIALS = True
check("with initials switched off the code carries nothing but the tag", plain.startswith("PAYEE") and "TAK" not in plain[:8] and S.payee_label(plain).startswith("Payee · "), (plain, S.payee_label(plain)))
os.environ.pop("PAYEE_KEY")
try:
    S.clean_lines(["TO: TAN AH KOW"]); raised = None
except S.MissingKeyError as err:
    raised = str(err)
check("with no key, it refuses to make a code and says exactly how to fix it", raised and "PAYEE_KEY" in raised and "secrets.token_hex" in raised, raised)
check("...but cleaning that has no name in it never needs the key", S.clean_lines(["Funds Transfer", "TOP-UP TO PAYLAH! : 91234567"]) == "Funds Transfer TOP-UP TO PAYLAH!" and S.clean_text("Debit Card Transaction KOPITIAM 01SEP 000003017336439") == "Debit Card Transaction KOPITIAM 01SEP")
os.environ["PAYEE_KEY"] = "test-key-one"

print("\nTEXT THAT ARRIVES AS ONE STRING (CSV, typed, already joined)")
j = S.clean_text("FAST Payment / Receipt INCOMING PAYNOW REF 9113502 FROM: JOHN TAN SEND BACK OTHER")
check("the name ends at the memo word: the memo stays", re.fullmatch(r"FAST Payment / Receipt INCOMING PAYNOW REF FROM: PAYEEJT[A-Z]{6} SEND BACK OTHER", j) is not None, j)
check("with names switched off only the numbers go", S.clean_text("FROM: JOHN TAN SEND BACK 91234567", names=False) == "FROM: JOHN TAN SEND BACK")
long_name = S.clean_lines(["TO: ONE TWO THREE FOUR FIVE SIX", "OTHER"])
check("a statement line gives the name its own line, so even a SIX-word name is fully replaced", all(w not in long_name for w in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX")), long_name)
check("(known limit) joined text can only guess where a name ends: after four words", "FIVE" in S.clean_text("TO: ONE TWO THREE FOUR FIVE SIX"), S.clean_text("TO: ONE TWO THREE FOUR FIVE SIX"))

print("\nIT IS SAFE TO CLEAN TWICE")
samples = out + [S.clean_text(x) for x in ("TO: TAN AH KOW RENT", "Debit Card Transaction KOPITIAM 01SEP 000003017336439")] + [L(["TO: ONE TWO THREE FOUR FIVE SIX", "OTHER"])]
check("cleaning clean text changes nothing: codes are not re-coded, nothing else moves", all(S.clean_text(s) == s and L([s]) == s for s in samples), [s for s in samples if S.clean_text(s) != s])

print("\nCLEANING MUST NOT CHANGE WHAT THE CATEGORISER DECIDES")
real = [
    ["Debit Card Transaction", "PRIME SUPERMARKET SINGAPO 01SEP", "XXXX-XXXX-XXXX-XXXX", "000003017336439"], ["Funds Transfer", "TOP-UP TO PAYLAH! : TF721191788421030460"],
    ["Debit Card Transaction", "ANAAIR 2052443178361 SG 07SEP", "9999-9999-9999-9999", "000003060423866"], ["Debit Card Transaction", "EXPEDIA 73543031466600 SE USA 12SEP USD860.57", "000003079819565"],
    ["FAST Payment / Receipt", "PAYNOW TRANSFER 5065060", "TO: NANYANG TECHNOLOGICAL UNIVERSIT", "QRDNTU2692980", "OTHER"], ["FAST Payment / Receipt", "PAYNOW TRANSFER 6231700", "TO: LAPTOP", "OTHER"],
    ["FAST Payment / Receipt", "INCOMING PAYNOW REF 9113502", "FROM: XXXX XXXX XX", "SEND BACK XXXXX", "OTHER"], ["Salary", "SUSHIRO GH SINGAPORE PTE LTD", "SEP2026PAYROLL", "2609"], ["Interest Earned"],
    ["FAST Payment / Receipt", "PAYNOW TRANSFER 1234567", "TO: LIM KOK WEE", "RENT", "OTHER"], ["FAST Payment / Receipt", "TO: TAN AH KOW", "DINNER SPLIT", "OTHER"],
    ["FAST Payment / Receipt", "INCOMING PAYNOW REF 9113502", "FROM: LIM MEI LING", "SEND BACK", "OTHER"], ["Debit Card Transaction", "SCOOT 2312345678901 SG", "XXXX-XXXX-XXXX-4821", "000003060423866"],
]
same = True; diffs = []
for ls in real:
    amount = "-50" if not (ls[0] in ("Salary", "Interest Earned") or "FROM:" in " ".join(ls)) else "50"
    before = decide(prepare(" ".join(ls), amount), Context(available_categories=TREE)); after = decide(prepare(L(ls), amount), Context(available_categories=TREE))
    if (before.status, before.category, before.type) != (after.status, after.category, after.type):
        same = False; diffs.append((" ".join(ls)[:50], (before.status, before.category), (after.status, after.category)))
check(f"all {len(real)} lines (including ones whose names became codes) are decided exactly as before", same, diffs)
car = decide(prepare("FAST Payment / Receipt TO: " + S.pseudonym("LIM TAN AH"), "-20"), Context(available_categories=TREE))
check("initials that happen to spell a merchant (L.T.A. -> LTA) can't mis-file a person as Transport", car.category != "Transport" and "PAYEELTA" in S.pseudonym("LIM TAN AH"), (car.category, S.pseudonym("LIM TAN AH")))
k = prepare("FAST Payment / Receipt TO: " + S.pseudonym("TAN AH KOW") + " ALLOWANCE OTHER", "-300")
check("the engine reads the code as the payee (and not the memo word after it), so history, rules and groups work", k.payee_key == S.pseudonym("TAN AH KOW"), k.payee_key)
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)