import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


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
    # A guess the app isn't confident enough to count; null once it's confirmed or if there's none.
    suggested_category_id: Optional[uuid.UUID] = None
    txn_type: Optional[str] = None  # purchase, own_transfer, person_payment, income, ...
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


class RecurringCreate(BaseModel):
    user_id: uuid.UUID
    description: str  # the label the user sees, e.g. "Netflix"
    merchant_pattern: str  # the fingerprint used to recognise it in transactions
    expected_amount: Decimal  # signed: negative for a charge, positive for a credit
    frequency: Literal["weekly", "biweekly", "monthly", "yearly"]
    amount_tolerance_pct: Decimal = Decimal("0.05")
    category_id: Optional[uuid.UUID] = None
    account_id: Optional[uuid.UUID] = None
    # False records a dismissed suggestion: it's remembered so it isn't suggested again,
    # but never shown as upcoming.
    is_active: bool = True


class RecurringFromTransaction(BaseModel):
    transaction_id: uuid.UUID
    # "every 3 months" is interval_count=3, interval_unit="month"
    interval_count: int = Field(ge=1, le=366)
    interval_unit: Literal["day", "week", "month", "year"]
    description: Optional[str] = None


class RecurringUpdate(BaseModel):
    description: Optional[str] = None
    is_active: Optional[bool] = None
    # Change how often it repeats: give a named frequency, or a count AND a unit.
    frequency: Optional[Literal["weekly", "biweekly", "monthly", "yearly"]] = None
    interval_count: Optional[int] = Field(default=None, ge=1, le=366)
    interval_unit: Optional[Literal["day", "week", "month", "year"]] = None

    # --- the Edit form: the same things the Add form asks for ---
    # What kind of thing it is. A transfer can go either way, so it also says which.
    kind: Optional[Literal["expense", "income", "transfer"]] = None
    direction: Optional[Literal["out", "in"]] = None
    # Entered as a positive number; the kind (and direction) decides the sign.
    amount: Optional[Decimal] = Field(default=None, gt=0)
    # Only for a rule made by hand: where its schedule runs from. A rule that follows real
    # transactions takes its dates from them, so it can't be given one.
    next_due_date: Optional[date] = None
    # These two can be cleared: send them as null (leaving them out leaves them alone).
    account_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None


class RecurringManualCreate(BaseModel):
    """The 'add a recurring transaction by hand' form."""

    user_id: uuid.UUID
    kind: Literal["expense", "income", "transfer"]
    # Only meaningful for a transfer: does the money leave the account or arrive in it?
    direction: Literal["out", "in"] = "out"
    description: str
    amount: Decimal = Field(gt=0)  # always entered as a positive number; `kind` decides the sign
    start_date: date  # the first (or next) date it happens; it repeats from here
    # "every 3 months" is interval_count=3, interval_unit="month"
    interval_count: int = Field(ge=1, le=366)
    interval_unit: Literal["day", "week", "month", "year"]
    account_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None