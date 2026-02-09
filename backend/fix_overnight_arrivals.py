"""
Migration script to fix overnight arrival booking dates.

For flights that depart late evening and arrive after midnight (e.g., depart 22:00,
arrive 00:35), the pickup_date should be the ARRIVAL date (next day), not the
departure date.

This script:
1. Finds all bookings linked to arrival flights
2. Checks if the arrival time indicates an overnight flight (before 06:00)
3. Compares with the flight's departure time to confirm it's overnight
4. Corrects pickup_date to arrival date if needed

Run with: python fix_overnight_arrivals.py [--dry-run]
"""
import sys
from datetime import date, time, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session
from database import SessionLocal
from db_models import Booking, FlightArrival


def is_overnight_arrival(departure_time: time, arrival_time: time) -> bool:
    """
    Check if a flight is an overnight flight based on departure and arrival times.

    An overnight flight departs in the evening and arrives after midnight.
    E.g., depart 22:00, arrive 00:35 = overnight
    E.g., depart 10:00, arrive 14:00 = not overnight
    """
    if departure_time is None or arrival_time is None:
        return False

    # If arrival time is early morning (before 06:00) and departure was evening (after 18:00)
    # then it's likely an overnight flight
    arrival_hour = arrival_time.hour
    departure_hour = departure_time.hour

    # Arrival in early morning (00:00-05:59) and departure in evening (18:00-23:59)
    return arrival_hour < 6 and departure_hour >= 18


def fix_overnight_arrivals(db: Session, dry_run: bool = True) -> dict:
    """
    Find and fix bookings with incorrect pickup dates for overnight arrivals.

    Args:
        db: Database session
        dry_run: If True, only report issues without making changes

    Returns:
        Dict with counts of found and fixed bookings
    """
    results = {
        "total_bookings_checked": 0,
        "overnight_arrivals_found": 0,
        "bookings_needing_fix": 0,
        "bookings_fixed": 0,
        "details": []
    }

    # Get all bookings with linked arrival flights
    bookings_with_arrivals = db.query(Booking).filter(
        Booking.arrival_id.isnot(None)
    ).all()

    results["total_bookings_checked"] = len(bookings_with_arrivals)
    print(f"Checking {len(bookings_with_arrivals)} bookings with linked arrival flights...")

    for booking in bookings_with_arrivals:
        # Get the linked arrival flight
        arrival = db.query(FlightArrival).filter(
            FlightArrival.id == booking.arrival_id
        ).first()

        if not arrival:
            continue

        # Check if this is an overnight arrival
        if is_overnight_arrival(arrival.departure_time, arrival.arrival_time):
            results["overnight_arrivals_found"] += 1

            # The arrival flight's date should be the date it ARRIVES
            # For overnight flights, arrival date = departure date + 1 day
            # But we need to check if the booking's pickup_date matches the arrival's date

            # If the booking pickup_date doesn't match the arrival date, it needs fixing
            if booking.pickup_date != arrival.date:
                results["bookings_needing_fix"] += 1

                detail = {
                    "booking_id": booking.id,
                    "reference": booking.reference,
                    "flight_number": booking.pickup_flight_number,
                    "arrival_id": arrival.id,
                    "arrival_date_in_db": arrival.date.isoformat(),
                    "arrival_time": arrival.arrival_time.strftime("%H:%M") if arrival.arrival_time else None,
                    "departure_time": arrival.departure_time.strftime("%H:%M") if arrival.departure_time else None,
                    "current_pickup_date": booking.pickup_date.isoformat(),
                    "should_be": arrival.date.isoformat(),
                }
                results["details"].append(detail)

                print(f"\n  Booking {booking.reference} (ID: {booking.id})")
                print(f"    Flight: {booking.pickup_flight_number}")
                print(f"    Departs: {arrival.departure_time}, Arrives: {arrival.arrival_time}")
                print(f"    Current pickup_date: {booking.pickup_date}")
                print(f"    Should be: {arrival.date}")

                if not dry_run:
                    booking.pickup_date = arrival.date
                    results["bookings_fixed"] += 1
                    print(f"    -> FIXED")

    if not dry_run and results["bookings_fixed"] > 0:
        db.commit()
        print(f"\nCommitted {results['bookings_fixed']} fixes to database")

    return results


def check_arrival_flight_dates(db: Session) -> dict:
    """
    Check if arrival flight dates are stored correctly.

    For overnight flights, the arrival date should be the day AFTER departure.
    This checks if any arrivals need their date corrected.
    """
    results = {
        "total_arrivals": 0,
        "overnight_arrivals": 0,
        "potentially_wrong_dates": 0,
        "details": []
    }

    arrivals = db.query(FlightArrival).all()
    results["total_arrivals"] = len(arrivals)

    print(f"Checking {len(arrivals)} arrival flights...")

    for arrival in arrivals:
        if is_overnight_arrival(arrival.departure_time, arrival.arrival_time):
            results["overnight_arrivals"] += 1

            # For overnight flights, we can't easily tell if the date is wrong
            # without knowing the original schedule. But we flag them for review.
            detail = {
                "arrival_id": arrival.id,
                "flight_number": arrival.flight_number,
                "date": arrival.date.isoformat(),
                "departure_time": arrival.departure_time.strftime("%H:%M") if arrival.departure_time else None,
                "arrival_time": arrival.arrival_time.strftime("%H:%M") if arrival.arrival_time else None,
                "origin": arrival.origin_name,
            }
            results["details"].append(detail)

            print(f"\n  Flight {arrival.flight_number} (ID: {arrival.id})")
            print(f"    Date in DB: {arrival.date}")
            print(f"    Departs: {arrival.departure_time} from {arrival.origin_name}")
            print(f"    Arrives: {arrival.arrival_time}")
            print(f"    ** This is an overnight flight - verify date is ARRIVAL date **")

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix overnight arrival booking dates")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Only report issues without making changes (default)")
    parser.add_argument("--fix", action="store_true",
                        help="Actually fix the issues (disables dry-run)")
    parser.add_argument("--check-flights", action="store_true",
                        help="Check arrival flight dates instead of bookings")
    args = parser.parse_args()

    dry_run = not args.fix

    db = SessionLocal()
    try:
        if args.check_flights:
            print("=" * 60)
            print("CHECKING ARRIVAL FLIGHT DATES")
            print("=" * 60)
            results = check_arrival_flight_dates(db)
            print(f"\n\nSummary:")
            print(f"  Total arrivals: {results['total_arrivals']}")
            print(f"  Overnight arrivals: {results['overnight_arrivals']}")
        else:
            print("=" * 60)
            print(f"FIXING OVERNIGHT ARRIVAL BOOKINGS {'(DRY RUN)' if dry_run else '(LIVE)'}")
            print("=" * 60)

            if not dry_run:
                confirm = input("\nThis will modify the database. Type 'yes' to continue: ")
                if confirm.lower() != 'yes':
                    print("Aborted.")
                    return

            results = fix_overnight_arrivals(db, dry_run=dry_run)

            print(f"\n\nSummary:")
            print(f"  Total bookings checked: {results['total_bookings_checked']}")
            print(f"  Overnight arrivals found: {results['overnight_arrivals_found']}")
            print(f"  Bookings needing fix: {results['bookings_needing_fix']}")
            if not dry_run:
                print(f"  Bookings fixed: {results['bookings_fixed']}")
            else:
                print(f"\n  Run with --fix to apply changes")

    finally:
        db.close()


if __name__ == "__main__":
    main()
