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
- Extended stays (15, 20, 30, 60 days)
- Overnight flights (23:35, 23:45, 23:50 landings)
- Duration tier boundaries (1, 4, 5, 8, 14, 15 days)
- Pricing tier boundaries (early, standard, late)

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    python create_test_bookings.py
"""

from playwright.sync_api import sync_playwright, Page
from datetime import datetime, timedelta
import time
import random
import os
import sys
import psycopg2

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
SINGLE_TEST = os.environ.get("SINGLE_TEST", "false").lower() == "true"  # Run only first test
PROMO_ONLY = os.environ.get("PROMO_ONLY", "false").lower() == "true"  # Run only promo code tests
TEST_FILTER = os.environ.get("TEST_FILTER", "")  # Filter tests by name (case-insensitive partial match)
TEST_INDEX = os.environ.get("TEST_INDEX", "")    # 1-based index of a single test to run (used by batch runner)
BROWSER = os.environ.get("BROWSER", "chromium").lower()  # chromium | firefox | webkit
DEVICE = os.environ.get("DEVICE", "")            # e.g. "iPhone 15 Pro", "iPad Pro 11"; empty for desktop

# Staging URL
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

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

# Staging database for promo code reset - uses environment variable
# Set STAGING_DATABASE_URL before running promo code tests
STAGING_DB_URL = os.environ.get("STAGING_DATABASE_URL", "")
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
TEST_PROMO_10 = "TEST10OFF"      # 10% off promo
TEST_PROMO_FREE = "TESTFREE"     # 100% off (FREE) promo


def reset_promo_code(promo_code: str, promo_type: str = "10") -> bool:
    """Reset a promo code after successful use so it can be reused.

    Args:
        promo_code: The promo code to reset
        promo_type: "10" for 10% promo, "free" for FREE promo
    """
    try:
        conn = psycopg2.connect(**STAGING_DB)
        cur = conn.cursor()

        if promo_type == "10":
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
        "duration": 7,
        "dropoff_time": "10:00",
        "return_time": "14:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "1010",
        "return_flight_number": "1011",
        "promo_code": "TEST10OFF",
        "promo_type": "10",
    },
    # FREE Parking Promo Code Test (5 days = completely free - under 7 day limit)
    {
        "name": "FREE Promo (5-day) - 100% free",
        "days_from_now": 28,
        "duration": 5,
        "dropoff_time": "08:00",
        "return_time": "14:00",
        "airline": "Virgin Atlantic",
        "airline_code": "OTHER",
        "destination": "Barcelona",
        "destination_code": "OTHER",
        "flight_number": "VS100",
        "return_flight_number": "VS101",
        "promo_code": "TESTFREE",
        "promo_type": "free",
    },
    # FREE Parking Promo Code Test (7 days = completely free - boundary max)
    {
        "name": "FREE Promo (7-day) - 100% free",
        "days_from_now": 30,
        "duration": 7,
        "dropoff_time": "09:00",
        "return_time": "15:00",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Malaga",
        "destination_code": "AGP",
        "flight_number": "2020",
        "return_flight_number": "2021",
        "promo_code": "TESTFREE",
        "promo_type": "free",
    },
    # FREE Parking Promo Code Test (8 days = 7-day deducted, pays 1 extra day - boundary)
    {
        "name": "FREE Promo (8-day) - pays extra day",
        "days_from_now": 32,
        "duration": 8,
        "dropoff_time": "10:00",
        "return_time": "14:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Faro",
        "destination_code": "FAO",
        "flight_number": "3030",
        "return_flight_number": "3031",
        "promo_code": "TESTFREE",
        "promo_type": "free",
    },
    # FREE Parking Promo Code Test (11 days = 7-day deducted, pays 4 extra days)
    {
        "name": "FREE Promo (11-day) - pays 4 days",
        "days_from_now": 34,
        "duration": 11,
        "dropoff_time": "07:00",
        "return_time": "17:00",
        "airline": "Virgin Atlantic",
        "airline_code": "OTHER",
        "destination": "Madrid",
        "destination_code": "OTHER",
        "flight_number": "VS200",
        "return_flight_number": "VS201",
        "promo_code": "TESTFREE",
        "promo_type": "free",
    },
    # FREE Parking Promo Code Test (14 days = 7-day deducted, pays 7 extra days)
    {
        "name": "FREE Promo (14-day) - pays 7 days",
        "days_from_now": 35,
        "duration": 14,
        "dropoff_time": "08:00",
        "return_time": "16:00",
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Palma de Mallorca",
        "destination_code": "PMI",
        "flight_number": "4040",
        "return_flight_number": "4041",
        "promo_code": "TESTFREE",
        "promo_type": "free",
    },
    # 10% OFF Promo Code - 14-day trip boundary
    {
        "name": "10% OFF Promo (14-day trip)",
        "days_from_now": 38,
        "duration": 14,
        "dropoff_time": "11:00",
        "return_time": "13:00",
        "airline": "Ryanair",
        "airline_code": "FR",
        "destination": "Alicante",
        "destination_code": "ALC",
        "flight_number": "5050",
        "return_flight_number": "5051",
        "promo_code": "TEST10OFF",
        "promo_type": "10",
    },
]


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


def create_booking(page: Page, test_case: dict, test_num: int) -> bool:
    """Create a single test booking using the booking form."""

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=test_case["days_from_now"])
    pickup_date = dropoff_date + timedelta(days=test_case["duration"])

    print(f"\n[Test {test_num}] {test_case['name']}")
    print(f"  Drop-off: {dropoff_date} at {test_case['dropoff_time']}")
    print(f"  Pickup: {pickup_date} at {test_case['return_time']}")
    print(f"  Duration: {test_case['duration']} days")

    try:
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
        time.sleep(3)

        # ============ WELCOME MODAL (shows first) ============
        print("  Handling welcome modal...")
        welcome_modal_btn = page.locator(".welcome-modal-btn")
        if welcome_modal_btn.is_visible(timeout=5000):
            print("    Closing welcome modal...")
            welcome_modal_btn.click()
            time.sleep(1)

        # ============ STEP 1: Trip Details ============
        print("  Step 1: Filling trip details...")

        # Select Drop-off Date using the date picker
        print("    Selecting drop-off date...")
        select_date_in_picker(page, dropoff_date, "dropoffDate")
        dismiss_busy_warning(page)
        time.sleep(1)

        # Select Airline
        print("    Selecting airline...")
        airline_dropdown = page.locator("#manualAirline")
        airline_dropdown.wait_for(state="visible", timeout=10000)
        if test_case["airline_code"] == "OTHER":
            # Select "Other" and fill in custom airline name
            airline_dropdown.select_option(value="Other")
            time.sleep(0.5)
            other_airline_input = page.locator("#customDepartureAirline")
            other_airline_input.wait_for(state="visible", timeout=5000)
            other_airline_input.fill(test_case["airline"])
            print(f"    Entered custom airline: {test_case['airline']}")
        else:
            airline_dropdown.select_option(value=test_case["airline_code"])
        time.sleep(1)  # Wait for destination dropdown to populate

        # Select Destination
        print("    Selecting destination...")
        destination_dropdown = page.locator("#manualDestination")
        destination_dropdown.wait_for(state="visible", timeout=10000)
        if test_case["destination_code"] == "OTHER":
            # Select "Other" and fill in custom destination name
            destination_dropdown.select_option(value="Other")
            time.sleep(0.5)
            other_destination_input = page.locator("#customDestination")
            other_destination_input.wait_for(state="visible", timeout=5000)
            other_destination_input.fill(test_case["destination"])
            print(f"    Entered custom destination: {test_case['destination']}")
        else:
            destination_dropdown.select_option(value=test_case["destination_code"])
        time.sleep(1)

        # Enter Flight Number
        print("    Entering flight number...")
        flight_number_input = page.locator("#manualFlightNumber")
        flight_number_input.wait_for(state="visible", timeout=10000)
        flight_number_input.fill(test_case["flight_number"])
        time.sleep(0.5)

        # Enter Departure Time
        print("    Entering departure time...")
        flight_time_input = page.locator("#manualFlightTime")
        flight_time_input.wait_for(state="visible", timeout=10000)
        flight_time_input.fill(test_case["dropoff_time"])
        dismiss_busy_warning(page)
        time.sleep(1)

        # Select Drop-off Time Slot - randomly select 2hr or 2.75hr slot
        print("    Selecting drop-off time slot...")
        time.sleep(2)  # Wait for slots to appear
        dismiss_busy_warning(page)
        slot_cards = page.locator(".dropoff-slot .slot-card")
        slot_count = slot_cards.count()
        if slot_count > 0:
            # Randomly select a slot (usually 2 options: 2hr and 2.75hr windows)
            random_index = random.randint(0, slot_count - 1)
            selected_slot = slot_cards.nth(random_index)
            dismiss_busy_warning(page)
            selected_slot.click()
            # Get the slot label text for logging
            try:
                slot_text = selected_slot.text_content()
                print(f"    Selected slot {random_index + 1} of {slot_count}: {slot_text[:50]}...")
            except:
                print(f"    Selected slot {random_index + 1} of {slot_count}")
            time.sleep(0.5)
        else:
            print("    No drop-off slots found!")

        # Select Return Date
        print("    Selecting return date...")
        time.sleep(1)
        # The return date picker appears after selecting dropoff slot
        return_date_picker = page.locator(".date-picker-input").nth(1)
        if return_date_picker.is_visible(timeout=3000):
            return_date_picker.click()
            time.sleep(0.5)

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
                        time.sleep(0.3)

            # Click on the day
            day_buttons = page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
            for i in range(day_buttons.count()):
                button = day_buttons.nth(i)
                if button.text_content() == str(target_day):
                    button.click()
                    break
            time.sleep(0.5)

        # Return flight details
        print("    Filling return flight details...")
        dismiss_busy_warning(page)
        time.sleep(1)

        # Select Return Airline
        return_airline_dropdown = page.locator("#manualArrivalAirline")
        if test_case["airline_code"] == "OTHER":
            return_airline_dropdown.select_option(value="Other")
            time.sleep(0.5)
            custom_return_airline = page.locator("#customArrivalAirline")
            custom_return_airline.wait_for(state="visible", timeout=5000)
            custom_return_airline.fill(test_case["airline"])
        else:
            return_airline_dropdown.select_option(value=test_case["airline_code"])
        time.sleep(0.5)

        # Select Origin (for return flight, origin is where they're coming FROM = departure destination)
        return_origin_dropdown = page.locator("#manualArrivalOrigin")
        if test_case["destination_code"] == "OTHER":
            return_origin_dropdown.select_option(value="Other")
            time.sleep(0.5)
            custom_return_origin = page.locator("#customOrigin")
            custom_return_origin.wait_for(state="visible", timeout=5000)
            custom_return_origin.fill(test_case["destination"])
        else:
            return_origin_dropdown.select_option(value=test_case["destination_code"])
        time.sleep(0.5)

        # Enter Return Flight Number
        return_flight_input = page.locator("#manualArrivalFlightNumber")
        if return_flight_input.is_visible():
            return_flight_input.fill(test_case["return_flight_number"])
        time.sleep(0.3)

        # Enter Arrival Time
        arrival_time_input = page.locator("#manualArrivalFlightTime")
        if arrival_time_input.is_visible():
            arrival_time_input.fill(test_case["return_time"])
        dismiss_busy_warning(page)
        time.sleep(1)

        # ============ STEP 2: Package Selection ============
        print("  Proceeding to Step 2 (Package Selection)...")

        # Click Continue to Package Selection button
        dismiss_busy_warning(page)
        package_btn = page.locator("button:has-text('Continue to Package Selection')")
        if package_btn.is_visible(timeout=5000):
            package_btn.click()
            time.sleep(1)

        # Added 2026-05-13: a "Please double-check your times" confirmation
        # modal now intercepts the Step 1 → Step 2 transition. Click through
        # "Yes, times are correct" to proceed. The modal may not appear in
        # every state (e.g. legacy flows that bypass it), so this is best-effort.
        try:
            confirm_btn = page.locator("button:has-text('Yes, times are correct')")
            if confirm_btn.is_visible(timeout=2000):
                print("    Confirming times modal...")
                confirm_btn.click()
        except Exception:
            pass
        time.sleep(2)

        # Step 2 shows the pricing and package info
        # Wait for pricing to load
        time.sleep(2)

        # Click Continue to Your Details button
        print("  Proceeding to Step 3 (Your Details)...")
        continue_details_btn = page.locator("button:has-text('Continue to Your Details')")
        if continue_details_btn.is_visible(timeout=5000):
            continue_details_btn.click()
            time.sleep(3)

        # ============ STEP 3: Your Details (Customer + Billing + Vehicle) ============
        print("  Step 3: Filling customer details...")

        # Fill contact information
        page.locator("#firstName").fill(CUSTOMER["first_name"])
        time.sleep(0.2)
        page.locator("#lastName").fill(CUSTOMER["last_name"])
        time.sleep(0.2)
        page.locator("#email").fill(CUSTOMER["email"])
        time.sleep(0.2)

        # Phone - using the PhoneInput component
        phone_input = page.locator(".phone-input input[type='tel']")
        phone_input.click()
        time.sleep(0.2)
        phone_input.fill("+44" + CUSTOMER["phone"])
        time.sleep(0.3)

        # Fill billing address - enter postcode and use manual entry
        page.locator("#billingPostcode").fill(CUSTOMER["postcode"])
        time.sleep(0.3)

        # Click Find Address button
        page.locator("button:has-text('Find Address')").click()
        time.sleep(2)

        # If address select appears, select first address or use manual entry
        try:
            if page.locator("#addressSelect").is_visible(timeout=3000):
                page.locator("#addressSelect").select_option(index=1)
                time.sleep(0.5)
            else:
                page.locator("text=Enter address manually").click()
                time.sleep(0.3)
        except:
            try:
                page.locator("text=Enter address manually").click()
                time.sleep(0.3)
            except:
                pass

        # Fill address fields if visible/empty
        if not page.locator("#billingAddress1").input_value():
            page.locator("#billingAddress1").fill(CUSTOMER["address1"])
        time.sleep(0.2)

        if not page.locator("#billingCity").input_value():
            page.locator("#billingCity").fill(CUSTOMER["city"])
        time.sleep(0.2)

        if not page.locator("#billingCounty").input_value():
            page.locator("#billingCounty").fill(CUSTOMER["county"])
        time.sleep(0.2)

        # Vehicle Information
        print("  Filling vehicle details...")
        page.locator("#registration").fill(VEHICLE["registration"])
        time.sleep(0.3)

        # Click DVLA Lookup button
        page.locator("button.validate-btn").click()
        time.sleep(2)

        # Check if DVLA verified the vehicle or if we need to select manually
        make_readonly = page.locator("#make.readonly-input")
        make_select = page.locator("select#make")

        if make_readonly.is_visible(timeout=2000):
            print("    DVLA verified make:", make_readonly.input_value())
        elif make_select.is_visible(timeout=2000):
            try:
                make_select.select_option(label=VEHICLE["make"])
                time.sleep(0.5)
            except:
                make_select.select_option(value=VEHICLE["make"])
                time.sleep(0.5)

        # Fill colour if needed
        colour_readonly = page.locator("#colour.readonly-input")
        colour_input = page.locator("#colour:not(.readonly-input)")

        if colour_readonly.is_visible(timeout=1000):
            print("    DVLA verified colour:", colour_readonly.input_value())
        elif colour_input.is_visible(timeout=1000):
            colour_input.fill(VEHICLE["colour"])
            time.sleep(0.3)

        # Select model from dropdown
        print("    Selecting model...")
        time.sleep(1)
        model_select = page.locator("select#model")
        if model_select.is_visible(timeout=3000):
            try:
                model_select.select_option(label=VEHICLE["model"])
                print(f"    Selected model: {VEHICLE['model']}")
            except:
                print(f"    Model {VEHICLE['model']} not found, selecting Other...")
                model_select.select_option(value="Other")
                time.sleep(0.3)
                page.locator("#customModel").fill(VEHICLE["model"])
            time.sleep(0.5)
        else:
            print("    Model dropdown not visible yet")

        # Click Continue to Payment
        print("  Proceeding to Step 4 (Payment)...")
        continue_payment_btn = page.locator("button:has-text('Continue to Payment')")
        if continue_payment_btn.is_visible(timeout=5000):
            continue_payment_btn.click()
            time.sleep(3)

        # ============ STEP 4: Payment ============
        print("  Step 4: Payment...")

        # Apply promo code if this test case has one
        promo_code = test_case.get("promo_code")
        promo_type = test_case.get("promo_type", "10")
        if promo_code:
            print(f"    Applying promo code: {promo_code}")
            time.sleep(1)

            # Find and fill promo code input
            promo_input = page.locator(".promo-code-input input, input[placeholder*='promo' i]")
            if promo_input.is_visible(timeout=5000):
                promo_input.fill(promo_code)
                time.sleep(0.5)

                # Click Apply button
                apply_btn = page.locator(".promo-apply-btn, button:has-text('Apply')")
                if apply_btn.is_visible(timeout=3000):
                    apply_btn.click()
                    time.sleep(2)

                    # Check for success - look for success indicators (use .first to avoid strict mode error)
                    time.sleep(1)
                    promo_success = page.locator(".promo-success, .promo-code-applied, .discount-applied").first

                    if promo_success.is_visible(timeout=3000):
                        print(f"    Promo code {promo_code} applied successfully!")
                    else:
                        print(f"    Warning: Could not confirm promo code applied")
            else:
                print("    Warning: Promo code input not found")

        # Accept terms checkbox - click the checkbox input directly, not the label links
        print("    Accepting terms...")
        time.sleep(1)

        terms_input = page.locator("input[name='terms']")

        try:
            # Check if already checked
            if terms_input.is_checked():
                print("    Terms already accepted")
            else:
                # Use JavaScript to check the checkbox - most reliable method
                page.evaluate("document.querySelector('input[name=\"terms\"]').click()")
                print("    Clicked terms checkbox via JavaScript")
                time.sleep(0.5)

                # Verify it's checked
                if terms_input.is_checked():
                    print("    Terms checkbox confirmed checked")
                else:
                    # Fallback: force set checked state
                    page.evaluate("document.querySelector('input[name=\"terms\"]').checked = true")
                    page.evaluate("document.querySelector('input[name=\"terms\"]').dispatchEvent(new Event('change', { bubbles: true }))")
                    print("    Set terms via JavaScript fallback")
        except Exception as e:
            print(f"    Warning: Could not click terms checkbox: {e}")
        time.sleep(1)

        # Free-booking short-circuit: 100% promo bookings render the green
        # "Complete Free Booking" button instead of the Stripe card form, so
        # the entire iframe-polling + card-fill block below is wasted work
        # (~15s) for those tests. Detect first; if present, skip Stripe.
        print("    Waiting for payment surface...")
        time.sleep(3)
        free_booking_btn = page.locator("button:has-text('Complete Free Booking')")
        try:
            is_free = free_booking_btn.is_visible(timeout=2000)
        except Exception:
            is_free = False

        if is_free:
            print("    Free booking detected — skipping Stripe card flow")
        else:
            time.sleep(2)
            # The StripePaymentElement uses iframes for card input.
            print("    Filling card details...")
            try:
                # Find the Stripe payment iframe. It can take 2-5s after the
                # Continue-to-Payment click for Stripe Elements to attach the
                # iframe, so poll up to ~15s. Detect by the standard autocomplete
                # attribute the card number input always carries.
                payment_frame = None
                CARD_NUMBER_SEL = "input[autocomplete='cc-number']"
                for _ in range(30):
                    stripe_frames = [
                        f for f in page.frames if "stripe" in (f.url or "").lower()
                    ] or page.frames
                    for frame in stripe_frames:
                        try:
                            if frame.locator(CARD_NUMBER_SEL).count() > 0:
                                payment_frame = frame
                                break
                        except Exception:
                            continue
                    if payment_frame:
                        print(f"    Found Stripe payment frame: {payment_frame.url[:60]}...")
                        break
                    time.sleep(0.5)

                if payment_frame:
                    # Use standard autocomplete attributes — survive Stripe internal
                    # markup changes that the old `#payment-numberInput` IDs do not.
                    card_sel = "input[autocomplete='cc-number']"
                    exp_sel = "input[autocomplete='cc-exp']"
                    cvc_sel = "input[autocomplete='cc-csc']"

                    card_input = payment_frame.locator(card_sel)
                    card_input.wait_for(state="visible", timeout=10000)
                    card_input.click()
                    time.sleep(0.2)
                    card_input.press_sequentially(STRIPE_TEST_CARD["number"], delay=40)
                    print("    Card number filled")
                    time.sleep(0.3)

                    expiry_input = payment_frame.locator(exp_sel)
                    expiry_input.click()
                    time.sleep(0.2)
                    expiry_input.press_sequentially(STRIPE_TEST_CARD["expiry"], delay=40)
                    print("    Expiry filled")
                    time.sleep(0.3)

                    cvc_input = payment_frame.locator(cvc_sel)
                    cvc_input.click()
                    time.sleep(0.2)
                    cvc_input.press_sequentially(STRIPE_TEST_CARD["cvc"], delay=40)
                    print("    CVC filled")
                    time.sleep(0.5)
                else:
                    print("    Could not find Stripe payment frame after polling")
                    page.screenshot(path=f"no_stripe_frame_{test_num}.png")

            except Exception as stripe_err:
                print(f"    Stripe fill failed: {stripe_err}")

        # Wait for the pay button to become enabled (elementComplete=true) — up
        # to ~6s. fill() used to race this with a flat sleep(2); polling here
        # makes the wait deterministic.
        pay_btn_wait = page.locator(".stripe-pay-btn")
        for _ in range(30):
            try:
                if pay_btn_wait.is_visible(timeout=200) and not pay_btn_wait.is_disabled():
                    break
            except Exception:
                pass
            time.sleep(0.2)

        # Submit Payment - handle both paid and free bookings
        print("  Submitting payment...")

        # Check for FREE booking button first (£0 total)
        free_booking_btn = page.locator("button:has-text('Complete Free Booking')")
        pay_btn = page.locator(".stripe-pay-btn, button:has-text('Pay ')")

        if free_booking_btn.is_visible(timeout=3000):
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
            test_cases_to_run = [tc for tc in TEST_CASES if tc.get("promo_code")]
            print(f"Running PROMO_ONLY: {len(test_cases_to_run)} promo code tests")
        elif TEST_FILTER:
            test_cases_to_run = [tc for tc in TEST_CASES if TEST_FILTER.lower() in tc["name"].lower()]
            print(f"Running tests matching '{TEST_FILTER}': {len(test_cases_to_run)} tests")
        else:
            test_cases_to_run = TEST_CASES

        for i, test_case in enumerate(test_cases_to_run, 1):
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
