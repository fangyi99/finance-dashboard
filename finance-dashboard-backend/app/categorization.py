import re
from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session
from .models import MerchantCategoryMap, Category

# Common prefixes/noise on SG bank transaction descriptions
NOISE_PATTERNS = [
    r"\bPAYLAH\*?\b", r"\bPAYNOW\b", r"\bNETS\b", r"\bGIRO\b",
    r"\bSQ\s?\*", r"\bPAYPAL\s?\*", r"#?\d{3,}",  # trailing reference numbers
]

def normalize_description(raw: str) -> str:
    text = raw.upper().strip()
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def categorize_transaction(description_raw: str, db: Session, fuzzy_threshold: int = 85):
    """
    Returns (category_id, category_source, confidence, normalized_description)
    category_id is None if no match found above threshold.
    """
    normalized = normalize_description(description_raw)

    # 1. Exact match
    exact = db.query(MerchantCategoryMap).filter(
        MerchantCategoryMap.merchant_key == normalized
    ).first()
    if exact:
        return exact.category_id, "rule", float(exact.confidence), normalized

    # 2. Fuzzy match against all known merchant keys
    all_mappings = db.query(MerchantCategoryMap).all()
    if not all_mappings:
        return None, "rule", None, normalized

    choices = {m.merchant_key: m for m in all_mappings}
    result = process.extractOne(
        normalized, choices.keys(), scorer=fuzz.token_sort_ratio
    )

    if result:
        matched_key, score, _ = result
        if score >= fuzzy_threshold:
            mapping = choices[matched_key]
            confidence = round(score / 100, 3)
            return mapping.category_id, "rule", confidence, normalized

    # 3. No match
    return None, "rule", None, normalized