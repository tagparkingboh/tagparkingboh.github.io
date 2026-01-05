"""Add users, login_codes, and sessions tables for authentication

Revision ID: us3r4uth0001
Revises: s3p4r4t3pr0m0
Create Date: 2026-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'us3r4uth0001'
down_revision: Union[str, None] = 's3p4r4t3pr0m0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
    ), {"table_name": table_name})
    return result.scalar()


def index_exists(index_name):
    """Check if an index exists in the database."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = :index_name)"
    ), {"index_name": index_name})
    return result.scalar()


def upgrade() -> None:
    # Create users table if it doesn't exist
    if not table_exists('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('first_name', sa.String(100), nullable=False),
            sa.Column('last_name', sa.String(100), nullable=False),
            sa.Column('phone', sa.String(20), nullable=True),
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    if not index_exists('ix_users_id'):
        op.create_index('ix_users_id', 'users', ['id'], unique=False)
    if not index_exists('ix_users_email'):
        op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # Create login_codes table if it doesn't exist
    if not table_exists('login_codes'):
        op.create_table(
            'login_codes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(6), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used', sa.Boolean(), server_default='false'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
    if not index_exists('ix_login_codes_id'):
        op.create_index('ix_login_codes_id', 'login_codes', ['id'], unique=False)

    # Create sessions table if it doesn't exist
    if not table_exists('sessions'):
        op.create_table(
            'sessions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('token', sa.String(64), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
    if not index_exists('ix_sessions_id'):
        op.create_index('ix_sessions_id', 'sessions', ['id'], unique=False)
    if not index_exists('ix_sessions_token'):
        op.create_index('ix_sessions_token', 'sessions', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_sessions_token', table_name='sessions')
    op.drop_index('ix_sessions_id', table_name='sessions')
    op.drop_table('sessions')

    op.drop_index('ix_login_codes_id', table_name='login_codes')
    op.drop_table('login_codes')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')
