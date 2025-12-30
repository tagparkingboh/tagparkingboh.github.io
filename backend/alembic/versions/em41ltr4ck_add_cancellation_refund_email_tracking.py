"""add_cancellation_refund_email_tracking

Revision ID: em41ltr4ck01
Revises: d3p4rtur30001
Create Date: 2025-12-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'em41ltr4ck01'
down_revision: Union[str, Sequence[str], None] = 'd3p4rtur30001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add cancellation and refund email tracking columns to bookings table.

    These columns track when cancellation and refund emails are sent,
    similar to the existing confirmation_email_sent tracking.
    """
    op.add_column('bookings',
        sa.Column('cancellation_email_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings',
        sa.Column('cancellation_email_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bookings',
        sa.Column('refund_email_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings',
        sa.Column('refund_email_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove cancellation and refund email tracking columns from bookings table."""
    op.drop_column('bookings', 'refund_email_sent_at')
    op.drop_column('bookings', 'refund_email_sent')
    op.drop_column('bookings', 'cancellation_email_sent_at')
    op.drop_column('bookings', 'cancellation_email_sent')
