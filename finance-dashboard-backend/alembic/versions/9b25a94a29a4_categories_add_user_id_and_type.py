"""categories: add user_id and type

Revision ID: 9b25a94a29a4
Revises: 27213b404894
Create Date: 2026-09-28 17:04:23.977973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b25a94a29a4'
down_revision: Union[str, Sequence[str], None] = '27213b404894'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('categories', sa.Column('user_id', sa.UUID(), nullable=True))
    op.add_column('categories', sa.Column('type', sa.String(), server_default='expense', nullable=False))
    op.create_foreign_key('fk_categories_user_id_users', 'categories', 'users', ['user_id'], ['id'])
    op.create_check_constraint(
        'ck_category_type', 'categories', "type IN ('income', 'expense', 'transfer')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_category_type', 'categories', type_='check')
    op.drop_constraint('fk_categories_user_id_users', 'categories', type_='foreignkey')
    op.drop_column('categories', 'type')
    op.drop_column('categories', 'user_id')
