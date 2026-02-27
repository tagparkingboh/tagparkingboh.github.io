#!/usr/bin/env python3
"""
Negative test cases for TAG Parking booking form.
Tests validation errors, missing fields, and edge cases.

Prerequisites:
    pip install playwright
    playwright install chromium

Usage:
    python test_negative_bookings.py
"""

from playwright.sync_api import sync_playwright, Page, expect
from datetime import datetime, timedelta
import time
import subprocess
import sys
import json
from typing import List, Tuple
from multiprocessing import Pool, cpu_count

# Staging URL
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

# Stripe test cards for decline scenarios
STRIPE_DECLINE_CARDS = {
    "generic_decline": {
        "number": "4000000000000002",
        "expiry": "10/69",
        "cvc": "549",
        "expected_error": "card_declined",
    },
    "insufficient_funds": {
        "number": "4000000000009995",
        "expiry": "10/69",
        "cvc": "549",
        "expected_error": "insufficient_funds",
    },
    "lost_card": {
        "number": "4000000000009987",
        "expiry": "10/69",
        "cvc": "549",
        "expected_error": "lost_card",
    },
    "stolen_card": {
        "number": "4000000000009979",
        "expiry": "10/69",
        "cvc": "549",
        "expected_error": "stolen_card",
    },
}

# Valid test data for baseline
VALID_CUSTOMER = {
    "first_name": "Mark",
    "last_name": "Testing",
    "email": "qa.orca.contact@gmail.com",
    "phone": "7977321321",
    "postcode": "BH8 8RB",
}

VALID_VEHICLE = {
    "registration": "AA19MOT",
}


class NegativeTestRunner:
    def __init__(self, page: Page):
        self.page = page
        self.results = {"passed": [], "failed": []}

    def navigate_to_booking(self):
        """Navigate to booking page and wait for load."""
        self.page.goto(STAGING_URL, wait_until="networkidle")
        time.sleep(2)

    def get_validation_errors(self):
        """Get all visible validation error messages."""
        errors = []
        # Check for error messages in various formats
        error_selectors = [
            ".error-message",
            ".field-error",
            ".validation-error",
            "[class*='error']",
            ".text-red-500",
            ".text-danger",
        ]
        for selector in error_selectors:
            elements = self.page.locator(selector).all()
            for el in elements:
                if el.is_visible():
                    text = el.text_content()
                    if text and text.strip():
                        errors.append(text.strip())
        return errors

    def is_button_disabled(self, button_text: str) -> bool:
        """Check if a button is disabled."""
        btn = self.page.locator(f"button:has-text('{button_text}')")
        if btn.count() > 0:
            return btn.first.is_disabled()
        return False

    def run_test(self, name: str, test_func):
        """Run a single test and record result."""
        print(f"\n[TEST] {name}")
        try:
            result = test_func()
            if result:
                print(f"  PASSED")
                self.results["passed"].append(name)
            else:
                print(f"  FAILED")
                self.results["failed"].append(name)
        except Exception as e:
            print(f"  ERROR: {str(e)}")
            self.results["failed"].append(f"{name} (error: {str(e)[:50]})")

    # ============ STEP 1 TESTS: Customer Details ============

    def test_empty_first_name(self) -> bool:
        """Test that empty first name shows validation error."""
        self.navigate_to_booking()

        # Fill everything except first name
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        # Try to click Continue - should be disabled or show error
        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        # Check if button is disabled
        if continue_btn.is_disabled():
            print("    Button disabled as expected")
            return True

        # If not disabled, click and check for error
        continue_btn.click()
        time.sleep(1)

        # Check if we're still on step 1 (validation failed)
        if self.page.locator("#firstName").is_visible():
            print("    Stayed on step 1 - validation working")
            return True

        return False

    def test_empty_last_name(self) -> bool:
        """Test that empty last name shows validation error."""
        self.navigate_to_booking()

        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        # Skip last name
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled as expected")
            return True

        continue_btn.click()
        time.sleep(1)

        if self.page.locator("#lastName").is_visible():
            print("    Stayed on step 1 - validation working")
            return True

        return False

    def test_invalid_email_format(self) -> bool:
        """Test that invalid email format is rejected."""
        self.navigate_to_booking()

        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill("invalid-email")  # Invalid format
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled for invalid email")
            return True

        continue_btn.click()
        time.sleep(1)

        # Check for email validation error or still on step 1
        if self.page.locator("#email").is_visible():
            print("    Stayed on step 1 - email validation working")
            return True

        return False

    def test_empty_email(self) -> bool:
        """Test that empty email shows validation error."""
        self.navigate_to_booking()

        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        # Skip email
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled as expected")
            return True

        continue_btn.click()
        time.sleep(1)

        if self.page.locator("#email").is_visible():
            print("    Stayed on step 1 - validation working")
            return True

        return False

    def test_empty_phone(self) -> bool:
        """Test that empty phone number shows validation error."""
        self.navigate_to_booking()

        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        # Skip phone - but may have default +44

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled as expected")
            return True

        continue_btn.click()
        time.sleep(1)

        if self.page.locator(".phone-input").is_visible():
            print("    Stayed on step 1 - validation working")
            return True

        return False

    def test_invalid_phone_format(self) -> bool:
        """Test that invalid phone format is rejected."""
        self.navigate_to_booking()

        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("123")  # Too short

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled for invalid phone")
            return True

        continue_btn.click()
        time.sleep(1)

        if self.page.locator(".phone-input").is_visible():
            print("    Stayed on step 1 - phone validation working")
            return True

        return False

    def test_empty_vehicle_registration(self) -> bool:
        """Test that empty vehicle registration is rejected."""
        self.navigate_to_booking()

        # Fill customer details
        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        # Fill address
        self.page.locator("#billingPostcode").fill(VALID_CUSTOMER["postcode"])
        self.page.locator("button:has-text('Find Address')").click()
        time.sleep(2)
        try:
            if self.page.locator("#addressSelect").is_visible(timeout=3000):
                self.page.locator("#addressSelect").select_option(index=1)
                time.sleep(0.5)
        except:
            pass

        # Skip vehicle registration

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled - vehicle required")
            return True

        continue_btn.click()
        time.sleep(1)

        if self.page.locator("#registration").is_visible():
            print("    Stayed on step 1 - vehicle validation working")
            return True

        return False

    def test_invalid_vehicle_registration(self) -> bool:
        """Test that invalid vehicle registration format is rejected."""
        self.navigate_to_booking()

        # Fill customer details
        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        # Fill address
        self.page.locator("#billingPostcode").fill(VALID_CUSTOMER["postcode"])
        self.page.locator("button:has-text('Find Address')").click()
        time.sleep(2)
        try:
            if self.page.locator("#addressSelect").is_visible(timeout=3000):
                self.page.locator("#addressSelect").select_option(index=1)
                time.sleep(0.5)
        except:
            pass

        # Enter invalid registration
        self.page.locator("#registration").fill("INVALID123456789")
        self.page.locator("button.validate-btn").click()
        time.sleep(2)

        # Check for DVLA error message
        error_visible = self.page.locator("text=not found").is_visible(timeout=3000) or \
                       self.page.locator("text=invalid").is_visible(timeout=1000) or \
                       self.page.locator("text=Unable").is_visible(timeout=1000)

        if error_visible:
            print("    DVLA lookup error shown for invalid reg")
            return True

        # Check if still needs vehicle details
        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")
        if continue_btn.is_disabled():
            print("    Button disabled - invalid vehicle")
            return True

        return False

    def test_missing_address(self) -> bool:
        """Test that missing address is rejected."""
        self.navigate_to_booking()

        # Fill customer details
        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        # Skip address entirely

        # Fill vehicle
        self.page.locator("#registration").fill(VALID_VEHICLE["registration"])
        self.page.locator("button.validate-btn").click()
        time.sleep(2)

        # Select model if needed
        model_select = self.page.locator("select#model")
        if model_select.is_visible(timeout=2000):
            model_select.select_option(label="A3")
            time.sleep(0.5)

        continue_btn = self.page.locator("button.next-btn:has-text('Continue to Trip Details')")

        if continue_btn.is_disabled():
            print("    Button disabled - address required")
            return True

        continue_btn.click()
        time.sleep(1)

        # Check if still on step 1
        if self.page.locator("#billingPostcode").is_visible():
            print("    Stayed on step 1 - address validation working")
            return True

        return False

    # ============ STEP 2 TESTS: Trip Details ============

    def fill_step1_and_proceed(self):
        """Fill step 1 with valid data and proceed to step 2."""
        self.navigate_to_booking()

        # Customer details
        self.page.locator("#firstName").fill(VALID_CUSTOMER["first_name"])
        self.page.locator("#lastName").fill(VALID_CUSTOMER["last_name"])
        self.page.locator("#email").fill(VALID_CUSTOMER["email"])
        phone_input = self.page.locator(".phone-input input[type='tel']")
        phone_input.fill("+44" + VALID_CUSTOMER["phone"])

        # Address - enter manually (lookup service not available in staging)
        self.page.locator("#billingPostcode").fill(VALID_CUSTOMER["postcode"])
        time.sleep(0.3)
        # Click manual entry link
        manual_link = self.page.locator("text=Enter address manually")
        if manual_link.is_visible(timeout=2000):
            manual_link.click()
            time.sleep(0.5)
        # Fill address fields
        self.page.locator("#billingAddress1").fill("176 Shelbourne Rd")
        time.sleep(0.2)
        self.page.locator("#billingCity").fill("Bournemouth")
        time.sleep(0.2)
        self.page.locator("#billingCounty").fill("Dorset")
        time.sleep(0.2)

        # Vehicle
        self.page.locator("#registration").fill(VALID_VEHICLE["registration"])
        self.page.locator("button.validate-btn").click()
        time.sleep(2)

        model_select = self.page.locator("select#model")
        if model_select.is_visible(timeout=3000):
            model_select.select_option(label="A3")
            time.sleep(0.5)

        # Proceed to step 2
        self.page.locator("button.next-btn:has-text('Continue to Trip Details')").click()
        time.sleep(2)

        # Handle welcome modal
        welcome_modal_btn = self.page.locator(".welcome-modal-btn")
        if welcome_modal_btn.is_visible(timeout=3000):
            welcome_modal_btn.click()
            time.sleep(1)

    def test_missing_dropoff_date(self) -> bool:
        """Test that missing drop-off date prevents progress."""
        self.fill_step1_and_proceed()

        # Don't select a date, just check if Continue button is disabled
        # The Continue button should be disabled until a date is selected
        time.sleep(1)

        continue_btn = self.page.locator("button:has-text('Continue to Package Selection')")

        if continue_btn.is_visible(timeout=3000):
            if continue_btn.is_disabled():
                print("    Button disabled - date required")
                return True
            else:
                # Button is enabled but shouldn't be without a date - this is actually a fail
                print("    Button enabled without date selected (unexpected)")
                return False
        else:
            # Button not visible yet - date is required first
            print("    Continue button not visible - date required first")
            return True

    def test_missing_airline(self) -> bool:
        """Test that missing airline selection is rejected."""
        self.fill_step1_and_proceed()

        # Select date
        dropoff_date = datetime.now().date() + timedelta(days=21)
        self.page.locator("#dropoffDate").click()
        time.sleep(0.5)

        # Navigate to correct month
        target_month = dropoff_date.month
        target_year = dropoff_date.year
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

        for _ in range(12):
            header = self.page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])
                    if displayed_month == target_month and displayed_year == target_year:
                        break
                    self.page.locator(".react-datepicker__navigation--next").click()
                    time.sleep(0.3)

        # Click day
        day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
        for i in range(day_buttons.count()):
            if day_buttons.nth(i).text_content() == str(dropoff_date.day):
                day_buttons.nth(i).click()
                break
        time.sleep(0.5)

        # Skip airline, fill rest
        self.page.locator("#manualDestination").select_option(value="ALC")
        self.page.locator("#manualFlightNumber").fill("1234")
        self.page.locator("#manualFlightTime").fill("10:00")

        continue_btn = self.page.locator("button:has-text('Continue to Package Selection')")

        if continue_btn.is_disabled():
            print("    Button disabled - airline required")
            return True

        return False

    def test_missing_flight_number(self) -> bool:
        """Test that missing flight number is rejected."""
        self.fill_step1_and_proceed()

        # Select date
        dropoff_date = datetime.now().date() + timedelta(days=21)
        self.page.locator("#dropoffDate").click()
        time.sleep(0.5)

        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

        for _ in range(12):
            header = self.page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])
                    if displayed_month == dropoff_date.month and displayed_year == dropoff_date.year:
                        break
                    self.page.locator(".react-datepicker__navigation--next").click()
                    time.sleep(0.3)

        day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
        for i in range(day_buttons.count()):
            if day_buttons.nth(i).text_content() == str(dropoff_date.day):
                day_buttons.nth(i).click()
                break
        time.sleep(0.5)

        # Fill airline and destination, skip flight number
        self.page.locator("#manualAirline").select_option(value="FR")
        time.sleep(0.3)
        self.page.locator("#manualDestination").select_option(value="ALC")
        time.sleep(0.3)
        # Skip flight number
        self.page.locator("#manualFlightTime").fill("10:00")

        continue_btn = self.page.locator("button:has-text('Continue to Package Selection')")

        if continue_btn.is_disabled():
            print("    Button disabled - flight number required")
            return True

        return False

    def test_past_dropoff_date(self) -> bool:
        """Test that past drop-off date is rejected."""
        self.fill_step1_and_proceed()

        # Try to select a past date
        past_date = datetime.now().date() - timedelta(days=5)
        self.page.locator("#dropoffDate").click()
        time.sleep(0.5)

        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

        # Navigate to past month
        for _ in range(3):
            header = self.page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])
                    if displayed_month == past_date.month and displayed_year == past_date.year:
                        break
                    self.page.locator(".react-datepicker__navigation--previous").click()
                    time.sleep(0.3)

        # Check if past days are disabled
        day_buttons = self.page.locator(".react-datepicker__day--disabled")
        if day_buttons.count() > 0:
            print("    Past dates are disabled")
            return True

        return False

    # ============ STEP 4 TESTS: Payment ============

    def test_terms_not_accepted(self) -> bool:
        """Test that payment cannot proceed without accepting terms."""
        # Navigate to payment step but DON'T accept terms
        self.fill_step1_and_proceed()

        dropoff_date = datetime.now().date() + timedelta(days=21)
        pickup_date = dropoff_date + timedelta(days=7)
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

        # Select dropoff date
        self.page.locator("#dropoffDate").click()
        time.sleep(0.5)

        for _ in range(12):
            header = self.page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])
                    if displayed_month == dropoff_date.month and displayed_year == dropoff_date.year:
                        break
                    self.page.locator(".react-datepicker__navigation--next").click()
                    time.sleep(0.3)

        day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
        for i in range(day_buttons.count()):
            if day_buttons.nth(i).text_content() == str(dropoff_date.day):
                day_buttons.nth(i).click()
                break
        time.sleep(1)

        # Fill flight details
        self.page.locator("#manualAirline").select_option(value="FR")
        time.sleep(0.3)
        self.page.locator("#manualDestination").select_option(value="ALC")
        time.sleep(0.3)
        self.page.locator("#manualFlightNumber").fill("1234")
        self.page.locator("#manualFlightTime").fill("10:00")
        time.sleep(1)

        # Select slot
        slot_cards = self.page.locator(".dropoff-slot .slot-card")
        if slot_cards.count() > 0:
            slot_cards.first.click()
            time.sleep(1)

        # Select return date
        return_picker = self.page.locator(".date-picker-input").nth(1)
        if return_picker.is_visible(timeout=3000):
            return_picker.click()
            time.sleep(0.5)

            for _ in range(12):
                header = self.page.locator(".react-datepicker__current-month").text_content()
                if header:
                    parts = header.split()
                    if len(parts) == 2:
                        displayed_month = month_names.index(parts[0]) + 1
                        displayed_year = int(parts[1])
                        if displayed_month == pickup_date.month and displayed_year == pickup_date.year:
                            break
                        self.page.locator(".react-datepicker__navigation--next").click()
                        time.sleep(0.3)

            day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
            for i in range(day_buttons.count()):
                if day_buttons.nth(i).text_content() == str(pickup_date.day):
                    day_buttons.nth(i).click()
                    break
            time.sleep(0.5)

        # Return flight
        self.page.locator("#manualArrivalAirline").select_option(value="FR")
        time.sleep(0.3)
        self.page.locator("#manualArrivalOrigin").select_option(value="ALC")
        time.sleep(0.3)
        self.page.locator("#manualArrivalFlightNumber").fill("1235")
        self.page.locator("#manualArrivalFlightTime").fill("14:00")
        time.sleep(1)

        # Proceed to package selection
        pkg_btn = self.page.locator("button:has-text('Continue to Package Selection')")
        if pkg_btn.is_visible(timeout=3000):
            pkg_btn.click()
            time.sleep(3)

        # Proceed to payment
        pay_btn = self.page.locator("button:has-text('Continue to Payment')")
        if pay_btn.is_visible(timeout=3000):
            pay_btn.click()
            time.sleep(3)

        # DO NOT accept terms - wait for payment section to load
        time.sleep(2)

        # Dismiss Stripe Link popup if it appears
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
        except:
            pass

        # The key test: WITHOUT checking terms, the Pay button should NOT be visible
        # Look for the pay button - it should NOT exist when terms aren't checked
        stripe_pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")

        # The pay button should NOT be visible without terms accepted
        if not stripe_pay_btn.is_visible(timeout=3000):
            # Check for info message about terms
            page_text = self.page.content().lower()
            if "terms" in page_text or "conditions" in page_text:
                print("    Pay button NOT visible + terms info shown - validation working")
                return True
            else:
                print("    Pay button NOT visible (terms required)")
                return True

        # If pay button IS visible, check if it's disabled
        if stripe_pay_btn.is_disabled():
            print("    Pay button disabled without terms accepted")
            return True

        # If button is visible and enabled, that's a failure (terms should be required)
        print("    Pay button visible and enabled without terms - FAIL")
        return False

    def go_to_payment_step(self):
        """Navigate through all steps to reach payment (helper for payment tests)."""
        self.fill_step1_and_proceed()

        dropoff_date = datetime.now().date() + timedelta(days=21)
        pickup_date = dropoff_date + timedelta(days=7)
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]

        # Select dropoff date
        self.page.locator("#dropoffDate").click()
        time.sleep(0.5)

        for _ in range(12):
            header = self.page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])
                    if displayed_month == dropoff_date.month and displayed_year == dropoff_date.year:
                        break
                    self.page.locator(".react-datepicker__navigation--next").click()
                    time.sleep(0.3)

        day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
        for i in range(day_buttons.count()):
            if day_buttons.nth(i).text_content() == str(dropoff_date.day):
                day_buttons.nth(i).click()
                break
        time.sleep(1)

        # Fill flight details
        self.page.locator("#manualAirline").select_option(value="FR")
        time.sleep(0.3)
        self.page.locator("#manualDestination").select_option(value="ALC")
        time.sleep(0.3)
        self.page.locator("#manualFlightNumber").fill("1234")
        self.page.locator("#manualFlightTime").fill("10:00")
        time.sleep(1)

        # Select slot
        slot_cards = self.page.locator(".dropoff-slot .slot-card")
        if slot_cards.count() > 0:
            slot_cards.first.click()
            time.sleep(1)

        # Select return date
        return_picker = self.page.locator(".date-picker-input").nth(1)
        if return_picker.is_visible(timeout=3000):
            return_picker.click()
            time.sleep(0.5)

            for _ in range(12):
                header = self.page.locator(".react-datepicker__current-month").text_content()
                if header:
                    parts = header.split()
                    if len(parts) == 2:
                        displayed_month = month_names.index(parts[0]) + 1
                        displayed_year = int(parts[1])
                        if displayed_month == pickup_date.month and displayed_year == pickup_date.year:
                            break
                        self.page.locator(".react-datepicker__navigation--next").click()
                        time.sleep(0.3)

            day_buttons = self.page.locator(".react-datepicker__day:not(.react-datepicker__day--outside-month)")
            for i in range(day_buttons.count()):
                if day_buttons.nth(i).text_content() == str(pickup_date.day):
                    day_buttons.nth(i).click()
                    break
            time.sleep(0.5)

        # Return flight
        self.page.locator("#manualArrivalAirline").select_option(value="FR")
        time.sleep(0.3)
        self.page.locator("#manualArrivalOrigin").select_option(value="ALC")
        time.sleep(0.3)
        self.page.locator("#manualArrivalFlightNumber").fill("1235")
        self.page.locator("#manualArrivalFlightTime").fill("14:00")
        time.sleep(1)

        # Proceed to package selection
        pkg_btn = self.page.locator("button:has-text('Continue to Package Selection')")
        if pkg_btn.is_visible(timeout=3000):
            pkg_btn.click()
            time.sleep(3)

        # Proceed to payment
        pay_btn = self.page.locator("button:has-text('Continue to Payment')")
        if pay_btn.is_visible(timeout=3000):
            pay_btn.click()
            time.sleep(3)

        # Accept terms
        terms_checkbox = self.page.locator("input[name='terms']")
        if terms_checkbox.is_visible(timeout=3000):
            if not terms_checkbox.is_checked():
                terms_checkbox.click()
            time.sleep(1)

        # Handle Link popup if it appears
        time.sleep(2)
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
        except:
            pass

    def find_stripe_payment_frame(self):
        """Find the Stripe payment iframe."""
        for frame in self.page.frames:
            try:
                card_input = frame.locator("#payment-numberInput")
                if card_input.count() > 0:
                    return frame
            except:
                continue
        return None

    def fill_card_details(self, card_number: str, expiry: str, cvc: str):
        """Fill card details in Stripe iframe."""
        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            # Card number
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            time.sleep(0.2)
            card_input.fill(card_number)
            time.sleep(0.3)

            # Expiry
            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            time.sleep(0.2)
            expiry_input.fill(expiry)
            time.sleep(0.3)

            # CVC
            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            time.sleep(0.2)
            cvc_input.fill(cvc)
            time.sleep(0.5)
            return True
        return False

    def test_missing_card_number(self) -> bool:
        """Test that missing card number prevents payment."""
        self.go_to_payment_step()

        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            # Only fill expiry and CVC, skip card number
            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            expiry_input.fill("10/69")
            time.sleep(0.3)

            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            cvc_input.fill("549")
            time.sleep(0.5)

        # Try to click pay button and check for error
        pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=3000):
            if pay_btn.is_disabled():
                print("    Pay button disabled - card number required")
                return True
            # Try clicking and check if payment fails
            pay_btn.click()
            time.sleep(3)
            # Should still be on payment page (not success)
            if not self.page.locator("text=Payment Successful").is_visible(timeout=2000):
                print("    Payment blocked - card number required")
                return True

        return False

    def test_missing_expiry(self) -> bool:
        """Test that missing expiry date prevents payment."""
        self.go_to_payment_step()

        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            # Fill card number and CVC, skip expiry
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            card_input.fill("4242424242424242")
            time.sleep(0.3)

            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            cvc_input.fill("549")
            time.sleep(0.5)

        pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=3000):
            if pay_btn.is_disabled():
                print("    Pay button disabled - expiry required")
                return True
            # Try clicking and check if payment fails
            pay_btn.click()
            time.sleep(3)
            if not self.page.locator("text=Payment Successful").is_visible(timeout=2000):
                print("    Payment blocked - expiry required")
                return True

        return False

    def test_missing_cvc(self) -> bool:
        """Test that missing CVC prevents payment."""
        self.go_to_payment_step()

        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            # Fill card number and expiry, skip CVC
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            card_input.fill("4242424242424242")
            time.sleep(0.3)

            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            expiry_input.fill("10/69")
            time.sleep(0.5)

        pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=3000):
            if pay_btn.is_disabled():
                print("    Pay button disabled - CVC required")
                return True
            # Try clicking and check if payment fails
            pay_btn.click()
            time.sleep(3)
            if not self.page.locator("text=Payment Successful").is_visible(timeout=2000):
                print("    Payment blocked - CVC required")
                return True

        return False

    def test_invalid_card_number(self) -> bool:
        """Test that invalid card number format is rejected."""
        self.go_to_payment_step()

        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            # Fill invalid card number
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            card_input.fill("1234567890123456")  # Invalid Luhn check
            time.sleep(0.3)

            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            expiry_input.fill("10/69")
            time.sleep(0.3)

            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            cvc_input.fill("549")
            time.sleep(0.5)

        # Check for Stripe validation error or disabled button
        pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=3000):
            if pay_btn.is_disabled():
                print("    Pay button disabled - invalid card number")
                return True

            # Try clicking and check for error
            pay_btn.click()
            time.sleep(3)

            # Check for error message
            if self.page.locator("text=invalid").is_visible(timeout=3000) or \
               self.page.locator("text=incorrect").is_visible(timeout=1000):
                print("    Error shown for invalid card number")
                return True

        return False

    def test_expired_card(self) -> bool:
        """Test that expired card is rejected."""
        self.go_to_payment_step()

        payment_frame = self.find_stripe_payment_frame()
        if payment_frame:
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            card_input.fill("4242424242424242")
            time.sleep(0.3)

            # Use past expiry date
            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            expiry_input.fill("01/20")  # Expired
            time.sleep(0.3)

            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            cvc_input.fill("549")
            time.sleep(0.5)

        pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
        if pay_btn.is_visible(timeout=3000):
            if pay_btn.is_disabled():
                print("    Pay button disabled - expired card")
                return True
            # Try clicking and check for expiry error
            pay_btn.click()
            time.sleep(3)
            # Check for expiry error or still on payment page
            if self.page.locator("text=/expir/i").is_visible(timeout=3000) or \
               self.page.locator("text=/invalid/i").is_visible(timeout=1000):
                print("    Error shown for expired card")
                return True
            if not self.page.locator("text=Payment Successful").is_visible(timeout=2000):
                print("    Payment blocked - expired card rejected")
                return True

        return False

    def test_stripe_decline_card(self, card_type: str = None, card_data: dict = None) -> bool:
        """Test Stripe decline scenario with specific test card."""
        self.go_to_payment_step()

        if self.fill_card_details(card_data["number"], card_data["expiry"], card_data["cvc"]):
            time.sleep(1)

            pay_btn = self.page.locator(".stripe-pay-btn, button:has-text('Pay ')")
            if pay_btn.is_visible(timeout=3000) and not pay_btn.is_disabled():
                pay_btn.click()
                time.sleep(10)  # Wait for payment processing

                # Check for decline error message
                error_texts = ["declined", "insufficient", "lost", "stolen", "failed", "error"]
                for error_text in error_texts:
                    if self.page.locator(f"text=/{error_text}/i").is_visible(timeout=2000):
                        print(f"    Decline error shown: {error_text}")
                        return True

                # Check we're still on payment page (not success)
                if not self.page.locator("text=Payment Successful").is_visible(timeout=2000):
                    print(f"    Payment failed as expected (not successful)")
                    return True

        return False


def run_single_test_in_process(test_info: Tuple[str, str, dict]) -> Tuple[str, bool, str]:
    """Run a single test in its own browser (for multiprocessing)."""
    test_name, test_method_name, test_args = test_info

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=50)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            runner = NegativeTestRunner(page)

            # Get the test method
            test_method = getattr(runner, test_method_name)

            # Run the test with args if provided
            if test_args:
                result = test_method(**test_args)
            else:
                result = test_method()

            context.close()
            browser.close()

            status = "PASS" if result else "FAIL"
            return (test_name, result, "")

    except Exception as e:
        return (test_name, False, str(e)[:100])


def main():
    print("=" * 60)
    print("TAG Parking - Negative Test Cases (Parallel Execution)")
    print("=" * 60)
    print(f"URL: {STAGING_URL}")
    print(f"Running 5 tests in parallel (5 browser windows)...")
    print()

    # Define all tests as (name, method_name, args)
    all_tests = [
        # Step 1 Tests - Customer Details
        ("Empty First Name", "test_empty_first_name", None),
        ("Empty Last Name", "test_empty_last_name", None),
        ("Invalid Email Format", "test_invalid_email_format", None),
        ("Empty Email", "test_empty_email", None),
        ("Empty Phone", "test_empty_phone", None),
        ("Invalid Phone Format", "test_invalid_phone_format", None),
        ("Empty Vehicle Registration", "test_empty_vehicle_registration", None),
        ("Invalid Vehicle Registration", "test_invalid_vehicle_registration", None),
        ("Missing Address", "test_missing_address", None),

        # Step 2 Tests - Trip Details
        ("Missing Drop-off Date", "test_missing_dropoff_date", None),
        ("Missing Airline", "test_missing_airline", None),
        ("Missing Flight Number", "test_missing_flight_number", None),
        ("Past Drop-off Date", "test_past_dropoff_date", None),

        # Step 4 Tests - Payment Validation
        ("Terms Not Accepted", "test_terms_not_accepted", None),
        ("Missing Card Number", "test_missing_card_number", None),
        ("Missing Expiry Date", "test_missing_expiry", None),
        ("Missing CVC", "test_missing_cvc", None),
        ("Invalid Card Number Format", "test_invalid_card_number", None),
        ("Expired Card", "test_expired_card", None),
    ]

    # Add Stripe decline tests
    for card_type, card_data in STRIPE_DECLINE_CARDS.items():
        all_tests.append((
            f"Stripe Decline: {card_type}",
            "test_stripe_decline_card",
            {"card_type": card_type, "card_data": card_data}
        ))

    all_results = {"passed": [], "failed": []}

    # Run tests in batches of 5 using multiprocessing
    batch_size = 5
    total_batches = (len(all_tests) + batch_size - 1) // batch_size

    for i in range(0, len(all_tests), batch_size):
        batch = all_tests[i:i + batch_size]
        batch_num = (i // batch_size) + 1

        print(f"\n--- Batch {batch_num}/{total_batches} ({len(batch)} tests) ---")

        # Use multiprocessing Pool to run tests in parallel
        with Pool(processes=min(5, len(batch))) as pool:
            results = pool.map(run_single_test_in_process, batch)

        for test_name, passed, error in results:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {test_name}")
            if passed:
                all_results["passed"].append(test_name)
            else:
                all_results["failed"].append(test_name if not error else f"{test_name} ({error[:30]})")

        # Small delay between batches
        if i + batch_size < len(all_tests):
            time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Tests: {len(all_tests)}")
    print(f"Passed: {len(all_results['passed'])}")
    print(f"Failed: {len(all_results['failed'])}")

    if all_results["passed"]:
        print("\nPassed tests:")
        for name in sorted(all_results["passed"]):
            print(f"  PASS {name}")

    if all_results["failed"]:
        print("\nFailed tests:")
        for name in sorted(all_results["failed"]):
            print(f"  FAIL {name}")


if __name__ == "__main__":
    main()
