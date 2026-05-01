"""
One-off backfill: record the Stripe refund for booking TAG-DYC21950 in the local DB.

Background: Kristian processed a full £68 refund for Paul Kinchin (TAG-DYC21950)
directly through the Stripe dashboard on 2026-04-17 14:04:27 BST after a
customer-service mix-up. The Stripe webhook either didn't fire or didn't update
the booking row, so the booking still shows status='completed' locally and the
payment row has no refund metadata. This script reconciles the local state.

Usage (read-only diagnostic — default):
    DATABASE_URL=<prod-url> python3 backend/scripts/backfill_refund_TAG-DYC21950.py

Usage (commit the changes):
    DATABASE_URL=<prod-url> python3 backend/scripts/backfill_refund_TAG-DYC21950.py --apply

Stripe refund metadata (from req_zf0Td49ZhdyFee):
    refund_id           re_3TG1enRtbty1KUNz1KWZop1f
    payment_intent      pi_3TG1enRtbty1KUNz1NrvmMyq
    amount              6800 pence (£68.00 — full)
    reason              requested_by_customer
    created             2026-04-17 14:04:27 BST → 2026-04-17 13:04:27 UTC
    initiated_by        kristian@tagparking.co.uk
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Allow running from repo root or backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from db_models import (  # noqa: E402
    AuditLog,
    AuditLogEvent,
    Booking,
    BookingStatus,
    Payment,
    PaymentStatus,
)


BOOKING_REFERENCE = "TAG-DYC21950"
EXPECTED_PAYMENT_INTENT = "pi_3TG1enRtbty1KUNz1NrvmMyq"
REFUND_ID = "re_3TG1enRtbty1KUNz1KWZop1f"
REFUND_AMOUNT_PENCE = 6800
REFUND_REASON = "requested_by_customer"
# 2026-04-17 14:04:27 BST = 13:04:27 UTC
REFUNDED_AT_UTC = datetime(2026, 4, 17, 13, 4, 27, tzinfo=timezone.utc)


def main(apply_changes: bool):
    db = SessionLocal()
    try:
        booking = (
            db.query(Booking)
            .filter(Booking.reference == BOOKING_REFERENCE)
            .first()
        )
        if booking is None:
            print(f"ABORT: no booking found with reference {BOOKING_REFERENCE!r}")
            return 1

        payment = (
            db.query(Payment).filter(Payment.booking_id == booking.id).first()
        )
        if payment is None:
            print(f"ABORT: booking {BOOKING_REFERENCE} has no payment row")
            return 1

        if payment.stripe_payment_intent_id != EXPECTED_PAYMENT_INTENT:
            print(
                f"ABORT: payment_intent mismatch — DB has "
                f"{payment.stripe_payment_intent_id!r}, expected "
                f"{EXPECTED_PAYMENT_INTENT!r}. Refusing to update the wrong row."
            )
            return 1

        print("=" * 72)
        customer_name = " ".join(
            n for n in (booking.customer_first_name, booking.customer_last_name) if n
        ) or "(no name on booking)"
        print(f"Booking      {booking.reference}  (id={booking.id})")
        print(f"Customer     {customer_name}")
        print(f"Drop-off     {booking.dropoff_date} {booking.dropoff_time}")
        print()
        print("BEFORE:")
        print(f"  bookings.status              = {booking.status.value}")
        print(f"  payments.status              = {payment.status.value}")
        print(f"  payments.amount_pence        = {payment.amount_pence}")
        print(f"  payments.refund_id           = {payment.refund_id}")
        print(f"  payments.refund_amount_pence = {payment.refund_amount_pence}")
        print(f"  payments.refund_reason       = {payment.refund_reason}")
        print(f"  payments.refunded_at         = {payment.refunded_at}")
        print()
        print("PROPOSED:")
        new_payment_status = (
            PaymentStatus.REFUNDED
            if REFUND_AMOUNT_PENCE >= (payment.amount_pence or 0)
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        print(f"  bookings.status              = {BookingStatus.REFUNDED.value}")
        print(f"  payments.status              = {new_payment_status.value}")
        print(f"  payments.refund_id           = {REFUND_ID}")
        print(f"  payments.refund_amount_pence = {REFUND_AMOUNT_PENCE}")
        print(f"  payments.refund_reason       = {REFUND_REASON}")
        print(f"  payments.refunded_at         = {REFUNDED_AT_UTC.isoformat()}")
        print("=" * 72)

        if not apply_changes:
            print("\nDry-run only. Re-run with --apply to commit these changes.")
            return 0

        booking.status = BookingStatus.REFUNDED
        payment.status = new_payment_status
        payment.refund_id = REFUND_ID
        payment.refund_amount_pence = REFUND_AMOUNT_PENCE
        payment.refund_reason = REFUND_REASON
        payment.refunded_at = REFUNDED_AT_UTC

        db.add(
            AuditLog(
                event=AuditLogEvent.BOOKING_REFUNDED.value,
                booking_reference=BOOKING_REFERENCE,
                event_data=json.dumps({
                    "refund_id": REFUND_ID,
                    "payment_intent_id": EXPECTED_PAYMENT_INTENT,
                    "refund_amount_pence": REFUND_AMOUNT_PENCE,
                    "refund_reason": REFUND_REASON,
                    "source": "manual_backfill_script",
                    "stripe_initiated_by": "kristian@tagparking.co.uk",
                    "stripe_request_id": "req_zf0Td49ZhdyFee",
                }),
            )
        )

        db.commit()
        print("\nAPPLIED. Booking status flipped to REFUNDED, payment row updated, audit row written.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"\nROLLED BACK due to error: {e!r}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the changes. Without this flag the script only prints the diff.",
    )
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(2)
    sys.exit(main(apply_changes=args.apply))
