"""Add per-user window_overrun_minutes to users

Each jockey has their own end-of-shift elasticity — the engine assigns
them shifts that finish up to N minutes past their preferred_end_time.
Replaces the previous global PlannerSettings.window_overrun_minutes
(per-user is more honest and admin-controllable).

Default 60 min for every jockey; KA gets 150 (2.5h) per operational
guidance — they're the regular fallback driver for late finishes.

Revision ID: 0vrn0n
Revises: w1nd0w
Create Date: 2026-04-26

"""
from alembic import op


revision = '0vrn0n'
down_revision = 'w1nd0w'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE users ADD COLUMN window_overrun_minutes "
        "INTEGER NOT NULL DEFAULT 60"
    )
    op.execute("""
        UPDATE users
        SET window_overrun_minutes = 150
        WHERE first_name = 'Kristian' AND last_name = 'Andrews-Brown'
    """)


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS window_overrun_minutes")
