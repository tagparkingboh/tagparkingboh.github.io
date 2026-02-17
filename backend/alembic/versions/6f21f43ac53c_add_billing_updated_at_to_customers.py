"""Add billing_updated_at to customers

Revision ID: 6f21f43ac53c
Revises: arr1v4l1d
Create Date: 2026-02-16 22:13:50.014713

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f21f43ac53c'
down_revision: Union[str, Sequence[str], None] = 'arr1v4l1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('customers', sa.Column('billing_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('customers', 'billing_updated_at')
