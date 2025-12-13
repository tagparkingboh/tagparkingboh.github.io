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
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table('marketing_subscribers') as batch_op:
        batch_op.add_column(sa.Column('promo_code', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('promo_code_used', sa.Boolean(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('promo_code_used_booking_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('promo_code_used_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_marketing_subscribers_promo_code', ['promo_code'], unique=True)
        # Note: Foreign key is defined in model but not enforced at DB level for SQLite
        # PostgreSQL in production will use the model's FK constraint


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('marketing_subscribers') as batch_op:
        batch_op.drop_index('ix_marketing_subscribers_promo_code')
        batch_op.drop_column('promo_code_used_at')
        batch_op.drop_column('promo_code_used_booking_id')
        batch_op.drop_column('promo_code_used')
        batch_op.drop_column('promo_code')
