"""
Migration: Add dates_selected value to auditlogevent enum

This migration adds the dates_selected event type for funnel tracking.

Run with:
    python migrations/add_dates_selected_audit_event.py [staging|production]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs
STAGING_URL = "postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway"
PRODUCTION_URL = "postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway"


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
        print("Usage: python migrations/add_dates_selected_audit_event.py [staging|production]")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Check current enum values
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'auditlogevent')
            ORDER BY enumsortorder
        """))
        current_values = [row[0] for row in result.fetchall()]
        print(f"Current AuditLogEvent values: {current_values}")

        # Add dates_selected if it doesn't exist
        if 'dates_selected' not in current_values:
            print("Adding enum value: dates_selected")
            conn.execute(text("ALTER TYPE auditlogevent ADD VALUE IF NOT EXISTS 'dates_selected'"))
            conn.commit()
            print("Successfully added 'dates_selected' to auditlogevent enum")
        else:
            print("Value 'dates_selected' already exists")

        # Verify
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'auditlogevent')
            ORDER BY enumsortorder
        """))
        updated_values = [row[0] for row in result.fetchall()]
        print(f"\nUpdated AuditLogEvent values: {updated_values}")

        print("\nMigration complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_dates_selected_audit_event.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
