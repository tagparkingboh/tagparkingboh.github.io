"""Add button_text_color to promo_modals

Revision ID: pr0m0btntxt
Revises: pr0m0m0dal
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pr0m0btntxt'
down_revision = 'pr0m0m0dal'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('promo_modals', sa.Column('button_text_color', sa.String(20), nullable=True, server_default='#ffffff'))


def downgrade():
    op.drop_column('promo_modals', 'button_text_color')
