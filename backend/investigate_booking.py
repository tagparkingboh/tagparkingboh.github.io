#!/usr/bin/env python3
"""Investigate booking TAG-C1G6XKGK and promo code status."""

import os
import sys

# Get database URL from environment variable
if 'DATABASE_URL' not in os.environ:
    print("Error: DATABASE_URL environment variable not set")
    print("Usage: DATABASE_URL='postgresql://...' python investigate_booking.py")
    sys.exit(1)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ['DATABASE_URL'])
Session = sessionmaker(bind=engine)
db = Session()

# Import models
from db_models import Booking, PromoCode, Promotion, Payment

# Find the booking
booking_ref = "TAG-C1G6XKGK"
booking = db.query(Booking).filter(Booking.reference == booking_ref).first()

print("=" * 60)
print(f"BOOKING: {booking_ref}")
print("=" * 60)

if booking:
    print(f"Booking ID: {booking.id}")
    print(f"Reference: {booking.reference}")
    print(f"Status: {booking.status}")
    print(f"Created: {booking.created_at}")
    print(f"Customer ID: {booking.customer_id}")

    # Check payment
    payment = db.query(Payment).filter(Payment.booking_id == booking.id).first()
    if payment:
        print(f"\nPayment Status: {payment.status}")
        print(f"Payment Amount: £{payment.amount_pence / 100 if payment.amount_pence else 0}")
else:
    print("Booking NOT FOUND!")

# Find the promotion "Testing Promo Codes 20% 16/3/2026"
print("\n" + "=" * 60)
print("PROMOTION: Testing Promo Codes 20% 16/3/2026")
print("=" * 60)

promotion = db.query(Promotion).filter(
    Promotion.name.ilike("%Testing Promo Codes 20%")
).first()

if promotion:
    print(f"Promotion ID: {promotion.id}")
    print(f"Name: {promotion.name}")
    print(f"Codes Sent: {promotion.codes_sent}")
    print(f"Codes Used: {promotion.codes_used}")

    # Get all promo codes for this promotion
    promo_codes = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion.id
    ).all()

    print(f"\nPromo Codes ({len(promo_codes)} total):")
    for pc in promo_codes:
        booking_ref_for_code = None
        if pc.booking_id:
            b = db.query(Booking).filter(Booking.id == pc.booking_id).first()
            if b:
                booking_ref_for_code = b.reference

        print(f"  - Code: {pc.code}")
        print(f"    Is Used: {pc.is_used}")
        print(f"    Used At: {pc.used_at}")
        print(f"    Booking ID: {pc.booking_id}")
        print(f"    Booking Ref: {booking_ref_for_code}")
        print()
else:
    print("Promotion NOT FOUND!")
    # Try to find any promotions with similar names
    print("\nSearching for similar promotions...")
    all_promos = db.query(Promotion).all()
    for p in all_promos:
        if "test" in p.name.lower() or "20" in p.name:
            print(f"  - {p.id}: {p.name}")

# Also check if there's a promo code linked to this booking
print("\n" + "=" * 60)
print("PROMO CODES LINKED TO BOOKING TAG-C1G6XKGK")
print("=" * 60)

if booking:
    linked_codes = db.query(PromoCode).filter(
        PromoCode.booking_id == booking.id
    ).all()

    if linked_codes:
        for pc in linked_codes:
            print(f"Code: {pc.code}, Promotion ID: {pc.promotion_id}")
    else:
        print("No promo codes linked to this booking!")

# Check the Payment record for promo code details
print("\n" + "=" * 60)
print("PAYMENT DETAILS FOR TAG-C1G6XKGK")
print("=" * 60)

if booking:
    payment = db.query(Payment).filter(Payment.booking_id == booking.id).first()
    if payment:
        # Print all payment attributes
        print(f"Payment ID: {payment.id}")
        print(f"Status: {payment.status}")
        print(f"Amount: £{payment.amount_pence / 100 if payment.amount_pence else 0}")

# Check what promo code the user said they used
print("\n" + "=" * 60)
print("SEARCHING FOR PROMO CODE THAT SHOULD HAVE BEEN USED")
print("=" * 60)

# Check the Stripe payment link - it might contain promo code info
if booking:
    payment = db.query(Payment).filter(Payment.booking_id == booking.id).first()
    if payment and payment.stripe_payment_link:
        print(f"Stripe Payment Link: {payment.stripe_payment_link}")

# Check the booking notes field
if booking:
    print(f"\nBooking notes: {booking.notes}")

# List all unused codes from the promotion
unused_codes = db.query(PromoCode).filter(
    PromoCode.promotion_id == 17,
    PromoCode.is_used == False
).all()

print(f"\nUnused codes from promotion 17: {[c.code for c in unused_codes]}")

# Check if any code exists that might match what user entered (case sensitivity issue?)
all_codes = db.query(PromoCode).filter(PromoCode.promotion_id == 17).all()
print(f"\nAll codes from promotion: {[c.code for c in all_codes]}")

# Check the payment links for bookings that DID have promo codes linked
print("\n" + "=" * 60)
print("COMPARING PAYMENT LINKS FOR PROMO-LINKED BOOKINGS")
print("=" * 60)

# Booking 347 (TAG-NKQ08686) used TAG-IPNA-8L7R
booking_347 = db.query(Booking).filter(Booking.id == 347).first()
if booking_347:
    payment_347 = db.query(Payment).filter(Payment.booking_id == 347).first()
    print(f"Booking 347 (TAG-NKQ08686) - used promo TAG-IPNA-8L7R")
    print(f"  Payment Link: {payment_347.stripe_payment_link if payment_347 else 'N/A'}")
    print(f"  Amount: £{payment_347.amount_pence / 100 if payment_347 else 'N/A'}")

# Booking 348 (TAG-MNF73277) used TAG-V2ZT-39LG
booking_348 = db.query(Booking).filter(Booking.id == 348).first()
if booking_348:
    payment_348 = db.query(Payment).filter(Payment.booking_id == 348).first()
    print(f"\nBooking 348 (TAG-MNF73277) - used promo TAG-V2ZT-39LG")
    print(f"  Payment Link: {payment_348.stripe_payment_link if payment_348 else 'N/A'}")
    print(f"  Amount: £{payment_348.amount_pence / 100 if payment_348 else 'N/A'}")

# Current booking
print(f"\nBooking 358 (TAG-C1G6XKGK) - NO promo linked")
print(f"  Payment Link: https://buy.stripe.com/test_9B6bJ378a7wH0Uf5cm04807")
print(f"  Amount: £176.8")

db.close()
