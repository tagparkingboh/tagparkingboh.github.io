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


def create_promo_code(code: str, email: str = None, discount_percent: int = 10) -> bool:
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
            discount_percent=discount_percent,
        )
        db.add(subscriber)
        db.commit()

        print(f"✓ Created promo code: {code.upper()}")
        print(f"  Email: {email}")
        print(f"  Discount: {discount_percent}%")
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
        print(f"{'CODE':<20} {'DISCOUNT':<10} {'EMAIL':<35} {'STATUS'}")
        print("-" * 80)

        for s in subscribers:
            status = "USED" if s.promo_code_used else "AVAILABLE"
            discount = f"{s.discount_percent or 10}%"
            print(f"{s.promo_code:<20} {discount:<10} {s.email:<35} {status}")
    finally:
        db.close()


def create_100_off_codes(count: int = 5):
    """Create multiple 100% off test codes."""
    import secrets
    import string

    codes = []
    for i in range(count):
        # Generate code like FREE-XXXX
        suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        code = f"FREE-{suffix}"
        if create_promo_code(code, discount_percent=100):
            codes.append(code)

    if codes:
        print(f"\n{'='*50}")
        print(f"Created {len(codes)} 100% off promo codes:")
        for code in codes:
            print(f"  {code}")
    return codes


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: reset TESTPROMO10
        reset_promo_code("TESTPROMO10")
    elif sys.argv[1] == "--list":
        list_promo_codes()
    elif sys.argv[1] == "--create" and len(sys.argv) >= 3:
        code = sys.argv[2]
        email = sys.argv[3] if len(sys.argv) > 3 else None
        # Check for --100off flag
        discount = 100 if "--100off" in sys.argv else 10
        create_promo_code(code, email, discount_percent=discount)
    elif sys.argv[1] == "--create-free" or sys.argv[1] == "--100off":
        # Create multiple 100% off codes
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        create_100_off_codes(count)
    elif sys.argv[1] == "--help":
        print(__doc__)
        print("\nCommands:")
        print("  python reset_test_promo.py                    Reset TESTPROMO10")
        print("  python reset_test_promo.py CODE               Reset specific code")
        print("  python reset_test_promo.py --list             List all codes")
        print("  python reset_test_promo.py --create CODE      Create 10% off code")
        print("  python reset_test_promo.py --create CODE --100off  Create 100% off code")
        print("  python reset_test_promo.py --100off [N]       Create N 100% off codes (default 5)")
    else:
        # Reset specific code
        reset_promo_code(sys.argv[1])
