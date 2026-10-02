"""
One-off utility: re-runs categorization against transactions that are still
Uncategorized, for when the merchant map gains new entries after those transactions
were already created. Categorization only ever runs once, at creation time — nothing
automatically goes back and re-checks existing rows when the map improves.

Only touches transactions where category_source != 'user', so a correction you made
by hand is never silently overwritten by a later rule match.

Run with: python -m app.recategorize
"""

from .database import SessionLocal
from .models import Category, Transaction
from .categorization import categorize_transaction


def run_recategorize():
    db = SessionLocal()
    try:
        uncategorized_category = (
            db.query(Category)
            .filter(Category.name == "Uncategorized", Category.parent_category_id.is_(None))
            .first()
        )
        uncategorized_id = uncategorized_category.id if uncategorized_category else None

        candidates = (
            db.query(Transaction)
            .filter(
                Transaction.category_source != "user",
                (Transaction.category_id.is_(None))
                | (Transaction.category_id == uncategorized_id),
            )
            .all()
        )

        updated = 0
        for transaction in candidates:
            category_id, source, confidence, normalized = categorize_transaction(
                transaction.description_raw, db
            )
            if category_id is not None:
                transaction.category_id = category_id
                transaction.category_source = source
                transaction.category_confidence = confidence
                transaction.description_normalized = normalized
                updated += 1

        db.commit()
        print(f"Checked {len(candidates)} uncategorized transaction(s), updated {updated}.")
    finally:
        db.close()


if __name__ == "__main__":
    run_recategorize()