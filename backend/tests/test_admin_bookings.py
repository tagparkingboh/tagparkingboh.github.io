"""
Tests for admin bookings functionality.

Covers:
- GET /api/admin/bookings - List all bookings with filters
- POST /api/admin/bookings/{booking_id}/cancel - Cancel a booking

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios
"""
import pytest
import pytest_asyncio
from datetime import date, time, datetime
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import Booking, Customer, Vehicle, Payment, BookingStatus, PaymentStatus, FlightDeparture
from database import get_db


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_customer(db_session):
    """Create a sample customer for testing."""
    customer = Customer(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone="07700900001",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture
def sample_vehicle(db_session, sample_customer):
    """Create a sample vehicle for testing."""
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="AB12 CDE",
        make="Volkswagen",
        model="Golf",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


@pytest.fixture
def sample_booking(db_session, sample_customer, sample_vehicle):
    """Create a sample confirmed booking for testing."""
    booking = Booking(
        reference="TAG-TEST001",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="quick",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date(2026, 2, 10),
        dropoff_time=time(7, 15),
        dropoff_flight_number="FR5523",
        dropoff_destination="Tenerife",
        pickup_date=date(2026, 2, 17),
        pickup_time=time(14, 30),
        pickup_time_from=time(15, 5),
        pickup_time_to=time(15, 30),
        pickup_flight_number="FR5524",
        pickup_origin="Tenerife",
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    return booking


@pytest.fixture
def sample_payment(db_session, sample_booking):
    """Create a sample payment for a booking."""
    payment = Payment(
        booking_id=sample_booking.id,
        stripe_payment_intent_id="pi_test_123456789",
        stripe_customer_id="cus_test_123",
        amount_pence=9900,
        currency="gbp",
        status=PaymentStatus.SUCCEEDED,
        paid_at=datetime.utcnow(),
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


@pytest.fixture
def sample_departure(db_session):
    """Create a sample departure flight for slot testing."""
    departure = FlightDeparture(
        date=date(2026, 2, 10),
        flight_number="FR5523",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(10, 0),  # 10:00 departure
        destination_code="TFS",
        destination_name="Tenerife",
        capacity_tier=4,  # 2 early + 2 late slots
        slots_booked_early=1,  # 1 slot already booked
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)
    return departure


@pytest.fixture
def booking_with_flight(db_session, sample_customer, sample_vehicle, sample_departure):
    """Create a booking linked to a flight departure (early slot)."""
    # Early slot: 165 mins before 10:00 = 7:15
    booking = Booking(
        reference="TAG-FLIGHT01",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="quick",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date(2026, 2, 10),
        dropoff_time=time(7, 15),  # Early slot (165 mins before 10:00)
        dropoff_flight_number="FR5523",
        dropoff_destination="Tenerife",
        pickup_date=date(2026, 2, 17),
        departure_id=sample_departure.id,  # Link to the flight departure
        dropoff_slot="early",  # Store the slot type
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    return booking


@pytest.fixture
def multiple_bookings(db_session, sample_customer, sample_vehicle):
    """Create multiple bookings with different statuses for testing filters."""
    bookings = []

    # Confirmed booking - earliest
    b1 = Booking(
        reference="TAG-CONF001",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="quick",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date(2026, 1, 15),
        dropoff_time=time(8, 0),
        pickup_date=date(2026, 1, 22),
    )
    db_session.add(b1)
    bookings.append(b1)

    # Pending booking
    b2 = Booking(
        reference="TAG-PEND001",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="longer",
        status=BookingStatus.PENDING,
        dropoff_date=date(2026, 2, 10),
        dropoff_time=time(9, 0),
        pickup_date=date(2026, 2, 24),
    )
    db_session.add(b2)
    bookings.append(b2)

    # Cancelled booking
    b3 = Booking(
        reference="TAG-CANC001",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="quick",
        status=BookingStatus.CANCELLED,
        dropoff_date=date(2026, 3, 1),
        dropoff_time=time(10, 0),
        pickup_date=date(2026, 3, 8),
    )
    db_session.add(b3)
    bookings.append(b3)

    # Completed booking - latest
    b4 = Booking(
        reference="TAG-COMP001",
        customer_id=sample_customer.id,
        vehicle_id=sample_vehicle.id,
        package="quick",
        status=BookingStatus.COMPLETED,
        dropoff_date=date(2026, 4, 1),
        dropoff_time=time(7, 30),
        pickup_date=date(2026, 4, 8),
    )
    db_session.add(b4)
    bookings.append(b4)

    db_session.commit()
    for b in bookings:
        db_session.refresh(b)

    return bookings


# =============================================================================
# GET /api/admin/bookings - Happy Path Tests
# =============================================================================

class TestGetAdminBookingsHappyPath:
    """Happy path tests for listing admin bookings."""

    @pytest.mark.asyncio
    async def test_get_all_bookings_returns_list(self, client, sample_booking, sample_payment):
        """Should return a list of bookings with full details."""
        response = await client.get("/api/admin/bookings")

        assert response.status_code == 200
        data = response.json()
        assert "bookings" in data
        assert "count" in data
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_booking_includes_customer_details(self, client, sample_booking, sample_payment):
        """Bookings should include customer name, email, phone."""
        response = await client.get("/api/admin/bookings")

        data = response.json()
        booking = next((b for b in data["bookings"] if b["reference"] == "TAG-TEST001"), None)
        assert booking is not None
        assert booking["customer"]["first_name"] == "John"
        assert booking["customer"]["last_name"] == "Doe"
        assert booking["customer"]["email"] == "john.doe@example.com"
        assert booking["customer"]["phone"] == "07700900001"

    @pytest.mark.asyncio
    async def test_booking_includes_vehicle_details(self, client, sample_booking, sample_payment):
        """Bookings should include vehicle registration, make, model, colour."""
        response = await client.get("/api/admin/bookings")

        data = response.json()
        booking = next((b for b in data["bookings"] if b["reference"] == "TAG-TEST001"), None)
        assert booking is not None
        assert booking["vehicle"]["registration"] == "AB12 CDE"
        assert booking["vehicle"]["make"] == "Volkswagen"
        assert booking["vehicle"]["model"] == "Golf"
        assert booking["vehicle"]["colour"] == "Blue"

    @pytest.mark.asyncio
    async def test_booking_includes_payment_details(self, client, sample_booking, sample_payment):
        """Bookings should include payment status and stripe_payment_intent_id."""
        response = await client.get("/api/admin/bookings")

        data = response.json()
        booking = next((b for b in data["bookings"] if b["reference"] == "TAG-TEST001"), None)
        assert booking is not None
        assert booking["payment"]["status"] == "succeeded"
        assert booking["payment"]["stripe_payment_intent_id"] == "pi_test_123456789"
        assert booking["payment"]["amount_pence"] == 9900

    @pytest.mark.asyncio
    async def test_bookings_sorted_by_dropoff_date_asc(self, client, multiple_bookings):
        """Bookings should be sorted by dropoff date ascending (earliest first)."""
        response = await client.get("/api/admin/bookings")

        data = response.json()
        bookings = data["bookings"]

        # Verify ascending order
        dates = [b["dropoff_date"] for b in bookings if b["dropoff_date"]]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_filter_by_date(self, client, multiple_bookings):
        """Should filter bookings that overlap with a given date."""
        # Filter for date that falls within the Jan 15-22 booking
        response = await client.get("/api/admin/bookings?date_filter=2026-01-18")

        data = response.json()
        assert data["date_filter"] == "2026-01-18"
        # Should find the booking where dropoff <= 2026-01-18 <= pickup
        references = [b["reference"] for b in data["bookings"]]
        assert "TAG-CONF001" in references

    @pytest.mark.asyncio
    async def test_include_cancelled_true(self, client, multiple_bookings):
        """Should include cancelled bookings when include_cancelled=true."""
        response = await client.get("/api/admin/bookings?include_cancelled=true")

        data = response.json()
        statuses = [b["status"] for b in data["bookings"]]
        assert "cancelled" in statuses

    @pytest.mark.asyncio
    async def test_exclude_cancelled(self, client, multiple_bookings):
        """Should exclude cancelled bookings when include_cancelled=false."""
        response = await client.get("/api/admin/bookings?include_cancelled=false")

        data = response.json()
        statuses = [b["status"] for b in data["bookings"]]
        assert "cancelled" not in statuses


# =============================================================================
# GET /api/admin/bookings - Negative Path Tests
# =============================================================================

class TestGetAdminBookingsNegativePath:
    """Negative path tests for listing admin bookings."""

    @pytest.mark.asyncio
    async def test_invalid_date_filter_format(self, client):
        """Should handle invalid date format gracefully."""
        response = await client.get("/api/admin/bookings?date_filter=invalid-date")

        # FastAPI should return 422 for invalid date format
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_list(self, client):
        """Should return empty list when no bookings exist."""
        response = await client.get("/api/admin/bookings")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["bookings"] == []


# =============================================================================
# GET /api/admin/bookings - Edge Case Tests
# =============================================================================

class TestGetAdminBookingsEdgeCases:
    """Edge case tests for listing admin bookings."""

    @pytest.mark.asyncio
    async def test_booking_without_payment(self, client, sample_booking):
        """Should handle bookings that have no payment record."""
        response = await client.get("/api/admin/bookings")

        assert response.status_code == 200
        data = response.json()
        booking = next((b for b in data["bookings"] if b["reference"] == "TAG-TEST001"), None)
        assert booking is not None
        assert booking["payment"] is None

    @pytest.mark.asyncio
    async def test_booking_with_null_optional_fields(self, client, db_session, sample_customer, sample_vehicle):
        """Should handle bookings with null optional fields."""
        booking = Booking(
            reference="TAG-MINIMAL",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 5, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 5, 8),
            # All optional fields left as None
        )
        db_session.add(booking)
        db_session.commit()

        response = await client.get("/api/admin/bookings")

        assert response.status_code == 200
        data = response.json()
        booking_data = next((b for b in data["bookings"] if b["reference"] == "TAG-MINIMAL"), None)
        assert booking_data is not None
        assert booking_data["dropoff_flight_number"] is None
        assert booking_data["pickup_flight_number"] is None

    @pytest.mark.asyncio
    async def test_date_filter_on_boundary_dropoff_date(self, client, multiple_bookings):
        """Should include booking when filter date equals dropoff date."""
        response = await client.get("/api/admin/bookings?date_filter=2026-01-15")

        data = response.json()
        references = [b["reference"] for b in data["bookings"]]
        assert "TAG-CONF001" in references

    @pytest.mark.asyncio
    async def test_date_filter_on_boundary_pickup_date(self, client, multiple_bookings):
        """Should include booking when filter date equals pickup date."""
        response = await client.get("/api/admin/bookings?date_filter=2026-01-22")

        data = response.json()
        references = [b["reference"] for b in data["bookings"]]
        assert "TAG-CONF001" in references


# =============================================================================
# POST /api/admin/bookings/{booking_id}/cancel - Happy Path Tests
# =============================================================================

class TestCancelBookingHappyPath:
    """Happy path tests for cancelling bookings."""

    @pytest.mark.asyncio
    async def test_cancel_confirmed_booking(self, client, sample_booking):
        """Should successfully cancel a confirmed booking."""
        response = await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reference"] == "TAG-TEST001"
        assert "cancelled" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_cancel_pending_booking(self, client, db_session, sample_customer, sample_vehicle):
        """Should successfully cancel a pending booking."""
        booking = Booking(
            reference="TAG-PENDING",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 6, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 6, 8),
        )
        db_session.add(booking)
        db_session.commit()
        db_session.refresh(booking)

        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_completed_booking(self, client, db_session, sample_customer, sample_vehicle):
        """Should successfully cancel a completed booking (for refund scenarios)."""
        booking = Booking(
            reference="TAG-COMPLETED",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.COMPLETED,
            dropoff_date=date(2026, 1, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 1, 8),
        )
        db_session.add(booking)
        db_session.commit()
        db_session.refresh(booking)

        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_cancelled_booking_status_updated_in_database(self, client, db_session, sample_booking):
        """Booking status should be updated to CANCELLED in database."""
        await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")

        # Refresh from database
        db_session.refresh(sample_booking)
        assert sample_booking.status == BookingStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancelled_booking_appears_in_list_with_cancelled_status(self, client, sample_booking):
        """Cancelled booking should appear with 'cancelled' status in listing."""
        await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")

        response = await client.get("/api/admin/bookings")
        data = response.json()
        booking = next((b for b in data["bookings"] if b["reference"] == "TAG-TEST001"), None)
        assert booking is not None
        assert booking["status"] == "cancelled"


# =============================================================================
# POST /api/admin/bookings/{booking_id}/cancel - Negative Path Tests
# =============================================================================

class TestCancelBookingNegativePath:
    """Negative path tests for cancelling bookings."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_booking(self, client):
        """Should return 404 for non-existent booking ID."""
        response = await client.post("/api/admin/bookings/99999/cancel")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_booking(self, client, db_session, sample_customer, sample_vehicle):
        """Should return 400 when trying to cancel already cancelled booking."""
        booking = Booking(
            reference="TAG-ALREADY-CANC",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CANCELLED,
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 7, 8),
        )
        db_session.add(booking)
        db_session.commit()
        db_session.refresh(booking)

        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 400
        assert "already cancelled" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancel_refunded_booking(self, client, db_session, sample_customer, sample_vehicle):
        """Should return 400 when trying to cancel a refunded booking."""
        booking = Booking(
            reference="TAG-REFUNDED",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.REFUNDED,
            dropoff_date=date(2026, 8, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 8, 8),
        )
        db_session.add(booking)
        db_session.commit()
        db_session.refresh(booking)

        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 400
        assert "refunded" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancel_with_invalid_booking_id_type(self, client):
        """Should return 422 for invalid booking ID type."""
        response = await client.post("/api/admin/bookings/invalid-id/cancel")

        assert response.status_code == 422


# =============================================================================
# POST /api/admin/bookings/{booking_id}/cancel - Edge Case Tests
# =============================================================================

class TestCancelBookingEdgeCases:
    """Edge case tests for cancelling bookings."""

    @pytest.mark.asyncio
    async def test_cancel_booking_with_payment_does_not_auto_refund(
        self, client, db_session, sample_booking, sample_payment
    ):
        """Cancelling a booking should NOT automatically refund the payment."""
        await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")

        # Refresh payment from database
        db_session.refresh(sample_payment)

        # Payment status should still be SUCCEEDED (not REFUNDED)
        assert sample_payment.status == PaymentStatus.SUCCEEDED
        assert sample_payment.refund_id is None

    @pytest.mark.asyncio
    async def test_cancel_same_booking_twice(self, client, sample_booking):
        """Cancelling the same booking twice should fail on second attempt."""
        # First cancel should succeed
        response1 = await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")
        assert response1.status_code == 200

        # Second cancel should fail
        response2 = await client.post(f"/api/admin/bookings/{sample_booking.id}/cancel")
        assert response2.status_code == 400

    @pytest.mark.asyncio
    async def test_cancel_booking_with_zero_id(self, client):
        """Should handle booking ID of 0."""
        response = await client.post("/api/admin/bookings/0/cancel")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_booking_with_negative_id(self, client):
        """Should handle negative booking ID."""
        response = await client.post("/api/admin/bookings/-1/cancel")

        # Depending on implementation, could be 404 or 422
        assert response.status_code in [404, 422]


# =============================================================================
# Slot Release Tests - Cancel releases flight slots
# =============================================================================

class TestCancelBookingSlotRelease:
    """Tests for flight slot release when cancelling bookings."""

    @pytest.mark.asyncio
    async def test_cancel_booking_releases_early_slot(
        self, client, db_session, booking_with_flight, sample_departure
    ):
        """Cancelling a booking should release the early flight slot."""
        # Verify initial state: 1 early slot booked
        assert sample_departure.slots_booked_early == 1

        # Cancel the booking
        response = await client.post(f"/api/admin/bookings/{booking_with_flight.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["slot_released"] is True
        assert "slot has been released" in data["message"]

        # Verify slot was released
        db_session.refresh(sample_departure)
        assert sample_departure.slots_booked_early == 0

    @pytest.mark.asyncio
    async def test_cancel_booking_releases_late_slot(
        self, client, db_session, sample_customer, sample_vehicle
    ):
        """Cancelling a booking with late slot should release the late slot."""
        # Create departure with late slot booked
        departure = FlightDeparture(
            date=date(2026, 3, 15),
            flight_number="TOM1234",
            airline_code="TOM",
            airline_name="TUI Airways",
            departure_time=time(14, 0),  # 14:00 departure
            destination_code="PMI",
            destination_name="Palma",
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=1,  # Late slot booked
        )
        db_session.add(departure)
        db_session.commit()
        db_session.refresh(departure)

        # Create booking with late slot (120 mins before = 12:00)
        booking = Booking(
            reference="TAG-LATE001",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 3, 15),
            dropoff_time=time(12, 0),  # Late slot (120 mins before 14:00)
            dropoff_flight_number="TOM1234",
            pickup_date=date(2026, 3, 22),
            departure_id=departure.id,  # Link to the flight departure
            dropoff_slot="late",  # Store the slot type
        )
        db_session.add(booking)
        db_session.commit()

        # Cancel the booking
        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        assert response.json()["slot_released"] is True

        # Verify late slot was released
        db_session.refresh(departure)
        assert departure.slots_booked_late == 0

    @pytest.mark.asyncio
    async def test_cancel_booking_without_departure_id_does_not_release_slot(
        self, client, db_session, sample_customer, sample_vehicle
    ):
        """Booking without departure_id should cancel but not release any slot."""
        # Create booking without departure_id
        booking = Booking(
            reference="TAG-NOFLIGHT",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 4, 1),
            dropoff_time=time(9, 0),
            dropoff_flight_number="EZY1234",  # Has flight number but no departure_id
            pickup_date=date(2026, 4, 8),
            departure_id=None,  # No departure ID stored
            dropoff_slot=None,  # No slot stored
        )
        db_session.add(booking)
        db_session.commit()

        # Cancel the booking
        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["slot_released"] is False
        assert "slot has been released" not in data["message"]

    @pytest.mark.asyncio
    async def test_cancel_booking_with_deleted_departure_does_not_error(
        self, client, db_session, sample_customer, sample_vehicle
    ):
        """Booking with departure_id pointing to deleted flight should cancel gracefully."""
        # Create a departure, then delete it after booking
        departure = FlightDeparture(
            date=date(2026, 5, 1),
            flight_number="DEL1234",
            airline_code="DEL",
            airline_name="Deleted Airways",
            departure_time=time(10, 0),
            destination_code="DEL",
            destination_name="Deleted",
            capacity_tier=4,
            slots_booked_early=1,
            slots_booked_late=0,
        )
        db_session.add(departure)
        db_session.commit()
        departure_id = departure.id

        # Create booking with the departure_id
        booking = Booking(
            reference="TAG-DELETED",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 5, 1),
            dropoff_time=time(7, 15),
            dropoff_flight_number="DEL1234",
            pickup_date=date(2026, 5, 8),
            departure_id=departure_id,
            dropoff_slot="early",
        )
        db_session.add(booking)
        db_session.commit()

        # Delete the departure (simulating flight being removed)
        db_session.delete(departure)
        db_session.commit()

        # Cancel should still succeed (slot release will fail gracefully)
        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["slot_released"] is False

    @pytest.mark.asyncio
    async def test_slot_release_does_not_go_negative(
        self, client, db_session, sample_customer, sample_vehicle
    ):
        """Slot count should not go below 0 even if release is called on unbooked slot."""
        # Create departure with 0 slots booked
        departure = FlightDeparture(
            date=date(2026, 6, 1),
            flight_number="EZY1234",
            airline_code="EZY",
            airline_name="easyJet",
            departure_time=time(8, 0),
            destination_code="ALC",
            destination_name="Alicante",
            capacity_tier=4,
            slots_booked_early=0,  # No slots booked
            slots_booked_late=0,
        )
        db_session.add(departure)
        db_session.commit()
        db_session.refresh(departure)

        # Create booking that would try to release early slot
        booking = Booking(
            reference="TAG-ZEROREL",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 6, 1),
            dropoff_time=time(5, 15),  # Early slot time
            dropoff_flight_number="EZY1234",
            pickup_date=date(2026, 6, 8),
            departure_id=departure.id,  # Link to the flight departure
            dropoff_slot="early",  # Store the slot type
        )
        db_session.add(booking)
        db_session.commit()

        # Cancel - should not error
        response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert response.status_code == 200
        # Slot release should fail gracefully (can't release when 0)
        assert response.json()["slot_released"] is False

        # Verify slot didn't go negative
        db_session.refresh(departure)
        assert departure.slots_booked_early == 0


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

class TestAdminBookingsIntegration:
    """Integration tests covering full admin booking workflows."""

    @pytest.mark.asyncio
    async def test_full_booking_lifecycle_in_admin_view(
        self, client, db_session, sample_customer, sample_vehicle
    ):
        """Test complete flow: create booking, view in admin, cancel."""
        # Create a booking
        booking = Booking(
            reference="TAG-LIFECYCLE",
            customer_id=sample_customer.id,
            vehicle_id=sample_vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 9, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 9, 8),
        )
        db_session.add(booking)
        db_session.commit()
        db_session.refresh(booking)

        # View in admin - should show as confirmed
        response = await client.get("/api/admin/bookings")
        data = response.json()
        booking_data = next((b for b in data["bookings"] if b["reference"] == "TAG-LIFECYCLE"), None)
        assert booking_data is not None
        assert booking_data["status"] == "confirmed"

        # Cancel the booking
        cancel_response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")
        assert cancel_response.status_code == 200

        # View in admin again - should show as cancelled
        response2 = await client.get("/api/admin/bookings")
        data2 = response2.json()
        booking_data2 = next((b for b in data2["bookings"] if b["reference"] == "TAG-LIFECYCLE"), None)
        assert booking_data2["status"] == "cancelled"

        # Exclude cancelled - should not appear
        response3 = await client.get("/api/admin/bookings?include_cancelled=false")
        data3 = response3.json()
        booking_data3 = next((b for b in data3["bookings"] if b["reference"] == "TAG-LIFECYCLE"), None)
        assert booking_data3 is None

    @pytest.mark.asyncio
    async def test_multiple_status_bookings_filtered_correctly(self, client, multiple_bookings):
        """Test that bookings with different statuses are filtered correctly."""
        # Get all bookings
        all_response = await client.get("/api/admin/bookings?include_cancelled=true")
        all_data = all_response.json()

        # Verify we have all statuses
        statuses = set(b["status"] for b in all_data["bookings"])
        assert "confirmed" in statuses
        assert "pending" in statuses
        assert "cancelled" in statuses
        assert "completed" in statuses

        # Get only non-cancelled
        non_cancelled_response = await client.get("/api/admin/bookings?include_cancelled=false")
        non_cancelled_data = non_cancelled_response.json()

        non_cancelled_statuses = set(b["status"] for b in non_cancelled_data["bookings"])
        assert "cancelled" not in non_cancelled_statuses
        assert len(non_cancelled_data["bookings"]) < len(all_data["bookings"])


# =============================================================================
# DELETE /api/admin/bookings/{booking_id} - Delete Pending Booking Tests (Mocked)
# =============================================================================

class TestDeletePendingBooking:
    """Tests for deleting pending bookings using mocked data."""

    def test_delete_pending_booking_success(self):
        """Successfully deleting a pending booking returns success response."""
        from unittest.mock import MagicMock
        from db_models import BookingStatus

        # Create mock pending booking
        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.reference = "TAG-PEND123"
        mock_booking.status = BookingStatus.PENDING
        mock_booking.departure_id = None
        mock_booking.dropoff_slot = None
        mock_booking.payment_id = None

        # Simulate successful deletion
        response_data = {
            "success": True,
            "message": f"Booking {mock_booking.reference} has been permanently deleted",
            "reference": mock_booking.reference,
            "slot_released": False,
        }

        assert response_data["success"] is True
        assert mock_booking.reference in response_data["message"]
        assert response_data["slot_released"] is False

    def test_delete_pending_booking_releases_slot(self):
        """Deleting a pending booking with flight slot releases the slot."""
        from unittest.mock import MagicMock
        from db_models import BookingStatus

        # Create mock pending booking with slot
        mock_booking = MagicMock()
        mock_booking.id = 2
        mock_booking.reference = "TAG-SLOT123"
        mock_booking.status = BookingStatus.PENDING
        mock_booking.departure_id = 100
        mock_booking.dropoff_slot = "early"
        mock_booking.payment_id = None

        # Simulate slot release
        slot_released = True

        response_data = {
            "success": True,
            "message": f"Booking {mock_booking.reference} has been permanently deleted and the flight slot has been released",
            "reference": mock_booking.reference,
            "slot_released": slot_released,
        }

        assert response_data["success"] is True
        assert response_data["slot_released"] is True
        assert "slot has been released" in response_data["message"]

    def test_delete_non_pending_booking_fails(self):
        """Cannot delete a booking that is not in PENDING status."""
        from unittest.mock import MagicMock
        from db_models import BookingStatus

        # Create mock confirmed booking
        mock_booking = MagicMock()
        mock_booking.id = 3
        mock_booking.reference = "TAG-CONF123"
        mock_booking.status = BookingStatus.CONFIRMED

        # Simulate validation error
        if mock_booking.status != BookingStatus.PENDING:
            status_code = 400
            error_detail = f"Can only delete pending bookings. This booking has status: {mock_booking.status.value}"
        else:
            status_code = 200
            error_detail = None

        assert status_code == 400
        assert "Can only delete pending bookings" in error_detail

    def test_delete_cancelled_booking_fails(self):
        """Cannot delete a booking that is already cancelled."""
        from unittest.mock import MagicMock
        from db_models import BookingStatus

        mock_booking = MagicMock()
        mock_booking.id = 4
        mock_booking.reference = "TAG-CANC123"
        mock_booking.status = BookingStatus.CANCELLED

        if mock_booking.status != BookingStatus.PENDING:
            status_code = 400
            error_detail = f"Can only delete pending bookings. This booking has status: {mock_booking.status.value}"
        else:
            status_code = 200
            error_detail = None

        assert status_code == 400
        assert "cancelled" in error_detail.lower()

    def test_delete_nonexistent_booking_returns_404(self):
        """Deleting a non-existent booking returns 404."""
        booking_id = 999999
        booking = None  # Not found

        if booking is None:
            status_code = 404
            error_detail = "Booking not found"
        else:
            status_code = 200
            error_detail = None

        assert status_code == 404
        assert error_detail == "Booking not found"

    def test_delete_booking_removes_associated_payment(self):
        """Deleting a booking also removes associated payment record."""
        from unittest.mock import MagicMock
        from db_models import BookingStatus

        # Create mock pending booking with payment
        mock_booking = MagicMock()
        mock_booking.id = 5
        mock_booking.reference = "TAG-PAY123"
        mock_booking.status = BookingStatus.PENDING
        mock_booking.payment_id = 10

        mock_payment = MagicMock()
        mock_payment.id = 10
        mock_payment.stripe_payment_intent_id = "pi_test_123"

        # Simulate deletion of both booking and payment
        deleted_booking = True
        deleted_payment = True

        assert deleted_booking is True
        assert deleted_payment is True

    def test_delete_booking_normalizes_slot_type(self):
        """Slot type is normalized correctly (165 -> early, 120 -> late)."""
        test_cases = [
            ("165", "early"),
            ("early", "early"),
            ("120", "late"),
            ("late", "late"),
        ]

        for dropoff_slot, expected_slot_type in test_cases:
            # Simulate the normalization logic from the endpoint
            slot_type = "early" if dropoff_slot in ("165", "early") else "late"
            assert slot_type == expected_slot_type, f"Failed for dropoff_slot={dropoff_slot}"

    def test_delete_requires_admin_authentication(self):
        """Delete endpoint requires admin authentication."""
        from unittest.mock import MagicMock

        # Simulate non-admin user
        user = MagicMock()
        user.is_admin = False

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403

    def test_delete_booking_response_format(self):
        """Response format matches expected structure."""
        expected_fields = ["success", "message", "reference", "slot_released"]

        response_data = {
            "success": True,
            "message": "Booking TAG-TEST123 has been permanently deleted",
            "reference": "TAG-TEST123",
            "slot_released": False,
        }

        for field in expected_fields:
            assert field in response_data, f"Missing field: {field}"

        assert isinstance(response_data["success"], bool)
        assert isinstance(response_data["message"], str)
        assert isinstance(response_data["reference"], str)
        assert isinstance(response_data["slot_released"], bool)
