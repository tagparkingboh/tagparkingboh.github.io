"""Add driver_type, preferred_days_off, excluded_shift_types to users

Phase 2 of the Roster Planner staff data model:
- driver_type enum (jockey | fleet) — engine only auto-assigns jockeys
- preferred_days_off integer[] (0=Mon..6=Sun) — hard exclude per-day
- excluded_shift_types shifttype[] — hard exclude per shift type
  (e.g. KW never on earlies, MS never on lates)

All additive, rollback-safe. The shifttype enum already exists from
the r0st3rpl migration.

Revision ID: jocky4ll
Revises: pl4nfb_o
Create Date: 2026-04-26

"""
from alembic import op


revision = 'jocky4ll'
down_revision = 'pl4nfb_o'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TYPE driver_type AS ENUM ('jockey', 'fleet')")
    op.execute("ALTER TABLE users ADD COLUMN driver_type driver_type")
    op.execute("ALTER TABLE users ADD COLUMN preferred_days_off integer[] NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE users ADD COLUMN excluded_shift_types shifttype[] NOT NULL DEFAULT '{}'")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS excluded_shift_types")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_days_off")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS driver_type")
    op.execute("DROP TYPE IF EXISTS driver_type")
