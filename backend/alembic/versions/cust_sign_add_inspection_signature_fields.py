"""Add customer_name and signed_date to vehicle_inspections

Revision ID: cust_sign
Revises: v3h1cl31nsp
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cust_sign'
down_revision: Union[str, None] = 'v3h1cl31nsp'
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
    if not column_exists('vehicle_inspections', 'customer_name'):
        op.add_column('vehicle_inspections', sa.Column('customer_name', sa.String(200), nullable=True))
    if not column_exists('vehicle_inspections', 'signed_date'):
        op.add_column('vehicle_inspections', sa.Column('signed_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('vehicle_inspections', 'signed_date')
    op.drop_column('vehicle_inspections', 'customer_name')
