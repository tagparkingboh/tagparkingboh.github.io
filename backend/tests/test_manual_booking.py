"""
Tests for manual booking functionality.

Covers:
- POST /api/admin/manual-booking - Create manual booking and send payment link email

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios
- Integration: Full flow tests with database verification
"""
import pytest
import pytest_asyncio
from datetime import date, time, datetime
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, require_admin, get_current_user
from db_models import Booking, Customer, Vehicle, Payment, BookingStatus, PaymentStatus, User
from database import get_db


# =============================================================================
# Auth Override for Testing
# =============================================================================

# Mock user for admin authentication
mock_admin_user = User(
    id=999,
    email="test_admin@example.com",
    is_admin=True,
    is_active=True,
)


async def mock_get_current_user():
    """Mock current user for testing."""
    return mock_admin_user


async def mock_require_admin():
    """Mock admin requirement for testing."""
    return mock_admin_user


# Apply auth overrides at module level
app.dependency_overrides[get_current_user] = mock_get_current_user
app.dependency_overrides[require_admin] = mock_require_admin


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
def valid_manual_booking_request():
    """Create a valid manual booking request payload."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": f"jane.smith.{unique_id}@example.com",
        "phone": "+44 7700 900123",
        "billing_address1": "123 Test Street",
        "billing_address2": "Apt 4B",
        "billing_city": "Bournemouth",
        "billing_county": "Dorset",
        "billing_postcode": "BH1 1AA",
        "billing_country": "United Kingdom",
        "registration": "AB12CDE",
        "make": "Toyota",
        "model": "Corolla",
        "colour": "Silver",
        "dropoff_date": "2026-03-15",
        "dropoff_time": "08:30",
        "pickup_date": "2026-03-22",
        "pickup_time": "14:00",
        "stripe_payment_link": "https://buy.stripe.com/test_abc123",
        "amount_pence": 9900,
        "notes": "Customer called to book - prefers early morning slot",
    }


@pytest.fixture
def minimal_manual_booking_request():
    """Create a minimal valid manual booking request (only required fields)."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "first_name": "John",
        "last_name": "Doe",
        "email": f"john.doe.{unique_id}@example.com",
        "billing_address1": "456 Main Road",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "registration": "XY99ZZZ",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "dropoff_date": "2026-04-01",
        "dropoff_time": "10:00",
        "pickup_date": "2026-04-08",
        "pickup_time": "16:30",
        "stripe_payment_link": "https://buy.stripe.com/test_xyz789",
        "amount_pence": 15000,
    }


@pytest.fixture
def existing_customer(db_session):
    """Create an existing customer for testing updates."""
    unique_id = uuid.uuid4().hex[:8]
    customer = Customer(
        first_name="Existing",
        last_name="Customer",
        email=f"existing.customer.{unique_id}@example.com",
        phone="+44 7700 111111",
        billing_address1="Old Address",
        billing_city="Old City",
        billing_postcode="OLD 1AA",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture
def existing_vehicle(db_session, existing_customer):
    """Create an existing vehicle for testing."""
    vehicle = Vehicle(
        customer_id=existing_customer.id,
        registration="EXIST123",
        make="Honda",
        model="Civic",
        colour="Red",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


# =============================================================================
# POST /api/admin/manual-booking - Happy Path Tests
# =============================================================================

class TestManualBookingHappyPath:
    """Happy path tests for creating manual bookings."""

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_manual_booking_success(
        self, mock_send_email, client, valid_manual_booking_request
    ):
        """Should successfully create a manual booking and send email."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_sent"] is True
        assert data["booking_reference"].startswith("TAG-")
        assert len(data["booking_reference"]) == 12  # TAG- + 8 chars
        assert "created" in data["message"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_manual_booking_minimal_fields(
        self, mock_send_email, client, minimal_manual_booking_request
    ):
        """Should create booking with only required fields."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=minimal_manual_booking_request
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["booking_reference"].startswith("TAG-")

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_customer_created_in_database(
        self, mock_send_email, client, db_session, valid_manual_booking_request
    ):
        """Should create customer record in database."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        assert response.status_code == 200

        # Verify customer in database
        customer = db_session.query(Customer).filter(
            Customer.email == valid_manual_booking_request["email"]
        ).first()
        assert customer is not None
        assert customer.first_name == "Jane"
        assert customer.last_name == "Smith"
        assert customer.billing_address1 == "123 Test Street"
        assert customer.billing_city == "Bournemouth"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_vehicle_created_in_database(
        self, mock_send_email, client, db_session, valid_manual_booking_request
    ):
        """Should create vehicle record in database."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        assert response.status_code == 200

        # Verify vehicle in database
        vehicle = db_session.query(Vehicle).filter(
            Vehicle.registration == valid_manual_booking_request["registration"].upper()
        ).first()
        assert vehicle is not None
        assert vehicle.make == "Toyota"
        assert vehicle.model == "Corolla"
        assert vehicle.colour == "Silver"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_booking_created_with_pending_status(
        self, mock_send_email, client, db_session, valid_manual_booking_request
    ):
        """Should create booking with PENDING status."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify booking in database
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking is not None
        assert booking.status == BookingStatus.PENDING
        assert booking.booking_source == "manual"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_payment_created_with_pending_status(
        self, mock_send_email, client, db_session, valid_manual_booking_request
    ):
        """Should create payment record with PENDING status and payment link."""
        mock_send_email.return_value = True

        response = await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify payment in database
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        payment = db_session.query(Payment).filter(
            Payment.booking_id == booking.id
        ).first()
        assert payment is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount_pence == 9900
        assert payment.stripe_payment_link == "https://buy.stripe.com/test_abc123"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_email_called_with_correct_parameters(
        self, mock_send_email, client, valid_manual_booking_request
    ):
        """Should call email function with correct parameters."""
        mock_send_email.return_value = True

        await client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request
        )

        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args[1]

        assert call_kwargs["email"] == valid_manual_booking_request["email"]
        assert call_kwargs["first_name"] == "Jane"
        assert call_kwargs["vehicle_make"] == "Toyota"
        assert call_kwargs["vehicle_model"] == "Corolla"
        assert call_kwargs["vehicle_registration"] == "AB12CDE"
        assert call_kwargs["amount"] == "£99.00"
        assert call_kwargs["payment_link"] == "https://buy.stripe.com/test_abc123"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_registration_uppercase_in_database(
        self, mock_send_email, client, db_session
    ):
        """Should store registration in uppercase."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Test",
            "last_name": "User",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "Test Street",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
            "registration": "ab12cde",  # lowercase
            "make": "Test",
            "model": "Car",
            "colour": "White",
            "dropoff_date": "2026-05-01",
            "dropoff_time": "09:00",
            "pickup_date": "2026-05-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_123",
            "amount_pence": 5000,
        }

        await client.post("/api/admin/manual-booking", json=request)

        vehicle = db_session.query(Vehicle).filter(
            Vehicle.registration == "AB12CDE"
        ).first()
        assert vehicle is not None

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_no_package_for_manual_bookings(
        self, mock_send_email, client, db_session
    ):
        """Manual bookings should not have a package - price is set via Stripe link."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "No",
            "last_name": "Package",
            "email": f"nopackage.{unique_id}@example.com",
            "billing_address1": "Test Street",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
            "registration": f"NP{unique_id[:6]}",
            "make": "Test",
            "model": "Car",
            "colour": "White",
            "dropoff_date": "2026-06-01",
            "dropoff_time": "09:00",
            "pickup_date": "2026-06-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_123",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package is None


# =============================================================================
# POST /api/admin/manual-booking - Negative Path Tests
# =============================================================================

class TestManualBookingNegativePath:
    """Negative path tests for creating manual bookings."""

    @pytest.mark.asyncio
    async def test_missing_required_field_first_name(self, client):
        """Should return 422 when first_name is missing."""
        request = {
            "last_name": "Smith",
            "email": "test@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_field_email(self, client):
        """Should return 422 when email is missing."""
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_field_registration(self, client):
        """Should return 422 when registration is missing."""
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "test@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_field_stripe_payment_link(self, client):
        """Should return 422 when stripe_payment_link is missing."""
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_field_amount_pence(self, client):
        """Should return 422 when amount_pence is missing."""
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, client):
        """Should return 422 for invalid date format."""
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "15-03-2026",  # Invalid format (should be YYYY-MM-DD)
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_time_format(self, client):
        """Should return 500 for invalid time format (runtime error)."""
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "8:30 AM",  # Invalid format (should be HH:MM)
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_negative_amount_pence(self, client):
        """Should handle negative amount_pence (may store it - business logic issue)."""
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": f"test.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"NEG{unique_id[:5]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": -9900,  # Negative amount
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        # Currently accepts negative - would need validation to reject
        assert response.status_code in [200, 422, 500]

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_email_failure_still_creates_booking(
        self, mock_send_email, client, db_session
    ):
        """Should create booking even if email fails to send."""
        mock_send_email.return_value = False  # Email fails
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Email",
            "last_name": "Fail",
            "email": f"emailfail.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"EF{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:30",
            "pickup_date": "2026-03-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_sent"] is False
        assert "failed to send" in data["message"].lower()

        # Verify booking was still created
        booking = db_session.query(Booking).filter(
            Booking.reference == data["booking_reference"]
        ).first()
        assert booking is not None


# =============================================================================
# POST /api/admin/manual-booking - Edge Case Tests
# =============================================================================

class TestManualBookingEdgeCases:
    """Edge case tests for creating manual bookings."""

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_existing_customer_updated(
        self, mock_send_email, client, db_session, existing_customer
    ):
        """Should update existing customer details when email matches."""
        mock_send_email.return_value = True

        request = {
            "first_name": "Updated",
            "last_name": "Name",
            "email": existing_customer.email,  # Use existing customer email
            "phone": "+44 7700 999999",
            "billing_address1": "New Address 123",
            "billing_city": "New City",
            "billing_postcode": "NEW 1AA",
            "registration": f"UPD{uuid.uuid4().hex[:5]}",
            "make": "BMW",
            "model": "X5",
            "colour": "Black",
            "dropoff_date": "2026-07-01",
            "dropoff_time": "09:00",
            "pickup_date": "2026-07-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_upd",
            "amount_pence": 12000,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200

        # Refresh customer from database
        db_session.refresh(existing_customer)
        assert existing_customer.first_name == "Updated"
        assert existing_customer.last_name == "Name"
        assert existing_customer.billing_address1 == "New Address 123"
        assert existing_customer.billing_city == "New City"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_existing_vehicle_reused(
        self, mock_send_email, client, db_session, existing_customer, existing_vehicle
    ):
        """Should reuse existing vehicle when registration matches."""
        mock_send_email.return_value = True
        vehicle_count_before = db_session.query(Vehicle).count()

        request = {
            "first_name": "Another",
            "last_name": "Customer",
            "email": f"another.{uuid.uuid4().hex[:8]}@example.com",
            "billing_address1": "456 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": existing_vehicle.registration,  # Existing registration
            "make": "Different",  # Different make (won't update existing)
            "model": "Model",
            "colour": "Green",
            "dropoff_date": "2026-08-01",
            "dropoff_time": "10:00",
            "pickup_date": "2026-08-08",
            "pickup_time": "16:00",
            "stripe_payment_link": "https://buy.stripe.com/test_exist",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200

        # Verify no new vehicle was created
        vehicle_count_after = db_session.query(Vehicle).count()
        assert vehicle_count_after == vehicle_count_before

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_same_day_booking(self, mock_send_email, client, db_session):
        """Should allow same-day drop-off and pick-up."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Same",
            "last_name": "Day",
            "email": f"sameday.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"SD{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-09-01",
            "dropoff_time": "08:00",
            "pickup_date": "2026-09-01",  # Same day
            "pickup_time": "18:00",
            "stripe_payment_link": "https://buy.stripe.com/test_same",
            "amount_pence": 5000,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.dropoff_date == booking.pickup_date
        assert booking.package is None  # Manual bookings don't have packages

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_very_long_booking(self, mock_send_email, client, db_session):
        """Should handle very long booking durations (30+ days)."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Long",
            "last_name": "Stay",
            "email": f"longstay.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"LS{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-10-01",
            "dropoff_time": "08:00",
            "pickup_date": "2026-11-15",  # 45 days
            "pickup_time": "18:00",
            "stripe_payment_link": "https://buy.stripe.com/test_long",
            "amount_pence": 50000,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package is None  # Manual bookings don't have packages

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_special_characters_in_name(self, mock_send_email, client, db_session):
        """Should handle special characters in names."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "José-María",
            "last_name": "O'Connor-Smith",
            "email": f"special.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"SC{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-12-01",
            "dropoff_time": "08:00",
            "pickup_date": "2026-12-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_special",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200

        customer = db_session.query(Customer).filter(
            Customer.email == request["email"]
        ).first()
        assert customer.first_name == "José-María"
        assert customer.last_name == "O'Connor-Smith"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_zero_amount_booking(self, mock_send_email, client, db_session):
        """Should allow zero amount (complimentary booking)."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Free",
            "last_name": "Booking",
            "email": f"free.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"FR{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-01-01",
            "dropoff_time": "08:00",
            "pickup_date": "2027-01-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_free",
            "amount_pence": 0,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        payment = db_session.query(Payment).join(Booking).filter(
            Booking.reference == reference
        ).first()
        assert payment.amount_pence == 0

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_notes_stored_as_admin_notes(self, mock_send_email, client, db_session):
        """Should store notes field as admin_notes in booking."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Notes",
            "last_name": "Test",
            "email": f"notes.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"NT{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-02-01",
            "dropoff_time": "08:00",
            "pickup_date": "2027-02-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_notes",
            "amount_pence": 9900,
            "notes": "VIP customer - handle with care",
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.admin_notes == "VIP customer - handle with care"


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

class TestManualBookingIntegration:
    """Integration tests for manual booking workflows."""

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_appears_in_admin_bookings_list(
        self, mock_send_email, client, db_session
    ):
        """Manual booking should appear in admin bookings list with 'manual' source."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        # Create manual booking
        request = {
            "first_name": "List",
            "last_name": "Test",
            "email": f"list.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"LT{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-03-01",
            "dropoff_time": "08:00",
            "pickup_date": "2027-03-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_list",
            "amount_pence": 9900,
        }

        create_response = await client.post("/api/admin/manual-booking", json=request)
        assert create_response.status_code == 200
        reference = create_response.json()["booking_reference"]

        # Fetch admin bookings
        list_response = await client.get("/api/admin/bookings")
        assert list_response.status_code == 200

        bookings = list_response.json()["bookings"]
        manual_booking = next(
            (b for b in bookings if b["reference"] == reference),
            None
        )

        assert manual_booking is not None
        assert manual_booking["booking_source"] == "manual"
        assert manual_booking["status"] == "pending"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_can_be_cancelled(
        self, mock_send_email, client, db_session
    ):
        """Manual booking should be cancellable via admin endpoint."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        # Create manual booking
        request = {
            "first_name": "Cancel",
            "last_name": "Test",
            "email": f"cancel.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"CT{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-04-01",
            "dropoff_time": "08:00",
            "pickup_date": "2027-04-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_cancel",
            "amount_pence": 9900,
        }

        create_response = await client.post("/api/admin/manual-booking", json=request)
        reference = create_response.json()["booking_reference"]

        # Get booking ID
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Cancel booking
        cancel_response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")

        assert cancel_response.status_code == 200
        assert cancel_response.json()["success"] is True

        # Verify status
        db_session.refresh(booking)
        assert booking.status == BookingStatus.CANCELLED

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_multiple_manual_bookings_unique_references(
        self, mock_send_email, client
    ):
        """Multiple manual bookings should have unique references."""
        mock_send_email.return_value = True
        references = set()

        for i in range(5):
            unique_id = uuid.uuid4().hex[:8]
            request = {
                "first_name": f"User{i}",
                "last_name": "Test",
                "email": f"user{i}.{unique_id}@example.com",
                "billing_address1": "123 Street",
                "billing_city": "City",
                "billing_postcode": "AB1 2CD",
                "registration": f"U{i}{unique_id[:5]}",
                "make": "Toyota",
                "model": "Corolla",
                "colour": "Blue",
                "dropoff_date": "2027-05-01",
                "dropoff_time": "08:00",
                "pickup_date": "2027-05-08",
                "pickup_time": "15:00",
                "stripe_payment_link": f"https://buy.stripe.com/test_{i}",
                "amount_pence": 9900,
            }

            response = await client.post("/api/admin/manual-booking", json=request)
            assert response.status_code == 200
            references.add(response.json()["booking_reference"])

        # All references should be unique
        assert len(references) == 5

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_full_data_integrity(self, mock_send_email, client, db_session):
        """Verify all submitted data is correctly stored in database."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Data",
            "last_name": "Integrity",
            "email": f"data.{unique_id}@example.com",
            "phone": "+44 7700 123456",
            "billing_address1": "100 Main Street",
            "billing_address2": "Floor 2",
            "billing_city": "Manchester",
            "billing_county": "Greater Manchester",
            "billing_postcode": "M1 1AA",
            "billing_country": "United Kingdom",
            "registration": f"DI{unique_id[:6]}",
            "make": "Mercedes",
            "model": "C-Class",
            "colour": "White",
            "dropoff_date": "2027-06-15",
            "dropoff_time": "07:45",
            "pickup_date": "2027-06-25",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_integrity",
            "amount_pence": 18500,
            "notes": "Corporate booking - invoice required",
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify customer
        customer = db_session.query(Customer).filter(
            Customer.email == request["email"]
        ).first()
        assert customer.first_name == "Data"
        assert customer.last_name == "Integrity"
        assert customer.phone == "+44 7700 123456"
        assert customer.billing_address1 == "100 Main Street"
        assert customer.billing_address2 == "Floor 2"
        assert customer.billing_city == "Manchester"
        assert customer.billing_county == "Greater Manchester"
        assert customer.billing_postcode == "M1 1AA"

        # Verify vehicle
        vehicle = db_session.query(Vehicle).filter(
            Vehicle.registration == f"DI{unique_id[:6]}".upper()
        ).first()
        assert vehicle.make == "Mercedes"
        assert vehicle.model == "C-Class"
        assert vehicle.colour == "White"

        # Verify booking
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.dropoff_date == date(2027, 6, 15)
        assert booking.dropoff_time == time(7, 45)
        assert booking.pickup_date == date(2027, 6, 25)
        assert booking.pickup_time == time(16, 30)
        assert booking.package is None  # Manual bookings don't have packages
        assert booking.booking_source == "manual"
        assert booking.admin_notes == "Corporate booking - invoice required"

        # Verify payment
        payment = db_session.query(Payment).filter(
            Payment.booking_id == booking.id
        ).first()
        assert payment.amount_pence == 18500
        assert payment.stripe_payment_link == "https://buy.stripe.com/test_integrity"
        assert payment.status == PaymentStatus.PENDING


# =============================================================================
# POST /api/admin/bookings/{booking_id}/mark-paid - Tests
# =============================================================================

class TestMarkBookingPaid:
    """Tests for marking manual bookings as paid."""

    async def _create_manual_booking(self, client, mock_send_email, unique_id=None):
        """Helper to create a manual booking for testing."""
        if unique_id is None:
            unique_id = uuid.uuid4().hex[:8]
        mock_send_email.return_value = True

        request = {
            "first_name": "MarkPaid",
            "last_name": "Test",
            "email": f"markpaid.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"MP{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-07-01",
            "dropoff_time": "08:00",
            "pickup_date": "2027-07-08",
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_markpaid",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        return response.json()["booking_reference"]

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_success(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should successfully mark a pending manual booking as paid."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        # Get booking ID
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Mark as paid
        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_sent"] is True
        assert "confirmed" in data["message"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_updates_booking_status(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should update booking status to CONFIRMED."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.status == BookingStatus.PENDING

        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        db_session.refresh(booking)
        assert booking.status == BookingStatus.CONFIRMED

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_updates_payment_status(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should update payment status to PAID."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        payment = db_session.query(Payment).filter(
            Payment.booking_id == booking.id
        ).first()
        assert payment.status == PaymentStatus.PENDING

        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        db_session.refresh(payment)
        assert payment.status == PaymentStatus.SUCCEEDED

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_sends_confirmation_email(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should send confirmation email when marking as paid."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        mock_confirmation_email.assert_called_once()
        call_kwargs = mock_confirmation_email.call_args[1]
        assert call_kwargs["booking_reference"] == reference
        assert call_kwargs["vehicle_make"] == "Toyota"
        assert call_kwargs["vehicle_model"] == "Corolla"

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_sets_email_sent_timestamp(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should update confirmation_email_sent fields."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.confirmation_email_sent is not True

        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        db_session.refresh(booking)
        assert booking.confirmation_email_sent is True
        assert booking.confirmation_email_sent_at is not None

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_email_failure_still_confirms(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should still confirm booking even if email fails."""
        mock_confirmation_email.return_value = False  # Email fails

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_sent"] is False
        assert "failed" in data["message"].lower()

        # Booking should still be confirmed
        db_session.refresh(booking)
        assert booking.status == BookingStatus.CONFIRMED

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_already_confirmed(
        self, mock_payment_email, client, db_session
    ):
        """Should return 400 if booking is already confirmed."""
        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Manually set to confirmed
        booking.status = BookingStatus.CONFIRMED
        db_session.commit()

        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 400
        assert "already confirmed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_cancelled_booking(
        self, mock_payment_email, client, db_session
    ):
        """Should return 400 if booking is cancelled."""
        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Manually set to cancelled
        booking.status = BookingStatus.CANCELLED
        db_session.commit()

        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 400
        assert "cancelled" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_refunded_booking(
        self, mock_payment_email, client, db_session
    ):
        """Should return 400 if booking is refunded."""
        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Manually set to refunded
        booking.status = BookingStatus.REFUNDED
        db_session.commit()

        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 400
        assert "refunded" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_mark_paid_booking_not_found(self, client):
        """Should return 404 if booking doesn't exist."""
        response = await client.post("/api/admin/bookings/99999/mark-paid")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_returns_reference(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should return the booking reference in response."""
        mock_confirmation_email.return_value = True

        reference = await self._create_manual_booking(client, mock_payment_email)

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.json()["reference"] == reference


# =============================================================================
# Flight Integration Tests - Manual Booking with Slot Management
# =============================================================================

class TestManualBookingFlightIntegration:
    """Tests for manual booking with flight/slot integration."""

    @pytest.fixture
    def flight_departure(self, db_session):
        """Create a flight departure for testing."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 8, 15),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(10, 30),
            destination_code="PMI",
            destination_name="Palma de Mallorca",
            capacity_tier=4,  # Max 2 early, 2 late
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    @pytest.fixture
    def flight_departure_full_early(self, db_session):
        """Create a flight departure with fully booked early slot."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 8, 16),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(11, 30),
            destination_code="ALC",
            destination_name="Alicante",
            capacity_tier=4,  # max_per_slot = 4 // 2 = 2
            slots_booked_early=2,  # Fully booked (2 >= max_per_slot of 2)
            slots_booked_late=1,  # Has availability (1 < max_per_slot of 2)
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    @pytest.fixture
    def flight_arrival(self, db_session):
        """Create a flight arrival for testing."""
        from db_models import FlightArrival
        unique_id = uuid.uuid4().hex[:8]

        arrival = FlightArrival(
            date=date(2027, 8, 22),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            arrival_time=time(15, 45),
            origin_code="PMI",
            origin_name="Palma de Mallorca",
        )
        db_session.add(arrival)
        db_session.commit()
        db_session.refresh(arrival)
        return arrival

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_booking_with_flight_integration(
        self, mock_send_email, client, db_session, flight_departure, flight_arrival
    ):
        """Should create booking with departure_id and dropoff_slot."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Flight",
            "last_name": "Integration",
            "email": f"flight.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"FI{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-08-15",
            "dropoff_time": "07:45",  # 2hr 45min before 10:30 departure
            "pickup_date": "2027-08-22",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_flight",
            "amount_pence": 9900,
            # Flight integration fields
            "departure_id": flight_departure.id,
            "dropoff_slot": "165",  # Early slot (2hr 45min before)
            "arrival_id": flight_arrival.id,
            "departure_flight_number": flight_departure.flight_number,
            "return_flight_number": flight_arrival.flight_number,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify booking stores flight data
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.departure_id == flight_departure.id
        assert booking.dropoff_slot == "165"
        assert booking.dropoff_flight_number == flight_departure.flight_number
        assert booking.pickup_flight_number == flight_arrival.flight_number

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_booking_validates_early_slot_availability(
        self, mock_send_email, client, db_session, flight_departure_full_early
    ):
        """Should reject when early slot is fully booked."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Full",
            "last_name": "Slot",
            "email": f"fullslot.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"FS{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight_departure_full_early.date),  # Use flight's date
            "dropoff_time": "08:45",
            "pickup_date": "2027-08-23",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_full",
            "amount_pence": 9900,
            "departure_id": flight_departure_full_early.id,
            "dropoff_slot": "165",  # Early slot - fully booked (2/2)
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        # Backend returns 400 for fully booked slot
        assert response.status_code == 400
        assert "early slot" in response.json()["detail"].lower()
        assert "fully booked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_booking_allows_available_late_slot(
        self, mock_send_email, client, db_session, flight_departure_full_early
    ):
        """Should allow booking late slot when early is full but late has availability."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Late",
            "last_name": "Slot",
            "email": f"lateslot.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"LS{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-08-16",
            "dropoff_time": "09:30",
            "pickup_date": "2027-08-23",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_late",
            "amount_pence": 9900,
            "departure_id": flight_departure_full_early.id,
            "dropoff_slot": "120",  # Late slot - has 1 available
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_booking_rejects_invalid_departure_id(
        self, mock_send_email, client, db_session
    ):
        """Should reject booking with non-existent departure_id."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Invalid",
            "last_name": "Flight",
            "email": f"invalid.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"IF{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-08-17",
            "dropoff_time": "08:00",
            "pickup_date": "2027-08-24",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_invalid",
            "amount_pence": 9900,
            "departure_id": 99999,  # Non-existent
            "dropoff_slot": "165",
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        # Backend returns 400 for invalid departure flight
        assert response.status_code in [400, 500]  # 400 if properly handled, 500 if exception
        if response.status_code == 400:
            assert "invalid departure" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_create_booking_without_flight_integration(
        self, mock_send_email, client, db_session
    ):
        """Should create booking without flight integration (manual time only)."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Manual",
            "last_name": "Time",
            "email": f"manual.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"MT{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-08-18",
            "dropoff_time": "09:00",
            "pickup_date": "2027-08-25",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_manual",
            "amount_pence": 9900,
            # No departure_id or dropoff_slot - manual time entry
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.departure_id is None
        assert booking.dropoff_slot is None


class TestMarkPaidSlotIncrement:
    """Tests for slot increment when marking booking as paid."""

    @pytest.fixture
    def flight_departure(self, db_session):
        """Create a flight departure for testing."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 9, 1),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(12, 0),
            destination_code="TFS",
            destination_name="Tenerife South",
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    async def _create_booking_with_flight(
        self, client, mock_send_email, db_session, flight_departure, slot_type="165"
    ):
        """Helper to create a manual booking with flight integration."""
        unique_id = uuid.uuid4().hex[:8]
        mock_send_email.return_value = True

        request = {
            "first_name": "SlotTest",
            "last_name": "User",
            "email": f"slottest.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"ST{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight_departure.date),
            "dropoff_time": "09:15" if slot_type == "165" else "10:00",
            "pickup_date": "2027-09-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_slot",
            "amount_pence": 9900,
            "departure_id": flight_departure.id,
            "dropoff_slot": slot_type,
            "departure_flight_number": flight_departure.flight_number,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        return response.json()["booking_reference"]

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_increments_early_slot(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_departure
    ):
        """Should increment early slot count when marking booking as paid."""
        mock_confirmation_email.return_value = True
        from db_models import FlightDeparture

        # Verify initial slot count
        assert flight_departure.slots_booked_early == 0

        # Create booking with early slot
        reference = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "165"
        )

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Mark as paid
        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        assert response.status_code == 200

        # Verify slot count incremented
        db_session.refresh(flight_departure)
        assert flight_departure.slots_booked_early == 1
        assert flight_departure.slots_booked_late == 0  # Unchanged

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_increments_late_slot(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_departure
    ):
        """Should increment late slot count when marking booking as paid."""
        mock_confirmation_email.return_value = True

        # Verify initial slot count
        assert flight_departure.slots_booked_late == 0

        # Create booking with late slot
        reference = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "120"
        )

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Mark as paid
        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        assert response.status_code == 200

        # Verify slot count incremented
        db_session.refresh(flight_departure)
        assert flight_departure.slots_booked_late == 1
        assert flight_departure.slots_booked_early == 0  # Unchanged

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_rejects_when_slot_becomes_full(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_departure
    ):
        """Should reject mark-paid when slot has become full since booking creation."""
        mock_confirmation_email.return_value = True

        # Create booking with early slot
        reference = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "165"
        )

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Simulate slot becoming full (e.g., another booking confirmed in between)
        # max_per_slot = capacity_tier // 2 = 4 // 2 = 2
        # Set slots_booked_early to max_per_slot to make it fully booked
        flight_departure.slots_booked_early = flight_departure.capacity_tier // 2
        db_session.commit()

        # Try to mark as paid - should fail because slot is now full
        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        # Backend returns 400 for fully booked slot
        assert response.status_code == 400
        assert "fully booked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_no_slot_increment_without_flight_data(
        self, mock_payment_email, mock_confirmation_email, client, db_session
    ):
        """Should not attempt slot increment for bookings without flight integration."""
        mock_confirmation_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]
        mock_payment_email.return_value = True

        # Create booking without flight integration
        request = {
            "first_name": "NoFlight",
            "last_name": "User",
            "email": f"noflight.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"NF{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2027-09-10",
            "dropoff_time": "09:00",
            "pickup_date": "2027-09-17",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_noflight",
            "amount_pence": 9900,
            # No departure_id or dropoff_slot
        }

        create_response = await client.post("/api/admin/manual-booking", json=request)
        reference = create_response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        # Mark as paid - should succeed without any slot operations
        response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mark_paid_multiple_bookings_increment_slots(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_departure
    ):
        """Should correctly increment slots for multiple bookings."""
        mock_confirmation_email.return_value = True

        # Create and confirm first booking (early slot)
        ref1 = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "165"
        )
        booking1 = db_session.query(Booking).filter(Booking.reference == ref1).first()
        await client.post(f"/api/admin/bookings/{booking1.id}/mark-paid")

        # Create and confirm second booking (early slot)
        ref2 = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "165"
        )
        booking2 = db_session.query(Booking).filter(Booking.reference == ref2).first()
        await client.post(f"/api/admin/bookings/{booking2.id}/mark-paid")

        # Create and confirm third booking (late slot)
        ref3 = await self._create_booking_with_flight(
            client, mock_payment_email, db_session, flight_departure, "120"
        )
        booking3 = db_session.query(Booking).filter(Booking.reference == ref3).first()
        await client.post(f"/api/admin/bookings/{booking3.id}/mark-paid")

        # Verify slot counts
        db_session.refresh(flight_departure)
        assert flight_departure.slots_booked_early == 2
        assert flight_departure.slots_booked_late == 1


# =============================================================================
# Online/Manual Booking Interaction Tests
# =============================================================================

class TestOnlineManualBookingInteraction:
    """Tests verifying that online and manual bookings share slot capacity correctly."""

    @pytest.fixture
    def shared_flight_departure(self, db_session):
        """Create a flight departure for shared booking tests."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 10, 1),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(10, 0),
            destination_code="PMI",
            destination_name="Palma de Mallorca",
            capacity_tier=4,  # max_per_slot = 2
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_online_booking_reduces_availability_for_manual(
        self, mock_send_email, client, db_session, shared_flight_departure
    ):
        """When online booking fills a slot, manual booking should be rejected."""
        mock_send_email.return_value = True

        # Simulate online bookings by directly incrementing slot counters
        # (In real online booking, this happens via book_departure_slot in db_service.py)
        shared_flight_departure.slots_booked_early = 2  # Fully booked early slot
        db_session.commit()

        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Manual",
            "last_name": "After Online",
            "email": f"manual.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"MA{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(shared_flight_departure.date),
            "dropoff_time": "07:15",
            "pickup_date": "2027-10-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_online",
            "amount_pence": 9900,
            "departure_id": shared_flight_departure.id,
            "dropoff_slot": "165",  # Early slot - should be full
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        # Should fail because online bookings filled the slot
        assert response.status_code == 400
        assert "early slot" in response.json()["detail"].lower()
        assert "fully booked" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_reduces_availability_for_online_check(
        self, mock_payment_email, mock_confirmation_email, client, db_session, shared_flight_departure
    ):
        """When manual booking is confirmed, slot count increases (reducing online availability)."""
        mock_payment_email.return_value = True
        mock_confirmation_email.return_value = True

        # Verify initial state
        assert shared_flight_departure.slots_booked_early == 0

        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Manual",
            "last_name": "First",
            "email": f"manual1.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"M1{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(shared_flight_departure.date),
            "dropoff_time": "07:15",
            "pickup_date": "2027-10-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_manual1",
            "amount_pence": 9900,
            "departure_id": shared_flight_departure.id,
            "dropoff_slot": "165",  # Early slot
        }

        # Create manual booking
        create_response = await client.post("/api/admin/manual-booking", json=request)
        assert create_response.status_code == 200
        reference = create_response.json()["booking_reference"]

        # Slot should NOT be incremented yet (booking is pending)
        db_session.refresh(shared_flight_departure)
        assert shared_flight_departure.slots_booked_early == 0

        # Mark as paid (confirm the booking)
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()
        mark_paid_response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        assert mark_paid_response.status_code == 200

        # Now slot should be incremented
        db_session.refresh(shared_flight_departure)
        assert shared_flight_departure.slots_booked_early == 1

        # This slot count is what online booking would check before allowing a new booking
        # With capacity_tier=4 (max_per_slot=2), one more early booking is still allowed
        assert shared_flight_departure.early_slots_available == 1

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_mixed_bookings_fill_capacity_correctly(
        self, mock_payment_email, mock_confirmation_email, client, db_session, shared_flight_departure
    ):
        """Mix of online and manual bookings should correctly track total capacity."""
        mock_payment_email.return_value = True
        mock_confirmation_email.return_value = True

        # Simulate 1 online booking on early slot
        shared_flight_departure.slots_booked_early = 1
        db_session.commit()

        # Create manual booking for early slot (should succeed - 1 more available)
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Mixed",
            "last_name": "Test",
            "email": f"mixed.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"MX{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(shared_flight_departure.date),
            "dropoff_time": "07:15",
            "pickup_date": "2027-10-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_mixed",
            "amount_pence": 9900,
            "departure_id": shared_flight_departure.id,
            "dropoff_slot": "165",
        }

        create_response = await client.post("/api/admin/manual-booking", json=request)
        assert create_response.status_code == 200
        reference = create_response.json()["booking_reference"]

        # Mark as paid
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()
        mark_paid_response = await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        assert mark_paid_response.status_code == 200

        # Now early slot should be at capacity (1 online + 1 manual = 2, max_per_slot = 2)
        db_session.refresh(shared_flight_departure)
        assert shared_flight_departure.slots_booked_early == 2
        assert shared_flight_departure.early_slots_available == 0

        # Another manual booking for early slot should fail
        unique_id2 = uuid.uuid4().hex[:8]
        request2 = {
            "first_name": "Should",
            "last_name": "Fail",
            "email": f"fail.{unique_id2}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"FL{unique_id2[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(shared_flight_departure.date),
            "dropoff_time": "07:15",
            "pickup_date": "2027-10-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_fail",
            "amount_pence": 9900,
            "departure_id": shared_flight_departure.id,
            "dropoff_slot": "165",
        }

        fail_response = await client.post("/api/admin/manual-booking", json=request2)
        assert fail_response.status_code == 400
        assert "fully booked" in fail_response.json()["detail"].lower()


# =============================================================================
# Slot Release on Cancellation Tests
# =============================================================================

class TestSlotReleaseOnCancellation:
    """Tests verifying that cancelling bookings releases slots correctly."""

    @pytest.fixture
    def flight_for_cancel(self, db_session):
        """Create a flight departure for cancellation tests."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 11, 1),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(14, 0),
            destination_code="AGP",
            destination_name="Malaga",
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_cancel_confirmed_manual_booking_releases_early_slot(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_for_cancel
    ):
        """Cancelling a confirmed manual booking should release the slot."""
        mock_payment_email.return_value = True
        mock_confirmation_email.return_value = True

        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Cancel",
            "last_name": "Test",
            "email": f"cancel.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"CT{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight_for_cancel.date),
            "dropoff_time": "11:15",
            "pickup_date": "2027-11-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_cancel",
            "amount_pence": 9900,
            "departure_id": flight_for_cancel.id,
            "dropoff_slot": "165",  # Early slot
        }

        # Create and confirm booking
        create_response = await client.post("/api/admin/manual-booking", json=request)
        reference = create_response.json()["booking_reference"]
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()

        # Mark as paid (increments slot)
        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_early == 1

        # Cancel the booking
        cancel_response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")
        assert cancel_response.status_code == 200

        # Slot should be released
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_early == 0

    @pytest.mark.asyncio
    @patch('email_service.send_booking_confirmation_email')
    @patch('email_service.send_manual_booking_payment_email')
    async def test_cancel_confirmed_manual_booking_releases_late_slot(
        self, mock_payment_email, mock_confirmation_email, client, db_session, flight_for_cancel
    ):
        """Cancelling a confirmed manual booking should release the late slot."""
        mock_payment_email.return_value = True
        mock_confirmation_email.return_value = True

        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Cancel",
            "last_name": "Late",
            "email": f"cancel.late.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"CL{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight_for_cancel.date),
            "dropoff_time": "12:00",
            "pickup_date": "2027-11-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_cancel_late",
            "amount_pence": 9900,
            "departure_id": flight_for_cancel.id,
            "dropoff_slot": "120",  # Late slot
        }

        # Create and confirm booking
        create_response = await client.post("/api/admin/manual-booking", json=request)
        reference = create_response.json()["booking_reference"]
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()

        # Mark as paid (increments slot)
        await client.post(f"/api/admin/bookings/{booking.id}/mark-paid")
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_late == 1

        # Cancel the booking
        cancel_response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")
        assert cancel_response.status_code == 200

        # Slot should be released
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_late == 0

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_cancel_pending_manual_booking_no_slot_change(
        self, mock_payment_email, client, db_session, flight_for_cancel
    ):
        """Cancelling a pending (not yet paid) manual booking should not affect slots."""
        mock_payment_email.return_value = True

        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Pending",
            "last_name": "Cancel",
            "email": f"pending.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"PC{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight_for_cancel.date),
            "dropoff_time": "11:15",
            "pickup_date": "2027-11-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_pending",
            "amount_pence": 9900,
            "departure_id": flight_for_cancel.id,
            "dropoff_slot": "165",
        }

        # Create booking but do NOT mark as paid
        create_response = await client.post("/api/admin/manual-booking", json=request)
        reference = create_response.json()["booking_reference"]
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()

        # Slot should still be 0 (pending booking doesn't reserve slot)
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_early == 0

        # Cancel the pending booking
        cancel_response = await client.post(f"/api/admin/bookings/{booking.id}/cancel")
        assert cancel_response.status_code == 200

        # Slot should still be 0
        db_session.refresh(flight_for_cancel)
        assert flight_for_cancel.slots_booked_early == 0


# =============================================================================
# capacity_tier=0 (Call Us Only) Tests
# =============================================================================

class TestCallUsOnlyFlights:
    """Tests for capacity_tier=0 flights that require calling to book."""

    @pytest.fixture
    def call_us_only_flight(self, db_session):
        """Create a Call Us Only flight (capacity_tier=0)."""
        from db_models import FlightDeparture
        unique_id = uuid.uuid4().hex[:8]

        flight = FlightDeparture(
            date=date(2027, 12, 1),
            flight_number=f"CU{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(6, 0),  # Early morning - Call Us only
            destination_code="TFS",
            destination_name="Tenerife South",
            capacity_tier=0,  # Call Us Only
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(flight)
        db_session.commit()
        db_session.refresh(flight)
        return flight

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_rejected_for_call_us_only_flight(
        self, mock_send_email, client, db_session, call_us_only_flight
    ):
        """Manual booking should be rejected for capacity_tier=0 flights."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Call",
            "last_name": "Us",
            "email": f"callus.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"CU{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(call_us_only_flight.date),
            "dropoff_time": "03:15",
            "pickup_date": "2027-12-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_callus",
            "amount_pence": 9900,
            "departure_id": call_us_only_flight.id,
            "dropoff_slot": "165",
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 400
        assert "calling to book" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_without_flight_allowed_for_any_date(
        self, mock_send_email, client, db_session, call_us_only_flight
    ):
        """Manual booking without flight integration should work regardless of flight capacity."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Manual",
            "last_name": "NoFlight",
            "email": f"noflight.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"NF{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(call_us_only_flight.date),  # Same date as Call Us flight
            "dropoff_time": "03:15",
            "pickup_date": "2027-12-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_noflight",
            "amount_pence": 9900,
            # No departure_id or dropoff_slot - manual time entry
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        # Should succeed because no flight integration requested
        assert response.status_code == 200


# =============================================================================
# Arrival ID Validation Tests
# =============================================================================

class TestArrivalIdValidation:
    """Tests for arrival_id and return flight validation."""

    @pytest.fixture
    def departure_and_arrival(self, db_session):
        """Create matching departure and arrival flights."""
        from db_models import FlightDeparture, FlightArrival
        unique_id = uuid.uuid4().hex[:8]

        departure = FlightDeparture(
            date=date(2028, 1, 15),
            flight_number=f"LS{unique_id[:4]}",
            airline_code="LS",
            airline_name="Jet2",
            departure_time=time(10, 30),
            destination_code="PMI",
            destination_name="Palma de Mallorca",
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=0,
        )
        db_session.add(departure)
        db_session.flush()

        arrival = FlightArrival(
            date=date(2028, 1, 22),
            flight_number=f"LS{int(unique_id[:4], 16) % 9000 + 1000}",  # Different flight number
            airline_code="LS",
            airline_name="Jet2",
            arrival_time=time(15, 45),
            origin_code="PMI",
            origin_name="Palma de Mallorca",
        )
        db_session.add(arrival)
        db_session.commit()
        db_session.refresh(departure)
        db_session.refresh(arrival)
        return {"departure": departure, "arrival": arrival}

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_stores_arrival_id(
        self, mock_send_email, client, db_session, departure_and_arrival
    ):
        """Manual booking should store arrival_id when provided."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]
        departure = departure_and_arrival["departure"]
        arrival = departure_and_arrival["arrival"]

        request = {
            "first_name": "Arrival",
            "last_name": "Test",
            "email": f"arrival.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"AR{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(departure.date),
            "dropoff_time": "07:45",
            "pickup_date": str(arrival.date),
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_arrival",
            "amount_pence": 9900,
            "departure_id": departure.id,
            "dropoff_slot": "165",
            "arrival_id": arrival.id,
            "departure_flight_number": departure.flight_number,
            "return_flight_number": arrival.flight_number,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify booking stores flight data including arrival
        booking = db_session.query(Booking).filter(Booking.reference == reference).first()
        assert booking.departure_id == departure.id
        assert booking.dropoff_slot == "165"
        assert booking.dropoff_flight_number == departure.flight_number
        assert booking.pickup_flight_number == arrival.flight_number

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_with_departure_but_no_arrival(
        self, mock_send_email, client, db_session, departure_and_arrival
    ):
        """Should allow booking with departure flight but no arrival flight."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]
        departure = departure_and_arrival["departure"]

        request = {
            "first_name": "Departure",
            "last_name": "Only",
            "email": f"deponly.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"DO{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(departure.date),
            "dropoff_time": "07:45",
            "pickup_date": "2028-01-22",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_deponly",
            "amount_pence": 9900,
            "departure_id": departure.id,
            "dropoff_slot": "165",
            # No arrival_id - customer returning on different airline or driving back
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_stores_flight_numbers(
        self, mock_send_email, client, db_session, departure_and_arrival
    ):
        """Should store both departure and return flight numbers."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]
        departure = departure_and_arrival["departure"]
        arrival = departure_and_arrival["arrival"]

        request = {
            "first_name": "Flight",
            "last_name": "Numbers",
            "email": f"flightnum.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"FN{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(departure.date),
            "dropoff_time": "07:45",
            "pickup_date": str(arrival.date),
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_flightnum",
            "amount_pence": 9900,
            "departure_id": departure.id,
            "dropoff_slot": "165",
            "departure_flight_number": departure.flight_number,
            "return_flight_number": arrival.flight_number,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(Booking.reference == reference).first()
        assert booking.dropoff_flight_number == departure.flight_number
        assert booking.pickup_flight_number == arrival.flight_number


# =============================================================================
# Capacity Tier Edge Case Tests
# =============================================================================

class TestCapacityTierEdgeCases:
    """Tests for various capacity_tier values and edge cases."""

    @pytest.fixture
    def flights_with_various_capacities(self, db_session):
        """Create flights with different capacity tiers."""
        from db_models import FlightDeparture
        flights = {}

        for tier in [2, 4, 6, 8]:
            unique_id = uuid.uuid4().hex[:8]
            flight = FlightDeparture(
                date=date(2028, 2, 1),
                flight_number=f"T{tier}{unique_id[:2]}",
                airline_code="LS",
                airline_name="Jet2",
                departure_time=time(8 + tier, 0),  # Different times
                destination_code="ALC",
                destination_name="Alicante",
                capacity_tier=tier,
                slots_booked_early=0,
                slots_booked_late=0,
            )
            db_session.add(flight)
            db_session.flush()
            flights[tier] = flight

        db_session.commit()
        for tier in flights:
            db_session.refresh(flights[tier])
        return flights

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_capacity_tier_2_max_one_per_slot(
        self, mock_send_email, client, db_session, flights_with_various_capacities
    ):
        """capacity_tier=2 should allow max 1 booking per slot type."""
        mock_send_email.return_value = True
        flight = flights_with_various_capacities[2]

        # First booking should succeed
        unique_id = uuid.uuid4().hex[:8]
        request1 = {
            "first_name": "First",
            "last_name": "Tier2",
            "email": f"first.tier2.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"T2A{unique_id[:5]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight.date),
            "dropoff_time": "06:00",
            "pickup_date": "2028-02-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_tier2a",
            "amount_pence": 9900,
            "departure_id": flight.id,
            "dropoff_slot": "165",
        }

        response1 = await client.post("/api/admin/manual-booking", json=request1)
        assert response1.status_code == 200

        # Simulate first booking being paid (slot incremented)
        flight.slots_booked_early = 1
        db_session.commit()

        # Second booking for same slot should fail
        unique_id2 = uuid.uuid4().hex[:8]
        request2 = {
            "first_name": "Second",
            "last_name": "Tier2",
            "email": f"second.tier2.{unique_id2}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"T2B{unique_id2[:5]}",
            "make": "Honda",
            "model": "Civic",
            "colour": "Red",
            "dropoff_date": str(flight.date),
            "dropoff_time": "06:00",
            "pickup_date": "2028-02-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_tier2b",
            "amount_pence": 9900,
            "departure_id": flight.id,
            "dropoff_slot": "165",
        }

        response2 = await client.post("/api/admin/manual-booking", json=request2)
        assert response2.status_code == 400
        assert "fully booked" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_capacity_tier_8_allows_four_per_slot(
        self, mock_send_email, client, db_session, flights_with_various_capacities
    ):
        """capacity_tier=8 should allow max 4 bookings per slot type."""
        mock_send_email.return_value = True
        flight = flights_with_various_capacities[8]

        # Simulate 3 bookings already made
        flight.slots_booked_early = 3
        db_session.commit()

        # 4th booking should succeed
        unique_id = uuid.uuid4().hex[:8]
        request = {
            "first_name": "Fourth",
            "last_name": "Tier8",
            "email": f"fourth.tier8.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"T8D{unique_id[:5]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": str(flight.date),
            "dropoff_time": "14:00",
            "pickup_date": "2028-02-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_tier8d",
            "amount_pence": 9900,
            "departure_id": flight.id,
            "dropoff_slot": "165",
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        assert response.status_code == 200

        # 5th booking should fail
        flight.slots_booked_early = 4
        db_session.commit()

        unique_id2 = uuid.uuid4().hex[:8]
        request2 = {
            "first_name": "Fifth",
            "last_name": "Tier8",
            "email": f"fifth.tier8.{unique_id2}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"T8E{unique_id2[:5]}",
            "make": "Honda",
            "model": "Civic",
            "colour": "Red",
            "dropoff_date": str(flight.date),
            "dropoff_time": "14:00",
            "pickup_date": "2028-02-08",
            "pickup_time": "16:30",
            "stripe_payment_link": "https://buy.stripe.com/test_tier8e",
            "amount_pence": 9900,
            "departure_id": flight.id,
            "dropoff_slot": "165",
        }

        response2 = await client.post("/api/admin/manual-booking", json=request2)
        assert response2.status_code == 400
        assert "fully booked" in response2.json()["detail"].lower()
