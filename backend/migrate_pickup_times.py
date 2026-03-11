#!/usr/bin/env python3
"""
Migration script to clean up pickup time fields.

This script:
1. Copies pickup_time to flight_arrival_time where flight_arrival_time is NULL
2. Updates pickup_time to be flight_arrival_time + 30 minutes

Run with --dry-run to preview changes without committing.
Run with --booking-id to test on a single booking first.
"""

import os
import sys
from datetime import time, timedelta, datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Staging database URL
STAGING_DB_URL = "postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway"


def add_30_minutes(t: time) -> time:
    """Add 30 minutes to a time object, handling midnight crossover."""
    if t is None:
        return None
    dt = datetime.combine(datetime.today(), t)
    dt += timedelta(minutes=30)
    return dt.time()


def run_migration(booking_id: int = None, dry_run: bool = True):
    """Run the migration."""
    print(f"\n{'='*60}")
    print(f"PICKUP TIME MIGRATION {'(DRY RUN)' if dry_run else '(LIVE)'}")
    print(f"{'='*60}")
    print(f"Database: Staging")
    print(f"Target: {'Booking ID ' + str(booking_id) if booking_id else 'ALL bookings'}")
    print(f"{'='*60}\n")

    engine = create_engine(STAGING_DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Build the WHERE clause
        where_clause = f"WHERE id = {booking_id}" if booking_id else ""

        # Step 1: Get current state
        query = text(f"""
            SELECT id, reference, pickup_time, pickup_time_from, pickup_time_to,
                   flight_arrival_time
            FROM bookings
            {where_clause}
            ORDER BY id
        """)

        result = session.execute(query)
        bookings = result.fetchall()

        print(f"Found {len(bookings)} booking(s) to process\n")

        changes = []
        for booking in bookings:
            booking_id_val, reference, pickup_time, pickup_time_from, pickup_time_to, flight_arrival_time = booking

            print(f"Booking {reference} (ID: {booking_id_val}):")
            print(f"  Current state:")
            print(f"    pickup_time:         {pickup_time}")
            print(f"    pickup_time_from:    {pickup_time_from}")
            print(f"    pickup_time_to:      {pickup_time_to}")
            print(f"    flight_arrival_time: {flight_arrival_time}")

            # Determine the arrival time to use
            if flight_arrival_time is not None:
                arrival = flight_arrival_time
            elif pickup_time is not None:
                arrival = pickup_time
            else:
                print(f"  -> SKIPPING: No time data available\n")
                continue

            # Calculate new pickup time (arrival + 30)
            new_pickup_time = add_30_minutes(arrival)

            print(f"  Proposed changes:")
            print(f"    flight_arrival_time: {arrival}")
            print(f"    pickup_time:         {new_pickup_time} (arrival + 30)")
            print()

            changes.append({
                'id': booking_id_val,
                'reference': reference,
                'flight_arrival_time': arrival,
                'pickup_time': new_pickup_time,
            })

        if not changes:
            print("No changes to make.")
            return

        if dry_run:
            print(f"\n{'='*60}")
            print("DRY RUN - No changes committed")
            print(f"{'='*60}")
            print(f"\nTo apply changes, run with --live flag")
            return

        # Apply changes
        print(f"\n{'='*60}")
        print("APPLYING CHANGES...")
        print(f"{'='*60}\n")

        for change in changes:
            update_query = text("""
                UPDATE bookings
                SET flight_arrival_time = :flight_arrival_time,
                    pickup_time = :pickup_time
                WHERE id = :id
            """)
            session.execute(update_query, {
                'id': change['id'],
                'flight_arrival_time': change['flight_arrival_time'],
                'pickup_time': change['pickup_time'],
            })
            print(f"  Updated {change['reference']}")

        session.commit()
        print(f"\n{'='*60}")
        print(f"SUCCESS: {len(changes)} booking(s) updated")
        print(f"{'='*60}")

        # Verify changes
        print("\nVerifying changes...")
        for change in changes:
            verify_query = text("""
                SELECT pickup_time, flight_arrival_time
                FROM bookings WHERE id = :id
            """)
            result = session.execute(verify_query, {'id': change['id']})
            row = result.fetchone()
            print(f"  {change['reference']}: pickup_time={row[0]}, flight_arrival_time={row[1]}")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate pickup time fields")
    parser.add_argument("--booking-id", type=int, help="Test on a single booking ID")
    parser.add_argument("--live", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--all", action="store_true", help="Process all bookings")

    args = parser.parse_args()

    if not args.booking_id and not args.all:
        print("Error: Must specify --booking-id or --all")
        sys.exit(1)

    dry_run = not args.live
    run_migration(booking_id=args.booking_id, dry_run=dry_run)
