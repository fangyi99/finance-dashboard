import uuid
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from .database import get_db
from .models import Transaction
from .schemas import TransactionCreate, TransactionOut, WidgetPreferencesBulkUpdate, WidgetPreferenceOut, MonthlySummaryOut, TabPreferencesBulkUpdate, TabPreferenceOut, CSVImportResult
from .models import WidgetPreference, TabPreference
from io import StringIO
from datetime import date, datetime
from calendar import monthrange
from sqlalchemy import func, and_
from .models import Account

app = FastAPI()

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
    transaction = Transaction(**payload.model_dump())
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

            transaction = Transaction(
                account_id=account_id,
                description_raw=description,
                amount=amount,
                transaction_date=tx_date,
            )
            db.add(transaction)
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"Row {i + 2}: {e}")  # +2 accounts for header row + 0-index

    db.commit()
    return CSVImportResult(imported_count=imported, skipped_count=skipped, errors=errors[:10])