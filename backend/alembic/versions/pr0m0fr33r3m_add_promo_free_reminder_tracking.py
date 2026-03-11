"""Add promo free reminder email tracking columns

Revision ID: pr0m0fr33r3m
Revises: pr0m010r3m
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'pr0m0fr33r3m'
down_revision: Union[str, None] = 'pr0m010r3m'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FREE Parking promo reminder email tracking columns
    # Use raw SQL with IF NOT EXISTS to handle cases where columns already exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'marketing_subscribers'
                          AND column_name = 'promo_free_reminder_sent') THEN
                ALTER TABLE marketing_subscribers ADD COLUMN promo_free_reminder_sent BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'marketing_subscribers'
                          AND column_name = 'promo_free_reminder_sent_at') THEN
                ALTER TABLE marketing_subscribers ADD COLUMN promo_free_reminder_sent_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column('marketing_subscribers', 'promo_free_reminder_sent')
    op.drop_column('marketing_subscribers', 'promo_free_reminder_sent_at')
