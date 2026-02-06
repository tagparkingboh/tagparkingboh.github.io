"""Add flexible duration pricing columns to pricing_settings

Revision ID: fl3xpr1c3
Revises: cust_sign
Create Date: 2026-02-06

New pricing tiers by duration:
- 1-4 days: £60 base
- 5-6 days: £72 base
- 7 days: £79 base (updated from £89)
- 8-9 days: £99 base
- 10-11 days: £119 base
- 12-13 days: £130 base
- 14 days: £140 base

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fl3xpr1c3'
down_revision: Union[str, None] = 'cust_sign'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = :table_name AND column_name = :column_name)"
    ), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade() -> None:
    # Add new duration-based pricing columns
    if not column_exists('pricing_settings', 'days_1_4_price'):
        op.add_column('pricing_settings', sa.Column('days_1_4_price', sa.Numeric(10, 2), nullable=False, server_default='60.00'))

    if not column_exists('pricing_settings', 'days_5_6_price'):
        op.add_column('pricing_settings', sa.Column('days_5_6_price', sa.Numeric(10, 2), nullable=False, server_default='72.00'))

    if not column_exists('pricing_settings', 'days_8_9_price'):
        op.add_column('pricing_settings', sa.Column('days_8_9_price', sa.Numeric(10, 2), nullable=False, server_default='99.00'))

    if not column_exists('pricing_settings', 'days_10_11_price'):
        op.add_column('pricing_settings', sa.Column('days_10_11_price', sa.Numeric(10, 2), nullable=False, server_default='119.00'))

    if not column_exists('pricing_settings', 'days_12_13_price'):
        op.add_column('pricing_settings', sa.Column('days_12_13_price', sa.Numeric(10, 2), nullable=False, server_default='130.00'))

    # Update week1_base_price default from £89 to £79
    # This also updates any existing rows to the new default
    op.execute("UPDATE pricing_settings SET week1_base_price = 79.00 WHERE week1_base_price = 89.00")


def downgrade() -> None:
    # Revert week1_base_price back to £89
    op.execute("UPDATE pricing_settings SET week1_base_price = 89.00 WHERE week1_base_price = 79.00")

    # Drop new columns
    op.drop_column('pricing_settings', 'days_1_4_price')
    op.drop_column('pricing_settings', 'days_5_6_price')
    op.drop_column('pricing_settings', 'days_8_9_price')
    op.drop_column('pricing_settings', 'days_10_11_price')
    op.drop_column('pricing_settings', 'days_12_13_price')
