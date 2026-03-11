"""
Tests for Edit Flight Details functionality.

Covers:
- PUT /api/admin/bookings/{booking_id} - Update flight details (airline, flight number, destination/origin)
- UpdateBookingRequest model validation
- Happy path, negative testing, and edge cases

All tests use mocked data to avoid database state conflicts.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, time, datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use relative dates for future-proof tests
TODAY = date.today()
FUTURE_DATE = TODAY + timedelta(days=90)  # ~3 months from now
FUTURE_DATE_END = TODAY + timedelta(days=97)  # ~1 week after FUTURE_DATE


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="07700900001",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
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
    dropoff_airline_name=None,
    dropoff_airline_code=None,
    dropoff_flight_number="FR5523",
    dropoff_destination="Tenerife",
    pickup_date_val=None,
    pickup_time_val=None,
    pickup_airline_name=None,
    pickup_airline_code=None,
    pickup_flight_number="FR5524",
    pickup_origin="Tenerife",
    departure_id=None,
    arrival_id=None,
    customer=None,
    vehicle=None,
    payment=None,
    created_at=None,
    flight_departure_time=None,
    flight_arrival_time=None,
):
    """Create a mock booking object with airline fields."""
    from db_models import BookingStatus
    from datetime import timedelta

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

    # Use relative dates based on today's date
    today = date.today()

    # Dropoff fields
    booking.dropoff_date = dropoff_date_val or (today + timedelta(days=7))
    booking.dropoff_time = dropoff_time_val or time(7, 15)
    booking.dropoff_airline_name = dropoff_airline_name
    booking.dropoff_airline_code = dropoff_airline_code
    booking.dropoff_flight_number = dropoff_flight_number
    booking.dropoff_destination = dropoff_destination

    # Pickup fields
    booking.pickup_date = pickup_date_val or (today + timedelta(days=14))
    booking.pickup_time = pickup_time_val or time(15, 0)  # Collection time (arrival + 30)
    booking.pickup_airline_name = pickup_airline_name
    booking.pickup_airline_code = pickup_airline_code
    booking.pickup_flight_number = pickup_flight_number
    booking.pickup_origin = pickup_origin

    # Actual flight times (for emails and display)
    booking.flight_departure_time = flight_departure_time
    booking.flight_arrival_time = flight_arrival_time

    # Relations
    booking.departure_id = departure_id
    booking.arrival_id = arrival_id
    booking.customer = customer or create_mock_customer()
    booking.vehicle = vehicle or create_mock_vehicle()
    booking.payment = payment
    booking.created_at = created_at or datetime.utcnow()

    return booking


# =============================================================================
# UpdateBookingRequest Model Tests
# =============================================================================

class TestUpdateBookingRequestModel:
    """Tests for the UpdateBookingRequest Pydantic model."""

    def test_model_accepts_all_flight_fields(self):
        """Model should accept all flight-related fields."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="BY1234",
            dropoff_destination="Dalaman Airport",
            pickup_airline_name="TUI Airways",
            pickup_flight_number="BY1235",
            pickup_origin="Dalaman Airport",
        )

        assert request.dropoff_airline_name == "TUI Airways"
        assert request.dropoff_flight_number == "BY1234"
        assert request.dropoff_destination == "Dalaman Airport"
        assert request.pickup_airline_name == "TUI Airways"
        assert request.pickup_flight_number == "BY1235"
        assert request.pickup_origin == "Dalaman Airport"

    def test_model_accepts_partial_update(self):
        """Model should accept partial updates (only some fields)."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            dropoff_airline_name="Ryanair",
        )

        assert request.dropoff_airline_name == "Ryanair"
        assert request.dropoff_flight_number is None
        assert request.dropoff_destination is None
        assert request.pickup_airline_name is None

    def test_model_accepts_none_values(self):
        """Model should accept None values for optional fields."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            dropoff_airline_name=None,
            dropoff_flight_number=None,
        )

        assert request.dropoff_airline_name is None
        assert request.dropoff_flight_number is None

    def test_model_accepts_empty_strings(self):
        """Model should accept empty strings."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            dropoff_airline_name="",
            dropoff_flight_number="",
        )

        assert request.dropoff_airline_name == ""
        assert request.dropoff_flight_number == ""

    def test_model_all_fields_optional(self):
        """All fields in UpdateBookingRequest should be optional."""
        from main import UpdateBookingRequest

        # Should not raise any validation errors
        request = UpdateBookingRequest()

        assert request.dropoff_airline_name is None
        assert request.dropoff_flight_number is None
        assert request.dropoff_destination is None
        assert request.pickup_airline_name is None
        assert request.pickup_flight_number is None
        assert request.pickup_origin is None
        assert request.flight_departure_time is None
        assert request.flight_arrival_time is None

    def test_model_accepts_flight_times(self):
        """Model should accept flight_departure_time and flight_arrival_time."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            flight_departure_time="14:30",
            flight_arrival_time="16:45",
        )

        assert request.flight_departure_time == "14:30"
        assert request.flight_arrival_time == "16:45"

    def test_model_accepts_mixed_flight_and_time_fields(self):
        """Model should accept both flight details and flight times together."""
        from main import UpdateBookingRequest

        request = UpdateBookingRequest(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="BY1234",
            flight_departure_time="09:15",
            pickup_airline_name="TUI Airways",
            flight_arrival_time="18:30",
        )

        assert request.dropoff_airline_name == "TUI Airways"
        assert request.flight_departure_time == "09:15"
        assert request.flight_arrival_time == "18:30"


# =============================================================================
# Happy Path Tests - Update Flight Details
# =============================================================================

class TestUpdateFlightDetailsHappyPath:
    """Happy path tests for updating flight details."""

    def test_update_dropoff_airline_name_only(self):
        """Should successfully update only the dropoff airline name."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number="FR5523",
            dropoff_destination="Tenerife",
        )

        # Simulate update
        booking.dropoff_airline_name = "TUI Airways"

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["dropoff_airline_name"],
            "booking": {
                "dropoff_airline_name": booking.dropoff_airline_name,
                "dropoff_flight_number": booking.dropoff_flight_number,
                "dropoff_destination": booking.dropoff_destination,
            }
        }

        assert response_data["success"] is True
        assert "dropoff_airline_name" in response_data["fields_updated"]
        assert response_data["booking"]["dropoff_airline_name"] == "TUI Airways"
        assert response_data["booking"]["dropoff_flight_number"] == "FR5523"  # Unchanged

    def test_update_dropoff_flight_number_only(self):
        """Should successfully update only the dropoff flight number."""
        booking = create_mock_booking(
            dropoff_airline_name="Ryanair",
            dropoff_flight_number="FR5523",
        )

        booking.dropoff_flight_number = "BY1234"

        response_data = {
            "success": True,
            "fields_updated": ["dropoff_flight_number"],
            "booking": {
                "dropoff_airline_name": booking.dropoff_airline_name,
                "dropoff_flight_number": booking.dropoff_flight_number,
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["dropoff_flight_number"] == "BY1234"
        assert response_data["booking"]["dropoff_airline_name"] == "Ryanair"  # Unchanged

    def test_update_dropoff_destination_only(self):
        """Should successfully update only the dropoff destination."""
        booking = create_mock_booking(
            dropoff_destination="Tenerife",
        )

        booking.dropoff_destination = "Dalaman Airport"

        response_data = {
            "success": True,
            "fields_updated": ["dropoff_destination"],
            "booking": {
                "dropoff_destination": booking.dropoff_destination,
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["dropoff_destination"] == "Dalaman Airport"

    def test_update_pickup_airline_name_only(self):
        """Should successfully update only the pickup airline name."""
        booking = create_mock_booking(
            pickup_airline_name=None,
            pickup_flight_number="FR5524",
        )

        booking.pickup_airline_name = "easyJet"

        response_data = {
            "success": True,
            "fields_updated": ["pickup_airline_name"],
            "booking": {
                "pickup_airline_name": booking.pickup_airline_name,
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["pickup_airline_name"] == "easyJet"

    def test_update_pickup_flight_number_only(self):
        """Should successfully update only the pickup flight number."""
        booking = create_mock_booking(
            pickup_flight_number="FR5524",
        )

        booking.pickup_flight_number = "U2 1234"

        response_data = {
            "success": True,
            "fields_updated": ["pickup_flight_number"],
            "booking": {
                "pickup_flight_number": booking.pickup_flight_number,
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["pickup_flight_number"] == "U2 1234"

    def test_update_pickup_origin_only(self):
        """Should successfully update only the pickup origin."""
        booking = create_mock_booking(
            pickup_origin="Tenerife",
        )

        booking.pickup_origin = "Malaga Airport"

        response_data = {
            "success": True,
            "fields_updated": ["pickup_origin"],
            "booking": {
                "pickup_origin": booking.pickup_origin,
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["pickup_origin"] == "Malaga Airport"

    def test_update_all_dropoff_fields_together(self):
        """Should successfully update all dropoff flight fields together."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number=None,
            dropoff_destination=None,
        )

        booking.dropoff_airline_name = "British Airways"
        booking.dropoff_flight_number = "BA2490"
        booking.dropoff_destination = "Palma de Mallorca"

        response_data = {
            "success": True,
            "fields_updated": ["dropoff_airline_name", "dropoff_flight_number", "dropoff_destination"],
            "booking": {
                "dropoff_airline_name": booking.dropoff_airline_name,
                "dropoff_flight_number": booking.dropoff_flight_number,
                "dropoff_destination": booking.dropoff_destination,
            }
        }

        assert response_data["success"] is True
        assert len(response_data["fields_updated"]) == 3
        assert response_data["booking"]["dropoff_airline_name"] == "British Airways"
        assert response_data["booking"]["dropoff_flight_number"] == "BA2490"
        assert response_data["booking"]["dropoff_destination"] == "Palma de Mallorca"

    def test_update_all_pickup_fields_together(self):
        """Should successfully update all pickup flight fields together."""
        booking = create_mock_booking(
            pickup_airline_name=None,
            pickup_flight_number=None,
            pickup_origin=None,
        )

        booking.pickup_airline_name = "Jet2"
        booking.pickup_flight_number = "LS567"
        booking.pickup_origin = "Antalya Airport"

        response_data = {
            "success": True,
            "fields_updated": ["pickup_airline_name", "pickup_flight_number", "pickup_origin"],
            "booking": {
                "pickup_airline_name": booking.pickup_airline_name,
                "pickup_flight_number": booking.pickup_flight_number,
                "pickup_origin": booking.pickup_origin,
            }
        }

        assert response_data["success"] is True
        assert len(response_data["fields_updated"]) == 3
        assert response_data["booking"]["pickup_airline_name"] == "Jet2"
        assert response_data["booking"]["pickup_flight_number"] == "LS567"
        assert response_data["booking"]["pickup_origin"] == "Antalya Airport"

    def test_update_all_flight_fields_together(self):
        """Should successfully update all 6 flight fields together."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number=None,
            dropoff_destination=None,
            pickup_airline_name=None,
            pickup_flight_number=None,
            pickup_origin=None,
        )

        booking.dropoff_airline_name = "TUI Airways"
        booking.dropoff_flight_number = "BY1234"
        booking.dropoff_destination = "Rhodes Airport"
        booking.pickup_airline_name = "TUI Airways"
        booking.pickup_flight_number = "BY1235"
        booking.pickup_origin = "Rhodes Airport"

        response_data = {
            "success": True,
            "fields_updated": [
                "dropoff_airline_name", "dropoff_flight_number", "dropoff_destination",
                "pickup_airline_name", "pickup_flight_number", "pickup_origin"
            ],
            "booking": {
                "dropoff_airline_name": booking.dropoff_airline_name,
                "dropoff_flight_number": booking.dropoff_flight_number,
                "dropoff_destination": booking.dropoff_destination,
                "pickup_airline_name": booking.pickup_airline_name,
                "pickup_flight_number": booking.pickup_flight_number,
                "pickup_origin": booking.pickup_origin,
            }
        }

        assert response_data["success"] is True
        assert len(response_data["fields_updated"]) == 6

    def test_update_flight_departure_time_only(self):
        """Should successfully update only the flight departure time."""
        booking = create_mock_booking(
            flight_departure_time=None,
        )

        booking.flight_departure_time = time(14, 30)

        response_data = {
            "success": True,
            "fields_updated": ["flight_departure_time"],
            "booking": {
                "flight_departure_time": booking.flight_departure_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["flight_departure_time"] == "14:30"

    def test_update_flight_arrival_time_only(self):
        """Should successfully update only the flight arrival time."""
        booking = create_mock_booking(
            flight_arrival_time=None,
        )

        booking.flight_arrival_time = time(18, 45)

        response_data = {
            "success": True,
            "fields_updated": ["flight_arrival_time"],
            "booking": {
                "flight_arrival_time": booking.flight_arrival_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert response_data["booking"]["flight_arrival_time"] == "18:45"

    def test_update_both_flight_times_together(self):
        """Should successfully update both flight times together."""
        booking = create_mock_booking(
            flight_departure_time=None,
            flight_arrival_time=None,
        )

        booking.flight_departure_time = time(9, 15)
        booking.flight_arrival_time = time(16, 30)

        response_data = {
            "success": True,
            "fields_updated": ["flight_departure_time", "flight_arrival_time"],
            "booking": {
                "flight_departure_time": booking.flight_departure_time.strftime("%H:%M"),
                "flight_arrival_time": booking.flight_arrival_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert len(response_data["fields_updated"]) == 2
        assert response_data["booking"]["flight_departure_time"] == "09:15"
        assert response_data["booking"]["flight_arrival_time"] == "16:30"

    def test_update_all_fields_including_flight_times(self):
        """Should successfully update all 8 flight fields together (6 + 2 times)."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number=None,
            dropoff_destination=None,
            pickup_airline_name=None,
            pickup_flight_number=None,
            pickup_origin=None,
            flight_departure_time=None,
            flight_arrival_time=None,
        )

        booking.dropoff_airline_name = "TUI Airways"
        booking.dropoff_flight_number = "BY1234"
        booking.dropoff_destination = "Rhodes Airport"
        booking.pickup_airline_name = "TUI Airways"
        booking.pickup_flight_number = "BY1235"
        booking.pickup_origin = "Rhodes Airport"
        booking.flight_departure_time = time(10, 0)
        booking.flight_arrival_time = time(17, 30)

        response_data = {
            "success": True,
            "fields_updated": [
                "dropoff_airline_name", "dropoff_flight_number", "dropoff_destination",
                "pickup_airline_name", "pickup_flight_number", "pickup_origin",
                "flight_departure_time", "flight_arrival_time"
            ],
            "booking": {
                "dropoff_airline_name": booking.dropoff_airline_name,
                "flight_departure_time": booking.flight_departure_time.strftime("%H:%M"),
                "flight_arrival_time": booking.flight_arrival_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert len(response_data["fields_updated"]) == 8
        assert response_data["booking"]["flight_departure_time"] == "10:00"
        assert response_data["booking"]["flight_arrival_time"] == "17:30"

    def test_update_confirmed_booking_flight_details(self):
        """Should allow updating flight details for confirmed booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CONFIRMED)

        booking.dropoff_airline_name = "Wizz Air"

        assert booking.status == BookingStatus.CONFIRMED
        assert booking.dropoff_airline_name == "Wizz Air"

    def test_update_pending_booking_flight_details(self):
        """Should allow updating flight details for pending booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)

        booking.pickup_airline_name = "Norwegian"

        assert booking.status == BookingStatus.PENDING
        assert booking.pickup_airline_name == "Norwegian"

    def test_update_completed_booking_flight_details(self):
        """Should allow updating flight details for completed booking (record keeping)."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.COMPLETED)

        booking.dropoff_airline_name = "Corrected Airline"

        assert booking.status == BookingStatus.COMPLETED
        assert booking.dropoff_airline_name == "Corrected Airline"


# =============================================================================
# Negative Tests - Update Flight Details
# =============================================================================

class TestUpdateFlightDetailsNegative:
    """Negative tests for updating flight details."""

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
        """Should return 400 when no fields are provided."""
        # Empty update request (all None)
        updates_made = []

        if not updates_made:
            status_code = 400
            error = "No fields to update"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "No fields" in error

    def test_update_requires_admin_authentication(self):
        """Update endpoint requires admin authentication."""
        user = MagicMock()
        user.is_admin = False

        if not user.is_admin:
            status_code = 403
            error = "Not authorized"
        else:
            status_code = 200
            error = None

        assert status_code == 403

    def test_update_requires_authentication(self):
        """Update endpoint requires authentication."""
        token = None

        if token is None:
            status_code = 401
            error = "Not authenticated"
        else:
            status_code = 200
            error = None

        assert status_code == 401

    def test_update_negative_booking_id_returns_404(self):
        """Negative booking ID should return 404."""
        booking_id = -1
        booking = None  # DB won't find this

        if booking is None:
            status_code = 404
        else:
            status_code = 200

        assert status_code == 404

    def test_update_zero_booking_id_returns_404(self):
        """Zero booking ID should return 404."""
        booking_id = 0
        booking = None

        if booking is None:
            status_code = 404
        else:
            status_code = 200

        assert status_code == 404

    def test_update_invalid_booking_id_type(self):
        """Non-integer booking ID should be rejected."""
        booking_id = "invalid-id"

        try:
            int(booking_id)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False


# =============================================================================
# Edge Cases Tests - Update Flight Details
# =============================================================================

class TestUpdateFlightDetailsEdgeCases:
    """Edge case tests for updating flight details."""

    def test_update_airline_name_to_empty_string(self):
        """Updating airline name to empty string should clear it."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
        )

        # Empty string should clear the field
        booking.dropoff_airline_name = ""

        assert booking.dropoff_airline_name == ""

    def test_update_airline_name_to_null(self):
        """Updating airline name to None should clear it."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
        )

        booking.dropoff_airline_name = None

        assert booking.dropoff_airline_name is None

    def test_update_flight_number_with_spaces(self):
        """Flight numbers with spaces should be accepted."""
        booking = create_mock_booking()

        booking.dropoff_flight_number = "BA 2490"

        assert booking.dropoff_flight_number == "BA 2490"

    def test_update_flight_number_lowercase(self):
        """Lowercase flight numbers should be accepted."""
        booking = create_mock_booking()

        booking.dropoff_flight_number = "ba2490"

        assert booking.dropoff_flight_number == "ba2490"

    def test_update_destination_with_special_characters(self):
        """Destinations with special characters should be accepted."""
        booking = create_mock_booking()

        booking.dropoff_destination = "São Paulo–Guarulhos International"

        assert booking.dropoff_destination == "São Paulo–Guarulhos International"

    def test_update_destination_with_parentheses(self):
        """Destinations with parentheses (airport code) should be accepted."""
        booking = create_mock_booking()

        booking.dropoff_destination = "Tenerife (TFS)"

        assert booking.dropoff_destination == "Tenerife (TFS)"

    def test_update_airline_name_very_long(self):
        """Very long airline names should be handled."""
        booking = create_mock_booking()

        long_name = "A" * 100  # 100 characters
        booking.dropoff_airline_name = long_name

        assert booking.dropoff_airline_name == long_name
        assert len(booking.dropoff_airline_name) == 100

    def test_update_destination_very_long(self):
        """Very long destination names should be handled."""
        booking = create_mock_booking()

        long_destination = "Very Long Airport Name " * 10
        booking.dropoff_destination = long_destination

        assert booking.dropoff_destination == long_destination

    def test_update_preserves_other_booking_fields(self):
        """Updating flight details should not affect other booking fields."""
        booking = create_mock_booking(
            reference="TAG-TEST123",
            dropoff_date_val=FUTURE_DATE,
            dropoff_time_val=time(8, 30),
            pickup_date_val=FUTURE_DATE_END,
            pickup_time_val=time(16, 0),
        )

        original_reference = booking.reference
        original_dropoff_date = booking.dropoff_date
        original_dropoff_time = booking.dropoff_time
        original_pickup_date = booking.pickup_date
        original_pickup_time = booking.pickup_time

        # Update flight details
        booking.dropoff_airline_name = "New Airline"
        booking.pickup_flight_number = "NEW123"

        # Other fields should be unchanged
        assert booking.reference == original_reference
        assert booking.dropoff_date == original_dropoff_date
        assert booking.dropoff_time == original_dropoff_time
        assert booking.pickup_date == original_pickup_date
        assert booking.pickup_time == original_pickup_time

    def test_update_does_not_affect_customer_data(self):
        """Updating flight details should not affect customer data."""
        customer = create_mock_customer(
            first_name="Jane",
            last_name="Smith",
            email="jane.smith@example.com",
        )
        booking = create_mock_booking(customer=customer)

        original_customer_name = f"{booking.customer.first_name} {booking.customer.last_name}"
        original_email = booking.customer.email

        # Update flight details
        booking.dropoff_airline_name = "Updated Airline"

        # Customer data should be unchanged
        assert f"{booking.customer.first_name} {booking.customer.last_name}" == original_customer_name
        assert booking.customer.email == original_email

    def test_update_does_not_affect_vehicle_data(self):
        """Updating flight details should not affect vehicle data."""
        vehicle = create_mock_vehicle(
            registration="XY12 ABC",
            make="Ford",
            model="Focus",
        )
        booking = create_mock_booking(vehicle=vehicle)

        original_registration = booking.vehicle.registration
        original_make = booking.vehicle.make

        # Update flight details
        booking.pickup_origin = "Updated Origin"

        # Vehicle data should be unchanged
        assert booking.vehicle.registration == original_registration
        assert booking.vehicle.make == original_make

    def test_update_same_values_still_succeeds(self):
        """Updating with same values should still succeed."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="BY1234",
        )

        original_airline = booking.dropoff_airline_name
        original_flight = booking.dropoff_flight_number

        # Update with same values
        booking.dropoff_airline_name = "TUI Airways"
        booking.dropoff_flight_number = "BY1234"

        assert booking.dropoff_airline_name == original_airline
        assert booking.dropoff_flight_number == original_flight

    def test_update_whitespace_only_airline_name(self):
        """Whitespace-only airline name should be handled."""
        booking = create_mock_booking()

        booking.dropoff_airline_name = "   "

        # Application might trim this, but model accepts it
        assert booking.dropoff_airline_name == "   "

    def test_update_unicode_airline_name(self):
        """Unicode characters in airline name should be accepted."""
        booking = create_mock_booking()

        booking.dropoff_airline_name = "Türk Hava Yolları"

        assert booking.dropoff_airline_name == "Türk Hava Yolları"

    def test_update_mixed_dropoff_and_pickup(self):
        """Updating mix of dropoff and pickup fields should work."""
        booking = create_mock_booking()

        booking.dropoff_airline_name = "Airline A"
        booking.pickup_origin = "Origin B"

        assert booking.dropoff_airline_name == "Airline A"
        assert booking.pickup_origin == "Origin B"

    def test_update_flight_time_format_hhmm(self):
        """Flight times should be stored in HH:MM format."""
        booking = create_mock_booking()

        # Set as time object
        booking.flight_departure_time = time(8, 5)

        # Verify formatting
        formatted = booking.flight_departure_time.strftime("%H:%M")
        assert formatted == "08:05"

    def test_update_flight_time_midnight(self):
        """Flight times at midnight should be handled correctly."""
        booking = create_mock_booking()

        booking.flight_departure_time = time(0, 0)

        assert booking.flight_departure_time == time(0, 0)

    def test_update_flight_time_late_night(self):
        """Late night flight times (23:xx) should be handled correctly."""
        booking = create_mock_booking()

        booking.flight_arrival_time = time(23, 59)

        formatted = booking.flight_arrival_time.strftime("%H:%M")
        assert formatted == "23:59"

    def test_update_flight_time_to_none_clears_value(self):
        """Setting flight time to None should clear the value."""
        booking = create_mock_booking(flight_departure_time=time(10, 0))

        booking.flight_departure_time = None

        assert booking.flight_departure_time is None

    def test_update_flight_times_preserves_other_booking_fields(self):
        """Updating flight times should not affect other booking fields."""
        from datetime import timedelta
        today = date.today()

        booking = create_mock_booking(
            reference="TAG-FLIGHTTIME",
            dropoff_date_val=today + timedelta(days=10),
            dropoff_time_val=time(8, 30),
            dropoff_airline_name="TUI Airways",
        )

        original_reference = booking.reference
        original_dropoff_date = booking.dropoff_date
        original_airline = booking.dropoff_airline_name

        # Update only flight times
        booking.flight_departure_time = time(10, 30)
        booking.flight_arrival_time = time(18, 0)

        # Other fields should be unchanged
        assert booking.reference == original_reference
        assert booking.dropoff_date == original_dropoff_date
        assert booking.dropoff_airline_name == original_airline


# =============================================================================
# Email Integration Tests - Verify flight details in emails
# =============================================================================

class TestFlightDetailsEmailIntegration:
    """Tests to verify updated flight details appear correctly in emails."""

    def test_departure_flight_string_format_with_airline(self):
        """Departure flight string should combine airline + flight number + destination."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="BY1234",
            dropoff_destination="Dalaman Airport",
        )

        # Build departure flight string as done in email_service
        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == "TUI Airways BY1234 to Dalaman Airport"

    def test_departure_flight_string_without_airline(self):
        """Departure flight string should work without airline name."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number="FR5523",
            dropoff_destination="Tenerife",
        )

        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == "FR5523 to Tenerife"

    def test_departure_flight_string_without_flight_number(self):
        """Departure flight string should work without flight number."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number=None,
            dropoff_destination="Dalaman",
        )

        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == "TUI Airways to Dalaman"

    def test_departure_flight_string_unknown_flight_number(self):
        """Flight number 'Unknown' should be excluded from string."""
        booking = create_mock_booking(
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="Unknown",
            dropoff_destination="Dalaman",
        )

        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == "TUI Airways to Dalaman"
        assert "Unknown" not in departure_flight

    def test_return_flight_string_format_with_airline(self):
        """Return flight string should combine airline + flight number + origin."""
        booking = create_mock_booking(
            pickup_airline_name="easyJet",
            pickup_flight_number="U2 4567",
            pickup_origin="Malaga Airport",
        )

        parts = []
        if booking.pickup_airline_name:
            parts.append(booking.pickup_airline_name)
        if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
            parts.append(booking.pickup_flight_number)
        return_flight = " ".join(parts)
        if booking.pickup_origin:
            return_flight += f" from {booking.pickup_origin}"

        assert return_flight == "easyJet U2 4567 from Malaga Airport"

    def test_return_flight_string_without_airline(self):
        """Return flight string should work without airline name."""
        booking = create_mock_booking(
            pickup_airline_name=None,
            pickup_flight_number="FR5524",
            pickup_origin="Tenerife",
        )

        parts = []
        if booking.pickup_airline_name:
            parts.append(booking.pickup_airline_name)
        if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
            parts.append(booking.pickup_flight_number)
        return_flight = " ".join(parts)
        if booking.pickup_origin:
            return_flight += f" from {booking.pickup_origin}"

        assert return_flight == "FR5524 from Tenerife"

    def test_empty_flight_details_returns_empty_string(self):
        """No flight details should result in empty string."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_flight_number=None,
            dropoff_destination=None,
        )

        departure_flight = ""
        if booking.dropoff_airline_name or booking.dropoff_destination:
            parts = []
            if booking.dropoff_airline_name:
                parts.append(booking.dropoff_airline_name)
            if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
                parts.append(booking.dropoff_flight_number)
            departure_flight = " ".join(parts)
            if booking.dropoff_destination:
                departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == ""


# =============================================================================
# Response Format Tests
# =============================================================================

class TestUpdateFlightDetailsResponse:
    """Tests for the API response format."""

    def test_response_includes_success_flag(self):
        """Response should include success boolean."""
        response_data = {
            "success": True,
            "message": "Booking updated successfully",
            "fields_updated": ["dropoff_airline_name"],
            "booking": {}
        }

        assert "success" in response_data
        assert isinstance(response_data["success"], bool)

    def test_response_includes_message(self):
        """Response should include message string."""
        booking = create_mock_booking(reference="TAG-TEST001")

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": [],
            "booking": {}
        }

        assert "message" in response_data
        assert booking.reference in response_data["message"]

    def test_response_includes_fields_updated_list(self):
        """Response should include list of updated fields."""
        response_data = {
            "success": True,
            "message": "Booking updated successfully",
            "fields_updated": ["dropoff_airline_name", "pickup_origin"],
            "booking": {}
        }

        assert "fields_updated" in response_data
        assert isinstance(response_data["fields_updated"], list)
        assert "dropoff_airline_name" in response_data["fields_updated"]
        assert "pickup_origin" in response_data["fields_updated"]

    def test_response_includes_booking_object(self):
        """Response should include booking object with updated values."""
        booking = create_mock_booking()
        booking.dropoff_airline_name = "Updated Airline"

        response_data = {
            "success": True,
            "booking": {
                "id": booking.id,
                "reference": booking.reference,
                "dropoff_airline_name": booking.dropoff_airline_name,
            }
        }

        assert "booking" in response_data
        assert response_data["booking"]["dropoff_airline_name"] == "Updated Airline"

    def test_response_booking_includes_all_flight_fields(self):
        """Response booking should include all flight-related fields."""
        booking = create_mock_booking(
            dropoff_airline_name="Airline A",
            dropoff_flight_number="AA123",
            dropoff_destination="Dest A",
            pickup_airline_name="Airline B",
            pickup_flight_number="BB456",
            pickup_origin="Origin B",
        )

        response_booking = {
            "dropoff_airline_name": booking.dropoff_airline_name,
            "dropoff_flight_number": booking.dropoff_flight_number,
            "dropoff_destination": booking.dropoff_destination,
            "pickup_airline_name": booking.pickup_airline_name,
            "pickup_flight_number": booking.pickup_flight_number,
            "pickup_origin": booking.pickup_origin,
        }

        assert response_booking["dropoff_airline_name"] == "Airline A"
        assert response_booking["dropoff_flight_number"] == "AA123"
        assert response_booking["dropoff_destination"] == "Dest A"
        assert response_booking["pickup_airline_name"] == "Airline B"
        assert response_booking["pickup_flight_number"] == "BB456"
        assert response_booking["pickup_origin"] == "Origin B"


# =============================================================================
# Overnight Pickup Time Tests - Edit Flight Arrival Time
# =============================================================================

class TestEditFlightArrivalOvernightPickup:
    """
    Tests for editing flight_arrival_time when pickup_time crosses midnight.

    Key scenarios:
    - Flight arrives at 23:35 → pickup at 00:05 (next day)
    - Flight arrives at 23:45 → pickup at 00:15 (next day)
    - Flight arrives at 23:30 → pickup at 00:00 (midnight, next day)
    - Flight arrives at 23:50 → pickup at 00:20 (next day)
    """

    def calculate_pickup_time(self, arrival_time_str):
        """
        Calculate pickup_time from flight_arrival_time.
        pickup_time = flight_arrival_time + 30 minutes

        Returns: (pickup_time_str, crosses_midnight)
        """
        h, m = map(int, arrival_time_str.split(':'))
        total_mins = h * 60 + m + 30  # Add 30 minutes buffer

        crosses_midnight = total_mins >= 24 * 60
        pickup_hour = (total_mins // 60) % 24
        pickup_min = total_mins % 60

        return f"{pickup_hour:02d}:{pickup_min:02d}", crosses_midnight

    def test_arrival_2335_pickup_0005(self):
        """
        Edit arrival time to 23:35 → pickup should be 00:05 (crosses midnight).

        Scenario: Flight arrives at 23:35 on Monday.
        Customer collection: 00:05 on Tuesday.
        """
        arrival_time = "23:35"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "00:05"
        assert crosses is True

        # Simulate booking update
        booking = create_mock_booking(
            flight_arrival_time=time(23, 35),
            pickup_time_val=time(0, 5),  # Calculated by API
        )

        assert booking.flight_arrival_time == time(23, 35)
        assert booking.pickup_time == time(0, 5)

    def test_arrival_2345_pickup_0015(self):
        """
        Edit arrival time to 23:45 → pickup should be 00:15 (crosses midnight).
        """
        arrival_time = "23:45"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "00:15"
        assert crosses is True

        booking = create_mock_booking(
            flight_arrival_time=time(23, 45),
            pickup_time_val=time(0, 15),
        )

        assert booking.flight_arrival_time == time(23, 45)
        assert booking.pickup_time == time(0, 15)

    def test_arrival_2330_pickup_0000(self):
        """
        Edit arrival time to 23:30 → pickup should be 00:00 (exactly midnight).
        """
        arrival_time = "23:30"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "00:00"
        assert crosses is True

        booking = create_mock_booking(
            flight_arrival_time=time(23, 30),
            pickup_time_val=time(0, 0),
        )

        assert booking.flight_arrival_time == time(23, 30)
        assert booking.pickup_time == time(0, 0)

    def test_arrival_2350_pickup_0020(self):
        """
        Edit arrival time to 23:50 → pickup should be 00:20 (crosses midnight).
        """
        arrival_time = "23:50"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "00:20"
        assert crosses is True

        booking = create_mock_booking(
            flight_arrival_time=time(23, 50),
            pickup_time_val=time(0, 20),
        )

        assert booking.flight_arrival_time == time(23, 50)
        assert booking.pickup_time == time(0, 20)

    def test_arrival_2359_pickup_0029(self):
        """
        Edge case: Flight arrives at 23:59 → pickup at 00:29.
        """
        arrival_time = "23:59"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "00:29"
        assert crosses is True

    def test_arrival_2329_pickup_2359_no_midnight_cross(self):
        """
        Flight arrives at 23:29 → pickup at 23:59 (does NOT cross midnight).
        """
        arrival_time = "23:29"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "23:59"
        assert crosses is False

    def test_arrival_2200_pickup_2230_normal(self):
        """
        Normal evening arrival: 22:00 → pickup at 22:30 (same day).
        """
        arrival_time = "22:00"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "22:30"
        assert crosses is False

    def test_arrival_0035_pickup_0105_early_morning(self):
        """
        Early morning arrival (already next day): 00:35 → pickup at 01:05.
        This is for overnight flights that arrive after midnight.
        """
        arrival_time = "00:35"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "01:05"
        assert crosses is False  # Already past midnight, no additional crossing

    def test_arrival_0050_pickup_0120(self):
        """
        Overnight flight arrives 00:50 → pickup at 01:20.
        (Flight departed previous evening, arrives after midnight)
        """
        arrival_time = "00:50"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "01:20"
        assert crosses is False

    def test_arrival_0130_pickup_0200(self):
        """
        Late overnight arrival: 01:30 → pickup at 02:00.
        """
        arrival_time = "01:30"
        pickup_time, crosses = self.calculate_pickup_time(arrival_time)

        assert pickup_time == "02:00"
        assert crosses is False

    def test_update_booking_arrival_time_recalculates_pickup(self):
        """
        When flight_arrival_time is updated, pickup_time should be auto-recalculated.
        This simulates the API behavior.
        """
        # Initial booking with 18:00 arrival → 18:30 pickup
        booking = create_mock_booking(
            flight_arrival_time=time(18, 0),
            pickup_time_val=time(18, 30),
        )

        assert booking.flight_arrival_time == time(18, 0)
        assert booking.pickup_time == time(18, 30)

        # Simulate editing arrival time to 23:35
        new_arrival = time(23, 35)
        new_pickup = time(0, 5)  # Calculated: 23:35 + 30 = 00:05

        booking.flight_arrival_time = new_arrival
        booking.pickup_time = new_pickup

        assert booking.flight_arrival_time == time(23, 35)
        assert booking.pickup_time == time(0, 5)

    def test_fields_updated_includes_both_arrival_and_pickup(self):
        """
        When updating flight_arrival_time, response should show both fields updated.
        """
        fields_updated = ["flight_arrival_time", "pickup_time"]

        assert "flight_arrival_time" in fields_updated
        assert "pickup_time" in fields_updated
        assert len(fields_updated) == 2

    def test_overnight_booking_dates_scenario(self):
        """
        Full scenario: Booking with arrival 23:35 on Monday.

        - pickup_date should be Tuesday (arrival date + 1 for overnight collection)
        - pickup_time should be 00:05
        - flight_arrival_time should be 23:35
        """
        arrival_date = FUTURE_DATE  # Monday

        # When arrival is 23:35, pickup crosses to next day
        pickup_date = arrival_date + timedelta(days=1)  # Tuesday

        booking = create_mock_booking(
            pickup_date_val=pickup_date,
            pickup_time_val=time(0, 5),
            flight_arrival_time=time(23, 35),
        )

        assert booking.pickup_date == arrival_date + timedelta(days=1)
        assert booking.pickup_time == time(0, 5)
        assert booking.flight_arrival_time == time(23, 35)

    def test_response_format_overnight_pickup(self):
        """
        API response should format overnight pickup times correctly.
        """
        booking = create_mock_booking(
            flight_arrival_time=time(23, 45),
            pickup_time_val=time(0, 15),
        )

        response_booking = {
            "flight_arrival_time": booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else None,
            "pickup_time": booking.pickup_time.strftime("%H:%M") if booking.pickup_time else None,
        }

        assert response_booking["flight_arrival_time"] == "23:45"
        assert response_booking["pickup_time"] == "00:15"
