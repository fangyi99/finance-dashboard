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
from .schemas import RecurringManualCreate, TransactionCreate, TransactionDetailOut, TransactionOut, TransactionUpdate, WidgetPreferencesBulkUpdate, WidgetPreferenceOut, MonthlySummaryOut, TabPreferencesBulkUpdate, TabPreferenceOut, CSVImportResult
from .models import WidgetPreference, TabPreference
from io import StringIO
from datetime import date, datetime, timezone
from calendar import monthrange
from sqlalchemy import func, or_, case, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .categorization import categorize_transaction
from .routers import accounts, categories, budgets
from collections import defaultdict
from typing import Literal, Optional
from .pdf_parser import (
    StatementParseError, extract_layout_pages, make_external_id,
    parse_layout_pages, parse_statement,
)
from datetime import timedelta
from .models import RecurringRule
from .schemas import RecurringCreate, RecurringFromTransaction, RecurringUpdate
from .recurring import (
    LOOKBACK_DAYS, PRESET_INTERVALS, TransactionIndex, description_key, detect_candidates, frequency_label, rule_schedule, suggest_label,
)

app = FastAPI()

app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(budgets.router)

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

@app.post("/statements/preview")
async def preview_statement(file: UploadFile = File(...), include_text: bool = False):
    """
    Parses a statement PDF and returns what was found WITHOUT saving anything — for trying
    a real statement safely. include_text=true also returns the extracted layout text, which
    is what to look at (and redact before sharing: it contains names, addresses and account
    numbers) if a statement doesn't parse the way it should.
    """
    data = await file.read()
    try:
        pages = extract_layout_pages(data)
    except StatementParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    response = {"ok": True, "error": None}
    try:
        result = parse_layout_pages(pages)
    except StatementParseError as e:
        # Still return the text in this case — it's exactly what's needed to see why.
        response = {"ok": False, "error": str(e)}
        if include_text:
            response["layout_text"] = pages
        return response

    response.update(
        {
            "bank": result.bank,
            "account_number": result.account_number,
            "statement_end": result.statement_end.isoformat() if result.statement_end else None,
            "opening_balance": str(result.opening_balance) if result.opening_balance is not None else None,
            "closing_balance": str(result.closing_balance) if result.closing_balance is not None else None,
            "computed_closing_balance": (
                str(result.computed_closing_balance) if result.computed_closing_balance is not None else None
            ),
            "reconciled": result.reconciled,
            "totals_match": result.totals_match,
            "warnings": result.warnings,
            "transactions": [
                {
                    "date": t.transaction_date.isoformat(),
                    "description": t.description,
                    "amount": str(t.amount),
                    "balance_after": str(t.balance_after) if t.balance_after is not None else None,
                }
                for t in result.transactions
            ],
        }
    )
    if include_text:
        response["layout_text"] = pages
    return response


@app.post("/accounts/{account_id}/import-statement")
async def import_statement(
    account_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.source != "pdf_import":
        raise HTTPException(status_code=400, detail="This account isn't set up for e-statement imports")

    data = await file.read()
    try:
        result = parse_statement(data)
    except StatementParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not result.transactions:
        raise HTTPException(status_code=422, detail="No transactions were found in this statement.")

    # A statement that doesn't add up (or can't be checked) is refused rather than imported
    # with a warning: a misread withdrawal/deposit would quietly corrupt balances and
    # summaries, which is worse than a clear "nothing was imported".
    if result.reconciled is not True:
        reason = result.warnings[-1] if result.warnings else "It couldn't be checked against its balances."
        raise HTTPException(
            status_code=422,
            detail=f"This statement didn't add up, so nothing was imported. {reason}",
        )

    rows = []
    seen = defaultdict(int)  # tells apart genuinely identical rows within one statement
    for t in result.transactions:
        seen[(t.transaction_date, t.amount, t.description)] += 1
        category_id, category_source, confidence, normalized = categorize_transaction(t.description, db)
        rows.append(
            {
                "id": uuid.uuid4(),
                "account_id": account.id,
                "description_raw": t.description,
                "description_normalized": normalized,
                "amount": t.amount,
                "currency": account.currency,
                "transaction_date": t.transaction_date,
                "category_id": category_id,
                "category_source": category_source,
                "category_confidence": confidence,
                "external_id": make_external_id(
                    account.id, t, seen[(t.transaction_date, t.amount, t.description)]
                ),
            }
        )

    # One batched insert; the unique external_id makes re-importing the same statement a
    # no-op instead of duplicating every row (same approach as the Stripe sync).
    stmt = pg_insert(Transaction.__table__).values(rows).on_conflict_do_nothing(index_elements=["external_id"])
    imported = db.execute(stmt).rowcount
    skipped = len(rows) - imported

    # Only move the balance forward in time: importing an older statement later (e.g.
    # catching up on past months) must not overwrite a newer balance with a stale one.
    if result.closing_balance is not None and result.statement_end is not None:
        if account.balance_as_of is None or result.statement_end >= account.balance_as_of:
            account.balance = result.closing_balance
            account.balance_as_of = result.statement_end
    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "closing_balance": str(result.closing_balance),
        "statement_end": result.statement_end.isoformat(),
        "warnings": result.warnings,
        "headers": result.headers,
    }

@app.get("/summary/total-balance/{user_id}")
def total_balance(user_id: uuid.UUID, db: Session = Depends(get_db)):
    # Stripe is left out on purpose: its balance is money the processor is still holding,
    # not money in a bank, and it lands in a bank account later as a payout — counting both
    # would count the same money twice.
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id)
        .filter(or_(Account.source.is_(None), Account.source != "stripe"))
        .order_by(Account.created_at)
        .all()
    )
    with_balance = [a for a in accounts if a.balance is not None]

    # Summed per currency — there's no exchange-rate conversion, so a SGD and a USD
    # balance are never added together.
    totals: dict = {}
    for a in with_balance:
        entry = totals.setdefault(a.currency, {"total": Decimal(0), "accounts": 0})
        entry["total"] += a.balance
        entry["accounts"] += 1

    # A statement balance is only as current as the statement, so the total is only as
    # current as its stalest account.
    dates = [a.balance_as_of for a in with_balance if a.balance_as_of]

    return {
        "currencies": [
            {"currency": cur, "total": str(v["total"]), "accounts": v["accounts"]}
            for cur, v in sorted(totals.items())
        ],
        "accounts": [
            {
                "id": str(a.id),
                "name": a.display_name or a.institution_name or "Account",
                "balance": str(a.balance),
                "currency": a.currency,
                "as_of": a.balance_as_of.isoformat() if a.balance_as_of else None,
            }
            for a in with_balance
        ],
        "accounts_without_balance": len(accounts) - len(with_balance),
        "as_of": min(dates).isoformat() if dates else None,
    }


@app.get("/summary/monthly/{user_id}", response_model=MonthlySummaryOut)
def get_monthly_summary(
    user_id: uuid.UUID,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    # Same rules as category_breakdown, so the dashboard and Cash Flow always agree:
    # an income-type category is income, an expense-type category is an expense, and a
    # transfer-type category (or no category at all) counts by the sign of its amount.
    no_fixed_tab = or_(Category.type == "transfer", Category.id.is_(None))
    income_amount = case(
        (Category.type == "income", func.abs(Transaction.amount)),
        (and_(no_fixed_tab, Transaction.amount > 0), Transaction.amount),
        else_=0,
    )
    expense_amount = case(
        (Category.type == "expense", func.abs(Transaction.amount)),
        (and_(no_fixed_tab, Transaction.amount < 0), -Transaction.amount),
        else_=0,
    )

    income, expenses = (
        db.query(
            func.coalesce(func.sum(income_amount), 0),
            func.coalesce(func.sum(expense_amount), 0),
        )
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(Account.user_id == user_id, Transaction.transaction_date.between(start, end))
        .one()
    )
    income, expenses = Decimal(income), Decimal(expenses)

    return MonthlySummaryOut(
        income=income,
        expenses=expenses,
        savings=income - expenses,
        month=f"{year}-{month:02d}",
    )


@app.get("/transactions/top-expenses/{user_id}")
def get_top_expenses(
    user_id: uuid.UUID,
    limit: int = 5,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])

    # Money that actually went out (negative amounts), excluding anything filed under an
    # income-type category. Transfers out are included, matching Cash Flow's Expense tab.
    rows = (
        db.query(Transaction, Category.name)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date.between(start, end),
            Transaction.amount < 0,
            or_(Category.type.is_(None), Category.type != "income"),
        )
        .order_by(Transaction.amount.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(t.id),
            "description_raw": t.description_raw,
            "amount": str(t.amount),
            "currency": t.currency,
            "transaction_date": t.transaction_date.isoformat(),
            "category_name": category_name,
        }
        for t, category_name in rows
    ]
# ---------------------------------------------------------------------------------------
# The recurring-transactions endpoints, for app/main.py.
#
# Replace the whole recurring section of main.py with this (everything from
# `def _recent_transactions` through the `DELETE /recurring/{rule_id}` endpoint).
#
# main.py needs these imports (add any you don't already have):
#
#   from datetime import date, timedelta
#   from decimal import Decimal
#   from .models import Account, Category, RecurringRule, Transaction
#   from .schemas import (RecurringCreate, RecurringFromTransaction,
#                         RecurringManualCreate, RecurringUpdate)
#   from .recurring import (LOOKBACK_DAYS, PRESET_INTERVALS, TransactionIndex,
#                           description_key, detect_candidates, frequency_label,
#                           rule_schedule, suggest_label)
#
# New in this version:
#   GET   /recurring/by-id/{rule_id}   one rule, with what the Edit form needs
#   PATCH /recurring/{rule_id}         can now change amount, type, category, account and,
#                                      for a hand-made rule, its date
# ---------------------------------------------------------------------------------------

def _recent_transactions(db: Session, user_id: uuid.UUID, today: date):
    since = today - timedelta(days=LOOKBACK_DAYS)
    return (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.transaction_date >= since,
            Transaction.transaction_date <= today,
        )
        .all()
    )


def _is_positive(rule) -> bool:
    return (rule.expected_amount or 0) > 0


def _find_duplicate_rule(db: Session, user_id: uuid.UUID, pattern: str, expected_amount):
    # No database-level uniqueness on rules, so this is the only thing stopping the same
    # charge being tracked twice. Direction matters: a charge and a credit with the same
    # wording are different things.
    for rule in db.query(RecurringRule).filter(
        RecurringRule.user_id == user_id, RecurringRule.merchant_pattern == pattern
    ):
        if _is_positive(rule) == (expected_amount > 0):
            return rule
    return None


def _set_interval(rule: RecurringRule, count: int, unit: str) -> None:
    # The interval is what schedules; the frequency name is kept beside it for readability
    # ('weekly', 'daily', or 'custom' when no name fits). Always set together.
    rule.interval_count = count
    rule.interval_unit = unit
    rule.frequency = frequency_label(count, unit)


def _follows_transactions(rule: RecurringRule) -> bool:
    # A rule made by hand has an internal key ("manual:...") that nothing can match. Every
    # other rule is tied to the wording of real transactions, and takes its dates from them.
    return not rule.merchant_pattern.startswith("manual:")


def _rule_kind(db: Session, rule: RecurringRule) -> str:
    # What kind of thing a rule is: its category's type, or failing that the way the money goes.
    if rule.category_id:
        category = db.get(Category, rule.category_id)
        if category and category.type in ("expense", "income", "transfer"):
            return category.type
    return "expense" if (rule.expected_amount or 0) < 0 else "income"


def _goes_out(db: Session, rule: RecurringRule) -> bool:
    if rule.expected_amount:
        return rule.expected_amount < 0
    return _rule_kind(db, rule) != "income"


def _category_names(db: Session) -> dict:
    return {c.id: c.name for c in db.query(Category).all()}


def _account_lookup(db: Session, user_id: uuid.UUID) -> dict:
    return {a.id: a for a in db.query(Account).filter(Account.user_id == user_id)}


def _rule_out(rule, schedule: dict, category_names: dict, accounts: dict) -> dict:
    account = accounts.get(rule.account_id) if rule.account_id else None
    return {
        "id": str(rule.id),
        "description": rule.description,
        "merchant_pattern": rule.merchant_pattern,
        "expected_amount": str(rule.expected_amount) if rule.expected_amount is not None else None,
        "amount_tolerance_pct": str(rule.amount_tolerance_pct),
        "amount_varies": Decimal(rule.amount_tolerance_pct or 0) > Decimal("0.05"),
        "frequency": rule.frequency,
        "interval_count": rule.interval_count,
        "interval_unit": rule.interval_unit,
        "category_id": str(rule.category_id) if rule.category_id else None,
        "category_name": category_names.get(rule.category_id),
        "account_id": str(rule.account_id) if rule.account_id else None,
        "account_name": (account.display_name or account.institution_name or "Account") if account else None,
        "is_active": rule.is_active,
        # True when its dates come from real transactions; False for one made by hand.
        "follows_transactions": _follows_transactions(rule),
        # From a real matching transaction if there is one, else the account's currency.
        "currency": schedule["currency"] or (account.currency if account else None) or "SGD",
        "last_occurred_date": schedule["last_occurred_date"].isoformat() if schedule["last_occurred_date"] else None,
        "next_due_date": schedule["next_due_date"].isoformat() if schedule["next_due_date"] else None,
    }


def _save_new_rule(db: Session, rule: RecurringRule) -> dict:
    today = date.today()
    schedule = rule_schedule(rule, TransactionIndex(_recent_transactions(db, rule.user_id, today)), today)
    rule.last_occurred_date = schedule["last_occurred_date"]
    rule.next_due_date = schedule["next_due_date"]
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule, schedule, _category_names(db), _account_lookup(db, rule.user_id))


@app.get("/recurring/suggestions/{user_id}")
def recurring_suggestions(user_id: uuid.UUID, db: Session = Depends(get_db)):
    today = date.today()
    # A pattern with a rule in ANY state (tracking, stopped, or dismissed) is never
    # suggested again — otherwise dismissing a suggestion would be pointless.
    existing = {
        (r.merchant_pattern, _is_positive(r))
        for r in db.query(RecurringRule).filter(RecurringRule.user_id == user_id)
    }
    candidates = detect_candidates(_recent_transactions(db, user_id, today), today, existing)
    names = _category_names(db)
    return [c.to_dict(names) for c in candidates]


@app.get("/recurring/upcoming/{user_id}")
def upcoming_recurring(user_id: uuid.UUID, days: int = 30, db: Session = Depends(get_db)):
    today = date.today()
    transactions = _recent_transactions(db, user_id, today)
    index = TransactionIndex(transactions)
    rules = db.query(RecurringRule).filter(RecurringRule.user_id == user_id).all()
    names = _category_names(db)
    accounts = _account_lookup(db, user_id)
    horizon = today + timedelta(days=days)

    items = []
    for rule in rules:
        if not rule.is_active:
            continue
        schedule = rule_schedule(rule, index, today)
        due = schedule["next_due_date"]
        if due is None or due > horizon:
            continue
        item = _rule_out(rule, schedule, names, accounts)
        item["days_until"] = (due - today).days
        items.append(item)
    items.sort(key=lambda i: (i["next_due_date"], i["description"]))

    existing = {(r.merchant_pattern, _is_positive(r)) for r in rules}
    return {
        "items": items,
        "suggestions_available": len(detect_candidates(transactions, today, existing)),
    }


@app.get("/recurring/for-transaction/{transaction_id}")
def recurring_for_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)):
    """Is this transaction's charge already being tracked? Lets the checkbox show its true state."""
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = db.get(Account, transaction.account_id)

    pattern = description_key(transaction.description_raw)
    rule = _find_duplicate_rule(db, account.user_id, pattern, transaction.amount) if pattern else None
    if not rule:
        return {"rule": None}

    today = date.today()
    index = TransactionIndex(_recent_transactions(db, rule.user_id, today))
    return {
        "rule": _rule_out(
            rule, rule_schedule(rule, index, today), _category_names(db), _account_lookup(db, rule.user_id)
        )
    }


@app.get("/recurring/{user_id}")
def list_recurring(user_id: uuid.UUID, db: Session = Depends(get_db)):
    today = date.today()
    index = TransactionIndex(_recent_transactions(db, user_id, today))
    names = _category_names(db)
    accounts = _account_lookup(db, user_id)
    rules = db.query(RecurringRule).filter(RecurringRule.user_id == user_id).all()
    out = [_rule_out(r, rule_schedule(r, index, today), names, accounts) for r in rules]
    # Tracked ones first, soonest due first; stopped/dismissed ones after.
    out.sort(key=lambda r: (not r["is_active"], r["next_due_date"] or "9999-12-31", r["description"]))
    return out


@app.post("/recurring", status_code=201)
def create_recurring(payload: RecurringCreate, db: Session = Depends(get_db)):
    if _find_duplicate_rule(db, payload.user_id, payload.merchant_pattern, payload.expected_amount):
        raise HTTPException(status_code=409, detail="You're already tracking this one.")

    rule = RecurringRule(
        user_id=payload.user_id,
        description=payload.description.strip() or suggest_label(payload.merchant_pattern),
        merchant_pattern=payload.merchant_pattern,
        expected_amount=payload.expected_amount,
        amount_tolerance_pct=payload.amount_tolerance_pct,
        category_id=payload.category_id,
        account_id=payload.account_id,
        is_active=payload.is_active,
    )
    _set_interval(rule, *PRESET_INTERVALS[payload.frequency])
    return _save_new_rule(db, rule)


@app.post("/recurring/manual", status_code=201)
def create_recurring_manual(payload: RecurringManualCreate, db: Session = Depends(get_db)):
    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=422, detail="Add a description.")

    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != payload.user_id:
            raise HTTPException(status_code=404, detail="Account not found")

    if payload.category_id:
        category = db.get(Category, payload.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        if category.user_id not in (None, payload.user_id):
            raise HTTPException(status_code=403, detail="That category isn't available to you")
        # The type picker and the category list are meant to agree; this catches a mismatch
        # rather than quietly filing an expense under an income category.
        if category.type != payload.kind:
            raise HTTPException(
                status_code=422,
                detail=f"That category is for {category.type}, not {payload.kind}.",
            )

    # The form takes a plain positive amount; the kind decides which way the money moves.
    # A transfer has no fixed direction, so it asks.
    outgoing = payload.kind == "expense" or (payload.kind == "transfer" and payload.direction == "out")

    rule = RecurringRule(
        user_id=payload.user_id,
        description=description,
        # Nothing to match imported transactions against, so each hand-made rule gets its own
        # key: it runs purely on the schedule, and two with the same name can coexist.
        merchant_pattern=f"manual:{uuid.uuid4().hex}",
        expected_amount=-payload.amount if outgoing else payload.amount,
        amount_tolerance_pct=Decimal("0.05"),
        category_id=payload.category_id,
        account_id=payload.account_id,
        # The date typed in is where the series STARTS (see next_on_or_after_anchor).
        next_due_date=payload.start_date,
        is_active=True,
    )
    _set_interval(rule, payload.interval_count, payload.interval_unit)
    return _save_new_rule(db, rule)


@app.post("/recurring/from-transaction", status_code=201)
def create_recurring_from_transaction(payload: RecurringFromTransaction, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, payload.transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = db.get(Account, transaction.account_id)

    pattern = description_key(transaction.description_raw)
    if not pattern:
        raise HTTPException(
            status_code=422,
            detail="This transaction has no recognisable wording to match future ones against.",
        )
    if _find_duplicate_rule(db, account.user_id, pattern, transaction.amount):
        raise HTTPException(status_code=409, detail="You're already tracking this one.")

    rule = RecurringRule(
        user_id=account.user_id,
        description=(payload.description or "").strip() or suggest_label(pattern),
        merchant_pattern=pattern,
        expected_amount=transaction.amount,
        amount_tolerance_pct=Decimal("0.05"),
        category_id=transaction.category_id,
        account_id=transaction.account_id,
        # Seeded from this transaction, so the schedule is right even though nothing
        # else matches yet.
        last_occurred_date=transaction.transaction_date,
        is_active=True,
    )
    _set_interval(rule, payload.interval_count, payload.interval_unit)
    return _save_new_rule(db, rule)


@app.get("/recurring/by-id/{rule_id}")
def get_recurring_by_id(rule_id: uuid.UUID, db: Session = Depends(get_db)):
    """One rule, with what the Edit form needs to fill itself in."""
    rule = db.get(RecurringRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    today = date.today()
    index = TransactionIndex(_recent_transactions(db, rule.user_id, today))
    out = _rule_out(rule, rule_schedule(rule, index, today), _category_names(db), _account_lookup(db, rule.user_id))
    out["kind"] = _rule_kind(db, rule)
    out["direction"] = "out" if _goes_out(db, rule) else "in"
    return out


@app.patch("/recurring/{rule_id}")
def update_recurring(rule_id: uuid.UUID, payload: RecurringUpdate, db: Session = Depends(get_db)):
    rule = db.get(RecurringRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Recurring rule not found")

    data = payload.model_dump(exclude_unset=True)
    follows = _follows_transactions(rule)

    # ---- Check everything first. Nothing is changed until all of it is known to be fine, so
    # ---- a request with one bad part never leaves a half-applied edit behind.
    if (data.get("interval_count") is None) != (data.get("interval_unit") is None):
        raise HTTPException(status_code=422, detail="Give both a number and a unit to change how often it repeats.")

    # The amount, and which way the money goes. (kind, direction and amount can't be null.)
    new_amount = None
    kind = data.get("kind") or _rule_kind(db, rule)
    if any(data.get(k) is not None for k in ("kind", "direction", "amount")):
        current = rule.expected_amount
        magnitude = data["amount"] if data.get("amount") is not None else (abs(current) if current else None)
        if not magnitude:
            raise HTTPException(status_code=422, detail="Give an amount.")
        if data.get("kind") is None and data.get("direction") is None:
            outgoing = _goes_out(db, rule)  # just a new amount: the money keeps going the same way
        else:
            direction = data.get("direction") or ("out" if _goes_out(db, rule) else "in")
            outgoing = kind == "expense" or (kind == "transfer" and direction == "out")
        new_amount = -magnitude if outgoing else magnitude
        if follows and current and (new_amount < 0) != (current < 0):
            raise HTTPException(
                status_code=422,
                detail="This one follows your transactions, so it can't switch between money out and money in.",
            )

    # The category must exist, be the user's to use, and agree with the kind.
    if "category_id" in data:
        category = None
        if data["category_id"] is not None:
            category = db.get(Category, data["category_id"])
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")
            if category.user_id not in (None, rule.user_id):
                raise HTTPException(status_code=403, detail="That category isn't available to you")
    else:
        category = db.get(Category, rule.category_id) if rule.category_id else None
    if category and ("category_id" in data or new_amount is not None) and category.type != kind:
        raise HTTPException(status_code=422, detail=f"That category is for {category.type}, not {kind}.")

    if data.get("account_id") is not None:
        account = db.get(Account, data["account_id"])
        if not account or account.user_id != rule.user_id:
            raise HTTPException(status_code=404, detail="Account not found")

    if data.get("next_due_date") is not None and follows:
        raise HTTPException(
            status_code=422,
            detail="This one follows your transactions, so its date can't be set by hand.",
        )

    # ---- All good: apply it.
    if data.get("description") is not None and data["description"].strip():
        rule.description = data["description"].strip()
    if data.get("is_active") is not None:
        rule.is_active = data["is_active"]
    if data.get("interval_count") is not None:
        _set_interval(rule, data["interval_count"], data["interval_unit"])
    elif data.get("frequency") is not None:
        _set_interval(rule, *PRESET_INTERVALS[data["frequency"]])
    if new_amount is not None:
        rule.expected_amount = new_amount
    if "category_id" in data:
        rule.category_id = data["category_id"]
    if "account_id" in data:
        rule.account_id = data["account_id"]
    if data.get("next_due_date") is not None:
        rule.next_due_date = data["next_due_date"]
    db.commit()
    db.refresh(rule)

    today = date.today()
    index = TransactionIndex(_recent_transactions(db, rule.user_id, today))
    return _rule_out(rule, rule_schedule(rule, index, today), _category_names(db), _account_lookup(db, rule.user_id))


@app.delete("/recurring/{rule_id}")
def delete_recurring(rule_id: uuid.UUID, db: Session = Depends(get_db)):
    rule = db.get(RecurringRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": True}