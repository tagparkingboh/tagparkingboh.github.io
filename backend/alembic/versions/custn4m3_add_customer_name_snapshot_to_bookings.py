"""Add customer_first_name and customer_last_name snapshot columns to bookings

Revision ID: custn4m3
Revises: p1ckupt1m3
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'custn4m3'
down_revision: Union[str, None] = 'n4m3f13lds'
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
    # Add snapshot columns for customer name at time of booking
    if not column_exists('bookings', 'customer_first_name'):
        op.add_column('bookings', sa.Column('customer_first_name', sa.String(100), nullable=True))
    if not column_exists('bookings', 'customer_last_name'):
        op.add_column('bookings', sa.Column('customer_last_name', sa.String(100), nullable=True))

    # Backfill existing bookings with current customer names
    op.execute(sa.text("""
        UPDATE bookings
        SET customer_first_name = customers.first_name,
            customer_last_name = customers.last_name
        FROM customers
        WHERE bookings.customer_id = customers.id
        AND bookings.customer_first_name IS NULL
    """))


def downgrade() -> None:
    op.drop_column('bookings', 'customer_last_name')
    op.drop_column('bookings', 'customer_first_name')
