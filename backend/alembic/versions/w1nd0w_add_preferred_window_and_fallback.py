"""Add preferred_start_time, preferred_end_time, is_fallback_driver to users

Phase 3 of the Roster Planner staff data model:
- preferred_start_time / preferred_end_time (TIME) — each driver's working
  window. The engine assigns shifts whose [start, end] is fully contained
  in the driver's window. Replaces the bucket-based excluded_shift_types
  / preferred_shift_types columns as the primary eligibility signal
  (those columns remain on the table but are no longer read by the engine).
- is_fallback_driver (BOOL) — true for drivers who only work when no
  primary driver is available (e.g. KA covers when MS or KW is off).

Backfill values for the three known jockeys:
- MS (Marek Smolarek):  03:00-12:00, primary
- KA (Kristian AB):     09:00-17:00, fallback
- KW (Karl Walden):     16:00-01:00 (next day), primary

A NULL window means "no window configured" — engine treats those drivers
as having an always-open window, preserving prior behaviour for any
jockey not yet migrated.

Revision ID: w1nd0w
Revises: jocky4ll
Create Date: 2026-04-26

"""
from alembic import op


revision = 'w1nd0w'
down_revision = 'jocky4ll'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN preferred_start_time TIME")
    op.execute("ALTER TABLE users ADD COLUMN preferred_end_time TIME")
    op.execute("ALTER TABLE users ADD COLUMN is_fallback_driver BOOLEAN NOT NULL DEFAULT FALSE")

    # Backfill the three current jockeys. Match by (first_name, last_name)
    # rather than id so the migration is portable across environments.
    op.execute("""
        UPDATE users
        SET preferred_start_time = '03:00',
            preferred_end_time   = '12:00',
            is_fallback_driver   = FALSE
        WHERE first_name = 'Marek' AND last_name = 'Smolarek'
    """)
    op.execute("""
        UPDATE users
        SET preferred_start_time = '09:00',
            preferred_end_time   = '17:00',
            is_fallback_driver   = TRUE
        WHERE first_name = 'Kristian' AND last_name = 'Andrews-Brown'
    """)
    op.execute("""
        UPDATE users
        SET preferred_start_time = '16:00',
            preferred_end_time   = '01:00',
            is_fallback_driver   = FALSE
        WHERE first_name = 'Karl' AND last_name = 'Walden'
    """)


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_fallback_driver")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_end_time")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_start_time")
