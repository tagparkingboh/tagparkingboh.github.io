"""Add override_json to planner_run_feedback

Lets QA reviewers attach a structured "what I would have done" override
alongside the existing severity + comment. JSON blob (TEXT) so we don't
churn the schema as override fields evolve. Initial shape captured by
the modal:
    {"staff_id": 7, "start_time": "07:30:00", "end_time": "11:00:00"}
All fields optional. Engine doesn't read this — it's QA-side
structured feedback for shadow-mode review.

Revision ID: pl4nfb_o
Revises: pl4nfb
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'pl4nfb_o'
down_revision = 'pl4nfb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'planner_run_feedback',
        sa.Column('override_json', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('planner_run_feedback', 'override_json')
