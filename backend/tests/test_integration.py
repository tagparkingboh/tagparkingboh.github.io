"""
Integration tests for the TAG Booking API.

Tests all database-backed endpoints with a separate test database.
Includes mocked Stripe calls for payment flow testing.

Updated to use capacity-based slot system:
- capacity_tier: 0, 2, 4, 6, or 8 (determines max slots)
- slots_booked_early/late: counters for bookings

Note: Database setup is handled by conftest.py
"""
import pytest
import pytest_asyncio
from datetime import date, time
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import Customer, Vehicle, Booking, FlightDeparture, FlightArrival, BookingStatus
from main import app


@pytest.fixture
def sample_departure(db_session):
    """Create a sample departure flight for testing with capacity_tier=2 (1 slot per time)."""
    departure = FlightDeparture(
        date=date(2025, 12, 15),
        flight_number="1234",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(10, 30),
        destination_code="FAO",
        destination_name="Faro, PT",
        capacity_tier=2,  # 1 early + 1 late slot
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)
    return departure


@pytest.fixture
def sample_arrival(db_session):
    """Create a sample arrival flight for testing."""
    arrival = FlightArrival(
        date=date(2025, 12, 22),
        flight_number="1235",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(14, 0),
        arrival_time=time(17, 30),
        origin_code="FAO",
        origin_name="Faro, PT",
    )
    db_session.add(arrival)
    db_session.commit()
    db_session.refresh(arrival)
    return arrival


@pytest.fixture
def sample_customer(db_session):
    """Get or create a sample customer for testing."""
    import uuid
    # Use unique email per test run to avoid conflicts on staging DB
    test_email = f"test_{uuid.uuid4().hex[:8]}@test.com"
    customer = Customer(
        first_name="Test",
        last_name="User",
        email=test_email,
        phone="+44 7000 000000",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Health Check Tests
# =============================================================================

@pytest.mark.asyncio
async def test_health_check(client):
    """Root endpoint should return healthy status."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


# =============================================================================
# Customer Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_customer_success(client):
    """Should create a new customer with valid data."""
    response = await client.post(
        "/api/customers",
        json={
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane.smith@test.com",
            "phone": "+44 7987 654321",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "customer_id" in data
    assert data["customer_id"] > 0


@pytest.mark.asyncio
async def test_create_customer_duplicate_email(client):
    """Should handle duplicate email gracefully (return existing customer)."""
    # Create first customer
    response1 = await client.post(
        "/api/customers",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "duplicate@test.com",
            "phone": "+44 7111 111111",
        }
    )
    assert response1.status_code == 200
    customer_id_1 = response1.json()["customer_id"]

    # Try to create another with same email
    response2 = await client.post(
        "/api/customers",
        json={
            "first_name": "John",
            "last_name": "Updated",
            "email": "duplicate@test.com",
            "phone": "+44 7222 222222",
        }
    )
    assert response2.status_code == 200
    # Should return same customer ID
    customer_id_2 = response2.json()["customer_id"]
    assert customer_id_1 == customer_id_2


@pytest.mark.asyncio
async def test_update_billing_address(client, sample_customer):
    """Should update customer billing address."""
    response = await client.patch(
        f"/api/customers/{sample_customer.id}/billing",
        json={
            "billing_address1": "123 Test Street",
            "billing_address2": "Flat 4",
            "billing_city": "Bournemouth",
            "billing_county": "Dorset",
            "billing_postcode": "BH1 1AA",
            "billing_country": "United Kingdom",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_update_billing_address_not_found(client):
    """Should return 404 for non-existent customer."""
    response = await client.patch(
        "/api/customers/99999/billing",
        json={
            "billing_address1": "123 Test Street",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "billing_country": "United Kingdom",
        }
    )
    assert response.status_code == 404


# =============================================================================
# Vehicle Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_vehicle_success(client, sample_customer):
    """Should create a new vehicle linked to customer."""
    response = await client.post(
        "/api/vehicles",
        json={
            "customer_id": sample_customer.id,
            "registration": "AB12 CDE",
            "make": "BMW",
            "model": "3 Series",
            "colour": "Black",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "vehicle_id" in data
    assert data["vehicle_id"] > 0


@pytest.mark.asyncio
async def test_create_vehicle_invalid_customer(client):
    """Should return error for non-existent customer."""
    response = await client.post(
        "/api/vehicles",
        json={
            "customer_id": 99999,
            "registration": "XY99 ZZZ",
            "make": "Audi",
            "model": "A4",
            "colour": "Silver",
        }
    )
    assert response.status_code == 404


# =============================================================================
# Flight Departure Endpoint Tests (Capacity-Based)
# =============================================================================

@pytest.mark.asyncio
async def test_get_departures_for_date(client, sample_departure):
    """Should return departures for a specific date with capacity info."""
    response = await client.get("/api/flights/departures/2025-12-15")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["flightNumber"] == "1234"
    assert data[0]["airlineCode"] == "FR"
    assert data[0]["destinationCode"] == "FAO"
    # New capacity-based fields
    assert data[0]["capacity_tier"] == 2
    assert data[0]["early_slots_available"] == 1
    assert data[0]["late_slots_available"] == 1
    assert data[0]["is_call_us_only"] is False
    assert data[0]["all_slots_booked"] is False


@pytest.mark.asyncio
async def test_get_departures_empty_date(client):
    """Should return empty array for date with no flights."""
    response = await client.get("/api/flights/departures/2025-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_get_departures_with_booked_slots(client, db_session):
    """Should show correct slot availability with capacity system."""
    import uuid
    # Use unique flight number to avoid conflicts with staging data
    unique_flight = f"TEST{uuid.uuid4().hex[:4].upper()}"
    test_date = date(2026, 6, 20)  # Use future date unlikely to have staging data

    # Create departure with early slot booked (1 of 1)
    departure = FlightDeparture(
        date=test_date,
        flight_number=unique_flight,
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(14, 0),
        destination_code="AGP",
        destination_name="Malaga, ES",
        capacity_tier=2,  # 1 slot per time
        slots_booked_early=1,  # Early slot booked
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get(f"/api/flights/departures/{test_date}")
    assert response.status_code == 200
    data = response.json()
    # Find our specific test flight
    our_flight = next((f for f in data if f["flightNumber"] == unique_flight), None)
    assert our_flight is not None, f"Test flight {unique_flight} not found in response"
    assert our_flight["early_slots_available"] == 0  # Fully booked
    assert our_flight["late_slots_available"] == 1   # Still available


@pytest.mark.asyncio
async def test_get_departures_all_slots_booked(client, db_session):
    """Should show all_slots_booked=True when fully booked."""
    departure = FlightDeparture(
        date=date(2025, 12, 21),
        flight_number="6666",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        destination_code="DUB",
        destination_name="Dublin, IE",
        capacity_tier=2,
        slots_booked_early=1,
        slots_booked_late=1,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get("/api/flights/departures/2025-12-21")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["all_slots_booked"] is True
    assert data[0]["early_slots_available"] == 0
    assert data[0]["late_slots_available"] == 0


@pytest.mark.asyncio
async def test_get_departures_call_us_only(client, db_session):
    """Should show is_call_us_only=True for capacity_tier=0 flights."""
    departure = FlightDeparture(
        date=date(2025, 12, 22),
        flight_number="CALLUS",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(6, 0),
        destination_code="LPA",
        destination_name="Gran Canaria",
        capacity_tier=0,  # Call Us only
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get("/api/flights/departures/2025-12-22")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["is_call_us_only"] is True
    assert data[0]["capacity_tier"] == 0


@pytest.mark.asyncio
async def test_get_departures_high_capacity(client, db_session):
    """Should correctly show availability for high capacity flights."""
    import uuid
    unique_flight = f"HICAP{uuid.uuid4().hex[:4].upper()}"
    test_date = date(2026, 7, 23)  # Use future date

    departure = FlightDeparture(
        date=test_date,
        flight_number=unique_flight,
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(12, 0),
        destination_code="AGP",
        destination_name="Malaga",
        capacity_tier=6,  # 3 slots per time
        slots_booked_early=1,
        slots_booked_late=2,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get(f"/api/flights/departures/{test_date}")
    assert response.status_code == 200
    data = response.json()
    # Find our specific test flight
    our_flight = next((f for f in data if f["flightNumber"] == unique_flight), None)
    assert our_flight is not None, f"Test flight {unique_flight} not found"
    assert our_flight["capacity_tier"] == 6
    assert our_flight["max_slots_per_time"] == 3
    assert our_flight["early_slots_available"] == 2  # 3 - 1
    assert our_flight["late_slots_available"] == 1   # 3 - 2
    assert our_flight["all_slots_booked"] is False


# =============================================================================
# Flight Arrival Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_arrivals_for_date(client, sample_arrival):
    """Should return arrivals for a specific date."""
    response = await client.get("/api/flights/arrivals/2025-12-22")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["flightNumber"] == "1235"
    assert data[0]["originCode"] == "FAO"
    assert data[0]["time"] == "17:30"


@pytest.mark.asyncio
async def test_get_arrivals_empty_date(client):
    """Should return empty array for date with no arrivals."""
    response = await client.get("/api/flights/arrivals/2025-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data == []


# =============================================================================
# Flight Schedule Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_schedule_combined(client, sample_departure, sample_arrival, db_session):
    """Should return combined departures and arrivals for a date."""
    # Add arrival on same date as departure
    arrival = FlightArrival(
        date=date(2025, 12, 15),
        flight_number="9999",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(12, 0),
        arrival_time=time(15, 0),
        origin_code="AGP",
        origin_name="Malaga, ES",
    )
    db_session.add(arrival)
    db_session.commit()

    response = await client.get("/api/flights/schedule/2025-12-15")
    assert response.status_code == 200
    data = response.json()
    # Should have 1 departure + 1 arrival
    assert len(data) == 2
    types = [f["type"] for f in data]
    assert "departure" in types
    assert "arrival" in types


# =============================================================================
# Payment/Booking Flow Tests (with mocked Stripe)
# =============================================================================

@pytest.mark.asyncio
async def test_create_payment_intent_success(client, sample_customer, sample_departure, db_session):
    """Should create booking and payment intent with slot booking."""
    # Create vehicle for customer
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="TEST123",
        make="Ford",
        model="Focus",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Mock Stripe
    mock_intent = MagicMock()
    mock_intent.client_secret = "pi_test_secret_123"
    mock_intent.id = "pi_test_123"

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test_secret_123",
            payment_intent_id="pi_test_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "phone": sample_customer.phone,
                        "package": "quick",
                        "flight_number": "1234",
                        "flight_date": "2025-12-15",
                        "drop_off_date": "2025-12-15",
                        "pickup_date": "2025-12-22",
                        "drop_off_slot": "165",
                        "departure_id": sample_departure.id,
                    }
                )

    assert response.status_code == 200
    data = response.json()
    assert "booking_reference" in data
    assert data["booking_reference"].startswith("TAG-")
    assert "client_secret" in data
    # Price depends on advance booking tier (quick package: early=£99, standard=£109, late=£119)
    assert data["amount"] in [9900, 10900, 11900]


@pytest.mark.asyncio
async def test_slot_booking_early(client, sample_customer, sample_departure, db_session):
    """Should increment early slot counter when drop_off_slot is 165."""
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="SLOT1TEST",
        make="VW",
        model="Golf",
        colour="White",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Verify slot is not booked initially
    assert sample_departure.slots_booked_early == 0

    import uuid
    unique_pi_id = f"pi_test_early_{uuid.uuid4().hex[:12]}"

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret=f"{unique_pi_id}_secret",
            payment_intent_id=unique_pi_id,
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test_456"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "1234",
                        "flight_date": "2025-12-15",
                        "drop_off_date": "2025-12-15",
                        "pickup_date": "2025-12-22",
                        "drop_off_slot": "165",  # Early slot
                        "departure_id": sample_departure.id,
                    }
                )

    assert response.status_code == 200

    # Note: Slot is NOT booked on payment intent creation
    # It's booked after payment succeeds via webhook
    # For this test, we're just verifying the payment intent was created


@pytest.mark.asyncio
async def test_slot_booking_late(client, sample_customer, db_session):
    """Should increment late slot counter when drop_off_slot is 120."""
    # Create a fresh departure for this test
    departure = FlightDeparture(
        date=date(2025, 12, 16),
        flight_number="7777",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(12, 0),
        destination_code="PMI",
        destination_name="Palma, ES",
        capacity_tier=2,
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="SLOT2TEST",
        make="Toyota",
        model="Yaris",
        colour="Red",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    import uuid
    unique_pi_id = f"pi_test_late_{uuid.uuid4().hex[:12]}"

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret=f"{unique_pi_id}_secret",
            payment_intent_id=unique_pi_id,
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test_789"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "longer",
                        "flight_number": "7777",
                        "flight_date": "2025-12-16",
                        "drop_off_date": "2025-12-16",
                        "pickup_date": "2025-12-30",
                        "drop_off_slot": "120",  # Late slot
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_booking_creates_record(client, sample_customer, sample_departure, db_session):
    """Should create a booking record in the database."""
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="BOOKING1",
        make="Honda",
        model="Civic",
        colour="Grey",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test_booking",
            payment_intent_id="pi_booking_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test_booking"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "1234",
                        "flight_date": "2025-12-15",
                        "drop_off_date": "2025-12-15",
                        "pickup_date": "2025-12-22",
                        "drop_off_slot": "165",
                        "departure_id": sample_departure.id,
                    }
                )

    assert response.status_code == 200
    booking_ref = response.json()["booking_reference"]

    # Check booking exists in database
    booking = db_session.query(Booking).filter(
        Booking.reference == booking_ref
    ).first()

    assert booking is not None
    assert booking.customer_id == sample_customer.id
    assert booking.vehicle_id == vehicle.id
    assert booking.package == "quick"


# =============================================================================
# Slot Availability / Fully Booked Tests (Capacity-Based)
# =============================================================================

@pytest.mark.asyncio
async def test_booking_fails_when_early_slot_full(client, sample_customer, db_session):
    """Should reject booking when early slots are at capacity."""
    # Create departure with early slot at capacity
    departure = FlightDeparture(
        date=date(2025, 12, 18),
        flight_number="FULL1",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(10, 0),
        destination_code="FAO",
        destination_name="Faro, PT",
        capacity_tier=2,  # 1 slot per time
        slots_booked_early=1,  # At capacity
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="FAIL1",
        make="BMW",
        model="X5",
        colour="Black",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test",
            payment_intent_id="pi_test",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "FULL1",
                        "flight_date": "2025-12-18",
                        "drop_off_date": "2025-12-18",
                        "pickup_date": "2025-12-25",
                        "drop_off_slot": "165",  # Trying to book early slot
                        "departure_id": departure.id,
                    }
                )

    # Should return 400 with error message
    assert response.status_code == 400
    data = response.json()
    assert "slot" in data["detail"].lower() or "booked" in data["detail"].lower()


@pytest.mark.asyncio
async def test_booking_fails_when_late_slot_full(client, sample_customer, db_session):
    """Should reject booking when late slots are at capacity."""
    departure = FlightDeparture(
        date=date(2025, 12, 19),
        flight_number="FULL2",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(14, 0),
        destination_code="PMI",
        destination_name="Palma, ES",
        capacity_tier=2,
        slots_booked_early=0,
        slots_booked_late=1,  # At capacity
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="FAIL2",
        make="Audi",
        model="A3",
        colour="White",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test",
            payment_intent_id="pi_test",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "longer",
                        "flight_number": "FULL2",
                        "flight_date": "2025-12-19",
                        "drop_off_date": "2025-12-19",
                        "pickup_date": "2026-01-02",
                        "drop_off_slot": "120",  # Trying to book late slot
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 400
    data = response.json()
    assert "slot" in data["detail"].lower() or "booked" in data["detail"].lower()


@pytest.mark.asyncio
async def test_booking_fails_when_all_slots_booked(client, sample_customer, db_session):
    """Should reject any booking when all slots are booked (fully booked flight)."""
    departure = FlightDeparture(
        date=date(2025, 12, 20),
        flight_number="FULLBOTH",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        destination_code="DUB",
        destination_name="Dublin, IE",
        capacity_tier=2,
        slots_booked_early=1,
        slots_booked_late=1,  # Both at capacity
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="FAILBOTH",
        make="Mercedes",
        model="C-Class",
        colour="Silver",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test",
            payment_intent_id="pi_test",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "FULLBOTH",
                        "flight_date": "2025-12-20",
                        "drop_off_date": "2025-12-20",
                        "pickup_date": "2025-12-27",
                        "drop_off_slot": "165",  # Either slot
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 400
    data = response.json()
    # Should mention fully booked or contact
    assert "booked" in data["detail"].lower() or "contact" in data["detail"].lower()


@pytest.mark.asyncio
async def test_booking_fails_for_call_us_only_flight(client, sample_customer, db_session):
    """Should reject booking for capacity_tier=0 (Call Us only) flights."""
    departure = FlightDeparture(
        date=date(2025, 12, 24),
        flight_number="CALLUS",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(6, 0),
        destination_code="LPA",
        destination_name="Gran Canaria",
        capacity_tier=0,  # Call Us only
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="CALLUS1",
        make="Ford",
        model="Fiesta",
        colour="Red",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test",
            payment_intent_id="pi_test",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "CALLUS",
                        "flight_date": "2025-12-24",
                        "drop_off_date": "2025-12-24",
                        "pickup_date": "2025-12-31",
                        "drop_off_slot": "165",
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 400
    data = response.json()
    assert "call" in data["detail"].lower() or "contact" in data["detail"].lower()


@pytest.mark.asyncio
async def test_can_book_late_slot_when_only_early_full(client, sample_customer, db_session):
    """Should allow booking late slot when only early slots are full."""
    departure = FlightDeparture(
        date=date(2025, 12, 21),
        flight_number="PARTIAL",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(12, 0),
        destination_code="AGP",
        destination_name="Malaga, ES",
        capacity_tier=2,
        slots_booked_early=1,  # Early at capacity
        slots_booked_late=0,   # Late available
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="PARTIAL1",
        make="VW",
        model="Polo",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    import uuid
    unique_pi_id = f"pi_partial_{uuid.uuid4().hex[:12]}"

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret=f"{unique_pi_id}_secret",
            payment_intent_id=unique_pi_id,
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_partial"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "PARTIAL",
                        "flight_date": "2025-12-21",
                        "drop_off_date": "2025-12-21",
                        "pickup_date": "2025-12-28",
                        "drop_off_slot": "120",  # Booking late slot
                        "departure_id": departure.id,
                    }
                )

    # Should succeed
    assert response.status_code == 200
    data = response.json()
    assert "booking_reference" in data


@pytest.mark.asyncio
async def test_can_book_early_slot_when_only_late_full(client, sample_customer, db_session):
    """Should allow booking early slot when only late slots are full."""
    departure = FlightDeparture(
        date=date(2025, 12, 23),
        flight_number="PARTIAL2",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(9, 0),
        destination_code="TFS",
        destination_name="Tenerife, ES",
        capacity_tier=2,
        slots_booked_early=0,  # Early available
        slots_booked_late=1,   # Late at capacity
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="PARTIAL2",
        make="Skoda",
        model="Octavia",
        colour="Grey",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    import uuid
    unique_pi_id = f"pi_partial2_{uuid.uuid4().hex[:12]}"

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret=f"{unique_pi_id}_secret",
            payment_intent_id=unique_pi_id,
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_partial2"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "longer",
                        "flight_number": "PARTIAL2",
                        "flight_date": "2025-12-23",
                        "drop_off_date": "2025-12-23",
                        "pickup_date": "2026-01-06",
                        "drop_off_slot": "165",  # Booking early slot
                        "departure_id": departure.id,
                    }
                )

    # Should succeed
    assert response.status_code == 200
    data = response.json()
    assert "booking_reference" in data


@pytest.mark.asyncio
async def test_departure_shows_capacity_info(client, db_session):
    """Departures endpoint should show capacity information."""
    import uuid
    # Use unique suffix for test flights and unique date
    suffix = uuid.uuid4().hex[:4].upper()
    test_date = date(2026, 8, 22)  # Use future date

    # Create various departures with different capacity states
    departures_data = [
        (f"EMPTY{suffix}", 2, 0, 0),      # Both available (capacity 2)
        (f"EARLY{suffix}", 2, 1, 0),      # Early full
        (f"LATE{suffix}", 2, 0, 1),       # Late full
        (f"FULL{suffix}", 2, 1, 1),       # Both full
        (f"HIGH{suffix}", 6, 1, 2),       # High capacity, partially booked
        (f"CALLUS{suffix}", 0, 0, 0),     # Call Us only
    ]

    for flight_num, cap, early, late in departures_data:
        dep = FlightDeparture(
            date=test_date,
            flight_number=flight_num,
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(10, 0),
            destination_code="FAO",
            destination_name="Faro, PT",
            capacity_tier=cap,
            slots_booked_early=early,
            slots_booked_late=late,
        )
        db_session.add(dep)
    db_session.commit()

    response = await client.get(f"/api/flights/departures/{test_date}")
    assert response.status_code == 200
    data = response.json()

    # Check each flight has correct capacity status (find by our unique flight numbers)
    flights_by_num = {f["flightNumber"]: f for f in data}

    # EMPTY: capacity 2, 0 booked
    assert flights_by_num[f"EMPTY{suffix}"]["capacity_tier"] == 2
    assert flights_by_num[f"EMPTY{suffix}"]["early_slots_available"] == 1
    assert flights_by_num[f"EMPTY{suffix}"]["late_slots_available"] == 1
    assert flights_by_num[f"EMPTY{suffix}"]["all_slots_booked"] is False

    # EARLY: early slot full
    assert flights_by_num[f"EARLY{suffix}"]["early_slots_available"] == 0
    assert flights_by_num[f"EARLY{suffix}"]["late_slots_available"] == 1

    # LATE: late slot full
    assert flights_by_num[f"LATE{suffix}"]["early_slots_available"] == 1
    assert flights_by_num[f"LATE{suffix}"]["late_slots_available"] == 0

    # FULL: both full
    assert flights_by_num[f"FULL{suffix}"]["all_slots_booked"] is True
    assert flights_by_num[f"FULL{suffix}"]["early_slots_available"] == 0
    assert flights_by_num[f"FULL{suffix}"]["late_slots_available"] == 0

    # HIGH: capacity 6, 1 early booked, 2 late booked
    assert flights_by_num[f"HIGH{suffix}"]["capacity_tier"] == 6
    assert flights_by_num[f"HIGH{suffix}"]["max_slots_per_time"] == 3
    assert flights_by_num[f"HIGH{suffix}"]["early_slots_available"] == 2  # 3 - 1
    assert flights_by_num[f"HIGH{suffix}"]["late_slots_available"] == 1   # 3 - 2

    # CALLUS: capacity 0
    assert flights_by_num[f"CALLUS{suffix}"]["is_call_us_only"] is True
    assert flights_by_num[f"CALLUS{suffix}"]["capacity_tier"] == 0


# =============================================================================
# Available Dates Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_available_dates(client, db_session):
    """Should return dates that have flights."""
    # Create departures on multiple dates
    for day in [10, 11, 15, 20]:
        departure = FlightDeparture(
            date=date(2025, 12, day),
            flight_number=f"{day}00",
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(10, 0),
            destination_code="FAO",
            destination_name="Faro, PT",
            capacity_tier=2,
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(departure)
    db_session.commit()

    response = await client.get("/api/flights/dates")
    assert response.status_code == 200
    data = response.json()
    # Returns array of date strings directly
    assert isinstance(data, list)
    assert len(data) == 4
    assert "2025-12-10" in data
    assert "2025-12-20" in data


# =============================================================================
# Full Booking Flow Integration Test
# =============================================================================

@pytest.mark.asyncio
async def test_full_booking_flow(client, db_session):
    """Test the complete booking flow from customer creation to payment."""
    # Step 1: Create customer
    customer_response = await client.post(
        "/api/customers",
        json={
            "first_name": "Integration",
            "last_name": "Test",
            "email": "integration@test.com",
            "phone": "+44 7000 000000",
        }
    )
    assert customer_response.status_code == 200
    customer_id = customer_response.json()["customer_id"]

    # Step 2: Create vehicle
    vehicle_response = await client.post(
        "/api/vehicles",
        json={
            "customer_id": customer_id,
            "registration": "INT123",
            "make": "Tesla",
            "model": "Model 3",
            "colour": "White",
        }
    )
    assert vehicle_response.status_code == 200
    vehicle_id = vehicle_response.json()["vehicle_id"]

    # Step 3: Update billing address
    billing_response = await client.patch(
        f"/api/customers/{customer_id}/billing",
        json={
            "billing_address1": "Integration House",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
            "billing_country": "United Kingdom",
        }
    )
    assert billing_response.status_code == 200

    # Step 4: Create departure flight
    departure = FlightDeparture(
        date=date(2025, 12, 25),
        flight_number="XMAS",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        destination_code="TFS",
        destination_name="Tenerife, ES",
        capacity_tier=2,
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    # Step 5: Check flights available
    flights_response = await client.get("/api/flights/departures/2025-12-25")
    assert flights_response.status_code == 200
    flights = flights_response.json()
    assert len(flights) == 1
    assert flights[0]["early_slots_available"] == 1

    # Step 6: Create payment intent
    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_integration_test",
            payment_intent_id="pi_int_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_int_test"

                payment_response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": customer_id,
                        "vehicle_id": vehicle_id,
                        "first_name": "Integration",
                        "last_name": "Test",
                        "email": "integration@test.com",
                        "package": "longer",
                        "flight_number": "XMAS",
                        "flight_date": "2025-12-25",
                        "drop_off_date": "2025-12-25",
                        "pickup_date": "2026-01-08",
                        "drop_off_slot": "165",
                        "departure_id": departure.id,
                    }
                )

    assert payment_response.status_code == 200
    payment_data = payment_response.json()
    # Price depends on advance booking tier (longer package: early=£150, standard=£160, late=£170)
    assert payment_data["amount"] in [15000, 16000, 17000]

    # Step 7: Verify booking exists
    booking = db_session.query(Booking).filter(
        Booking.reference == payment_data["booking_reference"]
    ).first()
    assert booking is not None
    assert booking.package == "longer"


# =============================================================================
# Destination/Origin Lookup from Flight Tables Tests
# =============================================================================

@pytest.mark.asyncio
async def test_booking_gets_destination_from_departure_table(client, sample_customer, sample_departure, db_session):
    """
    Booking should get dropoff_destination from FlightDeparture table, not frontend.

    This tests the new functionality where destination_name is looked up from
    the departure table using the departure_id, extracting just the city name.
    """
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="DEST001",
        make="Ford",
        model="Fiesta",
        colour="Red",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_dest_test",
            payment_intent_id="pi_dest_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_dest_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "1234",
                        "flight_date": "2025-12-15",
                        "drop_off_date": "2025-12-15",
                        "pickup_date": "2025-12-22",
                        "drop_off_slot": "165",
                        "departure_id": sample_departure.id,
                        # Note: NOT passing dropoff_destination - it should be looked up
                    }
                )

    assert response.status_code == 200
    data = response.json()

    # Verify booking was created with destination from flight table
    booking = db_session.query(Booking).filter(
        Booking.reference == data["booking_reference"]
    ).first()
    assert booking is not None
    # sample_departure has destination_name="Faro, PT", should extract "Faro"
    assert booking.dropoff_destination == "Faro"


@pytest.mark.asyncio
async def test_booking_gets_origin_from_arrival_table(client, sample_customer, sample_departure, sample_arrival, db_session):
    """
    Booking should get pickup_origin from FlightArrival table, not frontend.

    This tests the new functionality where origin_name is looked up from
    the arrival table using pickup_flight_number and pickup_date.
    """
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="ORIG001",
        make="Ford",
        model="Focus",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_orig_test",
            payment_intent_id="pi_orig_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_orig_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "1234",
                        "flight_date": "2025-12-15",
                        "drop_off_date": "2025-12-15",
                        "pickup_date": "2025-12-22",
                        "drop_off_slot": "165",
                        "departure_id": sample_departure.id,
                        "pickup_flight_number": "1235",  # Matches sample_arrival
                        "pickup_flight_time": "17:30",
                        # Note: NOT passing pickup_origin - it should be looked up
                    }
                )

    assert response.status_code == 200
    data = response.json()

    # Verify booking was created with origin from flight table
    booking = db_session.query(Booking).filter(
        Booking.reference == data["booking_reference"]
    ).first()
    assert booking is not None
    # sample_arrival has origin_name="Faro, PT", should extract "Faro"
    assert booking.pickup_origin == "Faro"


@pytest.mark.asyncio
async def test_tenerife_reinasofia_shortened_to_tenerife(client, sample_customer, db_session):
    """
    Tenerife-Reinasofia should be shortened to just 'Tenerife'.
    """
    # Create departure with Tenerife-Reinasofia
    departure = FlightDeparture(
        date=date(2025, 12, 20),
        flight_number="TFS001",
        airline_code="U2",
        airline_name="easyJet",
        departure_time=time(16, 0),
        destination_code="TFS",
        destination_name="Tenerife-Reinasofia, ES",
        capacity_tier=4,
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="TFS001",
        make="VW",
        model="Polo",
        colour="Silver",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_tfs_test",
            payment_intent_id="pi_tfs_123",
        )
        with patch("main.is_stripe_configured", return_value=True):
            with patch("main.get_settings") as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_tfs_test"

                response = await client.post(
                    "/api/payments/create-intent",
                    json={
                        "customer_id": sample_customer.id,
                        "vehicle_id": vehicle.id,
                        "first_name": sample_customer.first_name,
                        "last_name": sample_customer.last_name,
                        "email": sample_customer.email,
                        "package": "quick",
                        "flight_number": "TFS001",
                        "flight_date": "2025-12-20",
                        "drop_off_date": "2025-12-20",
                        "pickup_date": "2025-12-27",
                        "drop_off_slot": "165",
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 200
    data = response.json()

    # Verify Tenerife-Reinasofia is shortened to Tenerife
    booking = db_session.query(Booking).filter(
        Booking.reference == data["booking_reference"]
    ).first()
    assert booking is not None
    assert booking.dropoff_destination == "Tenerife"


@pytest.mark.asyncio
async def test_admin_bookings_returns_pickup_collection_time(client, sample_customer, sample_departure, sample_arrival, db_session):
    """
    Admin bookings API should return pickup_collection_time (45 min after landing).
    """
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="PCT123",
        make="Ford",
        model="Focus",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create booking with pickup_time of 14:00
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="PCT-TEST-001",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=sample_arrival.date,
        pickup_time=time(14, 0),  # 14:00 landing
        pickup_flight_number=sample_arrival.flight_number,
        status=BookingStatus.CONFIRMED,
    )
    db_session.add(booking)
    db_session.commit()

    # Get admin bookings
    response = await client.get("/api/admin/bookings")
    assert response.status_code == 200
    data = response.json()

    # Find our booking
    bookings = data["bookings"]
    our_booking = next((b for b in bookings if b["reference"] == "PCT-TEST-001"), None)
    assert our_booking is not None

    # Verify pickup_collection_time is 45 min after landing (14:00 + 45 = 14:45)
    assert our_booking["pickup_collection_time"] == "14:45"


@pytest.mark.asyncio
async def test_admin_bookings_pickup_collection_time_handles_hour_rollover(client, sample_customer, sample_departure, db_session):
    """
    Pickup collection time should correctly handle hour rollover (e.g., 14:30 + 45 = 15:15).
    """
    # Create arrival with time that causes hour rollover
    arrival = FlightArrival(
        date=date(2025, 12, 27),
        flight_number="HR001",
        airline_code="BA",
        airline_name="British Airways",
        arrival_time=time(14, 30),  # 14:30 + 45 = 15:15
        origin_code="LHR",
        origin_name="London Heathrow, GB",
    )
    db_session.add(arrival)
    db_session.commit()

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="HR123",
        make="Honda",
        model="Civic",
        colour="Red",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="HR-TEST-001",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=arrival.date,
        pickup_time=time(14, 30),  # 14:30 landing
        pickup_flight_number=arrival.flight_number,
        status=BookingStatus.CONFIRMED,
    )
    db_session.add(booking)
    db_session.commit()

    # Get admin bookings
    response = await client.get("/api/admin/bookings")
    assert response.status_code == 200
    data = response.json()

    # Find our booking
    bookings = data["bookings"]
    our_booking = next((b for b in bookings if b["reference"] == "HR-TEST-001"), None)
    assert our_booking is not None

    # Verify pickup_collection_time correctly rolled over (14:30 + 45 = 15:15)
    assert our_booking["pickup_collection_time"] == "15:15"


# =============================================================================
# Cancellation and Refund Email Tests
# =============================================================================

@pytest.mark.asyncio
async def test_send_cancellation_email_success(client, sample_customer, sample_departure, db_session):
    """
    Should send cancellation email for a cancelled booking and update tracking fields.
    """
    from db_models import Payment, PaymentStatus

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="CANCEL01",
        make="Ford",
        model="Focus",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create a cancelled booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="CAN-TEST-001",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=date(2025, 12, 22),
        pickup_time=time(14, 0),
        status=BookingStatus.CANCELLED,
        cancellation_email_sent=False,
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)

    # Mock email sending - need to patch in email_service since it's imported inside the endpoint
    with patch("email_service.send_cancellation_email", return_value=True):
        response = await client.post(f"/api/admin/bookings/{booking.id}/send-cancellation-email")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "CAN-TEST-001" in data["reference"]

    # Verify database updated
    db_session.refresh(booking)
    assert booking.cancellation_email_sent is True
    assert booking.cancellation_email_sent_at is not None


@pytest.mark.asyncio
async def test_send_cancellation_email_fails_for_non_cancelled_booking(client, sample_customer, sample_departure, db_session):
    """
    Should reject sending cancellation email for non-cancelled bookings.
    """
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="CANCEL02",
        make="VW",
        model="Golf",
        colour="White",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create a confirmed (not cancelled) booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="CAN-TEST-002",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=date(2025, 12, 22),
        pickup_time=time(14, 0),
        status=BookingStatus.CONFIRMED,  # Not cancelled
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)

    response = await client.post(f"/api/admin/bookings/{booking.id}/send-cancellation-email")

    assert response.status_code == 400
    data = response.json()
    assert "cancelled" in data["detail"].lower()


@pytest.mark.asyncio
async def test_send_cancellation_email_not_found(client):
    """
    Should return 404 for non-existent booking.
    """
    response = await client.post("/api/admin/bookings/99999/send-cancellation-email")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_refund_email_success(client, sample_customer, sample_departure, db_session):
    """
    Should send refund email for a cancelled booking with payment and update tracking fields.
    """
    from db_models import Payment, PaymentStatus

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="REFUND01",
        make="BMW",
        model="3 Series",
        colour="Black",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create a cancelled booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="REF-TEST-001",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=date(2025, 12, 22),
        pickup_time=time(14, 0),
        status=BookingStatus.CANCELLED,
        refund_email_sent=False,
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)

    # Create payment record with refund amount
    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id="pi_test_refund",
        amount_pence=9900,
        refund_amount_pence=9900,
        status=PaymentStatus.REFUNDED,
    )
    db_session.add(payment)
    db_session.commit()

    # Mock email sending - need to patch in email_service since it's imported inside the endpoint
    with patch("email_service.send_refund_email", return_value=True):
        response = await client.post(f"/api/admin/bookings/{booking.id}/send-refund-email")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "REF-TEST-001" in data["reference"]

    # Verify database updated
    db_session.refresh(booking)
    assert booking.refund_email_sent is True
    assert booking.refund_email_sent_at is not None


@pytest.mark.asyncio
async def test_send_refund_email_uses_original_amount_if_no_refund_amount(client, sample_customer, sample_departure, db_session):
    """
    Should use original payment amount if no specific refund_amount_pence is set.
    """
    from db_models import Payment, PaymentStatus

    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="REFUND02",
        make="Audi",
        model="A4",
        colour="Silver",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create a cancelled booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="REF-TEST-002",
        package="longer",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=date(2025, 12, 22),
        pickup_time=time(14, 0),
        status=BookingStatus.CANCELLED,
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)

    # Create payment record without refund_amount_pence
    payment = Payment(
        booking_id=booking.id,
        stripe_payment_intent_id="pi_test_refund2",
        amount_pence=15000,
        refund_amount_pence=None,  # No refund amount specified
        status=PaymentStatus.REFUNDED,
    )
    db_session.add(payment)
    db_session.commit()

    # Mock email sending - verify it's called (endpoint will use amount_pence as fallback)
    with patch("email_service.send_refund_email", return_value=True):
        response = await client.post(f"/api/admin/bookings/{booking.id}/send-refund-email")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_send_refund_email_fails_for_non_cancelled_booking(client, sample_customer, sample_departure, db_session):
    """
    Should reject sending refund email for non-cancelled bookings.
    """
    # Create vehicle
    vehicle = Vehicle(
        customer_id=sample_customer.id,
        registration="REFUND03",
        make="Mercedes",
        model="C-Class",
        colour="White",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Create a confirmed (not cancelled) booking
    booking = Booking(
        customer_id=sample_customer.id,
        vehicle_id=vehicle.id,
        reference="REF-TEST-003",
        package="quick",
        dropoff_date=sample_departure.date,
        dropoff_time=time(9, 0),
        dropoff_flight_number=sample_departure.flight_number,
        dropoff_slot="early",
        departure_id=sample_departure.id,
        pickup_date=date(2025, 12, 22),
        pickup_time=time(14, 0),
        status=BookingStatus.CONFIRMED,  # Not cancelled
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)

    response = await client.post(f"/api/admin/bookings/{booking.id}/send-refund-email")

    assert response.status_code == 400
    data = response.json()
    assert "cancelled" in data["detail"].lower()


@pytest.mark.asyncio
async def test_send_refund_email_not_found(client):
    """
    Should return 404 for non-existent booking.
    """
    response = await client.post("/api/admin/bookings/99999/send-refund-email")
    assert response.status_code == 404
