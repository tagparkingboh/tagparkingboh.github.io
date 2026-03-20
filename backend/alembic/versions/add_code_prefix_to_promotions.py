"""Add code_prefix to promotions

Revision ID: add_code_prefix
Revises:
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_code_prefix'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add code_prefix column to promotions table with default value 'TAG'
    op.add_column('promotions', sa.Column('code_prefix', sa.String(10), nullable=False, server_default='TAG'))


def downgrade():
    op.drop_column('promotions', 'code_prefix')
