"""
Migration: Add expires_at column to promo_codes table

This migration adds a field to track when a promo code expires.
NULL means the code never expires (backwards compatible).
The expiry is stored in UK timezone.

Run with:
    python migrations/add_promo_code_expiry.py [staging|production]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs from environment variables
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")

MIGRATION_SQL = """
-- Add expires_at column to promo_codes for tracking code expiry
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE;

-- Add index for efficient queries on expiry
CREATE INDEX IF NOT EXISTS ix_promo_codes_expires_at ON promo_codes (expires_at);
"""

def run_migration(env: str):
    """Run migration on specified environment."""
    if env == "staging":
        db_url = STAGING_URL
        print("Running migration on STAGING...")
    elif env == "production":
        db_url = PRODUCTION_URL
        print("Running migration on PRODUCTION...")
    else:
        print(f"Unknown environment: {env}")
        print("Usage: python migrations/add_promo_code_expiry.py [staging|production]")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Run migration
        conn.execute(text(MIGRATION_SQL))
        conn.commit()

        # Verify column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'promo_codes'
            AND column_name = 'expires_at'
        """))
        columns = [row[0] for row in result.fetchall()]

        if 'expires_at' in columns:
            print(f"Migration successful! Column 'expires_at' added to promo_codes table.")

            # Check index
            result = conn.execute(text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'promo_codes'
                AND indexname = 'ix_promo_codes_expires_at'
            """))
            indexes = [row[0] for row in result.fetchall()]
            if indexes:
                print(f"Index created: {indexes[0]}")
        else:
            print("Warning: Column 'expires_at' not found after migration!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_promo_code_expiry.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
