"""Add thank_you_email tracking to bookings

Revision ID: th4nky0u
Revises: m1l34ck
Create Date: 2026-02-24 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'th4nky0u'
down_revision: Union[str, Sequence[str], None] = 'm1l34ck'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add thank you email tracking columns to bookings."""
    op.add_column('bookings', sa.Column('thank_you_email_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('bookings', sa.Column('thank_you_email_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bookings', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove thank you email tracking columns from bookings."""
    op.drop_column('bookings', 'completed_at')
    op.drop_column('bookings', 'thank_you_email_sent_at')
    op.drop_column('bookings', 'thank_you_email_sent')
