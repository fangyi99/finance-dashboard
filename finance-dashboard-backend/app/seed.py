from .database import SessionLocal
from .models import Category, MerchantCategoryMap
from .classify.library import MERCHANT_MAP  # the merchant keywords live with the other categorisation rules

CATEGORY_TREE = {
    "Food": {"type": "expense", "children": ["Groceries", "Dining", "Delivery"]},
    "Transport": {"type": "expense", "children": []},
    "Healthcare & Wellness": {"type": "expense", "children": []},
    "Housing & Utilities": {"type": "expense", "children": []},
    "Telco": {"type": "expense", "children": []},
    "Shopping": {"type": "expense", "children": []},
    "Entertainment": {"type": "expense", "children": []},
    "Income": {"type": "income", "children": []},
    "Transfers": {
        "type": "transfer",
        "children": ["Own Accounts", "Friends & Family", "Savings & Investments"],
    },
    "Uncategorized": {"type": "expense", "children": []},
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
        categories_by_name = {}

        for parent_name, spec in CATEGORY_TREE.items():
            parent = get_or_create_category(db, parent_name, None, spec["type"])
            categories_by_name[parent_name] = parent
            for child_name in spec["children"]:
                child = get_or_create_category(db, child_name, parent.id, spec["type"])
                categories_by_name[child_name] = child

        for category_name, keywords in MERCHANT_MAP.items():
            category = categories_by_name.get(category_name)
            if not category:
                print(f"Warning: '{category_name}' in MERCHANT_MAP isn't in CATEGORY_TREE, skipping.")
                continue

            for keyword in keywords:
                existing = (
                    db.query(MerchantCategoryMap)
                    .filter(MerchantCategoryMap.merchant_key == keyword)
                    .first()
                )
                if not existing:
                    db.add(
                        MerchantCategoryMap(
                            merchant_key=keyword,
                            category_id=category.id,
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