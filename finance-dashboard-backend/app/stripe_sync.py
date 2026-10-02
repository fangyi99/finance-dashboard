"""
Pulls succeeded payments from Stripe into a Stripe-backed account.

Unlike CSV/PDF import, this gets called repeatedly against a live account, so it has
to be safe to run twice. Rather than checking each payment against the database one
at a time (one round-trip per payment — slow, and racy if two syncs ever overlapped),
the whole batch is sent as a single INSERT ... ON CONFLICT DO NOTHING, relying on the
unique constraint on `external_id` to atomically skip anything already imported. One
round-trip for the whole batch, and the database itself guarantees no duplicates can
slip through even under concurrent syncs.

Categorization is also different on purpose. The merchant-matching pipeline built for
CSV/PDF is designed for spending descriptions ("NTUC FAIRPRICE"); a Stripe payment
description ("Website design - Client A") isn't that kind of text, so running it
through that pipeline would just produce noise. Every synced payment is instead
assigned directly to the Income category.
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import stripe
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import Account, Category, Transaction

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def _get_income_category(db: Session) -> Category | None:
    return (
        db.query(Category)
        .filter(Category.name == "Income", Category.parent_category_id.is_(None))
        .first()
    )


def sync_stripe_account(account: Account, db: Session) -> dict:
    if account.source != "stripe":
        raise ValueError("Account is not a Stripe-backed account")

    list_kwargs = {"limit": 100}
    if account.last_synced_at:
        # Keeps each sync fast as history grows; ON CONFLICT is still the real
        # safety net against duplicates, this is just about not re-scanning everything.
        list_kwargs["created"] = {"gte": int(account.last_synced_at.timestamp())}

    payment_intents = stripe.PaymentIntent.list(**list_kwargs)
    income_category = _get_income_category(db)

    rows = []
    for pi in payment_intents.auto_paging_iter():
        if pi.status != "succeeded":
            continue
        description = pi.description or "Stripe payment"
        rows.append(
            {
                "id": uuid.uuid4(),
                "account_id": account.id,
                "description_raw": description,
                "description_normalized": description.upper(),
                "amount": Decimal(pi.amount) / 100,  # Stripe amounts are in the smallest unit
                "currency": pi.currency.upper(),
                "transaction_date": datetime.fromtimestamp(pi.created, tz=timezone.utc).date(),
                "category_id": income_category.id if income_category else None,
                "category_source": "rule",
                "external_id": pi.id,
            }
        )

    imported = 0
    if rows:
        stmt = pg_insert(Transaction.__table__).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"])
        result = db.execute(stmt)
        imported = result.rowcount  # rows actually inserted; conflicts aren't counted

    skipped = len(rows) - imported

    # Live balance from Stripe itself, rather than summing transactions ourselves —
    # more accurate, and reflects Stripe's own pending/available distinction.
    balance = stripe.Balance.retrieve()
    available = next(
        (b for b in balance.available if b.currency == account.currency.lower()), None
    )
    if available:
        account.balance = Decimal(available.amount) / 100
        account.balance_as_of = datetime.now(timezone.utc).date()

    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()

    return {"imported": imported, "skipped": skipped}