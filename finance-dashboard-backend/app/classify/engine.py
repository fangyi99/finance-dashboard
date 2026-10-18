"""
Decide: facts in (from prepare.py), a decision out.

Stages, first one to decide wins:

  1. Your own rules          payees and phrases you've confirmed          -> assigned
  2. Own-account pairing     an equal and opposite amount in your other
                             account (the caller works that out)          -> assigned
  3. Hard rules              bank type labels, your own wallets, known
                             merchants and billers, airline tickets,
                             self-transfer codes, "send back" repayments  -> assigned
  4. Evidence scoring        direction-aware keywords plus weak signals
                             (amount, repeat small payee, round amount),
                             combined as 1 - product(1 - strength)        -> assigned / suggested / unknown
  5. Default                 an unexplained PURCHASE gets a low-confidence
                             suggestion, never an assignment

Every decision carries the evidence that produced it, so the app can say WHY.

The statuses matter because budgets only count what is ASSIGNED:
    assigned    confident enough to count
    suggested   a good guess, waiting for one tap; does not count
    unknown     nothing reliable to go on

Weak signals (amount, repeats, round numbers, business-like names) are capped when combined, so
they can move a suggestion but can never, on their own, create an assignment.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from . import library as L
from .matching import best_match, build_index, find_phrase, tokenize
from .prepare import Features

# ---- thresholds and weights: the numbers to tune --------------------------------------------
ASSIGN_AT = 0.80  # a top score at least this, and clear of the runner-up, is assigned
LEAD_AT = 0.20  # ...clear meaning ahead of the second candidate by this much
SUGGEST_AT = 0.25  # at least this and it's worth suggesting
WEAK_CAP = 0.60  # all the weak signals together can't count for more than this
EPS = 1e-9

HARD_MERCHANT = 0.95
HARD_PAIRING = 0.98
HARD_LABEL = 0.99
HARD_AIRLINE = 0.90
HARD_REPAYMENT = 0.85
W_REPEAT_SMALL = 0.20  # three or more payments to the same payee, all small
W_SMALL_AMOUNT = 0.10
W_ROUND_AMOUNT = 0.10
SMALL = Decimal("15")
DEFAULT_SUGGESTION_SCORE = 0.20

# "Income" entries (the seed lists SALARY as a merchant) only make sense for money coming IN: a
# salary advance you PAY is not income. So money going out is matched against everything else.
_MERCHANT_PHRASES = {p: c for c, ps in L.all_merchants().items() for p in ps}
_MERCHANTS_IN = build_index(_MERCHANT_PHRASES)
_MERCHANTS_OUT = build_index({p: c for p, c in _MERCHANT_PHRASES.items() if c != "Income"})
_REIMBURSEMENT = build_index({p: True for p in L.REIMBURSEMENT_PHRASES})
_OWN_WALLET = build_index({p: True for p in L.OWN_WALLET_PHRASES})
_KEYWORDS: List[Tuple[Tuple[str, ...], L.Keyword]] = [(tuple(tokenize(k.phrase)), k) for k in L.KEYWORDS]


@dataclass
class UserRule:
    phrase: str  # matched as whole words anywhere in the transaction's words
    category: str


@dataclass
class Context:
    user_rules: List[UserRule] = field(default_factory=list)
    paired_own_account: bool = False  # an equal, opposite amount sits in another of the user's accounts
    history: Dict[str, List[Decimal]] = field(default_factory=dict)  # payee_key -> EARLIER outgoing amounts
    available_categories: Optional[set] = None  # leaf names in the user's tree; None = don't check


@dataclass
class Evidence:
    signal: str
    category: Optional[str]
    points: float
    detail: str


@dataclass
class Decision:
    status: str  # assigned | suggested | unknown
    category: Optional[str]
    type: str
    source: str  # user_rule | pairing | hard_rule | score | default | none
    confidence: float
    evidence: List[Evidence]
    candidates: List[Tuple[str, float]]
    features: Features


def _noisy_or(points: List[float]) -> float:
    left = 1.0
    for p in points:
        left *= 1.0 - p
    return 1.0 - left


def _guess_type(f: Features, category: Optional[str]) -> str:
    if category == "Own Accounts":
        return "own_transfer"
    if f.channel in ("card", "pos"):
        return "purchase"
    if f.channel == "salary":
        return "income"
    if f.channel == "interest":
        return "interest"
    if f.channel == "cash":
        return "cash"
    if f.channel == "giro":
        return "bill"
    if f.channel == "fee":
        return "fee"
    if f.channel in ("fast", "transfer", "own_transfer", "code"):
        if f.channel == "code":
            return "purchase" if f.direction == "out" else "unknown"
        return "person_payment" if f.direction == "out" else "incoming_transfer"
    return "unknown"


def _finish(f, ctx, status, category, source, confidence, evidence, candidates, type_=None) -> Decision:
    # A decision in a category the user's tree doesn't have can only ever be a suggestion.
    if category and ctx.available_categories is not None and category not in ctx.available_categories:
        evidence = evidence + [Evidence("missing_category", category, 0.0, f"'{category}' isn't in your category tree yet")]
        if status == "assigned":
            status = "suggested"
    return Decision(status, category, type_ or _guess_type(f, category), source, confidence, evidence, candidates, f)


def decide(f: Features, context: Optional[Context] = None) -> Decision:
    ctx = context or Context()
    tokens = f.tokens
    raw_tokens = tokenize(f.raw)

    # 1. your own rules -------------------------------------------------------------------
    for rule in ctx.user_rules:
        if find_phrase(raw_tokens, tokenize(rule.phrase)) is not None:
            ev = [Evidence("user_rule", rule.category, 1.0, f"your rule: '{rule.phrase}'")]
            wallet = f.direction == "out" and best_match(raw_tokens, _OWN_WALLET)
            return _finish(f, ctx, "assigned", rule.category, "user_rule", 1.0, ev, [(rule.category, 1.0)], "own_transfer" if wallet else None)

    # 2. own-account pairing --------------------------------------------------------------
    if ctx.paired_own_account:
        ev = [Evidence("pairing", "Own Accounts", HARD_PAIRING, "an equal and opposite amount in another of your accounts")]
        return _finish(f, ctx, "assigned", "Own Accounts", "pairing", HARD_PAIRING, ev, [("Own Accounts", HARD_PAIRING)], "own_transfer")

    # 3. hard rules -----------------------------------------------------------------------
    if f.channel in ("salary", "interest"):
        ev = [Evidence("bank_label", "Income", HARD_LABEL, f"the bank labels it '{f.label}'")]
        return _finish(f, ctx, "assigned", "Income", "hard_rule", HARD_LABEL, ev, [("Income", HARD_LABEL)])

    if f.direction == "out" and best_match(raw_tokens, _OWN_WALLET):
        ev = [Evidence("own_wallet", "Own Accounts", HARD_MERCHANT, "a top-up to your own wallet")]
        return _finish(f, ctx, "assigned", "Own Accounts", "hard_rule", HARD_MERCHANT, ev, [("Own Accounts", HARD_MERCHANT)], "own_transfer")

    merchant = best_match(tokens, _MERCHANTS_IN if f.direction == "in" else _MERCHANTS_OUT)
    if merchant:
        phrase, category, _ = merchant
        ev = [Evidence("known_merchant", category, HARD_MERCHANT, f"known merchant or biller: {' '.join(phrase)}")]
        return _finish(f, ctx, "assigned", category, "hard_rule", HARD_MERCHANT, ev, [(category, HARD_MERCHANT)])

    if f.channel in ("card", "pos", "code") and f.long_numbers and any(
        len(n) == 13 for n in f.long_numbers
    ) and any(t.endswith("AIR") or t.endswith("AIRLINES") or t.endswith("AIRWAYS") for t in tokens):
        ev = [Evidence("airline_ticket", "Travel", HARD_AIRLINE, "an airline name with a 13-digit ticket number")]
        return _finish(f, ctx, "assigned", "Travel", "hard_rule", HARD_AIRLINE, ev, [("Travel", HARD_AIRLINE)], "purchase")

    if f.channel == "own_transfer":
        ev = [Evidence("self_transfer_code", "Own Accounts", HARD_MERCHANT, "the bank's self-transfer code")]
        return _finish(f, ctx, "assigned", "Own Accounts", "hard_rule", HARD_MERCHANT, ev, [("Own Accounts", HARD_MERCHANT)], "own_transfer")

    if f.direction == "in" and f.channel in ("fast", "transfer") and best_match(f.counterparty_text and tokenize(f.counterparty_text) or tokens, _REIMBURSEMENT):
        ev = [Evidence("repayment_words", "Friends & Family", HARD_REPAYMENT, "money coming back from a person ('send back', 'refund'...)")]
        return _finish(f, ctx, "assigned", "Friends & Family", "hard_rule", HARD_REPAYMENT, ev, [("Friends & Family", HARD_REPAYMENT)], "reimbursement")

    # 4. evidence scoring -----------------------------------------------------------------
    strong: Dict[str, List[Evidence]] = {}
    weak: Dict[str, List[Evidence]] = {}

    for phrase, keyword in _KEYWORDS:
        if keyword.direction not in ("any", f.direction):
            continue
        if find_phrase(tokens, phrase) is not None:
            strong.setdefault(keyword.category, []).append(
                Evidence("keyword", keyword.category, keyword.strength, f"the word '{' '.join(phrase)}' on money going {f.direction}")
            )

    person_payment = f.channel in ("fast", "transfer") and f.direction == "out"
    if person_payment:
        earlier = ctx.history.get(f.payee_key or "", [])
        if len(earlier) >= 2 and all(a <= SMALL for a in earlier) and abs(f.amount) <= SMALL:
            weak.setdefault("Dining", []).append(
                Evidence("repeat_small_payee", "Dining", W_REPEAT_SMALL, f"{len(earlier) + 1} small payments to the same payee")
            )
        if abs(f.amount) <= SMALL:
            weak.setdefault("Dining", []).append(Evidence("small_amount", "Dining", W_SMALL_AMOUNT, "a small amount"))
        if f.counterparty_text and abs(f.amount) >= 50 and abs(f.amount) % 10 == 0:
            weak.setdefault("Friends & Family", []).append(Evidence("round_amount", "Friends & Family", W_ROUND_AMOUNT, "a round amount to a person"))

    scores: Dict[str, float] = {}
    evidence: List[Evidence] = []
    for category in set(strong) | set(weak):
        solid = _noisy_or([e.points for e in strong.get(category, [])])
        soft = min(_noisy_or([e.points for e in weak.get(category, [])]), WEAK_CAP)
        scores[category] = _noisy_or([solid, soft])
        evidence += strong.get(category, []) + weak.get(category, [])
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:2]

    if ranked:
        top_category, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        top_evidence = [e for e in evidence if e.category == top_category]
        if top >= ASSIGN_AT - EPS and top - second >= LEAD_AT - EPS:
            return _finish(f, ctx, "assigned", top_category, "score", top, top_evidence, ranked)
        if top >= SUGGEST_AT - EPS:
            return _finish(f, ctx, "suggested", top_category, "score", top, top_evidence, ranked)

    # 5. default --------------------------------------------------------------------------
    if _guess_type(f, None) == "purchase" and L.DEFAULT_PURCHASE_SUGGESTION:
        why = "a purchase, but nothing says what it was" + (" (a business-like name)" if f.business_like else "")
        ev = [Evidence("default_purchase", L.DEFAULT_PURCHASE_SUGGESTION, DEFAULT_SUGGESTION_SCORE, why)]
        return _finish(f, ctx, "suggested", L.DEFAULT_PURCHASE_SUGGESTION, "default", DEFAULT_SUGGESTION_SCORE, ev, [(L.DEFAULT_PURCHASE_SUGGESTION, DEFAULT_SUGGESTION_SCORE)])

    return _finish(f, ctx, "unknown", None, "none", 0.0, [], ranked)