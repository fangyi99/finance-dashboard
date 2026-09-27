import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    description_raw: str
    amount: Decimal
    currency: str = "SGD"
    transaction_date: date
    category_id: Optional[uuid.UUID] = None

class TransactionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    description_raw: str
    amount: Decimal
    currency: str
    transaction_date: date
    category_id: Optional[uuid.UUID]
    category_source: str
    is_recurring: bool
    created_at: datetime

    class Config:
        from_attributes = True   # lets Pydantic read directly from SQLAlchemy objects