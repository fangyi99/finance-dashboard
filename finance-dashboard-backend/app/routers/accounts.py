import uuid
from datetime import date, datetime
from calendar import monthrange
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, Transaction, User
from ..schemas import TransactionOut

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    user_id: uuid.UUID
    source: Literal["stripe", "csv_import", "pdf_import", "manual"]
    display_name: Optional[str] = None
    institution_name: Optional[str] = None
    currency: str = Field(default="SGD", min_length=3, max_length=3)


class AccountUpdate(BaseModel):
    display_name: Optional[str] = None
    institution_name: Optional[str] = None


class AccountOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    source: str
    display_name: Optional[str]
    institution_name: Optional[str]
    currency: str
    balance: Optional[Decimal]  # read from the statement (or Stripe) at import time
    balance_as_of: Optional[date]  # statement end date (or Stripe sync date), not the upload time
    last_synced_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=AccountOut)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/{user_id}", response_model=List[AccountOut])
def list_accounts(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(Account)
        .filter(Account.user_id == user_id)
        .order_by(Account.created_at)
        .all()
    )


# "by-id" keeps this from colliding with the list route above, since both take a UUID.
@router.get("/by-id/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/{account_id}/transactions", response_model=List[TransactionOut])
def list_account_transactions(
    account_id: uuid.UUID,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if not db.get(Account, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
 
    query = db.query(Transaction).filter(Transaction.account_id == account_id)
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


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: uuid.UUID, payload: AccountUpdate, db: Session = Depends(get_db)
):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return account