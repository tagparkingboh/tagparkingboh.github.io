"""Add multi-use promo code fields and usage tracking table

Revision ID: mult1us3
Revises: pr0m0sublmt
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'mult1us3'
down_revision = 'pr0m0sublmt'
branch_labels = None
depends_on = None


def upgrade():
    # Add multi-use fields to promo_codes table
    op.add_column('promo_codes', sa.Column('max_uses', sa.Integer(), nullable=True))
    op.add_column('promo_codes', sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'))

    # Create promo_code_usages table for tracking each usage of multi-use codes
    op.create_table(
        'promo_code_usages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('promo_code_id', sa.Integer(), sa.ForeignKey('promo_codes.id'), nullable=False, index=True),
        sa.Column('booking_id', sa.Integer(), sa.ForeignKey('bookings.id'), nullable=False, index=True),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('discount_amount_pence', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('promo_code_usages')
    op.drop_column('promo_codes', 'use_count')
    op.drop_column('promo_codes', 'max_uses')
