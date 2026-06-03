"""add referral invite source

Revision ID: r3fs0urc3
Revises: p4rkupd
Create Date: 2026-06-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "r3fs0urc3"
down_revision = "p4rkupd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "referral_programs",
        sa.Column("invite_source", sa.String(length=20), nullable=False, server_default="booking"),
    )
    op.execute("""
        UPDATE referral_programs rp
        SET invite_source = 'social'
        WHERE NOT EXISTS (
            SELECT 1
            FROM bookings b
            WHERE b.customer_id = rp.customer_id
              AND lower(b.status::text) = 'completed'
        )
    """)


def downgrade():
    op.drop_column("referral_programs", "invite_source")
