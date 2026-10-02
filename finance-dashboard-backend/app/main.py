from decimal import Decimal
import uuid
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from .database import get_db
from .models import CategoryFeedback, Transaction, Account, Category, CategoryVisibility
from .schemas import TransactionCreate, TransactionDetailOut, TransactionOut, TransactionUpdate, WidgetPreferencesBulkUpdate, WidgetPreferenceOut, MonthlySummaryOut, TabPreferencesBulkUpdate, TabPreferenceOut, CSVImportResult
from .models import WidgetPreference, TabPreference
from io import StringIO
from datetime import date, datetime
from calendar import monthrange
from sqlalchemy import func, or_
from .categorization import categorize_transaction
from .routers import accounts, categories
from collections import defaultdict
from typing import Literal, Optional

app = FastAPI()

app.include_router(accounts.router)
app.include_router(categories.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev; restrict this before any real deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOCKED_TABS = {"accounts", "settings"}

@app.get("/")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}

@app.post("/transactions", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    category_id, category_source, confidence, normalized = categorize_transaction(
        payload.description_raw, db
    )

    transaction = Transaction(
        **payload.model_dump(exclude={"category_id"}),  # ignore any client-sent category_id
        category_id=category_id,
        category_source=category_source,
        category_confidence=confidence,
        description_normalized=normalized,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction

@app.get("/transactions", response_model=List[TransactionOut])
def list_transactions(db: Session = Depends(get_db)):
    return db.query(Transaction).order_by(Transaction.transaction_date.desc()).all()

@app.put("/widget-preferences", response_model=List[WidgetPreferenceOut])
def set_widget_preferences(payload: WidgetPreferencesBulkUpdate, db: Session = Depends(get_db)):
    # wipe and replace — simplest approach for a one-time setup screen
    db.query(WidgetPreference).filter(WidgetPreference.user_id == payload.user_id).delete()

    new_prefs = []
    for pref in payload.preferences:
        wp = WidgetPreference(user_id=payload.user_id, **pref.model_dump())
        db.add(wp)
        new_prefs.append(wp)

    db.commit()
    for wp in new_prefs:
        db.refresh(wp)
    return new_prefs

@app.get("/widget-preferences/{user_id}", response_model=List[WidgetPreferenceOut])
def get_widget_preferences(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(WidgetPreference)
        .filter(WidgetPreference.user_id == user_id)
        .order_by(WidgetPreference.display_order)
        .all()
    )

@app.get("/summary/monthly/{user_id}", response_model=MonthlySummaryOut)
def get_monthly_summary(user_id: uuid.UUID, db: Session = Depends(get_db)):
    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = today.replace(day=monthrange(today.year, today.month)[1])

    results = (
        db.query(Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date.between(start_of_month, end_of_month),
        )
        .all()
    )

    income = sum(amt for (amt,) in results if amt > 0)
    expenses = sum(abs(amt) for (amt,) in results if amt < 0)

    return MonthlySummaryOut(
        income=income,
        expenses=expenses,
        savings=income - expenses,
        month=today.strftime("%Y-%m"),
    )


@app.get("/transactions/top-expenses/{user_id}", response_model=List[TransactionOut])
def get_top_expenses(user_id: uuid.UUID, limit: int = 5, db: Session = Depends(get_db)):
    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = today.replace(day=monthrange(today.year, today.month)[1])

    return (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date.between(start_of_month, end_of_month),
            Transaction.amount < 0,
        )
        .order_by(Transaction.amount.asc())  # most negative first = biggest expense
        .limit(limit)
        .all()
    )

@app.put("/tab-preferences", response_model=List[TabPreferenceOut])
def set_tab_preferences(payload: TabPreferencesBulkUpdate, db: Session = Depends(get_db)):
    db.query(TabPreference).filter(TabPreference.user_id == payload.user_id).delete()

    new_prefs = []
    for pref in payload.preferences:
        is_enabled = True if pref.tab_key in LOCKED_TABS else pref.is_enabled
        tp = TabPreference(
            user_id=payload.user_id,
            tab_key=pref.tab_key,
            is_enabled=is_enabled,
            display_order=pref.display_order,
        )
        db.add(tp)
        new_prefs.append(tp)

    db.commit()
    for tp in new_prefs:
        db.refresh(tp)
    return new_prefs


@app.get("/tab-preferences/{user_id}", response_model=List[TabPreferenceOut])
def get_tab_preferences(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(TabPreference)
        .filter(TabPreference.user_id == user_id)
        .order_by(TabPreference.display_order)
        .all()
    )

@app.post("/transactions/import-csv", response_model=CSVImportResult)
async def import_csv(
    account_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    try:
        df = pd.read_csv(StringIO(contents.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    # Expected columns for now — this is your "generic" format.
    # Bank-specific column mapping can be added later as separate presets.
    required_cols = {"date", "description", "amount"}
    df.columns = [c.strip().lower() for c in df.columns]
    if not required_cols.issubset(set(df.columns)):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: {required_cols}. Found: {list(df.columns)}"
        )

    imported = 0
    skipped = 0
    errors = []

    for i, row in df.iterrows():
        try:
            amount = float(str(row["amount"]).replace(",", "").replace("$", ""))
            tx_date = pd.to_datetime(row["date"]).date()
            description = str(row["description"]).strip()

            category_id, category_source, confidence, normalized = categorize_transaction(description, db)

            transaction = Transaction(
                account_id=account_id,
                description_raw=description,
                description_normalized=normalized,
                amount=amount,
                transaction_date=tx_date,
                category_id=category_id,
                category_source=category_source,
                category_confidence=confidence,
            )
            db.add(transaction)
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"Row {i + 2}: {e}")

    db.commit()
    return CSVImportResult(imported_count=imported, skipped_count=skipped, errors=errors[:10])

@app.get("/summary/category-breakdown/{user_id}")
def category_breakdown(
    user_id: uuid.UUID,
    type: Literal["income", "expense"] = "expense",
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    hidden_ids = {
        row.category_id
        for row in db.query(CategoryVisibility.category_id).filter(
            CategoryVisibility.user_id == user_id
        )
    }
    all_categories = {c.id: c for c in db.query(Category).all()}

    # Resolved once so both "no category at all" and "literally assigned to the
    # Uncategorized row" (e.g. via a deleted category's fallback) land in the SAME
    # bucket with a real, clickable UUID — rather than one synthetic key and one real
    # one that could silently show as two separate "Uncategorized" rows.
    uncategorized_category = next(
        (c for c in all_categories.values() if c.name == "Uncategorized" and c.parent_category_id is None),
        None,
    )
    uncategorized_key = str(uncategorized_category.id) if uncategorized_category else "uncategorized"

    # A transfer-type category has no fixed tab — a transaction under it shows on
    # Expense or Income based on its own amount sign (same treatment as a fully
    # uncategorized transaction, just scoped to categories whose type is "transfer").
    if type == "expense":
        type_filter = (Category.type == "expense") | (
            (Category.type == "transfer") & (Transaction.amount < 0)
        )
    else:
        type_filter = (Category.type == "income") | (
            (Category.type == "transfer") & (Transaction.amount > 0)
        )

    rows = (
        db.query(Transaction.amount, Transaction.category_id)
        .join(Account, Transaction.account_id == Account.id)
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Account.user_id == user_id,
            type_filter,
            Transaction.transaction_date.between(start, end),
        )
        .all()
    )

    sign_filter = Transaction.amount < 0 if type == "expense" else Transaction.amount > 0
    uncategorized_rows = (
        db.query(Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.category_id.is_(None),
            Transaction.transaction_date.between(start, end),
            sign_filter,
        )
        .all()
    )

    totals = defaultdict(Decimal)
    names = {}

    for amount, cat_id in rows:
        category = all_categories.get(cat_id)
        top_id = category.parent_category_id or cat_id
        top = all_categories.get(top_id)
        bucket_key = (
            "others" if (cat_id in hidden_ids or top_id in hidden_ids) else str(top_id)
        )
        bucket_name = "Others" if bucket_key == "others" else (top.name if top else "Uncategorized")
        totals[bucket_key] += abs(amount)
        names[bucket_key] = bucket_name

    for (amount,) in uncategorized_rows:
        totals[uncategorized_key] += abs(amount)
        names[uncategorized_key] = "Uncategorized"

    return [
        {"category_id": key, "category_name": names[key], "total": totals[key]}
        for key in totals
    ]

@app.get("/summary/category-detail/{user_id}")
def category_detail(
    user_id: uuid.UUID,
    category_id: uuid.UUID,
    type: Literal["expense", "income"] = "expense",
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    children = db.query(Category).filter(Category.parent_category_id == category_id).all()
    matching_ids = [category_id] + [c.id for c in children]

    uncategorized = (
        db.query(Category)
        .filter(Category.name == "Uncategorized", Category.parent_category_id.is_(None))
        .first()
    )
    include_null = bool(uncategorized and category_id == uncategorized.id)

    base_filter = [
        Account.user_id == user_id,
        Transaction.transaction_date.between(start, end),
    ]
    id_filter = (
        or_(Transaction.category_id.in_(matching_ids), Transaction.category_id.is_(None))
        if include_null
        else Transaction.category_id.in_(matching_ids)
    )

    # Children always inherit the parent's type, so checking the parent once covers
    # the whole group — if it's a transfer-type category, only the transactions whose
    # sign matches the tab being viewed from belong to this total (see category_breakdown).
    extra_filters = []
    if category.type == "transfer":
        extra_filters.append(Transaction.amount < 0 if type == "expense" else Transaction.amount > 0)

    rows = (
        db.query(Transaction.amount, Transaction.category_id)
        .join(Account, Transaction.account_id == Account.id)
        .filter(*base_filter, id_filter, *extra_filters)
        .all()
    )

    total = sum(abs(amount) for amount, _ in rows)

    child_totals: dict = {c.id: Decimal(0) for c in children}
    for amount, cat_id in rows:
        if cat_id in child_totals:
            child_totals[cat_id] += abs(amount)

    subcategories = [
        {"category_id": c.id, "category_name": c.name, "total": child_totals[c.id]}
        for c in children
    ]

    recent = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(*base_filter, id_filter, *extra_filters)
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "category_id": category.id,
        "category_name": category.name,
        "total": total,
        "subcategories": subcategories,
        "recent_transactions": [TransactionOut.model_validate(t) for t in recent],
    }

@app.get("/transactions/{user_id}", response_model=List[TransactionOut])
def list_transactions_for_user(
    user_id: uuid.UUID,
    account_id: Optional[uuid.UUID] = None,
    category_id: Optional[uuid.UUID] = None,
    type: Optional[Literal["expense", "income"]] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.user_id == user_id)
    )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        # category_breakdown rolls transactions up to their TOP-LEVEL category (e.g.
        # "Food" aggregates Groceries + Dining Out + Delivery), so when the filter is a
        # parent category, match it plus all of its children too — no transaction is
        # ever tagged with the parent itself, only with a specific child.
        matching_ids = [category_id]
        filtered_category = db.get(Category, category_id)
        if filtered_category and filtered_category.parent_category_id is None:
            child_ids = [
                c.id for c in db.query(Category.id).filter(Category.parent_category_id == category_id)
            ]
            matching_ids.extend(child_ids)

        uncategorized = (
            db.query(Category)
            .filter(Category.name == "Uncategorized", Category.parent_category_id.is_(None))
            .first()
        )
        if uncategorized and category_id == uncategorized.id:
            # "Uncategorized" covers both a transaction literally assigned to that row
            # and one with no category at all — see category_breakdown for why these
            # are treated as the same bucket.
            query = query.filter(
                or_(Transaction.category_id.in_(matching_ids), Transaction.category_id.is_(None))
            )
        else:
            query = query.filter(Transaction.category_id.in_(matching_ids))

        # A transfer-type category has no fixed tab (see category_breakdown) — when
        # drilling in from a specific tab, only that tab's matching-sign transactions
        # belong here, otherwise the list wouldn't match the total it was reached from.
        if filtered_category and filtered_category.type == "transfer" and type:
            query = query.filter(
                Transaction.amount < 0 if type == "expense" else Transaction.amount > 0
            )
    if year and month:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        query = query.filter(Transaction.transaction_date.between(start, end))
    elif year:
        query = query.filter(func.extract("year", Transaction.transaction_date) == year)

    return (
        query.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .all()
    )

@app.get("/transactions/by-id/{transaction_id}", response_model=TransactionDetailOut)
def get_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    category_name = None
    if transaction.category_id:
        category = db.get(Category, transaction.category_id)
        category_name = category.name if category else None

    return TransactionDetailOut(
        **TransactionOut.model_validate(transaction).model_dump(),
        category_name=category_name,
    )


@app.patch("/transactions/{transaction_id}", response_model=TransactionDetailOut)
def update_transaction(
    transaction_id: uuid.UUID, payload: TransactionUpdate, db: Session = Depends(get_db)
):
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    data = payload.model_dump(exclude_unset=True)

    if "category_id" in data and data["category_id"] is not None:
        new_category_id = data["category_id"]
        category = db.get(Category, new_category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        account = db.get(Account, transaction.account_id)
        if category.user_id not in (None, account.user_id):
            raise HTTPException(status_code=403, detail="That category isn't available to you")

        if transaction.category_id != new_category_id:
            # This is the actual ML feedback signal: a real user correction, distinct
            # from whatever the rule-matcher or a future classifier guessed.
            db.add(
                CategoryFeedback(
                    transaction_id=transaction.id,
                    description_normalized=transaction.description_normalized,
                    corrected_category_id=new_category_id,
                )
            )
        transaction.category_id = new_category_id
        transaction.category_source = "user"
        transaction.category_confidence = None

    if "notes" in data:
        transaction.notes = data["notes"]

    db.commit()
    db.refresh(transaction)

    category_name = None
    if transaction.category_id:
        category = db.get(Category, transaction.category_id)
        category_name = category.name if category else None

    return TransactionDetailOut(
        **TransactionOut.model_validate(transaction).model_dump(),
        category_name=category_name,
    )