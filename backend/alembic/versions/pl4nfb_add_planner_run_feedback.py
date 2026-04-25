"""Add planner_run_feedback table for shadow-mode QA review

Per-shift, per-run feedback so QA can call out specific engine
*assignment* decisions (who, when, which bookings grouped) without
needing the full proposal serialised back. Denormalises the shift's
fingerprint (date + start/end time + staff_id) so feedback survives
even if the parent run row is later pruned, and so we can group
"all complaints about KW being assigned mornings" across runs by
(shift_staff_id, shift_start_time).

Revision ID: pl4nfb
Revises: pl4nner_run
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa


revision = 'pl4nfb'
down_revision = 'pl4nner_run'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'planner_run_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'run_id',
            sa.String(64),
            sa.ForeignKey('planner_runs.run_id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('shift_date', sa.Date(), nullable=False),
        sa.Column('shift_start_time', sa.Time(), nullable=True),
        sa.Column('shift_end_time', sa.Time(), nullable=True),
        sa.Column('shift_staff_id', sa.Integer(), nullable=True),
        sa.Column('proposed_shift_index', sa.Integer(), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column(
            'submitted_by',
            sa.Integer(),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
        sa.Column(
            'submitted_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_planner_run_feedback_run_id', 'planner_run_feedback', ['run_id'],
    )
    op.create_index(
        'ix_planner_run_feedback_shift_date', 'planner_run_feedback', ['shift_date'],
    )
    # Cross-run pattern detection ("KW always wrong on mornings") — composite.
    op.create_index(
        'ix_planner_run_feedback_fingerprint',
        'planner_run_feedback',
        ['shift_staff_id', 'shift_start_time'],
    )


def downgrade():
    op.drop_index('ix_planner_run_feedback_fingerprint', table_name='planner_run_feedback')
    op.drop_index('ix_planner_run_feedback_shift_date', table_name='planner_run_feedback')
    op.drop_index('ix_planner_run_feedback_run_id', table_name='planner_run_feedback')
    op.drop_table('planner_run_feedback')
