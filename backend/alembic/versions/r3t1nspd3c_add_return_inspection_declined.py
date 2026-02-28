"""Add return_inspection_declined to bookings

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
    """Add return_inspection_declined column to bookings."""
    op.add_column(
        'bookings',
        sa.Column('return_inspection_declined', sa.Boolean(), nullable=True, server_default='false')
    )


def downgrade() -> None:
    """Remove return_inspection_declined column from bookings."""
    op.drop_column('bookings', 'return_inspection_declined')
