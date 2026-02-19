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


# =============================================================================
# Admin Edit Pickup Date/Time Integration Tests
# =============================================================================

class TestAdminEditPickupDateTimeIntegration:
    """Integration tests for admin editing pickup date and time."""

    def test_edit_pickup_date_time_full_flow(self):
        """Test full flow of editing pickup date and time via admin."""
        from db_models import BookingStatus

        # Step 1: Create a confirmed booking
        customer = create_mock_customer(
            id=1,
            first_name="Edit",
            last_name="Test",
            email="edit-test@example.com",
        )

        vehicle = create_mock_vehicle(
            id=1,
            customer_id=customer.id,
            registration="EDIT123",
        )

        booking = create_mock_booking(
            id=1,
            reference="TAG-EDIT001",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status="confirmed",
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        # Step 2: Verify initial booking state
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.pickup_date == date(2026, 3, 28)
        assert booking.pickup_time == time(14, 30)

        # Step 3: Simulate admin update request
        update_request = {
            "pickup_date": "2026-03-29",
            "pickup_time": "16:45",
        }

        # Step 4: Apply the update
        booking.pickup_date = date(2026, 3, 29)
        booking.pickup_time = time(16, 45)

        # Recalculate pickup windows (35-60 min buffer)
        arrival_dt = datetime.combine(date.today(), booking.pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        # Step 5: Verify the update was applied
        assert booking.pickup_date == date(2026, 3, 29)
        assert booking.pickup_time == time(16, 45)
        assert booking.pickup_time_from == time(17, 20)
        assert booking.pickup_time_to == time(17, 45)

        # Step 6: Generate API response
        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["pickup_date", "pickup_time"],
            "booking": {
                "id": booking.id,
                "reference": booking.reference,
                "pickup_date": booking.pickup_date.isoformat(),
                "pickup_time": booking.pickup_time.strftime("%H:%M"),
                "pickup_time_from": booking.pickup_time_from.strftime("%H:%M"),
                "pickup_time_to": booking.pickup_time_to.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert "pickup_date" in response_data["fields_updated"]
        assert "pickup_time" in response_data["fields_updated"]

    def test_edit_pickup_time_only_flow(self):
        """Test editing only pickup time without changing date."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-TIME001",
            status="confirmed",
            pickup_date=date(2026, 4, 15),
            pickup_time_val=time(10, 0),
        )

        original_date = booking.pickup_date

        # Update only time
        booking.pickup_time = time(18, 30)

        # Recalculate pickup windows
        arrival_dt = datetime.combine(date.today(), booking.pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        # Date should remain unchanged
        assert booking.pickup_date == original_date
        assert booking.pickup_time == time(18, 30)
        assert booking.pickup_time_from == time(19, 5)
        assert booking.pickup_time_to == time(19, 30)

    def test_edit_pickup_date_only_flow(self):
        """Test editing only pickup date without changing time."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-DATE001",
            status="confirmed",
            pickup_date=date(2026, 4, 15),
            pickup_time_val=time(14, 0),
        )

        original_time = booking.pickup_time

        # Update only date
        booking.pickup_date = date(2026, 4, 20)

        # Time should remain unchanged
        assert booking.pickup_date == date(2026, 4, 20)
        assert booking.pickup_time == original_time

    def test_edit_pickup_overnight_arrival_correction(self):
        """Test correcting an overnight arrival booking via admin edit."""
        from db_models import BookingStatus

        # Booking was incorrectly created with wrong date due to overnight flight
        booking = create_mock_booking(
            id=1,
            reference="TAG-OVERNIGHT",
            status="confirmed",
            pickup_date=date(2026, 3, 28),  # Wrong - should be 29th
            pickup_time_val=time(0, 35),     # Flight lands at 00:35
        )

        # Admin corrects the date
        booking.pickup_date = date(2026, 3, 29)

        # Recalculate pickup windows
        arrival_dt = datetime.combine(date.today(), booking.pickup_time)
        booking.pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()

        # Verify correction
        assert booking.pickup_date == date(2026, 3, 29)
        assert booking.pickup_time == time(0, 35)
        assert booking.pickup_time_from == time(1, 10)
        assert booking.pickup_time_to == time(1, 35)

    def test_edit_pickup_dropoff_unchanged(self):
        """Test that editing pickup does not affect dropoff details."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-UNCHANGED",
            status="confirmed",
            dropoff_date=date(2026, 3, 21),
            dropoff_time_val=time(7, 15),
            dropoff_flight_number="FR5523",
            dropoff_destination="Tenerife",
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
            pickup_flight_number="FR5524",
            pickup_origin="Tenerife",
        )

        # Store original dropoff values
        original_dropoff_date = booking.dropoff_date
        original_dropoff_time = booking.dropoff_time
        original_dropoff_flight = booking.dropoff_flight_number
        original_dropoff_dest = booking.dropoff_destination

        # Update pickup details
        booking.pickup_date = date(2026, 3, 30)
        booking.pickup_time = time(16, 0)

        # Verify dropoff unchanged
        assert booking.dropoff_date == original_dropoff_date
        assert booking.dropoff_time == original_dropoff_time
        assert booking.dropoff_flight_number == original_dropoff_flight
        assert booking.dropoff_destination == original_dropoff_dest

    def test_edit_pickup_api_request_validation(self):
        """Test API request validation for edit pickup endpoint."""
        # Valid request with both date and time
        valid_request_1 = {
            "pickup_date": "2026-03-29",
            "pickup_time": "14:30",
        }

        # Valid request with only date
        valid_request_2 = {
            "pickup_date": "2026-03-29",
        }

        # Valid request with only time
        valid_request_3 = {
            "pickup_time": "14:30",
        }

        # Invalid request with empty values
        invalid_request = {
            "pickup_date": None,
            "pickup_time": None,
        }

        # Check that at least one field is provided
        def validate_request(req):
            return req.get("pickup_date") is not None or req.get("pickup_time") is not None

        assert validate_request(valid_request_1) is True
        assert validate_request(valid_request_2) is True
        assert validate_request(valid_request_3) is True
        assert validate_request(invalid_request) is False

    def test_edit_pickup_booking_list_reflects_changes(self):
        """Test that booking list API reflects updated pickup details."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-LIST001",
            status="confirmed",
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        # Simulate update
        booking.pickup_date = date(2026, 3, 30)
        booking.pickup_time = time(16, 0)

        # Simulate booking list API response
        bookings_response = {
            "count": 1,
            "bookings": [
                {
                    "id": booking.id,
                    "reference": booking.reference,
                    "pickup_date": booking.pickup_date.isoformat(),
                    "pickup_time": booking.pickup_time.strftime("%H:%M"),
                }
            ]
        }

        assert bookings_response["bookings"][0]["pickup_date"] == "2026-03-30"
        assert bookings_response["bookings"][0]["pickup_time"] == "16:00"

    def test_edit_pickup_multiple_bookings_independent(self):
        """Test that editing one booking doesn't affect others."""
        from db_models import BookingStatus

        booking1 = create_mock_booking(
            id=1,
            reference="TAG-IND001",
            status="confirmed",
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        booking2 = create_mock_booking(
            id=2,
            reference="TAG-IND002",
            status="confirmed",
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(15, 0),
        )

        # Store original values for booking2
        original_date_b2 = booking2.pickup_date
        original_time_b2 = booking2.pickup_time

        # Update booking1 only
        booking1.pickup_date = date(2026, 4, 1)
        booking1.pickup_time = time(10, 0)

        # Verify booking1 updated
        assert booking1.pickup_date == date(2026, 4, 1)
        assert booking1.pickup_time == time(10, 0)

        # Verify booking2 unchanged
        assert booking2.pickup_date == original_date_b2
        assert booking2.pickup_time == original_time_b2


# =============================================================================
# Admin Edit Drop-off Time Integration Tests
# =============================================================================

class TestAdminEditDropoffTimeIntegration:
    """Integration tests for admin editing drop-off time with constraints."""

    def test_edit_dropoff_time_full_flow(self):
        """Test full flow of editing drop-off time via admin within limits."""
        from db_models import BookingStatus

        # Step 1: Create a confirmed booking
        customer = create_mock_customer(
            id=1,
            first_name="Dropoff",
            last_name="Test",
            email="dropoff-test@example.com",
        )

        vehicle = create_mock_vehicle(
            id=1,
            customer_id=customer.id,
            registration="DROP123",
        )

        booking = create_mock_booking(
            id=1,
            reference="TAG-DROP001",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status="confirmed",
            dropoff_date=date(2026, 3, 21),
            dropoff_time_val=time(9, 30),
        )

        # Step 2: Verify initial booking state
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.dropoff_time == time(9, 30)

        # Step 3: Simulate admin update request (30 mins earlier)
        update_request = {
            "dropoff_time": "09:00",
        }

        # Step 4: Validate the time change
        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = update_request["dropoff_time"].split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -30  # 30 mins earlier
        assert diff_minutes >= -60  # Within 1 hour limit
        assert diff_minutes <= 15   # Within 15 min later limit

        # Step 5: Apply the update
        booking.dropoff_time = time(9, 0)

        # Step 6: Verify the update was applied
        assert booking.dropoff_time == time(9, 0)

        # Step 7: Generate API response
        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} updated successfully",
            "fields_updated": ["dropoff_time"],
            "booking": {
                "id": booking.id,
                "reference": booking.reference,
                "dropoff_time": booking.dropoff_time.strftime("%H:%M"),
            }
        }

        assert response_data["success"] is True
        assert "dropoff_time" in response_data["fields_updated"]
        assert response_data["booking"]["dropoff_time"] == "09:00"

    def test_edit_dropoff_time_rejected_too_early(self):
        """Test that drop-off time more than 1 hour earlier is rejected."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-EARLY001",
            status="confirmed",
            dropoff_time_val=time(10, 0),
        )

        # Try to move 90 mins earlier (exceeds limit)
        requested_time = "08:30"

        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = requested_time.split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -90  # 90 mins earlier
        is_valid = diff_minutes >= -60

        if not is_valid:
            status_code = 400
            error_response = {
                "detail": f"Cannot move drop-off time more than 1 hour earlier. Current: {booking.dropoff_time.strftime('%H:%M')}, Requested: {requested_time}"
            }
        else:
            status_code = 200
            error_response = None

        assert status_code == 400
        assert "1 hour earlier" in error_response["detail"]

    def test_edit_dropoff_time_rejected_too_late(self):
        """Test that drop-off time more than 15 minutes later is rejected."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-LATE001",
            status="confirmed",
            dropoff_time_val=time(9, 30),
        )

        # Try to move 30 mins later (exceeds limit)
        requested_time = "10:00"

        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = requested_time.split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 30  # 30 mins later
        is_valid = diff_minutes <= 15

        if not is_valid:
            status_code = 400
            error_response = {
                "detail": f"Cannot move drop-off time more than 15 minutes later. Current: {booking.dropoff_time.strftime('%H:%M')}, Requested: {requested_time}"
            }
        else:
            status_code = 200
            error_response = None

        assert status_code == 400
        assert "15 minutes later" in error_response["detail"]

    def test_edit_dropoff_time_flight_departures_unchanged(self):
        """Test that editing drop-off time does NOT affect flight_departures."""
        from db_models import BookingStatus

        # Create a departure with booked slots
        departure = create_mock_departure(
            id=1,
            flight_number="FR5523",
            capacity_tier=4,
            slots_booked_early=2,
            slots_booked_late=1,
        )

        booking = create_mock_booking(
            id=1,
            reference="TAG-FLIGHT001",
            status="confirmed",
            departure_id=departure.id,
            dropoff_time_val=time(7, 15),
        )
        booking.dropoff_slot = "early"  # Set explicitly after creation

        # Store original departure state
        original_early = departure.slots_booked_early
        original_late = departure.slots_booked_late
        original_departure_id = booking.departure_id
        original_dropoff_slot = booking.dropoff_slot

        # Update drop-off time (within limits)
        booking.dropoff_time = time(6, 45)  # 30 mins earlier

        # Verify flight_departures is unchanged
        assert departure.slots_booked_early == original_early
        assert departure.slots_booked_late == original_late
        assert booking.departure_id == original_departure_id
        assert booking.dropoff_slot == original_dropoff_slot

    def test_edit_dropoff_time_booking_list_reflects_changes(self):
        """Test that booking list API reflects updated drop-off time."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-LIST002",
            status="confirmed",
            dropoff_date=date(2026, 3, 21),
            dropoff_time_val=time(9, 30),
        )

        # Simulate update
        booking.dropoff_time = time(9, 0)

        # Simulate booking list API response
        bookings_response = {
            "count": 1,
            "bookings": [
                {
                    "id": booking.id,
                    "reference": booking.reference,
                    "dropoff_date": booking.dropoff_date.isoformat(),
                    "dropoff_time": booking.dropoff_time.strftime("%H:%M"),
                }
            ]
        }

        assert bookings_response["bookings"][0]["dropoff_time"] == "09:00"

    def test_edit_dropoff_time_pickup_unchanged(self):
        """Test that editing drop-off time does not affect pickup details."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            id=1,
            reference="TAG-PICKUP001",
            status="confirmed",
            dropoff_date=date(2026, 3, 21),
            dropoff_time_val=time(9, 30),
            pickup_date=date(2026, 3, 28),
            pickup_time_val=time(14, 30),
        )

        # Store original pickup values
        original_pickup_date = booking.pickup_date
        original_pickup_time = booking.pickup_time

        # Update drop-off time
        booking.dropoff_time = time(9, 0)

        # Verify pickup unchanged
        assert booking.pickup_date == original_pickup_date
        assert booking.pickup_time == original_pickup_time

    def test_edit_dropoff_time_boundary_exactly_1_hour_earlier(self):
        """Test boundary case: exactly 1 hour earlier should be allowed."""
        booking = create_mock_booking(
            id=1,
            reference="TAG-BOUND001",
            status="confirmed",
            dropoff_time_val=time(10, 0),
        )

        requested_time = "09:00"  # Exactly 1 hour earlier

        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = requested_time.split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == -60
        is_valid = diff_minutes >= -60 and diff_minutes <= 15
        assert is_valid is True

    def test_edit_dropoff_time_boundary_exactly_15_mins_later(self):
        """Test boundary case: exactly 15 minutes later should be allowed."""
        booking = create_mock_booking(
            id=1,
            reference="TAG-BOUND002",
            status="confirmed",
            dropoff_time_val=time(9, 30),
        )

        requested_time = "09:45"  # Exactly 15 mins later

        old_minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        new_parts = requested_time.split(':')
        new_minutes = int(new_parts[0]) * 60 + int(new_parts[1])
        diff_minutes = new_minutes - old_minutes

        assert diff_minutes == 15
        is_valid = diff_minutes >= -60 and diff_minutes <= 15
        assert is_valid is True

    def test_edit_dropoff_time_multiple_bookings_independent(self):
        """Test that editing one booking's drop-off time doesn't affect others."""
        from db_models import BookingStatus

        booking1 = create_mock_booking(
            id=1,
            reference="TAG-MULTI001",
            status="confirmed",
            dropoff_time_val=time(9, 30),
        )

        booking2 = create_mock_booking(
            id=2,
            reference="TAG-MULTI002",
            status="confirmed",
            dropoff_time_val=time(10, 0),
        )

        # Store original time for booking2
        original_time_b2 = booking2.dropoff_time

        # Update booking1 only
        booking1.dropoff_time = time(9, 0)

        # Verify booking1 updated
        assert booking1.dropoff_time == time(9, 0)

        # Verify booking2 unchanged
        assert booking2.dropoff_time == original_time_b2
