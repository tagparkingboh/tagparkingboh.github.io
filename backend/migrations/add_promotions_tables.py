"""
Migration: Add promotions and promo_codes tables

This migration creates the new promo code generation system tables:
- promotions: Campaign/batch of promo codes with same discount
- promo_codes: Individual unique codes linked to recipients

Run with:
    python migrations/add_promotions_tables.py [staging|production]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# Database URLs from environment variables
# Set these before running: export STAGING_DATABASE_URL="..." and export PRODUCTION_DATABASE_URL="..."
STAGING_URL = os.environ.get("STAGING_DATABASE_URL", "")
PRODUCTION_URL = os.environ.get("PRODUCTION_DATABASE_URL", "")

MIGRATION_SQL = """
-- Create promotions table (campaign/batch level)
CREATE TABLE IF NOT EXISTS promotions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Discount settings
    discount_percent INTEGER NOT NULL,

    -- Code generation stats
    total_codes INTEGER NOT NULL DEFAULT 0,
    codes_sent INTEGER NOT NULL DEFAULT 0,
    codes_used INTEGER NOT NULL DEFAULT 0,

    -- Admin tracking
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create index on promotions
CREATE INDEX IF NOT EXISTS ix_promotions_id ON promotions(id);
CREATE INDEX IF NOT EXISTS ix_promotions_created_at ON promotions(created_at);

-- Create promo_codes table (individual codes)
CREATE TABLE IF NOT EXISTS promo_codes (
    id SERIAL PRIMARY KEY,
    promotion_id INTEGER NOT NULL REFERENCES promotions(id),
    code VARCHAR(20) NOT NULL UNIQUE,

    -- Recipient (one of these may be set)
    customer_id INTEGER REFERENCES customers(id),
    subscriber_id INTEGER REFERENCES marketing_subscribers(id),
    recipient_email VARCHAR(255),
    recipient_first_name VARCHAR(100),
    recipient_last_name VARCHAR(100),

    -- Email tracking
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP WITH TIME ZONE,
    email_subject VARCHAR(255),

    -- Usage tracking
    is_used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP WITH TIME ZONE,
    booking_id INTEGER REFERENCES bookings(id),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes on promo_codes
CREATE INDEX IF NOT EXISTS ix_promo_codes_id ON promo_codes(id);
CREATE INDEX IF NOT EXISTS ix_promo_codes_code ON promo_codes(code);
CREATE INDEX IF NOT EXISTS ix_promo_codes_promotion_id ON promo_codes(promotion_id);
CREATE INDEX IF NOT EXISTS ix_promo_codes_is_used ON promo_codes(is_used);
CREATE INDEX IF NOT EXISTS ix_promo_codes_customer_id ON promo_codes(customer_id);
CREATE INDEX IF NOT EXISTS ix_promo_codes_subscriber_id ON promo_codes(subscriber_id);
CREATE INDEX IF NOT EXISTS ix_promo_codes_recipient_email ON promo_codes(recipient_email);
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
        print("Usage: python migrations/add_promotions_tables.py [staging|production]")
        sys.exit(1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Run migration
        conn.execute(text(MIGRATION_SQL))
        conn.commit()

        # Verify tables exist
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('promotions', 'promo_codes')
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]

        if 'promotions' in tables and 'promo_codes' in tables:
            print(f"✅ Migration successful! Tables created: {tables}")
        else:
            print(f"⚠️ Warning: Expected tables not found. Found: {tables}")

        # Count existing records (should be 0 for new tables)
        promo_count = conn.execute(text("SELECT COUNT(*) FROM promotions")).scalar()
        code_count = conn.execute(text("SELECT COUNT(*) FROM promo_codes")).scalar()
        print(f"📊 Current records: {promo_count} promotions, {code_count} promo codes")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrations/add_promotions_tables.py [staging|production|both]")
        sys.exit(1)

    env = sys.argv[1].lower()

    if env == "both":
        run_migration("staging")
        print()
        run_migration("production")
    else:
        run_migration(env)
