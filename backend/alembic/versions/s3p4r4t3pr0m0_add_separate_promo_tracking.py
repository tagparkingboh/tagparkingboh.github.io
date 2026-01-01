"""Add separate promo tracking columns for 10% and FREE promos

Revision ID: s3p4r4t3pr0m0
Revises: p4ym3ntl1nk
Create Date: 2026-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's3p4r4t3pr0m0'
down_revision: Union[str, None] = 'p4ym3ntl1nk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 10% OFF Promo tracking columns
    op.add_column('marketing_subscribers', sa.Column('promo_10_code', sa.String(20), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_10_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_10_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_10_used', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_10_used_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_10_used_booking_id', sa.Integer(), nullable=True))

    # FREE Parking Promo tracking columns
    op.add_column('marketing_subscribers', sa.Column('promo_free_code', sa.String(20), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_free_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_free_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_free_used', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('marketing_subscribers', sa.Column('promo_free_used_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('marketing_subscribers', sa.Column('promo_free_used_booking_id', sa.Integer(), nullable=True))

    # Create unique indexes for the new promo codes
    op.create_index('ix_marketing_subscribers_promo_10_code', 'marketing_subscribers', ['promo_10_code'], unique=True)
    op.create_index('ix_marketing_subscribers_promo_free_code', 'marketing_subscribers', ['promo_free_code'], unique=True)

    # Create foreign key constraints
    op.create_foreign_key(
        'fk_marketing_subscribers_promo_10_booking',
        'marketing_subscribers', 'bookings',
        ['promo_10_used_booking_id'], ['id']
    )
    op.create_foreign_key(
        'fk_marketing_subscribers_promo_free_booking',
        'marketing_subscribers', 'bookings',
        ['promo_free_used_booking_id'], ['id']
    )


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint('fk_marketing_subscribers_promo_10_booking', 'marketing_subscribers', type_='foreignkey')
    op.drop_constraint('fk_marketing_subscribers_promo_free_booking', 'marketing_subscribers', type_='foreignkey')

    # Drop indexes
    op.drop_index('ix_marketing_subscribers_promo_10_code', table_name='marketing_subscribers')
    op.drop_index('ix_marketing_subscribers_promo_free_code', table_name='marketing_subscribers')

    # Drop 10% promo columns
    op.drop_column('marketing_subscribers', 'promo_10_code')
    op.drop_column('marketing_subscribers', 'promo_10_sent')
    op.drop_column('marketing_subscribers', 'promo_10_sent_at')
    op.drop_column('marketing_subscribers', 'promo_10_used')
    op.drop_column('marketing_subscribers', 'promo_10_used_at')
    op.drop_column('marketing_subscribers', 'promo_10_used_booking_id')

    # Drop FREE promo columns
    op.drop_column('marketing_subscribers', 'promo_free_code')
    op.drop_column('marketing_subscribers', 'promo_free_sent')
    op.drop_column('marketing_subscribers', 'promo_free_sent_at')
    op.drop_column('marketing_subscribers', 'promo_free_used')
    op.drop_column('marketing_subscribers', 'promo_free_used_at')
    op.drop_column('marketing_subscribers', 'promo_free_used_booking_id')
