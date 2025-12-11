"""add_audit_and_error_logs

Revision ID: a1b2c3d4e5f6
Revises: 713849103eff
Create Date: 2025-12-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '713849103eff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_logs and error_logs tables."""
    # Create audit_logs table
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('booking_reference', sa.String(length=20), nullable=True),
        sa.Column('event', sa.Enum(
            'booking_started', 'flight_selected', 'slot_selected',
            'vehicle_entered', 'customer_entered', 'billing_entered',
            'payment_initiated', 'payment_succeeded', 'payment_failed',
            'booking_confirmed', 'booking_abandoned', 'booking_cancelled',
            'booking_refunded', 'booking_updated',
            name='auditlogevent'
        ), nullable=False),
        sa.Column('event_data', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_session_id'), 'audit_logs', ['session_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_booking_reference'), 'audit_logs', ['booking_reference'], unique=False)
    op.create_index(op.f('ix_audit_logs_event'), 'audit_logs', ['event'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)

    # Create error_logs table
    op.create_table('error_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('severity', sa.Enum(
            'debug', 'info', 'warning', 'error', 'critical',
            name='errorseverity'
        ), nullable=False),
        sa.Column('error_type', sa.String(length=100), nullable=False),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('request_data', sa.Text(), nullable=True),
        sa.Column('endpoint', sa.String(length=200), nullable=True),
        sa.Column('booking_reference', sa.String(length=20), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_error_logs_id'), 'error_logs', ['id'], unique=False)
    op.create_index(op.f('ix_error_logs_severity'), 'error_logs', ['severity'], unique=False)
    op.create_index(op.f('ix_error_logs_error_type'), 'error_logs', ['error_type'], unique=False)
    op.create_index(op.f('ix_error_logs_endpoint'), 'error_logs', ['endpoint'], unique=False)
    op.create_index(op.f('ix_error_logs_booking_reference'), 'error_logs', ['booking_reference'], unique=False)
    op.create_index(op.f('ix_error_logs_created_at'), 'error_logs', ['created_at'], unique=False)


def downgrade() -> None:
    """Remove audit_logs and error_logs tables."""
    op.drop_index(op.f('ix_error_logs_created_at'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_booking_reference'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_endpoint'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_error_type'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_severity'), table_name='error_logs')
    op.drop_index(op.f('ix_error_logs_id'), table_name='error_logs')
    op.drop_table('error_logs')

    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_event'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_booking_reference'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_session_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_table('audit_logs')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS errorseverity")
    op.execute("DROP TYPE IF EXISTS auditlogevent")
