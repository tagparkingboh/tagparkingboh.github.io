"""Add date-effective parking capacity settings

Revision ID: c4ps3tt
Revises: 0vrn0n, supr0st, t3st1m0n1al
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
from zoneinfo import ZoneInfo


# revision identifiers, used by Alembic.
revision = "c4ps3tt"
down_revision = ("0vrn0n", "supr0st", "t3st1m0n1al")
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: the table may already exist outside alembic's bookkeeping —
    # main.py startup runs Base.metadata.create_all(), which creates any
    # missing model table without stamping a revision. That collision
    # crash-looped the staging deploy on 2026-06-11 (DuplicateTable). When the
    # table pre-exists we skip DDL (create_all also built the indexes) and
    # only top up the seed rows, which create_all does NOT insert.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "parking_capacity_settings" in inspector.get_table_names():
        existing = bind.execute(
            sa.text("SELECT COUNT(*) FROM parking_capacity_settings")
        ).scalar()
        if not existing:
            _seed_capacity_rows()
        return

    op.create_table(
        "parking_capacity_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_spaces", sa.Integer(), nullable=False),
        sa.Column("online_spaces", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint("total_spaces > 0", name="ck_parking_capacity_total_positive"),
        sa.CheckConstraint("online_spaces > 0", name="ck_parking_capacity_online_positive"),
        sa.CheckConstraint("total_spaces >= online_spaces", name="ck_parking_capacity_total_gte_online"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("effective_from"),
    )
    op.create_index(op.f("ix_parking_capacity_settings_id"), "parking_capacity_settings", ["id"], unique=False)
    op.create_index(
        op.f("ix_parking_capacity_settings_effective_from"),
        "parking_capacity_settings",
        ["effective_from"],
        unique=True,
    )

    _seed_capacity_rows()


def _seed_capacity_rows():
    # Preserve historical reporting semantics, then apply the June 2026
    # operational change requested for production rollout.
    op.bulk_insert(
        sa.table(
            "parking_capacity_settings",
            sa.column("effective_from", sa.DateTime(timezone=True)),
            sa.column("total_spaces", sa.Integer()),
            sa.column("online_spaces", sa.Integer()),
            sa.column("updated_by", sa.String()),
        ),
        [
            {
                "effective_from": datetime(1970, 1, 1, 0, 0, tzinfo=ZoneInfo("Europe/London")),
                "total_spaces": 70,
                "online_spaces": 64,
                "updated_by": "migration:c4ps3tt",
            },
            {
                "effective_from": datetime(2026, 6, 11, 0, 0, tzinfo=ZoneInfo("Europe/London")),
                "total_spaces": 75,
                "online_spaces": 73,
                "updated_by": "migration:c4ps3tt",
            },
        ],
    )


def downgrade():
    op.drop_index(op.f("ix_parking_capacity_settings_effective_from"), table_name="parking_capacity_settings")
    op.drop_index(op.f("ix_parking_capacity_settings_id"), table_name="parking_capacity_settings")
    op.drop_table("parking_capacity_settings")
