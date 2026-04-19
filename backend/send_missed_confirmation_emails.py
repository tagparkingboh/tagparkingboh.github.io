"""
One-time script to send confirmation emails that failed due to Stripe webhook bug.
Run this script directly: python send_missed_confirmation_emails.py
"""
import os
import sys
import time
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from email_service import send_booking_confirmation_email

# Use production database from environment variable
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("PRODUCTION_DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL or PRODUCTION_DATABASE_URL environment variable not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def format_date(d):
    """Format date as 'Saturday, 28 December 2025'."""
    if d:
        return d.strftime("%A, %d %B %Y")
    return ""


def format_time(t):
    """Format time as 'HH:MM'."""
    if t:
        return t.strftime("%H:%M")
    return ""


def main():
    db = SessionLocal()

    try:
        # Get online bookings from last 4 days that are CONFIRMED but didn't get confirmation email
        result = db.execute(text('''
            SELECT
                b.id,
                b.reference,
                c.email,
                c.first_name,
                c.last_name,
                b.customer_first_name,
                b.dropoff_date,
                b.dropoff_time,
                b.pickup_date,
                b.pickup_time,
                b.pickup_time_from,
                b.flight_departure_time,
                b.flight_arrival_time,
                b.dropoff_airline_name,
                b.dropoff_flight_number,
                b.dropoff_destination,
                b.pickup_airline_name,
                b.pickup_flight_number,
                b.pickup_origin,
                v.make,
                v.model,
                v.colour,
                v.registration,
                p.amount_pence
            FROM bookings b
            JOIN customers c ON b.customer_id = c.id
            JOIN vehicles v ON b.vehicle_id = v.id
            LEFT JOIN payments p ON p.booking_id = b.id
            WHERE b.created_at >= NOW() - INTERVAL '4 days'
            AND b.status = 'CONFIRMED'
            AND b.booking_source = 'online'
            AND (b.confirmation_email_sent = false OR b.confirmation_email_sent IS NULL)
            ORDER BY b.created_at DESC
        '''))

        rows = result.fetchall()
        print(f"\n{'='*60}")
        print(f"Found {len(rows)} bookings needing confirmation emails")
        print(f"{'='*60}\n")

        if not rows:
            print("No emails to send!")
            return

        # Ask for confirmation
        print("Bookings to process:")
        for row in rows:
            print(f"  - {row[1]}: {row[2]} ({row[5] or row[3]} {row[4]})")

        confirm = input(f"\nSend confirmation emails to these {len(rows)} customers? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

        sent_count = 0
        failed_count = 0

        for row in rows:
            booking_id = row[0]
            reference = row[1]
            email = row[2]
            first_name = row[5] or row[3]  # customer_first_name or customer.first_name
            dropoff_date = row[6]
            dropoff_time = row[7]
            pickup_date = row[8]
            pickup_time = row[9] or row[10]  # pickup_time or pickup_time_from
            flight_departure_time = row[11]
            flight_arrival_time = row[12]
            dropoff_airline_name = row[13]
            dropoff_flight_number = row[14]
            dropoff_destination = row[15]
            pickup_airline_name = row[16]
            pickup_flight_number = row[17]
            pickup_origin = row[18]
            vehicle_make = row[19]
            vehicle_model = row[20]
            vehicle_colour = row[21]
            vehicle_registration = row[22]
            amount_pence = row[23]

            # Format dates and times
            dropoff_date_str = format_date(dropoff_date)
            dropoff_time_str = format_time(dropoff_time)
            pickup_date_str = format_date(pickup_date)
            pickup_time_str = format_time(pickup_time)
            flight_arrival_time_str = format_time(flight_arrival_time)
            flight_departure_time_str = format_time(flight_departure_time)

            # Build flight info strings
            departure_flight = ""
            if dropoff_airline_name or dropoff_destination:
                parts = []
                if dropoff_airline_name:
                    parts.append(dropoff_airline_name)
                if dropoff_flight_number and dropoff_flight_number != 'Unknown':
                    parts.append(dropoff_flight_number)
                departure_flight = " ".join(parts)
                if dropoff_destination:
                    departure_flight += f" to {dropoff_destination}"

            return_flight = ""
            if pickup_airline_name or pickup_origin:
                parts = []
                if pickup_airline_name:
                    parts.append(pickup_airline_name)
                if pickup_flight_number and pickup_flight_number != 'Unknown':
                    parts.append(pickup_flight_number)
                return_flight = " ".join(parts)
                if pickup_origin:
                    return_flight += f" from {pickup_origin}"

            # Package name
            duration_days = (pickup_date - dropoff_date).days
            package_name = f"{duration_days} day{'s' if duration_days != 1 else ''}"

            # Amount paid
            amount_paid = f"£{amount_pence / 100:.2f}" if amount_pence else "N/A"

            print(f"\nSending to {email} ({reference})...", end=" ")

            try:
                success = send_booking_confirmation_email(
                    email=email,
                    first_name=first_name,
                    booking_reference=reference,
                    dropoff_date=dropoff_date_str,
                    dropoff_time=dropoff_time_str,
                    pickup_date=pickup_date_str,
                    pickup_time=pickup_time_str,
                    flight_arrival_time=flight_arrival_time_str,
                    flight_departure_time=flight_departure_time_str,
                    departure_flight=departure_flight,
                    return_flight=return_flight,
                    vehicle_make=vehicle_make,
                    vehicle_model=vehicle_model,
                    vehicle_colour=vehicle_colour,
                    vehicle_registration=vehicle_registration,
                    package_name=package_name,
                    amount_paid=amount_paid,
                    promo_code=None,  # We don't have promo info easily available
                    discount_amount=None,
                    original_amount=None,
                )

                if success:
                    print("OK")
                    sent_count += 1
                    # Update database
                    db.execute(text('''
                        UPDATE bookings
                        SET confirmation_email_sent = true,
                            confirmation_email_sent_at = NOW()
                        WHERE id = :booking_id
                    '''), {"booking_id": booking_id})
                    db.commit()
                else:
                    print("FAILED (email service returned false)")
                    failed_count += 1

            except Exception as e:
                print(f"ERROR: {e}")
                failed_count += 1

            # Rate limit: 1 email per second to avoid SendGrid throttling
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"COMPLETE: {sent_count} sent, {failed_count} failed")
        print(f"{'='*60}\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
