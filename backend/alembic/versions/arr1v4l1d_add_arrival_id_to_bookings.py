"""add_arrival_id_to_bookings

Revision ID: arr1v4l1d
Revises: fl3xpr1c3
Create Date: 2026-02-08

Add arrival_id column to bookings table to link bookings to return flights.
This enables automatic recalculation of pickup times when arrival times change.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'arr1v4l1d'
down_revision: Union[str, Sequence[str], None] = 'fl3xpr1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add arrival_id column to bookings table.

    This column stores the flight arrival ID so we can recalculate
    pickup times when arrival times change due to schedule updates.
    """
    op.add_column('bookings',
        sa.Column('arrival_id', sa.Integer(), sa.ForeignKey('flight_arrivals.id'), nullable=True))

    # Create index on arrival_id for faster lookups
    op.create_index('ix_bookings_arrival_id', 'bookings', ['arrival_id'])


def downgrade() -> None:
    """Remove arrival_id column from bookings table."""
    op.drop_index('ix_bookings_arrival_id', 'bookings')
    op.drop_column('bookings', 'arrival_id')
