#!/usr/bin/env python3
"""
Migration: Add blocked_dates table

Creates a table for blocking dates from bookings (e.g., holidays, maintenance).
Admins can block specific dates to prevent drop-offs and/or pick-ups.

Usage:
    python migrations/add_blocked_dates_table.py [staging|production|both]

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
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'blocked_dates'
        """))

        if result.fetchone():
            print(f"✓ Table 'blocked_dates' already exists in {db_name}")
            return True

        # Create the table
        print(f"Creating 'blocked_dates' table...")
        conn.execute(text("""
            CREATE TABLE blocked_dates (
                id SERIAL PRIMARY KEY,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                block_dropoffs BOOLEAN NOT NULL DEFAULT TRUE,
                block_pickups BOOLEAN NOT NULL DEFAULT TRUE,
                reason VARCHAR(255),
                created_by VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """))

        # Create indexes for efficient date range queries
        print(f"Creating indexes...")
        conn.execute(text("""
            CREATE INDEX idx_blocked_dates_start_date ON blocked_dates(start_date)
        """))
        conn.execute(text("""
            CREATE INDEX idx_blocked_dates_end_date ON blocked_dates(end_date)
        """))
        conn.execute(text("""
            CREATE INDEX idx_blocked_dates_range ON blocked_dates(start_date, end_date)
        """))

        conn.commit()
        print(f"✓ Successfully created 'blocked_dates' table in {db_name}")

        # Verify
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'blocked_dates'
            ORDER BY ordinal_position
        """))
        print(f"\nTable structure:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")

        return True


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "staging"

    if target not in ["staging", "production", "both"]:
        print("Usage: python migrations/add_blocked_dates_table.py [staging|production|both]")
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
