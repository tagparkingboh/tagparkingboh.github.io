"""Add testimonials table

Revision ID: t3st1m0n1al
Revises: f0und3rf0ll0w
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't3st1m0n1al'
down_revision = 'f0und3rf0ll0w'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'testimonials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_name', sa.String(100), nullable=False),
        sa.Column('review_text', sa.Text(), nullable=False),
        sa.Column('star_rating', sa.Integer(), nullable=True),  # NULL for unrated (LinkedIn, FB, etc.)
        sa.Column('date_of_travel', sa.Date(), nullable=True),
        sa.Column('date_added', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('status', sa.Enum('active', 'inactive', name='testimonialstatus'), nullable=False, server_default='inactive'),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_testimonials_id'), 'testimonials', ['id'], unique=False)
    op.create_index(op.f('ix_testimonials_status'), 'testimonials', ['status'], unique=False)
    op.create_index(op.f('ix_testimonials_star_rating'), 'testimonials', ['star_rating'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_testimonials_star_rating'), table_name='testimonials')
    op.drop_index(op.f('ix_testimonials_status'), table_name='testimonials')
    op.drop_index(op.f('ix_testimonials_id'), table_name='testimonials')
    op.drop_table('testimonials')
    op.execute("DROP TYPE IF EXISTS testimonialstatus")
