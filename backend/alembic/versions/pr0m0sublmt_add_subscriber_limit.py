"""Add subscriber limit fields to promo_modals

Revision ID: pr0m0sublmt
Revises: pr0m0btntxt
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pr0m0sublmt'
down_revision = 'pr0m0btntxt'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('promo_modals', sa.Column('max_subscribers', sa.Integer(), nullable=True))
    op.add_column('promo_modals', sa.Column('subscribers_at_activation', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('promo_modals', 'subscribers_at_activation')
    op.drop_column('promo_modals', 'max_subscribers')
