"""Add soft-suppression fields to roster_shifts

Revision ID: supr0st
Revises: r3fs0urc3
Create Date: 2026-06-09

"""
from alembic import op
import sqlalchemy as sa


revision = "supr0st"
down_revision = "r3fs0urc3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "roster_shifts",
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "roster_shifts",
        sa.Column("suppressed_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "roster_shifts",
        sa.Column("suppression_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_roster_shifts_suppressed_by_user_id_users",
        "roster_shifts",
        "users",
        ["suppressed_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_roster_shifts_suppressed_at",
        "roster_shifts",
        ["suppressed_at"],
    )


def downgrade():
    op.drop_index("ix_roster_shifts_suppressed_at", table_name="roster_shifts")
    op.drop_constraint(
        "fk_roster_shifts_suppressed_by_user_id_users",
        "roster_shifts",
        type_="foreignkey",
    )
    op.drop_column("roster_shifts", "suppression_reason")
    op.drop_column("roster_shifts", "suppressed_by_user_id")
    op.drop_column("roster_shifts", "suppressed_at")
