"""
Migration: Add shared_privately columns to promo_codes table

This migration adds fields to track when a promo code was shared privately
(via text, to friends, etc.) - similar to shared_on_socials but for private sharing.

Run with:
    python migrations/add_shared_privately.py [staging|production]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs from environment variables
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")

MIGRATION_SQL = """
-- Add shared_privately tracking columns to promo_codes
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS shared_privately BOOLEAN DEFAULT FALSE;
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS shared_privately_at TIMESTAMP WITH TIME ZONE;
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
        print("Usage: python migrations/add_shared_privately.py [staging|production]")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Run migration
        conn.execute(text(MIGRATION_SQL))
        conn.commit()

        # Verify columns exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'promo_codes'
            AND column_name IN ('shared_privately', 'shared_privately_at')
            ORDER BY column_name
        """))
        columns = [row[0] for row in result.fetchall()]

        if 'shared_privately' in columns and 'shared_privately_at' in columns:
            print(f"Migration successful! Columns added: {columns}")
        else:
            print(f"Warning: Expected columns not found. Found: {columns}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_shared_privately.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
