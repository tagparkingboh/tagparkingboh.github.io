"""Add heard about us marketing attribution feature

Revision ID: h34rd4b0ut
Revises: pr0m0fr33r3m
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h34rd4b0ut'
down_revision: Union[str, None] = 'pr0m0fr33r3m'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add has_answered_heard_about_us column to customers table
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'customers'
                          AND column_name = 'has_answered_heard_about_us') THEN
                ALTER TABLE customers ADD COLUMN has_answered_heard_about_us BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    """)

    # Create marketing_sources table
    op.execute("""
        CREATE TABLE IF NOT EXISTS marketing_sources (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL UNIQUE REFERENCES customers(id),
            source VARCHAR(50) NOT NULL,
            source_detail VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create index on customer_id for fast lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_marketing_sources_customer_id ON marketing_sources(customer_id);
    """)

    # Create marketing_source_monthly_totals table
    op.execute("""
        CREATE TABLE IF NOT EXISTS marketing_source_monthly_totals (
            id SERIAL PRIMARY KEY,
            year_month VARCHAR(7) NOT NULL,
            source VARCHAR(50) NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(year_month, source)
        );
    """)

    # Create index on year_month for fast queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_marketing_source_monthly_totals_year_month ON marketing_source_monthly_totals(year_month);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_marketing_source_monthly_totals_year_month;")
    op.execute("DROP TABLE IF EXISTS marketing_source_monthly_totals;")
    op.execute("DROP INDEX IF EXISTS ix_marketing_sources_customer_id;")
    op.execute("DROP TABLE IF EXISTS marketing_sources;")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS has_answered_heard_about_us;")
