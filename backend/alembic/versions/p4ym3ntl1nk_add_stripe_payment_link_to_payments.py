"""Add stripe_payment_link to payments

Revision ID: p4ym3ntl1nk
Revises: em41ltr4ck
Create Date: 2025-12-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p4ym3ntl1nk'
down_revision: Union[str, None] = 'em41ltr4ck'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add stripe_payment_link column for manual bookings
    op.add_column('payments', sa.Column('stripe_payment_link', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'stripe_payment_link')
