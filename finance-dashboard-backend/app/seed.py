from .database import SessionLocal
from .models import Category, MerchantCategoryMap

# Two-level tree: parent -> children. `type` decides how a category is treated in
# summaries: income and expense count towards the monthly totals, transfer does not
# (moving money between own accounts, to savings, or to friends is not earning/spending).
# Children inherit their parent's type. Leaf names must be unique across the tree,
# because the merchant map below refers to leaves by name.
CATEGORY_TREE = {
    "Housing": {
        "type": "expense",
        "children": ["Rent/Mortgage", "Utilities"],
    },
    "Food": {
        "type": "expense",
        "children": ["Groceries", "Dining Out", "Delivery"],
    },
    "Transport": {"type": "expense", "children": []},
    "Education": {"type": "expense", "children": []},
    "Healthcare": {"type": "expense", "children": []},
    "Shopping": {"type": "expense", "children": []},
    "Entertainment": {"type": "expense", "children": []},
    "Income": {
        "type": "income",
        "children": ["Salary", "Dividends & Interest"],
    },
    "Transfers": {
        "type": "transfer",
        "children": ["Own Accounts", "Friends & Family"],
    },
    "Savings & Investments": {"type": "transfer", "children": []},
    "Uncategorized": {"type": "expense", "children": []},
}

# Bootstrap sample only: brand -> leaf category, chosen by hand, not from a dataset.
# It should grow from real statements and user corrections. Several merchants now point
# at a top-level category directly (e.g. Transport) since their old subcategory was cut.
SEED_MERCHANT_MAP = {
    "NTUC FAIRPRICE": "Groceries",
    "COLD STORAGE": "Groceries",
    "SHENG SIONG": "Groceries",
    "GRAB": "Transport",
    "COMFORTDELGRO": "Transport",
    "SBS TRANSIT": "Transport",
    "SMRT": "Transport",
    "NETFLIX": "Entertainment",
    "SPOTIFY": "Entertainment",
    "STARBUCKS": "Dining Out",
    "MCDONALDS": "Dining Out",
    "SP GROUP": "Utilities",
    "SINGTEL": "Utilities",
    "SHOPEE": "Shopping",
    "LAZADA": "Shopping",
    "IKEA": "Housing",
    "COURTS": "Shopping",
    "UNIQLO": "Shopping",
    "SALARY": "Salary",
}


def get_or_create_category(db, name, parent_id, category_type):
    existing = (
        db.query(Category)
        .filter(
            Category.name == name,
            Category.parent_category_id == parent_id,
            Category.user_id.is_(None),
        )
        .first()
    )
    if not existing:
        existing = Category(
            name=name,
            parent_category_id=parent_id,
            type=category_type,
            user_id=None,
            is_system_default=True,
        )
        db.add(existing)
        db.flush()  # populate existing.id without committing yet
    return existing


def run_seed():
    db = SessionLocal()
    try:
        leaf_ids = {}

        for parent_name, spec in CATEGORY_TREE.items():
            parent = get_or_create_category(db, parent_name, None, spec["type"])
            leaf_ids[parent_name] = parent.id
            for child_name in spec["children"]:
                child = get_or_create_category(db, child_name, parent.id, spec["type"])
                leaf_ids[child_name] = child.id

        for merchant_key, category_name in SEED_MERCHANT_MAP.items():
            existing = (
                db.query(MerchantCategoryMap)
                .filter(MerchantCategoryMap.merchant_key == merchant_key)
                .first()
            )
            if not existing:
                db.add(
                    MerchantCategoryMap(
                        merchant_key=merchant_key,
                        category_id=leaf_ids[category_name],
                        confidence=1.0,
                        source="seed_data",
                    )
                )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()