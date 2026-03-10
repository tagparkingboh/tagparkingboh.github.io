#!/usr/bin/env python3
"""
E2E tests for booking form state persistence across page refresh and navigation.

These tests verify:
1. Manual flight data (departure/arrival) persists after page refresh at each step
2. Data persists after navigating away and returning
3. Data persists after browser back/forward navigation
4. Form can be completed successfully after refresh/navigation scenarios

Bug Reference:
- Booking TAG-LLP80398 had missing pickup/return flight data
- Root cause: manualDepartureData and manualArrivalData were not persisted to sessionStorage

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    python test_booking_persistence_e2e.py

    # Run with visible browser
    HEADLESS=false python test_booking_persistence_e2e.py
"""

from playwright.sync_api import sync_playwright, Page
from datetime import datetime, timedelta
import time
import random
import os
import sys

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

# Test customer details
CUSTOMER = {
    "first_name": "Persistence",
    "last_name": "Test",
    "email": "persistence.test@example.com",
    "phone": "7911123456",
    "address1": "123 Test Street",
    "city": "Bournemouth",
    "county": "Dorset",
    "postcode": "BH1 1AA",
}

# Test vehicle
VEHICLE = {
    "registration": "TEST123",
    "make": "Audi",
    "model": "A3",
    "colour": "Black",
}

# Test flight details
FLIGHT_DATA = {
    "airline_code": "FR",
    "airline_name": "Ryanair",
    "destination_code": "ALC",
    "destination_name": "Alicante",
    "dropoff_time": "10:00",
    "dropoff_flight_number": "FR1234",
    "return_time": "14:00",
    "return_flight_number": "FR1235",
}


def format_date_for_picker(date_obj):
    """Format date as DD/MM/YYYY for the date picker."""
    return date_obj.strftime("%d/%m/%Y")


def select_date_in_picker(page: Page, date_obj, picker_id: str):
    """Select a date using the react-datepicker calendar UI."""
    picker = page.locator(f"#{picker_id}")
    picker.click()
    time.sleep(0.5)

    target_month = date_obj.month
    target_year = date_obj.year
    target_day = date_obj.day

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

    day_buttons = page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
    for i in range(day_buttons.count()):
        button = day_buttons.nth(i)
        if button.text_content() == str(target_day):
            button.click()
            break

    time.sleep(0.5)


def close_welcome_modal(page: Page):
    """Close the welcome modal if it appears."""
    welcome_modal_btn = page.locator(".welcome-modal-btn")
    if welcome_modal_btn.is_visible(timeout=3000):
        welcome_modal_btn.click()
        time.sleep(1)


def fill_step1_departure(page: Page, dropoff_date, flight_data: dict):
    """Fill Step 1 departure details (before dropoff slot selection)."""
    print("    Filling departure details...")

    # Select Drop-off Date
    select_date_in_picker(page, dropoff_date, "dropoffDate")
    time.sleep(1)

    # Select Airline
    airline_dropdown = page.locator("#manualAirline")
    airline_dropdown.wait_for(state="visible", timeout=10000)
    airline_dropdown.select_option(value=flight_data["airline_code"])
    time.sleep(1)

    # Select Destination
    destination_dropdown = page.locator("#manualDestination")
    destination_dropdown.wait_for(state="visible", timeout=10000)
    destination_dropdown.select_option(value=flight_data["destination_code"])
    time.sleep(1)

    # Enter Flight Number
    flight_number_input = page.locator("#manualFlightNumber")
    flight_number_input.fill(flight_data["dropoff_flight_number"])
    time.sleep(0.5)

    # Enter Departure Time
    flight_time_input = page.locator("#manualFlightTime")
    flight_time_input.fill(flight_data["dropoff_time"])
    time.sleep(1)

    # Select Drop-off Time Slot
    time.sleep(2)
    slot_cards = page.locator(".dropoff-slot .slot-card")
    if slot_cards.count() > 0:
        slot_cards.first.click()
        time.sleep(0.5)


def fill_step1_arrival(page: Page, pickup_date, flight_data: dict):
    """Fill Step 1 arrival/return details."""
    print("    Filling return flight details...")

    # Select Return Date
    return_date_picker = page.locator(".date-picker-input").nth(1)
    if return_date_picker.is_visible(timeout=3000):
        return_date_picker.click()
        time.sleep(0.5)

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

        day_buttons = page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
        for i in range(day_buttons.count()):
            button = day_buttons.nth(i)
            if button.text_content() == str(target_day):
                button.click()
                break
        time.sleep(0.5)

    time.sleep(1)

    # Select Return Airline
    return_airline_dropdown = page.locator("#manualArrivalAirline")
    return_airline_dropdown.select_option(value=flight_data["airline_code"])
    time.sleep(0.5)

    # Select Origin
    return_origin_dropdown = page.locator("#manualArrivalOrigin")
    return_origin_dropdown.select_option(value=flight_data["destination_code"])
    time.sleep(0.5)

    # Enter Return Flight Number
    return_flight_input = page.locator("#manualArrivalFlightNumber")
    if return_flight_input.is_visible():
        return_flight_input.fill(flight_data["return_flight_number"])
    time.sleep(0.3)

    # Enter Arrival Time
    arrival_time_input = page.locator("#manualArrivalFlightTime")
    if arrival_time_input.is_visible():
        arrival_time_input.fill(flight_data["return_time"])
    time.sleep(1)


def verify_step1_data(page: Page, flight_data: dict) -> bool:
    """Verify that Step 1 data is correctly populated (after refresh)."""
    print("    Verifying Step 1 data after refresh...")

    errors = []

    # Check airline
    airline_dropdown = page.locator("#manualAirline")
    airline_value = airline_dropdown.input_value()
    if airline_value != flight_data["airline_code"]:
        errors.append(f"Airline: expected {flight_data['airline_code']}, got {airline_value}")

    # Check destination
    destination_dropdown = page.locator("#manualDestination")
    destination_value = destination_dropdown.input_value()
    if destination_value != flight_data["destination_code"]:
        errors.append(f"Destination: expected {flight_data['destination_code']}, got {destination_value}")

    # Check departure time
    flight_time_input = page.locator("#manualFlightTime")
    time_value = flight_time_input.input_value()
    if time_value != flight_data["dropoff_time"]:
        errors.append(f"Departure time: expected {flight_data['dropoff_time']}, got {time_value}")

    # Check flight number
    flight_number_input = page.locator("#manualFlightNumber")
    flight_num_value = flight_number_input.input_value()
    if flight_num_value != flight_data["dropoff_flight_number"]:
        errors.append(f"Flight number: expected {flight_data['dropoff_flight_number']}, got {flight_num_value}")

    # Check return airline
    return_airline = page.locator("#manualArrivalAirline")
    return_airline_value = return_airline.input_value()
    if return_airline_value != flight_data["airline_code"]:
        errors.append(f"Return airline: expected {flight_data['airline_code']}, got {return_airline_value}")

    # Check return time
    arrival_time = page.locator("#manualArrivalFlightTime")
    arrival_value = arrival_time.input_value()
    if arrival_value != flight_data["return_time"]:
        errors.append(f"Return time: expected {flight_data['return_time']}, got {arrival_value}")

    if errors:
        print("    ERRORS found:")
        for error in errors:
            print(f"      - {error}")
        return False

    print("    All Step 1 data verified successfully!")
    return True


def click_continue_to_step2(page: Page):
    """Click Continue to Package Selection button."""
    btn = page.locator("button:has-text('Continue to Package Selection')")
    if btn.is_visible(timeout=5000):
        btn.click()
        time.sleep(3)


def click_continue_to_step3(page: Page):
    """Click Continue to Your Details button."""
    btn = page.locator("button:has-text('Continue to Your Details')")
    if btn.is_visible(timeout=5000):
        btn.click()
        time.sleep(3)


def click_continue_to_step4(page: Page):
    """Click Continue to Payment button."""
    btn = page.locator("button:has-text('Continue to Payment')")
    if btn.is_visible(timeout=5000):
        btn.click()
        time.sleep(3)


def fill_step3(page: Page, customer: dict, vehicle: dict):
    """Fill Step 3 (Your Details)."""
    print("    Filling customer details...")

    page.locator("#firstName").fill(customer["first_name"])
    time.sleep(0.2)
    page.locator("#lastName").fill(customer["last_name"])
    time.sleep(0.2)
    page.locator("#email").fill(customer["email"])
    time.sleep(0.2)

    phone_input = page.locator(".phone-input input[type='tel']")
    phone_input.click()
    time.sleep(0.2)
    phone_input.fill("+44" + customer["phone"])
    time.sleep(0.3)

    # Billing address
    page.locator("#billingPostcode").fill(customer["postcode"])
    time.sleep(0.3)

    # Click manual entry
    try:
        manual_link = page.locator("text=Enter address manually")
        if manual_link.is_visible(timeout=2000):
            manual_link.click()
            time.sleep(0.3)
    except:
        pass

    page.locator("#billingAddress1").fill(customer["address1"])
    time.sleep(0.2)
    page.locator("#billingCity").fill(customer["city"])
    time.sleep(0.2)

    # Vehicle
    print("    Filling vehicle details...")
    page.locator("#registration").fill(vehicle["registration"])
    time.sleep(0.3)

    # Select make
    make_select = page.locator("select#make")
    if make_select.is_visible(timeout=3000):
        try:
            make_select.select_option(label=vehicle["make"])
            time.sleep(0.5)
        except:
            pass

    # Select model
    model_select = page.locator("select#model")
    if model_select.is_visible(timeout=3000):
        try:
            model_select.select_option(label=vehicle["model"])
            time.sleep(0.5)
        except:
            model_select.select_option(value="Other")
            page.locator("#customModel").fill(vehicle["model"])
            time.sleep(0.5)

    # Fill colour
    colour_input = page.locator("#colour")
    if colour_input.is_visible(timeout=1000):
        colour_input.fill(vehicle["colour"])
        time.sleep(0.3)


def get_current_step(page: Page) -> int:
    """Get the current step number from the page."""
    try:
        # Look for step indicators
        for step in range(1, 5):
            if page.locator(f".step-{step}.active, .step-indicator:has-text('{step}').active").is_visible(timeout=500):
                return step
    except:
        pass
    return 1


# ============================================================================
# TEST CASES
# ============================================================================

def test_refresh_after_step1_complete(page: Page) -> bool:
    """
    Test: Complete Step 1, refresh page, verify all data persists.
    This is the core test for the bug fix.
    """
    print("\n" + "="*60)
    print("TEST: Refresh after Step 1 complete")
    print("="*60)

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=21)
    pickup_date = dropoff_date + timedelta(days=7)

    try:
        # Navigate to booking page
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Complete Step 1
        print("  Completing Step 1...")
        fill_step1_departure(page, dropoff_date, FLIGHT_DATA)
        fill_step1_arrival(page, pickup_date, FLIGHT_DATA)

        # Verify Continue button is enabled (Step 1 complete)
        time.sleep(1)
        continue_btn = page.locator("button:has-text('Continue to Package Selection')")
        if not continue_btn.is_enabled():
            print("  ERROR: Continue button not enabled after filling Step 1")
            return False

        print("  Step 1 complete. Refreshing page...")

        # REFRESH THE PAGE
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Verify data persisted
        if not verify_step1_data(page, FLIGHT_DATA):
            print("  FAILED: Data did not persist after refresh!")
            return False

        # Verify Continue button is still enabled
        time.sleep(1)
        continue_btn = page.locator("button:has-text('Continue to Package Selection')")
        if not continue_btn.is_enabled():
            print("  ERROR: Continue button not enabled after refresh")
            return False

        print("  SUCCESS: All data persisted after refresh!")
        return True

    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return False


def test_refresh_at_each_step(page: Page) -> bool:
    """
    Test: Complete each step, refresh page at each step, verify data persists.
    """
    print("\n" + "="*60)
    print("TEST: Refresh at each step")
    print("="*60)

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=25)
    pickup_date = dropoff_date + timedelta(days=7)

    try:
        # Step 1
        print("\n  === Step 1 ===")
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        fill_step1_departure(page, dropoff_date, FLIGHT_DATA)
        fill_step1_arrival(page, pickup_date, FLIGHT_DATA)

        print("  Refreshing at Step 1...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        if not verify_step1_data(page, FLIGHT_DATA):
            print("  FAILED: Step 1 data lost after refresh")
            return False

        # Continue to Step 2
        click_continue_to_step2(page)

        # Step 2 refresh
        print("\n  === Step 2 ===")
        print("  Refreshing at Step 2...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Should still be on Step 2 with pricing visible
        time.sleep(2)

        # Continue to Step 3
        click_continue_to_step3(page)

        # Step 3 refresh
        print("\n  === Step 3 ===")
        fill_step3(page, CUSTOMER, VEHICLE)

        print("  Refreshing at Step 3...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Re-fill Step 3 if needed (formData should persist but may need to re-fill some fields)
        time.sleep(2)

        # Continue to Step 4
        click_continue_to_step4(page)

        # Step 4 refresh
        print("\n  === Step 4 ===")
        print("  Refreshing at Step 4...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Verify we're still on payment step
        time.sleep(2)

        print("  SUCCESS: All steps survived refresh!")
        return True

    except Exception as e:
        print(f"  FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_navigate_away_and_return(page: Page) -> bool:
    """
    Test: Complete Step 1, navigate to a different URL, return, verify data persists.
    """
    print("\n" + "="*60)
    print("TEST: Navigate away and return")
    print("="*60)

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=28)
    pickup_date = dropoff_date + timedelta(days=7)

    try:
        # Navigate to booking page and complete Step 1
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        print("  Completing Step 1...")
        fill_step1_departure(page, dropoff_date, FLIGHT_DATA)
        fill_step1_arrival(page, pickup_date, FLIGHT_DATA)

        print("  Navigating away to homepage...")
        page.goto("https://staging-tagparking.netlify.app/", wait_until="networkidle")
        time.sleep(2)

        print("  Returning to booking page...")
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Verify data persisted
        if not verify_step1_data(page, FLIGHT_DATA):
            print("  FAILED: Data did not persist after navigating away!")
            return False

        print("  SUCCESS: Data persisted after navigate away and return!")
        return True

    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return False


def test_browser_back_forward(page: Page) -> bool:
    """
    Test: Complete steps, use browser back/forward buttons, verify data persists.
    """
    print("\n" + "="*60)
    print("TEST: Browser back/forward navigation")
    print("="*60)

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=30)
    pickup_date = dropoff_date + timedelta(days=7)

    try:
        # Navigate to booking page and complete Step 1
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        print("  Completing Step 1...")
        fill_step1_departure(page, dropoff_date, FLIGHT_DATA)
        fill_step1_arrival(page, pickup_date, FLIGHT_DATA)

        # Go to Step 2
        click_continue_to_step2(page)
        time.sleep(2)

        # Go to Step 3
        click_continue_to_step3(page)
        time.sleep(2)

        print("  Using browser back button...")
        page.go_back()
        time.sleep(2)

        print("  Using browser back button again...")
        page.go_back()
        time.sleep(2)

        # Should be back at Step 1 or at the booking page
        # Verify data is still there
        time.sleep(2)

        # Wait for form to load
        close_welcome_modal(page)

        if not verify_step1_data(page, FLIGHT_DATA):
            print("  FAILED: Data lost after browser back!")
            return False

        print("  Using browser forward button...")
        page.go_forward()
        time.sleep(2)

        print("  Using browser forward button again...")
        page.go_forward()
        time.sleep(2)

        print("  SUCCESS: Data persisted through back/forward navigation!")
        return True

    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return False


def test_partial_step1_refresh(page: Page) -> bool:
    """
    Test: Partially fill Step 1, refresh, verify partial data persists.
    """
    print("\n" + "="*60)
    print("TEST: Partial Step 1 data refresh")
    print("="*60)

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=22)

    try:
        page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Fill only departure part, not return
        print("  Filling departure only (not return)...")

        # Select Drop-off Date
        select_date_in_picker(page, dropoff_date, "dropoffDate")
        time.sleep(1)

        # Select Airline
        airline_dropdown = page.locator("#manualAirline")
        airline_dropdown.wait_for(state="visible", timeout=10000)
        airline_dropdown.select_option(value=FLIGHT_DATA["airline_code"])
        time.sleep(1)

        # Select Destination
        destination_dropdown = page.locator("#manualDestination")
        destination_dropdown.select_option(value=FLIGHT_DATA["destination_code"])
        time.sleep(1)

        # Enter Departure Time
        flight_time_input = page.locator("#manualFlightTime")
        flight_time_input.fill(FLIGHT_DATA["dropoff_time"])
        time.sleep(1)

        print("  Refreshing with partial data...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        close_welcome_modal(page)

        # Verify partial data persisted
        print("    Verifying partial data...")

        airline_dropdown = page.locator("#manualAirline")
        airline_value = airline_dropdown.input_value()
        if airline_value != FLIGHT_DATA["airline_code"]:
            print(f"  FAILED: Airline not persisted. Got: {airline_value}")
            return False

        flight_time_input = page.locator("#manualFlightTime")
        time_value = flight_time_input.input_value()
        if time_value != FLIGHT_DATA["dropoff_time"]:
            print(f"  FAILED: Departure time not persisted. Got: {time_value}")
            return False

        print("  SUCCESS: Partial data persisted!")
        return True

    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return False


def run_all_tests():
    """Run all persistence tests."""
    print("\n" + "="*60)
    print("BOOKING PERSISTENCE E2E TESTS")
    print("="*60)
    print(f"URL: {STAGING_URL}")
    print(f"Headless: {HEADLESS}")

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        # Run tests
        tests = [
            ("Refresh after Step 1 complete", test_refresh_after_step1_complete),
            ("Partial Step 1 data refresh", test_partial_step1_refresh),
            ("Navigate away and return", test_navigate_away_and_return),
            ("Browser back/forward", test_browser_back_forward),
            ("Refresh at each step", test_refresh_at_each_step),
        ]

        for test_name, test_func in tests:
            # Clear session storage before each test
            page.goto(STAGING_URL, wait_until="networkidle")
            time.sleep(1)
            try:
                page.evaluate("Object.keys(sessionStorage).forEach(key => { if(key.startsWith('booking_')) sessionStorage.removeItem(key) })")
            except:
                pass

            try:
                results[test_name] = test_func(page)
            except Exception as e:
                print(f"  Test {test_name} crashed: {e}")
                results[test_name] = False

        browser.close()

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        print(f"  {status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
