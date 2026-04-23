"""Add marketing email campaigns tables

Revision ID: m4rk3m41l
Revises: sms001
Create Date: 2026-04-22

"""
from alembic import op
import sqlalchemy as sa


revision = 'm4rk3m41l'
down_revision = 'sms001'
branch_labels = None
depends_on = None


def upgrade():
    # Create marketing_email_campaigns table
    op.create_table(
        'marketing_email_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('promo_code_id', sa.Integer(), sa.ForeignKey('promo_codes.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('total_recipients', sa.Integer(), server_default='0'),
        sa.Column('sent_count', sa.Integer(), server_default='0'),
        sa.Column('failed_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
    )

    # Create marketing_email_recipients table
    op.create_table(
        'marketing_email_recipients',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('marketing_email_campaigns.id'), nullable=False),
        sa.Column('subscriber_id', sa.Integer(), sa.ForeignKey('marketing_subscribers.id'), nullable=False),
        sa.Column('email_sent', sa.Boolean(), server_default='false'),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_failed', sa.Boolean(), server_default='false'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.UniqueConstraint('campaign_id', 'subscriber_id', name='uq_campaign_subscriber'),
    )


def downgrade():
    op.drop_table('marketing_email_recipients')
    op.drop_table('marketing_email_campaigns')
