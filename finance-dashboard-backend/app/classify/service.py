"""
The bridge between the pure engine and the database. Everything here talks to the database;
nothing here decides anything (engine.py does that).

    Categoriser(db, user_id).decide(...)   one transaction in, a Resolved out: the columns to store
    link_pair(...)                         records an own-account transfer on BOTH of its sides
    learn_from_correction(...)             you set a category: remember it as a rule, apply it to the past
    apply_rule_to_past(...)                what "apply to the others too" means

A Categoriser loads the user's categories and rules ONCE, so an import of hundreds of rows costs
two or three small queries per row (repeat-payee history and own-account pairing), not a reload.

What gets stored, and the rule that keeps budgets honest:
    assigned    -> category_id is set (this is what budgets and summaries count)
    suggested   -> suggested_category_id is set and category_id stays EMPTY, so a guess never counts
    unknown     -> both stay empty
    always      -> txn_type, payee_key and a `categorisation` record saying WHY
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import sanitize
from ..categorization import normalize_description
from ..models import Account, CategorisationRule, Category, Transaction
from .engine import Context, Decision, UserRule, decide
from .matching import find_phrase, tokenize
from .prepare import Features, prepare

PAIR_WINDOW_DAYS = 2  # an own-account transfer shows up within this many days on the other side
PAIRABLE_CHANNELS = {"fast", "transfer", "own_transfer"}  # a card purchase is never half of a transfer
PAIRING_CONFIDENCE = Decimal("0.980")


@dataclass
class Resolved:
    """What to store for one transaction."""

    category_id: Optional[uuid.UUID]
    category_source: str
    category_confidence: Optional[Decimal]
    description_normalized: str
    description_raw: str  # the CLEANED text: this, and never the original, is what gets stored
    suggested_category_id: Optional[uuid.UUID]
    txn_type: str
    payee_key: Optional[str]
    categorisation: dict
    pair_with: Optional[uuid.UUID]  # the other half of an own-account transfer (set only when pairing decided it)
    decision: Decision

    def fields(self) -> dict:
        """Column values for a new Transaction (or a bulk-insert row)."""
        return {
            "category_id": self.category_id,
            "category_source": self.category_source,
            "category_confidence": self.category_confidence,
            "description_normalized": self.description_normalized,
            "description_raw": self.description_raw,
            "suggested_category_id": self.suggested_category_id,
            "txn_type": self.txn_type,
            "payee_key": self.payee_key,
            "categorisation": self.categorisation,
            "paired_transaction_id": self.pair_with,
        }


def _record(decision: Decision, status: str) -> dict:
    return {
        "engine": 1,
        "status": status,
        "source": decision.source,
        "confidence": round(decision.confidence, 3),
        "type": decision.type,
        "suggested_name": decision.category if status == "suggested" else None,
        "candidates": [[name, round(score, 3)] for name, score in decision.candidates],
        "evidence": [
            {"signal": e.signal, "category": e.category, "points": round(e.points, 3), "detail": e.detail}
            for e in decision.evidence
        ],
    }


class Categoriser:
    def __init__(self, db: Session, user_id: uuid.UUID, track_batch: bool = True, redact_names: Optional[bool] = None):
        self.db = db
        self.user_id = user_id
        # Names are replaced by a code before anything is decided or stored (see sanitize.py). The sandbox turns
        # this off (its names are fictional), and so does recategorize, which only re-reads what is already stored.
        self.redact_names = sanitize.REDACT_NAMES if redact_names is None else redact_names
        # An import adds rows in bulk AFTER deciding them all, so the database can't yet see the
        # earlier rows of the same import; track_batch remembers them for the repeat-payee check.
        self.track_batch = track_batch
        self._batch: Dict[str, List[Decimal]] = defaultdict(list)

        categories = db.query(Category).filter(or_(Category.user_id.is_(None), Category.user_id == user_id)).all()
        self.names_by_id = {c.id: c.name for c in categories}
        self.ids: Dict[str, uuid.UUID] = {}
        for c in sorted(categories, key=lambda c: c.user_id is not None):  # a built-in category wins a name clash
            self.ids.setdefault(c.name, c.id)

        rules = db.query(CategorisationRule).filter(CategorisationRule.user_id == user_id).all()
        loaded = [UserRule(r.phrase, self.names_by_id[r.category_id]) for r in rules if r.category_id in self.names_by_id]
        # the most specific rule (most words) is tried first
        self.rules = sorted(loaded, key=lambda r: (-len(tokenize(r.phrase)), -len(r.phrase)))

    # ---- the three things the engine can't know on its own -----------------------------------
    def _counterpart(self, f: Features, account_id, amount: Decimal, tx_date: date, exclude_id, existing_pair_id):
        """The other half of an own-account transfer, if there is one."""
        if existing_pair_id:  # already linked: keep it stable
            return self.db.get(Transaction, existing_pair_id)
        if f.channel not in PAIRABLE_CHANNELS or amount == 0:
            return None
        window = timedelta(days=PAIR_WINDOW_DAYS)
        query = (
            self.db.query(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .filter(
                Account.user_id == self.user_id,
                Transaction.account_id != account_id,
                Transaction.amount == -amount,
                Transaction.paired_transaction_id.is_(None),
                Transaction.transaction_date.between(tx_date - window, tx_date + window),
            )
        )
        if exclude_id:
            query = query.filter(Transaction.id != exclude_id)
        for candidate in query.order_by(func.abs(Transaction.transaction_date - tx_date), Transaction.created_at).limit(5):
            if prepare(candidate.description_raw, candidate.amount).channel in PAIRABLE_CHANNELS:
                return candidate
        return None

    def _history(self, f: Features, exclude_id) -> Dict[str, List[Decimal]]:
        """Other outgoing payments to the same payee, for the repeat-small-payee check."""
        if not f.payee_key or f.direction != "out":
            return {}
        query = (
            self.db.query(Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .filter(Account.user_id == self.user_id, Transaction.payee_key == f.payee_key, Transaction.amount < 0)
        )
        if exclude_id:
            query = query.filter(Transaction.id != exclude_id)
        earlier = [abs(a) for (a,) in query.all()] + self._batch.get(f.payee_key, [])
        return {f.payee_key: earlier}

    # ---- the decision -------------------------------------------------------------------------
    def decide(self, *, account_id, description: str, amount, transaction_date: date, exclude_id=None, existing_pair_id=None) -> Resolved:
        amount = Decimal(str(amount))
        description = sanitize.clean_text(description, names=self.redact_names)  # decide on, and store, the cleaned text
        features = prepare(description, amount)
        counterpart = self._counterpart(features, account_id, amount, transaction_date, exclude_id, existing_pair_id)
        context = Context(
            user_rules=self.rules,
            paired_own_account=counterpart is not None,
            history=self._history(features, exclude_id),
            available_categories=set(self.ids),
        )
        decision = decide(features, context)

        if self.track_batch and amount < 0 and features.payee_key:
            self._batch[features.payee_key].append(abs(amount))
        return self._resolve(features, decision, description, counterpart)

    def _resolve(self, f: Features, d: Decision, description: str, counterpart) -> Resolved:
        status = d.status
        category_id = self.ids.get(d.category) if status == "assigned" and d.category else None
        if status == "assigned" and category_id is None:
            status = "suggested"  # the engine only assigns categories that exist; be safe anyway
        suggested_id = self.ids.get(d.category) if status == "suggested" and d.category else None
        return Resolved(
            category_id=category_id,
            category_source="rule",  # the column only allows ml | rule | user; 'user' is for a human's own choice
            category_confidence=Decimal(str(round(d.confidence, 3))) if category_id else None,
            description_normalized=normalize_description(description),
            description_raw=description,
            suggested_category_id=suggested_id,
            txn_type=d.type,
            payee_key=f.payee_key,
            categorisation=_record(d, status),
            pair_with=counterpart.id if (counterpart is not None and d.source == "pairing") else None,
            decision=d,
        )


# ---- what a row becomes (shared by the database paths here and the in-memory sandbox build) ------
def pairing_protected(category_source, categorisation) -> bool:
    """A partner you categorised yourself, or one a rule of yours decided, is never re-filed by pairing."""
    return category_source == "user" or (categorisation or {}).get("source") == "user_rule"


def pairing_fields(own_category_id) -> dict:
    """The column values of a transaction found to be half of an own-account transfer."""
    return {
        "category_id": own_category_id,
        "category_source": "rule",
        "category_confidence": PAIRING_CONFIDENCE,
        "suggested_category_id": None,
        "txn_type": "own_transfer",
        "categorisation": {
            "engine": 1, "status": "assigned", "source": "pairing", "confidence": 0.98, "type": "own_transfer",
            "suggested_name": None, "candidates": [["Own Accounts", 0.98]],
            "evidence": [{"signal": "pairing", "category": "Own Accounts", "points": 0.98,
                          "detail": "paired with a transaction in another of your accounts"}],
        },
    }


def user_rule_fields(category_id, category_name, txn_type, phrase) -> dict:
    """The column values of a transaction that one of YOUR rules has filed."""
    return {
        "category_id": category_id,
        "category_source": "rule",
        "category_confidence": Decimal("1.000"),
        "suggested_category_id": None,
        "categorisation": {
            "engine": 1, "status": "assigned", "source": "user_rule", "confidence": 1.0, "type": txn_type,
            "suggested_name": None, "candidates": [[category_name, 1.0]],
            "evidence": [{"signal": "user_rule", "category": category_name, "points": 1.0, "detail": f"your rule: '{phrase}'"}],
        },
    }


# ---- own-account pairing -----------------------------------------------------------------------
def link_pair(db: Session, categoriser: Categoriser, new_id, counterpart_id, override_rule_assigned: bool = True) -> None:
    """
    Records an own-account transfer on both sides. The NEW transaction already knows its partner
    (it was stored with paired_transaction_id); this tells the partner, and, unless you've set the
    partner's category yourself or taught a rule for it, re-files it as Own Accounts too. That's what
    makes the order of import irrelevant: whichever statement arrives second fixes up the first.
    With override_rule_assigned=False, a partner that a rule already categorised is linked but left as it is.
    """
    if not counterpart_id:
        return
    new, other = db.get(Transaction, new_id), db.get(Transaction, counterpart_id)
    if new is None or other is None:
        return
    new.paired_transaction_id = other.id
    other.paired_transaction_id = new.id
    protected = pairing_protected(other.category_source, other.categorisation)
    if not override_rule_assigned and other.category_id not in (None, categoriser.ids.get("Uncategorized")):
        protected = True
    own = categoriser.ids.get("Own Accounts")
    if own and not protected:
        for column, value in pairing_fields(own).items():
            setattr(other, column, value)


# ---- learning ---------------------------------------------------------------------------------
def rule_phrase(payee_key: Optional[str]) -> Optional[str]:
    """
    The durable part of a payee key. Reference-like and masked pieces (digits, XXXX) are dropped, so
    "TOP UP TO PAYLAH XXXXXX" teaches "TOP UP TO PAYLAH". A payee with no durable words (a fully
    masked name) yields None: there is nothing to learn from.
    """
    words = [t for t in tokenize(payee_key or "") if not t.isdigit() and set(t) != {"X"}]
    phrase = " ".join(words)
    return phrase if len(phrase) >= 3 else None


def apply_rule_to_past(db: Session, user_id, phrase: str, category_id, skip_ids=()) -> int:
    """
    Files every earlier transaction whose payee contains `phrase` under `category_id`, EXCEPT ones you
    set yourself. Returns how many changed.
    """
    words = tokenize(phrase)
    if not words:
        return 0
    name = db.get(Category, category_id).name
    query = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.category_source != "user",
            Transaction.payee_key.ilike(f"%{' '.join(words)}%"),
        )
    )
    changed = 0
    for t in query:
        if t.id in skip_ids or find_phrase(tokenize(t.payee_key or ""), words) is None:
            continue
        if t.category_id == category_id and t.suggested_category_id is None:
            continue
        for column, value in user_rule_fields(category_id, name, t.txn_type, phrase).items():
            setattr(t, column, value)
        changed += 1
    return changed


def save_rule(db: Session, user_id, phrase: str, category_id, apply_to_past: bool = True, skip_ids=()):
    """
    Saves "this phrase means this category" as one of YOUR rules (changing the category if the rule exists),
    and optionally files the earlier matching transactions that you haven't set yourself.
    Returns (rule, how many earlier transactions it re-filed).
    """
    rule = db.query(CategorisationRule).filter(CategorisationRule.user_id == user_id, CategorisationRule.phrase == phrase).first()
    if rule:
        rule.category_id = category_id
    else:
        rule = CategorisationRule(user_id=user_id, phrase=phrase, category_id=category_id)
        db.add(rule)
    db.flush()
    applied = apply_rule_to_past(db, user_id, phrase, category_id, skip_ids=set(skip_ids)) if apply_to_past else 0
    return rule, applied


def keep_review_state(old, new):
    """
    A decision record is rewritten when a transaction is re-evaluated. If you had SKIPPED it in the review
    queue, that has to survive the rewrite, or recategorize would quietly put it back in your queue.
    """
    if old and old.get("review") == "skipped":
        kept = {"review": "skipped"}
        if "skipped_at" in old:
            kept["skipped_at"] = old["skipped_at"]
        return {**new, **kept}
    return new


def learn_from_correction(db: Session, transaction: Transaction, category_id, apply_to_past: bool = True):
    """
    Call this when YOU set or confirm a category on a transaction. It remembers "this payee means this
    category" as one of your rules, and (optionally) applies it to the earlier ones. Returns the rule, or
    None if there was nothing durable to learn (no category, "Uncategorized", or a payee with no real name).
    """
    if category_id is None:
        return None
    category = db.get(Category, category_id)
    if category is None or (category.name == "Uncategorized" and category.user_id is None):
        return None
    key = transaction.payee_key or prepare(transaction.description_raw, transaction.amount).payee_key
    phrase = rule_phrase(key)
    if not phrase:
        return None
    user_id = db.get(Account, transaction.account_id).user_id
    rule, _ = save_rule(db, user_id, phrase, category_id, apply_to_past, skip_ids={transaction.id})
    return rule