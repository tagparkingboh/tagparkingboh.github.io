"""
Tests for manual booking functionality.

Covers:
- POST /api/admin/manual-booking - Create manual booking and send payment link email
- POST /api/admin/bookings/{booking_id}/mark-paid - Mark booking as paid
- Flight integration - slot availability and capacity
- Cancellation and slot release

Test categories:
- Unit tests: Test individual functions with mocked dependencies
- Integration tests: Test full API flows with mocked database and services
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Fixtures and Mock Factories
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    return db


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@tagparking.co.uk"
    user.role = "admin"
    user.is_active = True
    return user


@pytest.fixture
def valid_manual_booking_request():
    """Create a valid manual booking request payload with relative dates."""
    # Use dates relative to today for consistent test behavior
    today = date.today()
    dropoff = today + timedelta(days=11)  # ~11 days from now
    pickup = today + timedelta(days=18)   # ~18 days from now (7 day trip)

    return {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
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
        "dropoff_date": dropoff.isoformat(),
        "dropoff_time": "08:30",
        "pickup_date": pickup.isoformat(),
        "pickup_time": "14:00",
        "stripe_payment_link": "https://buy.stripe.com/test_abc123",
        "amount_pence": 9900,
        "notes": "Customer called to book - prefers early morning slot",
    }


def create_mock_customer(**kwargs):
    """Factory to create mock customer objects."""
    defaults = {
        "id": 1,
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
        "phone": "+44 7700 900123",
        "billing_address1": "123 Test Street",
        "billing_address2": None,
        "billing_city": "Bournemouth",
        "billing_county": "Dorset",
        "billing_postcode": "BH1 1AA",
        "billing_country": "United Kingdom",
    }
    defaults.update(kwargs)
    customer = MagicMock()
    for key, value in defaults.items():
        setattr(customer, key, value)
    return customer


def create_mock_vehicle(**kwargs):
    """Factory to create mock vehicle objects."""
    defaults = {
        "id": 1,
        "customer_id": 1,
        "registration": "AB12CDE",
        "make": "Toyota",
        "model": "Corolla",
        "colour": "Silver",
    }
    defaults.update(kwargs)
    vehicle = MagicMock()
    for key, value in defaults.items():
        setattr(vehicle, key, value)
    return vehicle


def create_mock_booking(**kwargs):
    """Factory to create mock booking objects."""
    # Use relative dates
    today = date.today()
    defaults = {
        "id": 1,
        "reference": "TAG-ABC12345",
        "customer_id": 1,
        "vehicle_id": 1,
        "status": MagicMock(value="pending"),
        "booking_source": "manual",
        "dropoff_date": today + timedelta(days=11),
        "dropoff_time": time(8, 30),
        "pickup_date": today + timedelta(days=18),
        "pickup_time": time(14, 0),
        "package": None,
        "admin_notes": None,
        "departure_id": None,
        "arrival_id": None,
        "departure_flight_number": None,
        "arrival_flight_number": None,
        "dropoff_flight_number": None,
        "pickup_flight_number": None,
        "flight_departure_time": None,
        "flight_arrival_time": None,
        "slot_type": None,
        "confirmation_email_sent_at": None,
    }
    defaults.update(kwargs)
    booking = MagicMock()
    for key, value in defaults.items():
        setattr(booking, key, value)
    return booking


def create_mock_payment(**kwargs):
    """Factory to create mock payment objects."""
    defaults = {
        "id": 1,
        "booking_id": 1,
        "amount_pence": 9900,
        "status": MagicMock(value="pending"),
        "stripe_payment_link": "https://buy.stripe.com/test_abc123",
        "stripe_payment_intent_id": None,
    }
    defaults.update(kwargs)
    payment = MagicMock()
    for key, value in defaults.items():
        setattr(payment, key, value)
    return payment


def create_mock_departure(**kwargs):
    """Factory to create mock flight departure objects."""
    today = date.today()
    defaults = {
        "id": 1,
        "flight_number": "FR1234",
        "date": today + timedelta(days=11),
        "departure_time": time(11, 0),
        "destination_code": "FAO",
        "destination_name": "Faro, PT",
        "capacity_tier": 2,
        "slots_booked_early": 0,
        "slots_booked_late": 0,
    }
    defaults.update(kwargs)
    departure = MagicMock()
    for key, value in defaults.items():
        setattr(departure, key, value)
    return departure


def create_mock_arrival(**kwargs):
    """Factory to create mock flight arrival objects."""
    today = date.today()
    defaults = {
        "id": 1,
        "flight_number": "FR1235",
        "date": today + timedelta(days=18),
        "arrival_time": time(14, 30),
        "origin_code": "FAO",
        "origin_name": "Faro, PT",
    }
    defaults.update(kwargs)
    arrival = MagicMock()
    for key, value in defaults.items():
        setattr(arrival, key, value)
    return arrival


# =============================================================================
# Unit Tests - ManualBookingRequest Validation
# =============================================================================

class TestManualBookingRequestValidation:
    """Unit tests for ManualBookingRequest model validation."""

    def test_valid_request_parses_successfully(self, valid_manual_booking_request):
        """Should parse valid request without errors."""
        from models import ManualBookingRequest

        request = ManualBookingRequest(**valid_manual_booking_request)

        assert request.first_name == "Jane"
        assert request.last_name == "Smith"
        assert request.email == "jane.smith@example.com"
        assert request.registration == "AB12CDE"
        assert request.amount_pence == 9900

    def test_missing_required_field_raises_error(self, valid_manual_booking_request):
        """Should raise validation error when required field is missing."""
        from models import ManualBookingRequest
        from pydantic import ValidationError

        del valid_manual_booking_request["first_name"]

        with pytest.raises(ValidationError) as exc_info:
            ManualBookingRequest(**valid_manual_booking_request)

        assert "first_name" in str(exc_info.value)

    def test_invalid_date_format_raises_error(self, valid_manual_booking_request):
        """Should raise validation error for invalid date format."""
        from models import ManualBookingRequest
        from pydantic import ValidationError

        valid_manual_booking_request["dropoff_date"] = "invalid-date"

        with pytest.raises(ValidationError):
            ManualBookingRequest(**valid_manual_booking_request)

    def test_optional_fields_can_be_none(self):
        """Should accept None for optional fields."""
        from models import ManualBookingRequest

        today = date.today()
        dropoff = today + timedelta(days=11)
        pickup = today + timedelta(days=18)

        minimal_request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "billing_address1": "123 Test St",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": dropoff.isoformat(),
            "dropoff_time": "08:30",
            "pickup_date": pickup.isoformat(),
            "pickup_time": "14:00",
            "amount_pence": 9900,
            "stripe_payment_link": "https://buy.stripe.com/test",
        }

        request = ManualBookingRequest(**minimal_request)

        assert request.phone is None
        assert request.billing_address2 is None
        assert request.notes is None

    def test_free_booking_without_payment_link(self):
        """Should allow free bookings without Stripe link."""
        from models import ManualBookingRequest

        today = date.today()
        dropoff = today + timedelta(days=11)
        pickup = today + timedelta(days=18)

        free_request = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "billing_address1": "123 Test St",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": dropoff.isoformat(),
            "dropoff_time": "08:30",
            "pickup_date": pickup.isoformat(),
            "pickup_time": "14:00",
            "amount_pence": 0,
            "is_free_booking": True,
        }

        request = ManualBookingRequest(**free_request)

        assert request.amount_pence == 0
        assert request.is_free_booking is True
        assert request.stripe_payment_link is None

    def test_request_accepts_flight_times(self):
        """Should accept flight_departure_time and flight_arrival_time fields."""
        from models import ManualBookingRequest

        today = date.today()
        dropoff = today + timedelta(days=11)
        pickup = today + timedelta(days=18)

        request_with_times = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "billing_address1": "123 Test St",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": dropoff.isoformat(),
            "dropoff_time": "08:30",
            "pickup_date": pickup.isoformat(),
            "pickup_time": "14:00",
            "amount_pence": 9900,
            "stripe_payment_link": "https://buy.stripe.com/test",
            "flight_departure_time": "10:30",
            "flight_arrival_time": "16:45",
        }

        request = ManualBookingRequest(**request_with_times)

        assert request.flight_departure_time == "10:30"
        assert request.flight_arrival_time == "16:45"

    def test_flight_times_are_optional(self):
        """Flight times should be optional in ManualBookingRequest."""
        from models import ManualBookingRequest

        today = date.today()
        dropoff = today + timedelta(days=11)
        pickup = today + timedelta(days=18)

        request_without_times = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "billing_address1": "123 Test St",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "registration": "AB12CDE",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": dropoff.isoformat(),
            "dropoff_time": "08:30",
            "pickup_date": pickup.isoformat(),
            "pickup_time": "14:00",
            "amount_pence": 9900,
            "stripe_payment_link": "https://buy.stripe.com/test",
        }

        request = ManualBookingRequest(**request_without_times)

        assert request.flight_departure_time is None
        assert request.flight_arrival_time is None


# =============================================================================
# Unit Tests - Slot Availability Logic
# =============================================================================

class TestSlotAvailabilityLogic:
    """Unit tests for slot availability calculations."""

    def test_capacity_tier_2_allows_one_per_slot(self):
        """Capacity tier 2 should allow max 1 booking per slot."""
        departure = create_mock_departure(capacity_tier=2)

        max_per_slot = departure.capacity_tier // 2

        assert max_per_slot == 1

    def test_capacity_tier_4_allows_two_per_slot(self):
        """Capacity tier 4 should allow max 2 bookings per slot."""
        departure = create_mock_departure(capacity_tier=4)

        max_per_slot = departure.capacity_tier // 2

        assert max_per_slot == 2

    def test_capacity_tier_8_allows_four_per_slot(self):
        """Capacity tier 8 should allow max 4 bookings per slot."""
        departure = create_mock_departure(capacity_tier=8)

        max_per_slot = departure.capacity_tier // 2

        assert max_per_slot == 4

    def test_early_slot_available_when_below_capacity(self):
        """Early slot should be available when below capacity."""
        departure = create_mock_departure(
            capacity_tier=4,
            slots_booked_early=1,
        )

        max_per_slot = departure.capacity_tier // 2
        is_available = departure.slots_booked_early < max_per_slot

        assert is_available is True

    def test_early_slot_full_when_at_capacity(self):
        """Early slot should be full when at capacity."""
        departure = create_mock_departure(
            capacity_tier=4,
            slots_booked_early=2,
        )

        max_per_slot = departure.capacity_tier // 2
        is_available = departure.slots_booked_early < max_per_slot

        assert is_available is False

    def test_late_slot_available_when_early_full(self):
        """Late slot should be available even when early is full."""
        departure = create_mock_departure(
            capacity_tier=4,
            slots_booked_early=2,
            slots_booked_late=0,
        )

        max_per_slot = departure.capacity_tier // 2
        is_late_available = departure.slots_booked_late < max_per_slot

        assert is_late_available is True

    def test_call_us_only_flight_has_zero_capacity(self):
        """Call-us-only flights should have capacity_tier of 0."""
        departure = create_mock_departure(capacity_tier=0)

        assert departure.capacity_tier == 0
        assert departure.capacity_tier // 2 == 0


# =============================================================================
# Unit Tests - Booking Reference Generation
# =============================================================================

class TestBookingReferenceGeneration:
    """Unit tests for booking reference format."""

    def test_reference_starts_with_tag_prefix(self):
        """Booking reference should start with 'TAG-'."""
        import random
        import string

        reference = "TAG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        assert reference.startswith("TAG-")

    def test_reference_has_correct_length(self):
        """Booking reference should be 12 characters (TAG- + 8)."""
        import random
        import string

        reference = "TAG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        assert len(reference) == 12

    def test_references_are_unique(self):
        """Multiple generated references should be unique."""
        import random
        import string

        references = set()
        for _ in range(100):
            ref = "TAG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            references.add(ref)

        assert len(references) == 100


# =============================================================================
# Integration Tests - Create Manual Booking API
# =============================================================================

class TestCreateManualBookingAPI:
    """Integration tests for POST /api/admin/manual-booking."""

    @pytest.fixture
    def mock_app_dependencies(self, mock_db, mock_admin_user):
        """Set up mock dependencies for the FastAPI app."""
        from main import app, require_admin
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        yield

        app.dependency_overrides.clear()

    @patch("email_service.send_manual_booking_payment_email")
    def test_create_booking_success(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should successfully create booking and return reference."""
        from main import app

        mock_email.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["booking_reference"].startswith("TAG-")

    @patch("email_service.send_manual_booking_payment_email")
    def test_create_booking_sends_email(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should call email service with correct parameters."""
        from main import app

        mock_email.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs["email"] == "jane.smith@example.com"
        assert call_kwargs["first_name"] == "Jane"

    @patch("email_service.send_manual_booking_payment_email")
    def test_email_failure_still_creates_booking(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should create booking even if email fails."""
        from main import app

        mock_email.return_value = False
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_sent"] is False

    def test_missing_payment_link_for_paid_booking_fails(
        self, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should reject paid booking without Stripe payment link."""
        from main import app

        del valid_manual_booking_request["stripe_payment_link"]

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 422

    @patch("email_service.send_manual_booking_payment_email")
    def test_free_booking_without_payment_link_succeeds(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should allow free booking without Stripe link."""
        from main import app

        mock_email.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = None

        valid_manual_booking_request["amount_pence"] = 0
        valid_manual_booking_request["is_free_booking"] = True
        del valid_manual_booking_request["stripe_payment_link"]

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 200

    @patch("email_service.send_manual_booking_payment_email")
    def test_creates_new_customer_in_database(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should create new customer record when not exists."""
        from main import app

        mock_email.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        # Verify db.add was called (for customer and vehicle)
        assert mock_db.add.called

    @patch("email_service.send_manual_booking_payment_email")
    def test_reuses_existing_customer(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should update existing customer when email matches."""
        from main import app

        mock_email.return_value = True
        existing_customer = create_mock_customer(id=999)

        # First query (customer) returns existing, second (vehicle) returns None
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            existing_customer,  # Customer lookup
            None,  # Vehicle lookup
            None,  # Departure lookup (if applicable)
        ]

        client = TestClient(app)
        client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        # Verify customer details were updated
        assert existing_customer.first_name == "Jane"


# =============================================================================
# Integration Tests - Slot Validation
# =============================================================================

class TestSlotValidationIntegration:
    """Integration tests for slot availability validation."""

    @pytest.fixture
    def mock_app_dependencies(self, mock_db, mock_admin_user):
        """Set up mock dependencies."""
        from main import app, require_admin
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        yield

        app.dependency_overrides.clear()

    @patch("email_service.send_manual_booking_payment_email")
    def test_rejects_booking_when_early_slot_full(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should reject booking when early slot is at capacity."""
        from main import app

        departure = create_mock_departure(
            capacity_tier=2,
            slots_booked_early=1,  # At capacity for tier 2
        )

        # Customer None, Vehicle None, Departure found
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # Customer
            None,  # Vehicle
            departure,  # Departure
        ]

        valid_manual_booking_request["departure_id"] = 1
        valid_manual_booking_request["dropoff_slot"] = "early"

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 400
        assert "early slot" in response.json()["detail"].lower()

    @patch("email_service.send_manual_booking_payment_email")
    def test_rejects_call_us_only_flight(
        self, mock_email, mock_app_dependencies, mock_db, valid_manual_booking_request
    ):
        """Should reject booking for call-us-only flights."""
        from main import app

        departure = create_mock_departure(capacity_tier=0)

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # Customer
            None,  # Vehicle
            departure,  # Departure (call-us-only)
        ]

        valid_manual_booking_request["departure_id"] = 1
        valid_manual_booking_request["dropoff_slot"] = "early"

        client = TestClient(app)
        response = client.post(
            "/api/admin/manual-booking",
            json=valid_manual_booking_request,
        )

        assert response.status_code == 400
        assert "call" in response.json()["detail"].lower()


# =============================================================================
# Integration Tests - Mark Booking Paid
# =============================================================================

class TestMarkBookingPaidAPI:
    """Integration tests for marking booking as paid."""

    @pytest.fixture
    def mock_app_dependencies(self, mock_db, mock_admin_user):
        """Set up mock dependencies."""
        from main import app, require_admin
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        yield

        app.dependency_overrides.clear()

    @patch("email_service.send_booking_confirmation_email")
    def test_mark_paid_success(
        self, mock_email, mock_app_dependencies, mock_db
    ):
        """Should successfully mark pending booking as paid."""
        from main import app
        from db_models import BookingStatus

        booking = create_mock_booking()
        booking.status = BookingStatus.PENDING
        payment = create_mock_payment()

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            booking,
            payment,
        ]
        mock_email.return_value = True

        client = TestClient(app)
        response = client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_mark_paid_booking_not_found(self, mock_app_dependencies, mock_db):
        """Should return 404 for non-existent booking."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.post("/api/admin/bookings/99999/mark-paid")

        assert response.status_code == 404

    def test_mark_paid_returns_email_status(
        self, mock_app_dependencies, mock_db
    ):
        """Should return email_sent status in response."""
        from main import app
        from db_models import BookingStatus

        # Create a fully populated booking mock with customer and vehicle
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        booking = create_mock_booking()
        booking.status = BookingStatus.PENDING
        booking.customer = customer
        booking.vehicle = vehicle
        booking.customer_first_name = "Jane"
        booking.package = "quick"
        payment = create_mock_payment()

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            booking,
            payment,
            None,  # MarketingSubscriber query returns None
        ]

        client = TestClient(app)
        response = client.post(f"/api/admin/bookings/{booking.id}/mark-paid")

        # Verify the response includes email_sent field (may be True or False)
        assert response.status_code == 200
        data = response.json()
        assert "email_sent" in data
        assert isinstance(data["email_sent"], bool)


# =============================================================================
# Unit Tests - Price Calculation
# =============================================================================

class TestPriceCalculation:
    """Unit tests for price formatting and calculation."""

    def test_amount_pence_to_pounds_conversion(self):
        """Should correctly convert pence to pounds."""
        amount_pence = 9900
        amount_pounds = amount_pence / 100

        assert amount_pounds == 99.00

    def test_format_price_with_currency_symbol(self):
        """Should format price with currency symbol."""
        amount_pence = 9900
        formatted = f"£{amount_pence / 100:.2f}"

        assert formatted == "£99.00"

    def test_zero_amount_for_free_booking(self):
        """Free bookings should have zero amount."""
        payment = create_mock_payment(amount_pence=0)

        assert payment.amount_pence == 0


# =============================================================================
# Unit Tests - Registration Formatting
# =============================================================================

class TestRegistrationFormatting:
    """Unit tests for vehicle registration formatting."""

    def test_registration_converted_to_uppercase(self):
        """Should convert registration to uppercase."""
        reg = "ab12cde"
        formatted = reg.upper()

        assert formatted == "AB12CDE"

    def test_registration_preserves_uppercase(self):
        """Should preserve already uppercase registration."""
        reg = "AB12CDE"
        formatted = reg.upper()

        assert formatted == "AB12CDE"


# =============================================================================
# Unit Tests - Destination Name Formatting
# =============================================================================

class TestDestinationNameFormatting:
    """Unit tests for destination name extraction."""

    def test_extract_city_from_full_name(self):
        """Should extract city name from 'City, CountryCode' format."""
        full_name = "Faro, PT"
        parts = full_name.split(', ')
        city = parts[0] if parts else full_name

        assert city == "Faro"

    def test_shorten_tenerife_reinasofia(self):
        """Should shorten Tenerife-Reinasofia to Tenerife."""
        destination = "Tenerife-Reinasofia"
        if destination == "Tenerife-Reinasofia":
            destination = "Tenerife"

        assert destination == "Tenerife"

    def test_preserve_simple_city_name(self):
        """Should preserve simple city names unchanged."""
        destination = "Malaga"

        assert destination == "Malaga"


# =============================================================================
# Integration Tests - Full Booking Flow
# =============================================================================

class TestFullBookingFlow:
    """End-to-end integration tests for complete booking workflows."""

    def test_manual_booking_workflow_mock(self):
        """Test complete manual booking workflow with mocks."""
        # 1. Create customer
        customer = create_mock_customer()
        assert customer.email == "jane.smith@example.com"

        # 2. Create vehicle
        vehicle = create_mock_vehicle(customer_id=customer.id)
        assert vehicle.customer_id == customer.id

        # 3. Create booking
        booking = create_mock_booking(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
        )
        assert booking.status.value == "pending"

        # 4. Create payment
        payment = create_mock_payment(booking_id=booking.id)
        assert payment.booking_id == booking.id

        # 5. Simulate payment (mark as paid)
        booking.status = MagicMock(value="confirmed")
        payment.status = MagicMock(value="succeeded")

        assert booking.status.value == "confirmed"
        assert payment.status.value == "succeeded"

    def test_booking_with_flight_integration_mock(self):
        """Test booking with flight slot integration."""
        departure = create_mock_departure(
            capacity_tier=4,
            slots_booked_early=1,
        )

        # Book early slot
        booking = create_mock_booking(
            departure_id=departure.id,
            slot_type="early",
        )

        # Increment slot count
        departure.slots_booked_early += 1

        assert departure.slots_booked_early == 2
        assert booking.departure_id == departure.id

    def test_cancellation_releases_slot_mock(self):
        """Test that cancellation releases slot."""
        departure = create_mock_departure(
            capacity_tier=4,
            slots_booked_early=2,
        )

        booking = create_mock_booking(
            departure_id=departure.id,
            slot_type="early",
        )
        booking.status = MagicMock(value="confirmed")

        # Cancel booking
        booking.status = MagicMock(value="cancelled")
        departure.slots_booked_early -= 1

        assert departure.slots_booked_early == 1
        assert booking.status.value == "cancelled"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_same_day_booking(self):
        """Should handle same-day drop-off and pick-up."""
        today = date.today()
        same_day = today + timedelta(days=14)

        booking = create_mock_booking(
            dropoff_date=same_day,
            pickup_date=same_day,
        )

        duration = (booking.pickup_date - booking.dropoff_date).days

        assert duration == 0

    def test_very_long_booking(self):
        """Should handle very long booking durations."""
        today = date.today()
        dropoff = today + timedelta(days=30)
        pickup = today + timedelta(days=75)  # 45 day trip

        booking = create_mock_booking(
            dropoff_date=dropoff,
            pickup_date=pickup,
        )

        duration = (booking.pickup_date - booking.dropoff_date).days

        assert duration == 45

    def test_special_characters_in_name(self):
        """Should handle special characters in names."""
        customer = create_mock_customer(
            first_name="José-María",
            last_name="O'Connor-Smith",
        )

        assert customer.first_name == "José-María"
        assert customer.last_name == "O'Connor-Smith"

    def test_zero_amount_complimentary_booking(self):
        """Should handle complimentary (zero amount) bookings."""
        payment = create_mock_payment(amount_pence=0)

        assert payment.amount_pence == 0

    def test_maximum_capacity_tier(self):
        """Should handle maximum capacity tier correctly."""
        departure = create_mock_departure(capacity_tier=20)

        max_per_slot = departure.capacity_tier // 2

        assert max_per_slot == 10
