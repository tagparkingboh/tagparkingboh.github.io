"""add_promo_code_columns_to_marketing_subscribers

Revision ID: 2e255cc8b15c
Revises: 0b1751152310
Create Date: 2025-12-11 10:05:39.948528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e255cc8b15c'
down_revision: Union[str, Sequence[str], None] = '0b1751152310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('marketing_subscribers', sa.Column('promo_code', sa.String(20), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_code_used', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_code_used_booking_id', sa.Integer(), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_code_used_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_marketing_subscribers_promo_code', 'marketing_subscribers', ['promo_code'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_marketing_subscribers_promo_code', table_name='marketing_subscribers')
    op.drop_column('marketing_subscribers', 'promo_code_used_at')
    op.drop_column('marketing_subscribers', 'promo_code_used_booking_id')
    op.drop_column('marketing_subscribers', 'promo_code_used')
    op.drop_column('marketing_subscribers', 'promo_code')
