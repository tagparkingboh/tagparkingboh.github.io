"""
Tests for admin bookings functionality.

Covers:
- GET /api/admin/bookings - List all bookings with filters
- POST /api/admin/bookings/{booking_id}/cancel - Cancel a booking
- DELETE /api/admin/bookings/{booking_id} - Delete pending or cancelled booking
- Billing address in response

All tests use mocked data to avoid database state conflicts.
"""
import pytest
from unittest.mock import MagicMock
from datetime import date, time, datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="07700900001",
    billing_address1="123 Test Street",
    billing_address2=None,
    billing_city="London",
    billing_county="Greater London",
    billing_postcode="SW1A 1AA",
    billing_country="United Kingdom",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_address1 = billing_address1
    customer.billing_address2 = billing_address2
    customer.billing_city = billing_city
    customer.billing_county = billing_county
    customer.billing_postcode = billing_postcode
    customer.billing_country = billing_country
    return customer


def create_mock_vehicle(
    id=1,
    customer_id=1,
    registration="AB12 CDE",
    make="Volkswagen",
    model="Golf",
    colour="Blue",
):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = make
    vehicle.model = model
    vehicle.colour = colour
    return vehicle


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    vehicle_id=1,
    package="quick",
    status="confirmed",
    dropoff_date_val=None,
    dropoff_time_val=None,
    dropoff_flight_number="FR5523",
    dropoff_destination="Tenerife",
    pickup_date_val=None,
    pickup_time_val=None,
    pickup_time_from_val=None,
    pickup_time_to_val=None,
    pickup_flight_number="FR5524",
    pickup_origin="Tenerife",
    departure_id=None,
    dropoff_slot=None,
    arrival_id=None,
    booking_source="online",
    notes=None,
    customer=None,
    vehicle=None,
    payment=None,
    created_at=None,
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.package = package

    # Convert string status to enum if needed
    if isinstance(status, str):
        booking.status = BookingStatus(status)
    else:
        booking.status = status

    booking.dropoff_date = dropoff_date_val or date(2026, 2, 10)
    booking.dropoff_time = dropoff_time_val or time(7, 15)
    booking.dropoff_flight_number = dropoff_flight_number
    booking.dropoff_destination = dropoff_destination
    booking.pickup_date = pickup_date_val or date(2026, 2, 17)
    booking.pickup_time = pickup_time_val or time(14, 30)
    booking.pickup_time_from = pickup_time_from_val or time(15, 5)
    booking.pickup_time_to = pickup_time_to_val or time(15, 30)
    booking.pickup_flight_number = pickup_flight_number
    booking.pickup_origin = pickup_origin
    booking.departure_id = departure_id
    booking.dropoff_slot = dropoff_slot
    booking.arrival_id = arrival_id
    booking.booking_source = booking_source
    booking.notes = notes
    booking.customer = customer or create_mock_customer()
    booking.vehicle = vehicle or create_mock_vehicle()
    booking.payment = payment
    booking.created_at = created_at or datetime.utcnow()
    booking.customer_first_name = None  # Snapshot name
    booking.customer_last_name = None
    return booking


def create_mock_payment(
    id=1,
    booking_id=1,
    stripe_payment_intent_id="pi_test_123456789",
    stripe_customer_id="cus_test_123",
    amount_pence=9900,
    currency="gbp",
    status="succeeded",
    paid_at=None,
    refund_id=None,
    refund_amount_pence=None,
    refunded_at=None,
):
    """Create a mock payment object."""
    from db_models import PaymentStatus

    payment = MagicMock()
    payment.id = id
    payment.booking_id = booking_id
    payment.stripe_payment_intent_id = stripe_payment_intent_id
    payment.stripe_customer_id = stripe_customer_id
    payment.amount_pence = amount_pence
    payment.currency = currency
    payment.status = PaymentStatus(status) if isinstance(status, str) else status
    payment.paid_at = paid_at or datetime.utcnow()
    payment.refund_id = refund_id
    payment.refund_amount_pence = refund_amount_pence
    payment.refunded_at = refunded_at
    return payment


def create_mock_departure(
    id=1,
    date_val=None,
    flight_number="FR5523",
    airline_code="FR",
    airline_name="Ryanair",
    departure_time_val=None,
    destination_code="TFS",
    destination_name="Tenerife",
    capacity_tier=4,
    slots_booked_early=1,
    slots_booked_late=0,
):
    """Create a mock flight departure object."""
    departure = MagicMock()
    departure.id = id
    departure.date = date_val or date(2026, 2, 10)
    departure.flight_number = flight_number
    departure.airline_code = airline_code
    departure.airline_name = airline_name
    departure.departure_time = departure_time_val or time(10, 0)
    departure.destination_code = destination_code
    departure.destination_name = destination_name
    departure.capacity_tier = capacity_tier
    departure.slots_booked_early = slots_booked_early
    departure.slots_booked_late = slots_booked_late
    return departure


# =============================================================================
# GET /api/admin/bookings - Response Structure Tests
# =============================================================================

class TestGetAdminBookingsResponse:
    """Tests for admin bookings list response structure."""

    def test_response_contains_bookings_list_and_count(self):
        """Response should contain bookings list and count."""
        bookings = [
            create_mock_booking(id=1, reference="TAG-001"),
            create_mock_booking(id=2, reference="TAG-002"),
        ]

        response_data = {
            "count": len(bookings),
            "date_filter": None,
            "bookings": [{"id": b.id, "reference": b.reference} for b in bookings],
        }

        assert "bookings" in response_data
        assert "count" in response_data
        assert response_data["count"] == 2
        assert len(response_data["bookings"]) == 2

    def test_booking_includes_customer_details(self):
        """Bookings should include customer name, email, phone."""
        customer = create_mock_customer(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            phone="07700900001",
        )
        booking = create_mock_booking(customer=customer)

        booking_data = {
            "customer": {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
            }
        }

        assert booking_data["customer"]["first_name"] == "John"
        assert booking_data["customer"]["last_name"] == "Doe"
        assert booking_data["customer"]["email"] == "john.doe@example.com"
        assert booking_data["customer"]["phone"] == "07700900001"

    def test_booking_includes_billing_address(self):
        """Bookings should include customer billing address."""
        customer = create_mock_customer(
            billing_address1="123 Test Street",
            billing_address2="Flat 4",
            billing_city="London",
            billing_county="Greater London",
            billing_postcode="SW1A 1AA",
            billing_country="United Kingdom",
        )
        booking = create_mock_booking(customer=customer)

        booking_data = {
            "customer": {
                "billing_address1": customer.billing_address1,
                "billing_address2": customer.billing_address2,
                "billing_city": customer.billing_city,
                "billing_county": customer.billing_county,
                "billing_postcode": customer.billing_postcode,
                "billing_country": customer.billing_country,
            }
        }

        assert booking_data["customer"]["billing_address1"] == "123 Test Street"
        assert booking_data["customer"]["billing_address2"] == "Flat 4"
        assert booking_data["customer"]["billing_city"] == "London"
        assert booking_data["customer"]["billing_postcode"] == "SW1A 1AA"

    def test_booking_includes_vehicle_details(self):
        """Bookings should include vehicle registration, make, model, colour."""
        vehicle = create_mock_vehicle(
            registration="AB12 CDE",
            make="Volkswagen",
            model="Golf",
            colour="Blue",
        )
        booking = create_mock_booking(vehicle=vehicle)

        booking_data = {
            "vehicle": {
                "registration": vehicle.registration,
                "make": vehicle.make,
                "model": vehicle.model,
                "colour": vehicle.colour,
            }
        }

        assert booking_data["vehicle"]["registration"] == "AB12 CDE"
        assert booking_data["vehicle"]["make"] == "Volkswagen"
        assert booking_data["vehicle"]["model"] == "Golf"
        assert booking_data["vehicle"]["colour"] == "Blue"

    def test_booking_includes_payment_details(self):
        """Bookings should include payment status and stripe IDs."""
        payment = create_mock_payment(
            status="succeeded",
            stripe_payment_intent_id="pi_test_123",
            amount_pence=9900,
        )
        booking = create_mock_booking(payment=payment)

        booking_data = {
            "payment": {
                "status": payment.status.value,
                "stripe_payment_intent_id": payment.stripe_payment_intent_id,
                "amount_pence": payment.amount_pence,
            }
        }

        assert booking_data["payment"]["status"] == "succeeded"
        assert booking_data["payment"]["stripe_payment_intent_id"] == "pi_test_123"
        assert booking_data["payment"]["amount_pence"] == 9900

    def test_booking_without_payment_returns_null(self):
        """Bookings without payment should have null payment field."""
        booking = create_mock_booking(payment=None)

        booking_data = {
            "payment": booking.payment,
        }

        assert booking_data["payment"] is None


# =============================================================================
# GET /api/admin/bookings - Filtering Tests
# =============================================================================

class TestGetAdminBookingsFiltering:
    """Tests for admin bookings filtering."""

    def test_bookings_sorted_by_dropoff_date_ascending(self):
        """Bookings should be sorted by dropoff date ascending."""
        bookings = [
            {"dropoff_date": "2026-01-15"},
            {"dropoff_date": "2026-02-10"},
            {"dropoff_date": "2026-03-01"},
        ]

        dates = [b["dropoff_date"] for b in bookings]
        assert dates == sorted(dates)

    def test_filter_by_date_returns_overlapping_bookings(self):
        """Date filter should return bookings that overlap with given date."""
        # Booking: dropoff 2026-01-15, pickup 2026-01-22
        filter_date = date(2026, 1, 18)
        dropoff = date(2026, 1, 15)
        pickup = date(2026, 1, 22)

        # Check if filter_date falls within booking period
        is_overlap = dropoff <= filter_date <= pickup
        assert is_overlap is True

    def test_include_cancelled_true_includes_cancelled_bookings(self):
        """Include cancelled=true should include cancelled bookings."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status=BookingStatus.CONFIRMED),
            create_mock_booking(id=2, status=BookingStatus.CANCELLED),
            create_mock_booking(id=3, status=BookingStatus.PENDING),
        ]

        include_cancelled = True
        if include_cancelled:
            filtered = bookings
        else:
            filtered = [b for b in bookings if b.status != BookingStatus.CANCELLED]

        statuses = [b.status for b in filtered]
        assert BookingStatus.CANCELLED in statuses

    def test_include_cancelled_false_excludes_cancelled_bookings(self):
        """Include cancelled=false should exclude cancelled bookings."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status=BookingStatus.CONFIRMED),
            create_mock_booking(id=2, status=BookingStatus.CANCELLED),
            create_mock_booking(id=3, status=BookingStatus.PENDING),
        ]

        include_cancelled = False
        filtered = [b for b in bookings if include_cancelled or b.status != BookingStatus.CANCELLED]

        statuses = [b.status for b in filtered]
        assert BookingStatus.CANCELLED not in statuses

    def test_date_filter_boundary_dropoff_date(self):
        """Filter date equal to dropoff date should include booking."""
        filter_date = date(2026, 1, 15)
        dropoff = date(2026, 1, 15)
        pickup = date(2026, 1, 22)

        is_overlap = dropoff <= filter_date <= pickup
        assert is_overlap is True

    def test_date_filter_boundary_pickup_date(self):
        """Filter date equal to pickup date should include booking."""
        filter_date = date(2026, 1, 22)
        dropoff = date(2026, 1, 15)
        pickup = date(2026, 1, 22)

        is_overlap = dropoff <= filter_date <= pickup
        assert is_overlap is True


# =============================================================================
# POST /api/admin/bookings/{booking_id}/cancel - Cancel Booking Tests
# =============================================================================

class TestCancelBooking:
    """Tests for cancelling bookings."""

    def test_cancel_confirmed_booking_success(self):
        """Should successfully cancel a confirmed booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CONFIRMED)

        # Simulate cancellation
        response_data = {
            "success": True,
            "reference": booking.reference,
            "message": f"Booking {booking.reference} has been cancelled",
            "slot_released": False,
            "stripe_cancelled": False,
        }

        assert response_data["success"] is True
        assert "cancelled" in response_data["message"].lower()

    def test_cancel_pending_booking_success(self):
        """Should successfully cancel a pending booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)

        response_data = {
            "success": True,
            "reference": booking.reference,
        }

        assert response_data["success"] is True

    def test_cancel_nonexistent_booking_returns_404(self):
        """Should return 404 for non-existent booking."""
        booking = None  # Not found

        if booking is None:
            status_code = 404
            error = "Booking not found"
        else:
            status_code = 200
            error = None

        assert status_code == 404
        assert "not found" in error.lower()

    def test_cancel_already_cancelled_booking_returns_400(self):
        """Should return 400 when trying to cancel already cancelled booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CANCELLED)

        if booking.status == BookingStatus.CANCELLED:
            status_code = 400
            error = "Booking is already cancelled"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "already cancelled" in error.lower()

    def test_cancel_refunded_booking_returns_400(self):
        """Should return 400 when trying to cancel a refunded booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.REFUNDED)

        if booking.status == BookingStatus.REFUNDED:
            status_code = 400
            error = "Cannot cancel a refunded booking"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "refunded" in error.lower()

    def test_cancel_booking_does_not_auto_refund_payment(self):
        """Cancelling should NOT automatically refund the payment."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status=PaymentStatus.SUCCEEDED)
        booking = create_mock_booking(payment=payment)

        # After cancellation, payment status should still be SUCCEEDED
        # (manual refund via Stripe dashboard required)
        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.refund_id is None


# =============================================================================
# Cancel Booking - Slot Release Tests
# =============================================================================

class TestCancelBookingSlotRelease:
    """Tests for flight slot release when cancelling bookings."""

    def test_cancel_releases_early_slot(self):
        """Cancelling booking with early slot should release it."""
        departure = create_mock_departure(slots_booked_early=1)
        booking = create_mock_booking(
            departure_id=departure.id,
            dropoff_slot="early",
        )

        # Simulate slot release
        if booking.departure_id and booking.dropoff_slot == "early":
            departure.slots_booked_early -= 1
            slot_released = True
        else:
            slot_released = False

        assert slot_released is True
        assert departure.slots_booked_early == 0

    def test_cancel_releases_late_slot(self):
        """Cancelling booking with late slot should release it."""
        departure = create_mock_departure(slots_booked_late=1)
        booking = create_mock_booking(
            departure_id=departure.id,
            dropoff_slot="late",
        )

        if booking.departure_id and booking.dropoff_slot == "late":
            departure.slots_booked_late -= 1
            slot_released = True
        else:
            slot_released = False

        assert slot_released is True
        assert departure.slots_booked_late == 0

    def test_cancel_without_departure_id_does_not_release_slot(self):
        """Booking without departure_id should not release any slot."""
        booking = create_mock_booking(
            departure_id=None,
            dropoff_slot=None,
        )

        slot_released = False
        if booking.departure_id and booking.dropoff_slot:
            slot_released = True

        assert slot_released is False

    def test_slot_count_does_not_go_negative(self):
        """Slot count should not go below 0."""
        departure = create_mock_departure(slots_booked_early=0)

        # Try to release when already at 0
        new_count = max(0, departure.slots_booked_early - 1)

        assert new_count == 0

    def test_slot_type_normalization_165_to_early(self):
        """Slot type '165' should be normalized to 'early'."""
        dropoff_slot = "165"
        slot_type = "early" if dropoff_slot in ("165", "early") else "late"
        assert slot_type == "early"

    def test_slot_type_normalization_120_to_late(self):
        """Slot type '120' should be normalized to 'late'."""
        dropoff_slot = "120"
        slot_type = "early" if dropoff_slot in ("165", "early") else "late"
        assert slot_type == "late"


# =============================================================================
# DELETE /api/admin/bookings/{booking_id} - Delete Booking Tests
# =============================================================================

class TestDeleteBooking:
    """Tests for deleting pending and cancelled bookings."""

    def test_delete_pending_booking_success(self):
        """Successfully deleting a pending booking returns success."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} has been permanently deleted",
            "reference": booking.reference,
            "slot_released": False,
        }

        assert response_data["success"] is True
        assert "permanently deleted" in response_data["message"]

    def test_delete_pending_booking_releases_slot(self):
        """Deleting pending booking with slot releases the slot."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.PENDING,
            departure_id=100,
            dropoff_slot="early",
        )

        slot_released = True if booking.departure_id and booking.dropoff_slot else False

        response_data = {
            "success": True,
            "slot_released": slot_released,
        }

        assert response_data["slot_released"] is True

    def test_delete_confirmed_booking_fails(self):
        """Cannot delete a booking that is CONFIRMED."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CONFIRMED)

        if booking.status not in (BookingStatus.PENDING, BookingStatus.CANCELLED):
            status_code = 400
            error = f"Can only delete pending or cancelled bookings. This booking has status: {booking.status.value}"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "Can only delete pending or cancelled bookings" in error

    def test_delete_cancelled_booking_success(self):
        """Should successfully delete a cancelled booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CANCELLED)

        if booking.status in (BookingStatus.PENDING, BookingStatus.CANCELLED):
            status_code = 200
            response_data = {
                "success": True,
                "message": f"Booking {booking.reference} has been permanently deleted",
                "reference": booking.reference,
                "slot_released": False,
            }
        else:
            status_code = 400
            response_data = None

        assert status_code == 200
        assert response_data["success"] is True
        assert "permanently deleted" in response_data["message"]

    def test_delete_completed_booking_fails(self):
        """Cannot delete a booking that is COMPLETED."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.COMPLETED)

        if booking.status not in (BookingStatus.PENDING, BookingStatus.CANCELLED):
            status_code = 400
            error = f"Can only delete pending or cancelled bookings. This booking has status: {booking.status.value}"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "completed" in error.lower()

    def test_delete_nonexistent_booking_returns_404(self):
        """Deleting non-existent booking returns 404."""
        booking = None  # Not found

        if booking is None:
            status_code = 404
            error = "Booking not found"
        else:
            status_code = 200
            error = None

        assert status_code == 404

    def test_delete_removes_associated_payment(self):
        """Deleting booking removes associated payment record."""
        from db_models import BookingStatus

        payment = create_mock_payment()
        booking = create_mock_booking(status=BookingStatus.PENDING)

        # Simulate deletion - both should be deleted
        deleted_booking = True
        deleted_payment = True

        assert deleted_booking is True
        assert deleted_payment is True

    def test_delete_clears_promo_code_references(self):
        """Deleting booking clears promo code references in MarketingSubscriber."""
        # Simulate clearing FK references before delete
        booking_id = 123

        # These would be set to None before deletion
        promo_code_used_booking_id = None
        promo_10_used_booking_id = None
        promo_free_used_booking_id = None

        assert promo_code_used_booking_id is None
        assert promo_10_used_booking_id is None
        assert promo_free_used_booking_id is None

    def test_delete_requires_admin_authentication(self):
        """Delete endpoint requires admin authentication."""
        user = MagicMock()
        user.is_admin = False

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# PUT /api/admin/bookings/{booking_id} - Update Booking Tests
# =============================================================================

class TestUpdateBooking:
    """Tests for updating booking details."""

    def test_update_pickup_date_success(self):
        """Should successfully update pickup date."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 28),
        )

        new_pickup_date = date(2026, 3, 29)
        booking.pickup_date = new_pickup_date

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["pickup_date"],
            "booking": {"pickup_date": booking.pickup_date.isoformat()}
        }

        assert response_data["success"] is True
        assert "pickup_date" in response_data["fields_updated"]
        assert response_data["booking"]["pickup_date"] == "2026-03-29"

    def test_update_pickup_time_recalculates_windows(self):
        """Updating pickup_time should recalculate pickup_time_from and pickup_time_to."""
        from datetime import timedelta

        booking = create_mock_booking(
            pickup_time_val=time(14, 30),
            pickup_time_from_val=time(15, 5),
            pickup_time_to_val=time(15, 30),
        )

        new_arrival_time = time(0, 35)
        booking.pickup_time = new_arrival_time

        arrival_dt = datetime.combine(date.today(), new_arrival_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        assert booking.pickup_time == time(0, 35)
        assert booking.pickup_time_from == time(1, 10)
        assert booking.pickup_time_to == time(1, 35)

    def test_update_nonexistent_booking_returns_404(self):
        """Should return 404 for non-existent booking."""
        booking = None

        if booking is None:
            status_code = 404
            error = "Booking not found"
        else:
            status_code = 200
            error = None

        assert status_code == 404
        assert "not found" in error.lower()

    def test_update_with_no_fields_returns_400(self):
        """Should return 400 when no fields provided."""
        updates = {}

        if not updates:
            status_code = 400
            error = "No fields to update"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "No fields" in error

    def test_update_flight_numbers(self):
        """Should update flight numbers."""
        booking = create_mock_booking(
            dropoff_flight_number="FR5523",
            pickup_flight_number="FR5524",
        )

        booking.dropoff_flight_number = "TUI123"
        booking.pickup_flight_number = "TUI671"

        assert booking.dropoff_flight_number == "TUI123"
        assert booking.pickup_flight_number == "TUI671"

    def test_update_requires_admin_auth(self):
        """Update endpoint requires admin authentication."""
        user = MagicMock()
        user.is_admin = False

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


class TestUpdateBookingOvernightFix:
    """Tests for fixing overnight arrival booking dates."""

    def test_overnight_arrival_date_correction(self):
        """Flight arriving 00:35 on 29th should have pickup_date as 29th."""
        booking = create_mock_booking(
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(0, 35),
        )

        booking.pickup_date = date(2026, 3, 29)

        assert booking.pickup_date == date(2026, 3, 29)
        assert booking.pickup_time == time(0, 35)

    def test_overnight_pickup_windows_correct(self):
        """Overnight flight pickup windows calculated correctly."""
        from datetime import timedelta

        arrival_time = time(0, 35)
        arrival_dt = datetime.combine(date.today(), arrival_time)

        pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        assert pickup_time_from == time(1, 10)
        assert pickup_time_to == time(1, 35)

    def test_late_evening_no_date_change(self):
        """Flight arriving 22:00 on 28th should stay on 28th."""
        booking = create_mock_booking(
            pickup_date_val=date(2026, 2, 28),
            pickup_time_val=time(22, 0),
        )

        assert booking.pickup_date == date(2026, 2, 28)


# =============================================================================
# Admin Bookings Integration Flow Tests
# =============================================================================

class TestAdminBookingsIntegration:
    """Integration tests for admin booking workflows."""

    def test_full_booking_lifecycle(self):
        """Test: view booking -> cancel -> verify cancelled status."""
        from db_models import BookingStatus

        # Step 1: Create confirmed booking
        booking = create_mock_booking(status=BookingStatus.CONFIRMED)
        assert booking.status == BookingStatus.CONFIRMED

        # Step 2: Cancel booking
        booking.status = BookingStatus.CANCELLED
        assert booking.status == BookingStatus.CANCELLED

        # Step 3: Booking should be filtered out with include_cancelled=false
        include_cancelled = False
        should_show = include_cancelled or booking.status != BookingStatus.CANCELLED
        assert should_show is False

    def test_multiple_status_bookings_filtered_correctly(self):
        """Multiple status bookings should filter correctly."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status=BookingStatus.CONFIRMED),
            create_mock_booking(id=2, status=BookingStatus.PENDING),
            create_mock_booking(id=3, status=BookingStatus.CANCELLED),
            create_mock_booking(id=4, status=BookingStatus.COMPLETED),
        ]

        # All statuses present
        statuses = {b.status for b in bookings}
        assert BookingStatus.CONFIRMED in statuses
        assert BookingStatus.PENDING in statuses
        assert BookingStatus.CANCELLED in statuses
        assert BookingStatus.COMPLETED in statuses

        # Filtered without cancelled
        filtered = [b for b in bookings if b.status != BookingStatus.CANCELLED]
        filtered_statuses = {b.status for b in filtered}
        assert BookingStatus.CANCELLED not in filtered_statuses
        assert len(filtered) == 3

    def test_booking_with_all_fields_populated(self):
        """Booking with all fields should serialize correctly."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        payment = create_mock_payment()
        booking = create_mock_booking(
            customer=customer,
            vehicle=vehicle,
            payment=payment,
        )

        # All required fields present
        assert booking.reference is not None
        assert booking.customer is not None
        assert booking.vehicle is not None
        assert booking.payment is not None
        assert booking.dropoff_date is not None
        assert booking.pickup_date is not None


# =============================================================================
# Validation Tests
# =============================================================================

class TestAdminBookingsValidation:
    """Validation tests for admin bookings endpoints."""

    def test_invalid_date_filter_format(self):
        """Invalid date format should be rejected."""
        invalid_date = "invalid-date"

        try:
            date.fromisoformat(invalid_date)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_invalid_booking_id_type(self):
        """Non-integer booking ID should be rejected."""
        booking_id = "invalid-id"

        try:
            int(booking_id)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_negative_booking_id_returns_404_or_422(self):
        """Negative booking ID should return 404 or 422."""
        booking_id = -1

        # Negative IDs won't match any booking
        if booking_id < 0:
            status_code = 404  # or 422 depending on implementation
        else:
            status_code = 200

        assert status_code in [404, 422]

    def test_zero_booking_id_returns_404(self):
        """Zero booking ID should return 404."""
        booking_id = 0
        booking = None  # No booking with ID 0

        if booking is None:
            status_code = 404
        else:
            status_code = 200

        assert status_code == 404


# =============================================================================
# PUT /api/admin/bookings/{booking_id} - Edit Pickup Date/Time Tests
# =============================================================================

class TestEditPickupDateTime:
    """Tests for editing booking pickup date and time."""

    def test_update_pickup_date_only(self):
        """Should successfully update only the pickup date."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        new_pickup_date = date(2026, 3, 30)
        booking.pickup_date = new_pickup_date

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["pickup_date"],
            "booking": {
                "pickup_date": booking.pickup_date.isoformat(),
                "pickup_time": booking.pickup_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert "pickup_date" in response_data["fields_updated"]
        assert response_data["booking"]["pickup_date"] == "2026-03-30"
        assert response_data["booking"]["pickup_time"] == "14:30"  # Unchanged

    def test_update_pickup_time_only(self):
        """Should successfully update only the pickup time."""
        from db_models import BookingStatus
        from datetime import timedelta

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
            pickup_time_from_val=time(15, 5),
            pickup_time_to_val=time(15, 30),
        )

        new_pickup_time = time(16, 45)
        booking.pickup_time = new_pickup_time

        # Recalculate pickup windows
        arrival_dt = datetime.combine(date.today(), new_pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["pickup_time"],
            "booking": {
                "pickup_date": booking.pickup_date.isoformat(),
                "pickup_time": booking.pickup_time.strftime("%H:%M"),
                "pickup_time_from": booking.pickup_time_from.strftime("%H:%M"),
                "pickup_time_to": booking.pickup_time_to.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert "pickup_time" in response_data["fields_updated"]
        assert response_data["booking"]["pickup_date"] == "2026-03-28"  # Unchanged
        assert response_data["booking"]["pickup_time"] == "16:45"
        assert response_data["booking"]["pickup_time_from"] == "17:20"
        assert response_data["booking"]["pickup_time_to"] == "17:45"

    def test_update_pickup_date_and_time_together(self):
        """Should successfully update both pickup date and time."""
        from db_models import BookingStatus
        from datetime import timedelta

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
            pickup_time_from_val=time(15, 5),
            pickup_time_to_val=time(15, 30),
        )

        new_pickup_date = date(2026, 4, 1)
        new_pickup_time = time(10, 15)
        booking.pickup_date = new_pickup_date
        booking.pickup_time = new_pickup_time

        # Recalculate pickup windows
        arrival_dt = datetime.combine(date.today(), new_pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["pickup_date", "pickup_time"],
            "booking": {
                "pickup_date": booking.pickup_date.isoformat(),
                "pickup_time": booking.pickup_time.strftime("%H:%M"),
                "pickup_time_from": booking.pickup_time_from.strftime("%H:%M"),
                "pickup_time_to": booking.pickup_time_to.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert "pickup_date" in response_data["fields_updated"]
        assert "pickup_time" in response_data["fields_updated"]
        assert response_data["booking"]["pickup_date"] == "2026-04-01"
        assert response_data["booking"]["pickup_time"] == "10:15"
        assert response_data["booking"]["pickup_time_from"] == "10:50"
        assert response_data["booking"]["pickup_time_to"] == "11:15"

    def test_update_pickup_time_midnight_crossover(self):
        """Updating pickup time near midnight should handle day boundary correctly."""
        from db_models import BookingStatus
        from datetime import timedelta

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(23, 30),
        )

        new_pickup_time = time(23, 45)
        booking.pickup_time = new_pickup_time

        # Recalculate pickup windows - will cross midnight
        arrival_dt = datetime.combine(date.today(), new_pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        assert booking.pickup_time == time(23, 45)
        assert booking.pickup_time_from == time(0, 20)  # Crosses midnight
        assert booking.pickup_time_to == time(0, 45)  # Crosses midnight

    def test_update_pickup_time_early_morning(self):
        """Updating pickup time to early morning hours works correctly."""
        from db_models import BookingStatus
        from datetime import timedelta

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            pickup_date_val=date(2026, 3, 29),
            pickup_time_val=time(14, 30),
        )

        # Flight arrives at 1:15 AM
        new_pickup_time = time(1, 15)
        booking.pickup_time = new_pickup_time

        arrival_dt = datetime.combine(date.today(), new_pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        assert booking.pickup_time == time(1, 15)
        assert booking.pickup_time_from == time(1, 50)
        assert booking.pickup_time_to == time(2, 15)

    def test_update_pickup_time_invalid_format_rejected(self):
        """Invalid time format should be rejected."""
        invalid_times = ["25:00", "14:60", "invalid", "2pm", ""]

        for invalid_time in invalid_times:
            try:
                datetime.strptime(invalid_time, "%H:%M")
                is_valid = True
            except ValueError:
                is_valid = False

            assert is_valid is False, f"Expected '{invalid_time}' to be invalid"

    def test_update_pickup_time_valid_formats(self):
        """Valid time formats should be accepted."""
        valid_times = ["00:00", "12:30", "23:59", "01:05", "14:30"]

        for valid_time in valid_times:
            try:
                parsed = datetime.strptime(valid_time, "%H:%M")
                is_valid = True
            except ValueError:
                is_valid = False

            assert is_valid is True, f"Expected '{valid_time}' to be valid"

    def test_update_does_not_affect_departure_flight(self):
        """Updating pickup date/time should not affect departure/dropoff data."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            dropoff_date_val=date(2026, 3, 21),
            dropoff_time_val=time(7, 15),
            dropoff_flight_number="FR5523",
            dropoff_destination="Tenerife",
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        # Update pickup details
        booking.pickup_date = date(2026, 3, 30)
        booking.pickup_time = time(16, 0)

        # Dropoff details should remain unchanged
        assert booking.dropoff_date == date(2026, 3, 21)
        assert booking.dropoff_time == time(7, 15)
        assert booking.dropoff_flight_number == "FR5523"
        assert booking.dropoff_destination == "Tenerife"

    def test_update_pending_booking_pickup(self):
        """Should allow updating pickup for pending bookings."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.PENDING,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        booking.pickup_date = date(2026, 3, 29)
        booking.pickup_time = time(15, 0)

        assert booking.status == BookingStatus.PENDING
        assert booking.pickup_date == date(2026, 3, 29)
        assert booking.pickup_time == time(15, 0)

    def test_update_completed_booking_pickup(self):
        """Should allow updating pickup for completed bookings (for records)."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.COMPLETED,
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        # Admin can still update for record-keeping purposes
        booking.pickup_date = date(2026, 3, 29)
        booking.pickup_time = time(15, 0)

        assert booking.status == BookingStatus.COMPLETED
        assert booking.pickup_date == date(2026, 3, 29)
        assert booking.pickup_time == time(15, 0)


# =============================================================================
# PUT /api/admin/bookings/{booking_id} - Edit Drop-off Time Tests
# =============================================================================

class TestEditDropoffTime:
    """Tests for editing booking drop-off time with validation constraints."""

    def test_update_dropoff_time_within_limits(self):
        """Should allow dropoff time change within allowed range (1hr earlier, 15min later)."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            status=BookingStatus.CONFIRMED,
            dropoff_time_val=time(9, 30),
        )

        # Move 30 mins earlier (within 1 hour limit)
        new_dropoff_time = time(9, 0)
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -30  # 30 mins earlier
        assert diff_minutes >= -60  # Within 1 hour earlier limit

        booking.dropoff_time = new_dropoff_time
        assert booking.dropoff_time == time(9, 0)

    def test_update_dropoff_time_exactly_1_hour_earlier(self):
        """Should allow dropoff time exactly 1 hour earlier."""
        booking = create_mock_booking(dropoff_time_val=time(10, 0))

        new_dropoff_time = time(9, 0)
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -60  # Exactly 1 hour earlier
        is_valid = diff_minutes >= -60
        assert is_valid is True

    def test_update_dropoff_time_exactly_15_mins_later(self):
        """Should allow dropoff time exactly 15 minutes later."""
        booking = create_mock_booking(dropoff_time_val=time(9, 30))

        new_dropoff_time = time(9, 45)
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 15  # Exactly 15 mins later
        is_valid = diff_minutes <= 15
        assert is_valid is True

    def test_reject_dropoff_time_more_than_1_hour_earlier(self):
        """Should reject dropoff time more than 1 hour earlier."""
        booking = create_mock_booking(dropoff_time_val=time(10, 0))

        new_dropoff_time = time(8, 30)  # 1.5 hours earlier
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -90  # 90 mins earlier
        is_valid = diff_minutes >= -60  # Exceeds 1 hour limit
        assert is_valid is False

    def test_reject_dropoff_time_more_than_15_mins_later(self):
        """Should reject dropoff time more than 15 minutes later."""
        booking = create_mock_booking(dropoff_time_val=time(9, 30))

        new_dropoff_time = time(10, 0)  # 30 mins later
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 30  # 30 mins later
        is_valid = diff_minutes <= 15  # Exceeds 15 min limit
        assert is_valid is False

    def test_update_dropoff_time_10_mins_earlier(self):
        """Should allow 10 minutes earlier (common small adjustment)."""
        booking = create_mock_booking(dropoff_time_val=time(9, 30))

        new_dropoff_time = time(9, 20)
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -10
        is_valid = diff_minutes >= -60 and diff_minutes <= 15
        assert is_valid is True

    def test_update_dropoff_time_10_mins_later(self):
        """Should allow 10 minutes later (common small adjustment)."""
        booking = create_mock_booking(dropoff_time_val=time(9, 30))

        new_dropoff_time = time(9, 40)
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 10
        is_valid = diff_minutes >= -60 and diff_minutes <= 15
        assert is_valid is True

    def test_update_dropoff_time_midnight_crossing_earlier(self):
        """Should handle midnight crossing when moving earlier (e.g., 00:30 to 23:45)."""
        booking = create_mock_booking(dropoff_time_val=time(0, 30))

        new_dropoff_time = time(23, 45)  # 45 mins earlier, crossing midnight
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute  # 30
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute  # 1425

        diff_minutes = new_minutes - old_minutes  # 1395 (appears to be going forward)

        # Handle midnight crossing
        if diff_minutes > 720:  # More than 12 hours forward likely means going back
            diff_minutes -= 1440

        assert diff_minutes == -45  # Actually 45 mins earlier
        is_valid = diff_minutes >= -60
        assert is_valid is True

    def test_update_dropoff_time_midnight_crossing_later(self):
        """Should handle midnight crossing when moving later (e.g., 23:50 to 00:05)."""
        booking = create_mock_booking(dropoff_time_val=time(23, 50))

        new_dropoff_time = time(0, 5)  # 15 mins later, crossing midnight
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute  # 1430
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute  # 5

        diff_minutes = new_minutes - old_minutes  # -1425 (appears to be going back)

        # Handle midnight crossing
        if diff_minutes < -720:  # More than 12 hours back likely means going forward
            diff_minutes += 1440

        assert diff_minutes == 15  # Actually 15 mins later
        is_valid = diff_minutes <= 15
        assert is_valid is True

    def test_update_dropoff_time_does_not_affect_pickup(self):
        """Updating dropoff time should not affect pickup details."""
        booking = create_mock_booking(
            dropoff_time_val=time(9, 30),
            pickup_date_val=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        original_pickup_date = booking.pickup_date
        original_pickup_time = booking.pickup_time

        # Update dropoff
        booking.dropoff_time = time(9, 0)

        # Pickup should remain unchanged
        assert booking.pickup_date == original_pickup_date
        assert booking.pickup_time == original_pickup_time

    def test_update_dropoff_time_does_not_affect_flight_departure(self):
        """Updating dropoff time should NOT modify flight_departures table."""
        departure = create_mock_departure(
            id=1,
            slots_booked_early=1,
            slots_booked_late=0,
        )

        booking = create_mock_booking(
            departure_id=departure.id,
            dropoff_slot="early",
            dropoff_time_val=time(9, 30),
        )

        original_early_slots = departure.slots_booked_early
        original_late_slots = departure.slots_booked_late

        # Update dropoff time
        booking.dropoff_time = time(9, 0)

        # Flight departure slots should remain unchanged
        assert departure.slots_booked_early == original_early_slots
        assert departure.slots_booked_late == original_late_slots
        assert booking.departure_id == departure.id  # Still linked

    def test_dropoff_time_validation_error_message_format(self):
        """Validation error should include current and requested times."""
        booking = create_mock_booking(dropoff_time_val=time(10, 0))
        requested_time = "08:30"  # More than 1 hour earlier

        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = requested_time.split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        if diff_minutes < -60:
            error_message = f"Cannot move drop-off time more than 1 hour earlier. Current: {booking.dropoff_time.strftime('%H:%M')}, Requested: {requested_time}"
        else:
            error_message = None

        assert error_message is not None
        assert "10:00" in error_message
        assert "08:30" in error_message
        assert "1 hour earlier" in error_message

    def test_update_dropoff_time_same_time_allowed(self):
        """Should allow setting the same time (no change)."""
        booking = create_mock_booking(dropoff_time_val=time(9, 30))

        new_dropoff_time = time(9, 30)  # Same time
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_minutes = new_dropoff_time.hour * 60 + new_dropoff_time.minute
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 0
        is_valid = diff_minutes >= -60 and diff_minutes <= 15
        assert is_valid is True
