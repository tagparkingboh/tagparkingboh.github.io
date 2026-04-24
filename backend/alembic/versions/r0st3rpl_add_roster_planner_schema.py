"""Add roster planner schema (additive)

Adds:
  - users.preferred_shift_types  (shifttype[] array — soft preferences per staff)
  - users.auto_assign_excluded   (bool — Mark Custard / John Penney / anyone excluded)
  - roster_planner_settings      (key/value settings table, editable from QA tab)
  - roster_shifts.created_source (varchar — 'manual' | 'planner', default 'manual')
  - roster_shifts.planner_run_id (varchar — run uuid for audit / undo; nullable)

All additive. Zero impact on present behaviour — existing code ignores new columns.

Revision ID: r0st3rpl
Revises: m4rk3m41l
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa


revision = 'r0st3rpl'
down_revision = 'm4rk3m41l'
branch_labels = None
depends_on = None


def upgrade():
    # Additive columns on users — preferences + auto-assign exclusion
    # Array of the existing `shifttype` enum; default empty array = "flexible".
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS preferred_shift_types shifttype[] NOT NULL DEFAULT '{}'
    """)
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS auto_assign_excluded boolean NOT NULL DEFAULT false
    """)

    # Key/value settings table — keeps schema flexible while the rules evolve
    op.create_table(
        'roster_planner_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True),
        sa.Column('value_json', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index(
        'ix_roster_planner_settings_key',
        'roster_planner_settings',
        ['key'],
        unique=True,
    )

    # Audit tags on roster_shifts — lets the engine mark its own rows and enable undo
    op.execute("""
        ALTER TABLE roster_shifts
        ADD COLUMN IF NOT EXISTS created_source varchar(50) NOT NULL DEFAULT 'manual'
    """)
    op.execute("""
        ALTER TABLE roster_shifts
        ADD COLUMN IF NOT EXISTS planner_run_id varchar(64)
    """)
    op.create_index(
        'ix_roster_shifts_planner_run_id',
        'roster_shifts',
        ['planner_run_id'],
    )


def downgrade():
    op.drop_index('ix_roster_shifts_planner_run_id', table_name='roster_shifts')
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS planner_run_id")
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS created_source")

    op.drop_index('ix_roster_planner_settings_key', table_name='roster_planner_settings')
    op.drop_table('roster_planner_settings')

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auto_assign_excluded")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_shift_types")
