"""Add SMS templates and messages tables

Revision ID: sms001
Revises: mult1us3
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sms001'
down_revision = 'mult1us3'
branch_labels = None
depends_on = None


def upgrade():
    # Create sms_templates table
    op.create_table(
        'sms_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_automated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('trigger_event', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_sms_templates_id', 'sms_templates', ['id'])
    op.create_index('ix_sms_templates_name', 'sms_templates', ['name'])

    # Create sms_messages table
    op.create_table(
        'sms_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_number', sa.String(20), nullable=False, index=True),
        sa.Column('booking_id', sa.Integer(), sa.ForeignKey('bookings.id'), nullable=True, index=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True, index=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('sms_templates.id'), nullable=True),
        sa.Column('direction', sa.Enum('outbound', 'inbound', name='smsdirection'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('provider_message_id', sa.String(100), nullable=True, index=True),
        sa.Column('status', sa.Enum('pending', 'sent', 'delivered', 'failed', name='smsstatus'), nullable=False, server_default='pending'),
        sa.Column('status_detail', sa.String(255), nullable=True),
        sa.Column('is_bulk', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('bulk_batch_id', sa.String(50), nullable=True, index=True),
        sa.Column('sent_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_sms_messages_id', 'sms_messages', ['id'])

    # Seed default automated templates
    op.execute("""
        INSERT INTO sms_templates (name, content, description, is_active, is_automated, trigger_event)
        VALUES
        (
            'booking_confirmation',
            'Hi {{first_name}}, your TAG Parking booking {{booking_reference}} is confirmed! Drop-off: {{dropoff_date}} at {{dropoff_time}}. See you soon!',
            'Sent automatically when a booking is confirmed',
            true,
            true,
            'booking_confirmed'
        ),
        (
            'reminder_2day',
            'Hi {{first_name}}, reminder: your parking at TAG starts in 2 days ({{dropoff_date}}). Booking ref: {{booking_reference}}. Safe travels!',
            'Sent automatically 2 days before drop-off',
            true,
            true,
            'reminder_2day'
        )
    """)


def downgrade():
    op.drop_table('sms_messages')
    op.drop_table('sms_templates')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS smsdirection")
    op.execute("DROP TYPE IF EXISTS smsstatus")
