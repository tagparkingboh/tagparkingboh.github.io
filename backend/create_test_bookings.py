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

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
SINGLE_TEST = os.environ.get("SINGLE_TEST", "false").lower() == "true"  # Run only first test

# Staging URL
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

# Test customer details
CUSTOMER = {
    "first_name": "Mark",
    "last_name": "Testing",
    "email": "qa.orca.contact@gmail.com",
    "phone": "7977321321",
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
        "airline": "easyJet",
        "airline_code": "U2",
        "destination": "Dublin",
        "destination_code": "DUB",
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
        # Navigate to booking page
        page.goto(STAGING_URL, wait_until="networkidle")
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
        time.sleep(1)

        # Select Airline
        print("    Selecting airline...")
        page.locator("#manualAirline").select_option(value=test_case["airline_code"])
        time.sleep(0.5)

        # Select Destination
        print("    Selecting destination...")
        page.locator("#manualDestination").select_option(value=test_case["destination_code"])
        time.sleep(0.5)

        # Enter Flight Number
        print("    Entering flight number...")
        page.locator("#manualFlightNumber").fill(test_case["flight_number"])
        time.sleep(0.3)

        # Enter Departure Time
        print("    Entering departure time...")
        page.locator("#manualFlightTime").fill(test_case["dropoff_time"])
        time.sleep(1)

        # Select Drop-off Time Slot - randomly select 2hr or 2.75hr slot
        print("    Selecting drop-off time slot...")
        time.sleep(2)  # Wait for slots to appear
        slot_cards = page.locator(".dropoff-slot .slot-card")
        slot_count = slot_cards.count()
        if slot_count > 0:
            # Randomly select a slot (usually 2 options: 2hr and 2.75hr windows)
            random_index = random.randint(0, slot_count - 1)
            selected_slot = slot_cards.nth(random_index)
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
        time.sleep(1)

        # Select Return Airline
        page.locator("#manualArrivalAirline").select_option(value=test_case["airline_code"])
        time.sleep(0.5)

        # Select Origin
        page.locator("#manualArrivalOrigin").select_option(value=test_case["destination_code"])
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
        time.sleep(1)

        # ============ STEP 2: Package Selection ============
        print("  Proceeding to Step 2 (Package Selection)...")

        # Click Continue to Package Selection button
        package_btn = page.locator("button:has-text('Continue to Package Selection')")
        if package_btn.is_visible(timeout=5000):
            package_btn.click()
            time.sleep(3)

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

        # Accept terms checkbox
        print("    Accepting terms...")
        terms_checkbox = page.locator("input[name='terms']")
        if terms_checkbox.is_visible(timeout=3000):
            if not terms_checkbox.is_checked():
                terms_checkbox.click()
            time.sleep(1)

        # Wait for Stripe PaymentElement to load
        print("    Waiting for Stripe payment form...")
        time.sleep(3)

        # Dismiss Stripe Link popup if it appears (for emails registered with Link)
        # The Link modal needs to be closed so we can use the card form
        time.sleep(2)

        try:
            link_closed = False

            # First try pressing Escape multiple times - this often dismisses Link
            for _ in range(3):
                page.keyboard.press("Escape")
                time.sleep(0.3)

            # Try clicking outside the modal area (top-left corner of page)
            try:
                page.mouse.click(10, 10)
                time.sleep(0.5)
            except:
                pass

            # Look for close/back buttons in all frames
            for frame in page.frames:
                try:
                    # Various selectors for Link close/dismiss buttons
                    close_selectors = [
                        "[data-testid='link-close-button']",
                        "button[aria-label='Close']",
                        "button[aria-label='Back']",
                        ".p-LinkAutofillPrompt [role='button']",
                        "button:has(svg path[d*='M1.2'])",  # X icon paths
                        "[class*='CloseButton']",
                        "[class*='close']",
                    ]
                    for selector in close_selectors:
                        close_btn = frame.locator(selector).first
                        if close_btn.is_visible(timeout=300):
                            print(f"    Found Link close button: {selector}")
                            close_btn.click()
                            link_closed = True
                            time.sleep(0.5)
                            break
                    if link_closed:
                        break
                except:
                    continue

            if not link_closed:
                print("    Link modal close button not found, trying Escape again...")
                for _ in range(3):
                    page.keyboard.press("Escape")
                    time.sleep(0.3)

        except Exception as e:
            print(f"    Could not close Link modal: {e}")

        time.sleep(1)

        # The StripePaymentElement uses iframes for card input
        # The inputs have specific IDs: payment-numberInput, payment-expiryInput, payment-cvcInput
        print("    Filling card details...")

        try:
            # Find the Stripe iframe containing the payment form
            # It's usually the first __privateStripeFrame or has specific naming
            stripe_frames = page.frames
            payment_frame = None

            for frame in stripe_frames:
                # Check if this frame has the card number input
                try:
                    card_input = frame.locator("#payment-numberInput")
                    if card_input.count() > 0:
                        payment_frame = frame
                        print("    Found Stripe payment frame")
                        break
                except:
                    continue

            if payment_frame:
                # Fill card number
                card_input = payment_frame.locator("#payment-numberInput")
                card_input.click()
                time.sleep(0.2)
                card_input.fill(STRIPE_TEST_CARD["number"])
                print("    Card number filled")
                time.sleep(0.3)

                # Fill expiry
                expiry_input = payment_frame.locator("#payment-expiryInput")
                expiry_input.click()
                time.sleep(0.2)
                expiry_input.fill(STRIPE_TEST_CARD["expiry"])
                print("    Expiry filled")
                time.sleep(0.3)

                # Fill CVC
                cvc_input = payment_frame.locator("#payment-cvcInput")
                cvc_input.click()
                time.sleep(0.2)
                cvc_input.fill(STRIPE_TEST_CARD["cvc"])
                print("    CVC filled")
                time.sleep(0.5)
            else:
                print("    Could not find Stripe payment frame, trying frame_locator...")
                # Try using frame_locator approach
                for iframe in page.locator("iframe").all():
                    try:
                        frame = page.frame_locator(f"iframe >> nth={page.locator('iframe').all().index(iframe)}")
                        card_input = frame.locator("#payment-numberInput")
                        if card_input.is_visible(timeout=500):
                            card_input.fill(STRIPE_TEST_CARD["number"])
                            frame.locator("#payment-expiryInput").fill(STRIPE_TEST_CARD["expiry"])
                            frame.locator("#payment-cvcInput").fill(STRIPE_TEST_CARD["cvc"])
                            print("    Card details filled via frame_locator")
                            break
                    except:
                        continue

        except Exception as stripe_err:
            print(f"    Stripe fill failed: {stripe_err}")

        time.sleep(2)

        # Submit Payment using the stripe-pay-btn
        print("  Submitting payment...")
        pay_btn = page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=5000):
            # Check if button is enabled
            if not pay_btn.is_disabled():
                pay_btn.click()
            else:
                print("    Pay button is disabled - card details may not have filled correctly")
                page.screenshot(path=f"payment_disabled_{test_num}.png")

        # Wait for confirmation
        print("  Waiting for booking confirmation...")
        time.sleep(10)

        # Check for success - look for "Payment Successful!" or booking reference
        success = False
        booking_ref = None

        # Check for Payment Successful text
        if page.locator("text=Payment Successful").is_visible(timeout=20000):
            success = True
            # Try to extract the booking reference (format: TAG-XXXXXXX)
            try:
                # Look for text containing TAG- pattern
                ref_element = page.locator("text=/TAG-[A-Z0-9]+/")
                if ref_element.is_visible(timeout=3000):
                    booking_ref = ref_element.text_content()
            except:
                pass
        elif page.locator("text=Booking Confirmed").is_visible(timeout=5000):
            success = True
        elif page.locator(".booking-reference").is_visible(timeout=5000):
            booking_ref = page.locator(".booking-reference").text_content()
            success = True
        elif page.locator("text=Thank you").is_visible(timeout=5000):
            success = True

        if success:
            if booking_ref:
                print(f"  ✓ Booking created! Reference: {booking_ref}")
            else:
                print(f"  ✓ Booking created successfully!")
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
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=slow_mo)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        results = {"success": [], "failed": []}

        # Optionally run only the first test case for smoke testing
        test_cases_to_run = TEST_CASES[:1] if SINGLE_TEST else TEST_CASES

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


if __name__ == "__main__":
    main()
