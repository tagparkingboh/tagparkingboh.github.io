"""Add pickup_time_from and pickup_time_to columns to bookings

Revision ID: p1ckupt1m3
Revises: us3r4uth0001
Create Date: 2026-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p1ckupt1m3'
down_revision: Union[str, None] = 'us3r4uth0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = :table_name AND column_name = :column_name)"
    ), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade() -> None:
    if not column_exists('bookings', 'pickup_time_from'):
        op.add_column('bookings', sa.Column('pickup_time_from', sa.Time(), nullable=True))
    if not column_exists('bookings', 'pickup_time_to'):
        op.add_column('bookings', sa.Column('pickup_time_to', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('bookings', 'pickup_time_to')
    op.drop_column('bookings', 'pickup_time_from')
