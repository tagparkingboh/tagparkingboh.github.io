"""Add vehicle_inspections table

Revision ID: v3h1cl31nsp
Revises: custn4m3
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v3h1cl31nsp'
down_revision: Union[str, None] = 'custn4m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
    ), {"table_name": table_name})
    return result.scalar()


def upgrade() -> None:
    if not table_exists('vehicle_inspections'):
        op.create_table(
            'vehicle_inspections',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('booking_id', sa.Integer(), nullable=False),
            sa.Column('inspection_type', sa.Enum('DROPOFF', 'PICKUP', name='inspectiontype'), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('photos', sa.Text(), nullable=True),
            sa.Column('inspector_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
            sa.ForeignKeyConstraint(['inspector_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('booking_id', 'inspection_type', name='uq_inspection_booking_type'),
        )
        op.create_index(op.f('ix_vehicle_inspections_id'), 'vehicle_inspections', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_vehicle_inspections_id'), table_name='vehicle_inspections')
    op.drop_table('vehicle_inspections')
    op.execute("DROP TYPE IF EXISTS inspectiontype")
