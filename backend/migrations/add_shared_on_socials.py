"""
Migration: Add shared_on_socials columns to promo_codes table

This migration adds fields to track when a promo code was shared on social media
(for codes that aren't emailed to specific recipients).

Run with:
    python migrations/add_shared_on_socials.py [staging|production]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs
STAGING_URL = "postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway"
PRODUCTION_URL = "postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway"

MIGRATION_SQL = """
-- Add shared_on_socials tracking columns to promo_codes
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS shared_on_socials BOOLEAN DEFAULT FALSE;
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS shared_on_socials_at TIMESTAMP WITH TIME ZONE;
"""

def run_migration(env: str):
    """Run migration on specified environment."""
    if env == "staging":
        db_url = STAGING_URL
        print("🔄 Running migration on STAGING...")
    elif env == "production":
        db_url = PRODUCTION_URL
        print("🔄 Running migration on PRODUCTION...")
    else:
        print(f"❌ Unknown environment: {env}")
        print("Usage: python migrations/add_shared_on_socials.py [staging|production]")
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
            AND column_name IN ('shared_on_socials', 'shared_on_socials_at')
            ORDER BY column_name
        """))
        columns = [row[0] for row in result.fetchall()]

        if 'shared_on_socials' in columns and 'shared_on_socials_at' in columns:
            print(f"✅ Migration successful! Columns added: {columns}")
        else:
            print(f"⚠️ Warning: Expected columns not found. Found: {columns}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_shared_on_socials.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
