"""Add manual flight entry fields to bookings

Revision ID: m4nu4lfl1
Revises: th4nky0u
Create Date: 2026-02-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm4nu4lfl1'
down_revision: Union[str, Sequence[str], None] = 'th4nky0u'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fields for customer-provided flight times and manual flight entry."""

    # Departure time override (when customer corrects time for existing flight)
    op.add_column('bookings', sa.Column('dropoff_time_override', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('dropoff_scheduled_time', sa.Time(), nullable=True))

    # Manual departure entry (when flight not in system)
    op.add_column('bookings', sa.Column('dropoff_manual_entry', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('dropoff_airline_code', sa.String(10), nullable=True))
    op.add_column('bookings', sa.Column('dropoff_airline_name', sa.String(100), nullable=True))

    # Pickup/arrival time override (when customer corrects arrival time)
    op.add_column('bookings', sa.Column('pickup_time_override', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('pickup_scheduled_time', sa.Time(), nullable=True))

    # Manual arrival entry (when return flight not in system)
    op.add_column('bookings', sa.Column('pickup_manual_entry', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('pickup_airline_code', sa.String(10), nullable=True))
    op.add_column('bookings', sa.Column('pickup_airline_name', sa.String(100), nullable=True))


def downgrade() -> None:
    """Remove manual flight entry fields from bookings."""
    op.drop_column('bookings', 'pickup_airline_name')
    op.drop_column('bookings', 'pickup_airline_code')
    op.drop_column('bookings', 'pickup_manual_entry')
    op.drop_column('bookings', 'pickup_scheduled_time')
    op.drop_column('bookings', 'pickup_time_override')
    op.drop_column('bookings', 'dropoff_airline_name')
    op.drop_column('bookings', 'dropoff_airline_code')
    op.drop_column('bookings', 'dropoff_manual_entry')
    op.drop_column('bookings', 'dropoff_scheduled_time')
    op.drop_column('bookings', 'dropoff_time_override')
