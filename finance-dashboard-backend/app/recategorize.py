"""
Re-runs the categoriser over transactions already in the database. Run it once after the migration (it
also fills in the new payee_key and txn_type columns), and again whenever the engine or its rules improve.
Categorisation otherwise only runs once, when a transaction is created.

    python -m app.recategorize                  uncategorised transactions only (what it always did)
    python -m app.recategorize --rules          ALSO re-check transactions a rule filed earlier: their category
                                                changes only when the engine is confident AND disagrees
    python -m app.recategorize --dry-run        show what would change, and change nothing

Never touches a category YOU set by hand (category_source 'user'). For those it only fills in payee_key
and txn_type, which changes nothing you can see.
"""

import sys
from collections import Counter, defaultdict
from decimal import Decimal

from .classify.prepare import prepare
from .classify.service import Categoriser, keep_review_state, link_pair
from .database import SessionLocal
from .models import Account, Transaction


def _apply(db, categoriser, t, r, uncategorized_id, include_rules, original_category_id):
    """
    Applies one decision to one transaction. Returns what happened, as a word.

    `original_category_id` is what the row had when this run STARTED: an earlier row in the run can
    re-file this one as the other half of an own-account transfer, and the summary has to count that
    as a change, not as something that was already so.
    """
    t.payee_key = r.payee_key
    t.txn_type = r.txn_type
    outcome = "unchanged"
    uncategorised = t.category_id is None or t.category_id == uncategorized_id
    was_uncategorised = original_category_id is None or original_category_id == uncategorized_id

    if t.category_source == "user":
        outcome = "kept_yours"
    elif was_uncategorised and not uncategorised:
        outcome = "assigned"  # filed a moment ago as the other half of an own-account transfer
    elif uncategorised:
        t.categorisation = keep_review_state(t.categorisation, r.categorisation)
        if r.category_id:
            t.category_id, t.category_source, t.category_confidence = r.category_id, "rule", r.category_confidence
            t.suggested_category_id = None
            outcome = "assigned"
        else:
            t.suggested_category_id = r.suggested_category_id
            outcome = "suggested" if r.decision.status == "suggested" else "unknown"
    elif include_rules and t.category_source == "rule":
        if r.category_id is None:
            outcome = "kept_rule"  # the engine isn't confident: leave the earlier decision alone
        elif r.category_id == t.category_id:
            t.categorisation = r.categorisation
            outcome = "confirmed" if t.category_id == original_category_id else "changed"
        else:
            t.category_id, t.category_source, t.category_confidence = r.category_id, "rule", r.category_confidence
            t.suggested_category_id = None
            t.categorisation = r.categorisation
            outcome = "changed"

    if r.pair_with:
        link_pair(db, categoriser, t.id, r.pair_with, override_rule_assigned=include_rules)
    return outcome


def run_for_user(db, user_id, include_rules=False):
    # redact_names=False: this re-reads text that is already stored, so there is nothing new to code
    categoriser = Categoriser(db, user_id, track_batch=False, redact_names=False)  # rows are flushed as we go
    uncategorized_id = categoriser.ids.get("Uncategorized")
    rows = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id)
        .order_by(Transaction.transaction_date, Transaction.created_at)
        .all()
    )
    original = {t.id: t.category_id for t in rows}
    # pass 1: payee keys for everyone, so the repeat-payee check sees ALL the other payments
    for t in rows:
        if t.payee_key is None:
            t.payee_key = prepare(t.description_raw, t.amount).payee_key
    db.flush()

    outcomes, changes = Counter(), []
    for t in rows:
        r = categoriser.decide(
            account_id=t.account_id, description=t.description_raw, amount=t.amount,
            transaction_date=t.transaction_date, exclude_id=t.id, existing_pair_id=t.paired_transaction_id,
        )
        outcome = _apply(db, categoriser, t, r, uncategorized_id, include_rules, original[t.id])
        db.flush()
        outcomes[outcome] += 1
        if outcome == "changed":
            changes.append((categoriser.names_by_id.get(original[t.id]), categoriser.names_by_id.get(t.category_id), t.description_raw[:60]))
    return len(rows), outcomes, changes


def run_recategorize(include_rules=False, dry_run=False):
    db = SessionLocal()
    try:
        total = Counter()
        for (user_id,) in db.query(Account.user_id).distinct().all():
            n, outcomes, changes = run_for_user(db, user_id, include_rules)
            total.update(outcomes)
            for old, new, description in changes[:15]:
                print(f"  changed: {old or 'none'} -> {new}   {description}")
        words = {
            "assigned": "newly categorised", "suggested": "given a suggestion (does not count until you confirm it)",
            "unknown": "still unknown", "confirmed": "re-checked and agreed", "changed": "changed category",
            "kept_rule": "left as an earlier rule had it (engine not confident)", "kept_yours": "yours, untouched",
            "unchanged": "not in scope",
        }
        print(("DRY RUN: nothing was changed. " if dry_run else "") + f"Checked {sum(total.values())} transaction(s):")
        for key in words:
            if total[key]:
                print(f"  {total[key]:>5}  {words[key]}")
        if dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run_recategorize(include_rules="--rules" in sys.argv, dry_run="--dry-run" in sys.argv)