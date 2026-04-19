"""
Migration script to update ShiftType enum in PostgreSQL.

Adds new time-based shift types while keeping backwards compatibility.

Run with: python migrations/update_shift_type_enum.py
"""
import sys
import os
from sqlalchemy import create_engine, text

# Database URL from environment variable
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")

if not STAGING_URL:
    print("Error: STAGING_DATABASE_URL environment variable not set")
    sys.exit(1)

engine = create_engine(STAGING_URL)

# New shift type values to add
NEW_VALUES = [
    'early_morning',
    'morning',
    'midday',
    'afternoon',
    'late_afternoon',
    'evening',
    'full_morning',
    'full_afternoon',
    'full_evening',
]

def migrate():
    """Add new enum values to shifttype enum in PostgreSQL."""
    with engine.connect() as conn:
        # Check current enum values
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'shifttype')
            ORDER BY enumsortorder
        """))
        current_values = [row[0] for row in result]
        print(f"Current ShiftType values: {current_values}")

        # Add new values that don't exist
        for value in NEW_VALUES:
            if value not in current_values:
                print(f"Adding enum value: {value}")
                conn.execute(text(f"ALTER TYPE shifttype ADD VALUE IF NOT EXISTS '{value}'"))
                conn.commit()
            else:
                print(f"Value already exists: {value}")

        # Verify
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'shifttype')
            ORDER BY enumsortorder
        """))
        updated_values = [row[0] for row in result]
        print(f"\nUpdated ShiftType values: {updated_values}")

        print("\nMigration complete!")

if __name__ == "__main__":
    migrate()
