"""add_capacity_tier_to_departures

Revision ID: c4p4c1ty0001
Revises: bed854b0395c
Create Date: 2025-12-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4p4c1ty0001'
down_revision: Union[str, Sequence[str], None] = 'bed854b0395c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: Replace boolean slot flags with capacity tier system.

    Old system: is_slot_1_booked, is_slot_2_booked (2 slots max)
    New system: capacity_tier (0,2,4,6,8) + slot counters
    """
    # Add new columns
    op.add_column('flight_departures',
        sa.Column('capacity_tier', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('flight_departures',
        sa.Column('slots_booked_early', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('flight_departures',
        sa.Column('slots_booked_late', sa.Integer(), nullable=False, server_default='0'))

    # Migrate existing data: if old slots were booked, set capacity_tier=2 and migrate booking counts
    # For existing flights with is_slot_1_booked=True, set slots_booked_early=1
    # For existing flights with is_slot_2_booked=True, set slots_booked_late=1
    # Set capacity_tier=2 for any flight that had the old boolean columns
    op.execute("""
        UPDATE flight_departures
        SET capacity_tier = 2,
            slots_booked_early = CASE WHEN is_slot_1_booked = TRUE THEN 1 ELSE 0 END,
            slots_booked_late = CASE WHEN is_slot_2_booked = TRUE THEN 1 ELSE 0 END
        WHERE is_slot_1_booked IS NOT NULL OR is_slot_2_booked IS NOT NULL
    """)

    # Drop old columns
    op.drop_column('flight_departures', 'is_slot_1_booked')
    op.drop_column('flight_departures', 'is_slot_2_booked')


def downgrade() -> None:
    """
    Downgrade schema: Revert to boolean slot flags.

    Note: This will lose capacity information beyond 2 slots.
    """
    # Add back old columns
    op.add_column('flight_departures',
        sa.Column('is_slot_1_booked', sa.Boolean(), default=False))
    op.add_column('flight_departures',
        sa.Column('is_slot_2_booked', sa.Boolean(), default=False))

    # Migrate data back: if slots_booked_early > 0, set is_slot_1_booked=True
    op.execute("""
        UPDATE flight_departures
        SET is_slot_1_booked = (slots_booked_early > 0),
            is_slot_2_booked = (slots_booked_late > 0)
    """)

    # Drop new columns
    op.drop_column('flight_departures', 'capacity_tier')
    op.drop_column('flight_departures', 'slots_booked_early')
    op.drop_column('flight_departures', 'slots_booked_late')
