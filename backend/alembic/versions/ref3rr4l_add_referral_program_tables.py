"""Add referral program tables

Revision ID: ref3rr4l
Revises: 0vrn0n
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ref3rr4l"
down_revision: Union[str, None] = "0vrn0n"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_programs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="eligible"),
        sa.Column("invite_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referral_code_id", sa.Integer(), nullable=True),
        sa.Column("reward_code_id", sa.Integer(), nullable=True),
        sa.Column("qualified_referral_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_earned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["referral_code_id"], ["promo_codes.id"]),
        sa.ForeignKeyConstraint(["reward_code_id"], ["promo_codes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", name="uq_referral_programs_customer_id"),
    )
    op.create_index("ix_referral_programs_customer_id", "referral_programs", ["customer_id"])
    op.create_index("ix_referral_programs_referral_code_id", "referral_programs", ["referral_code_id"])
    op.create_index("ix_referral_programs_reward_code_id", "referral_programs", ["reward_code_id"])
    op.create_index("ix_referral_programs_status", "referral_programs", ["status"])

    op.create_table(
        "referral_attributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_program_id", sa.Integer(), nullable=False),
        sa.Column("referrer_customer_id", sa.Integer(), nullable=False),
        sa.Column("referred_customer_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("is_self_use", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
        sa.ForeignKeyConstraint(["referral_program_id"], ["referral_programs.id"]),
        sa.ForeignKeyConstraint(["referred_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["referrer_customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_referral_attributions_booking_id"),
    )
    op.create_index("ix_referral_attributions_booking_id", "referral_attributions", ["booking_id"])
    op.create_index("ix_referral_attributions_promo_code_id", "referral_attributions", ["promo_code_id"])
    op.create_index("ix_referral_attributions_referral_program_id", "referral_attributions", ["referral_program_id"])
    op.create_index("ix_referral_attributions_referred_customer_id", "referral_attributions", ["referred_customer_id"])
    op.create_index("ix_referral_attributions_referrer_customer_id", "referral_attributions", ["referrer_customer_id"])
    op.create_index("ix_referral_attributions_status", "referral_attributions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_referral_attributions_status", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_referrer_customer_id", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_referred_customer_id", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_referral_program_id", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_promo_code_id", table_name="referral_attributions")
    op.drop_index("ix_referral_attributions_booking_id", table_name="referral_attributions")
    op.drop_table("referral_attributions")

    op.drop_index("ix_referral_programs_status", table_name="referral_programs")
    op.drop_index("ix_referral_programs_reward_code_id", table_name="referral_programs")
    op.drop_index("ix_referral_programs_referral_code_id", table_name="referral_programs")
    op.drop_index("ix_referral_programs_customer_id", table_name="referral_programs")
    op.drop_table("referral_programs")
