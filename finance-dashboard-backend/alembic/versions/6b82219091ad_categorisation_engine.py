"""categorisation engine

Revision ID: 6b82219091ad
Revises: 4680a5969578
Create Date: 2026-10-16 14:03:09.992429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6b82219091ad'
down_revision: Union[str, Sequence[str], None] = '4680a5969578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categorisation_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("phrase", sa.String(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("char_length(btrim(phrase)) > 0", name="ck_categorisation_rule_phrase_not_blank"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "phrase", name="uq_categorisation_rule_user_phrase"),
    )
    op.add_column("transactions", sa.Column("suggested_category_id", sa.UUID(), nullable=True))
    op.add_column("transactions", sa.Column("txn_type", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("payee_key", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("categorisation", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("transactions", sa.Column("paired_transaction_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_transactions_payee_key"), "transactions", ["payee_key"], unique=False)
    op.create_foreign_key(
        "fk_transactions_paired_transaction", "transactions", "transactions",
        ["paired_transaction_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transactions_suggested_category", "transactions", "categories",
        ["suggested_category_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_suggested_category", "transactions", type_="foreignkey")
    op.drop_constraint("fk_transactions_paired_transaction", "transactions", type_="foreignkey")
    op.drop_index(op.f("ix_transactions_payee_key"), table_name="transactions")
    op.drop_column("transactions", "paired_transaction_id")
    op.drop_column("transactions", "categorisation")
    op.drop_column("transactions", "payee_key")
    op.drop_column("transactions", "txn_type")
    op.drop_column("transactions", "suggested_category_id")
    op.drop_table("categorisation_rules")
