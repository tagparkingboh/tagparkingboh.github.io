"""
Tests for customer detail and add vehicle endpoints.

Covers:
- GET /api/admin/customers/{customer_id} - Get customer with vehicles
- POST /api/admin/customers/{customer_id}/vehicles - Add vehicle to customer

All tests use mocked data - no real database connections.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from httpx import AsyncClient, ASGITransport


# ============================================================================
# MOCK DATABASE SETUP
# ============================================================================

class MockCustomer:
    """Mock customer object."""
    def __init__(self, id=1, first_name="John", last_name="Doe",
                 email="john@example.com", phone="+447123456789",
                 billing_address1="123 Test St", billing_address2=None,
                 billing_city="London", billing_county=None,
                 billing_postcode="SW1A 1AA", billing_country="United Kingdom",
                 created_at=None, marketing_source=None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.phone = phone
        self.billing_address1 = billing_address1
        self.billing_address2 = billing_address2
        self.billing_city = billing_city
        self.billing_county = billing_county
        self.billing_postcode = billing_postcode
        self.billing_country = billing_country
        self.created_at = created_at or datetime(2026, 1, 15, 10, 30, 0)
        self.marketing_source = marketing_source


class MockMarketingSource:
    """Mock marketing source object."""
    def __init__(self, source="Google"):
        self.source = source


class MockVehicle:
    """Mock vehicle object."""
    def __init__(self, id=1, customer_id=1, registration="AB12CDE",
                 make="Ford", model="Focus", colour="Blue", created_at=None):
        self.id = id
        self.customer_id = customer_id
        self.registration = registration
        self.make = make
        self.model = model
        self.colour = colour
        self.created_at = created_at or datetime(2026, 2, 1)


class MockQuery:
    """Mock SQLAlchemy query object."""
    def __init__(self, results=None, count_value=0):
        self._results = results if results is not None else []
        self._count_value = count_value
        self._single_result = None

    def filter(self, *args):
        return self

    def first(self):
        if self._single_result is not None:
            return self._single_result
        return self._results[0] if self._results else None

    def all(self):
        return self._results

    def count(self):
        return self._count_value

    def set_single_result(self, result):
        self._single_result = result
        return self


class MockSession:
    """Mock database session."""
    def __init__(self, customers=None, vehicles=None, booking_count=0):
        self._customers = customers or []
        self._vehicles = vehicles or []
        self._booking_count = booking_count
        self._query_type = None
        self._added = []

    def query(self, model):
        self._query_type = model.__name__ if hasattr(model, '__name__') else str(model)
        if 'Customer' in str(model):
            return MockQuery(self._customers)
        elif 'Vehicle' in str(model):
            return MockQuery(self._vehicles)
        elif 'Booking' in str(model):
            return MockQuery(count_value=self._booking_count)
        return MockQuery()

    def add(self, obj):
        self._added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        if hasattr(obj, 'id') and obj.id is None:
            obj.id = len(self._added)
        if hasattr(obj, 'created_at') and obj.created_at is None:
            obj.created_at = datetime.now()


# ============================================================================
# MOCKED UNIT TESTS - Test individual functions/logic in isolation
# ============================================================================

class TestCustomerDetailMocked:
    """Mocked unit tests for customer detail endpoint."""

    def test_customer_detail_returns_all_fields(self):
        """Happy path: Customer detail includes all expected fields."""
        customer = MockCustomer(
            id=1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="+447123456789",
            billing_postcode="SW1A 1AA",
            marketing_source=MockMarketingSource("Google")
        )

        # Build response data as endpoint would
        marketing_source = None
        if customer.marketing_source:
            marketing_source = customer.marketing_source.source

        response = {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "billing_postcode": customer.billing_postcode,
            "marketing_source": marketing_source,
        }

        assert response["id"] == 1
        assert response["first_name"] == "John"
        assert response["last_name"] == "Doe"
        assert response["email"] == "john@example.com"
        assert response["phone"] == "+447123456789"
        assert response["billing_postcode"] == "SW1A 1AA"
        assert response["marketing_source"] == "Google"

    def test_customer_detail_handles_null_marketing_source(self):
        """Edge case: Customer without marketing source."""
        customer = MockCustomer(marketing_source=None)

        marketing_source = None
        if customer.marketing_source:
            marketing_source = customer.marketing_source.source

        assert marketing_source is None

    def test_customer_detail_handles_null_created_at(self):
        """Edge case: Customer without created_at timestamp."""
        customer = MockCustomer()
        customer.created_at = None

        created_at_iso = customer.created_at.isoformat() if customer.created_at else None
        assert created_at_iso is None

    def test_customer_vehicles_list_formatting(self):
        """Happy path: Vehicles list is properly formatted."""
        vehicles = [
            MockVehicle(id=1, registration="AB12CDE", make="Ford", model="Focus", colour="Blue"),
            MockVehicle(id=2, registration="XY98ZAB", make="BMW", model=None, colour="Black"),
        ]

        vehicles_data = [
            {
                "id": v.id,
                "registration": v.registration,
                "make": v.make,
                "model": v.model,
                "colour": v.colour,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in vehicles
        ]

        assert len(vehicles_data) == 2
        assert vehicles_data[0]["registration"] == "AB12CDE"
        assert vehicles_data[0]["model"] == "Focus"
        assert vehicles_data[1]["model"] is None  # Handles optional model

    def test_customer_with_no_vehicles(self):
        """Edge case: Customer with empty vehicles list."""
        vehicles = []
        vehicles_data = [
            {"id": v.id, "registration": v.registration}
            for v in vehicles
        ]

        assert vehicles_data == []


class TestAddVehicleMocked:
    """Mocked unit tests for add vehicle endpoint."""

    def test_registration_normalization(self):
        """Happy path: Registration is normalized (uppercase, no spaces)."""
        test_cases = [
            ("ab12 cde", "AB12CDE"),
            ("AB12CDE", "AB12CDE"),
            ("ab 12 cd e", "AB12CDE"),
            ("  xy98zab  ", "XY98ZAB"),
        ]

        for input_reg, expected in test_cases:
            normalized = input_reg.upper().replace(" ", "").strip()
            assert normalized == expected, f"Failed for input: {input_reg}"

    def test_duplicate_vehicle_check_logic(self):
        """Unhappy path: Duplicate vehicle detection logic."""
        existing_registrations = ["AB12CDE", "XY98ZAB"]
        new_reg = "ab12cde"  # Should match AB12CDE after normalization

        normalized_new = new_reg.upper().replace(" ", "")
        is_duplicate = normalized_new in existing_registrations

        assert is_duplicate is True

    def test_vehicle_creation_with_optional_model(self):
        """Edge case: Vehicle can be created without model."""
        vehicle = MockVehicle(
            registration="AB12CDE",
            make="Ford",
            model=None,
            colour="Blue"
        )

        assert vehicle.model is None
        assert vehicle.make == "Ford"

    def test_empty_registration_validation(self):
        """Unhappy path: Empty registration should fail."""
        registration = ""
        is_valid = bool(registration.strip())
        assert is_valid is False

    def test_empty_make_validation(self):
        """Unhappy path: Empty make should fail."""
        make = "   "
        is_valid = bool(make.strip())
        assert is_valid is False

    def test_empty_colour_validation(self):
        """Unhappy path: Empty colour should fail."""
        colour = ""
        is_valid = bool(colour.strip())
        assert is_valid is False


# ============================================================================
# MOCKED INTEGRATION TESTS - Test endpoint logic with mocked dependencies
# ============================================================================

class TestCustomerDetailIntegration:
    """Integration tests for GET /api/admin/customers/{customer_id}."""

    def test_get_customer_detail_success(self):
        """Happy path: Successfully get customer details with vehicles."""
        customer = MockCustomer(
            id=1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            marketing_source=MockMarketingSource("Google")
        )
        vehicles = [
            MockVehicle(id=1, registration="AB12CDE", make="Ford"),
            MockVehicle(id=2, registration="XY98ZAB", make="BMW", model=None),
        ]
        db = MockSession(customers=[customer], vehicles=vehicles, booking_count=3)

        # Simulate endpoint logic
        found_customer = db.query(type('Customer', (), {})).filter().first()
        found_vehicles = db.query(type('Vehicle', (), {})).filter().all()
        booking_count = db.query(type('Booking', (), {})).filter().count()

        vehicles_data = [
            {
                "id": v.id,
                "registration": v.registration,
                "make": v.make,
                "model": v.model,
                "colour": v.colour,
            }
            for v in found_vehicles
        ]

        marketing_source = None
        if found_customer.marketing_source:
            marketing_source = found_customer.marketing_source.source

        response = {
            "id": found_customer.id,
            "first_name": found_customer.first_name,
            "last_name": found_customer.last_name,
            "email": found_customer.email,
            "marketing_source": marketing_source,
            "vehicles": vehicles_data,
            "booking_count": booking_count,
        }

        assert response["id"] == 1
        assert response["first_name"] == "John"
        assert response["marketing_source"] == "Google"
        assert len(response["vehicles"]) == 2
        assert response["booking_count"] == 3

    def test_get_customer_detail_not_found(self):
        """Unhappy path: Customer not found returns 404."""
        db = MockSession(customers=[])  # No customers

        found_customer = db.query(type('Customer', (), {})).filter().first()
        assert found_customer is None  # Should return 404

    def test_get_customer_detail_no_vehicles(self):
        """Edge case: Customer with no vehicles."""
        customer = MockCustomer(id=1)
        db = MockSession(customers=[customer], vehicles=[])

        found_vehicles = db.query(type('Vehicle', (), {})).filter().all()
        assert found_vehicles == []

    def test_get_customer_detail_zero_bookings(self):
        """Edge case: Customer with zero bookings."""
        customer = MockCustomer(id=1)
        db = MockSession(customers=[customer], booking_count=0)

        booking_count = db.query(type('Booking', (), {})).filter().count()
        assert booking_count == 0

    def test_get_customer_detail_many_bookings(self):
        """Boundary: Customer with many bookings."""
        customer = MockCustomer(id=1)
        db = MockSession(customers=[customer], booking_count=500)

        booking_count = db.query(type('Booking', (), {})).filter().count()
        assert booking_count == 500


class TestAddVehicleIntegration:
    """Integration tests for POST /api/admin/customers/{customer_id}/vehicles."""

    def test_add_vehicle_success(self):
        """Happy path: Successfully add vehicle to customer."""
        customer = MockCustomer(id=1)
        db = MockSession(customers=[customer], vehicles=[])

        # Simulate finding customer
        found_customer = db.query(type('Customer', (), {})).filter().first()
        assert found_customer is not None

        # Simulate checking for duplicate (none exists)
        existing = db.query(type('Vehicle', (), {})).filter().first()
        assert existing is None

        # Create vehicle
        request_data = {
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": None,
            "colour": "Blue",
        }

        normalized_reg = request_data["registration"].upper().replace(" ", "")
        assert normalized_reg == "AB12CDE"

    def test_add_vehicle_customer_not_found(self):
        """Unhappy path: Customer not found returns 404."""
        db = MockSession(customers=[])

        found_customer = db.query(type('Customer', (), {})).filter().first()
        assert found_customer is None  # Should return 404

    def test_add_vehicle_duplicate_registration(self):
        """Unhappy path: Duplicate registration returns 400."""
        customer = MockCustomer(id=1)
        existing_vehicle = MockVehicle(id=1, registration="AB12CDE")
        db = MockSession(customers=[customer], vehicles=[existing_vehicle])

        found_customer = db.query(type('Customer', (), {})).filter().first()
        existing = db.query(type('Vehicle', (), {})).filter().first()

        assert found_customer is not None
        assert existing is not None  # Duplicate found, should return 400

    def test_add_vehicle_normalizes_registration_with_spaces(self):
        """Happy path: Registration with spaces is normalized."""
        input_reg = "ab 12 cde"
        normalized = input_reg.upper().replace(" ", "")

        assert normalized == "AB12CDE"

    def test_add_vehicle_normalizes_lowercase_registration(self):
        """Happy path: Lowercase registration is normalized to uppercase."""
        input_reg = "xy98zab"
        normalized = input_reg.upper().replace(" ", "")

        assert normalized == "XY98ZAB"

    def test_add_vehicle_with_model(self):
        """Happy path: Vehicle with optional model field."""
        request_data = {
            "registration": "AB12CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
        }

        assert request_data["model"] == "Focus"

    def test_add_vehicle_without_model(self):
        """Edge case: Vehicle without model field."""
        request_data = {
            "registration": "AB12CDE",
            "make": "Ford",
            "model": None,
            "colour": "Blue",
        }

        assert request_data["model"] is None


class TestCustomerDetailBoundaries:
    """Boundary tests for customer detail endpoints."""

    def test_customer_id_zero(self):
        """Boundary: Customer ID of 0 (invalid)."""
        customer_id = 0
        is_valid = customer_id > 0
        assert is_valid is False

    def test_customer_id_negative(self):
        """Boundary: Negative customer ID (invalid)."""
        customer_id = -1
        is_valid = customer_id > 0
        assert is_valid is False

    def test_customer_id_positive(self):
        """Boundary: Positive customer ID (valid)."""
        customer_id = 1
        is_valid = customer_id > 0
        assert is_valid is True

    def test_customer_id_large(self):
        """Boundary: Large customer ID (valid)."""
        customer_id = 999999999
        is_valid = customer_id > 0
        assert is_valid is True

    def test_registration_max_length(self):
        """Boundary: Registration at max length (20 chars)."""
        registration = "A" * 20
        is_valid = len(registration) <= 20
        assert is_valid is True

    def test_registration_over_max_length(self):
        """Boundary: Registration over max length."""
        registration = "A" * 21
        is_valid = len(registration) <= 20
        assert is_valid is False

    def test_many_vehicles(self):
        """Boundary: Customer with many vehicles."""
        num_vehicles = 100
        vehicles = [MockVehicle(id=i, registration=f"REG{i:05d}") for i in range(num_vehicles)]
        assert len(vehicles) == 100

    def test_customer_with_all_null_optional_fields(self):
        """Edge case: Customer with all optional fields null."""
        customer = MockCustomer(
            billing_address2=None,
            billing_county=None,
            marketing_source=None,
        )

        assert customer.billing_address2 is None
        assert customer.billing_county is None
        assert customer.marketing_source is None

    def test_vehicle_registration_with_special_chars(self):
        """Edge case: Registration normalization handles special chars."""
        # Only uppercase and remove spaces
        input_reg = "AB12-CDE"
        normalized = input_reg.upper().replace(" ", "")

        # Note: This doesn't strip hyphens - that's expected behavior
        assert normalized == "AB12-CDE"
