#!/usr/bin/env python3
"""
Migration: Add code_prefix column to promotions table

This allows promotions to have custom prefixes for their promo codes.
For example, a "Spring Sale" promotion could have codes like "SPRING-XXXX-XXXX"
instead of the default "TAG-XXXX-XXXX".

Usage:
    python migrations/add_code_prefix_to_promotions.py [staging|production|both]

Default: staging only (safe for testing)
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs
STAGING_URL = "postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway"
PRODUCTION_URL = "postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway"


def run_migration(db_url: str, db_name: str):
    """Run migration on the specified database."""
    print(f"\n{'='*60}")
    print(f"Running migration on {db_name}")
    print(f"{'='*60}")

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'promotions'
            AND column_name = 'code_prefix'
        """))

        if result.fetchone():
            print(f"✓ Column 'code_prefix' already exists in {db_name}")
            return True

        # Add the column
        print(f"Adding 'code_prefix' column to promotions table...")
        conn.execute(text("""
            ALTER TABLE promotions
            ADD COLUMN code_prefix VARCHAR(10) NOT NULL DEFAULT 'TAG'
        """))
        conn.commit()
        print(f"✓ Successfully added 'code_prefix' column to {db_name}")

        # Verify
        result = conn.execute(text("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'promotions'
            AND column_name = 'code_prefix'
        """))
        row = result.fetchone()
        if row:
            print(f"  - Column: {row[0]}, Type: {row[1]}, Default: {row[2]}")

        return True


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "staging"

    if target not in ["staging", "production", "both"]:
        print("Usage: python migrations/add_code_prefix_to_promotions.py [staging|production|both]")
        print("Default: staging only")
        sys.exit(1)

    success = True

    if target in ["staging", "both"]:
        try:
            run_migration(STAGING_URL, "STAGING")
        except Exception as e:
            print(f"✗ Staging migration failed: {e}")
            success = False

    if target in ["production", "both"]:
        try:
            run_migration(PRODUCTION_URL, "PRODUCTION")
        except Exception as e:
            print(f"✗ Production migration failed: {e}")
            success = False

    print(f"\n{'='*60}")
    if success:
        print("Migration completed successfully!")
    else:
        print("Migration completed with errors.")
    print(f"{'='*60}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
