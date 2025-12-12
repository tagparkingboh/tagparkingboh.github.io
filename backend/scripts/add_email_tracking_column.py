#!/usr/bin/env python3
"""
Migration script to add confirmation_email_sent columns to bookings table.

Usage:
    python scripts/add_email_tracking_column.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal


def add_email_tracking_columns():
    """Add confirmation_email_sent and confirmation_email_sent_at columns to bookings table."""
    db = SessionLocal()
    try:
        # Check if column already exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'bookings'
            AND column_name = 'confirmation_email_sent'
        """))

        if result.fetchone():
            print("Column 'confirmation_email_sent' already exists. Skipping migration.")
            return True

        # Add the columns
        print("Adding 'confirmation_email_sent' column...")
        db.execute(text("""
            ALTER TABLE bookings
            ADD COLUMN confirmation_email_sent BOOLEAN DEFAULT FALSE
        """))

        print("Adding 'confirmation_email_sent_at' column...")
        db.execute(text("""
            ALTER TABLE bookings
            ADD COLUMN confirmation_email_sent_at TIMESTAMP WITH TIME ZONE
        """))

        db.commit()
        print("Migration completed successfully!")
        return True

    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    add_email_tracking_columns()
