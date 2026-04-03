"""Add is_read field to sms_messages for thread support

Revision ID: sms_threads_001
Revises: None
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sms_threads_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_read column to sms_messages
    # Default to True for outbound messages (we sent them, so we've "read" them)
    # Default to False for inbound messages (unread)
    op.add_column('sms_messages', sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'))

    # Mark all existing outbound messages as read (we sent them)
    op.execute("UPDATE sms_messages SET is_read = true WHERE direction = 'outbound'")

    # Mark all existing inbound messages as read (legacy - assume admin has seen them)
    op.execute("UPDATE sms_messages SET is_read = true WHERE direction = 'inbound'")


def downgrade() -> None:
    op.drop_column('sms_messages', 'is_read')
