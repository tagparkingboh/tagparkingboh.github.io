import os
from sqlalchemy import create_engine, text

# Database URLs from environment variables
# Set these before running: export STAGING_DATABASE_URL="..." and export PRODUCTION_DATABASE_URL="..."
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")

def run_migration(name, url):
    print(f"\n{name}:")
    engine = create_engine(url)
    with engine.connect() as conn:
        # Check current values
        result = conn.execute(text("""
            SELECT enumlabel FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'auditlogevent')
            ORDER BY enumsortorder
        """))
        current = [r[0] for r in result.fetchall()]
        print(f"  Current values: {current}")

        if 'dates_selected' not in current:
            conn.execute(text("ALTER TYPE auditlogevent ADD VALUE IF NOT EXISTS 'dates_selected'"))
            conn.commit()
            print("  Added 'dates_selected'")
        else:
            print("  'dates_selected' already exists")

run_migration("STAGING", STAGING_URL)
run_migration("PRODUCTION", PRODUCTION_URL)
print("\nDone!")
