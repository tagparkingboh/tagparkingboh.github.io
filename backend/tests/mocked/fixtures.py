"""
Shared test fixtures and factory helpers for mocked tests.

Usage:
    from tests.mocked.fixtures import (
        admin_client, mock_db, mock_booking, mock_customer, mock_user,
        MockQueryChain
    )
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, date, time
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
import pytz

uk_tz = pytz.timezone('Europe/London')


# =============================================================================
# FACTORY HELPERS
# =============================================================================

def mock_user(
    id: int = 1,
    email: str = "admin@test.com",
    role: str = "admin",
    is_active: bool = True,
    **overrides
):
    """Create a mock user object."""
    user = MagicMock()
    user.id = overrides.get('id', id)
    user.email = overrides.get('email', email)
    user.role = overrides.get('role', role)
    user.is_active = overrides.get('is_active', is_active)
    user.is_admin = role == "admin"
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def mock_customer(
    id: int = 1,
    first_name: str = "John",
    last_name: str = "Doe",
    email: str = "john@test.com",
    phone: str = "07700900123",
    billing_postcode: str = "M1 1AA",
    billing_city: str = "Manchester",
    billing_address1: str = "123 Test Street",
    billing_updated_at: datetime = None,
    created_at: datetime = None,
    bookings: list = None,
    vehicles: list = None,
    **overrides
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = overrides.get('id', id)
    customer.first_name = overrides.get('first_name', first_name)
    customer.last_name = overrides.get('last_name', last_name)
    customer.email = overrides.get('email', email)
    customer.phone = overrides.get('phone', phone)
    customer.billing_postcode = overrides.get('billing_postcode', billing_postcode)
    customer.billing_city = overrides.get('billing_city', billing_city)
    customer.billing_address1 = overrides.get('billing_address1', billing_address1)
    customer.billing_updated_at = overrides.get('billing_updated_at', billing_updated_at or datetime.now(uk_tz))
    customer.created_at = overrides.get('created_at', created_at or datetime.now(uk_tz))
    customer.bookings = overrides.get('bookings', bookings or [])
    customer.vehicles = overrides.get('vehicles', vehicles or [])
    for key, value in overrides.items():
        setattr(customer, key, value)
    return customer


def mock_booking(
    id: str = "BK001",
    customer_id: int = 1,
    status: str = "confirmed",
    drop_off_date: date = None,
    drop_off_time: time = None,
    pick_up_date: date = None,
    pick_up_time: time = None,
    departure_flight_number: str = "FR1234",
    departure_destination: str = "Malaga",
    departure_airline_code: str = "FR",
    arrival_flight_number: str = "FR1235",
    total_price: Decimal = Decimal("75.00"),
    created_at: datetime = None,
    customer: MagicMock = None,
    vehicle: MagicMock = None,
    **overrides
):
    """Create a mock booking object."""
    booking = MagicMock()
    booking.id = overrides.get('id', id)
    booking.customer_id = overrides.get('customer_id', customer_id)

    # Status as enum-like object
    status_val = overrides.get('status', status)
    booking.status = MagicMock()
    booking.status.value = status_val
    booking.status.__str__ = lambda self: status_val

    booking.drop_off_date = overrides.get('drop_off_date', drop_off_date or date(2026, 5, 1))
    booking.drop_off_time = overrides.get('drop_off_time', drop_off_time or time(8, 0))
    booking.pick_up_date = overrides.get('pick_up_date', pick_up_date or date(2026, 5, 8))
    booking.pick_up_time = overrides.get('pick_up_time', pick_up_time or time(15, 0))
    booking.departure_flight_number = overrides.get('departure_flight_number', departure_flight_number)
    booking.departure_destination = overrides.get('departure_destination', departure_destination)
    booking.departure_airline_code = overrides.get('departure_airline_code', departure_airline_code)
    booking.arrival_flight_number = overrides.get('arrival_flight_number', arrival_flight_number)
    booking.total_price = overrides.get('total_price', total_price)
    booking.created_at = overrides.get('created_at', created_at or datetime.now(uk_tz))
    booking.customer = overrides.get('customer', customer)
    booking.vehicle = overrides.get('vehicle', vehicle)

    for key, value in overrides.items():
        setattr(booking, key, value)
    return booking


def mock_vehicle(
    id: int = 1,
    registration: str = "AB12CDE",
    make: str = "Ford",
    model: str = "Focus",
    colour: str = "Blue",
    customer_id: int = 1,
    **overrides
):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = overrides.get('id', id)
    vehicle.registration = overrides.get('registration', registration)
    vehicle.make = overrides.get('make', make)
    vehicle.model = overrides.get('model', model)
    vehicle.colour = overrides.get('colour', colour)
    vehicle.customer_id = overrides.get('customer_id', customer_id)
    for key, value in overrides.items():
        setattr(vehicle, key, value)
    return vehicle


# =============================================================================
# QUERY CHAIN MOCK
# =============================================================================

class MockQueryChain:
    """
    Fluent mock for SQLAlchemy query chains.

    Usage:
        chain = MockQueryChain(return_value=[mock_booking()])
        mock_db.query.return_value = chain

        # Now db.query(Booking).filter(...).order_by(...).all() returns [mock_booking()]
    """

    def __init__(self, return_value=None, return_one=None, return_first=None, return_scalar=None):
        self._return_value = return_value if return_value is not None else []
        self._return_one = return_one
        self._return_first = return_first
        self._return_scalar = return_scalar

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def distinct(self, *args, **kwargs):
        return self

    def subquery(self):
        return MagicMock()

    def all(self):
        return self._return_value

    def first(self):
        if self._return_first is not None:
            return self._return_first
        return self._return_value[0] if self._return_value else None

    def one(self):
        if self._return_one is not None:
            return self._return_one
        return self._return_value[0] if self._return_value else None

    def one_or_none(self):
        return self.first()

    def scalar(self):
        if self._return_scalar is not None:
            return self._return_scalar
        return len(self._return_value)

    def count(self):
        return len(self._return_value)

    def delete(self):
        return len(self._return_value)

    def update(self, *args, **kwargs):
        return len(self._return_value)


# =============================================================================
# PYTEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query = MagicMock(return_value=MockQueryChain())
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return mock_user(role="admin")


@pytest.fixture
def mock_employee():
    """Create a mock employee user."""
    return mock_user(id=2, email="employee@test.com", role="employee")
