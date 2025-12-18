"""
Integration tests for the TAG Booking API.

Tests all database-backed endpoints with a separate test database.
Includes mocked Stripe calls for payment flow testing.
"""
import pytest
import pytest_asyncio
from datetime import date, time
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///./tag_test.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from db_models import Customer, Vehicle, Booking, FlightDeparture, FlightArrival
from main import app


# Test database setup
TEST_DATABASE_URL = "sqlite:///./tag_test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the dependency
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create fresh test database for each test."""
    # Create all tables
    Base.metadata.create_all(bind=test_engine)
    yield
    # Drop all tables after test
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Get a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_departure(db_session):
    """Create a sample departure flight for testing."""
    departure = FlightDeparture(
        date=date(2025, 12, 15),
        flight_number="1234",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(10, 30),
        destination_code="FAO",
        destination_name="Faro, PT",
        is_slot_1_booked=False,
        is_slot_2_booked=False,
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
    """Create a sample customer for testing."""
    customer = Customer(
        first_name="John",
        last_name="Doe",
        email="john.doe@test.com",
        phone="+44 7123 456789",
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
# Flight Departure Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_departures_for_date(client, sample_departure):
    """Should return departures for a specific date."""
    response = await client.get("/api/flights/departures/2025-12-15")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["flightNumber"] == "1234"
    assert data[0]["airlineCode"] == "FR"
    assert data[0]["destinationCode"] == "FAO"
    assert data[0]["is_slot_1_booked"] is False
    assert data[0]["is_slot_2_booked"] is False


@pytest.mark.asyncio
async def test_get_departures_empty_date(client):
    """Should return empty array for date with no flights."""
    response = await client.get("/api/flights/departures/2025-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_get_departures_with_booked_slots(client, db_session):
    """Should show correct slot booking status."""
    # Create departure with slot 1 booked
    departure = FlightDeparture(
        date=date(2025, 12, 20),
        flight_number="5555",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(14, 0),
        destination_code="AGP",
        destination_name="Malaga, ES",
        is_slot_1_booked=True,
        is_slot_2_booked=False,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get("/api/flights/departures/2025-12-20")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["is_slot_1_booked"] is True
    assert data[0]["is_slot_2_booked"] is False


@pytest.mark.asyncio
async def test_get_departures_both_slots_booked(client, db_session):
    """Should show both slots as booked when fully booked."""
    departure = FlightDeparture(
        date=date(2025, 12, 21),
        flight_number="6666",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        destination_code="DUB",
        destination_name="Dublin, IE",
        is_slot_1_booked=True,
        is_slot_2_booked=True,
    )
    db_session.add(departure)
    db_session.commit()

    response = await client.get("/api/flights/departures/2025-12-21")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["is_slot_1_booked"] is True
    assert data[0]["is_slot_2_booked"] is True


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
    assert data["amount"] == 9900  # £99.00 in pence


@pytest.mark.asyncio
async def test_slot_booking_slot_1(client, sample_customer, sample_departure, db_session):
    """Should mark slot 1 as booked when drop_off_slot is 165."""
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
    assert sample_departure.is_slot_1_booked is False

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test_secret_456",
            payment_intent_id="pi_test_456",
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
                        "drop_off_slot": "165",  # Slot 1
                        "departure_id": sample_departure.id,
                    }
                )

    assert response.status_code == 200

    # Refresh departure from database
    db_session.refresh(sample_departure)
    assert sample_departure.is_slot_1_booked is True
    assert sample_departure.is_slot_2_booked is False


@pytest.mark.asyncio
async def test_slot_booking_slot_2(client, sample_customer, db_session):
    """Should mark slot 2 as booked when drop_off_slot is 120."""
    # Create a fresh departure for this test
    departure = FlightDeparture(
        date=date(2025, 12, 16),
        flight_number="7777",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(12, 0),
        destination_code="PMI",
        destination_name="Palma, ES",
        is_slot_1_booked=False,
        is_slot_2_booked=False,
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

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_test_secret_789",
            payment_intent_id="pi_test_789",
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
                        "drop_off_slot": "120",  # Slot 2
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 200

    # Refresh departure from database
    db_session.refresh(departure)
    assert departure.is_slot_1_booked is False
    assert departure.is_slot_2_booked is True


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
# Slot Availability / Fully Booked Tests
# =============================================================================

@pytest.mark.asyncio
async def test_booking_fails_when_slot_1_already_booked(client, sample_customer, db_session):
    """Should reject booking when slot 1 is already booked."""
    # Create departure with slot 1 already booked
    departure = FlightDeparture(
        date=date(2025, 12, 18),
        flight_number="FULL1",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(10, 0),
        destination_code="FAO",
        destination_name="Faro, PT",
        is_slot_1_booked=True,  # Already booked
        is_slot_2_booked=False,
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
                        "drop_off_slot": "165",  # Trying to book slot 1
                        "departure_id": departure.id,
                    }
                )

    # Should return 400 with error message
    assert response.status_code == 400
    data = response.json()
    assert "slot" in data["detail"].lower() or "booked" in data["detail"].lower()


@pytest.mark.asyncio
async def test_booking_fails_when_slot_2_already_booked(client, sample_customer, db_session):
    """Should reject booking when slot 2 is already booked."""
    departure = FlightDeparture(
        date=date(2025, 12, 19),
        flight_number="FULL2",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(14, 0),
        destination_code="PMI",
        destination_name="Palma, ES",
        is_slot_1_booked=False,
        is_slot_2_booked=True,  # Already booked
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
                        "drop_off_slot": "120",  # Trying to book slot 2
                        "departure_id": departure.id,
                    }
                )

    assert response.status_code == 400
    data = response.json()
    assert "slot" in data["detail"].lower() or "booked" in data["detail"].lower()


@pytest.mark.asyncio
async def test_booking_fails_when_both_slots_booked(client, sample_customer, db_session):
    """Should reject any booking when both slots are booked (fully booked flight)."""
    departure = FlightDeparture(
        date=date(2025, 12, 20),
        flight_number="FULLBOTH",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        destination_code="DUB",
        destination_name="Dublin, IE",
        is_slot_1_booked=True,
        is_slot_2_booked=True,  # Both booked
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
    # Should mention contacting directly
    assert "contact" in data["detail"].lower() or "booked" in data["detail"].lower()


@pytest.mark.asyncio
async def test_can_book_slot_2_when_only_slot_1_booked(client, sample_customer, db_session):
    """Should allow booking slot 2 when only slot 1 is booked."""
    departure = FlightDeparture(
        date=date(2025, 12, 21),
        flight_number="PARTIAL",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(12, 0),
        destination_code="AGP",
        destination_name="Malaga, ES",
        is_slot_1_booked=True,  # Slot 1 booked
        is_slot_2_booked=False,  # Slot 2 available
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

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_partial",
            payment_intent_id="pi_partial_123",
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
                        "drop_off_slot": "120",  # Booking slot 2
                        "departure_id": departure.id,
                    }
                )

    # Should succeed
    assert response.status_code == 200
    data = response.json()
    assert "booking_reference" in data


@pytest.mark.asyncio
async def test_can_book_slot_1_when_only_slot_2_booked(client, sample_customer, db_session):
    """Should allow booking slot 1 when only slot 2 is booked."""
    departure = FlightDeparture(
        date=date(2025, 12, 23),
        flight_number="PARTIAL2",
        airline_code="LS",
        airline_name="Jet2",
        departure_time=time(9, 0),
        destination_code="TFS",
        destination_name="Tenerife, ES",
        is_slot_1_booked=False,  # Slot 1 available
        is_slot_2_booked=True,   # Slot 2 booked
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

    with patch("main.create_payment_intent") as mock_create:
        mock_create.return_value = MagicMock(
            client_secret="pi_partial2",
            payment_intent_id="pi_partial2_123",
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
                        "drop_off_slot": "165",  # Booking slot 1
                        "departure_id": departure.id,
                    }
                )

    # Should succeed
    assert response.status_code == 200
    data = response.json()
    assert "booking_reference" in data

    # Verify slot 1 is now booked
    db_session.refresh(departure)
    assert departure.is_slot_1_booked is True
    assert departure.is_slot_2_booked is True  # Both now booked


@pytest.mark.asyncio
async def test_departure_shows_available_slots(client, db_session):
    """Departures endpoint should show which slots are available."""
    # Create various departures with different slot states
    departures_data = [
        ("NONE", False, False),  # Both available
        ("ONE", True, False),    # Only slot 2 available
        ("TWO", False, True),    # Only slot 1 available
        ("BOTH", True, True),    # None available (fully booked)
    ]

    for flight_num, slot1, slot2 in departures_data:
        dep = FlightDeparture(
            date=date(2025, 12, 22),
            flight_number=flight_num,
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(10, 0),
            destination_code="FAO",
            destination_name="Faro, PT",
            is_slot_1_booked=slot1,
            is_slot_2_booked=slot2,
        )
        db_session.add(dep)
    db_session.commit()

    response = await client.get("/api/flights/departures/2025-12-22")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4

    # Check each flight has correct slot status
    flights_by_num = {f["flightNumber"]: f for f in data}

    assert flights_by_num["NONE"]["is_slot_1_booked"] is False
    assert flights_by_num["NONE"]["is_slot_2_booked"] is False

    assert flights_by_num["ONE"]["is_slot_1_booked"] is True
    assert flights_by_num["ONE"]["is_slot_2_booked"] is False

    assert flights_by_num["TWO"]["is_slot_1_booked"] is False
    assert flights_by_num["TWO"]["is_slot_2_booked"] is True

    assert flights_by_num["BOTH"]["is_slot_1_booked"] is True
    assert flights_by_num["BOTH"]["is_slot_2_booked"] is True


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
            is_slot_1_booked=False,
            is_slot_2_booked=False,
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
        is_slot_1_booked=False,
        is_slot_2_booked=False,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)

    # Step 5: Check flights available
    flights_response = await client.get("/api/flights/departures/2025-12-25")
    assert flights_response.status_code == 200
    flights = flights_response.json()
    assert len(flights) == 1
    assert flights[0]["is_slot_1_booked"] is False

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
    assert payment_data["amount"] == 15000  # £150.00 for longer package

    # Step 7: Verify slot is now booked
    flights_after = await client.get("/api/flights/departures/2025-12-25")
    flights_data = flights_after.json()
    assert flights_data[0]["is_slot_1_booked"] is True

    # Step 8: Verify booking exists
    booking = db_session.query(Booking).filter(
        Booking.reference == payment_data["booking_reference"]
    ).first()
    assert booking is not None
    assert booking.package == "longer"
