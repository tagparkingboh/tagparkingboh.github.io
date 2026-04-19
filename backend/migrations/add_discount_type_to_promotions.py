"""
Migration: Add discount_type column to promotions table

This migration adds the discount_type column to support different discount behaviors:
- 'percentage': Standard percentage discount (e.g., 10% off total price)
- 'free_week': "1 Week Free Parking" - deducts week1_price (free for <=7 days, partial for >7 days)
- 'free_100': "100% Off" - completely free regardless of trip length

The column is nullable - when NULL, the discount type is auto-determined:
- 100% discount -> defaults to 'free_week' behavior
- Other percentages -> defaults to 'percentage' behavior

Run with:
    python migrations/add_discount_type_to_promotions.py [staging|production|both]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs from environment variables
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")

MIGRATION_SQL = """
-- Add discount_type column to promotions table
-- NULL = auto-determine based on discount_percent (100% -> free_week, others -> percentage)
ALTER TABLE promotions
ADD COLUMN IF NOT EXISTS discount_type VARCHAR(20);

-- Add a comment explaining the column
COMMENT ON COLUMN promotions.discount_type IS
'Discount type: percentage, free_week (1 week free), or free_100 (100% off). NULL = auto-determine.';
"""

VERIFY_SQL = """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'promotions'
AND column_name = 'discount_type';
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
        print("Usage: python migrations/add_discount_type_to_promotions.py [staging|production|both]")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Run migration
        print("  Adding discount_type column...")
        conn.execute(text(MIGRATION_SQL))
        conn.commit()

        # Verify column exists
        result = conn.execute(text(VERIFY_SQL))
        row = result.fetchone()

        if row:
            print(f"  Column verified: {row[0]} ({row[1]}, nullable={row[2]})")
            print(f"Migration successful for {env.upper()}!")
        else:
            print(f"Warning: Column not found after migration!")

        # Show current promotions with discount_type
        promo_count = conn.execute(text("""
            SELECT COUNT(*),
                   SUM(CASE WHEN discount_type IS NULL THEN 1 ELSE 0 END) as null_count,
                   SUM(CASE WHEN discount_type IS NOT NULL THEN 1 ELSE 0 END) as set_count
            FROM promotions
        """)).fetchone()

        print(f"  Promotions: {promo_count[0]} total, {promo_count[1]} with NULL discount_type, {promo_count[2]} with discount_type set")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_discount_type_to_promotions.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
