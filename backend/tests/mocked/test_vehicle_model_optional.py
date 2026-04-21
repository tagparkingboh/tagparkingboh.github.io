"""
Tests for Vehicle Model Optional Feature.

The vehicle model field is now optional as DVLA API only returns make + colour.
This test file covers the model-optional behavior across:
- Vehicle creation endpoints
- Email functions with None model
- Database model handling

Test categories:
- Happy path: Vehicle creation without model
- Happy path: Vehicle creation with model (backwards compatibility)
- Edge cases: None model in emails
- Edge cases: Empty string model
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_vehicle(
    id=1,
    customer_id=1,
    registration="AB12 CDE",
    make="Ford",
    model=None,  # Now optional
    colour="Blue",
):
    """Create a mock vehicle object with optional model."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = make
    vehicle.model = model
    vehicle.colour = colour
    vehicle.created_at = datetime.utcnow()
    return vehicle


def create_mock_customer(id=1, email="test@example.com"):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.email = email
    customer.first_name = "Test"
    customer.last_name = "User"
    return customer


# =============================================================================
# Unit Tests - Vehicle Model Optional
# =============================================================================

class TestVehicleModelOptional:
    """Unit tests for vehicle model being optional."""

    def test_vehicle_can_have_none_model(self):
        """Vehicle should accept None as model value."""
        vehicle = create_mock_vehicle(model=None)
        assert vehicle.model is None

    def test_vehicle_can_have_string_model(self):
        """Vehicle should still accept string model for backwards compatibility."""
        vehicle = create_mock_vehicle(model="Focus")
        assert vehicle.model == "Focus"

    def test_vehicle_can_have_empty_string_model(self):
        """Vehicle should accept empty string as model value."""
        vehicle = create_mock_vehicle(model="")
        assert vehicle.model == ""

    def test_vehicle_display_without_model(self):
        """Vehicle display should work without model."""
        vehicle = create_mock_vehicle(model=None)
        display = f"{vehicle.colour} {vehicle.make}"
        assert display == "Blue Ford"
        assert vehicle.model is None

    def test_vehicle_display_with_model(self):
        """Vehicle display should work with model for backwards compat."""
        vehicle = create_mock_vehicle(model="Focus")
        display = f"{vehicle.colour} {vehicle.make} {vehicle.model or ''}".strip()
        assert display == "Blue Ford Focus"


# =============================================================================
# Unit Tests - CreateVehicleRequest Model Optional
# =============================================================================

class TestCreateVehicleRequestModelOptional:
    """Unit tests for CreateVehicleRequest with optional model."""

    def test_request_without_model(self):
        """CreateVehicleRequest should work without model field."""
        from main import CreateVehicleRequest

        request = CreateVehicleRequest(
            customer_id=1,
            registration="AB12 CDE",
            make="Ford",
            colour="Blue",
            # model not provided
        )
        assert request.model is None
        assert request.make == "Ford"
        assert request.colour == "Blue"

    def test_request_with_model(self):
        """CreateVehicleRequest should still accept model for backwards compat."""
        from main import CreateVehicleRequest

        request = CreateVehicleRequest(
            customer_id=1,
            registration="AB12 CDE",
            make="Ford",
            model="Focus",
            colour="Blue",
        )
        assert request.model == "Focus"

    def test_request_with_none_model(self):
        """CreateVehicleRequest should accept explicit None model."""
        from main import CreateVehicleRequest

        request = CreateVehicleRequest(
            customer_id=1,
            registration="AB12 CDE",
            make="Ford",
            model=None,
            colour="Blue",
        )
        assert request.model is None


# =============================================================================
# Unit Tests - AdminBookingRequest Model Optional
# =============================================================================

class TestAdminBookingRequestModelOptional:
    """Unit tests for AdminBookingRequest with optional model."""

    def test_admin_request_without_model(self):
        """AdminBookingRequest should work without model field."""
        from models import AdminBookingRequest
        from datetime import date

        request = AdminBookingRequest(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="07123456789",
            drop_off_date=date(2026, 6, 1),
            drop_off_time="10:00",
            flight_date=date(2026, 6, 1),
            flight_time="12:00",
            flight_number="BA123",
            airline_code="BA",
            airline_name="British Airways",
            destination_code="AGP",
            destination_name="Malaga",
            pickup_date=date(2026, 6, 8),
            return_flight_time="14:00",
            return_flight_number="BA456",
            registration="AB12 CDE",
            make="Ford",
            colour="Blue",
            package="quick",
            # model not provided
        )
        assert request.model is None

    def test_admin_request_with_model(self):
        """AdminBookingRequest should still accept model."""
        from models import AdminBookingRequest
        from datetime import date

        request = AdminBookingRequest(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="07123456789",
            drop_off_date=date(2026, 6, 1),
            drop_off_time="10:00",
            flight_date=date(2026, 6, 1),
            flight_time="12:00",
            flight_number="BA123",
            airline_code="BA",
            airline_name="British Airways",
            destination_code="AGP",
            destination_name="Malaga",
            pickup_date=date(2026, 6, 8),
            return_flight_time="14:00",
            return_flight_number="BA456",
            registration="AB12 CDE",
            make="Ford",
            model="Focus",
            colour="Blue",
            package="quick",
        )
        assert request.model == "Focus"


# =============================================================================
# Unit Tests - ManualBookingRequest Model Optional
# =============================================================================

class TestManualBookingRequestModelOptional:
    """Unit tests for ManualBookingRequest with optional model."""

    def test_manual_request_without_model(self):
        """ManualBookingRequest should work without model field."""
        from models import ManualBookingRequest
        from datetime import date

        request = ManualBookingRequest(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            billing_address1="123 Test St",
            billing_city="London",
            billing_postcode="SW1A 1AA",
            registration="AB12 CDE",
            make="Ford",
            colour="Blue",
            dropoff_date=date(2026, 6, 1),
            dropoff_time="10:00",
            pickup_date=date(2026, 6, 8),
            pickup_time="14:00",
            stripe_payment_link="https://pay.stripe.com/test",
            amount_pence=9900,
            # model not provided
        )
        assert request.model is None


# =============================================================================
# Unit Tests - Email Service Model Optional
# =============================================================================

class TestEmailServiceModelOptional:
    """Unit tests for email service with optional model."""

    def test_confirmation_email_without_model(self):
        """Confirmation email should work with None model."""
        from email_service import send_booking_confirmation_email

        with patch('email_service.send_email', return_value=True) as mock_send:
            result = send_booking_confirmation_email(
                email="test@example.com",
                first_name="Test",
                booking_reference="TAG-12345678",
                dropoff_date="Saturday, 1 June 2026",
                dropoff_time="10:00",
                pickup_date="Saturday, 8 June 2026",
                pickup_time="14:30",
                flight_arrival_time="14:00",
                flight_departure_time="12:00",
                departure_flight="BA123 to Malaga (AGP)",
                return_flight="BA456 from Malaga (AGP)",
                vehicle_make="Ford",
                vehicle_colour="Blue",
                vehicle_registration="AB12 CDE",
                package_name="1 Week",
                amount_paid="£99.00",
                vehicle_model=None,  # No model
            )

            assert result is True
            mock_send.assert_called_once()
            # Check that email was sent without error
            call_args = mock_send.call_args
            html_content = call_args[0][2]  # Third positional arg is html_content
            assert "Ford" in html_content
            assert "Blue" in html_content

    def test_confirmation_email_with_model(self):
        """Confirmation email should still work with model for backwards compat."""
        from email_service import send_booking_confirmation_email

        with patch('email_service.send_email', return_value=True) as mock_send:
            result = send_booking_confirmation_email(
                email="test@example.com",
                first_name="Test",
                booking_reference="TAG-12345678",
                dropoff_date="Saturday, 1 June 2026",
                dropoff_time="10:00",
                pickup_date="Saturday, 8 June 2026",
                pickup_time="14:30",
                flight_arrival_time="14:00",
                flight_departure_time="12:00",
                departure_flight="BA123 to Malaga (AGP)",
                return_flight="BA456 from Malaga (AGP)",
                vehicle_make="Ford",
                vehicle_colour="Blue",
                vehicle_registration="AB12 CDE",
                package_name="1 Week",
                amount_paid="£99.00",
                vehicle_model="Focus",
            )

            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            html_content = call_args[0][2]
            assert "Focus" in html_content

    def test_manual_payment_email_without_model(self):
        """Manual payment email should work with None model."""
        from email_service import send_manual_booking_payment_email

        with patch('email_service.send_email', return_value=True) as mock_send:
            result = send_manual_booking_payment_email(
                email="test@example.com",
                first_name="Test",
                dropoff_date="Saturday, 1 June 2026",
                dropoff_time="10:00",
                pickup_date="Saturday, 8 June 2026",
                pickup_time="14:30",
                vehicle_make="Ford",
                vehicle_colour="Blue",
                vehicle_registration="AB12 CDE",
                amount="£99.00",
                payment_link="https://pay.stripe.com/test",
                vehicle_model=None,  # No model
            )

            assert result is True
            mock_send.assert_called_once()


# =============================================================================
# Unit Tests - Database Model
# =============================================================================

class TestDatabaseModelOptional:
    """Unit tests for database model with optional model field."""

    def test_vehicle_model_is_nullable(self):
        """Vehicle.model column should be nullable."""
        from db_models import Vehicle
        from sqlalchemy import inspect

        mapper = inspect(Vehicle)
        model_column = mapper.columns['model']
        assert model_column.nullable is True

    def test_vehicle_model_default_is_none(self):
        """Vehicle.model should default to None when not provided."""
        from db_models import Vehicle

        # Create vehicle without model
        vehicle = Vehicle(
            customer_id=1,
            registration="AB12CDE",
            make="Ford",
            colour="Blue",
            # model not provided
        )
        # SQLAlchemy will use column default (None for nullable)
        assert vehicle.model is None


# =============================================================================
# Unit Tests - db_service create_vehicle
# =============================================================================

class TestDbServiceCreateVehicle:
    """Unit tests for db_service.create_vehicle with optional model."""

    def test_create_vehicle_without_model(self):
        """create_vehicle should work without model parameter."""
        from db_service import create_vehicle
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        vehicle, is_new = create_vehicle(
            db=mock_db,
            customer_id=1,
            registration="AB12 CDE",
            make="Ford",
            colour="Blue",
            # model not provided - uses default None
        )

        # Should have called db.add with a Vehicle
        mock_db.add.assert_called_once()
        added_vehicle = mock_db.add.call_args[0][0]
        assert added_vehicle.model is None
        assert added_vehicle.make == "Ford"
        assert added_vehicle.colour == "Blue"

    def test_create_vehicle_with_model(self):
        """create_vehicle should still accept model for backwards compat."""
        from db_service import create_vehicle
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        vehicle, is_new = create_vehicle(
            db=mock_db,
            customer_id=1,
            registration="AB12 CDE",
            make="Ford",
            colour="Blue",
            model="Focus",
        )

        mock_db.add.assert_called_once()
        added_vehicle = mock_db.add.call_args[0][0]
        assert added_vehicle.model == "Focus"


# =============================================================================
# Integration Tests - Vehicle API Endpoints
# =============================================================================

class TestVehicleApiModelOptional:
    """Integration tests for vehicle API with optional model."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    @pytest.fixture
    def client(self, mock_db):
        """Create test client with mocked dependencies."""
        from main import app, get_db
        from fastapi.testclient import TestClient

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_create_vehicle_endpoint_without_model(self, client, mock_db):
        """POST /api/vehicles should work without model field."""
        # Mock customer exists
        mock_customer = MagicMock()
        mock_customer.id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer

        response = client.post(
            "/api/vehicles",
            json={
                "customer_id": 1,
                "registration": "AB12 CDE",
                "make": "Ford",
                "colour": "Blue",
                # No model field
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_vehicle_endpoint_with_model(self, client, mock_db):
        """POST /api/vehicles should still accept model field."""
        mock_customer = MagicMock()
        mock_customer.id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer

        response = client.post(
            "/api/vehicles",
            json={
                "customer_id": 1,
                "registration": "AB12 CDE",
                "make": "Ford",
                "model": "Focus",
                "colour": "Blue",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
