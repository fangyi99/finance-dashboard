"""
Keeps personal data out of the database.

A bank statement's text carries things the app has no use for and shouldn't hold: a payee's NAME, phone numbers,
account and card numbers (dashes and all), long transaction references, an NRIC, an email. This module removes
them BEFORE anything is stored, and everything downstream (the categoriser, rules, recurring detection, the review
queue) only ever sees the cleaned text.

What is removed
  * phone numbers ("91234567", "+65 9123 4567")
  * dashed account and card numbers ("123-45678-9", "XXXX-XXXX-XXXX-1234")
  * long references: any standalone number of 6+ digits, and long letter+digit codes such as
    TF721191788421030460, PLPE4624805523045114, 20260912SSPISGSGBRT0036553, QRDNTU2692980
  * NRIC/FIN numbers and email addresses
What is kept
  * merchant and organisation names, the bank's labels, memo words ("RENT", "SEND BACK", "LAPTOP"),
    short numbers (a store number, "SEP2026PAYROLL"), dates, and business registration numbers (UENs)

Names. A name after "FROM:" or "TO:" is replaced by a CODE, not deleted. The same person always gets the same code,
so "payments to the same payee", rules you teach the app and the review queue's groups keep working, but the name
can't be read back out. The code is PAYEE + the name's initials + six letters from a keyed hash:

    TO: TAN AH KOW   ->   TO: PAYEETAKBKQXLM

  * One word, letters only, so it can't be mistaken for a merchant, and recurring detection (which drops any word
    containing a digit) still sees it.
  * The hash is keyed with PAYEE_KEY, a secret you keep in your .env and NOT in the database. Without a key, anyone
    holding the database could rebuild the codes by hashing a list of names. Lose the key and the codes change, so
    keep it safe. (Generate one with:  python -c "import secrets; print(secrets.token_hex(16))")
  * Organisations are not personal data and are what the categoriser reads, so they're kept: a name that contains a
    business word (PTE LTD, UNIVERSITY), a known merchant, or only everyday words (LAPTOP, RENT) is left alone.
  * Initials are a convenience so you can recognise "T.A.K." in the app; set KEEP_INITIALS = False to drop them.

Cleaning is idempotent: cleaning already-clean text changes nothing, so it's safe to apply at every entry point.
"""

import hashlib
import hmac
import os
import re
from typing import Iterable, List, Optional

from .classify import library as L
from .classify.matching import build_index, best_match, tokenize

REDACT_NAMES = True  # False keeps names as printed (the sandbox does this: its names are fictional)
KEEP_INITIALS = True
INITIALS_MAX = 6
CODE_LENGTH = 6


class MissingKeyError(RuntimeError):
    pass


# ---- patterns -------------------------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
NRIC_RE = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE)
UEN_RE = re.compile(r"(?:\d{8}[A-Z]|\d{9}[A-Z]|[TS]\d{2}[A-Z]{2}\d{4}[A-Z])", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<![\w-])(?:\+?65[ -]?)?[689]\d{3}[ -]?\d{4}(?![\w-])")
DASHED_RE = re.compile(r"(?<![\w-])(?:[Xx\d]{1,6}-){2,}[Xx\d]{1,6}(?![\w-])")
DATE_LIKE_RE = re.compile(r"\d{1,2}-\d{1,2}-\d{2,4}")
SPACED_CARD_RE = re.compile(r"(?<![\w-])[Xx\d]{4}(?: [Xx\d]{4}){3}(?![\w-])")
RUN_RE = re.compile(r"[A-Za-z0-9]{6,}")
CUE_RE = re.compile(r"\b(?:FROM|TO)\s*:", re.IGNORECASE)
PSEUDONYM_RE = re.compile(r"^PAYEE[A-Z]{%d,%d}$" % (CODE_LENGTH, CODE_LENGTH + INITIALS_MAX))

# Words that mean "this is a business or institution, not a person".
ORG_WORDS = {
    "UNIVERSITY", "UNIVERSIT", "UNIVERSITI", "COLLEGE", "SCHOOL", "POLYTECHNIC", "INSTITUTE", "INSTITUTION", "ACADEMY",
    "KINDERGARTEN", "TUITION", "HOSPITAL", "CLINIC", "DENTAL", "PHARMACY", "MEDICAL", "BANK", "INSURANCE", "ASSURANCE",
    "GOV", "GOVERNMENT", "MINISTRY", "BOARD", "COUNCIL", "AUTHORITY", "ASSOCIATION", "SOCIETY", "CLUB", "CHURCH",
    "TEMPLE", "MOSQUE", "FOUNDATION", "CENTRE", "CENTER", "CAFE", "RESTAURANT", "BAKERY", "KOPITIAM", "SUPERMARKET",
    "TRADING", "ENTERPRISE", "ENTERPRISES", "SERVICES", "SERVICE", "PTE", "LTD", "LLP", "SDN", "BHD", "INC", "CORP",
    "COMPANY", "STUDIO", "SALON", "FITNESS", "GYM", "AGENCY", "TRAVEL", "AIRLINES", "AIRWAYS", "HOTEL", "RESORT",
    "STORE", "SHOP", "MART",
    # banks and payment services: they appear after FROM:/TO: and are never a person
    "DBS", "POSB", "OCBC", "UOB", "CITI", "CITIBANK", "HSBC", "MAYBANK", "CIMB", "ANZ", "TRUST", "GXS", "PAYNOW", "PAYLAH",
    "GRABPAY", "WISE", "REVOLUT", "PAYPAL", "STRIPE",
}
# Everyday words people type as a label instead of a name ("TO: LAPTOP"): not a person, and useful to keep.
MEMO_WORDS = {
    "LAPTOP", "PHONE", "IPHONE", "MACBOOK", "IPAD", "TABLET", "MONITOR", "CAMERA", "FURNITURE", "FOOD", "GROCERIES",
    "FEES", "FEE", "BILL", "BILLS", "UTILITIES", "ALLOWANCE", "DEPOSIT", "LOAN", "REFUND", "TICKET", "TICKETS",
    "FLIGHT", "HOTEL", "BOOKING", "BOOK", "BOOKS", "TRANSPORT", "SAVINGS", "INVESTMENT", "PAYMENT", "TRANSFER", "OTHER",
    "BIRTHDAY", "WEDDING", "RENT", "DINNER", "LUNCH", "BREAKFAST", "GIFT", "SALARY", "BONUS", "SPLIT", "SHARE",
}
_STOP = set()
for _phrase in list(L.REIMBURSEMENT_PHRASES) + [k.phrase for k in L.KEYWORDS]:
    _STOP.add(tokenize(_phrase)[0])
_STOP |= {"OTHER"}
_ORG_INDEX = build_index({p: c for c, ps in L.all_merchants().items() for p in ps})


# ---- numbers ------------------------------------------------------------------------------------------------
def _run(match: "re.Match") -> str:
    word = match.group()
    digits = sum(ch.isdigit() for ch in word)
    if UEN_RE.fullmatch(word):
        return word  # a business registration number is public, and useful
    if word.isdigit():
        return " "  # a long number: a reference, a ticket, a terminal or account number
    if len(word) >= 9 and digits >= 6:
        return " "  # a long code such as TF721191788421030460 or QRDNTU2692980
    return word


def scrub_numbers(text: str) -> str:
    text = EMAIL_RE.sub(" ", text)
    text = NRIC_RE.sub(" ", text)
    text = PHONE_RE.sub(" ", text)
    text = DASHED_RE.sub(lambda m: m.group() if DATE_LIKE_RE.fullmatch(m.group()) else " ", text)
    text = SPACED_CARD_RE.sub(" ", text)
    return RUN_RE.sub(_run, text)


# ---- names --------------------------------------------------------------------------------------------------
def _key() -> bytes:
    key = os.environ.get("PAYEE_KEY", "")
    if not key:
        raise MissingKeyError(
            "PAYEE_KEY isn't set. Add a line like PAYEE_KEY=<random text> to your .env and restart the backend. "
            'Make one with:  python -c "import secrets; print(secrets.token_hex(16))"'
        )
    return key.encode()


def ensure_ready() -> None:
    """Call before a bulk import: fails at once, with the fix, if names are being coded and there's no key."""
    if REDACT_NAMES:
        _key()


def is_pseudonym(token: str) -> bool:
    return bool(PSEUDONYM_RE.match(token.upper()))


def pseudonym(name: str) -> str:
    """The code for a name: the same name always gives the same code, and the name can't be read back out of it."""
    words = tokenize(name)
    digest = hmac.new(_key(), " ".join(words).encode(), hashlib.sha256).digest()
    code = "".join(chr(ord("A") + b % 26) for b in digest[:CODE_LENGTH])
    initials = "".join(w[0] for w in words if w[0].isalpha())[:INITIALS_MAX] if KEEP_INITIALS else ""
    return f"PAYEE{initials}{code}"


def payee_label(payee_key: Optional[str]) -> Optional[str]:
    """How to show a payee key to a person: a code reads as 'T.A.K. · BKQX', anything else is tidied."""
    if not payee_key:
        return None
    token = payee_key.strip().upper()
    if is_pseudonym(token):
        body = token[len("PAYEE"):]
        initials, code = body[:-CODE_LENGTH], body[-CODE_LENGTH:]
        return (".".join(initials) + ". · " if initials else "Payee · ") + code[:4]
    return None


def _is_personal(words: List[str]) -> bool:
    """Is this probably a PERSON's name (as opposed to a business, an institution, or a label like LAPTOP)?"""
    tokens = tokenize(" ".join(words))
    if not tokens or all(set(t) <= {"X"} for t in tokens):
        return False  # empty, or already masked
    if len(tokens) == 1 and is_pseudonym(tokens[0]):
        return False  # already a code
    if any(t in ORG_WORDS for t in tokens) or best_match(tokens, _ORG_INDEX):
        return False
    if all(t in MEMO_WORDS or t in _STOP for t in tokens):
        return False
    return True


def _replace_name(rest: str, cap: Optional[int]) -> str:
    """
    `rest` is what follows FROM: or TO:. The name is its first words, up to a memo word, 'OTHER', or `cap` words
    (None = no limit, used when the statement gave the name its own line). Only the name is replaced.
    """
    words = rest.split()
    if words and is_pseudonym(words[0]):
        return rest  # already coded (a second cleaning pass): the words after it are not part of the name
    end = 0
    while end < len(words) and (cap is None or end < cap):
        if words[end].upper().strip(".,;:") in _STOP:
            break
        end += 1
    name, remainder = words[:end], words[end:]
    if not name:
        return rest
    tokens = tokenize(" ".join(name))
    if all(set(t) <= {"X"} for t in tokens):  # a masked name carries nothing: drop it
        return " ".join(remainder)
    if not _is_personal(name):
        return rest
    return " ".join([pseudonym(" ".join(name))] + remainder)


def _redact_names_in_text(text: str) -> str:
    match = CUE_RE.search(text)
    if not match:
        return text
    head, rest = text[: match.end()], text[match.end():]
    return f"{head} {_replace_name(rest.strip(), cap=4)}".strip()


# ---- putting it together ---------------------------------------------------------------------------------------
def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*[:*]\s*$", "", text)  # "TOP-UP TO PAYLAH! :" once its number is gone
    text = re.sub(r"(?<=\w)\*(?=\s)", "", text)  # "SHOPEE* " once its number is gone
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str, names: Optional[bool] = None) -> str:
    """Cleans one string (a CSV description, a typed one, or text already joined). Names end at a memo word or 4 words."""
    names = REDACT_NAMES if names is None else names
    text = scrub_numbers(text or "")
    if names:
        text = _redact_names_in_text(re.sub(r"\s+", " ", text))
    return _tidy(text)


def clean_lines(lines: Iterable[str], names: Optional[bool] = None) -> str:
    """
    Cleans a statement transaction's lines. Because each line is separate, the name is exactly what follows
    FROM:/TO: on its own line, and the memo lines after it are left alone.
    """
    names = REDACT_NAMES if names is None else names
    out = []
    for line in lines:
        line = scrub_numbers(line)
        match = re.match(r"^(?P<head>.*?\b(?:FROM|TO)\s*:)\s*(?P<rest>.*)$", line.strip(), re.IGNORECASE)
        if match and names:
            line = f"{match['head']} {_replace_name(match['rest'], cap=None)}"
        if line.strip():
            out.append(line.strip())
    return _tidy(" ".join(out))