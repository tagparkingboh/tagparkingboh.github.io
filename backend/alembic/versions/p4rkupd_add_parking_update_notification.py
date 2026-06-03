"""add parking update notification tracking

Revision ID: p4rkupd
Revises: ref3rr4l
Create Date: 2026-06-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "p4rkupd"
down_revision = "ref3rr4l"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bookings",
        sa.Column("parking_update_email_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column("bookings", sa.Column("parking_update_email_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("parking_update_email_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("bookings", sa.Column("parking_update_email_last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("parking_update_sms_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column("bookings", sa.Column("parking_update_sms_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("parking_update_last_error", sa.Text(), nullable=True))
    op.execute("""
        UPDATE sms_templates
        SET is_active = TRUE,
            is_automated = TRUE,
            trigger_event = 'parking_update'
        WHERE name = 'Car Parking Charges'
    """)
    op.execute("""
        INSERT INTO sms_templates (name, content, description, is_active, is_automated, trigger_event)
        SELECT
            'Car Parking Charges',
            'Hi {{first_name}}, we have sent a service update about Bournemouth Airport parking charges for booking {{booking_reference}}. Please check your email before drop-off.',
            'Sent automatically after the parking update email succeeds',
            TRUE,
            TRUE,
            'parking_update'
        WHERE NOT EXISTS (
            SELECT 1 FROM sms_templates WHERE name = 'Car Parking Charges'
        )
    """)


def downgrade():
    op.execute("""
        UPDATE sms_templates
        SET trigger_event = NULL,
            is_automated = FALSE
        WHERE name = 'Car Parking Charges'
          AND trigger_event = 'parking_update'
    """)
    op.drop_column("bookings", "parking_update_last_error")
    op.drop_column("bookings", "parking_update_sms_sent_at")
    op.drop_column("bookings", "parking_update_sms_status")
    op.drop_column("bookings", "parking_update_email_last_attempt_at")
    op.drop_column("bookings", "parking_update_email_attempt_count")
    op.drop_column("bookings", "parking_update_email_sent_at")
    op.drop_column("bookings", "parking_update_email_status")
