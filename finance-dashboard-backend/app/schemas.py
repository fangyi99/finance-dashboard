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
    notes: Optional[str] = None
    amount: Decimal
    currency: str
    transaction_date: date
    category_id: Optional[uuid.UUID]
    category_source: str
    is_recurring: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionDetailOut(TransactionOut):
    category_name: Optional[str] = None


class TransactionUpdate(BaseModel):
    # Both optional and independent: send just one to change only that field.
    category_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class WidgetPreferenceCreate(BaseModel):
    widget_key: str
    is_enabled: bool = True
    display_order: int


class WidgetPreferenceOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    widget_key: str
    is_enabled: bool
    display_order: int

    class Config:
        from_attributes = True


class WidgetPreferencesBulkUpdate(BaseModel):
    user_id: uuid.UUID
    preferences: list[WidgetPreferenceCreate]


class TabPreferenceCreate(BaseModel):
    tab_key: str
    is_enabled: bool = True
    display_order: int


class TabPreferenceOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    tab_key: str
    is_enabled: bool
    display_order: int

    class Config:
        from_attributes = True


class TabPreferencesBulkUpdate(BaseModel):
    user_id: uuid.UUID
    preferences: list[TabPreferenceCreate]


class MonthlySummaryOut(BaseModel):
    income: Decimal
    expenses: Decimal
    savings: Decimal
    month: str  # e.g. "2026-09"


class CSVImportResult(BaseModel):
    imported_count: int
    skipped_count: int
    errors: list[str]