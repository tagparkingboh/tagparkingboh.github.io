"""add_unsubscribe_fields_to_marketing_subscribers

Revision ID: bed854b0395c
Revises: 2e255cc8b15c
Create Date: 2025-12-17 15:28:29.716990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bed854b0395c'
down_revision: Union[str, Sequence[str], None] = '2e255cc8b15c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table('marketing_subscribers') as batch_op:
        batch_op.add_column(sa.Column('unsubscribe_token', sa.String(64), nullable=True))
        batch_op.add_column(sa.Column('unsubscribed', sa.Boolean(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_marketing_subscribers_unsubscribe_token', ['unsubscribe_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('marketing_subscribers') as batch_op:
        batch_op.drop_index('ix_marketing_subscribers_unsubscribe_token')
        batch_op.drop_column('unsubscribed_at')
        batch_op.drop_column('unsubscribed')
        batch_op.drop_column('unsubscribe_token')
