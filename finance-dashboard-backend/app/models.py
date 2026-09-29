import uuid
from sqlalchemy import (
    Column, String, Numeric, Date, DateTime, Boolean, Integer,
    ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    accounts = relationship("Account", back_populates="user")
    recurring_rules = relationship("RecurringRule", back_populates="user")
    widget_preferences = relationship("WidgetPreference", back_populates="user")
    tab_preferences = relationship("TabPreference", back_populates="user")


class WidgetPreference(Base):
    __tablename__ = "widget_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    widget_key = Column(String, nullable=False)  # e.g. 'balance_summary', 'upcoming_transactions'
    is_enabled = Column(Boolean, default=True)
    display_order = Column(Integer)

    user = relationship("User", back_populates="widget_preferences")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source = Column(String, nullable=False)  # 'stripe' | 'csv_import' | 'pdf_import' | 'manual'
    display_name = Column(String)
    institution_name = Column(String)  # 'DBS', 'OCBC', 'Stripe', etc
    currency = Column(String, default="SGD")  # account's primary/default currency
    balance = Column(Numeric(14, 2), nullable=True)
    balance_as_of = Column(Date, nullable=True)  # statement end date (or Stripe sync date)
    last_synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            source.in_(["stripe", "csv_import", "pdf_import", "manual"]),
            name="ck_account_source"
        ),
    )

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # NULL = system default
    name = Column(String, nullable=False)
    parent_category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    type = Column(String, nullable=False, server_default="expense")  # 'income' | 'expense' | 'transfer'
    is_system_default = Column(Boolean, default=True)

    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category")
    recurring_rules = relationship("RecurringRule", back_populates="category")
    merchant_mappings = relationship("MerchantCategoryMap", back_populates="category")
    feedback_entries = relationship(
        "CategoryFeedback", back_populates="corrected_category"
    )
    __table_args__ = (
        CheckConstraint("type IN ('income', 'expense', 'transfer')", name="ck_category_type"),
    )


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    description = Column(String, nullable=False)  # user-facing label, e.g. "Netflix"
    merchant_pattern = Column(String, nullable=False)  # normalized string used for matching, e.g. "NETFLIX"

    expected_amount = Column(Numeric(12, 2))
    amount_tolerance_pct = Column(Numeric(4, 2), default=0.05)  # allowed variance, e.g. 0.05 = +/-5%

    frequency = Column(String, nullable=False)  # 'weekly' | 'biweekly' | 'monthly' | 'yearly'
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))

    next_due_date = Column(Date)
    last_occurred_date = Column(Date)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            frequency.in_(["weekly", "biweekly", "monthly", "yearly"]),
            name="ck_recurring_rule_frequency"
        ),
    )

    user = relationship("User", back_populates="recurring_rules")
    category = relationship("Category", back_populates="recurring_rules")
    transactions = relationship("Transaction", back_populates="recurring_rule")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)

    description_raw = Column(String, nullable=False)
    description_normalized = Column(String)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String, default="SGD")  # this specific transaction's currency
    transaction_date = Column(Date, nullable=False)

    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    category_source = Column(String, default="rule")  # 'ml' | 'rule' | 'user'
    category_confidence = Column(Numeric(4, 3))  # 0.000-1.000, from ML/fuzzy match

    is_recurring = Column(Boolean, default=False)
    recurring_rule_id = Column(UUID(as_uuid=True), ForeignKey("recurring_rules.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            category_source.in_(["ml", "rule", "user"]),
            name="ck_transaction_category_source"
        ),
    )

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    recurring_rule = relationship("RecurringRule", back_populates="transactions")
    feedback_entries = relationship("CategoryFeedback", back_populates="transaction")


class MerchantCategoryMap(Base):
    __tablename__ = "merchant_category_maps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_key = Column(String, unique=True, nullable=False)  # normalized merchant name
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    confidence = Column(Numeric(4, 3), default=1.0)
    source = Column(String, default="user_feedback")  # e.g. 'seed_data' | 'user_feedback'

    category = relationship("Category", back_populates="merchant_mappings")


class CategoryFeedback(Base):
    __tablename__ = "category_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    description_normalized = Column(String)
    corrected_category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="feedback_entries")
    corrected_category = relationship("Category", back_populates="feedback_entries")

class TabPreference(Base):
    __tablename__ = "tab_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tab_key = Column(String, nullable=False)   # 'dashboard' | 'accounts' | 'cash_flow' | 'budget' | 'settings'
    is_enabled = Column(Boolean, default=True)
    display_order = Column(Integer, nullable=False)

    user = relationship("User", back_populates="tab_preferences")