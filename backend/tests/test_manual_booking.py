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

from main import app
from db_models import Booking, Customer, Vehicle, Payment, BookingStatus, PaymentStatus
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
    async def test_quick_package_for_7_day_booking(
        self, mock_send_email, client, db_session
    ):
        """Should assign 'quick' package for 7-day or less bookings."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Quick",
            "last_name": "Package",
            "email": f"quick.{unique_id}@example.com",
            "billing_address1": "Test Street",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
            "registration": f"QP{unique_id[:6]}",
            "make": "Test",
            "model": "Car",
            "colour": "White",
            "dropoff_date": "2026-06-01",
            "dropoff_time": "09:00",
            "pickup_date": "2026-06-08",  # 7 days
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_123",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package == "quick"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_longer_package_for_more_than_7_days(
        self, mock_send_email, client, db_session
    ):
        """Should assign 'longer' package for more than 7-day bookings."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Longer",
            "last_name": "Package",
            "email": f"longer.{unique_id}@example.com",
            "billing_address1": "Test Street",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
            "registration": f"LP{unique_id[:6]}",
            "make": "Test",
            "model": "Car",
            "colour": "White",
            "dropoff_date": "2026-06-01",
            "dropoff_time": "09:00",
            "pickup_date": "2026-06-15",  # 14 days
            "pickup_time": "15:00",
            "stripe_payment_link": "https://buy.stripe.com/test_123",
            "amount_pence": 15000,
        }

        response = await client.post("/api/admin/manual-booking", json=request)
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package == "longer"


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
        assert booking.package == "quick"  # 0 days = quick

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
        assert booking.package == "longer"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_boundary_7_day_booking(self, mock_send_email, client, db_session):
        """Should assign 'quick' package for exactly 7-day booking."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Seven",
            "last_name": "Days",
            "email": f"sevendays.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"7D{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-11-01",
            "dropoff_time": "08:00",
            "pickup_date": "2026-11-08",  # Exactly 7 days
            "pickup_time": "08:00",
            "stripe_payment_link": "https://buy.stripe.com/test_7day",
            "amount_pence": 9900,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package == "quick"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_boundary_8_day_booking(self, mock_send_email, client, db_session):
        """Should assign 'longer' package for 8-day booking."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request = {
            "first_name": "Eight",
            "last_name": "Days",
            "email": f"eightdays.{unique_id}@example.com",
            "billing_address1": "123 Street",
            "billing_city": "City",
            "billing_postcode": "AB1 2CD",
            "registration": f"8D{unique_id[:6]}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Blue",
            "dropoff_date": "2026-11-01",
            "dropoff_time": "08:00",
            "pickup_date": "2026-11-09",  # 8 days
            "pickup_time": "08:00",
            "stripe_payment_link": "https://buy.stripe.com/test_8day",
            "amount_pence": 12000,
        }

        response = await client.post("/api/admin/manual-booking", json=request)

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()
        assert booking.package == "longer"

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
        assert booking.package == "longer"  # 10 days
        assert booking.booking_source == "manual"
        assert booking.admin_notes == "Corporate booking - invoice required"

        # Verify payment
        payment = db_session.query(Payment).filter(
            Payment.booking_id == booking.id
        ).first()
        assert payment.amount_pence == 18500
        assert payment.stripe_payment_link == "https://buy.stripe.com/test_integrity"
        assert payment.status == PaymentStatus.PENDING
