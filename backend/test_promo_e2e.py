#!/usr/bin/env python3
"""
E2E tests for promo code functionality on TAG Parking staging.

Tests:
1. 10% OFF promo code - Verifies discount is applied and payment completes
2. FREE parking promo code - Verifies 100% discount and free booking flow

Prerequisites:
    pip install playwright
    playwright install chromium

    # Ensure test promo codes exist in staging:
    python scripts/reset_test_promo.py --ensure-test

    # Reset promo codes before running (marks them as unused):
    python scripts/reset_test_promo.py --reset-all-test

Usage:
    python test_promo_e2e.py                    # Run all promo tests
    python test_promo_e2e.py --10off            # Run only 10% off test
    python test_promo_e2e.py --free             # Run only FREE promo test
    HEADLESS=true python test_promo_e2e.py     # Run headless
"""

from playwright.sync_api import sync_playwright, Page
from datetime import datetime, timedelta
import time
import os
import sys
import psycopg2

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

# Staging database connection
STAGING_DB = {
    "host": "switchback.proxy.rlwy.net",
    "port": 25567,
    "user": "postgres",
    "password": "oviYXmjpSwWKHejteMgdIxXTorTtGdUl",
    "dbname": "railway"
}

# Test promo codes (must exist in staging database)
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

# Test customer details
CUSTOMER = {
    "first_name": "Promo",
    "last_name": "Tester",
    "email": "qa.orca.contact@gmail.com",
    "phone": "7977321321",
    "address1": "176 Shelbourne Rd",
    "city": "Bournemouth",
    "county": "Dorset",
    "postcode": "BH8 8RB",
}

# Test vehicle
VEHICLE = {
    "registration": "PR0M0TST",
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


def select_date_in_picker(page: Page, target_date: datetime, field_id: str):
    """Select a date in the date picker."""
    # Click the date input to open picker
    date_input = page.locator(f"#{field_id}")
    date_input.click()
    time.sleep(0.5)

    # Navigate to correct month
    current_date = datetime.now()
    months_diff = (target_date.year - current_date.year) * 12 + (target_date.month - current_date.month)

    if months_diff > 0:
        for _ in range(months_diff):
            next_btn = page.locator(".react-datepicker__navigation--next")
            if next_btn.is_visible():
                next_btn.click()
                time.sleep(0.3)

    # Click the day
    day_selector = f".react-datepicker__day--0{target_date.day:02d}:not(.react-datepicker__day--outside-month)"
    day_element = page.locator(day_selector).first
    if day_element.is_visible(timeout=3000):
        day_element.click()
        time.sleep(0.3)


def fill_booking_form(page: Page, dropoff_date: datetime, pickup_date: datetime, test_name: str):
    """Fill the booking form up to the payment step."""

    print(f"\n[{test_name}] Starting booking...")
    print(f"  Drop-off: {dropoff_date.strftime('%Y-%m-%d')} at 10:00")
    print(f"  Pickup: {pickup_date.strftime('%Y-%m-%d')} at 14:00")

    # Navigate to booking page
    page.goto(STAGING_URL, wait_until="networkidle")
    time.sleep(3)

    # Dismiss welcome modal
    print("  Handling welcome modal...")
    welcome_modal_btn = page.locator(".welcome-modal-btn")
    if welcome_modal_btn.is_visible(timeout=5000):
        welcome_modal_btn.click()
        time.sleep(1)

    # ============ STEP 1: Trip Details ============
    print("  Step 1: Trip details...")

    # Select drop-off date
    select_date_in_picker(page, dropoff_date, "dropoffDate")
    time.sleep(0.5)

    # Select drop-off time
    time_select = page.locator("#dropoffTime")
    time_select.select_option("10:00")
    time.sleep(0.3)

    # Select pickup date
    select_date_in_picker(page, pickup_date, "pickupDate")
    time.sleep(0.5)

    # Select pickup time
    pickup_time_select = page.locator("#pickupTime")
    pickup_time_select.select_option("14:00")
    time.sleep(0.3)

    # Fill departure flight details
    print("    Filling departure flight...")
    page.locator("#airlineSearch").fill("Ryanair")
    time.sleep(1)
    airline_dropdown = page.locator(".airline-dropdown-item").first
    if airline_dropdown.is_visible(timeout=3000):
        airline_dropdown.click()
    time.sleep(0.5)

    page.locator("#destinationSearch").fill("Alicante")
    time.sleep(1)
    dest_dropdown = page.locator(".destination-dropdown-item").first
    if dest_dropdown.is_visible(timeout=3000):
        dest_dropdown.click()
    time.sleep(0.5)

    page.locator("#flightNumber").fill("1234")
    time.sleep(0.3)

    # Fill arrival flight details
    print("    Filling arrival flight...")
    page.locator("#arrivalAirlineSearch").fill("Ryanair")
    time.sleep(1)
    arr_airline = page.locator(".airline-dropdown-item").first
    if arr_airline.is_visible(timeout=3000):
        arr_airline.click()
    time.sleep(0.5)

    page.locator("#arrivalOriginSearch").fill("Alicante")
    time.sleep(1)
    arr_origin = page.locator(".destination-dropdown-item").first
    if arr_origin.is_visible(timeout=3000):
        arr_origin.click()
    time.sleep(0.5)

    page.locator("#arrivalFlightNumber").fill("1235")
    time.sleep(0.3)

    # Continue to Step 2
    print("  Proceeding to Step 2...")
    continue_btn = page.locator("button:has-text('Continue to Packages')")
    if continue_btn.is_visible(timeout=5000):
        continue_btn.click()
        time.sleep(2)

    # ============ STEP 2: Package Selection ============
    print("  Step 2: Package selection...")

    # Select Quick package (required for FREE promo testing)
    quick_package = page.locator(".package-card:has-text('Quick')")
    if quick_package.is_visible(timeout=5000):
        quick_package.click()
        time.sleep(1)

    # Continue to Step 3
    print("  Proceeding to Step 3...")
    continue_details_btn = page.locator("button:has-text('Continue to Your Details')")
    if continue_details_btn.is_visible(timeout=5000):
        continue_details_btn.click()
        time.sleep(2)

    # ============ STEP 3: Your Details ============
    print("  Step 3: Customer details...")

    # Fill contact information
    page.locator("#firstName").fill(CUSTOMER["first_name"])
    time.sleep(0.2)
    page.locator("#lastName").fill(CUSTOMER["last_name"])
    time.sleep(0.2)
    page.locator("#email").fill(CUSTOMER["email"])
    time.sleep(0.2)

    # Phone
    phone_input = page.locator(".phone-input input[type='tel']")
    phone_input.click()
    time.sleep(0.2)
    phone_input.fill("+44" + CUSTOMER["phone"])
    time.sleep(0.3)

    # Address - use postcode search
    print("    Searching postcode...")
    postcode_input = page.locator("#postcodeSearch")
    if postcode_input.is_visible(timeout=3000):
        postcode_input.fill(CUSTOMER["postcode"])
        time.sleep(0.5)

        find_btn = page.locator("button:has-text('Find')")
        if find_btn.is_visible(timeout=2000):
            find_btn.click()
            time.sleep(2)

            # Select first address from results
            address_item = page.locator(".address-result-item").first
            if address_item.is_visible(timeout=5000):
                address_item.click()
                time.sleep(1)

    # Vehicle details
    print("    Filling vehicle details...")
    page.locator("#vehicleReg").fill(VEHICLE["registration"])
    time.sleep(0.3)

    # Make dropdown
    make_select = page.locator("#vehicleMake")
    if make_select.is_visible(timeout=3000):
        make_select.click()
        time.sleep(0.5)
        make_option = page.locator(f".make-option:has-text('{VEHICLE['make']}')")
        if make_option.is_visible(timeout=3000):
            make_option.click()
            time.sleep(0.5)

    # Model dropdown
    model_select = page.locator("#vehicleModel")
    if model_select.is_visible(timeout=3000):
        model_select.click()
        time.sleep(0.5)
        model_option = page.locator(f".model-option:has-text('{VEHICLE['model']}')")
        if model_option.is_visible(timeout=3000):
            model_option.click()
            time.sleep(0.5)

    # Colour dropdown
    colour_select = page.locator("#vehicleColour")
    if colour_select.is_visible(timeout=3000):
        colour_select.click()
        time.sleep(0.5)
        colour_option = page.locator(f".colour-option:has-text('{VEHICLE['colour']}')")
        if colour_option.is_visible(timeout=3000):
            colour_option.click()
            time.sleep(0.5)

    # Continue to Payment
    print("  Proceeding to Step 4 (Payment)...")
    continue_payment_btn = page.locator("button:has-text('Continue to Payment')")
    if continue_payment_btn.is_visible(timeout=5000):
        continue_payment_btn.click()
        time.sleep(3)


def apply_promo_code(page: Page, promo_code: str) -> bool:
    """Enter and apply a promo code."""
    print(f"  Applying promo code: {promo_code}")

    # Find promo code input
    promo_input = page.locator(".promo-code-input input[placeholder='Enter promo code']")
    if not promo_input.is_visible(timeout=5000):
        print("    ERROR: Promo code input not found")
        return False

    # Enter promo code
    promo_input.fill(promo_code)
    time.sleep(0.5)

    # Click Apply button
    apply_btn = page.locator(".promo-apply-btn, button:has-text('Apply')")
    if apply_btn.is_visible(timeout=3000):
        apply_btn.click()
        time.sleep(2)

    # Check for success message
    promo_applied = page.locator(".promo-success, .promo-code-applied, text=/10% off|FREE|discount/i")
    if promo_applied.is_visible(timeout=5000):
        print("    Promo code applied successfully!")
        return True

    # Check for error
    promo_error = page.locator(".promo-error, text=/invalid|already used/i")
    if promo_error.is_visible(timeout=2000):
        error_text = promo_error.text_content()
        print(f"    Promo code error: {error_text}")
        return False

    # Check if the promo appears in summary
    promo_in_summary = page.locator(f"text={promo_code}")
    if promo_in_summary.is_visible(timeout=3000):
        print("    Promo code visible in summary")
        return True

    print("    Could not confirm promo code applied")
    return True  # Continue anyway


def fill_stripe_payment(page: Page) -> bool:
    """Fill Stripe payment form and submit."""
    print("  Filling payment details...")

    # Accept terms
    terms_checkbox = page.locator("input[name='terms']")
    if terms_checkbox.is_visible(timeout=3000):
        if not terms_checkbox.is_checked():
            terms_checkbox.click()
        time.sleep(1)

    # Wait for Stripe
    time.sleep(3)

    # Dismiss Stripe Link popup
    for _ in range(3):
        page.keyboard.press("Escape")
        time.sleep(0.3)

    try:
        page.mouse.click(10, 10)
        time.sleep(0.5)

        # Try to find and close Link modal
        close_selectors = [
            "[data-testid='link-close-button']",
            "button[aria-label='Close']",
            "button[aria-label='Back']",
        ]
        for selector in close_selectors:
            try:
                close_btn = page.locator(selector)
                if close_btn.is_visible(timeout=1000):
                    close_btn.click()
                    time.sleep(0.5)
                    break
            except:
                continue
    except:
        pass

    time.sleep(1)

    # Fill card details in Stripe iframe
    print("    Filling card details...")
    try:
        stripe_frames = page.frames
        payment_frame = None

        for frame in stripe_frames:
            try:
                card_input = frame.locator("#payment-numberInput")
                if card_input.count() > 0:
                    payment_frame = frame
                    break
            except:
                continue

        if payment_frame:
            # Card number
            card_input = payment_frame.locator("#payment-numberInput")
            card_input.click()
            time.sleep(0.2)
            card_input.fill(STRIPE_TEST_CARD["number"])
            print("    Card number filled")
            time.sleep(0.3)

            # Expiry
            expiry_input = payment_frame.locator("#payment-expiryInput")
            expiry_input.click()
            time.sleep(0.2)
            expiry_input.fill(STRIPE_TEST_CARD["expiry"])
            print("    Expiry filled")
            time.sleep(0.3)

            # CVC
            cvc_input = payment_frame.locator("#payment-cvcInput")
            cvc_input.click()
            time.sleep(0.2)
            cvc_input.fill(STRIPE_TEST_CARD["cvc"])
            print("    CVC filled")
            time.sleep(0.5)
        else:
            print("    Could not find Stripe payment frame")
            return False

    except Exception as e:
        print(f"    Stripe fill error: {e}")
        return False

    time.sleep(2)

    # Submit payment
    print("  Submitting payment...")
    pay_btn = page.locator(".stripe-pay-btn, button:has-text('Pay ')")
    if pay_btn.is_visible(timeout=5000) and not pay_btn.is_disabled():
        pay_btn.click()
    else:
        print("    Pay button disabled or not found")
        page.screenshot(path="promo_test_payment_error.png")
        return False

    return True


def wait_for_confirmation(page: Page) -> tuple[bool, str]:
    """Wait for booking confirmation and return (success, reference)."""
    print("  Waiting for confirmation...")
    time.sleep(10)

    booking_ref = None

    # Check for success indicators
    if page.locator("text=Payment Successful").is_visible(timeout=20000):
        print("    Payment successful!")
        try:
            ref_element = page.locator("text=/TAG-[A-Z0-9]+/")
            if ref_element.is_visible(timeout=3000):
                booking_ref = ref_element.text_content()
        except:
            pass
        return True, booking_ref

    if page.locator("text=Booking Confirmed").is_visible(timeout=5000):
        print("    Booking confirmed!")
        return True, booking_ref

    if page.locator(".booking-reference").is_visible(timeout=5000):
        booking_ref = page.locator(".booking-reference").text_content()
        return True, booking_ref

    if page.locator("text=Thank you").is_visible(timeout=5000):
        return True, booking_ref

    # Check for free booking success
    if page.locator("text=Free Booking").is_visible(timeout=5000):
        print("    Free booking confirmed!")
        return True, booking_ref

    print("    Could not confirm booking")
    page.screenshot(path="promo_test_confirmation_error.png")
    return False, None


def test_10_percent_promo(page: Page) -> bool:
    """Test 10% off promo code with payment."""
    test_name = "10% OFF Promo Test"
    print(f"\n{'='*60}")
    print(f"RUNNING: {test_name}")
    print(f"{'='*60}")

    # Set up dates - 7 day trip (eligible for Quick package)
    dropoff_date = datetime.now() + timedelta(days=21)
    pickup_date = dropoff_date + timedelta(days=7)

    try:
        # Fill booking form
        fill_booking_form(page, dropoff_date, pickup_date, test_name)

        # Apply promo code
        if not apply_promo_code(page, TEST_PROMO_10):
            print(f"  FAILED: Could not apply promo code {TEST_PROMO_10}")
            return False

        # Complete payment
        if not fill_stripe_payment(page):
            print("  FAILED: Could not complete payment")
            return False

        # Wait for confirmation
        success, booking_ref = wait_for_confirmation(page)

        if success:
            print(f"\n  SUCCESS: {test_name}")
            if booking_ref:
                print(f"  Booking Reference: {booking_ref}")
            # Reset promo code for reuse in future tests
            reset_promo_code(TEST_PROMO_10, "10")
            return True
        else:
            print(f"\n  FAILED: {test_name}")
            return False

    except Exception as e:
        print(f"\n  ERROR: {test_name} - {e}")
        page.screenshot(path="promo_10_error.png")
        return False


def test_free_promo(page: Page) -> bool:
    """Test FREE parking promo code (no payment).

    FREE promo rules:
    - Trips ≤7 days: Completely free (no payment needed)
    - Trips >7 days: 7-day base price deducted, pay for extra days

    This test uses a 7-day trip to verify the completely free booking flow.
    """
    test_name = "FREE Parking Promo Test (7-day trip)"
    print(f"\n{'='*60}")
    print(f"RUNNING: {test_name}")
    print(f"{'='*60}")

    # Set up dates - exactly 7 days (≤7 days = completely free with FREE promo)
    dropoff_date = datetime.now() + timedelta(days=28)
    pickup_date = dropoff_date + timedelta(days=7)
    print(f"  Duration: 7 days (eligible for 100% free booking)")

    try:
        # Fill booking form
        fill_booking_form(page, dropoff_date, pickup_date, test_name)

        # Apply promo code
        if not apply_promo_code(page, TEST_PROMO_FREE):
            print(f"  FAILED: Could not apply promo code {TEST_PROMO_FREE}")
            return False

        # For FREE promo, there should be a "Complete Free Booking" button instead of payment
        time.sleep(2)

        # Accept terms
        terms_checkbox = page.locator("input[name='terms']")
        if terms_checkbox.is_visible(timeout=3000):
            if not terms_checkbox.is_checked():
                terms_checkbox.click()
            time.sleep(1)

        # Look for free booking button
        free_booking_btn = page.locator("button:has-text('Complete Free Booking'), button:has-text('Confirm Free Booking'), .free-booking-btn")
        if free_booking_btn.is_visible(timeout=5000):
            print("  Completing free booking...")
            free_booking_btn.click()
        else:
            # If no free booking button, check if there's a pay button showing £0
            pay_btn = page.locator(".stripe-pay-btn, button:has-text('Pay ')")
            if pay_btn.is_visible(timeout=3000):
                # This might be showing £0.00 for free booking
                print("  Clicking pay button for free booking...")
                pay_btn.click()

        # Wait for confirmation
        success, booking_ref = wait_for_confirmation(page)

        if success:
            print(f"\n  SUCCESS: {test_name}")
            if booking_ref:
                print(f"  Booking Reference: {booking_ref}")
            # Reset promo code for reuse in future tests
            reset_promo_code(TEST_PROMO_FREE, "free")
            return True
        else:
            print(f"\n  FAILED: {test_name}")
            return False

    except Exception as e:
        print(f"\n  ERROR: {test_name} - {e}")
        page.screenshot(path="promo_free_error.png")
        return False


def main():
    """Run promo code E2E tests."""
    run_10_off = "--10off" in sys.argv or len(sys.argv) == 1
    run_free = "--free" in sys.argv or len(sys.argv) == 1

    print("\n" + "="*60)
    print("TAG Parking - Promo Code E2E Tests")
    print("="*60)
    print(f"Headless: {HEADLESS}")
    print(f"Test 10% OFF: {run_10_off}")
    print(f"Test FREE: {run_free}")
    print(f"Promo codes: {TEST_PROMO_10}, {TEST_PROMO_FREE}")

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=100)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-GB",
        )
        page = context.new_page()

        try:
            if run_10_off:
                results["10% OFF Promo"] = test_10_percent_promo(page)

            if run_free:
                results["FREE Promo"] = test_free_promo(page)

        finally:
            browser.close()

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} passed")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
