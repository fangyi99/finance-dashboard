"""recurring intervals

Revision ID: dbb9f4b689bd
Revises: 5b6d0871dec5
Create Date: 2026-10-11 16:38:08.010781

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dbb9f4b689bd'
down_revision: Union[str, Sequence[str], None] = '5b6d0871dec5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_rules",
        sa.Column("interval_count", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "recurring_rules",
        sa.Column("interval_unit", sa.String(), server_default="month", nullable=False),
    )
 
    # Existing rows keep their meaning: the old named frequency becomes a count and a unit.
    # (monthly is already the default, 1 month.)
    op.execute("UPDATE recurring_rules SET interval_count = 1, interval_unit = 'week' WHERE frequency = 'weekly'")
    op.execute("UPDATE recurring_rules SET interval_count = 2, interval_unit = 'week' WHERE frequency = 'biweekly'")
    op.execute("UPDATE recurring_rules SET interval_count = 1, interval_unit = 'year' WHERE frequency = 'yearly'")
 
    # 'daily' and 'custom' become valid names; the old rule only allowed four.
    op.execute("ALTER TABLE recurring_rules DROP CONSTRAINT IF EXISTS ck_recurring_rule_frequency")
    op.create_check_constraint(
        "ck_recurring_rule_frequency",
        "recurring_rules",
        "frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'yearly', 'custom')",
    )
    op.create_check_constraint(
        "ck_recurring_rule_interval_unit",
        "recurring_rules",
        "interval_unit IN ('day', 'week', 'month', 'year')",
    )
    op.create_check_constraint(
        "ck_recurring_rule_interval_count",
        "recurring_rules",
        "interval_count BETWEEN 1 AND 366",
    )


def downgrade() -> None:
    op.execute("UPDATE recurring_rules SET frequency = 'monthly' WHERE frequency IN ('daily', 'custom')")
 
    op.drop_constraint("ck_recurring_rule_interval_count", "recurring_rules", type_="check")
    op.drop_constraint("ck_recurring_rule_interval_unit", "recurring_rules", type_="check")
    op.drop_constraint("ck_recurring_rule_frequency", "recurring_rules", type_="check")
    op.create_check_constraint(
        "ck_recurring_rule_frequency",
        "recurring_rules",
        "frequency IN ('weekly', 'biweekly', 'monthly', 'yearly')",
    )
    op.drop_column("recurring_rules", "interval_unit")
    op.drop_column("recurring_rules", "interval_count")
