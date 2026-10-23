"""
The review queue: the transactions the app couldn't place, grouped so that ONE answer covers many.

Why groups: uncategorised transactions cluster. In the sandbox, 42 of them are only 13 payees, and one hawker
alone is 17 payments. Asking about a payee, not a transaction, turns dozens of questions into a few.

What needs review: a transaction with no category (or the built-in "Uncategorized"), that you haven't set
yourself. Spending in that state isn't counted in your budgets, which is why it's worth asking about.

A group is one payee in one direction: money OUT to a person is not the same question as money IN from them.

Skipping: one action, "I don't know". The group leaves the queue and the count, but stays uncategorised and
visible everywhere else, and can be moved back. The mark is kept inside the transaction's existing decision
record (categorisation["review"]), so this needs no migration, and recategorize preserves it.

Suggestions are shown only when there's evidence behind them. The built-in last-resort guess ("Shopping" for a
purchase nothing explains) is marked weak, because it has been right well under half the time: the screen should
ask the person to choose, not pre-select it.
"""

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .classify.matching import tokenize
from .classify.service import rule_phrase, save_rule
from .models import Account, Category, CategoryFeedback, CategoryVisibility, Transaction
from .sanitize import payee_label

REVIEW = "review"
SKIPPED = "skipped"
SAMPLE_COUNT = 3
QUICK_CHOICES = 5


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ---- pure helpers (no database; tested on their own) ---------------------------------------------------
def is_skipped(t) -> bool:
    return (t.categorisation or {}).get(REVIEW) == SKIPPED


def direction_of(t) -> str:
    return "in" if t.amount > 0 else "out"


def group_key(t) -> str:
    return f"{direction_of(t)}:{t.payee_key or 'row-' + str(t.id)}"


def _masked(payee_key: str) -> bool:
    tokens = tokenize(payee_key)
    return bool(tokens) and all(set(tok) <= {"X"} for tok in tokens)


def group_label(payee_key: Optional[str], rows) -> str:
    if not payee_key:
        base = "No description"
    elif _masked(payee_key):
        base = "Unnamed payee"
    else:
        base = payee_label(payee_key) or payee_key.title()  # a coded name reads as initials: "T.A.K. · BKQX"
    if rows and all(getattr(r, "txn_type", None) == "cash" for r in rows):
        return "Cash withdrawal" if base == "No description" else f"Cash withdrawal · {base}"
    return base


def pick_suggestion(rows, categories_by_name: Dict[str, Category]) -> Optional[dict]:
    """The group's suggestion: the one most of its rows agree on, and how much evidence stands behind it."""
    votes, strong, reason = Counter(), {}, {}
    for r in rows:
        record = r.categorisation or {}
        name = record.get("suggested_name") if record.get("status") == "suggested" else None
        if not name:
            continue
        votes[name] += 1
        strong[name] = strong.get(name, False) or record.get("source") != "default"
        evidence = record.get("evidence") or [{}]
        reason.setdefault(name, evidence[0].get("detail"))
    if not votes:
        return None
    name = votes.most_common(1)[0][0]
    category = categories_by_name.get(name.lower())
    why = reason.get(name) or ""
    return {
        "category_id": str(category.id) if category else None,
        "category_name": name,
        "exists": category is not None,  # False: the tree doesn't have it yet, so accepting creates it
        "strong": strong[name],
        "reason": (why[:1].upper() + why[1:]) if why else None,
        "votes": votes[name],
    }


def build_group(key: str, rows: list, categories_by_name: Dict[str, Category], both_directions: set) -> dict:
    ordered = sorted(rows, key=lambda r: (r.transaction_date, str(r.id)))
    total = sum((abs(r.amount) for r in rows), Decimal(0))
    payee = rows[0].payee_key
    currency = Counter(r.currency for r in rows).most_common(1)[0][0]
    return {
        "key": key,
        "label": group_label(payee, rows),
        "direction": direction_of(rows[0]),
        "count": len(rows),
        "total": str(total),
        "average": str((total / len(rows)).quantize(Decimal("0.01"))),
        "currency": currency,
        "first_date": ordered[0].transaction_date.isoformat(),
        "last_date": ordered[-1].transaction_date.isoformat(),
        "suggestion": pick_suggestion(rows, categories_by_name),
        # The same payee also appears going the other way, so one rule for both directions might be wrong.
        "both_directions": bool(payee) and payee in both_directions,
        "samples": [
            {"id": str(r.id), "date": r.transaction_date.isoformat(), "description": (r.description_raw or "")[:90], "amount": str(r.amount)}
            for r in reversed(ordered[-SAMPLE_COUNT:])
        ],
    }


def summarise(todo: list, skipped: list) -> dict:
    """The numbers behind the dashboard prompt. (Money is summed in the most common currency.)"""
    pool = todo or skipped
    currency = Counter(r.currency for r in pool).most_common(1)[0][0] if pool else "SGD"
    return {
        "groups": len({group_key(r) for r in todo}),
        "transactions": len(todo),
        "spend_total": str(sum((-r.amount for r in todo if r.amount < 0), Decimal(0))),
        "currency": currency,
        "skipped_groups": len({group_key(r) for r in skipped}),
        "skipped_transactions": len(skipped),
    }


# ---- loading ----------------------------------------------------------------------------------------
def _visible_categories(db: Session, user_id) -> List[Category]:
    return db.query(Category).filter(or_(Category.user_id.is_(None), Category.user_id == user_id)).all()


def _needs_review(db: Session, user_id, uncategorized_id) -> list:
    unplaced = Transaction.category_id.is_(None)
    if uncategorized_id:
        unplaced = or_(unplaced, Transaction.category_id == uncategorized_id)
    return (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id, Transaction.amount != 0, Transaction.category_source != "user", unplaced)
        .all()
    )


def _payees_both_ways(db: Session, user_id) -> set:
    rows = (
        db.query(Transaction.payee_key)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id, Transaction.payee_key.isnot(None))
        .group_by(Transaction.payee_key)
        .having(func.min(Transaction.amount) < 0, func.max(Transaction.amount) > 0)
        .all()
    )
    return {p for (p,) in rows}


def _quick_choices(db: Session, user_id, categories: List[Category]) -> dict:
    usage = dict(
        db.query(Transaction.category_id, func.count(Transaction.id))
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id, Transaction.category_id.isnot(None))
        .group_by(Transaction.category_id)
        .all()
    )
    hidden = {c for (c,) in db.query(CategoryVisibility.category_id).filter(CategoryVisibility.user_id == user_id)}
    parents = {c.parent_category_id for c in categories if c.parent_category_id}  # group headers, not answers

    def pick(types):
        candidates = [c for c in categories if c.type in types and c.id not in hidden and c.id not in parents
                      and not (c.name == "Uncategorized" and c.user_id is None)]
        ranked = sorted(candidates, key=lambda c: (-usage.get(c.id, 0), c.name))
        return [{"id": str(c.id), "name": c.name, "type": c.type} for c in ranked[:QUICK_CHOICES]]

    return {"out": pick({"expense", "transfer"}), "in": pick({"income", "transfer"})}


def _by_name(categories: List[Category]) -> Dict[str, Category]:
    out: Dict[str, Category] = {}
    for c in sorted(categories, key=lambda c: c.user_id is not None):  # a built-in category wins a name clash
        out.setdefault(c.name.lower(), c)
    return out


def load_review(db: Session, user_id, skipped: bool = False) -> dict:
    categories = _visible_categories(db, user_id)
    uncategorized = next((c.id for c in categories if c.name == "Uncategorized" and c.user_id is None), None)
    rows = _needs_review(db, user_id, uncategorized)
    todo = [r for r in rows if not is_skipped(r)]
    parked = [r for r in rows if is_skipped(r)]

    grouped = defaultdict(list)
    for r in (parked if skipped else todo):
        grouped[group_key(r)].append(r)
    both, names = _payees_both_ways(db, user_id), _by_name(categories)
    groups = [build_group(key, members, names, both) for key, members in grouped.items()]
    groups.sort(key=lambda g: (-Decimal(g["total"]), -g["count"], g["label"]))
    return {"groups": groups, "summary": summarise(todo, parked), "quick_choices": _quick_choices(db, user_id, categories)}


# ---- acting on a group --------------------------------------------------------------------------------
def _members(db: Session, user_id, key: str, want_skipped: Optional[bool]) -> list:
    categories = _visible_categories(db, user_id)
    uncategorized = next((c.id for c in categories if c.name == "Uncategorized" and c.user_id is None), None)
    rows = [r for r in _needs_review(db, user_id, uncategorized) if group_key(r) == key]
    if want_skipped is not None:
        rows = [r for r in rows if is_skipped(r) == want_skipped]
    if not rows:
        raise ReviewError(404, "That group has already been dealt with.")
    return rows


def _legacy_record(t) -> dict:
    return {"engine": 0, "status": "unknown", "source": "legacy", "confidence": 0, "type": t.txn_type,
            "suggested_name": None, "candidates": [], "evidence": []}


def skip_group(db: Session, user_id, key: str) -> int:
    rows = _members(db, user_id, key, want_skipped=False)
    now = datetime.now(timezone.utc).isoformat()
    for t in rows:
        t.categorisation = {**(t.categorisation or _legacy_record(t)), REVIEW: SKIPPED, "skipped_at": now}
    db.commit()
    return len(rows)


def unskip_group(db: Session, user_id, key: str) -> int:
    rows = _members(db, user_id, key, want_skipped=True)
    for t in rows:
        t.categorisation = {k: v for k, v in (t.categorisation or {}).items() if k not in (REVIEW, "skipped_at")}
    db.commit()
    return len(rows)


def _chosen_category(db: Session, user_id, category_id, new_category: Optional[dict], direction: str):
    """The category to file under: an existing one by id, or one named by the person (reused if it exists)."""
    if category_id:
        category = db.get(Category, category_id)
        if category is None or category.user_id not in (None, user_id):
            raise ReviewError(404, "Category not found.")
        created = False
    else:
        name = (new_category or {}).get("name", "").strip()
        if not name:
            raise ReviewError(400, "The category needs a name.")
        category = (
            db.query(Category)
            .filter(or_(Category.user_id.is_(None), Category.user_id == user_id),
                    func.lower(Category.name) == name.lower(), Category.parent_category_id.is_(None))
            .first()
        )
        created = category is None
        if created:
            category = Category(
                user_id=user_id, name=name, parent_category_id=None, is_system_default=False,
                type=(new_category or {}).get("type") or ("income" if direction == "in" else "expense"),
            )
            db.add(category)
            db.flush()
    if category.name == "Uncategorized" and category.user_id is None:
        raise ReviewError(400, "Pick a real category, or use Skip if you don't know.")
    return category, created


def resolve_group(db: Session, user_id, key: str, category_id=None, new_category: Optional[dict] = None, apply_to_all: bool = True) -> dict:
    """
    Files every transaction in the group under one category, as YOUR choice (so nothing ever overrides it), and
    records each as a correction (the training data for any future model). With apply_to_all it also saves a rule
    for the payee, applied to earlier transactions you haven't set yourself and to every future one.
    """
    rows = _members(db, user_id, key, want_skipped=None)
    category, created = _chosen_category(db, user_id, category_id, new_category, direction_of(rows[0]))
    record = {
        "engine": 1, "status": "assigned", "source": "user", "confidence": 1.0, "type": rows[0].txn_type,
        "suggested_name": None, "candidates": [[category.name, 1.0]],
        "evidence": [{"signal": "user_choice", "category": category.name, "points": 1.0, "detail": "you chose this category"}],
    }
    for t in rows:
        t.category_id, t.category_source, t.category_confidence, t.suggested_category_id = category.id, "user", None, None
        t.categorisation = {**record, "type": t.txn_type}  # a fresh record: this also clears any skip mark
        db.add(CategoryFeedback(transaction_id=t.id, description_normalized=t.description_normalized, corrected_category_id=category.id))
    rule_text, also_filed = None, 0
    if apply_to_all:
        rule_text = rule_phrase(rows[0].payee_key)
        if rule_text:
            _, also_filed = save_rule(db, user_id, rule_text, category.id, True, skip_ids={t.id for t in rows})
    db.commit()
    return {
        "resolved": len(rows), "category": {"id": str(category.id), "name": category.name},
        "created_category": created, "rule": rule_text, "also_filed": also_filed,
    }