#!/usr/bin/env python3
"""
E2E test with network capture and hard refresh at each booking step.

This test:
1. Captures all network requests/responses
2. Does a HARD REFRESH (Ctrl+Shift+R / clear cache) at the start of each step
3. Logs all data sent to the API for analysis
4. Completes a full booking to verify data integrity

Usage:
    python test_booking_network_capture.py

    # Run headless
    HEADLESS=true python test_booking_network_capture.py
"""

from playwright.sync_api import sync_playwright, Page, Request, Response
from datetime import datetime, timedelta
import time
import json
import os
import sys

# Configuration
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
STAGING_URL = "https://staging-tagparking.netlify.app/tag-it"

# Test data
CUSTOMER = {
    "first_name": "Network",
    "last_name": "Test",
    "email": "network.test@example.com",
    "phone": "7911999888",
    "address1": "123 Network Street",
    "city": "Bournemouth",
    "county": "Dorset",
    "postcode": "BH1 1AA",
}

VEHICLE = {
    "registration": "NET123",
    "make": "Audi",
    "model": "A3",
    "colour": "Blue",
}

FLIGHT_DATA = {
    "airline_code": "FR",
    "airline_name": "Ryanair",
    "destination_code": "ALC",
    "destination_name": "Alicante",
    "dropoff_time": "10:00",
    "dropoff_flight_number": "FR9999",
    "return_time": "14:00",
    "return_flight_number": "FR9998",
}

# Stripe test card
STRIPE_TEST_CARD = {
    "number": "4242424242424242",
    "expiry": "10/69",
    "cvc": "549",
}

# Network capture storage
captured_requests = []
captured_responses = []


def log_request(request: Request):
    """Capture outgoing requests."""
    if "api" in request.url or "stripe" in request.url.lower():
        req_data = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "post_data": None
        }
        try:
            if request.post_data:
                req_data["post_data"] = request.post_data
                # Try to parse as JSON for readability
                try:
                    req_data["post_data_json"] = json.loads(request.post_data)
                except:
                    pass
        except:
            pass
        captured_requests.append(req_data)

        # Log important requests
        if "create-intent" in request.url or "payment" in request.url.lower():
            print(f"\n{'='*60}")
            print(f"CAPTURED REQUEST: {request.method} {request.url}")
            print(f"{'='*60}")
            if req_data.get("post_data_json"):
                print(json.dumps(req_data["post_data_json"], indent=2))
            elif req_data.get("post_data"):
                print(req_data["post_data"][:500])
            print(f"{'='*60}\n")


def log_response(response: Response):
    """Capture incoming responses."""
    if "api" in response.url or "stripe" in response.url.lower():
        resp_data = {
            "timestamp": datetime.now().isoformat(),
            "status": response.status,
            "url": response.url,
            "headers": dict(response.headers),
            "body": None
        }
        try:
            body = response.text()
            resp_data["body"] = body
            # Try to parse as JSON
            try:
                resp_data["body_json"] = json.loads(body)
            except:
                pass
        except:
            pass
        captured_responses.append(resp_data)

        # Log important responses
        if "create-intent" in response.url or "booking" in response.url.lower():
            print(f"\n{'='*60}")
            print(f"CAPTURED RESPONSE: {response.status} {response.url}")
            print(f"{'='*60}")
            if resp_data.get("body_json"):
                print(json.dumps(resp_data["body_json"], indent=2))
            elif resp_data.get("body"):
                print(resp_data["body"][:500])
            print(f"{'='*60}\n")


def hard_refresh(page: Page):
    """Perform a hard refresh (bypass cache and reload)."""
    print("  >>> HARD REFRESH <<<")
    # Use keyboard shortcut for hard refresh (Cmd+Shift+R on Mac)
    # This bypasses the cache without clearing cookies/session
    page.keyboard.press("Meta+Shift+KeyR")
    time.sleep(3)
    # Fallback: regular reload if keyboard shortcut didn't work
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except:
        page.reload(wait_until="networkidle")
        time.sleep(2)


def dump_session_storage(page: Page, label: str):
    """Dump sessionStorage for debugging."""
    print(f"\n  --- SessionStorage at {label} ---")
    try:
        storage = page.evaluate("""
            () => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    if (key.startsWith('booking_')) {
                        try {
                            items[key] = JSON.parse(sessionStorage.getItem(key));
                        } catch {
                            items[key] = sessionStorage.getItem(key);
                        }
                    }
                }
                return items;
            }
        """)
        for key, value in storage.items():
            print(f"    {key}: {json.dumps(value, indent=6) if isinstance(value, dict) else value}")
    except Exception as e:
        print(f"    Error reading sessionStorage: {e}")
    print("  -----------------------------------\n")


def close_welcome_modal(page: Page):
    """Close the welcome modal if visible."""
    try:
        modal_btn = page.locator(".welcome-modal-btn")
        if modal_btn.is_visible(timeout=3000):
            modal_btn.click()
            time.sleep(1)
    except:
        pass


def select_date_in_picker(page: Page, date_obj, picker_id: str):
    """Select a date in the date picker."""
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
                month_names = ["January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]
                displayed_month = month_names.index(parts[0]) + 1
                displayed_year = int(parts[1])

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


def fill_step1(page: Page, dropoff_date, pickup_date, flight_data: dict):
    """Fill Step 1 - Trip Details."""
    print("\n  Filling Step 1 - Trip Details...")

    # Dropoff date
    select_date_in_picker(page, dropoff_date, "dropoffDate")
    time.sleep(1)

    # Airline
    airline_dropdown = page.locator("#manualAirline")
    airline_dropdown.wait_for(state="visible", timeout=10000)
    airline_dropdown.select_option(value=flight_data["airline_code"])
    time.sleep(1)

    # Destination
    destination_dropdown = page.locator("#manualDestination")
    destination_dropdown.select_option(value=flight_data["destination_code"])
    time.sleep(1)

    # Flight number
    page.locator("#manualFlightNumber").fill(flight_data["dropoff_flight_number"])
    time.sleep(0.5)

    # Departure time
    page.locator("#manualFlightTime").fill(flight_data["dropoff_time"])
    time.sleep(1)

    # Dropoff slot
    time.sleep(2)
    slot_cards = page.locator(".dropoff-slot .slot-card")
    if slot_cards.count() > 0:
        slot_cards.first.click()
        time.sleep(0.5)

    # Pickup date
    return_date_picker = page.locator(".date-picker-input").nth(1)
    if return_date_picker.is_visible(timeout=3000):
        return_date_picker.click()
        time.sleep(0.5)

        target_month = pickup_date.month
        target_year = pickup_date.year
        target_day = pickup_date.day

        for _ in range(24):
            header = page.locator(".react-datepicker__current-month").text_content()
            if header:
                parts = header.split()
                if len(parts) == 2:
                    month_names = ["January", "February", "March", "April", "May", "June",
                                  "July", "August", "September", "October", "November", "December"]
                    displayed_month = month_names.index(parts[0]) + 1
                    displayed_year = int(parts[1])

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

    # Return airline
    page.locator("#manualArrivalAirline").select_option(value=flight_data["airline_code"])
    time.sleep(0.5)

    # Return origin
    page.locator("#manualArrivalOrigin").select_option(value=flight_data["destination_code"])
    time.sleep(0.5)

    # Return flight number
    return_flight = page.locator("#manualArrivalFlightNumber")
    if return_flight.is_visible():
        return_flight.fill(flight_data["return_flight_number"])
    time.sleep(0.3)

    # Arrival time
    arrival_time = page.locator("#manualArrivalFlightTime")
    if arrival_time.is_visible():
        arrival_time.fill(flight_data["return_time"])
    time.sleep(1)

    print("  Step 1 complete.")


def fill_step3(page: Page, customer: dict, vehicle: dict):
    """Fill Step 3 - Your Details."""
    print("\n  Filling Step 3 - Your Details...")

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

    # Billing - manual entry
    page.locator("#billingPostcode").fill(customer["postcode"])
    time.sleep(0.3)

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
    page.locator("#registration").fill(vehicle["registration"])
    time.sleep(0.3)

    make_select = page.locator("select#make")
    if make_select.is_visible(timeout=3000):
        try:
            make_select.select_option(label=vehicle["make"])
            time.sleep(0.5)
        except:
            pass

    model_select = page.locator("select#model")
    if model_select.is_visible(timeout=3000):
        try:
            model_select.select_option(label=vehicle["model"])
            time.sleep(0.5)
        except:
            model_select.select_option(value="Other")
            page.locator("#customModel").fill(vehicle["model"])
            time.sleep(0.5)

    colour_input = page.locator("#colour")
    if colour_input.is_visible(timeout=1000):
        colour_input.fill(vehicle["colour"])
        time.sleep(0.3)

    print("  Step 3 complete.")


def complete_payment(page: Page) -> bool:
    """Complete Step 4 - Payment."""
    print("\n  Step 4 - Payment...")

    # Accept terms
    print("    Accepting terms...")
    time.sleep(1)
    try:
        terms_input = page.locator("input[name='terms']")
        if not terms_input.is_checked():
            page.evaluate("document.querySelector('input[name=\"terms\"]').click()")
            time.sleep(0.5)
    except Exception as e:
        print(f"    Warning: {e}")

    time.sleep(2)

    # Wait for Stripe
    print("    Waiting for Stripe...")
    time.sleep(3)

    # Dismiss Link popup
    for _ in range(3):
        page.keyboard.press("Escape")
        time.sleep(0.3)

    # Fill card details
    print("    Filling card details...")
    try:
        stripe_frame = page.frame_locator("iframe[name*='__privateStripeFrame']").first

        card_input = stripe_frame.locator("input[name='number']")
        if card_input.is_visible(timeout=5000):
            card_input.fill(STRIPE_TEST_CARD["number"])
            time.sleep(0.5)

        expiry_input = stripe_frame.locator("input[name='expiry']")
        if expiry_input.is_visible(timeout=2000):
            expiry_input.fill(STRIPE_TEST_CARD["expiry"])
            time.sleep(0.5)

        cvc_input = stripe_frame.locator("input[name='cvc']")
        if cvc_input.is_visible(timeout=2000):
            cvc_input.fill(STRIPE_TEST_CARD["cvc"])
            time.sleep(0.5)

    except Exception as e:
        print(f"    Stripe iframe error: {e}")
        # Try PaymentElement approach
        try:
            time.sleep(2)
            card_tab = page.locator("button:has-text('Card')")
            if card_tab.is_visible(timeout=2000):
                card_tab.click()
                time.sleep(1)

            stripe_container = page.locator(".StripeElement, [class*='stripe']").first
            if stripe_container.is_visible(timeout=3000):
                stripe_container.click()
                time.sleep(0.5)
                page.keyboard.type(STRIPE_TEST_CARD["number"])
                time.sleep(0.3)
                page.keyboard.type(STRIPE_TEST_CARD["expiry"].replace("/", ""))
                time.sleep(0.3)
                page.keyboard.type(STRIPE_TEST_CARD["cvc"])
                time.sleep(0.5)
        except Exception as e2:
            print(f"    Alt Stripe error: {e2}")

    # Click Pay
    print("    Clicking Pay button...")
    time.sleep(1)
    pay_button = page.locator(".stripe-pay-btn, button:has-text('Pay')")
    if pay_button.is_visible(timeout=5000):
        pay_button.click()
        time.sleep(5)

        # Check success
        success = page.locator(".booking-confirmation, :has-text('Booking Confirmed'), :has-text('Payment Complete')")
        if success.is_visible(timeout=30000):
            print("    Payment successful!")
            return True

        time.sleep(3)
        if "confirmation" in page.url.lower() or page.locator(":has-text('TAG-')").is_visible(timeout=5000):
            print("    Booking confirmed!")
            return True

    print("    Payment may not have completed")
    return False


def run_test():
    """Run the network capture test with hard refresh at each step."""
    global captured_requests, captured_responses
    captured_requests = []
    captured_responses = []

    print("\n" + "="*70)
    print("NETWORK CAPTURE E2E TEST WITH HARD REFRESH")
    print("="*70)
    print(f"URL: {STAGING_URL}")
    print(f"Headless: {HEADLESS}")

    today = datetime.now().date()
    dropoff_date = today + timedelta(days=21)
    pickup_date = dropoff_date + timedelta(days=7)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # Set up network listeners
        page.on("request", log_request)
        page.on("response", log_response)

        try:
            # ============ INITIAL LOAD ============
            print("\n" + "-"*70)
            print("STEP 0: Initial page load")
            print("-"*70)
            page.goto(STAGING_URL, wait_until="networkidle")
            time.sleep(3)
            close_welcome_modal(page)
            dump_session_storage(page, "Initial Load")

            # ============ STEP 1: ENTER FLIGHT DETAILS ============
            print("\n" + "-"*70)
            print("STEP 1: Enter flight details")
            print("-"*70)

            fill_step1(page, dropoff_date, pickup_date, FLIGHT_DATA)
            dump_session_storage(page, "After Entering Flight Details")

            # Click Continue to Package Selection
            btn = page.locator("button:has-text('Continue to Package Selection')")
            if btn.is_visible(timeout=5000):
                btn.click()
                time.sleep(3)

            # ============ HARD REFRESH ON PACKAGE SELECTION ============
            print("\n" + "-"*70)
            print(">>> HARD REFRESH on Package Selection page <<<")
            print("-"*70)
            hard_refresh(page)
            close_welcome_modal(page)
            dump_session_storage(page, "After Hard Refresh (Package Selection)")

            # ============ STEP 2: SELECT PACKAGE ============
            print("\n" + "-"*70)
            print("STEP 2: Select package (continue to details)")
            print("-"*70)
            time.sleep(2)

            # Click Continue to Your Details
            btn = page.locator("button:has-text('Continue to Your Details')")
            if btn.is_visible(timeout=5000):
                btn.click()
                time.sleep(3)

            # ============ HARD REFRESH ON CONTACT/BILLING/VEHICLE ============
            print("\n" + "-"*70)
            print(">>> HARD REFRESH on Contact/Billing/Vehicle page <<<")
            print("-"*70)
            hard_refresh(page)
            close_welcome_modal(page)
            dump_session_storage(page, "After Hard Refresh (Contact/Billing/Vehicle)")

            # ============ STEP 3: ENTER CONTACT/BILLING/VEHICLE ============
            print("\n" + "-"*70)
            print("STEP 3: Enter contact/billing/vehicle details")
            print("-"*70)

            fill_step3(page, CUSTOMER, VEHICLE)
            dump_session_storage(page, "After Entering Contact/Billing/Vehicle")

            # Click Continue to Payment
            btn = page.locator("button:has-text('Continue to Payment')")
            if btn.is_visible(timeout=5000):
                btn.click()
                time.sleep(3)

            # ============ HARD REFRESH ON PAYMENT PAGE ============
            print("\n" + "-"*70)
            print(">>> HARD REFRESH on Payment page <<<")
            print("-"*70)
            hard_refresh(page)
            close_welcome_modal(page)
            dump_session_storage(page, "After Hard Refresh (Payment Page)")

            # ============ STEP 4: CHECK T&Cs AND ENTER PAYMENT INFO ============
            print("\n" + "-"*70)
            print("STEP 4: Check T&Cs and enter payment info")
            print("-"*70)

            # Accept terms
            print("    Accepting T&Cs...")
            time.sleep(1)
            try:
                terms_input = page.locator("input[name='terms']")
                if not terms_input.is_checked():
                    page.evaluate("document.querySelector('input[name=\"terms\"]').click()")
                    time.sleep(0.5)
            except Exception as e:
                print(f"    Warning: {e}")

            time.sleep(2)

            # Wait for Stripe
            print("    Waiting for Stripe...")
            time.sleep(3)

            # Dismiss Link popup
            for _ in range(3):
                page.keyboard.press("Escape")
                time.sleep(0.3)

            # Fill card details
            print("    Filling card details...")
            try:
                stripe_frame = page.frame_locator("iframe[name*='__privateStripeFrame']").first

                card_input = stripe_frame.locator("input[name='number']")
                if card_input.is_visible(timeout=5000):
                    card_input.fill(STRIPE_TEST_CARD["number"])
                    time.sleep(0.5)

                expiry_input = stripe_frame.locator("input[name='expiry']")
                if expiry_input.is_visible(timeout=2000):
                    expiry_input.fill(STRIPE_TEST_CARD["expiry"])
                    time.sleep(0.5)

                cvc_input = stripe_frame.locator("input[name='cvc']")
                if cvc_input.is_visible(timeout=2000):
                    cvc_input.fill(STRIPE_TEST_CARD["cvc"])
                    time.sleep(0.5)

            except Exception as e:
                print(f"    Stripe iframe error: {e}")

            dump_session_storage(page, "After Entering Payment Info (before hard refresh)")

            # ============ HARD REFRESH AFTER ENTERING PAYMENT INFO ============
            print("\n" + "-"*70)
            print(">>> HARD REFRESH after entering payment info <<<")
            print("-"*70)
            hard_refresh(page)
            close_welcome_modal(page)
            dump_session_storage(page, "After Hard Refresh (Payment Info Entered)")

            # Re-accept terms and re-fill card if needed
            time.sleep(2)
            print("    Re-checking T&Cs after refresh...")
            try:
                terms_input = page.locator("input[name='terms']")
                if not terms_input.is_checked():
                    page.evaluate("document.querySelector('input[name=\"terms\"]').click()")
                    time.sleep(0.5)
            except:
                pass

            time.sleep(2)

            # Dismiss Link popup again
            for _ in range(3):
                page.keyboard.press("Escape")
                time.sleep(0.3)

            # Re-fill card details
            print("    Re-filling card details after refresh...")
            try:
                stripe_frame = page.frame_locator("iframe[name*='__privateStripeFrame']").first

                card_input = stripe_frame.locator("input[name='number']")
                if card_input.is_visible(timeout=5000):
                    card_input.fill(STRIPE_TEST_CARD["number"])
                    time.sleep(0.5)

                expiry_input = stripe_frame.locator("input[name='expiry']")
                if expiry_input.is_visible(timeout=2000):
                    expiry_input.fill(STRIPE_TEST_CARD["expiry"])
                    time.sleep(0.5)

                cvc_input = stripe_frame.locator("input[name='cvc']")
                if cvc_input.is_visible(timeout=2000):
                    cvc_input.fill(STRIPE_TEST_CARD["cvc"])
                    time.sleep(0.5)
            except Exception as e:
                print(f"    Re-fill error: {e}")

            # ============ COMPLETE PAYMENT ============
            print("\n" + "-"*70)
            print("STEP 5: Complete payment")
            print("-"*70)

            # Click Pay
            print("    Clicking Pay button...")
            time.sleep(1)
            pay_button = page.locator(".stripe-pay-btn, button:has-text('Pay')")
            if pay_button.is_visible(timeout=5000):
                pay_button.click()
                time.sleep(5)

                # Check success
                success_elem = page.locator(".booking-confirmation, :has-text('Booking Confirmed'), :has-text('Payment Complete')")
                if success_elem.is_visible(timeout=30000):
                    print("    Payment successful!")
                    success = True
                else:
                    time.sleep(3)
                    if "confirmation" in page.url.lower() or page.locator(":has-text('TAG-')").is_visible(timeout=5000):
                        print("    Booking confirmed!")
                        success = True
                    else:
                        print("    Payment may not have completed")
                        success = False
            else:
                print("    Pay button not visible")
                success = False

            if success:
                print("\n" + "="*70)
                print("TEST PASSED - Booking completed successfully!")
                print("="*70)
            else:
                print("\n" + "="*70)
                print("TEST FAILED - Booking did not complete")
                print("="*70)

        except Exception as e:
            print(f"\nTEST FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            success = False

        finally:
            # Save captured network data
            print("\n" + "-"*70)
            print("SAVING NETWORK CAPTURE DATA")
            print("-"*70)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"network_capture_{timestamp}.json"

            with open(filename, "w") as f:
                json.dump({
                    "requests": captured_requests,
                    "responses": captured_responses
                }, f, indent=2, default=str)

            print(f"  Saved to: {filename}")
            print(f"  Requests captured: {len(captured_requests)}")
            print(f"  Responses captured: {len(captured_responses)}")

            # Print summary of create-intent requests
            print("\n  API REQUESTS SUMMARY:")
            for req in captured_requests:
                if "create-intent" in req["url"]:
                    print(f"\n  >>> CREATE-INTENT REQUEST <<<")
                    if req.get("post_data_json"):
                        data = req["post_data_json"]
                        print(f"    dropoff_manual_entry: {data.get('dropoff_manual_entry')}")
                        print(f"    pickup_manual_entry: {data.get('pickup_manual_entry')}")
                        print(f"    dropoff_flight_time: {data.get('dropoff_flight_time')}")
                        print(f"    pickup_flight_time: {data.get('pickup_flight_time')}")
                        print(f"    dropoff_airline_code: {data.get('dropoff_airline_code')}")
                        print(f"    pickup_airline_code: {data.get('pickup_airline_code')}")
                        print(f"    flight_number: {data.get('flight_number')}")
                        print(f"    pickup_flight_number: {data.get('pickup_flight_number')}")

            browser.close()

        return success


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
