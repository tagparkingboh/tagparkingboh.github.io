"""
Migration script to add employee unavailability feature.

Changes:
1. Add 'unavailable' value to holidaytype enum
2. Add start_time and end_time columns to employee_holidays table

Run with: python migrations/add_employee_unavailability.py [staging|production]

URLs from backend/docs/SPEC.md
"""
import sys
from sqlalchemy import create_engine, text

# Database URLs from SPEC.md
STAGING_URL = "postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway"
PRODUCTION_URL = "postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway"


def migrate(db_url: str, env_name: str):
    """Run the migration."""
    print(f"\n{'='*60}")
    print(f"Running migration on {env_name}")
    print(f"{'='*60}\n")

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Step 1: Add 'unavailable' to holidaytype enum
        print("Step 1: Adding 'unavailable' to holidaytype enum...")

        # Check current enum values
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'holidaytype')
            ORDER BY enumsortorder
        """))
        current_values = [row[0] for row in result]
        print(f"  Current holidaytype values: {current_values}")

        if 'unavailable' not in current_values:
            print("  Adding enum value: unavailable")
            conn.execute(text("ALTER TYPE holidaytype ADD VALUE IF NOT EXISTS 'unavailable'"))
            conn.commit()
            print("  Added 'unavailable' to holidaytype enum")
        else:
            print("  'unavailable' already exists in holidaytype enum")

        # Step 2: Add start_time and end_time columns
        print("\nStep 2: Adding start_time and end_time columns...")

        # Check if columns exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'employee_holidays'
            AND column_name IN ('start_time', 'end_time')
        """))
        existing_columns = [row[0] for row in result]
        print(f"  Existing time columns: {existing_columns}")

        if 'start_time' not in existing_columns:
            print("  Adding column: start_time")
            conn.execute(text("""
                ALTER TABLE employee_holidays
                ADD COLUMN start_time TIME NULL
            """))
            conn.commit()
            print("  Added start_time column")
        else:
            print("  start_time column already exists")

        if 'end_time' not in existing_columns:
            print("  Adding column: end_time")
            conn.execute(text("""
                ALTER TABLE employee_holidays
                ADD COLUMN end_time TIME NULL
            """))
            conn.commit()
            print("  Added end_time column")
        else:
            print("  end_time column already exists")

        # Verify changes
        print("\nVerifying changes...")

        # Verify enum
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'holidaytype')
            ORDER BY enumsortorder
        """))
        updated_values = [row[0] for row in result]
        print(f"  Updated holidaytype values: {updated_values}")

        # Verify columns
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'employee_holidays'
            AND column_name IN ('start_time', 'end_time')
            ORDER BY column_name
        """))
        columns = [(row[0], row[1], row[2]) for row in result]
        for col_name, data_type, nullable in columns:
            print(f"  Column: {col_name} ({data_type}, nullable={nullable})")

        print(f"\n{'='*60}")
        print(f"Migration complete on {env_name}!")
        print(f"{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_employee_unavailability.py [staging|production|both]")
        print("\nOptions:")
        print("  staging    - Run on staging database only")
        print("  production - Run on production database only")
        print("  both       - Run on both staging and production")
        sys.exit(1)

    target = sys.argv[1].lower()

    if target == 'staging':
        migrate(STAGING_URL, "STAGING")
    elif target == 'production':
        migrate(PRODUCTION_URL, "PRODUCTION")
    elif target == 'both':
        migrate(STAGING_URL, "STAGING")
        migrate(PRODUCTION_URL, "PRODUCTION")
    else:
        print(f"Unknown target: {target}")
        print("Use 'staging', 'production', or 'both'")
        sys.exit(1)


if __name__ == "__main__":
    main()
