"""Add promo 10 reminder email tracking columns

Revision ID: pr0m010r3m
Revises: t3st1m0n1al
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'pr0m010r3m'
down_revision: Union[str, None] = 't3st1m0n1al'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Promo 10% reminder email tracking columns
    op.add_column('marketing_subscribers', sa.Column('promo_10_reminder_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_10_reminder_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('marketing_subscribers', 'promo_10_reminder_sent')
    op.drop_column('marketing_subscribers', 'promo_10_reminder_sent_at')
