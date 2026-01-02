"""Add first_name and last_name to marketing_subscribers

Revision ID: n4m3f13lds
Revises: p1ckupt1m3
Create Date: 2026-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n4m3f13lds'
down_revision: Union[str, None] = 'p1ckupt1m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add first_name and last_name columns
    # Using nullable=True initially, then we can backfill existing records
    op.add_column('marketing_subscribers', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('last_name', sa.String(100), nullable=True))

    # Also add welcome_email_sent if it doesn't exist
    op.add_column('marketing_subscribers', sa.Column('welcome_email_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('welcome_email_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('marketing_subscribers', 'welcome_email_sent_at')
    op.drop_column('marketing_subscribers', 'welcome_email_sent')
    op.drop_column('marketing_subscribers', 'last_name')
    op.drop_column('marketing_subscribers', 'first_name')
