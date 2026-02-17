"""Add reminder_2day_sent to bookings

Revision ID: e956ff986452
Revises: 6f21f43ac53c
Create Date: 2026-02-17 14:13:58.145050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e956ff986452'
down_revision: Union[str, Sequence[str], None] = '6f21f43ac53c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bookings', sa.Column('reminder_2day_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('reminder_2day_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bookings', 'reminder_2day_sent_at')
    op.drop_column('bookings', 'reminder_2day_sent')
