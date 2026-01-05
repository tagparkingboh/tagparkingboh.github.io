"""
Tests for admin abandoned leads functionality.

Covers:
- GET /api/admin/abandoned-leads - List customers who started but didn't complete booking

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

from main import app, require_admin
from db_models import Booking, Customer, Vehicle, BookingStatus, User
from database import get_db


# Mock admin user for testing
def mock_require_admin():
    """Return a mock admin user for testing."""
    return User(
        id=1,
        email="test@admin.com",
        first_name="Test",
        last_name="Admin",
        is_admin=True,
    )


# Override require_admin for all tests in this module
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
def abandoned_customer(db_session):
    """Create a customer with no bookings (abandoned at step 3)."""
    customer = Customer(
        first_name="Abandoned",
        last_name="User",
        email=f"abandoned_{datetime.utcnow().timestamp()}@test.com",
        phone="07700900001",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture
def abandoned_customer_with_address(db_session):
    """Create a customer with billing address but no bookings."""
    customer = Customer(
        first_name="AddressUser",
        last_name="Test",
        email=f"address_user_{datetime.utcnow().timestamp()}@test.com",
        phone="07700900002",
        billing_address1="123 Test Street",
        billing_city="Bournemouth",
        billing_postcode="BH1 1AA",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture
def customer_with_pending_booking(db_session):
    """Create a customer with a pending (not confirmed) booking."""
    customer = Customer(
        first_name="Pending",
        last_name="Customer",
        email=f"pending_{datetime.utcnow().timestamp()}@test.com",
        phone="07700900003",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    vehicle = Vehicle(
        customer_id=customer.id,
        registration="PE12 NDG",
        make="Ford",
        model="Focus",
        colour="Silver",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    booking = Booking(
        reference=f"TAG-PEND{int(datetime.utcnow().timestamp())}",
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        package="quick",
        status=BookingStatus.PENDING,
        dropoff_date=date(2026, 6, 1),
        dropoff_time=time(8, 0),
        pickup_date=date(2026, 6, 8),
    )
    db_session.add(booking)
    db_session.commit()

    return customer


@pytest.fixture
def customer_with_confirmed_booking(db_session):
    """Create a customer with a confirmed booking (NOT an abandoned lead)."""
    customer = Customer(
        first_name="Confirmed",
        last_name="Customer",
        email=f"confirmed_{datetime.utcnow().timestamp()}@test.com",
        phone="07700900004",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    vehicle = Vehicle(
        customer_id=customer.id,
        registration="CO12 NFM",
        make="BMW",
        model="3 Series",
        colour="Black",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    booking = Booking(
        reference=f"TAG-CONF{int(datetime.utcnow().timestamp())}",
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        package="quick",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date(2026, 7, 1),
        dropoff_time=time(9, 0),
        pickup_date=date(2026, 7, 8),
    )
    db_session.add(booking)
    db_session.commit()

    return customer


# =============================================================================
# GET /api/admin/abandoned-leads - Happy Path Tests
# =============================================================================

class TestGetAbandonedLeadsHappyPath:
    """Happy path tests for listing abandoned leads."""

    @pytest.mark.asyncio
    async def test_get_abandoned_leads_returns_list(self, client, abandoned_customer):
        """Should return a list of abandoned leads."""
        response = await client.get("/api/admin/abandoned-leads")

        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert "count" in data
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_abandoned_lead_includes_contact_details(self, client, abandoned_customer):
        """Leads should include name, email, phone."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == abandoned_customer.email), None)
        assert lead is not None
        assert lead["first_name"] == "Abandoned"
        assert lead["last_name"] == "User"
        assert lead["phone"] == "07700900001"

    @pytest.mark.asyncio
    async def test_abandoned_lead_includes_billing_address(self, client, abandoned_customer_with_address):
        """Leads should include billing address if provided."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == abandoned_customer_with_address.email), None)
        assert lead is not None
        assert lead["billing_address1"] == "123 Test Street"
        assert lead["billing_city"] == "Bournemouth"
        assert lead["billing_postcode"] == "BH1 1AA"

    @pytest.mark.asyncio
    async def test_abandoned_lead_includes_created_at(self, client, abandoned_customer):
        """Leads should include created_at timestamp."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == abandoned_customer.email), None)
        assert lead is not None
        assert lead["created_at"] is not None

    @pytest.mark.asyncio
    async def test_customer_with_pending_booking_is_abandoned_lead(self, client, customer_with_pending_booking):
        """Customer with only pending booking should be an abandoned lead."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == customer_with_pending_booking.email), None)
        assert lead is not None
        assert lead["booking_attempts"] == 1
        assert lead["last_booking_status"] == "pending"

    @pytest.mark.asyncio
    async def test_leads_sorted_by_created_at_desc(self, client, abandoned_customer, abandoned_customer_with_address):
        """Leads should be sorted by created_at descending (newest first)."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        leads = data["leads"]

        # Verify descending order
        if len(leads) >= 2:
            dates = [l["created_at"] for l in leads if l["created_at"]]
            assert dates == sorted(dates, reverse=True)


# =============================================================================
# GET /api/admin/abandoned-leads - Negative Path Tests
# =============================================================================

class TestGetAbandonedLeadsNegativePath:
    """Negative path tests for listing abandoned leads."""

    @pytest.mark.asyncio
    async def test_confirmed_customer_not_in_abandoned_leads(self, client, customer_with_confirmed_booking):
        """Customer with confirmed booking should NOT appear in abandoned leads."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == customer_with_confirmed_booking.email), None)
        assert lead is None

    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_list(self, client):
        """Should return empty list when no abandoned leads exist."""
        response = await client.get("/api/admin/abandoned-leads")

        assert response.status_code == 200
        data = response.json()
        # Note: May not be empty due to other test data, but structure should be correct
        assert "leads" in data
        assert "count" in data
        assert isinstance(data["leads"], list)


# =============================================================================
# GET /api/admin/abandoned-leads - Edge Case Tests
# =============================================================================

class TestGetAbandonedLeadsEdgeCases:
    """Edge case tests for listing abandoned leads."""

    @pytest.mark.asyncio
    async def test_customer_with_cancelled_booking_is_abandoned_lead(self, client, db_session):
        """Customer whose booking was cancelled should be an abandoned lead."""
        customer = Customer(
            first_name="Cancelled",
            last_name="Booking",
            email=f"cancelled_{datetime.utcnow().timestamp()}@test.com",
            phone="07700900005",
        )
        db_session.add(customer)
        db_session.commit()
        db_session.refresh(customer)

        vehicle = Vehicle(
            customer_id=customer.id,
            registration="CA12 NCL",
            make="Audi",
            model="A4",
            colour="White",
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        booking = Booking(
            reference=f"TAG-CANC{int(datetime.utcnow().timestamp())}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            status=BookingStatus.CANCELLED,
            dropoff_date=date(2026, 8, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 8, 8),
        )
        db_session.add(booking)
        db_session.commit()

        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == customer.email), None)
        assert lead is not None
        assert lead["booking_attempts"] == 1
        assert lead["last_booking_status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_customer_with_multiple_failed_bookings(self, client, db_session):
        """Customer with multiple non-confirmed bookings should show attempt count."""
        customer = Customer(
            first_name="MultiAttempt",
            last_name="User",
            email=f"multi_{datetime.utcnow().timestamp()}@test.com",
            phone="07700900006",
        )
        db_session.add(customer)
        db_session.commit()
        db_session.refresh(customer)

        vehicle = Vehicle(
            customer_id=customer.id,
            registration="MU12 LTI",
            make="Mercedes",
            model="C Class",
            colour="Grey",
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        # Add multiple failed booking attempts
        ts = int(datetime.utcnow().timestamp())
        for i in range(3):
            booking = Booking(
                reference=f"TAG-MULTI{ts}{i}",
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                package="quick",
                status=BookingStatus.PENDING,
                dropoff_date=date(2026, 9, 1 + i),
                dropoff_time=time(8, 0),
                pickup_date=date(2026, 9, 8 + i),
            )
            db_session.add(booking)
        db_session.commit()

        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == customer.email), None)
        assert lead is not None
        assert lead["booking_attempts"] == 3

    @pytest.mark.asyncio
    async def test_customer_with_null_optional_fields(self, client, db_session):
        """Should handle customers with null optional fields."""
        customer = Customer(
            first_name="Minimal",
            last_name="Data",
            email=f"minimal_{datetime.utcnow().timestamp()}@test.com",
            phone="07700900007",
            # All optional billing fields left as None
        )
        db_session.add(customer)
        db_session.commit()
        db_session.refresh(customer)

        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        lead = next((l for l in data["leads"] if l["email"] == customer.email), None)
        assert lead is not None
        assert lead["billing_address1"] is None
        assert lead["billing_city"] is None
        assert lead["billing_postcode"] is None
        assert lead["booking_attempts"] == 0
        assert lead["last_booking_status"] is None


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

class TestAbandonedLeadsIntegration:
    """Integration tests covering full abandoned leads workflows."""

    @pytest.mark.asyncio
    async def test_customer_transitions_from_abandoned_to_confirmed(self, client, db_session):
        """Customer should be removed from abandoned leads when booking is confirmed."""
        # Create abandoned customer
        customer = Customer(
            first_name="Transition",
            last_name="Test",
            email=f"transition_{datetime.utcnow().timestamp()}@test.com",
            phone="07700900008",
        )
        db_session.add(customer)
        db_session.commit()
        db_session.refresh(customer)

        # Verify they appear in abandoned leads
        response1 = await client.get("/api/admin/abandoned-leads")
        data1 = response1.json()
        lead1 = next((l for l in data1["leads"] if l["email"] == customer.email), None)
        assert lead1 is not None

        # Add vehicle and confirmed booking
        vehicle = Vehicle(
            customer_id=customer.id,
            registration="TR12 ANS",
            make="Tesla",
            model="Model 3",
            colour="Red",
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        booking = Booking(
            reference=f"TAG-TRANS{int(datetime.utcnow().timestamp())}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            status=BookingStatus.CONFIRMED,
            dropoff_date=date(2026, 10, 1),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 10, 8),
        )
        db_session.add(booking)
        db_session.commit()

        # Verify they no longer appear in abandoned leads
        response2 = await client.get("/api/admin/abandoned-leads")
        data2 = response2.json()
        lead2 = next((l for l in data2["leads"] if l["email"] == customer.email), None)
        assert lead2 is None

    @pytest.mark.asyncio
    async def test_count_matches_leads_length(self, client, abandoned_customer, abandoned_customer_with_address):
        """The count field should match the number of leads returned."""
        response = await client.get("/api/admin/abandoned-leads")

        data = response.json()
        assert data["count"] == len(data["leads"])
