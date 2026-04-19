#!/usr/bin/env python3
"""
Migration: Add blocked_time_slots table

Creates a child table for blocking specific time slots within blocked dates.
This allows for partial day blocking (e.g., block 6am-10am and 2pm-4pm separately).

Usage:
    python migrations/add_blocked_time_slots_table.py [staging|production|both]

Default: staging only (safe for testing)
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs from environment variables
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")


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
            AND table_name = 'blocked_time_slots'
        """))

        if result.fetchone():
            print(f"✓ Table 'blocked_time_slots' already exists in {db_name}")
            return True

        # Verify blocked_dates table exists (parent table)
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'blocked_dates'
        """))

        if not result.fetchone():
            print(f"✗ Parent table 'blocked_dates' does not exist in {db_name}")
            print("  Please run add_blocked_dates_table.py first")
            return False

        # Create the table
        print(f"Creating 'blocked_time_slots' table...")
        conn.execute(text("""
            CREATE TABLE blocked_time_slots (
                id SERIAL PRIMARY KEY,
                blocked_date_id INTEGER NOT NULL REFERENCES blocked_dates(id) ON DELETE CASCADE,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                block_dropoffs BOOLEAN NOT NULL DEFAULT TRUE,
                block_pickups BOOLEAN NOT NULL DEFAULT TRUE,
                reason VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT valid_time_range CHECK (start_time < end_time)
            )
        """))

        # Create indexes for efficient queries
        print(f"Creating indexes...")
        conn.execute(text("""
            CREATE INDEX idx_blocked_time_slots_blocked_date_id ON blocked_time_slots(blocked_date_id)
        """))
        conn.execute(text("""
            CREATE INDEX idx_blocked_time_slots_times ON blocked_time_slots(start_time, end_time)
        """))

        conn.commit()
        print(f"✓ Successfully created 'blocked_time_slots' table in {db_name}")

        # Verify
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'blocked_time_slots'
            ORDER BY ordinal_position
        """))
        print(f"\nTable structure:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")

        return True


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "staging"

    if target not in ["staging", "production", "both"]:
        print("Usage: python migrations/add_blocked_time_slots_table.py [staging|production|both]")
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
