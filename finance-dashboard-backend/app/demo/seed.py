"""
Loads the sandbox dataset (data.py) into the database as ONE isolated demo user, so the app can switch to
it and every screen works unchanged.

    python -m app.demo.seed                      create or refresh the demo user
    python -m app.demo.seed --ground-truth FILE  write the labelled rows (no database needed)

What makes this a real demonstration rather than a pre-filled table: every row goes through the same
categoriser as a real import, so the sandbox shows what the pipeline genuinely does (some rows placed,
some only suggested, some unknown), own-account transfers get paired across accounts, two "corrections"
are made the way you would make them (which teach rules), and the recurring items on the Upcoming
widget come out of the real recurring detection.

Speed: against a database over the network, every round trip costs tens of milliseconds, so the build is
done in memory. The whole dataset is known up front, so the questions the categoriser would normally ask
the database ("is there an equal and opposite transfer in my other account?", "how many earlier payments
to this payee?") are answered from the rows decided so far, and the transactions go in as ONE insert. That
is about 30 statements instead of about 750. The decisions come from the same Categoriser code, and the
shared recipes in classify/service.py, so the result is identical.

Isolation: everything belongs to one fixed demo user. Resetting deletes only that user's rows, in an order
the foreign keys allow, and never touches anyone else's.
"""

import csv
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..classify.matching import find_phrase, tokenize
from ..classify.service import (
    PAIR_WINDOW_DAYS, PAIRABLE_CHANNELS, Categoriser, pairing_fields, pairing_protected, rule_phrase, user_rule_fields,
)
from ..database import SessionLocal
from ..models import (
    Account, Budget, CategorisationRule, Category, CategoryFeedback, RecurringRule,
    TabPreference, Transaction, User, WidgetPreference,
)
from ..recurring import PRESET_INTERVALS, TransactionIndex, detect_candidates, frequency_label, rule_schedule
from .data import SALARY, generate, ground_truth

DEMO_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "finance-dashboard/sandbox-demo-user")
DEMO_EMAIL = "sandbox-demo@example.invalid"
STALE_AFTER_DAYS = 5  # "start" refreshes the data when the newest transaction is older than this

# So the demo user lands on a populated dashboard instead of being sent through onboarding.
WIDGETS = ["balance_summary", "monthly_summary", "top_expenses", "upcoming_transactions", "budgets"]
TABS = ["dashboard", "accounts", "cash_flow", "budget", "settings"]

# Two corrections made "by hand", so the sandbox shows learning: one hawker and the monthly allowance are
# filed by the user once, and the rule that teaches is applied to every other one. The other hawker is
# deliberately left alone, so the sandbox also shows suggestions waiting for a confirmation.
TAUGHT = [("TAN AH KOW", "Dining"), ("TAN SIEW HONG ALLOWANCE", "Friends & Family")]

# Which detected recurring items to approve, and what to call them. The detector's own labels come out of
# the old description cleaner, which doesn't understand real statement lines ("To Demo User Tf"), and it
# also finds things that aren't worth tracking (a transfer to your own account, a cash withdrawal). A person
# approving suggestions would pick the meaningful ones and rename them, which is what this does.
# (text the detected pattern must contain, name shown)
RECURRING_APPROVED = [
    ("LIM KOK WEE", "Rent"), ("SP SERVICES", "SP utilities"), ("SINGTEL", "Singtel mobile"), ("NETFLIX", "Netflix"),
    ("SPOTIFY", "Spotify"), ("AIA SINGAPORE", "AIA insurance"), ("MOOMOO", "Moomoo investing"),
    ("SYFE", "Syfe investing"), ("TAN SIEW HONG", "Allowance"), ("INTEREST EARNED", "Savings interest"),
]


def wipe_demo(db) -> None:
    """Deletes everything the demo user owns, children before parents."""
    account_ids = [a for (a,) in db.query(Account.id).filter(Account.user_id == DEMO_USER_ID)]
    if account_ids:
        tx_ids = db.query(Transaction.id).filter(Transaction.account_id.in_(account_ids))
        db.query(CategoryFeedback).filter(CategoryFeedback.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
        db.query(Transaction).filter(Transaction.account_id.in_(account_ids)).delete(synchronize_session=False)
    for model in (RecurringRule, Budget, CategorisationRule, WidgetPreference, TabPreference):
        db.query(model).filter(model.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(Account).filter(Account.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(User).filter(User.id == DEMO_USER_ID).delete(synchronize_session=False)
    db.flush()


class _InMemoryCategoriser(Categoriser):
    """
    Decides exactly as Categoriser does, but answers "what else is there?" from the rows decided so far
    (held as the dicts that will be inserted) instead of asking the database.
    """

    def __init__(self, db, user_id):
        super().__init__(db, user_id, track_batch=False)
        self.rows = []

    def _counterpart(self, f, account_id, amount, tx_date, exclude_id, existing_pair_id):
        if f.channel not in PAIRABLE_CHANNELS or amount == 0:
            return None
        best = None
        for row in self.rows:  # in the order they were decided, so an equal gap goes to the earlier one
            gap = abs((row["transaction_date"] - tx_date).days)
            if (row["account_id"] == account_id or row["amount"] != -amount or row["paired_transaction_id"] is not None
                    or row["_channel"] not in PAIRABLE_CHANNELS or gap > PAIR_WINDOW_DAYS):
                continue
            if best is None or gap < best[0]:
                best = (gap, row)
        return SimpleNamespace(id=best[1]["id"]) if best else None

    def _history(self, f, exclude_id):
        if not f.payee_key or f.direction != "out":
            return {}
        return {f.payee_key: [abs(r["amount"]) for r in self.rows if r["payee_key"] == f.payee_key and r["amount"] < 0]}


def _teach(categoriser, rows, feedback, rules, phrase: str, category_name: str) -> None:
    """You correct one transaction by hand; that teaches a rule, applied to every other one. (In memory.)"""
    category_id = categoriser.ids[category_name]
    candidates = [x for x in rows if phrase.lower() in (x["payee_key"] or "").lower()]
    if not candidates:
        return
    t = min(candidates, key=lambda x: x["transaction_date"])
    t.update(category_id=category_id, category_source="user", category_confidence=None, suggested_category_id=None)
    t["categorisation"] = {
        "engine": 1, "status": "assigned", "source": "user", "confidence": 1.0, "type": t["txn_type"],
        "suggested_name": None, "candidates": [[category_name, 1.0]],
        "evidence": [{"signal": "user_choice", "category": category_name, "points": 1.0, "detail": "you chose this category"}],
    }
    feedback.append({"transaction_id": t["id"], "description_normalized": t["description_normalized"], "corrected_category_id": category_id})
    learned = rule_phrase(t["payee_key"])
    if not learned:
        return
    rules.append({"phrase": learned, "category_id": category_id})
    words = tokenize(learned)
    for x in rows:  # the same test apply_rule_to_past uses
        if x is t or x["category_source"] == "user" or find_phrase(tokenize(x["payee_key"] or ""), words) is None:
            continue
        if x["category_id"] == category_id and x["suggested_category_id"] is None:
            continue
        x.update(user_rule_fields(category_id, category_name, x["txn_type"], learned))


def reset_demo(db, today: date = None) -> dict:
    """Rebuilds the demo user from scratch, relative to `today`. Commits."""
    today = today or date.today()
    wipe_demo(db)
    data = generate(today)
    now = datetime.now(timezone.utc)

    db.add(User(id=DEMO_USER_ID, email=DEMO_EMAIL))
    accounts = {}
    for spec in data.accounts:
        total = sum((r.amount for r in data.rows if r.account == spec.key), Decimal(0))
        accounts[spec.key] = Account(
            id=uuid.uuid4(), user_id=DEMO_USER_ID, source=spec.source, display_name=spec.display_name,
            institution_name=spec.institution_name, currency=spec.currency,
            balance=spec.opening_balance + total, balance_as_of=data.end, last_synced_at=now,
        )
    db.add_all(accounts.values())
    db.flush()

    categoriser = _InMemoryCategoriser(db, DEMO_USER_ID)
    ids, rows, stripe_orders = categoriser.ids, categoriser.rows, 0
    for r in data.rows:
        account = accounts[r.account]
        resolved = categoriser.decide(account_id=account.id, description=r.description, amount=r.amount, transaction_date=r.day)
        row = {
            "id": uuid.uuid4(), "account_id": account.id, "description_raw": r.description, "amount": r.amount,
            "currency": account.currency, "transaction_date": r.day, **resolved.fields(),
            "external_id": None, "notes": None, "is_recurring": False, "recurring_rule_id": None,
            "_channel": resolved.decision.features.channel,  # the leading underscore keeps it out of the insert
        }
        if r.forced_category:  # Stripe's own feed says what these are: customers paying for orders
            stripe_orders += 1
            row.update(
                external_id=f"pi_demo_{stripe_orders:04d}", category_id=ids[r.forced_category], category_source="rule",
                category_confidence=Decimal("1.000"), suggested_category_id=None, txn_type=r.true_type,
                categorisation={
                    "engine": 1, "status": "assigned", "source": "demo", "confidence": 1.0, "type": r.true_type,
                    "suggested_name": None, "candidates": [[r.forced_category, 1.0]],
                    "evidence": [{"signal": "payment_gateway", "category": r.forced_category, "points": 1.0, "detail": "a payment received through Stripe"}],
                },
            )
        if resolved.pair_with:  # what link_pair does, on the rows held in memory
            partner = next(x for x in rows if x["id"] == resolved.pair_with)
            partner["paired_transaction_id"] = row["id"]
            if ids.get("Own Accounts") and not pairing_protected(partner["category_source"], partner["categorisation"]):
                partner.update(pairing_fields(ids["Own Accounts"]))
        rows.append(row)

    feedback, rules = [], []
    for phrase, category_name in TAUGHT:
        _teach(categoriser, rows, feedback, rules, phrase, category_name)

    # ONE insert for every transaction. (A transfer's two halves point at each other; that's fine inside a
    # single statement, because the database checks the link once the whole statement is in.)
    insertable = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    db.execute(pg_insert(Transaction.__table__).values(insertable))
    db.add_all([CategoryFeedback(**f) for f in feedback] + [CategorisationRule(user_id=DEMO_USER_ID, **r) for r in rules])

    # Recurring items: from the real detection, approved the way you'd approve a suggestion.
    recent = [SimpleNamespace(**row) for row in insertable]
    index = TransactionIndex(recent)
    recurring = 0
    for c in detect_candidates(recent, today):
        label = next((name for needle, name in RECURRING_APPROVED if needle in c.pattern), None)
        if c.frequency != "monthly" or label is None:
            continue
        rule = RecurringRule(
            user_id=DEMO_USER_ID, description=label, merchant_pattern=c.pattern, expected_amount=c.expected_amount,
            amount_tolerance_pct=c.tolerance, category_id=c.category_id, account_id=c.account_id, is_active=True,
        )
        interval = PRESET_INTERVALS[c.frequency]
        rule.interval_count, rule.interval_unit = interval.count, interval.unit
        rule.frequency = frequency_label(interval.count, interval.unit)
        schedule = rule_schedule(rule, index, today)
        rule.last_occurred_date, rule.next_due_date = schedule["last_occurred_date"], schedule["next_due_date"]
        db.add(rule)
        recurring += 1

    # Salary: added by hand, like the Add Recurring form. The detector can't see it (the reference changes
    # every month), and a hand-made rule runs on its schedule alone.
    salaries = sorted(r.day for r in data.rows if r.true_type == "income" and r.description.startswith("Salary"))
    if salaries:
        salary = RecurringRule(
            user_id=DEMO_USER_ID, description="Salary", merchant_pattern=f"manual:{uuid.uuid4().hex}",
            expected_amount=SALARY, amount_tolerance_pct=Decimal("0.05"),
            category_id=ids["Income"], account_id=accounts["posb"].id, is_active=True,
            next_due_date=salaries[-1],
        )
        salary.interval_count, salary.interval_unit, salary.frequency = 1, "month", "monthly"
        schedule = rule_schedule(salary, index, today)
        salary.last_occurred_date, salary.next_due_date = schedule["last_occurred_date"], schedule["next_due_date"]
        db.add(salary)
        recurring += 1

    for b in data.budgets:
        db.add(Budget(user_id=DEMO_USER_ID, name=b.name, amount=b.amount, category_id=ids[b.category] if b.category else None))
    for order, key in enumerate(WIDGETS):
        db.add(WidgetPreference(user_id=DEMO_USER_ID, widget_key=key, is_enabled=True, display_order=order))
    for order, key in enumerate(TABS):
        db.add(TabPreference(user_id=DEMO_USER_ID, tab_key=key, is_enabled=True, display_order=order))
    db.commit()
    return {**status(db), "recurring_rules": recurring, "budgets": len(data.budgets)}


def status(db) -> dict:
    user = db.get(User, DEMO_USER_ID)
    if user is None:
        return {"user_id": str(DEMO_USER_ID), "seeded": False, "transactions": 0, "accounts": 0, "latest_transaction": None}
    count, latest = (
        db.query(func.count(Transaction.id), func.max(Transaction.transaction_date))
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == DEMO_USER_ID)
        .one()
    )
    return {
        "user_id": str(DEMO_USER_ID), "seeded": True, "transactions": count,
        "accounts": db.query(func.count(Account.id)).filter(Account.user_id == DEMO_USER_ID).scalar(),
        "latest_transaction": latest.isoformat() if latest else None,
    }


def ensure_demo(db, today: date = None):
    """Seeds the demo if it's missing, or refreshes it if it has gone stale. Returns (status, refreshed)."""
    today = today or date.today()
    current = status(db)
    latest = date.fromisoformat(current["latest_transaction"]) if current["latest_transaction"] else None
    if not current["seeded"] or latest is None or latest < today - timedelta(days=STALE_AFTER_DAYS):
        return reset_demo(db, today), True
    return current, False


def write_ground_truth(path: str, today: date = None) -> int:
    rows = ground_truth(today or date.today())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["account", "description", "amount", "true_category", "true_type"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    if "--ground-truth" in sys.argv:
        target = sys.argv[sys.argv.index("--ground-truth") + 1]
        print(f"Wrote {write_ground_truth(target)} labelled rows to {target}")
    else:
        db = SessionLocal()
        try:
            print(reset_demo(db))
        finally:
            db.close()