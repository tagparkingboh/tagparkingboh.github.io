"""Add declined column to vehicle_inspections

Revision ID: r3t1nspd3c
Revises: fl1ghth1st
Create Date: 2026-02-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'r3t1nspd3c'
down_revision: Union[str, Sequence[str], None] = 'fl1ghth1st'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add declined column to vehicle_inspections.

    This allows marking return inspections as declined by customer,
    enabling booking completion without a full inspection.
    """
    op.add_column(
        'vehicle_inspections',
        sa.Column('declined', sa.Boolean(), nullable=True, server_default='false')
    )


def downgrade() -> None:
    """Remove declined column from vehicle_inspections."""
    op.drop_column('vehicle_inspections', 'declined')
