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
        "children": ["Rent/Mortgage", "Utilities", "Maintenance & Furnishing"],
    },
    "Food": {
        "type": "expense",
        "children": ["Groceries", "Dining Out", "Coffee & Drinks", "Delivery"],
    },
    "Transport": {
        "type": "expense",
        "children": ["Public Transit", "Ride-hailing", "Fuel & Parking"],
    },
    "Education": {
        "type": "expense",
        "children": ["Tuition", "Courses", "Books & Supplies"],
    },
    "Healthcare": {
        "type": "expense",
        "children": ["Clinics", "Pharmacy", "Insurance", "Personal Care"],
    },
    "Shopping": {
        "type": "expense",
        "children": ["Clothing", "Tech", "General"],
    },
    "Entertainment": {
        "type": "expense",
        "children": ["Subscriptions", "Events", "Hobbies"],
    },
    "Income": {
        "type": "income",
        "children": ["Salary", "Freelance", "Dividends & Interest", "Other Income"],
    },
    "Transfers": {
        "type": "transfer",
        "children": ["Own Accounts", "Friends & Family"],
    },
    "Savings & Investments": {"type": "transfer", "children": []},
    "Uncategorized": {"type": "expense", "children": []},
}

# Bootstrap sample only: brand -> leaf category, chosen by hand, not from a dataset.
# It should grow from real statements and user corrections.
SEED_MERCHANT_MAP = {
    "NTUC FAIRPRICE": "Groceries",
    "COLD STORAGE": "Groceries",
    "SHENG SIONG": "Groceries",
    "GRAB": "Ride-hailing",  # ambiguous: GrabFood/GrabMart also show up as GRAB
    "COMFORTDELGRO": "Ride-hailing",
    "SBS TRANSIT": "Public Transit",
    "SMRT": "Public Transit",
    "NETFLIX": "Subscriptions",
    "SPOTIFY": "Subscriptions",
    "STARBUCKS": "Coffee & Drinks",
    "MCDONALDS": "Dining Out",
    "SP GROUP": "Utilities",
    "SINGTEL": "Utilities",
    "SHOPEE": "General",
    "LAZADA": "General",
    "IKEA": "Maintenance & Furnishing",
    "COURTS": "Maintenance & Furnishing",  # also sells electronics
    "UNIQLO": "Clothing",
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