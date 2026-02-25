"""Add flight history tables for audit trail

Revision ID: fl1ghth1st
Revises: m4nu4lfl1
Create Date: 2026-02-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fl1ghth1st'
down_revision: Union[str, Sequence[str], None] = 'm4nu4lfl1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create flight history tables for tracking changes."""

    # Flight departure history table
    op.create_table(
        'flight_departure_history',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('flight_id', sa.Integer(), sa.ForeignKey('flight_departures.id'), nullable=False, index=True),

        # Snapshot of flight data
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('flight_number', sa.String(20), nullable=False),
        sa.Column('airline_code', sa.String(10), nullable=False),
        sa.Column('airline_name', sa.String(100), nullable=False),
        sa.Column('departure_time', sa.Time(), nullable=False),
        sa.Column('destination_code', sa.String(10), nullable=False),
        sa.Column('destination_name', sa.String(100), nullable=True),
        sa.Column('capacity_tier', sa.Integer(), nullable=False),
        sa.Column('slots_booked_early', sa.Integer(), nullable=False),
        sa.Column('slots_booked_late', sa.Integer(), nullable=False),

        # Change metadata
        sa.Column('change_type', sa.String(20), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('changed_by', sa.String(100), nullable=True),
    )

    # Flight arrival history table
    op.create_table(
        'flight_arrival_history',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('flight_id', sa.Integer(), sa.ForeignKey('flight_arrivals.id'), nullable=False, index=True),

        # Snapshot of flight data
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('flight_number', sa.String(20), nullable=False),
        sa.Column('airline_code', sa.String(10), nullable=False),
        sa.Column('airline_name', sa.String(100), nullable=False),
        sa.Column('departure_time', sa.Time(), nullable=True),
        sa.Column('arrival_time', sa.Time(), nullable=False),
        sa.Column('origin_code', sa.String(10), nullable=False),
        sa.Column('origin_name', sa.String(100), nullable=True),

        # Change metadata
        sa.Column('change_type', sa.String(20), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('changed_by', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    """Remove flight history tables."""
    op.drop_table('flight_arrival_history')
    op.drop_table('flight_departure_history')
