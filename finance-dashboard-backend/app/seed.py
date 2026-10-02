from .database import SessionLocal
from .models import Category, MerchantCategoryMap

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

MERCHANT_MAP = {
    "Groceries": ["NTUC", "FAIRPRICE", "COLD STORAGE", "SHENG SIONG", "GIANT SUPERMARKET", "DON DON DONKI", "REDMART"],
    "Dining": ["KOPI TIAM", "FOOD JUNCTION", "MCDONALD", "TOAST BOX", "YAKUN", "STARBUCKS"],
    "Delivery": ["GRABFOOD", "DELIVEROO", "FOODPANDA"],
    "Transport": ["SIMPLYGO", "TRANSITLINK", "GRAB", "COMFORTDELGRO", "TADA"],
    "Healthcare & Wellness": [
        "HOSPITAL", "CLINIC", "POLYCLINIC", "WATSONS", "GUARDIAN", "RAFFLES MEDICAL",
        "MINMED", "DENTAL", "FACIAL", "MASSAGE", "HAIRCUT", "SALON",
    ],
    "Housing & Utilities": [
        "SP SERVICES", "SP GROUP", "TEMBUSU", "KEPPEL ELECTRIC", "GENECO",
        "HDB", "MORTGAGE", "CONDO", "MAINTENANCE", "IKEA",
    ],
    "Telco": ["SINGTEL", "STARHUB", "M1", "SIMBA", "MYREPUBLIC", "GIGA", "GOMO", "CIRCLES.LIFE"],
    "Shopping": ["LAZADA", "SHOPEE", "AMAZON", "UNIQLO", "TAOBAO", "SHEIN", "COURTS"],
    "Savings & Investments": [
        "AIA", "PRUDENTIAL", "GREAT EASTERN", "MANULIFE", "INCOME INSURANCE", "SINGLIFE",
        "MOOMOO", "TIGER BROKERS", "SYFE", "STASHAWAY", "ENDOWUS", "INTERACTIVE BROKERS", "POEMS",
    ],
    "Entertainment": ["NETFLIX", "SPOTIFY", "DISNEY PLUS", "DISNEY+", "YOUTUBE PREMIUM", "AMAZON PRIME"],
    "Income": ["SALARY"],
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