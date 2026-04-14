"""
Restore customer phone numbers from Stripe billing details.

Run with:
    python3 scripts/restore_phones_from_stripe.py --stripe-key "sk_live_xxx" --db-url "postgresql://..."

Or with environment variables:
    export STRIPE_SECRET_KEY="sk_live_xxx"
    export DATABASE_URL="postgresql://..."
    python3 scripts/restore_phones_from_stripe.py

This script:
1. Fetches all customers from Stripe with their billing phone numbers
2. Matches them to your database customers by email
3. Updates phone numbers for customers that currently have empty phones
"""
import os
import sys
import argparse

# Parse command line arguments first
parser = argparse.ArgumentParser(description='Restore phone numbers from Stripe')
parser.add_argument('--stripe-key', help='Stripe secret key (sk_live_xxx)')
parser.add_argument('--db-url', help='Database URL (postgresql://...)')
parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating database')
args = parser.parse_args()

# Use command line args or fall back to env vars
stripe_key = args.stripe_key or os.environ.get("STRIPE_SECRET_KEY")
db_url = args.db_url or os.environ.get("DATABASE_URL")

if not db_url:
    print("ERROR: Database URL required")
    print("Usage: python3 scripts/restore_phones_from_stripe.py --stripe-key 'sk_live_xxx' --db-url 'postgresql://...'")
    sys.exit(1)

if not stripe_key:
    print("ERROR: Stripe secret key required")
    print("Usage: python3 scripts/restore_phones_from_stripe.py --stripe-key 'sk_live_xxx' --db-url 'postgresql://...'")
    sys.exit(1)

# Set DATABASE_URL env var for database module import
os.environ["DATABASE_URL"] = db_url

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stripe
from database import SessionLocal
from db_models import Customer

def main():
    stripe.api_key = stripe_key
    dry_run = args.dry_run

    if dry_run:
        print("=== DRY RUN MODE - No changes will be made ===\n")

    print("Fetching customers from Stripe...")

    # Collect all Stripe customers with phone numbers
    stripe_phones = {}  # email -> phone
    has_more = True
    starting_after = None
    total_fetched = 0

    while has_more:
        params = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after

        customers = stripe.Customer.list(**params)

        for cust in customers.data:
            total_fetched += 1
            email = cust.email
            phone = None

            # Check phone field directly on customer
            if cust.phone:
                phone = cust.phone
            # Check billing address phone
            elif cust.address and cust.address.get("phone"):
                phone = cust.address["phone"]
            # Check shipping address phone
            elif cust.shipping and cust.shipping.get("phone"):
                phone = cust.shipping["phone"]
            # Check invoice settings (where billing details phone often is)
            elif cust.invoice_settings and cust.invoice_settings.get("default_payment_method"):
                # Need to fetch the payment method to get billing details
                try:
                    pm = stripe.PaymentMethod.retrieve(cust.invoice_settings["default_payment_method"])
                    if pm.billing_details and pm.billing_details.phone:
                        phone = pm.billing_details.phone
                except Exception:
                    pass

            if email and phone:
                # Normalize email to lowercase
                stripe_phones[email.lower()] = phone

        has_more = customers.has_more
        if customers.data:
            starting_after = customers.data[-1].id

    print(f"Fetched {total_fetched} customers from Stripe")
    print(f"Found {len(stripe_phones)} with email + phone")

    # Now update database
    db = SessionLocal()

    # Get customers with empty phone
    customers_to_update = db.query(Customer).filter(
        (Customer.phone == '') | (Customer.phone == None)
    ).all()

    print(f"Found {len(customers_to_update)} customers in DB with empty phone")

    updated = 0
    for cust in customers_to_update:
        email_lower = cust.email.lower() if cust.email else None
        if email_lower and email_lower in stripe_phones:
            phone = stripe_phones[email_lower]
            # Format phone number
            if not phone.startswith('+'):
                phone = '+' + phone.replace(' ', '').replace('-', '')
            print(f"  {cust.id}: {cust.first_name} {cust.last_name} ({cust.email}) -> {phone}")
            cust.phone = phone
            updated += 1

    if updated > 0:
        if dry_run:
            print(f"\n[DRY RUN] Would restore {updated} phone numbers")
            db.rollback()
        else:
            db.commit()
            print(f"\nRestored {updated} phone numbers")
    else:
        print("\nNo phone numbers to restore")

    db.close()

if __name__ == "__main__":
    main()
