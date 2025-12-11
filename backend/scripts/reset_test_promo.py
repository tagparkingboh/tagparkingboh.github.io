#!/usr/bin/env python3
"""
Utility script to create/reset test promo codes for staging environment.

Usage:
    python scripts/reset_test_promo.py              # Reset TESTPROMO10
    python scripts/reset_test_promo.py MYCODE       # Reset specific code
    python scripts/reset_test_promo.py --create NEW # Create new code
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from db_models import MarketingSubscriber


def reset_promo_code(code: str) -> bool:
    """Reset a promo code so it can be reused."""
    db = SessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code == code.upper()
        ).first()

        if subscriber:
            subscriber.promo_code_used = False
            subscriber.promo_code_used_at = None
            subscriber.promo_code_used_booking_id = None
            db.commit()
            print(f"✓ Reset promo code: {code.upper()}")
            print(f"  Status: AVAILABLE")
            return True
        else:
            print(f"✗ Promo code not found: {code.upper()}")
            return False
    finally:
        db.close()


def create_promo_code(code: str, email: str = None) -> bool:
    """Create a new test promo code."""
    import random
    import string

    db = SessionLocal()
    try:
        # Check if code already exists
        existing = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code == code.upper()
        ).first()

        if existing:
            print(f"✗ Promo code already exists: {code.upper()}")
            print(f"  Use reset command to make it available again")
            return False

        # Generate unique email if not provided
        if not email:
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            email = f"testpromo_{suffix}@staging.example.com"

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=email,
            promo_code=code.upper(),
            promo_code_used=False,
        )
        db.add(subscriber)
        db.commit()

        print(f"✓ Created promo code: {code.upper()}")
        print(f"  Email: {email}")
        print(f"  Status: AVAILABLE")
        return True
    finally:
        db.close()


def list_promo_codes():
    """List all promo codes in the system."""
    db = SessionLocal()
    try:
        subscribers = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code.isnot(None)
        ).all()

        if not subscribers:
            print("No promo codes found.")
            return

        print(f"Found {len(subscribers)} promo code(s):\n")
        print(f"{'CODE':<20} {'EMAIL':<40} {'STATUS'}")
        print("-" * 75)

        for s in subscribers:
            status = "USED" if s.promo_code_used else "AVAILABLE"
            print(f"{s.promo_code:<20} {s.email:<40} {status}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: reset TESTPROMO10
        reset_promo_code("TESTPROMO10")
    elif sys.argv[1] == "--list":
        list_promo_codes()
    elif sys.argv[1] == "--create" and len(sys.argv) >= 3:
        code = sys.argv[2]
        email = sys.argv[3] if len(sys.argv) > 3 else None
        create_promo_code(code, email)
    elif sys.argv[1] == "--help":
        print(__doc__)
    else:
        # Reset specific code
        reset_promo_code(sys.argv[1])
