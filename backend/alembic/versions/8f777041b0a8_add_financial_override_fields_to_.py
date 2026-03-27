"""Add financial override fields to bookings

Revision ID: 8f777041b0a8
Revises: h34rd4b0ut
Create Date: 2026-03-26 21:39:37.336110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8f777041b0a8'
down_revision: Union[str, Sequence[str], None] = 'h34rd4b0ut'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add override fields for financial reporting."""
    op.add_column('bookings', sa.Column('override_gross_pence', sa.Integer(), nullable=True))
    op.add_column('bookings', sa.Column('override_discount_pence', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove override fields."""
    op.drop_column('bookings', 'override_discount_pence')
    op.drop_column('bookings', 'override_gross_pence')
