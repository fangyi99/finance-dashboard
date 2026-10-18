"""
Teach the app a rule by hand: whenever a transaction contains PHRASE (as whole words), it's CATEGORY.

    python -m app.classify.add_rule "TOP UP TO PAYLAH" "Dining"
    python -m app.classify.add_rule "TAN AH KOW" "Dining" --no-apply     (don't touch earlier transactions)
    python -m app.classify.add_rule "..." "..." --user-id <uuid>         (only needed with more than one user)

Your rules beat every built-in rule. By default the rule is also applied to earlier transactions, except
ones you set by hand.
"""

import sys

from ..database import SessionLocal
from ..models import Account, CategorisationRule, Category
from .matching import tokenize
from .service import apply_rule_to_past


def add_rule(phrase, category_name, user_id=None, apply=True):
    db = SessionLocal()
    try:
        words = " ".join(tokenize(phrase))
        if not words:
            raise SystemExit("The phrase needs at least one word.")
        if user_id is None:
            users = [u for (u,) in db.query(Account.user_id).distinct().all()]
            if len(users) != 1:
                raise SystemExit(f"Found {len(users)} users with accounts; say which with --user-id.")
            user_id = users[0]
        category = (
            db.query(Category).filter(Category.name == category_name, (Category.user_id.is_(None)) | (Category.user_id == user_id))
            .order_by(Category.user_id.is_(None).desc()).first()
        )
        if category is None:
            names = sorted({c.name for c in db.query(Category).filter((Category.user_id.is_(None)) | (Category.user_id == user_id))})
            raise SystemExit(f"No category called {category_name!r}. Choose one of: {', '.join(names)}")
        rule = db.query(CategorisationRule).filter(CategorisationRule.user_id == user_id, CategorisationRule.phrase == words).first()
        if rule:
            rule.category_id = category.id
        else:
            db.add(CategorisationRule(user_id=user_id, phrase=words, category_id=category.id))
        db.flush()
        changed = apply_rule_to_past(db, user_id, words, category.id) if apply else 0
        db.commit()
        print(f"Rule saved: {words!r} -> {category.name}." + (f" Applied to {changed} earlier transaction(s)." if apply else ""))
        if apply and changed == 0:
            print("(None changed. If you expected some, run `python -m app.recategorize` first: it fills in the payee keys this uses.)")
    finally:
        db.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]
    uid = flags[flags.index("--user-id") + 1] if "--user-id" in flags else None
    if uid:
        args = [a for a in args if a != uid]
    if len(args) != 2:
        raise SystemExit(__doc__)
    add_rule(args[0], args[1], user_id=uid, apply="--no-apply" not in flags)