import uuid
from sqlalchemy import (
    Column, String, Numeric, Date, DateTime, Boolean, Integer,
    ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class TabPreference(Base):
    __tablename__ = "tab_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    tab_key = Column(String, nullable=False)  # 'dashboard' | 'accounts' | 'cash_flow' | 'budget' | 'settings'
    is_enabled = Column(Boolean, default=True)
    display_order = Column(Integer, nullable=False)

    user = relationship("User", back_populates="tab_preferences")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # NULL until the user's first import locks it in — see /accounts/{id}/import-method.
    # Once set, the backend refuses to change it (an account doesn't switch between
    # being a statement-tracked account and a Stripe-tracked one after the fact).
    source = Column(String, nullable=True)  # 'stripe' | 'csv_import' | 'pdf_import' | 'manual'
    display_name = Column(String)
    institution_name = Column(String)  # 'DBS', 'OCBC', 'Stripe', etc
    currency = Column(String, default="SGD")  # account's primary/default currency
    balance = Column(Numeric(14, 2), nullable=True)
    balance_as_of = Column(Date, nullable=True)  # statement end date, or Stripe sync date
    last_synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "source IS NULL OR source IN ('stripe', 'csv_import', 'pdf_import', 'manual')",
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

    __table_args__ = (
        CheckConstraint("type IN ('income', 'expense', 'transfer')", name="ck_category_type"),
    )

    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category", foreign_keys="Transaction.category_id")
    recurring_rules = relationship("RecurringRule", back_populates="category")
    merchant_mappings = relationship("MerchantCategoryMap", back_populates="category")
    feedback_entries = relationship(
        "CategoryFeedback", back_populates="corrected_category"
    )


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    description = Column(String, nullable=False)  # user-facing label, e.g. "Netflix"
    merchant_pattern = Column(String, nullable=False)  # normalized string used for matching, e.g. "NETFLIX"

    expected_amount = Column(Numeric(12, 2))
    amount_tolerance_pct = Column(Numeric(4, 2), default=0.05)  # allowed variance, e.g. 0.05 = +/-5%

    # How often, as a count and a unit: "every 3 months" is (3, 'month'). This is what the
    # schedule is worked out from.
    interval_count = Column(Integer, nullable=False, server_default="1")
    interval_unit = Column(String, nullable=False, server_default="month")  # day | week | month | year
    # A readable name kept in step with the interval, for the cases that have one:
    # 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'yearly', else 'custom'.
    frequency = Column(String, nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    # Which account this charge comes out of / lands in. Optional: set when approving a
    # suggestion or entering one by hand. SET NULL so removing an account never breaks a rule.
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    next_due_date = Column(Date)
    last_occurred_date = Column(Date)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            frequency.in_(["daily", "weekly", "biweekly", "monthly", "yearly", "custom"]),
            name="ck_recurring_rule_frequency"
        ),
        CheckConstraint(
            interval_unit.in_(["day", "week", "month", "year"]),
            name="ck_recurring_rule_interval_unit"
        ),
        CheckConstraint("interval_count BETWEEN 1 AND 366", name="ck_recurring_rule_interval_count"),
    )

    user = relationship("User", back_populates="recurring_rules")
    category = relationship("Category", back_populates="recurring_rules")
    account = relationship("Account")
    transactions = relationship("Transaction", back_populates="recurring_rule")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)

    description_raw = Column(String, nullable=False)
    description_normalized = Column(String)
    notes = Column(String, nullable=True)  # the user's own free-text note, optional

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String, default="SGD")  # this specific transaction's currency
    transaction_date = Column(Date, nullable=False)

    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    category_source = Column(String, default="rule")  # 'ml' | 'rule' | 'user'
    category_confidence = Column(Numeric(4, 3))  # 0.000-1.000, from ML/fuzzy match

    is_recurring = Column(Boolean, default=False)
    recurring_rule_id = Column(UUID(as_uuid=True), ForeignKey("recurring_rules.id"), nullable=True)

    # --- how the categoriser (app/classify) reached its decision ---
    # A SUGGESTION is kept apart from category_id, so budgets and summaries (which read
    # category_id) can never count a guess. Confirming a suggestion copies it into category_id.
    suggested_category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL", name="fk_transactions_suggested_category"), nullable=True
    )
    # What kind of thing it is: purchase, own_transfer, person_payment, income, bill, cash, ...
    txn_type = Column(String, nullable=True)
    # What a learned rule and the repeat-payee check are keyed on (a merchant, or a payee's name).
    payee_key = Column(String, nullable=True, index=True)
    # {"status", "source", "confidence", "suggested_name", "candidates", "evidence": [...]}: the WHY.
    categorisation = Column(JSONB, nullable=True)
    # The other half of an own-account transfer: an equal and opposite amount in another account.
    paired_transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL", name="fk_transactions_paired_transaction"), nullable=True
    )

    # Stripe's payment ID (e.g. "pi_..."), used to avoid re-importing the same payment
    # on every sync. NULL for CSV/manual/PDF transactions, which have no such ID.
    external_id = Column(String, unique=True, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            category_source.in_(["ml", "rule", "user"]),
            name="ck_transaction_category_source"
        ),
    )

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions", foreign_keys=[category_id])
    suggested_category = relationship("Category", foreign_keys=[suggested_category_id])
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


class CategoryVisibility(Base):
    __tablename__ = "category_visibilities"

    # A row only exists for a category a user has explicitly hidden — absence of a row
    # means visible. Applies to both system-default and user-owned categories, since
    # hiding "Groceries" from your breakdown is independent of who owns the row.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uq_category_visibility_user_category"),
    )


class CategoryFeedback(Base):
    __tablename__ = "category_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    description_normalized = Column(String)
    corrected_category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="feedback_entries")
    corrected_category = relationship("Category", back_populates="feedback_entries")


class Budget(Base):
    """A monthly spending limit: "Groceries: 500 a month"."""

    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)  # the limit for one calendar month
    # What it measures: one category (and everything under it), or NULL for all spending.
    # No ON DELETE action on purpose: a category with a budget can't be deleted until the
    # budget is changed or removed (the categories router says so), rather than the budget
    # quietly turning into "all spending".
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_budget_amount_positive"),
        CheckConstraint("char_length(btrim(name)) > 0", name="ck_budget_name_not_blank"),
    )

    user = relationship("User")
    category = relationship("Category")


class CategorisationRule(Base):
    """
    Something YOU taught the app: this phrase always means this category ("TOP UP TO PAYLAH" ->
    Dining, "TAN AH KOW" -> Dining). Per user, unlike merchant_category_maps, which is one shared
    list. These are checked before any built-in rule, so you are always in charge.
    """

    __tablename__ = "categorisation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    phrase = Column(String, nullable=False)  # upper case; matched as whole words
    # If the category is deleted, the rule goes with it.
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "phrase", name="uq_categorisation_rule_user_phrase"),
        CheckConstraint("char_length(btrim(phrase)) > 0", name="ck_categorisation_rule_phrase_not_blank"),
    )

    user = relationship("User")
    category = relationship("Category")