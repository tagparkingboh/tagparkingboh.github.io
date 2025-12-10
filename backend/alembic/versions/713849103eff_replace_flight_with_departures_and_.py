"""replace_flight_with_departures_and_arrivals

Revision ID: 713849103eff
Revises: 6017ce10fb88
Create Date: 2025-12-03 14:57:04.932678

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '713849103eff'
down_revision: Union[str, Sequence[str], None] = '6017ce10fb88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old flights table
    op.drop_index(op.f('ix_flights_date'), table_name='flights')
    op.drop_index(op.f('ix_flights_id'), table_name='flights')
    op.drop_table('flights')

    # Create flight_departures table
    op.create_table('flight_departures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('flight_number', sa.String(length=20), nullable=False),
        sa.Column('airline_code', sa.String(length=10), nullable=False),
        sa.Column('airline_name', sa.String(length=100), nullable=False),
        sa.Column('departure_time', sa.Time(), nullable=False),
        sa.Column('destination_code', sa.String(length=10), nullable=False),
        sa.Column('destination_name', sa.String(length=100), nullable=True),
        sa.Column('is_slot_1_booked', sa.Boolean(), default=False),
        sa.Column('is_slot_2_booked', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_flight_departures_id'), 'flight_departures', ['id'], unique=False)
    op.create_index(op.f('ix_flight_departures_date'), 'flight_departures', ['date'], unique=False)

    # Create flight_arrivals table
    op.create_table('flight_arrivals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('flight_number', sa.String(length=20), nullable=False),
        sa.Column('airline_code', sa.String(length=10), nullable=False),
        sa.Column('airline_name', sa.String(length=100), nullable=False),
        sa.Column('departure_time', sa.Time(), nullable=True),
        sa.Column('arrival_time', sa.Time(), nullable=False),
        sa.Column('origin_code', sa.String(length=10), nullable=False),
        sa.Column('origin_name', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_flight_arrivals_id'), 'flight_arrivals', ['id'], unique=False)
    op.create_index(op.f('ix_flight_arrivals_date'), 'flight_arrivals', ['date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop new tables
    op.drop_index(op.f('ix_flight_arrivals_date'), table_name='flight_arrivals')
    op.drop_index(op.f('ix_flight_arrivals_id'), table_name='flight_arrivals')
    op.drop_table('flight_arrivals')

    op.drop_index(op.f('ix_flight_departures_date'), table_name='flight_departures')
    op.drop_index(op.f('ix_flight_departures_id'), table_name='flight_departures')
    op.drop_table('flight_departures')

    # Recreate old flights table
    op.create_table('flights',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('date', sa.DATE(), nullable=False),
        sa.Column('flight_number', sa.VARCHAR(length=20), nullable=False),
        sa.Column('airline_code', sa.VARCHAR(length=10), nullable=False),
        sa.Column('airline_name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('flight_type', sa.VARCHAR(length=9), nullable=False),
        sa.Column('scheduled_time', sa.TIME(), nullable=False),
        sa.Column('origin_code', sa.VARCHAR(length=10), nullable=True),
        sa.Column('origin_name', sa.VARCHAR(length=100), nullable=True),
        sa.Column('destination_code', sa.VARCHAR(length=10), nullable=True),
        sa.Column('destination_name', sa.VARCHAR(length=100), nullable=True),
        sa.Column('slot_early_booked', sa.INTEGER(), nullable=True),
        sa.Column('slot_late_booked', sa.INTEGER(), nullable=True),
        sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_flights_id'), 'flights', ['id'], unique=False)
    op.create_index(op.f('ix_flights_date'), 'flights', ['date'], unique=False)
