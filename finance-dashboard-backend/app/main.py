import uuid
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from .database import get_db
from .models import Transaction
from .schemas import TransactionCreate, TransactionOut, WidgetPreferencesBulkUpdate, WidgetPreferenceOut, MonthlySummaryOut
from .models import WidgetPreference
from datetime import date
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