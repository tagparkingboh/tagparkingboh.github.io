"""Add shift duplicate dependency fields

Revision ID: shftpool
Revises: supr0st
Create Date: 2026-06-17

"""
from alembic import op


revision = "shftpool"
down_revision = "supr0st"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE roster_shifts
        ADD COLUMN IF NOT EXISTS parent_shift_id integer
    """)
    op.execute("""
        ALTER TABLE roster_shifts
        ADD COLUMN IF NOT EXISTS dependents_independent boolean NOT NULL DEFAULT false
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_roster_shifts_parent_shift_id_roster_shifts'
            ) THEN
                ALTER TABLE roster_shifts
                ADD CONSTRAINT fk_roster_shifts_parent_shift_id_roster_shifts
                FOREIGN KEY (parent_shift_id)
                REFERENCES roster_shifts(id)
                ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_roster_shifts_parent_shift_id
        ON roster_shifts(parent_shift_id)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_roster_shifts_parent_shift_id")
    op.execute("""
        ALTER TABLE roster_shifts
        DROP CONSTRAINT IF EXISTS fk_roster_shifts_parent_shift_id_roster_shifts
    """)
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS dependents_independent")
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS parent_shift_id")
