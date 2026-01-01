"""add_departure_id_to_bookings

Revision ID: d3p4rtur30001
Revises: c4p4c1ty0001
Create Date: 2025-12-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3p4rtur30001'
down_revision: Union[str, Sequence[str], None] = 'c4p4c1ty0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add departure_id and dropoff_slot columns to bookings table.

    These columns store the flight departure ID and slot type (early/late)
    so we can properly release the slot when a booking is cancelled.
    """
    op.add_column('bookings',
        sa.Column('departure_id', sa.Integer(), sa.ForeignKey('flight_departures.id'), nullable=True))
    op.add_column('bookings',
        sa.Column('dropoff_slot', sa.String(10), nullable=True))

    # Create index on departure_id for faster lookups
    op.create_index('ix_bookings_departure_id', 'bookings', ['departure_id'])


def downgrade() -> None:
    """Remove departure_id and dropoff_slot columns from bookings table."""
    op.drop_index('ix_bookings_departure_id', 'bookings')
    op.drop_column('bookings', 'dropoff_slot')
    op.drop_column('bookings', 'departure_id')
