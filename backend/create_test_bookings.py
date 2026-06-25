#!/usr/bin/env python3
"""
Create automated test bookings for TAG Parking staging environment.
Uses Playwright to automate the browser booking flow with Stripe test card.

Booking Flow:
1. Welcome modal (dismiss)
2. Step 1: Trip Details (flight selection, dates, times)
3. Step 2: Package Selection (pricing)
4. Step 3: Your Details (contact, billing, vehicle)
5. Step 4: Payment (Stripe)

Tests cover:
- Normal booking smoke: 7d, 14d, overnight, late-tier, 1d, and 8d boundary
- Promo core: TEST10, FREE100, and FREEWEEK at <=7 and >=8 billing-day boundaries
- Referral flows: two referree bookings and self-use guard coverage

Current lean staging set:
    01 7-day standard trip
    02 14-day trip
    07 Overnight flight 23:35 landing
    10 Late tier booking (<7 days)
    11 1-day minimum duration
    14 8-day trip (start of 8-9 tier)
    16 TEST10 7-day, return 23:30
    17 FREE100 7 billing days => £0
    18 FREEWEEK 7 billing days => £0
    19 FREEWEEK 8 billing days / 01:05 return => deduct AIRPORT_QUOTE_WEEK1_PRICE_PENCE
    20 FREE100 8 billing days / 01:05 return => £0
    23 Referral referree 1
    24 Referral referree 2
    25 Referral self-use referrer

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    python create_test_bookings.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo
import time
import random
import os
import sys
import psycopg2
import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
SINGLE_TEST = os.environ.get("SINGLE_TEST", "false").lower() == "true"  # Run only first test
PROMO_ONLY = os.environ.get("PROMO_ONLY", "false").lower() == "true"  # Run only promo code tests
REFERRAL_ONLY = os.environ.get("REFERRAL_ONLY", "false").lower() == "true"  # Run only referral code tests
AIRPORT_QUOTE_E2E_ONLY = os.environ.get("AIRPORT_QUOTE_E2E_ONLY", "false").lower() == "true"
TEST_FILTER = os.environ.get("TEST_FILTER", "")  # Filter tests by name (case-insensitive partial match)
TEST_INDEX = os.environ.get("TEST_INDEX", "")    # 1-based index of a single test to run (used by batch runner)
BROWSER = os.environ.get("BROWSER", "chromium").lower()  # chromium | firefox | webkit
DEVICE = os.environ.get("DEVICE", "")            # e.g. "iPhone 15 Pro", "iPad Pro 11"; empty for desktop

# Staging URL
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"
STAGING_API_URL = (
    os.environ.get("STAGING_API_URL")
    or os.environ.get("VITE_API_URL")
    or "https://staging.tagparking.co.uk"
).rstrip("/")

# Test customer details
CUSTOMER = {
    "first_name": "Mark",
    "last_name": "Testing",
    "email": "qa.orca.contact@gmail.com",
    "phone": "7441343276",
    "address1": "176 Shelbourne Rd",
    "city": "Bournemouth",
    "county": "Dorset",
    "postcode": "BH8 8RB",
}

# Test vehicle
VEHICLE = {
    "registration": "AA19MOT",
    "make": "Audi",
    "model": "A3",
    "colour": "White",
}

# Stripe test card
STRIPE_TEST_CARD = {
    "number": "4242424242424242",
    "expiry": "10/69",
    "cvc": "549",
}

# Staging database for promo code reset - uses environment variable.
# Railway/Staging exposes DATABASE_URL; STAGING_DATABASE_URL is supported for
# local explicitness when pointing at staging.
STAGING_DB_URL = os.environ.get("STAGING_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
# Parse URL into components for psycopg2 if needed
if STAGING_DB_URL:
    # URL format: postgresql://user:pass@host:port/dbname
    import re
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', STAGING_DB_URL)
    if match:
        STAGING_DB = {
            "user": match.group(1),
            "password": match.group(2),
            "host": match.group(3),
            "port": int(match.group(4)),
            "dbname": match.group(5)
        }
    else:
        STAGING_DB = None
else:
    STAGING_DB = None

# Test promo codes
TEST_PROMO_10 = "TEST10"         # 10% off promo
TEST_PROMO_FREE = "FREEWEEK"     # 1 week free promo
TEST_REFERRAL_CODE = "REF-JH2C-4WCH"  # qa.orca.contact@gmail.com referral code
MARKETING_PROMO_TYPES = {"10", "free", "free_week", "free_100"}

LEAN_STAGING_TEST_INDEXES = [1, 2, 7, 10, 11, 14, 16, 17, 18, 19, 20, 23, 24, 25]
AIRPORT_QUOTE_E2E_TODAY = os.environ.get(
    "AIRPORT_QUOTE_E2E_TODAY",
    datetime.now(ZoneInfo("Europe/London")).date().isoformat(),
)
AIRPORT_QUOTE_MATRIX = {
    "near-short": Decimal("25"),
    "near-long": Decimal("20"),
    "far-short": Decimal("15"),
    "far-long": Decimal("10"),
}
AIRPORT_QUOTE_MIN_PRICE_PENCE = 6500
AIRPORT_QUOTE_WEEK1_PRICE_PENCE = 6000
AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS = 70
AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS = 7

DYNAMIC_FLIGHT_OPTIONS = [
    {"airline": "Ryanair", "airline_code": "FR", "destination": "Alicante", "destination_code": "ALC"},
    {"airline": "Ryanair", "airline_code": "FR", "destination": "Faro", "destination_code": "FAO"},
    {"airline": "Ryanair", "airline_code": "FR", "destination": "Malaga", "destination_code": "AGP"},
    {"airline": "easyJet", "airline_code": "U2", "destination": "Malaga", "destination_code": "AGP"},
    {"airline": "easyJet", "airline_code": "U2", "destination": "Palma", "destination_code": "PMI"},
    {"airline": "TUI", "airline_code": "BY", "destination": "Tenerife", "destination_code": "TFS"},
]
DYNAMIC_DROPOFF_TIMES = ["06:45", "08:15", "09:30", "10:45", "12:20", "14:10"]


def reset_promo_code(promo_code: str, promo_type: str = "10") -> bool:
    """Reset a promo code after successful use so it can be reused.

    Args:
        promo_code: The promo code to reset
        promo_type: "10" for 10% promo, "free" for FREE promo
    """
    if promo_type == "referral":
        print(f"    Referral code {promo_code} is unlimited-use; no reset needed")
        return True
    if not STAGING_DB:
        print("    Warning: STAGING_DATABASE_URL is not set; cannot reset promo code")
        return False

    try:
        conn = psycopg2.connect(**STAGING_DB)
        cur = conn.cursor()

        cur.execute(
            '''
            SELECT id
            FROM promo_codes
            WHERE code = %s
            ''',
            (promo_code,),
        )
        promo_code_row = cur.fetchone()
        if promo_code_row:
            promo_code_id = promo_code_row[0]
            cur.execute(
                '''
                DELETE FROM promo_code_usages
                WHERE promo_code_id = %s
                ''',
                (promo_code_id,),
            )
            cur.execute(
                '''
                UPDATE promo_codes
                SET is_used = false,
                    used_at = NULL,
                    booking_id = NULL,
                    use_count = 0
                WHERE id = %s
                ''',
                (promo_code_id,),
            )
        elif promo_type == "10":
            cur.execute('''
                UPDATE marketing_subscribers
                SET promo_10_used = false,
                    promo_10_used_at = NULL,
                    promo_10_used_booking_id = NULL
                WHERE promo_10_code = %s
            ''', (promo_code,))
        else:  # free
            cur.execute('''
                UPDATE marketing_subscribers
                SET promo_free_used = false,
                    promo_free_used_at = NULL,
                    promo_free_used_booking_id = NULL
                WHERE promo_free_code = %s
            ''', (promo_code,))

        conn.commit()
        cur.close()
        conn.close()
        print(f"    Promo code {promo_code} reset for reuse")
        return True
    except Exception as e:
        print(f"    Warning: Could not reset promo code: {e}")
        return False

# Test cases - reduced set for initial testing
TEST_CASES = [
    # Standard Bookings
    {
        "name": "7-day standard trip",
        "days_from_now": 21,
        "duration": 7,
        "dropoff_time": "10:00",
        "return_time": "14:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "1234",
        "return_flight_number": "1235",
    },
    {
        "name": "14-day trip",
        "days_from_now": 10,
        "duration": 14,
        "dropoff_time": "08:30",
        "return_time": "16:30",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "456",
        "return_flight_number": "457",
    },
    # Extended Stay Tests
    {
        "name": "15-day extended stay (boundary)",
        "days_from_now": 30,
        "duration": 15,
        "dropoff_time": "09:00",
        "return_time": "12:00",
        "airline": "TUI",
        "airline_code": "BY",
        "destination": "Tenerife",
        "destination_code": "TFS",
        "flight_number": "123",
        "return_flight_number": "124",
    },
    {
        "name": "20-day extended stay",
        "days_from_now": 35,
        "duration": 20,
        "dropoff_time": "11:00",
        "return_time": "15:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "789",
        "return_flight_number": "790",
    },
    {
        "name": "30-day extended stay",
        "days_from_now": 60,
        "duration": 30,
        "dropoff_time": "07:00",
        "return_time": "18:00",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Palma",
        "destination_code": "PMI",
        "flight_number": "111",
        "return_flight_number": "112",
    },
    {
        "name": "60-day max duration",
        "days_from_now": 90,
        "duration": 60,
        "dropoff_time": "10:00",
        "return_time": "14:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Malta",
        "destination_code": "MLA",
        "flight_number": "999",
        "return_flight_number": "998",
    },
    # Overnight Flight Tests
    {
        "name": "Overnight flight 23:35 landing",
        "days_from_now": 20,
        "duration": 7,
        "dropoff_time": "16:00",
        "return_time": "23:35",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "333",
        "return_flight_number": "334",
    },
    {
        "name": "Overnight flight 23:45 landing",
        "days_from_now": 22,
        "duration": 7,
        "dropoff_time": "14:00",
        "return_time": "23:45",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "444",
        "return_flight_number": "445",
    },
    {
        "name": "Overnight flight 23:50 landing",
        "days_from_now": 25,
        "duration": 7,
        "dropoff_time": "12:00",
        "return_time": "23:50",
        "airline": "TUI",
        "airline_code": "BY",
        "destination": "Tenerife",
        "destination_code": "TFS",
        "flight_number": "555",
        "return_flight_number": "556",
    },
    # Late Tier Test
    {
        "name": "Late tier booking (<7 days)",
        "days_from_now": 3,
        "duration": 7,
        "dropoff_time": "09:00",
        "return_time": "13:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "666",
        "return_flight_number": "667",
    },
    # Duration Boundary Tests
    {
        "name": "1-day minimum duration",
        "days_from_now": 18,
        "duration": 1,
        "dropoff_time": "06:00",
        "return_time": "20:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "777",
        "return_flight_number": "778",
    },
    {
        "name": "4-day trip (end of 1-4 tier)",
        "days_from_now": 19,
        "duration": 4,
        "dropoff_time": "08:00",
        "return_time": "15:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "888",
        "return_flight_number": "889",
    },
    {
        "name": "5-day trip (start of 5-6 tier)",
        "days_from_now": 20,
        "duration": 5,
        "dropoff_time": "08:00",
        "return_time": "15:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "101",
        "return_flight_number": "102",
    },
    {
        "name": "8-day trip (start of 8-9 tier)",
        "days_from_now": 21,
        "duration": 8,
        "dropoff_time": "10:00",
        "return_time": "14:00",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Palma",
        "destination_code": "PMI",
        "flight_number": "201",
        "return_flight_number": "202",
    },
    # Standard Tier Test
    {
        "name": "Standard tier (7-13 days ahead)",
        "days_from_now": 8,
        "duration": 7,
        "dropoff_time": "11:00",
        "return_time": "16:00",
        "airline": "TUI",
        "airline_code": "BY",
        "destination": "Tenerife",
        "destination_code": "TFS",
        "flight_number": "301",
        "return_flight_number": "302",
    },
    # ============ PROMO CODE TESTS ============
    # 10% OFF Promo Code Test
    {
        "name": "10% OFF Promo Code (7-day trip)",
        "days_from_now": 25,
        "days_from_now_range": (21, 35),
        "dynamic_trip": True,
        "duration": 7,
        "dropoff_time": "10:00",
        "dropoff_time_options": ["07:30", "09:45", "12:15"],
        "return_time": "23:30",
        "return_time_options": ["23:30"],
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "1010",
        "return_flight_number": "1011",
        "promo_code": "TEST10",
        "promo_type": "10",
    },
    # FREE100 Promo Code Test (7 days = completely free)
    {
        "name": "FREE100 Promo (7-day) - 100% free",
        "days_from_now": 28,
        "days_from_now_range": (24, 38),
        "dynamic_trip": True,
        "duration": 7,
        "dropoff_time": "08:00",
        "return_time": "18:40",
        "airline": "Virgin Atlantic",
        "airline_code": "OTHER",
        "destination": "Barcelona",
        "destination_code": "OTHER",
        "flight_number": "VS100",
        "return_flight_number": "VS101",
        "promo_code": "FREE100",
        "promo_type": "free_100",
    },
    # FREEWEEK Promo Code Test (7 days = completely free - boundary max)
    {
        "name": "FREEWEEK Promo (7-day) - 100% free",
        "days_from_now": 30,
        "days_from_now_range": (26, 40),
        "dynamic_trip": True,
        "duration": 7,
        "dropoff_time": "09:00",
        "return_time": "05:30",
        "return_time_options": ["05:30"],
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "2020",
        "return_flight_number": "2021",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
    },
    # FREEWEEK Promo Code Test (7-night trip returning on 8th calendar day at 01:05)
    {
        "name": "FREEWEEK Promo (7-night, 8th-day 01:05) - pays extra day",
        "days_from_now": 32,
        "days_from_now_range": (28, 42),
        "dynamic_trip": True,
        "duration": 8,
        "dropoff_time": "10:00",
        "return_time": "01:05",
        "return_time_options": ["01:05"],
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "3030",
        "return_flight_number": "3031",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
    },
    # FREE100 Promo Code Test (8 days = completely free under same timing as FREEWEEK boundary)
    {
        "name": "FREE100 Promo (8-day) - 100% free",
        "days_from_now": 34,
        "days_from_now_range": (30, 44),
        "dynamic_trip": True,
        "duration": 8,
        "dropoff_time": "07:00",
        "return_time": "01:05",
        "return_time_options": ["01:05"],
        "airline": "Virgin Atlantic",
        "airline_code": "OTHER",
        "destination": "Madrid",
        "destination_code": "OTHER",
        "flight_number": "VS200",
        "return_flight_number": "VS201",
        "promo_code": "FREE100",
        "promo_type": "free_100",
    },
    # FREEWEEK Promo Code Test (14 days = 7-day deducted, pays 7 extra days)
    {
        "name": "FREEWEEK Promo (14-day) - pays 7 days",
        "days_from_now": 35,
        "days_from_now_range": (31, 45),
        "dynamic_trip": True,
        "duration": 14,
        "dropoff_time": "08:00",
        "return_time": "16:00",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Palma de Mallorca",
        "destination_code": "PMI",
        "flight_number": "4040",
        "return_flight_number": "4041",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
    },
    # 10% OFF Promo Code - 14-day trip boundary
    {
        "name": "10% OFF Promo (14-day trip)",
        "days_from_now": 38,
        "days_from_now_range": (34, 48),
        "dynamic_trip": True,
        "duration": 14,
        "dropoff_time": "11:00",
        "return_time": "13:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "5050",
        "return_flight_number": "5051",
        "promo_code": "TEST10",
        "promo_type": "10",
    },
    # Referral Code Tests
    {
        "name": "Referral code referree 1 (UK now + 60 days)",
        "days_from_now": 60,
        "date_timezone": "Europe/London",
        "duration": 7,
        "dropoff_time": "09:30",
        "return_time": "15:30",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "6060",
        "return_flight_number": "6061",
        "promo_code": TEST_REFERRAL_CODE,
        "promo_type": "referral",
        "customer": {
            "first_name": "Referral",
            "last_name": "FriendOne",
            "email": "qa.orca.contact+referral-friend1@gmail.com",
        },
    },
    {
        "name": "Referral code referree 2 (UK now + 60 days)",
        "days_from_now": 60,
        "date_timezone": "Europe/London",
        "duration": 14,
        "dropoff_time": "10:45",
        "return_time": "16:45",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "7070",
        "return_flight_number": "7071",
        "promo_code": TEST_REFERRAL_CODE,
        "promo_type": "referral",
        "customer": {
            "first_name": "Referral",
            "last_name": "FriendTwo",
            "email": "qa.orca.contact+referral-friend2@gmail.com",
        },
    },
    {
        "name": "Referral code self-use referrer",
        "days_from_now": 64,
        "duration": 7,
        "dropoff_time": "12:00",
        "return_time": "14:00",
        "airline": "Jet2",
        "airline_code": "LS",
        "destination": "Palma de Mallorca",
        "destination_code": "PMI",
        "flight_number": "8080",
        "return_flight_number": "8081",
        "promo_code": TEST_REFERRAL_CODE,
        "promo_type": "referral",
    },
    # ============ AIRPORT QUOTE MATRIX + CONVERSION E2E ============
    # These use the live Europe/London date by default (override with
    # AIRPORT_QUOTE_E2E_TODAY for pinned-date debugging). The form time is the
    # flight departure time; dropoff_slot_id fixes the customer handover time
    # used by the quote.
    {
        "name": "AQ matrix near-short converts (25%)",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 21,
        "duration": 3,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-short",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "AQ260",
        "return_flight_number": "AQ261",
    },
    {
        "name": "AQ matrix near-long converts (20%, 7d+1m => billing 8)",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 28,
        "duration": 7,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:31",
        "expected_band": "near-long",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "AQ270",
        "return_flight_number": "AQ271",
    },
    {
        "name": "AQ matrix far-short converts (15%)",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 82,
        "duration": 3,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "far-short",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "AQ280",
        "return_flight_number": "AQ281",
    },
    {
        "name": "AQ matrix far-long converts (10%)",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 85,
        "duration": 10,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "far-long",
        "airline": "TUI",
        "airline_code": "BY",
        "destination": "Tenerife",
        "destination_code": "TFS",
        "flight_number": "AQ290",
        "return_flight_number": "AQ291",
    },
    {
        "name": "AQ promo TEST10 near-short paid converts after floor",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 35,
        "duration": 3,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-short",
        "promo_code": "TEST10",
        "promo_type": "10",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "AQ300",
        "return_flight_number": "AQ301",
    },
    {
        "name": "AQ promo FREE100 near-short free converts without Stripe",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 36,
        "duration": 3,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-short",
        "promo_code": "FREE100",
        "promo_type": "free_100",
        "airline": "Virgin Atlantic",
        "airline_code": "OTHER",
        "destination": "Barcelona",
        "destination_code": "OTHER",
        "flight_number": "AQ310",
        "return_flight_number": "AQ311",
    },
    {
        "name": "AQ FREEWEEK 3d boundary free converts",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 37,
        "duration": 3,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-short",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "AQ320",
        "return_flight_number": "AQ321",
    },
    {
        "name": "AQ FREEWEEK 7d exact pickup boundary free converts",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 38,
        "duration": 7,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-short",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "AQ330",
        "return_flight_number": "AQ331",
    },
    {
        "name": "AQ FREEWEEK 7d+1m pickup boundary paid deducts 60",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 39,
        "duration": 7,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:31",
        "expected_band": "near-long",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Palma",
        "destination_code": "PMI",
        "flight_number": "AQ340",
        "return_flight_number": "AQ341",
    },
    {
        "name": "AQ FREEWEEK 10d paid deducts 60",
        "airport_quote_e2e": True,
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 40,
        "duration": 10,
        "dropoff_time": "12:00",
        "dropoff_slot_id": "120",
        "return_time": "09:30",
        "expected_band": "near-long",
        "promo_code": "FREEWEEK",
        "promo_type": "free_week",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "AQ350",
        "return_flight_number": "AQ351",
    },
    {
        "name": "AQ abandoned checkout leaves conversion false",
        "airport_quote_api_only": "abandon",
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 41,
        "duration": 3,
        "entry_time": "10:00",
        "exit_time": "10:00",
        "expected_band": "near-short",
    },
    {
        "name": "AQ re-show leaves first conversion row untouched",
        "airport_quote_api_only": "reshow",
        "today": AIRPORT_QUOTE_E2E_TODAY,
        "days_from_now": 42,
        "duration": 3,
        "entry_time": "10:00",
        "exit_time": "10:00",
        "expected_band": "near-short",
    },
    {
        "name": "AQ homepage comparison writes zero conversion rows",
        "airport_quote_api_only": "homepage",
    },
]

AIRPORT_QUOTE_E2E_INDEXES = [
    index
    for index, test_case in enumerate(TEST_CASES, start=1)
    if test_case.get("airport_quote_e2e") or test_case.get("airport_quote_api_only")
]


def get_today_for_test_case(test_case):
    """Return the test's date anchor; referral referrees use UK date boundaries."""
    if test_case.get("today"):
        return datetime.strptime(test_case["today"], "%Y-%m-%d").date()
    timezone_name = test_case.get("date_timezone")
    if timezone_name:
        return datetime.now(ZoneInfo(timezone_name)).date()
    return datetime.now().date()


def get_airport_quote_only_test_cases():
    return [tc for tc in TEST_CASES if tc.get("airport_quote_e2e") or tc.get("airport_quote_api_only")]


def is_marketing_promo_test(test_case):
    return test_case.get("promo_type", "10") in MARKETING_PROMO_TYPES


def is_referral_promo_test(test_case):
    return test_case.get("promo_type") == "referral"


def require_staging_db():
    if not STAGING_DB:
        raise RuntimeError("STAGING_DATABASE_URL or DATABASE_URL is required for airport quote E2E assertions")
    return STAGING_DB


def with_staging_db(query: str, params: tuple = (), fetch: str = "all"):
    conn = psycopg2.connect(**require_staging_db())
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "scalar":
            row = cur.fetchone()
            result = row[0] if row else None
        elif fetch == "none":
            result = None
        else:
            result = cur.fetchall()
        conn.commit()
        cur.close()
        return result
    finally:
        conn.close()


def parse_iso_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def add_days(date_text: str, days: int):
    return parse_iso_date(date_text) + timedelta(days=days)


def pence_floor_discount(cheapest_pence: int, discount_pct: Decimal) -> int:
    discounted = int(
        (Decimal(cheapest_pence) * (Decimal("1") - discount_pct / Decimal("100")))
        .to_integral_value(rounding=ROUND_FLOOR)
    )
    return max(min(discounted, cheapest_pence - 1), AIRPORT_QUOTE_MIN_PRICE_PENCE)


def expected_band_for(lead_days: int, billing_days: int) -> str:
    lead = "near" if lead_days <= AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS else "far"
    duration = "short" if billing_days <= AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS else "long"
    return f"{lead}-{duration}"


def expected_promo_total_for_airport_quote(tag_pence: int, promo_type: str, billing_days: int) -> Optional[int]:
    if promo_type == "10":
        return int(tag_pence * 0.9)
    if promo_type == "free_100":
        return 0
    if promo_type == "free_week":
        if billing_days <= 7:
            return 0
        return max(0, tag_pence - AIRPORT_QUOTE_WEEK1_PRICE_PENCE)
    return None


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"POST {url} failed with HTTP {exc.code}: {body[:500]}") from exc


def get_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body[:500]}") from exc


def airport_quote_payload_from_case(test_case: dict) -> dict:
    today = get_today_for_test_case(test_case)
    entry_date = today + timedelta(days=test_case["days_from_now"])
    exit_date = entry_date + timedelta(days=test_case["duration"])
    return {
        "entryDate": entry_date.isoformat(),
        "entryTime": test_case.get("entry_time", "10:00"),
        "exitDate": exit_date.isoformat(),
        "exitTime": test_case.get("exit_time", "10:00"),
        "destination": test_case.get("destination", "Other"),
    }


def fetch_airport_quote(payload: dict) -> tuple[dict, dict]:
    response = post_json(f"{STAGING_API_URL}/api/airport-parking/quote", payload)
    return response, payload


def airport_quote_snapshot_id_from_response(response: dict):
    return response.get("quoteId") or response.get("pricingInfo", {}).get("airport_quote_snapshot_id")


def conversion_row(snapshot_id: int):
    return with_staging_db(
        """
        SELECT airport_quote_snapshot_id, lead_days, billing_days, discount_band,
               tag_pence, cheapest_boh_pence, converted, shown_at
        FROM airport_quote_conversion_log
        WHERE airport_quote_snapshot_id = %s
        """,
        (snapshot_id,),
        fetch="one",
    )


def wait_for_conversion_state(snapshot_id: int, expected: bool, timeout_seconds: int = 45):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        row = conversion_row(snapshot_id)
        if row and bool(row[6]) is expected:
            return row
        time.sleep(1)
    row = conversion_row(snapshot_id)
    raise AssertionError(f"conversion row {snapshot_id} did not reach converted={expected}; last row={row}")


def assert_airport_quote_response_and_log(response: dict, request_payload: dict, expected_band: str):
    snapshot_id = airport_quote_snapshot_id_from_response(response)
    assert snapshot_id, f"quote response missing snapshot id: {response}"

    airport_prices = response.get("airportPrices") or []
    cheapest = min(int(item["pricePence"]) for item in airport_prices if int(item.get("pricePence") or 0) > 0)
    billing_days = int(response["billing_days"])
    lead_days = (parse_iso_date(request_payload["entryDate"]) - parse_iso_date(AIRPORT_QUOTE_E2E_TODAY)).days
    computed_band = expected_band_for(lead_days, billing_days)
    assert computed_band == expected_band, (
        f"test dates landed in {computed_band}, expected {expected_band}; "
        f"lead={lead_days}, billing={billing_days}, payload={request_payload}"
    )

    discount_pct = AIRPORT_QUOTE_MATRIX[expected_band]
    expected_tag = pence_floor_discount(cheapest, discount_pct)
    actual_tag = int(response["tagPricePence"])
    actual_discount = Decimal(str(response.get("pricingInfo", {}).get("discount_pct_used")))
    assert actual_discount == discount_pct, f"{expected_band} expected {discount_pct}% got {actual_discount}%"
    assert actual_tag == expected_tag, (
        f"{expected_band} expected TAG {expected_tag} from BOH {cheapest}, got {actual_tag}; "
        f"response={response}"
    )

    row = wait_for_conversion_state(int(snapshot_id), False, timeout_seconds=20)
    assert row[1] == lead_days, f"lead_days mismatch for snapshot {snapshot_id}: {row}"
    assert row[2] == billing_days, f"billing_days mismatch for snapshot {snapshot_id}: {row}"
    assert row[3] == expected_band, f"discount_band mismatch for snapshot {snapshot_id}: {row}"
    assert row[4] == expected_tag, f"tag_pence mismatch for snapshot {snapshot_id}: {row}"
    assert row[5] == cheapest, f"cheapest_boh_pence mismatch for snapshot {snapshot_id}: {row}"
    return {
        "snapshot_id": int(snapshot_id),
        "lead_days": lead_days,
        "billing_days": billing_days,
        "discount_band": expected_band,
        "tag_pence": expected_tag,
        "cheapest_boh_pence": cheapest,
        "shown_at": row[7],
    }


def assert_airport_quote_conversion_row(snapshot_id: int, expected_band: str, expected_converted: bool):
    row = wait_for_conversion_state(snapshot_id, expected_converted, timeout_seconds=60)
    lead_days = int(row[1])
    billing_days = int(row[2])
    cheapest = int(row[5])
    expected_tag = pence_floor_discount(cheapest, AIRPORT_QUOTE_MATRIX[expected_band])
    computed_band = expected_band_for(lead_days, billing_days)
    assert computed_band == expected_band, (
        f"snapshot {snapshot_id} landed in {computed_band}, expected {expected_band}; row={row}"
    )
    assert row[3] == expected_band, f"discount_band mismatch for snapshot {snapshot_id}: {row}"
    assert int(row[4]) == expected_tag, f"tag_pence mismatch for snapshot {snapshot_id}: {row}"
    return {
        "snapshot_id": int(snapshot_id),
        "lead_days": lead_days,
        "billing_days": billing_days,
        "discount_band": expected_band,
        "tag_pence": expected_tag,
        "cheapest_boh_pence": cheapest,
        "shown_at": row[7],
    }


def count_conversion_rows() -> int:
    return int(with_staging_db("SELECT COUNT(*) FROM airport_quote_conversion_log", fetch="scalar") or 0)


def run_airport_quote_api_only(test_case: dict, test_num: int) -> bool:
    print(f"\n[Test {test_num}] {test_case['name']}")
    try:
        mode = test_case["airport_quote_api_only"]
        if mode == "homepage":
            before = count_conversion_rows()
            get_json(f"{STAGING_API_URL}/api/airport-parking/homepage-comparison")
            after = count_conversion_rows()
            assert after == before, f"homepage comparison wrote conversion rows: before={before}, after={after}"
            print("  ✓ Homepage comparison wrote zero conversion rows")
            return True

        payload = airport_quote_payload_from_case(test_case)
        quote, request_payload = fetch_airport_quote(payload)
        state = assert_airport_quote_response_and_log(quote, request_payload, test_case["expected_band"])

        if mode == "abandon":
            row = conversion_row(state["snapshot_id"])
            assert row and bool(row[6]) is False, f"abandoned quote converted unexpectedly: {row}"
            print(f"  ✓ Abandoned quote {state['snapshot_id']} remains converted=false")
            return True

        if mode == "reshow":
            original_row = conversion_row(state["snapshot_id"])
            second_quote, _ = fetch_airport_quote(payload)
            second_id = int(second_quote["quoteId"])
            assert second_id != state["snapshot_id"], "re-show should create a fresh snapshot id"
            after_row = conversion_row(state["snapshot_id"])
            assert after_row == original_row, f"first conversion row was clobbered: before={original_row}, after={after_row}"
            print(f"  ✓ Re-show left first row {state['snapshot_id']} untouched")
            return True

        raise AssertionError(f"unknown airport_quote_api_only mode {mode}")
    except Exception as exc:
        print(f"  ✗ Airport quote API assertion failed: {exc}")
        return False


def get_promo_only_test_cases():
    return [tc for tc in TEST_CASES if tc.get("promo_code") and is_marketing_promo_test(tc)]


def get_referral_only_test_cases():
    return [tc for tc in TEST_CASES if is_referral_promo_test(tc)]


def resolve_dynamic_test_case(test_case: dict) -> dict:
    """Resolve per-run dynamic flight inputs for test cases that opt in."""
    if not test_case.get("dynamic_trip"):
        return test_case

    resolved = dict(test_case)
    if resolved.get("days_from_now_range"):
        start, end = resolved["days_from_now_range"]
        resolved["days_from_now"] = random.randint(start, end)

    flight = random.choice(DYNAMIC_FLIGHT_OPTIONS)
    resolved.update(flight)

    if resolved.get("dropoff_time_options"):
        resolved["dropoff_time"] = random.choice(resolved["dropoff_time_options"])
    else:
        resolved["dropoff_time"] = random.choice(DYNAMIC_DROPOFF_TIMES)

    if resolved.get("return_time_options"):
        resolved["return_time"] = random.choice(resolved["return_time_options"])

    return resolved


def format_date_for_picker(date_obj):
    """Format date as DD/MM/YYYY for the date picker."""
    return date_obj.strftime("%d/%m/%Y")


def select_date_in_picker(page: Page, date_obj, picker_id: str):
    """Select a date using the react-datepicker calendar UI."""
    # Click on the date picker input to open the calendar
    picker = page.locator(f"#{picker_id}")
    picker.click()
    time.sleep(0.5)

    # The react-datepicker shows a calendar popup
    # Navigate to the correct month/year if needed
    target_month = date_obj.month
    target_year = date_obj.year
    target_day = date_obj.day

    # Keep clicking next month until we reach the target month
    max_attempts = 24  # Maximum 2 years of navigation
    for _ in range(max_attempts):
        # Check current displayed month/year
        header = page.locator(".react-datepicker__current-month").text_content()
        # Header format is like "March 2026"
        if header:
            parts = header.split()
            if len(parts) == 2:
                displayed_month_name = parts[0]
                displayed_year = int(parts[1])

                month_names = ["January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]
                displayed_month = month_names.index(displayed_month_name) + 1

                if displayed_month == target_month and displayed_year == target_year:
                    break

                # Navigate forward or backward
                if (displayed_year < target_year or
                    (displayed_year == target_year and displayed_month < target_month)):
                    page.locator(".react-datepicker__navigation--next").click()
                else:
                    page.locator(".react-datepicker__navigation--previous").click()
                time.sleep(0.3)

    # Now click on the target day
    # Use the day button that matches our date
    day_selector = f".react-datepicker__day--0{target_day:02d}" if target_day < 10 else f".react-datepicker__day--0{target_day}"
    # Actually react-datepicker uses format like .react-datepicker__day--001 for day 1
    day_selector = f".react-datepicker__day--0{target_day:02d}"

    # Find day buttons that aren't from other months
    day_buttons = page.locator(f".react-datepicker__day:not(.react-datepicker__day--outside-month)")

    # Click on the day with the matching text
    for i in range(day_buttons.count()):
        button = day_buttons.nth(i)
        if button.text_content() == str(target_day):
            button.click()
            break

    time.sleep(0.5)


def dismiss_busy_warning(page: Page):
    """Dismiss the capacity warning modal when it appears during E2E flows."""
    try:
        warning_btn = page.locator(".busy-warning-btn")
        if warning_btn.is_visible(timeout=1000):
            print("    Dismissing busy-warning modal...")
            warning_btn.click()
            time.sleep(0.5)
    except Exception:
        pass


def dismiss_arrival_guidance(page: Page):
    """Dismiss the arrival date/time guidance modal when it blocks manual flight entry."""
    try:
        guidance = page.locator("text=/Please enter the arrival date and time shown for your flight/i")
        if guidance.is_visible(timeout=1000):
            got_it_btn = page.locator("button:has-text('Got it')").first
            if got_it_btn.is_visible(timeout=1000):
                print("    Dismissing arrival date/time guidance modal...")
                got_it_btn.click()
                time.sleep(0.5)
    except Exception:
        pass


def confirm_times_if_present(page: Page):
    """Confirm the trip-times modal when it appears during booking transitions."""
    try:
        confirm_btn = page.locator(
            "button:has-text('Yes, times are correct'), "
            "button:has-text('Yes times are correct'), "
            "button:has-text('Yes, the times are correct')"
        ).first
        if confirm_btn.is_visible(timeout=3000):
            print("    Confirming times modal...")
            confirm_btn.click()
            time.sleep(0.5)
    except Exception:
        pass


def wait_visible(page: Page, selector: str, timeout: int = 5000):
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=timeout)
    return locator


def short_pause(seconds: float = 0.2):
    time.sleep(seconds)


def digits_only(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def money_values_pence(text: str) -> list[int]:
    values = []
    for chunk in (text or "").split("£")[1:]:
        amount = []
        for ch in chunk:
            if ch.isdigit() or ch in ".,": 
                amount.append(ch)
            elif amount:
                break
        normalised = "".join(amount).replace(",", "")
        if normalised:
            try:
                values.append(int(round(float(normalised) * 100)))
            except ValueError:
                pass
    return values


def get_checkout_total_pence(page: Page) -> Optional[int]:
    selectors = [
        ".summary-item.total",
        ".booking-summary",
        ".order-summary",
        ".payment-summary",
        ".modal-content",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=500):
                values = money_values_pence(locator.text_content() or "")
                if values:
                    return values[-1]
        except Exception:
            pass
    return None


def get_airport_quote_week1_price_for_test() -> int:
    raw = os.environ.get("AIRPORT_QUOTE_WEEK1_PRICE_PENCE")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return AIRPORT_QUOTE_WEEK1_PRICE_PENCE


def expected_promo_total_pence(original_total_pence: int, promo_type: str, duration_days: int) -> Optional[int]:
    if promo_type == "10":
        return int(original_total_pence * 0.9)
    if promo_type == "free_100":
        return 0
    if promo_type == "free_week":
        if duration_days <= 7:
            return 0
        return max(0, original_total_pence - get_airport_quote_week1_price_for_test())
    return None


def parse_hhmm_for_test(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")[:2]
    return int(hour), int(minute)


def offset_hhmm_for_test(value: str, minutes_delta: int) -> str:
    hour, minute = parse_hhmm_for_test(value)
    total = (hour * 60 + minute + minutes_delta) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def calculate_billing_days_for_test(dropoff_date, dropoff_time: str, pickup_date, pickup_time: str) -> int:
    drop_hour, drop_minute = parse_hhmm_for_test(dropoff_time)
    pickup_hour, pickup_minute = parse_hhmm_for_test(pickup_time)
    dropoff_dt = datetime.combine(dropoff_date, datetime.min.time()).replace(hour=drop_hour, minute=drop_minute)
    pickup_dt = datetime.combine(pickup_date, datetime.min.time()).replace(hour=pickup_hour, minute=pickup_minute)
    elapsed_seconds = (pickup_dt - dropoff_dt).total_seconds()
    return max(1, int((elapsed_seconds + 24 * 60 * 60 - 1) // (24 * 60 * 60)))


def wait_for_total(page: Page, expected_total_pence: int, timeout_seconds: int = 12) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        total = get_checkout_total_pence(page)
        if total == expected_total_pence:
            return True
        short_pause(0.3)
    return False


def fill_stripe_input(locator, value: str, label: str, min_digits: int) -> bool:
    expected_digits = digits_only(value)
    for attempt in range(2):
        locator.wait_for(state="visible", timeout=10000)
        locator.click()
        short_pause(0.3)
        try:
            locator.fill(value)
        except Exception:
            pass
        short_pause(0.7)

        actual_digits = digits_only(locator.input_value())
        if len(actual_digits) >= min_digits:
            print(f"    {label} filled")
            return True

        locator.click()
        try:
            locator.fill("")
        except Exception:
            pass
        short_pause(0.3)
        locator.press_sequentially(value, delay=140)
        short_pause(0.8)

        actual_digits = digits_only(locator.input_value())
        if len(actual_digits) >= min_digits or actual_digits == expected_digits:
            print(f"    {label} filled")
            return True

        print(f"    {label} fill attempt {attempt + 1} incomplete: {actual_digits!r}")

    return False


def find_stripe_payment_frame(page: Page):
    """Find Stripe's card-number frame once Elements has mounted."""
    card_number_sel = "input[autocomplete='cc-number']"
    for _ in range(30):
        stripe_frames = [
            f for f in page.frames if "stripe" in (f.url or "").lower()
        ] or page.frames
        for frame in stripe_frames:
            try:
                if frame.locator(card_number_sel).count() > 0:
                    return frame
            except Exception:
                continue
        time.sleep(0.5)
    return None


def recover_payment_refresh_prompt(page: Page) -> bool:
    """Recover the payment step when Stripe asks for a page refresh."""
    refresh_text = page.locator(
        "text=/refresh the page|please refresh|refresh this page/i"
    ).first
    continue_btn = page.locator(
        "button:has-text('Continue to booking'), "
        "button:has-text('Continue Booking'), "
        "button:has-text('Continue to Booking')"
    ).first

    try:
        should_refresh = refresh_text.is_visible(timeout=1000) or continue_btn.is_visible(timeout=1000)
    except Exception:
        should_refresh = False

    if not should_refresh:
        return False

    print("    Stripe requested refresh; reloading and continuing booking...")
    page.reload(wait_until="load", timeout=45000)
    short_pause(2.0)
    continue_btn = page.locator(
        "button:has-text('Continue to booking'), "
        "button:has-text('Continue Booking'), "
        "button:has-text('Continue to Booking')"
    ).first
    try:
        continue_btn.wait_for(state="visible", timeout=15000)
        continue_btn.click()
        page.locator(
            ".promo-code-section, .promo-code-input input, "
            "iframe[name^='__privateStripeFrame'], "
            ".stripe-pay-btn, button:has-text('Pay ')"
        ).first.wait_for(state="visible", timeout=20000)
        return True
    except Exception as exc:
        print(f"    Refresh recovery did not reach payment surface: {exc}")
        page.screenshot(path="payment_refresh_recovery_failed.png")
        return False


def answer_heard_about_us_if_present(page: Page) -> bool:
    """Complete the attribution gate shown before terms for unique emails."""
    section = page.locator(".heard-about-us-section")
    try:
        if not section.is_visible(timeout=3000):
            return True
    except Exception:
        return True

    print("    Completing 'Where did you hear about us?' step...")
    try:
        section.locator("select").select_option("google")
        time.sleep(0.5)

        continue_btn = section.locator(".heard-about-us-submit, button:has-text('Continue')")
        continue_btn.click()
        page.locator("input[name='terms']").wait_for(state="attached", timeout=10000)
        print("    Attribution step completed")
        return True
    except Exception as e:
        print(f"    Error: Could not complete attribution step: {e}")
        page.screenshot(path="heard_about_us_failed.png")
        return False


def accept_terms(page: Page, test_num: int) -> bool:
    """Accept checkout terms; payment controls render only after this is checked."""
    print("    Accepting terms...")
    time.sleep(1)

    terms_input = page.locator("input[name='terms']")

    try:
        terms_input.wait_for(state="attached", timeout=10000)

        if terms_input.is_checked(timeout=1000):
            print("    Terms already accepted")
            return True

        page.evaluate("document.querySelector('input[name=\"terms\"]').click()")
        print("    Clicked terms checkbox via JavaScript")
        time.sleep(0.5)

        if terms_input.is_checked(timeout=1000):
            print("    Terms checkbox confirmed checked")
            return True

        page.evaluate("document.querySelector('input[name=\"terms\"]').checked = true")
        page.evaluate("document.querySelector('input[name=\"terms\"]').dispatchEvent(new Event('change', { bubbles: true }))")
        print("    Set terms via JavaScript fallback")
        return terms_input.is_checked(timeout=1000)
    except Exception as e:
        print(f"    Error: Could not click terms checkbox: {e}")
        page.screenshot(path=f"terms_failed_{test_num}.png")
        return False


def create_booking(page: Page, test_case: dict, test_num: int) -> bool:
    """Create a single test booking using the booking form."""

    test_case = resolve_dynamic_test_case(test_case)
    customer = {**CUSTOMER, **test_case.get("customer", {})}
    vehicle = {**VEHICLE, **test_case.get("vehicle", {})}

    today = get_today_for_test_case(test_case)
    dropoff_date = today + timedelta(days=test_case["days_from_now"])
    pickup_date = dropoff_date + timedelta(days=test_case["duration"])
    billing_dropoff_time = test_case["dropoff_time"]
    billing_pickup_time = test_case["return_time"]
    if test_case.get("airport_quote_e2e"):
        if test_case.get("dropoff_slot_id"):
            billing_dropoff_time = offset_hhmm_for_test(
                test_case["dropoff_time"],
                -int(test_case["dropoff_slot_id"]),
            )
        billing_pickup_time = offset_hhmm_for_test(test_case["return_time"], 30)
    billing_days = calculate_billing_days_for_test(
        dropoff_date,
        billing_dropoff_time,
        pickup_date,
        billing_pickup_time,
    )

    print(f"\n[Test {test_num}] {test_case['name']}")
    print(f"  Drop-off flight: {dropoff_date} at {test_case['dropoff_time']}")
    print(f"  Return arrival: {pickup_date} at {test_case['return_time']}")
    if test_case.get("airport_quote_e2e"):
        print(
            "  Quote billing window: "
            f"{dropoff_date} {billing_dropoff_time} -> {pickup_date} {billing_pickup_time}"
        )
    print(f"  Duration: {test_case['duration']} calendar days ({billing_days} billing days)")
    print(f"  Customer: {customer['email']}")

    try:
        airport_quote_capture = {"response": None, "request": None, "events": []}
        create_intent_capture = {"request": None, "response": None}
        airport_quote_state = None

        if test_case.get("airport_quote_e2e"):
            def capture_response(response):
                try:
                    if "/api/airport-parking/quote" in response.url:
                        event = {"status": response.status, "url": response.url}
                        if response.status != 200:
                            try:
                                event["body"] = response.text()[:300]
                            except Exception:
                                pass
                        airport_quote_capture["events"].append(event)
                        if response.status == 200:
                            airport_quote_capture["response"] = response.json()
                            try:
                                airport_quote_capture["request"] = response.request.post_data_json
                            except Exception:
                                airport_quote_capture["request"] = None
                    elif "/api/payments/create-intent" in response.url and response.status == 200:
                        create_intent_capture["response"] = response.json()
                except Exception:
                    pass

            def capture_request(request):
                try:
                    if "/api/payments/create-intent" in request.url and request.method == "POST":
                        create_intent_capture["request"] = request.post_data_json
                except Exception:
                    pass

            page.on("response", capture_response)
            page.on("request", capture_request)

        # Navigate to booking page. Use "load" instead of "networkidle" —
        # the app's network never idles within 30s on WebKit (Stripe Elements
        # keeps pinging, fonts/analytics in flight), which was failing every
        # WebKit/iOS test on page.goto. "load" fires once DOM + critical
        # resources are in; the time.sleep(3) below covers what little remains.
        # Retry on transient navigation errors (Netlify occasionally returns
        # ERR_CONNECTION_RESET when 4 parallel workers hit the URL at once).
        goto_err = None
        for attempt in range(3):
            try:
                page.goto(STAGING_URL, wait_until="load", timeout=45000)
                goto_err = None
                break
            except Exception as e:
                goto_err = e
                print(f"  page.goto attempt {attempt + 1}/3 failed: {e}")
                time.sleep(2)
        if goto_err:
            raise goto_err
        page.locator(".welcome-modal-btn, #dropoffDate").first.wait_for(state="visible", timeout=10000)

        # ============ WELCOME MODAL (shows first) ============
        print("  Handling welcome modal...")
        welcome_modal_btn = page.locator(".welcome-modal-btn")
        if welcome_modal_btn.is_visible(timeout=5000):
            print("    Closing welcome modal...")
            welcome_modal_btn.click()
            short_pause()

        # ============ STEP 1: Trip Details ============
        print("  Step 1: Filling trip details...")

        # Select Drop-off Date using the date picker
        print("    Selecting drop-off date...")
        select_date_in_picker(page, dropoff_date, "dropoffDate")
        dismiss_busy_warning(page)
        short_pause()

        # Select Airline
        print("    Selecting airline...")
        airline_dropdown = page.locator("#manualAirline")
        airline_dropdown.wait_for(state="visible", timeout=10000)
        if test_case["airline_code"] == "OTHER":
            # Select "Other" and fill in custom airline name
            airline_dropdown.select_option(value="Other")
            short_pause()
            other_airline_input = page.locator("#customDepartureAirline")
            other_airline_input.wait_for(state="visible", timeout=5000)
            other_airline_input.fill(test_case["airline"])
            print(f"    Entered custom airline: {test_case['airline']}")
        else:
            airline_dropdown.select_option(value=test_case["airline_code"])
        destination_dropdown = page.locator("#manualDestination")
        destination_dropdown.wait_for(state="visible", timeout=10000)

        # Select Destination
        print("    Selecting destination...")
        if test_case["destination_code"] == "OTHER":
            # Select "Other" and fill in custom destination name
            destination_dropdown.select_option(value="Other")
            short_pause()
            other_destination_input = page.locator("#customDestination")
            other_destination_input.wait_for(state="visible", timeout=5000)
            other_destination_input.fill(test_case["destination"])
            print(f"    Entered custom destination: {test_case['destination']}")
        else:
            destination_dropdown.select_option(value=test_case["destination_code"])
        short_pause()

        # Enter Flight Number
        print("    Entering flight number...")
        flight_number_input = page.locator("#manualFlightNumber")
        flight_number_input.wait_for(state="visible", timeout=10000)
        flight_number_input.fill(test_case["flight_number"])
        short_pause()

        # Enter Departure Time
        print("    Entering departure time...")
        flight_time_input = page.locator("#manualFlightTime")
        flight_time_input.wait_for(state="visible", timeout=10000)
        flight_time_input.fill(test_case["dropoff_time"])
        dismiss_busy_warning(page)
        short_pause()

        # Select Drop-off Time Slot - randomly select 2hr or 2.75hr slot
        print("    Selecting drop-off time slot...")
        wait_visible(page, ".dropoff-slot .slot-card", timeout=10000)
        dismiss_busy_warning(page)
        slot_cards = page.locator(".dropoff-slot .slot-card")
        slot_count = slot_cards.count()
        if slot_count > 0:
            requested_slot = test_case.get("dropoff_slot_id")
            random_index = random.randint(0, slot_count - 1)
            if requested_slot:
                wanted = "2 hours before" if requested_slot == "120" else "1½ hours before"
                for slot_index in range(slot_count):
                    slot_text = slot_cards.nth(slot_index).text_content() or ""
                    if wanted in slot_text:
                        random_index = slot_index
                        break
            selected_slot = slot_cards.nth(random_index)
            dismiss_busy_warning(page)
            selected_slot.click()
            # Get the slot label text for logging
            try:
                slot_text = selected_slot.text_content()
                print(f"    Selected slot {random_index + 1} of {slot_count}: {slot_text[:50]}...")
            except:
                print(f"    Selected slot {random_index + 1} of {slot_count}")
            short_pause()
        else:
            print("    No drop-off slots found!")

        # Select Return Date
        print("    Selecting return date...")
        short_pause()
        # The return date picker appears after selecting dropoff slot
        return_date_picker = page.locator(".date-picker-input").nth(1)
        if return_date_picker.is_visible(timeout=3000):
            return_date_picker.click()
            short_pause()

            # Navigate to correct month/year for pickup date
            target_month = pickup_date.month
            target_year = pickup_date.year
            target_day = pickup_date.day

            max_attempts = 24
            for _ in range(max_attempts):
                header = page.locator(".react-datepicker__current-month").text_content()
                if header:
                    parts = header.split()
                    if len(parts) == 2:
                        displayed_month_name = parts[0]
                        displayed_year = int(parts[1])

                        month_names = ["January", "February", "March", "April", "May", "June",
                                      "July", "August", "September", "October", "November", "December"]
                        displayed_month = month_names.index(displayed_month_name) + 1

                        if displayed_month == target_month and displayed_year == target_year:
                            break

                        if (displayed_year < target_year or
                            (displayed_year == target_year and displayed_month < target_month)):
                            page.locator(".react-datepicker__navigation--next").click()
                        else:
                            page.locator(".react-datepicker__navigation--previous").click()
                        short_pause(0.1)

            # Click on the day
            day_buttons = page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
            for i in range(day_buttons.count()):
                button = day_buttons.nth(i)
                if button.text_content() == str(target_day):
                    button.click()
                    break
            short_pause()
            dismiss_arrival_guidance(page)

        # Return flight details
        print("    Filling return flight details...")
        dismiss_busy_warning(page)
        dismiss_arrival_guidance(page)
        short_pause()

        # Select Return Airline
        return_airline_dropdown = page.locator("#manualArrivalAirline")
        if test_case["airline_code"] == "OTHER":
            return_airline_dropdown.select_option(value="Other")
            short_pause()
            custom_return_airline = page.locator("#customArrivalAirline")
            custom_return_airline.wait_for(state="visible", timeout=5000)
            custom_return_airline.fill(test_case["airline"])
        else:
            return_airline_dropdown.select_option(value=test_case["airline_code"])
        short_pause()

        # Select Origin (for return flight, origin is where they're coming FROM = departure destination)
        return_origin_dropdown = page.locator("#manualArrivalOrigin")
        if test_case["destination_code"] == "OTHER":
            return_origin_dropdown.select_option(value="Other")
            short_pause()
            custom_return_origin = page.locator("#customOrigin")
            custom_return_origin.wait_for(state="visible", timeout=5000)
            custom_return_origin.fill(test_case["destination"])
        else:
            return_origin_dropdown.select_option(value=test_case["destination_code"])
        short_pause()

        # Enter Return Flight Number
        return_flight_input = page.locator("#manualArrivalFlightNumber")
        if return_flight_input.is_visible():
            return_flight_input.fill(test_case["return_flight_number"])
        short_pause()

        # Enter Arrival Time
        arrival_time_input = page.locator("#manualArrivalFlightTime")
        if arrival_time_input.is_visible():
            arrival_time_input.fill(test_case["return_time"])
        dismiss_busy_warning(page)
        dismiss_arrival_guidance(page)
        short_pause()

        # ============ STEP 2: Package Selection ============
        print("  Proceeding to Step 2 (Package Selection)...")

        # Click Continue to Package Selection button
        dismiss_busy_warning(page)
        dismiss_arrival_guidance(page)
        package_btn = page.locator("button:has-text('Continue to Package Selection')")
        if package_btn.is_visible(timeout=5000):
            package_btn.click()
            short_pause()

        # A "Please double-check your times" confirmation modal can intercept
        # the Step 1 → Step 2 transition.
        confirm_times_if_present(page)
        wait_visible(page, "button.next-btn, button:has-text('Continue to Your Details'), button:has-text('Continue to Tag it'), button:has-text('Continue to TAG it')", timeout=15000)

        # Click Continue to Your Details button
        print("  Proceeding to Step 3 (Your Details)...")
        continue_details_btn = page.locator(
            "button.next-btn, "
            "button:has-text('Continue to Your Details'), "
            "button:has-text('Continue to Tag it'), "
            "button:has-text('Continue to TAG it')"
        ).first
        if continue_details_btn.is_visible(timeout=5000):
            continue_details_btn.click()
            short_pause()
        confirm_times_if_present(page)
        if continue_details_btn.is_visible(timeout=5000):
            print("    Continuing to your details after times confirmation...")
            continue_details_btn.click()
        page.locator("#firstName").wait_for(state="visible", timeout=15000)

        if test_case.get("airport_quote_e2e"):
            deadline = time.time() + 90
            while time.time() < deadline and not airport_quote_capture["response"]:
                short_pause(0.5)
            if not airport_quote_capture["response"] or not airport_quote_capture["request"]:
                raise AssertionError(
                    "airport quote response/request was not captured before checkout; "
                    f"events={airport_quote_capture['events']}"
                )
            airport_quote_state = assert_airport_quote_response_and_log(
                airport_quote_capture["response"],
                airport_quote_capture["request"],
                test_case["expected_band"],
            )
            billing_days = airport_quote_state["billing_days"]
            print(
                "    Airport quote verified: "
                f"snapshot={airport_quote_state['snapshot_id']} "
                f"band={airport_quote_state['discount_band']} "
                f"billing={airport_quote_state['billing_days']} "
                f"BOH=£{airport_quote_state['cheapest_boh_pence'] / 100:.2f} "
                f"TAG=£{airport_quote_state['tag_pence'] / 100:.2f}"
            )

        # ============ STEP 3: Your Details (Customer + Billing + Vehicle) ============
        print("  Step 3: Filling customer details...")

        # Fill contact information
        page.locator("#firstName").fill(customer["first_name"])
        short_pause(0.05)
        page.locator("#lastName").fill(customer["last_name"])
        short_pause(0.05)
        page.locator("#email").fill(customer["email"])
        short_pause(0.05)

        # Phone - using the PhoneInput component
        phone_input = page.locator(".phone-input input[type='tel']")
        phone_input.click()
        short_pause(0.05)
        phone_input.fill("+44" + customer["phone"])
        short_pause(0.1)

        # Fill billing address - enter postcode and use manual entry
        page.locator("#billingPostcode").fill(customer["postcode"])
        short_pause(0.1)

        # Click Find Address button
        page.locator("button:has-text('Find Address')").click()
        short_pause(0.5)

        # If address select appears, select first address or use manual entry
        try:
            if page.locator("#addressSelect").is_visible(timeout=3000):
                page.locator("#addressSelect").select_option(index=1)
                short_pause()
            else:
                page.locator("text=Enter address manually").click()
                short_pause()
        except:
            try:
                page.locator("text=Enter address manually").click()
                short_pause()
            except:
                pass

        # Fill address fields if visible/empty
        if not page.locator("#billingAddress1").input_value():
            page.locator("#billingAddress1").fill(customer["address1"])
        short_pause(0.05)

        if not page.locator("#billingCity").input_value():
            page.locator("#billingCity").fill(customer["city"])
        short_pause(0.05)

        if not page.locator("#billingCounty").input_value():
            page.locator("#billingCounty").fill(customer["county"])
        short_pause(0.05)

        # Vehicle Information
        print("  Filling vehicle details...")
        page.locator("#registration").fill(vehicle["registration"])
        short_pause(0.1)

        # Click DVLA Lookup button
        print("    Running DVLA lookup...")
        try:
            with page.expect_response(
                lambda response: "/api/vehicles/dvla-lookup" in response.url
                and response.request.method == "POST",
                timeout=15000,
            ) as dvla_response_info:
                page.locator("button.validate-btn").click()
            dvla_response = dvla_response_info.value
            print(f"    DVLA lookup response: {dvla_response.status}")
        except Exception:
            print("    Warning: DVLA lookup response was not observed within 15s")
        short_pause(1.5)

        try:
            page.locator(
                "#make.readonly-input, select#make, #colour.readonly-input, select#model"
            ).first.wait_for(state="visible", timeout=10000)
        except Exception:
            print("    Warning: vehicle fields did not settle within 10s")
        short_pause(0.75)

        # Check if DVLA verified the vehicle or if we need to select manually
        make_readonly = page.locator("#make.readonly-input")
        make_input = page.locator("input#make:not(.readonly-input)")
        make_select = page.locator("select#make")

        if make_readonly.is_visible(timeout=5000):
            print("    DVLA verified make:", make_readonly.input_value())
        elif make_input.is_visible(timeout=5000):
            print("    Entering make manually...")
            make_input.fill(vehicle["make"])
            short_pause()
        elif make_select.is_visible(timeout=5000):
            try:
                make_select.select_option(label=vehicle["make"])
                short_pause()
            except:
                make_select.select_option(value=vehicle["make"])
                short_pause()

        # Fill colour if needed
        colour_readonly = page.locator("#colour.readonly-input")
        colour_input = page.locator("#colour:not(.readonly-input)")

        if colour_readonly.is_visible(timeout=1000):
            print("    DVLA verified colour:", colour_readonly.input_value())
        elif colour_input.is_visible(timeout=1000):
            print("    Entering colour manually...")
            colour_input.fill(vehicle["colour"])
            short_pause()

        # Select model from dropdown when the active booking form exposes one.
        print("    Selecting model...")
        short_pause(1.0)
        model_select = page.locator("select#model")
        if model_select.is_visible(timeout=10000):
            try:
                model_select.select_option(label=vehicle["model"])
                print(f"    Selected model: {vehicle['model']}")
            except:
                print(f"    Model {vehicle['model']} not found, selecting Other...")
                model_select.select_option(value="Other")
                short_pause()
                page.locator("#customModel").fill(vehicle["model"])
            short_pause()
        else:
            print("    Model dropdown not visible on this form; continuing with make/colour")

        # Click Continue to Payment
        print("  Proceeding to Step 4 (Payment)...")
        short_pause(1.0)
        continue_payment_btn = page.locator("button:has-text('Continue to Payment')")
        if continue_payment_btn.is_visible(timeout=5000):
            continue_payment_btn.click()

            payment_step_ready = page.locator(
                ".promo-code-section, .promo-code-input input, "
                "iframe[name^='__privateStripeFrame'], "
                "button:has-text('Complete Free Booking')"
            ).first
            try:
                payment_step_ready.wait_for(state="visible", timeout=15000)
            except Exception:
                print("    Warning: Payment step did not show an expected ready marker within 15s")

        # ============ STEP 4: Payment ============
        print("  Step 4: Payment...")

        # Apply promo code if this test case has one
        promo_code = test_case.get("promo_code")
        promo_type = test_case.get("promo_type", "10")
        expected_total = None
        if airport_quote_state:
            pre_checkout_total = get_checkout_total_pence(page)
            if pre_checkout_total != airport_quote_state["tag_pence"]:
                raise AssertionError(
                    f"checkout pre-promo total {pre_checkout_total} did not match "
                    f"quote TAG {airport_quote_state['tag_pence']}"
                )
            print(f"    Checkout pre-promo TAG matched quote: £{pre_checkout_total / 100:.2f}")

        if promo_code:
            promo_applied = False
            if is_marketing_promo_test(test_case):
                reset_promo_code(promo_code, promo_type)
            print(f"    Applying promo code: {promo_code}")
            pre_promo_total = get_checkout_total_pence(page)
            if airport_quote_state:
                expected_total = expected_promo_total_for_airport_quote(
                    airport_quote_state["tag_pence"],
                    promo_type,
                    airport_quote_state["billing_days"],
                )
            else:
                expected_total = (
                    expected_promo_total_pence(pre_promo_total, promo_type, billing_days)
                    if pre_promo_total is not None
                    else None
                )
            if expected_total is not None:
                print(
                    f"    Expecting promo total: £{expected_total / 100:.2f} "
                    f"from £{pre_promo_total / 100:.2f}"
                )
            short_pause()

            # Find and fill promo code input
            promo_input = page.locator(
                ".promo-code-section .promo-code-input input, "
                ".promo-code-input input, "
                "input[placeholder*='promo' i]"
            ).first
            if promo_input.is_visible(timeout=5000):
                promo_input.fill(promo_code)
                short_pause()

                # Click Apply button
                apply_btn = page.locator(
                    ".promo-code-section .promo-apply-btn, "
                    ".promo-apply-btn, "
                    "button:has-text('Apply')"
                ).first
                if apply_btn.is_visible(timeout=3000):
                    apply_btn.click()
                    try:
                        page.locator("button:has-text('Checking')").wait_for(state="hidden", timeout=12000)
                    except Exception:
                        pass

                    if expected_total is not None and wait_for_total(page, expected_total):
                        print(f"    Promo code {promo_code} total matched expected amount")
                        promo_applied = True

                    # Check for success across current and legacy promo UI states.
                    success_indicators = [
                        page.locator(".promo-success, .promo-code-applied, .discount-applied").first,
                        page.locator(".promo-badge, button.promo-remove, .summary-item.discount, .discount-amount").first,
                        page.locator("text=/Promo code applied/i").first,
                    ]
                    if not promo_applied:
                        for indicator in success_indicators:
                            try:
                                if indicator.is_visible(timeout=10000):
                                    print(f"    Promo code {promo_code} applied successfully!")
                                    promo_applied = True
                                    break
                            except Exception:
                                pass

                    if not promo_applied:
                        promo_error = page.locator(".promo-error").first
                        if promo_error.is_visible(timeout=1000):
                            print(f"    Promo error: {promo_error.text_content()}")
                        else:
                            print(f"    Error: Could not confirm promo code applied")
                else:
                    print("    Error: Promo code Apply button not found")
            else:
                print("    Error: Promo code input not found")

            if not promo_applied:
                page.screenshot(path=f"promo_apply_failed_{test_num}.png")
                return False

        if not answer_heard_about_us_if_present(page):
            return False

        if not accept_terms(page, test_num):
            return False
        short_pause()

        # Free-booking short-circuit: 100% promo bookings render the green
        # "Complete Free Booking" button instead of the Stripe card form, so
        # the entire iframe-polling + card-fill block below is wasted work
        # (~15s) for those tests. Detect first; if present, skip Stripe.
        print("    Waiting for payment surface...")
        short_pause(0.5)
        free_booking_selector = (
            "button:has-text('Complete Free Booking'), "
            "button:has-text('Complete free booking'), "
            "button:has-text('Confirm Free Booking')"
        )
        free_booking_btn = page.locator(free_booking_selector).first
        try:
            is_free = expected_total == 0 and free_booking_btn.is_visible(timeout=2000)
        except Exception:
            is_free = False
        is_free = is_free or expected_total == 0

        if is_free:
            print("    Free booking detected — skipping Stripe card flow")
        else:
            short_pause(0.5)
            # The StripePaymentElement uses iframes for card input.
            print("    Filling card details...")
            try:
                # Find the Stripe payment iframe. It can take 2-5s after the
                # Continue-to-Payment click for Stripe Elements to attach the
                # iframe, so poll up to ~15s. Detect by the standard autocomplete
                # attribute the card number input always carries.
                CARD_NUMBER_SEL = "input[autocomplete='cc-number']"
                payment_frame = find_stripe_payment_frame(page)
                if not payment_frame and recover_payment_refresh_prompt(page):
                    latest_snapshot_id = airport_quote_snapshot_id_from_response(
                        airport_quote_capture["response"] or {}
                    )
                    if airport_quote_state and latest_snapshot_id and int(latest_snapshot_id) != airport_quote_state["snapshot_id"]:
                        old_snapshot_id = airport_quote_state["snapshot_id"]
                        airport_quote_state = assert_airport_quote_response_and_log(
                            airport_quote_capture["response"],
                            airport_quote_capture["request"],
                            test_case["expected_band"],
                        )
                        billing_days = airport_quote_state["billing_days"]
                        if promo_code:
                            expected_total = expected_promo_total_for_airport_quote(
                                airport_quote_state["tag_pence"],
                                promo_type,
                                airport_quote_state["billing_days"],
                            )
                        print(
                            "    Airport quote refreshed after payment recovery: "
                            f"{old_snapshot_id} -> {airport_quote_state['snapshot_id']}"
                        )
                    payment_frame = find_stripe_payment_frame(page)

                if payment_frame:
                    # Use standard autocomplete attributes — survive Stripe internal
                    # markup changes that the old `#payment-numberInput` IDs do not.
                    card_sel = "input[autocomplete='cc-number']"
                    exp_sel = "input[autocomplete='cc-exp']"
                    cvc_sel = "input[autocomplete='cc-csc']"

                    card_input = payment_frame.locator(card_sel)
                    if not fill_stripe_input(card_input, STRIPE_TEST_CARD["number"], "Card number", 16):
                        raise Exception("Card number did not fully populate")

                    expiry_input = payment_frame.locator(exp_sel)
                    if not fill_stripe_input(expiry_input, STRIPE_TEST_CARD["expiry"], "Expiry", 4):
                        raise Exception("Expiry did not fully populate")

                    cvc_input = payment_frame.locator(cvc_sel)
                    if not fill_stripe_input(cvc_input, STRIPE_TEST_CARD["cvc"], "CVC", 3):
                        raise Exception("CVC did not fully populate")
                    short_pause(1)
                else:
                    print("    Could not find Stripe payment frame after polling")
                    page.screenshot(path=f"no_stripe_frame_{test_num}.png")

            except Exception as stripe_err:
                print(f"    Stripe fill failed: {stripe_err}")

        # Wait for the pay button to become enabled (elementComplete=true) — up
        # to ~6s. fill() used to race this with a flat sleep(2); polling here
        # makes the wait deterministic.
        pay_btn_wait = page.locator(".stripe-pay-btn")
        for _ in range(50):
            try:
                if pay_btn_wait.is_visible(timeout=200) and not pay_btn_wait.is_disabled():
                    break
            except Exception:
                pass
            time.sleep(0.2)

        # Submit Payment - handle both paid and free bookings
        print("  Submitting payment...")

        # Check for FREE booking button first (£0 total)
        free_booking_btn = page.locator(free_booking_selector).first
        pay_btn = page.locator(".stripe-pay-btn, button:has-text('Pay ')")

        if expected_total == 0 and free_booking_btn.is_visible(timeout=10000):
            print("    Free booking detected - clicking 'Complete Free Booking'")
            free_booking_btn.click()
        elif pay_btn.is_visible(timeout=5000):
            # Check if button is enabled
            if not pay_btn.is_disabled():
                pay_btn.click()
            else:
                print("    Pay button is disabled - card details may not have filled correctly")
                page.screenshot(path=f"payment_disabled_{test_num}.png")
        else:
            print("    No payment button found!")
            page.screenshot(path=f"no_payment_btn_{test_num}.png")

        # Wait for confirmation
        print("  Waiting for booking confirmation...")
        time.sleep(10)

        # Check for REAL post-payment success only. The booking reference and
        # generic "Thank you" copy render before the charge completes, so any
        # fallback that accepts them produces false passes.
        success = False
        booking_ref = None

        success_marker = page.locator("text=Payment Successful")
        try:
            success_marker.wait_for(state="visible", timeout=30000)
            success = True
            try:
                ref_element = page.locator("text=/TAG-[A-Z0-9]+/")
                if ref_element.is_visible(timeout=3000):
                    booking_ref = ref_element.text_content()
            except Exception:
                pass
        except Exception:
            success = False

        if success:
            if booking_ref:
                print(f"  ✓ Booking created! Reference: {booking_ref}")
            else:
                print(f"  ✓ Booking created successfully!")

            if airport_quote_state:
                intent_request = create_intent_capture.get("request") or {}
                intent_response = create_intent_capture.get("response") or {}
                sent_snapshot_id = intent_request.get("airport_quote_snapshot_id")
                if not sent_snapshot_id:
                    raise AssertionError(
                        f"create-intent sent airport_quote_snapshot_id={sent_snapshot_id}, "
                        f"expected {airport_quote_state['snapshot_id']}"
                    )
                if int(sent_snapshot_id) != airport_quote_state["snapshot_id"]:
                    old_snapshot_id = airport_quote_state["snapshot_id"]
                    airport_quote_state = assert_airport_quote_conversion_row(
                        int(sent_snapshot_id),
                        test_case["expected_band"],
                        True,
                    )
                    print(
                        "    Payment used refreshed airport quote snapshot: "
                        f"{old_snapshot_id} -> {airport_quote_state['snapshot_id']}"
                    )
                expected_free = expected_total == 0
                if expected_free:
                    assert intent_response.get("is_free_booking") is True, intent_response
                    assert str(intent_response.get("payment_intent_id", "")).startswith("free_"), intent_response
                    print("    Free-booking path verified: no Stripe PaymentIntent")
                else:
                    assert intent_response.get("is_free_booking") in (False, None), intent_response
                    assert str(intent_response.get("payment_intent_id", "")).startswith("pi_"), intent_response
                    print("    Paid Stripe path verified via PaymentIntent response")

                wait_for_conversion_state(airport_quote_state["snapshot_id"], True, timeout_seconds=60)
                print(f"    Conversion row flipped true for snapshot {airport_quote_state['snapshot_id']}")

            # Reset promo code for reuse if this was a promo test
            if promo_code:
                reset_promo_code(promo_code, promo_type)

            return True
        else:
            print(f"  ✗ Could not confirm booking - checking page state...")
            # Take screenshot for debugging
            page.screenshot(path=f"booking_state_{test_num}.png")
            return False

    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
        page.screenshot(path=f"error_test_{test_num}.png")
        return False


def main():
    from playwright.sync_api import sync_playwright

    print("=" * 60)
    print("TAG Parking - Automated Test Booking Creator")
    print("=" * 60)
    print(f"URL: {STAGING_URL}")
    print(f"Customer: {CUSTOMER['first_name']} {CUSTOMER['last_name']}")
    print(f"Vehicle: {VEHICLE['colour']} {VEHICLE['make']} {VEHICLE['model']} ({VEHICLE['registration']})")
    print(f"Test cases: {len(TEST_CASES)}")
    print()

    with sync_playwright() as p:
        # Use headless mode for CI/automation, headed for local debugging
        slow_mo = 0 if HEADLESS else 100
        if BROWSER not in ("chromium", "firefox", "webkit"):
            raise ValueError(f"Unsupported BROWSER={BROWSER}")
        browser = getattr(p, BROWSER).launch(headless=HEADLESS, slow_mo=slow_mo)
        if DEVICE:
            device_cfg = p.devices.get(DEVICE)
            if device_cfg is None:
                raise ValueError(f"Unknown DEVICE={DEVICE}")
            context = browser.new_context(**device_cfg)
            print(f"Browser: {BROWSER} / Device: {DEVICE}")
        else:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            print(f"Browser: {BROWSER} (desktop)")
        page = context.new_page()

        results = {"success": [], "failed": []}

        # Filter test cases based on environment variables
        if TEST_INDEX:
            idx = int(TEST_INDEX) - 1
            test_cases_to_run = [TEST_CASES[idx]]
            print(f"Running single test by index {TEST_INDEX}: {TEST_CASES[idx]['name']}")
        elif SINGLE_TEST:
            test_cases_to_run = TEST_CASES[:1]
        elif PROMO_ONLY:
            test_cases_to_run = get_promo_only_test_cases()
            print(f"Running PROMO_ONLY: {len(test_cases_to_run)} promo code tests")
        elif REFERRAL_ONLY:
            test_cases_to_run = get_referral_only_test_cases()
            print(f"Running REFERRAL_ONLY: {len(test_cases_to_run)} referral code tests")
        elif AIRPORT_QUOTE_E2E_ONLY:
            test_cases_to_run = get_airport_quote_only_test_cases()
            print(f"Running AIRPORT_QUOTE_E2E_ONLY: {len(test_cases_to_run)} airport quote tests")
        elif TEST_FILTER:
            test_cases_to_run = [tc for tc in TEST_CASES if TEST_FILTER.lower() in tc["name"].lower()]
            print(f"Running tests matching '{TEST_FILTER}': {len(test_cases_to_run)} tests")
        else:
            test_cases_to_run = TEST_CASES

        for i, test_case in enumerate(test_cases_to_run, 1):
            if test_case.get("airport_quote_api_only"):
                success = run_airport_quote_api_only(test_case, i)
            else:
                success = create_booking(page, test_case, i)
            if success:
                results["success"].append(test_case["name"])
            else:
                results["failed"].append(test_case["name"])

            # Delay between tests
            time.sleep(3)

        browser.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successful: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")

    if results["success"]:
        print("\nSuccessful bookings:")
        for name in results["success"]:
            print(f"  ✓ {name}")

    if results["failed"]:
        print("\nFailed bookings:")
        for name in results["failed"]:
            print(f"  ✗ {name}")

    # Non-zero exit so callers (run_staging_batches.py, CI) see real failures.
    sys.exit(0 if not results["failed"] else 1)


if __name__ == "__main__":
    main()
