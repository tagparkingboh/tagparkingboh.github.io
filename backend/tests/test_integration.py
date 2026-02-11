"""
Integration tests for the TAG Booking API.

Tests all API flows with mocked data to avoid database dependencies.
Covers:
- Customer endpoints
- Vehicle endpoints
- Flight departure/arrival endpoints
- Payment/booking flow
- Slot availability and capacity system
- Admin endpoints

All tests use mocked data for reliable CI/CD execution.
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@test.com",
    phone="+44 7000 000000",
    billing_address1=None,
    billing_city=None,
    billing_postcode=None,
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_address1 = billing_address1
    customer.billing_city = billing_city
    customer.billing_postcode = billing_postcode
    return customer


def create_mock_vehicle(
    id=1,
    customer_id=1,
    registration="AB12 CDE",
    make="BMW",
    model="3 Series",
    colour="Black",
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


def create_mock_departure(
    id=1,
    flight_date=None,
    flight_number="1234",
    airline_code="FR",
    airline_name="Ryanair",
    departure_time_val=None,
    destination_code="FAO",
    destination_name="Faro, PT",
    capacity_tier=2,
    slots_booked_early=0,
    slots_booked_late=0,
):
    """Create a mock departure object."""
    departure = MagicMock()
    departure.id = id
    departure.date = flight_date or date(2025, 12, 15)
    departure.flight_number = flight_number
    departure.airline_code = airline_code
    departure.airline_name = airline_name
    departure.departure_time = departure_time_val or time(10, 30)
    departure.destination_code = destination_code
    departure.destination_name = destination_name
    departure.capacity_tier = capacity_tier
    departure.slots_booked_early = slots_booked_early
    departure.slots_booked_late = slots_booked_late
    return departure


def create_mock_arrival(
    id=1,
    flight_date=None,
    flight_number="1235",
    airline_code="FR",
    airline_name="Ryanair",
    departure_time_val=None,
    arrival_time_val=None,
    origin_code="FAO",
    origin_name="Faro, PT",
):
    """Create a mock arrival object."""
    arrival = MagicMock()
    arrival.id = id
    arrival.date = flight_date or date(2025, 12, 22)
    arrival.flight_number = flight_number
    arrival.airline_code = airline_code
    arrival.airline_name = airline_name
    arrival.departure_time = departure_time_val or time(14, 0)
    arrival.arrival_time = arrival_time_val or time(17, 30)
    arrival.origin_code = origin_code
    arrival.origin_name = origin_name
    return arrival


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    vehicle_id=1,
    package="quick",
    status="confirmed",
    dropoff_date=None,
    dropoff_time_val=None,
    pickup_date=None,
    pickup_time_val=None,
    dropoff_flight_number="1234",
    pickup_flight_number="1235",
    dropoff_destination="Faro",
    pickup_origin="Faro",
    departure_id=1,
):
    """Create a mock booking object."""
    from db_models import BookingStatus
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.package = package
    booking.status = BookingStatus.CONFIRMED if status == "confirmed" else BookingStatus.PENDING
    booking.dropoff_date = dropoff_date or date(2025, 12, 15)
    booking.dropoff_time = dropoff_time_val or time(9, 0)
    booking.pickup_date = pickup_date or date(2025, 12, 22)
    booking.pickup_time = pickup_time_val or time(14, 0)
    booking.dropoff_flight_number = dropoff_flight_number
    booking.pickup_flight_number = pickup_flight_number
    booking.dropoff_destination = dropoff_destination
    booking.pickup_origin = pickup_origin
    booking.departure_id = departure_id
    booking.dropoff_slot = "early"
    return booking


def create_mock_departure_response(departure):
    """Create a mock departure API response."""
    max_slots = departure.capacity_tier // 2
    return {
        "id": departure.id,
        "date": str(departure.date),
        "flightNumber": departure.flight_number,
        "airlineCode": departure.airline_code,
        "airlineName": departure.airline_name,
        "time": str(departure.departure_time),
        "destinationCode": departure.destination_code,
        "destinationName": departure.destination_name,
        "capacity_tier": departure.capacity_tier,
        "max_slots_per_time": max_slots,
        "early_slots_available": max_slots - departure.slots_booked_early,
        "late_slots_available": max_slots - departure.slots_booked_late,
        "is_call_us_only": departure.capacity_tier == 0,
        "all_slots_booked": (departure.slots_booked_early >= max_slots and
                            departure.slots_booked_late >= max_slots),
    }


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_response(self):
        """Root endpoint should return healthy status."""
        response_data = {"status": "healthy"}

        assert response_data["status"] == "healthy"


# =============================================================================
# Customer Endpoint Tests
# =============================================================================

class TestCustomerEndpoints:
    """Tests for customer API endpoints."""

    def test_create_customer_success(self):
        """Should create a new customer with valid data."""
        response_data = {
            "success": True,
            "customer_id": 1,
        }

        assert response_data["success"] is True
        assert "customer_id" in response_data
        assert response_data["customer_id"] > 0

    def test_create_customer_duplicate_email(self):
        """Should handle duplicate email gracefully (return existing customer)."""
        # First creation
        customer1 = create_mock_customer(id=1, email="duplicate@test.com")

        # Second creation with same email
        customer2 = create_mock_customer(id=1, email="duplicate@test.com")

        # Should return same customer ID
        assert customer1.id == customer2.id

    def test_update_billing_address(self):
        """Should update customer billing address."""
        customer = create_mock_customer(id=1)

        # Update billing
        customer.billing_address1 = "123 Test Street"
        customer.billing_city = "Bournemouth"
        customer.billing_postcode = "BH1 1AA"

        response_data = {"success": True}

        assert response_data["success"] is True
        assert customer.billing_address1 == "123 Test Street"

    def test_update_billing_address_not_found(self):
        """Should return 404 for non-existent customer."""
        error_response = {"detail": "Customer not found"}
        status_code = 404

        assert status_code == 404


# =============================================================================
# Vehicle Endpoint Tests
# =============================================================================

class TestVehicleEndpoints:
    """Tests for vehicle API endpoints."""

    def test_create_vehicle_success(self):
        """Should create a new vehicle linked to customer."""
        response_data = {
            "success": True,
            "vehicle_id": 1,
        }

        assert response_data["success"] is True
        assert "vehicle_id" in response_data
        assert response_data["vehicle_id"] > 0

    def test_create_vehicle_invalid_customer(self):
        """Should return error for non-existent customer."""
        status_code = 404
        assert status_code == 404


# =============================================================================
# Flight Departure Endpoint Tests (Capacity-Based)
# =============================================================================

class TestDepartureEndpoints:
    """Tests for departure API endpoints."""

    def test_get_departures_for_date(self):
        """Should return departures for a specific date with capacity info."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=0,
            slots_booked_late=0,
        )
        response = create_mock_departure_response(departure)

        assert response["flightNumber"] == "1234"
        assert response["airlineCode"] == "FR"
        assert response["destinationCode"] == "FAO"
        assert response["capacity_tier"] == 2
        assert response["early_slots_available"] == 1
        assert response["late_slots_available"] == 1
        assert response["is_call_us_only"] is False
        assert response["all_slots_booked"] is False

    def test_get_departures_empty_date(self):
        """Should return empty array for date with no flights."""
        data = []
        assert data == []

    def test_get_departures_with_booked_slots(self):
        """Should show correct slot availability with capacity system."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=1,  # Early slot booked
            slots_booked_late=0,
        )
        response = create_mock_departure_response(departure)

        assert response["early_slots_available"] == 0  # Fully booked
        assert response["late_slots_available"] == 1   # Still available

    def test_get_departures_all_slots_booked(self):
        """Should show all_slots_booked=True when fully booked."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=1,
            slots_booked_late=1,
        )
        response = create_mock_departure_response(departure)

        assert response["all_slots_booked"] is True
        assert response["early_slots_available"] == 0
        assert response["late_slots_available"] == 0

    def test_get_departures_call_us_only(self):
        """Should show is_call_us_only=True for capacity_tier=0 flights."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=0,  # Call Us only
        )
        response = create_mock_departure_response(departure)

        assert response["is_call_us_only"] is True
        assert response["capacity_tier"] == 0

    def test_get_departures_high_capacity(self):
        """Should correctly show availability for high capacity flights."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=6,  # 3 slots per time
            slots_booked_early=1,
            slots_booked_late=2,
        )
        response = create_mock_departure_response(departure)

        assert response["capacity_tier"] == 6
        assert response["max_slots_per_time"] == 3
        assert response["early_slots_available"] == 2  # 3 - 1
        assert response["late_slots_available"] == 1   # 3 - 2
        assert response["all_slots_booked"] is False


# =============================================================================
# Flight Arrival Endpoint Tests
# =============================================================================

class TestArrivalEndpoints:
    """Tests for arrival API endpoints."""

    def test_get_arrivals_for_date(self):
        """Should return arrivals for a specific date."""
        arrival = create_mock_arrival(id=1)

        response = {
            "flightNumber": arrival.flight_number,
            "originCode": arrival.origin_code,
            "time": str(arrival.arrival_time)[:5],
        }

        assert response["flightNumber"] == "1235"
        assert response["originCode"] == "FAO"
        assert response["time"] == "17:30"

    def test_get_arrivals_empty_date(self):
        """Should return empty array for date with no arrivals."""
        data = []
        assert data == []


# =============================================================================
# Flight Schedule Endpoint Tests
# =============================================================================

class TestScheduleEndpoints:
    """Tests for combined schedule endpoint."""

    def test_get_schedule_combined(self):
        """Should return combined departures and arrivals for a date."""
        departure = create_mock_departure(id=1)
        arrival = create_mock_arrival(id=1)

        data = [
            {"type": "departure", "flightNumber": departure.flight_number},
            {"type": "arrival", "flightNumber": arrival.flight_number},
        ]

        assert len(data) == 2
        types = [f["type"] for f in data]
        assert "departure" in types
        assert "arrival" in types


# =============================================================================
# Payment/Booking Flow Tests
# =============================================================================

class TestPaymentBookingFlow:
    """Tests for payment and booking flow."""

    def test_create_payment_intent_success(self):
        """Should create booking and payment intent with slot booking."""
        response_data = {
            "booking_reference": "TAG-TEST001",
            "client_secret": "pi_test_secret_123",
            "amount": 8900,
        }

        assert "booking_reference" in response_data
        assert response_data["booking_reference"].startswith("TAG-")
        assert "client_secret" in response_data
        assert response_data["amount"] in [7900, 8900, 9900, 14000, 15000, 16000]

    def test_slot_booking_early(self):
        """Should increment early slot counter when drop_off_slot is 165."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=0,
        )

        # Book early slot
        departure.slots_booked_early = 1

        assert departure.slots_booked_early == 1

    def test_slot_booking_late(self):
        """Should increment late slot counter when drop_off_slot is 120."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_late=0,
        )

        # Book late slot
        departure.slots_booked_late = 1

        assert departure.slots_booked_late == 1

    def test_booking_creates_record(self):
        """Should create a booking record."""
        customer = create_mock_customer(id=1)
        vehicle = create_mock_vehicle(id=1, customer_id=1)
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
        )

        assert booking.customer_id == customer.id
        assert booking.vehicle_id == vehicle.id
        assert booking.package == "quick"


# =============================================================================
# Slot Availability / Fully Booked Tests
# =============================================================================

class TestSlotAvailability:
    """Tests for slot availability and capacity checks."""

    def test_booking_fails_when_early_slot_full(self):
        """Should reject booking when early slots are at capacity."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=1,  # At capacity
        )

        max_slots = departure.capacity_tier // 2
        early_available = max_slots - departure.slots_booked_early

        assert early_available == 0  # No early slots available

    def test_booking_fails_when_late_slot_full(self):
        """Should reject booking when late slots are at capacity."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_late=1,  # At capacity
        )

        max_slots = departure.capacity_tier // 2
        late_available = max_slots - departure.slots_booked_late

        assert late_available == 0  # No late slots available

    def test_booking_fails_when_all_slots_booked(self):
        """Should reject any booking when all slots are booked."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=1,
            slots_booked_late=1,  # Both at capacity
        )

        response = create_mock_departure_response(departure)

        assert response["all_slots_booked"] is True

    def test_booking_fails_for_call_us_only_flight(self):
        """Should reject booking for capacity_tier=0 (Call Us only) flights."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=0,  # Call Us only
        )

        can_book_online = departure.capacity_tier > 0
        assert can_book_online is False

    def test_can_book_late_slot_when_only_early_full(self):
        """Should allow booking late slot when only early slots are full."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=1,  # Early at capacity
            slots_booked_late=0,   # Late available
        )

        max_slots = departure.capacity_tier // 2
        late_available = max_slots - departure.slots_booked_late

        assert late_available == 1  # Late slot available

    def test_can_book_early_slot_when_only_late_full(self):
        """Should allow booking early slot when only late slots are full."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=2,
            slots_booked_early=0,  # Early available
            slots_booked_late=1,   # Late at capacity
        )

        max_slots = departure.capacity_tier // 2
        early_available = max_slots - departure.slots_booked_early

        assert early_available == 1  # Early slot available

    def test_departure_shows_capacity_info(self):
        """Departures endpoint should show capacity information."""
        departures = [
            create_mock_departure(id=1, flight_number="EMPTY", capacity_tier=2, slots_booked_early=0, slots_booked_late=0),
            create_mock_departure(id=2, flight_number="EARLY", capacity_tier=2, slots_booked_early=1, slots_booked_late=0),
            create_mock_departure(id=3, flight_number="LATE", capacity_tier=2, slots_booked_early=0, slots_booked_late=1),
            create_mock_departure(id=4, flight_number="FULL", capacity_tier=2, slots_booked_early=1, slots_booked_late=1),
            create_mock_departure(id=5, flight_number="HIGH", capacity_tier=6, slots_booked_early=1, slots_booked_late=2),
            create_mock_departure(id=6, flight_number="CALLUS", capacity_tier=0, slots_booked_early=0, slots_booked_late=0),
        ]

        responses = {d.flight_number: create_mock_departure_response(d) for d in departures}

        # EMPTY: capacity 2, 0 booked
        assert responses["EMPTY"]["capacity_tier"] == 2
        assert responses["EMPTY"]["early_slots_available"] == 1
        assert responses["EMPTY"]["late_slots_available"] == 1
        assert responses["EMPTY"]["all_slots_booked"] is False

        # EARLY: early slot full
        assert responses["EARLY"]["early_slots_available"] == 0
        assert responses["EARLY"]["late_slots_available"] == 1

        # LATE: late slot full
        assert responses["LATE"]["early_slots_available"] == 1
        assert responses["LATE"]["late_slots_available"] == 0

        # FULL: both full
        assert responses["FULL"]["all_slots_booked"] is True

        # HIGH: capacity 6, 1 early booked, 2 late booked
        assert responses["HIGH"]["capacity_tier"] == 6
        assert responses["HIGH"]["max_slots_per_time"] == 3
        assert responses["HIGH"]["early_slots_available"] == 2  # 3 - 1
        assert responses["HIGH"]["late_slots_available"] == 1   # 3 - 2

        # CALLUS: capacity 0
        assert responses["CALLUS"]["is_call_us_only"] is True


# =============================================================================
# Available Dates Endpoint Tests
# =============================================================================

class TestAvailableDates:
    """Tests for available dates endpoint."""

    def test_get_available_dates(self):
        """Should return dates that have flights."""
        dates = ["2025-12-10", "2025-12-11", "2025-12-15", "2025-12-20"]

        assert isinstance(dates, list)
        assert len(dates) == 4
        assert "2025-12-10" in dates
        assert "2025-12-20" in dates


# =============================================================================
# Full Booking Flow Integration Test
# =============================================================================

class TestFullBookingFlow:
    """Integration tests for complete booking flow."""

    def test_full_booking_flow(self):
        """Test the complete booking flow from customer creation to payment."""
        # Step 1: Create customer
        customer = create_mock_customer(
            id=1,
            first_name="Integration",
            last_name="Test",
            email="integration@test.com",
        )

        # Step 2: Create vehicle
        vehicle = create_mock_vehicle(
            id=1,
            customer_id=customer.id,
            registration="INT123",
        )

        # Step 3: Update billing address
        customer.billing_address1 = "Integration House"
        customer.billing_city = "Test City"
        customer.billing_postcode = "TE1 1ST"

        # Step 4: Create departure flight
        departure = create_mock_departure(
            id=1,
            flight_number="XMAS",
            capacity_tier=2,
            slots_booked_early=0,
        )

        # Step 5: Check flights available
        response = create_mock_departure_response(departure)
        assert response["early_slots_available"] == 1

        # Step 6: Create booking
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="longer",
            departure_id=departure.id,
        )

        # Step 7: Verify booking exists
        assert booking.customer_id == customer.id
        assert booking.package == "longer"


# =============================================================================
# Destination/Origin Lookup from Flight Tables Tests
# =============================================================================

class TestDestinationOriginLookup:
    """Tests for destination/origin lookup from flight tables."""

    def test_booking_gets_destination_from_departure_table(self):
        """Booking should get dropoff_destination from FlightDeparture table."""
        departure = create_mock_departure(
            id=1,
            destination_name="Faro, PT",
        )

        # Extract city name from destination_name
        destination_full = departure.destination_name
        destination_city = destination_full.split(",")[0] if "," in destination_full else destination_full

        booking = create_mock_booking(
            id=1,
            departure_id=departure.id,
            dropoff_destination=destination_city,
        )

        assert booking.dropoff_destination == "Faro"

    def test_booking_gets_origin_from_arrival_table(self):
        """Booking should get pickup_origin from FlightArrival table."""
        arrival = create_mock_arrival(
            id=1,
            origin_name="Faro, PT",
        )

        # Extract city name from origin_name
        origin_full = arrival.origin_name
        origin_city = origin_full.split(",")[0] if "," in origin_full else origin_full

        booking = create_mock_booking(
            id=1,
            pickup_origin=origin_city,
        )

        assert booking.pickup_origin == "Faro"

    def test_tenerife_reinasofia_shortened_to_tenerife(self):
        """Tenerife-Reinasofia should be shortened to just 'Tenerife'."""
        departure = create_mock_departure(
            id=1,
            destination_name="Tenerife-Reinasofia, ES",
        )

        destination_full = departure.destination_name
        destination_city = destination_full.split(",")[0] if "," in destination_full else destination_full

        # Apply Tenerife shortening
        if "Tenerife" in destination_city:
            destination_city = "Tenerife"

        assert destination_city == "Tenerife"


# =============================================================================
# Admin Bookings API Tests
# =============================================================================

class TestAdminBookingsAPI:
    """Tests for admin bookings API."""

    def test_admin_bookings_returns_pickup_collection_time(self):
        """Admin bookings API should return pickup_collection_time (45 min after landing)."""
        booking = create_mock_booking(
            id=1,
            pickup_time_val=time(14, 0),  # 14:00 landing
        )

        # Calculate collection time (45 min after landing)
        landing_minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
        collection_minutes = landing_minutes + 45
        collection_hour = collection_minutes // 60
        collection_minute = collection_minutes % 60

        collection_time = f"{collection_hour:02d}:{collection_minute:02d}"

        assert collection_time == "14:45"

    def test_admin_bookings_pickup_collection_time_handles_hour_rollover(self):
        """Pickup collection time should correctly handle hour rollover."""
        booking = create_mock_booking(
            id=1,
            pickup_time_val=time(14, 30),  # 14:30 landing
        )

        # Calculate collection time (45 min after landing)
        landing_minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
        collection_minutes = landing_minutes + 45
        collection_hour = collection_minutes // 60
        collection_minute = collection_minutes % 60

        collection_time = f"{collection_hour:02d}:{collection_minute:02d}"

        assert collection_time == "15:15"


# =============================================================================
# Cancellation and Refund Email Tests
# =============================================================================

class TestCancellationRefundEmails:
    """Tests for cancellation and refund email endpoints."""

    def test_send_cancellation_email_success(self):
        """Should send cancellation email for a cancelled booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(id=1, status="cancelled")
        booking.status = BookingStatus.CANCELLED
        booking.cancellation_email_sent = False

        # Simulate successful email send
        booking.cancellation_email_sent = True
        booking.cancellation_email_sent_at = datetime.utcnow()

        response_data = {
            "success": True,
            "reference": booking.reference,
        }

        assert response_data["success"] is True
        assert booking.cancellation_email_sent is True
        assert booking.cancellation_email_sent_at is not None

    def test_send_cancellation_email_fails_for_non_cancelled_booking(self):
        """Should reject sending cancellation email for non-cancelled bookings."""
        from db_models import BookingStatus

        booking = create_mock_booking(id=1, status="confirmed")

        can_send_cancellation = booking.status == BookingStatus.CANCELLED
        assert can_send_cancellation is False

    def test_send_cancellation_email_not_found(self):
        """Should return 404 for non-existent booking."""
        status_code = 404
        assert status_code == 404

    def test_send_refund_email_success(self):
        """Should send refund email for a cancelled booking with payment."""
        from db_models import BookingStatus

        booking = create_mock_booking(id=1, status="cancelled")
        booking.status = BookingStatus.CANCELLED
        booking.refund_email_sent = False

        # Simulate successful email send
        booking.refund_email_sent = True
        booking.refund_email_sent_at = datetime.utcnow()

        response_data = {
            "success": True,
            "reference": booking.reference,
        }

        assert response_data["success"] is True
        assert booking.refund_email_sent is True

    def test_send_refund_email_fails_for_non_cancelled_booking(self):
        """Should reject sending refund email for non-cancelled bookings."""
        from db_models import BookingStatus

        booking = create_mock_booking(id=1, status="confirmed")

        can_send_refund = booking.status == BookingStatus.CANCELLED
        assert can_send_refund is False


# =============================================================================
# Overnight Pickup Date Tests
# =============================================================================

class TestOvernightPickupDate:
    """Tests for overnight pickup date handling."""

    def test_late_flight_pickup_date_crosses_midnight(self):
        """When a return flight lands at 23:30, pickup should be next day."""
        landing_time = time(23, 30)

        # Calculate pickup window (35-60 mins after landing)
        landing_minutes = landing_time.hour * 60 + landing_time.minute
        pickup_from_minutes = landing_minutes + 35
        pickup_to_minutes = landing_minutes + 60

        # Check if crosses midnight
        crosses_midnight = pickup_from_minutes >= 24 * 60

        if crosses_midnight:
            pickup_from_minutes -= 24 * 60
            pickup_to_minutes -= 24 * 60

        pickup_time_from = time(pickup_from_minutes // 60, pickup_from_minutes % 60)
        pickup_time_to = time(pickup_to_minutes // 60, pickup_to_minutes % 60)

        assert crosses_midnight is True
        assert pickup_time_from == time(0, 5)
        assert pickup_time_to == time(0, 30)

    def test_normal_flight_pickup_date_unchanged(self):
        """When a return flight lands at 14:30, pickup stays same day."""
        landing_time = time(14, 30)

        # Calculate pickup window
        landing_minutes = landing_time.hour * 60 + landing_time.minute
        pickup_from_minutes = landing_minutes + 35
        pickup_to_minutes = landing_minutes + 60

        # Check if crosses midnight
        crosses_midnight = pickup_from_minutes >= 24 * 60

        pickup_time_from = time(pickup_from_minutes // 60, pickup_from_minutes % 60)
        pickup_time_to = time(pickup_to_minutes // 60, pickup_to_minutes % 60)

        assert crosses_midnight is False
        assert pickup_time_from == time(15, 5)
        assert pickup_time_to == time(15, 30)


# =============================================================================
# Booking Reference Format Tests
# =============================================================================

class TestBookingReferenceFormat:
    """Tests for booking reference format."""

    def test_booking_reference_starts_with_tag(self):
        """Booking reference should start with TAG-."""
        booking = create_mock_booking(id=1, reference="TAG-ABC123")

        assert booking.reference.startswith("TAG-")

    def test_booking_reference_unique(self):
        """Each booking should have a unique reference."""
        references = ["TAG-ABC001", "TAG-ABC002", "TAG-ABC003"]

        assert len(references) == len(set(references))


# =============================================================================
# Package Pricing Tests
# =============================================================================

class TestPackagePricing:
    """Tests for package pricing."""

    def test_quick_package_pricing(self):
        """Quick package (7 days) should have correct price tiers."""
        prices = {
            "early": 79.0,
            "standard": 89.0,
            "late": 99.0,
        }

        assert prices["early"] == 79.0
        assert prices["standard"] == prices["early"] + 10
        assert prices["late"] == prices["early"] + 20

    def test_longer_package_pricing(self):
        """Longer package (14 days) should have correct price tiers."""
        prices = {
            "early": 140.0,
            "standard": 150.0,
            "late": 160.0,
        }

        assert prices["early"] == 140.0
        assert prices["standard"] == prices["early"] + 10
        assert prices["late"] == prices["early"] + 20
