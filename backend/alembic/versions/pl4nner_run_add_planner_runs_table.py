"""Add planner_runs audit table for shadow-mode engine runs

Shadow mode (the planner has not gone live yet — see backend/docs/SPEC.md
§ Roster Planner): the engine fires on booking / holiday / settings events
but NEVER writes to roster_shifts. Each invocation appends one row here so
QA can review what the engine would have produced before flipping to live
writes.

Append-only by convention (no UPDATE / DELETE paths in code). Indexes
support the QA UI's two access patterns: most-recent-first list, and
filter-by-trigger.

Revision ID: pl4nner_run
Revises: r0st3rpl
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa


revision = 'pl4nner_run'
down_revision = 'r0st3rpl'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'planner_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(64), nullable=False, unique=True),
        sa.Column(
            'triggered_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('trigger_event', sa.String(50), nullable=False),
        sa.Column('trigger_ref', sa.String(100), nullable=True),
        sa.Column('window_start', sa.Date(), nullable=False),
        sa.Column('window_end', sa.Date(), nullable=False),
        sa.Column('proposal_json', sa.Text(), nullable=True),
        sa.Column('diff_vs_current_json', sa.Text(), nullable=True),
        sa.Column('warnings_json', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('error_text', sa.Text(), nullable=True),
    )
    op.create_index(
        'ix_planner_runs_run_id', 'planner_runs', ['run_id'], unique=True,
    )
    op.create_index(
        'ix_planner_runs_triggered_at', 'planner_runs', ['triggered_at'],
    )
    op.create_index(
        'ix_planner_runs_trigger_event', 'planner_runs', ['trigger_event'],
    )


def downgrade():
    op.drop_index('ix_planner_runs_trigger_event', table_name='planner_runs')
    op.drop_index('ix_planner_runs_triggered_at', table_name='planner_runs')
    op.drop_index('ix_planner_runs_run_id', table_name='planner_runs')
    op.drop_table('planner_runs')
