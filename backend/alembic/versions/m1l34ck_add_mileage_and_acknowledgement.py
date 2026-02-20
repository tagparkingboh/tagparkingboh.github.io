"""Add mileage and acknowledgement_confirmed to vehicle_inspections

Revision ID: m1l34ck
Revises: e956ff986452
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm1l34ck'
down_revision: Union[str, None] = 'e956ff986452'
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
    """Add mileage and acknowledgement_confirmed columns."""
    if not column_exists('vehicle_inspections', 'mileage'):
        op.add_column('vehicle_inspections', sa.Column('mileage', sa.Integer(), nullable=True))
    if not column_exists('vehicle_inspections', 'acknowledgement_confirmed'):
        op.add_column('vehicle_inspections', sa.Column('acknowledgement_confirmed', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    """Remove mileage and acknowledgement_confirmed columns."""
    op.drop_column('vehicle_inspections', 'acknowledgement_confirmed')
    op.drop_column('vehicle_inspections', 'mileage')
