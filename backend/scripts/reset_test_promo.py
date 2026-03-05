#!/usr/bin/env python3
"""
Utility script to create/reset test promo codes for staging environment.

Supports two promo types:
- 10% OFF promo (promo_10_code field)
- FREE parking promo (promo_free_code field, 100% off)

Usage:
    python scripts/reset_test_promo.py --list              # List all promo codes
    python scripts/reset_test_promo.py --reset-10 CODE     # Reset a 10% promo code
    python scripts/reset_test_promo.py --reset-free CODE   # Reset a FREE promo code
    python scripts/reset_test_promo.py --create-10 CODE    # Create 10% promo code
    python scripts/reset_test_promo.py --create-free CODE  # Create FREE promo code
    python scripts/reset_test_promo.py --reset-all-test    # Reset all test promo codes
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from db_models import MarketingSubscriber


# Default test promo codes for automation testing
TEST_PROMO_10 = "TEST10OFF"      # 10% off promo for testing
TEST_PROMO_FREE = "TESTFREE"     # 100% off (FREE) promo for testing


def reset_promo_10_code(code: str) -> bool:
    """Reset a 10% promo code so it can be reused."""
    db = SessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_10_code == code.upper()
        ).first()

        if subscriber:
            subscriber.promo_10_used = False
            subscriber.promo_10_used_at = None
            subscriber.promo_10_used_booking_id = None
            db.commit()
            print(f"✓ Reset 10% promo code: {code.upper()}")
            print(f"  Email: {subscriber.email}")
            print(f"  Status: AVAILABLE")
            return True
        else:
            print(f"✗ 10% promo code not found: {code.upper()}")
            return False
    finally:
        db.close()


def reset_promo_free_code(code: str) -> bool:
    """Reset a FREE promo code so it can be reused."""
    db = SessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_free_code == code.upper()
        ).first()

        if subscriber:
            subscriber.promo_free_used = False
            subscriber.promo_free_used_at = None
            subscriber.promo_free_used_booking_id = None
            db.commit()
            print(f"✓ Reset FREE promo code: {code.upper()}")
            print(f"  Email: {subscriber.email}")
            print(f"  Status: AVAILABLE")
            return True
        else:
            print(f"✗ FREE promo code not found: {code.upper()}")
            return False
    finally:
        db.close()


def create_promo_10_code(code: str, email: str = None) -> bool:
    """Create a new 10% off test promo code."""
    import random
    import string

    db = SessionLocal()
    try:
        # Check if code already exists
        existing = db.query(MarketingSubscriber).filter(
            (MarketingSubscriber.promo_10_code == code.upper()) |
            (MarketingSubscriber.promo_free_code == code.upper()) |
            (MarketingSubscriber.promo_code == code.upper())
        ).first()

        if existing:
            print(f"✗ Promo code already exists: {code.upper()}")
            return False

        # Generate unique email if not provided
        if not email:
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            email = f"testpromo10_{suffix}@staging.example.com"

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User10",
            email=email,
            promo_10_code=code.upper(),
            promo_10_sent=True,  # Mark as sent so it's usable
            promo_10_used=False,
        )
        db.add(subscriber)
        db.commit()

        print(f"✓ Created 10% OFF promo code: {code.upper()}")
        print(f"  Email: {email}")
        print(f"  Discount: 10%")
        print(f"  Status: AVAILABLE")
        return True
    finally:
        db.close()


def create_promo_free_code(code: str, email: str = None) -> bool:
    """Create a new FREE parking (100% off) promo code."""
    import random
    import string

    db = SessionLocal()
    try:
        # Check if code already exists
        existing = db.query(MarketingSubscriber).filter(
            (MarketingSubscriber.promo_10_code == code.upper()) |
            (MarketingSubscriber.promo_free_code == code.upper()) |
            (MarketingSubscriber.promo_code == code.upper())
        ).first()

        if existing:
            print(f"✗ Promo code already exists: {code.upper()}")
            return False

        # Generate unique email if not provided
        if not email:
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            email = f"testpromofree_{suffix}@staging.example.com"

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="UserFree",
            email=email,
            promo_free_code=code.upper(),
            promo_free_sent=True,  # Mark as sent so it's usable
            promo_free_used=False,
        )
        db.add(subscriber)
        db.commit()

        print(f"✓ Created FREE parking promo code: {code.upper()}")
        print(f"  Email: {email}")
        print(f"  Discount: 100% (FREE)")
        print(f"  Status: AVAILABLE")
        return True
    finally:
        db.close()


def list_promo_codes():
    """List all promo codes in the system."""
    db = SessionLocal()
    try:
        subscribers = db.query(MarketingSubscriber).filter(
            (MarketingSubscriber.promo_code.isnot(None)) |
            (MarketingSubscriber.promo_10_code.isnot(None)) |
            (MarketingSubscriber.promo_free_code.isnot(None))
        ).all()

        if not subscribers:
            print("No promo codes found.")
            return

        print(f"\nFound {len(subscribers)} subscriber(s) with promo codes:\n")

        # 10% OFF promos
        print("=" * 80)
        print("10% OFF PROMOS (promo_10_code)")
        print("=" * 80)
        print(f"{'CODE':<20} {'EMAIL':<40} {'STATUS'}")
        print("-" * 80)
        found_10 = False
        for s in subscribers:
            if s.promo_10_code:
                found_10 = True
                status = "USED" if s.promo_10_used else "AVAILABLE"
                print(f"{s.promo_10_code:<20} {s.email:<40} {status}")
        if not found_10:
            print("  (none)")

        # FREE promos
        print("\n" + "=" * 80)
        print("FREE PARKING PROMOS (promo_free_code) - 100% OFF")
        print("=" * 80)
        print(f"{'CODE':<20} {'EMAIL':<40} {'STATUS'}")
        print("-" * 80)
        found_free = False
        for s in subscribers:
            if s.promo_free_code:
                found_free = True
                status = "USED" if s.promo_free_used else "AVAILABLE"
                print(f"{s.promo_free_code:<20} {s.email:<40} {status}")
        if not found_free:
            print("  (none)")

        # Legacy promos
        print("\n" + "=" * 80)
        print("LEGACY PROMOS (promo_code)")
        print("=" * 80)
        print(f"{'CODE':<20} {'DISCOUNT':<10} {'EMAIL':<30} {'STATUS'}")
        print("-" * 80)
        found_legacy = False
        for s in subscribers:
            if s.promo_code:
                found_legacy = True
                status = "USED" if s.promo_code_used else "AVAILABLE"
                discount = f"{s.discount_percent or 10}%"
                print(f"{s.promo_code:<20} {discount:<10} {s.email:<30} {status}")
        if not found_legacy:
            print("  (none)")

    finally:
        db.close()


def reset_all_test_codes():
    """Reset all standard test promo codes."""
    print("Resetting all test promo codes...\n")

    # Reset 10% test code
    reset_promo_10_code(TEST_PROMO_10)

    # Reset FREE test code
    reset_promo_free_code(TEST_PROMO_FREE)

    print("\nDone!")


def ensure_test_codes_exist():
    """Ensure the test promo codes exist, create if not."""
    db = SessionLocal()
    try:
        # Check for 10% test code
        sub_10 = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_10_code == TEST_PROMO_10
        ).first()

        if not sub_10:
            print(f"Creating test 10% promo code: {TEST_PROMO_10}")
            create_promo_10_code(TEST_PROMO_10, "test10off@staging.tagparking.com")
        else:
            print(f"✓ Test 10% promo code exists: {TEST_PROMO_10}")

        # Check for FREE test code
        sub_free = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_free_code == TEST_PROMO_FREE
        ).first()

        if not sub_free:
            print(f"Creating test FREE promo code: {TEST_PROMO_FREE}")
            create_promo_free_code(TEST_PROMO_FREE, "testfree@staging.tagparking.com")
        else:
            print(f"✓ Test FREE promo code exists: {TEST_PROMO_FREE}")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--list":
        list_promo_codes()
    elif cmd == "--reset-10" and len(sys.argv) >= 3:
        reset_promo_10_code(sys.argv[2])
    elif cmd == "--reset-free" and len(sys.argv) >= 3:
        reset_promo_free_code(sys.argv[2])
    elif cmd == "--create-10" and len(sys.argv) >= 3:
        email = sys.argv[3] if len(sys.argv) > 3 else None
        create_promo_10_code(sys.argv[2], email)
    elif cmd == "--create-free" and len(sys.argv) >= 3:
        email = sys.argv[3] if len(sys.argv) > 3 else None
        create_promo_free_code(sys.argv[2], email)
    elif cmd == "--reset-all-test":
        reset_all_test_codes()
    elif cmd == "--ensure-test":
        ensure_test_codes_exist()
    elif cmd == "--help":
        print(__doc__)
    else:
        print("Unknown command. Use --help for usage.")
        sys.exit(1)
