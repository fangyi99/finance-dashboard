"""
Prepare: one raw transaction in, a set of FACTS out. It decides nothing about categories.

What it pulls out of a line such as
    "Debit Card Transaction PRIME SUPERMARKET SINGAPO 01SEP XXXX-XXXX-XXXX-XXXX 000003017336439"
is: the bank's own type label (Debit Card Transaction), the direction of the money, the merchant
words (PRIME SUPERMARKET), and the things that are NOT the merchant (the card number, the
reference, the date the card was used). Keeping the two apart is what lets the engine read the
merchant without tripping over reference numbers.

The parser joins a transaction's lines with spaces, so where a payee's NAME ends and the MEMO
begins is lost ("FROM: AAA BBB SEND BACK ..."). That's worked around here and in the engine; if
the parser ever kept the line breaks the work-around could go.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from . import library as L
from ..sanitize import is_pseudonym
from .matching import find_phrase, tokenize

_MONTHS = "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
_CARD_MASK = re.compile(r"\b(?:[Xx\d]{4}-){3}[Xx\d]{4}\b")
_CARD_DATE = re.compile(rf"\b(\d{{1,2}}(?:{_MONTHS}))\b", re.IGNORECASE)
_TF_REF = re.compile(r"\bTF\d{10,}\b")
_FAST_REF = re.compile(r"\b\d{8}[A-Z]{4}[A-Z0-9]{6,}\b")
_LONG_NUMBER = re.compile(r"\b\d{6,}\b")
# Singapore UENs: businesses (8 digits + letter), local companies (9 digits + letter), others (T/S + yy + 2 letters + 4 digits + letter)
_UEN = re.compile(r"\b(?:\d{8}[A-Z]|\d{9}[A-Z]|[TS]\d{2}[A-Z]{2}\d{4}[A-Z])\b")
_COUNTERPARTY = re.compile(r"\b(FROM|TO)\s*:\s*(.*)$", re.IGNORECASE)
_CODE_LABEL = re.compile(rf"^({L.BANK_CODE_PATTERN})\b\s*(.*)$")


@dataclass
class Features:
    raw: str
    amount: Decimal
    direction: str  # "in" or "out"
    label: Optional[str]  # the bank's type label, lower case, if recognised
    channel: str  # card, transfer, fast, salary, cash, interest, pos, giro, own_transfer, fee, code or unknown
    merchant_text: str  # the merchant words, cleaned
    counterparty_text: str  # whatever follows FROM: or TO:, cleaned
    tokens: List[str]  # every searchable word (merchant + counterparty)
    references: List[str] = field(default_factory=list)
    long_numbers: List[str] = field(default_factory=list)
    reference_prefixes: List[str] = field(default_factory=list)  # e.g. ["TF"]
    uen: Optional[str] = None
    card_date: Optional[str] = None  # the date the CARD was used ("01SEP"), as printed
    paynow: bool = False
    business_like: bool = False
    clean_name: Optional[str] = None  # tidy display name
    payee_key: Optional[str] = None  # what a learned rule is keyed on


def _split_label(text: str):
    low = text.lower()
    for label in sorted(L.BANK_LABELS, key=len, reverse=True):
        if low.startswith(label) and (len(low) == len(label) or not low[len(label)].isalnum()):
            return label, L.BANK_LABELS[label]["channel"], text[len(label):].strip()
    match = _CODE_LABEL.match(text)
    if match:
        return match.group(1).lower(), "code", match.group(2)
    words = text.upper().split()
    for prefix, channel in sorted(L.CODE_PREFIXES, key=lambda p: len(p[0]), reverse=True):
        if tuple(words[: len(prefix)]) == prefix:
            return None, channel, " ".join(text.split()[len(prefix):])
    return None, "unknown", text


def _clean(text: str) -> str:
    return " ".join(text.split())


def prepare(description: str, amount) -> Features:
    amount = Decimal(str(amount))
    direction = "in" if amount > 0 else "out"
    text = _clean(description or "")
    label, channel, body = _split_label(text)

    uen_match = _UEN.search(text.upper())
    references, prefixes = [], []

    for match in _TF_REF.finditer(body):
        references.append(match.group())
        prefixes.append("TF")
    body = _TF_REF.sub(" ", body)
    for match in _FAST_REF.finditer(body):
        references.append(match.group())
    body = _FAST_REF.sub(" ", body)
    long_numbers = _LONG_NUMBER.findall(body)
    references += long_numbers
    body = _LONG_NUMBER.sub(" ", body)
    # references that mix letters and digits (0352FR22317891, MB113479726000K34)
    def _mixed_reference(match):
        word = match.group()
        if sum(c.isdigit() for c in word) >= 6 and any(c.isalpha() for c in word):
            references.append(word)
            return " "
        return word

    body = re.sub(r"[A-Za-z0-9]{9,}", _mixed_reference, body)

    body = _CARD_MASK.sub(" ", body)
    card_date = None
    date_match = _CARD_DATE.search(body)
    if date_match:
        card_date = date_match.group(1).upper()
        body = _CARD_DATE.sub(" ", body, count=1)
    body = _clean(body)

    counterparty = ""
    merchant = body
    cp = _COUNTERPARTY.search(body)
    if cp:
        merchant, counterparty = body[: cp.start()], cp.group(2)

    merchant_tokens = [t for t in tokenize(merchant) if t not in L.NOISE_WORDS]
    if channel in ("card", "pos", "code"):
        while merchant_tokens and merchant_tokens[-1] in L.TRAILING_COUNTRY:
            merchant_tokens.pop()
    counterparty_tokens = [t for t in tokenize(counterparty) if t != "OTHER"]

    all_tokens = merchant_tokens + counterparty_tokens
    business_like = any(t in L.BUSINESS_WORDS for t in all_tokens)
    paynow = find_phrase(tokenize(text), ["PAYNOW"]) is not None

    masked = lambda ts: bool(ts) and all(set(t) <= {"X"} for t in ts)  # noqa: E731

    clean_name = None
    if merchant_tokens and not masked(merchant_tokens):
        clean_name = " ".join(w.capitalize() for w in merchant_tokens)[:40]

    payee_key = None
    if counterparty_tokens:
        # the name is what comes before the memo; cap at 4 words since the boundary isn't marked
        memo_start = len(counterparty_tokens)
        phrases = [tokenize(p) for p in L.REIMBURSEMENT_PHRASES] + [tokenize(k.phrase) for k in L.KEYWORDS]
        for phrase in phrases:
            at = find_phrase(counterparty_tokens, phrase)
            if at is not None:
                memo_start = min(memo_start, at)
        name_tokens = counterparty_tokens[: min(memo_start, 4)]
        if is_pseudonym(counterparty_tokens[0]):
            name_tokens = counterparty_tokens[:1]  # a cleaned name is ONE word; whatever follows is the memo
        if name_tokens:
            payee_key = " ".join(name_tokens)
        if clean_name is None and name_tokens and not masked(name_tokens):
            clean_name = " ".join(w.capitalize() for w in name_tokens)[:40]
    elif merchant_tokens:
        payee_key = " ".join(t for t in merchant_tokens if not t.isdigit())[:60] or None

    return Features(
        raw=text, amount=amount, direction=direction, label=label, channel=channel,
        merchant_text=" ".join(merchant_tokens), counterparty_text=" ".join(counterparty_tokens),
        tokens=all_tokens, references=references, long_numbers=long_numbers, reference_prefixes=prefixes,
        uen=uen_match.group() if uen_match else None, card_date=card_date, paynow=paynow,
        business_like=business_like, clean_name=clean_name, payee_key=payee_key,
    )