"""Add promo_modals table

Revision ID: pr0m0m0dal
Revises: 8f777041b0a8
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pr0m0m0dal'
down_revision = '8f777041b0a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'promo_modals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('button_text', sa.String(50), nullable=True, server_default='Subscribe'),
        sa.Column('button_action', sa.String(50), nullable=True, server_default='subscribe'),
        sa.Column('button_link', sa.String(500), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('background_color', sa.String(20), nullable=True, server_default='#1e3a5f'),
        sa.Column('text_color', sa.String(20), nullable=True, server_default='#ffffff'),
        sa.Column('button_color', sa.String(20), nullable=True, server_default='#22c55e'),
        sa.Column('button_text_color', sa.String(20), nullable=True, server_default='#ffffff'),
        sa.Column('status', sa.Enum('active', 'inactive', 'scheduled', name='promomodalstatus'), nullable=False, server_default='inactive'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('click_count', sa.Integer(), nullable=True, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_promo_modals_id'), 'promo_modals', ['id'], unique=False)
    op.create_index(op.f('ix_promo_modals_status'), 'promo_modals', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_promo_modals_status'), table_name='promo_modals')
    op.drop_index(op.f('ix_promo_modals_id'), table_name='promo_modals')
    op.drop_table('promo_modals')
    op.execute("DROP TYPE IF EXISTS promomodalstatus")
