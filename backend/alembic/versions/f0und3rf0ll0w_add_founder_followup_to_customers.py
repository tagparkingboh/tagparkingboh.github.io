"""Add founder followup fields to customers

Revision ID: f0und3rf0ll0w
Revises: pr1c1ngs3tt1ngs
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0und3rf0ll0w'
down_revision = 'r3t1nspd3c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add founder follow-up email tracking fields to customers table
    op.add_column('customers', sa.Column('founder_followup_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('customers', sa.Column('founder_followup_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'founder_followup_sent_at')
    op.drop_column('customers', 'founder_followup_sent')
