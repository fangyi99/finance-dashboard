"""
READ-ONLY report: how would the engine categorise the transactions you already have, and how does that
compare with what's there now? It never writes anything (it ends with a rollback), so it's safe to run any
time, before you trust the engine and again whenever you change a rule.

    python -m app.classify.report

It shows:
  * what the engine would decide for everything: assigned / suggested / unknown
  * how often it agrees with the categories YOU set by hand (the honest accuracy test)
  * where it disagrees with categories an earlier rule gave (a bug it fixes shows up here)
  * the payees it can't place, biggest spend first: these are the rules worth adding

For a fuller picture run `python -m app.recategorize` once first: it fills in each payee's key, which the
repeat-payee check uses.
"""

from collections import Counter, defaultdict

from ..database import SessionLocal
from ..models import Account, Transaction
from .service import Categoriser


def _money(x):
    return f"{abs(x):,.2f}"


def report_for_user(db, user_id):
    categoriser = Categoriser(db, user_id, track_batch=False)
    uncategorized_id = categoriser.ids.get("Uncategorized")
    rows = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id)
        .order_by(Transaction.transaction_date, Transaction.created_at)
        .all()
    )
    status, mine, earlier, unplaced = Counter(), Counter(), Counter(), defaultdict(lambda: [0, 0.0])
    mine_wrong, earlier_diff = [], []

    for t in rows:
        r = categoriser.decide(
            account_id=t.account_id, description=t.description_raw, amount=t.amount,
            transaction_date=t.transaction_date, exclude_id=t.id, existing_pair_id=t.paired_transaction_id,
        )
        d = r.decision
        status[d.status] += 1
        now = categoriser.names_by_id.get(t.category_id) if t.category_id not in (None, uncategorized_id) else None
        kind = mine if t.category_source == "user" else earlier if t.category_source == "rule" and now else None
        if kind is not None:
            if d.status != "assigned":
                kind["engine unsure"] += 1
            elif d.category == now:
                kind["agree"] += 1
            else:
                kind["disagree"] += 1
                (mine_wrong if kind is mine else earlier_diff).append((now, d.category, t.description_raw[:56]))
        if d.status != "assigned" and now is None:
            key = r.payee_key or "(no payee)"
            unplaced[key][0] += 1
            unplaced[key][1] += abs(float(t.amount))

    print(f"\n=== {len(rows)} transactions ===")
    print("What the engine would decide:", ", ".join(f"{v} {k}" for k, v in status.most_common()))
    for title, counter, wrong in (("categories YOU set by hand", mine, mine_wrong), ("categories an earlier RULE gave", earlier, earlier_diff)):
        total = sum(counter.values())
        if total:
            print(f"\nAgainst the {total} {title}: " + ", ".join(f"{v} {k}" for k, v in counter.most_common()))
            for old, new, description in wrong[:10]:
                print(f"   was {old!r}, engine says {new!r}:  {description}")
    if unplaced:
        print("\nPayees it can't place, biggest spend first (each is a rule worth adding):")
        for key, (count, spend) in sorted(unplaced.items(), key=lambda kv: -kv[1][1])[:12]:
            print(f"   {count:>3} x  {_money(spend):>10}   {key[:60]}")


def run_report():
    db = SessionLocal()
    try:
        for (user_id,) in db.query(Account.user_id).distinct().all():
            report_for_user(db, user_id)
    finally:
        db.rollback()  # nothing above writes; this makes that a guarantee, not a hope
        db.close()


if __name__ == "__main__":
    run_report()