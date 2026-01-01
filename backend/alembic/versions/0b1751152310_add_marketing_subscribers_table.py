"""add_marketing_subscribers_table

Revision ID: 0b1751152310
Revises: a1b2c3d4e5f6
Create Date: 2025-12-11 02:12:47.101411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b1751152310'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'marketing_subscribers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('subscribed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_marketing_subscribers_email', 'marketing_subscribers', ['email'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_marketing_subscribers_email', table_name='marketing_subscribers')
    op.drop_table('marketing_subscribers')
