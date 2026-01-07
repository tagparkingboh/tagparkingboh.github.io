"""
Tests for customer name snapshot feature.

This feature ensures that when a booking is created, the customer's name
at that point in time is stored in the booking record. This prevents
shared email addresses (e.g., married couples) from overwriting
historical booking names when a different person makes a new booking.

Test categories:
- Unit tests: Test db_service.create_booking snapshots customer name
- Integration tests: Full API flow verifying snapshot behavior
- Shared email scenario: Verify the original problem is fixed
"""
import pytest
import pytest_asyncio
from datetime import date, time
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, get_current_user, require_admin
from db_models import Booking, Customer, Vehicle, Payment, BookingStatus, PaymentStatus, User
from database import get_db
import db_service


# =============================================================================
# Auth Override Fixtures
# =============================================================================

@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing."""
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "admin@test.com"
    user.first_name = "Test"
    user.last_name = "Admin"
    user.is_admin = True
    user.is_active = True
    return user


@pytest_asyncio.fixture
async def authenticated_client(mock_admin_user):
    """Create an async test client with mocked admin authentication."""
    async def mock_get_current_user():
        return mock_admin_user

    async def mock_require_admin():
        return mock_admin_user

    # Override auth dependencies
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[require_admin] = mock_require_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


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
def unique_email():
    """Generate a unique email for testing."""
    unique_id = uuid.uuid4().hex[:8]
    return f"test.snapshot.{unique_id}@example.com"


@pytest.fixture
def create_test_customer(db_session):
    """Factory fixture to create test customers."""
    created_customers = []

    def _create(first_name, last_name, email):
        customer = Customer(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone="+44 7700 900000",
            billing_address1="123 Test Street",
            billing_city="Test City",
            billing_postcode="TE1 1ST",
        )
        db_session.add(customer)
        db_session.commit()
        db_session.refresh(customer)
        created_customers.append(customer)
        return customer

    yield _create

    # Cleanup
    for customer in created_customers:
        # Delete associated bookings first
        db_session.query(Booking).filter(Booking.customer_id == customer.id).delete()
        db_session.query(Vehicle).filter(Vehicle.customer_id == customer.id).delete()
        db_session.delete(customer)
    db_session.commit()


@pytest.fixture
def create_test_vehicle(db_session):
    """Factory fixture to create test vehicles."""
    created_vehicles = []

    def _create(customer_id, registration=None):
        if registration is None:
            registration = f"TEST{uuid.uuid4().hex[:4].upper()}"
        vehicle = Vehicle(
            customer_id=customer_id,
            registration=registration,
            make="Toyota",
            model="Corolla",
            colour="Silver",
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)
        created_vehicles.append(vehicle)
        return vehicle

    yield _create

    # Cleanup handled by customer fixture (cascade)


# =============================================================================
# Unit Tests: db_service.create_booking
# =============================================================================

class TestCreateBookingSnapshot:
    """Unit tests for customer name snapshot in db_service.create_booking."""

    def test_create_booking_snapshots_customer_name(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """Should snapshot customer first_name and last_name into booking."""
        customer = create_test_customer("John", "Smith", f"john.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        assert booking.customer_first_name == "John"
        assert booking.customer_last_name == "Smith"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()

    def test_snapshot_independent_of_customer_updates(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """Snapshot should remain unchanged even if customer record is updated."""
        customer = create_test_customer("John", "Smith", f"john.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        # Create booking with original name
        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        original_first = booking.customer_first_name
        original_last = booking.customer_last_name

        # Update customer name (simulating another family member booking)
        customer.first_name = "Jane"
        customer.last_name = "Smith-Jones"
        db_session.commit()

        # Refresh booking from database
        db_session.refresh(booking)

        # Snapshot should be unchanged
        assert booking.customer_first_name == original_first
        assert booking.customer_last_name == original_last
        assert booking.customer_first_name == "John"
        assert booking.customer_last_name == "Smith"

        # But customer relationship shows updated name
        assert booking.customer.first_name == "Jane"
        assert booking.customer.last_name == "Smith-Jones"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()


# =============================================================================
# Integration Tests: Shared Email Address Scenario
# =============================================================================

class TestSharedEmailScenario:
    """
    Integration tests for the shared email address scenario.

    This is the main use case: a married couple shares an email address,
    and each person should have their own name on their bookings.
    """

    def test_shared_email_bookings_preserve_individual_names(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """
        When two people share an email, each booking should show
        the name of the person who made it.
        """
        shared_email = f"smith.family.{uuid.uuid4().hex[:8]}@test.com"

        # John makes the first booking
        customer = create_test_customer("John", "Smith", shared_email)
        vehicle1 = create_test_vehicle(customer.id, f"JOHN{uuid.uuid4().hex[:4].upper()}")

        booking1 = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle1.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        # Verify John's booking
        assert booking1.customer_first_name == "John"
        assert booking1.customer_last_name == "Smith"

        # Jane uses the same email and updates the customer record
        customer.first_name = "Jane"
        customer.last_name = "Smith"
        db_session.commit()

        # Jane makes a second booking
        vehicle2 = create_test_vehicle(customer.id, f"JANE{uuid.uuid4().hex[:4].upper()}")

        booking2 = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle2.id,
            package="quick",
            dropoff_date=date(2026, 8, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 8, 8),
        )

        # Verify Jane's booking
        assert booking2.customer_first_name == "Jane"
        assert booking2.customer_last_name == "Smith"

        # John's booking should STILL show John (not Jane)
        db_session.refresh(booking1)
        assert booking1.customer_first_name == "John"
        assert booking1.customer_last_name == "Smith"

        # Both bookings point to the same customer record
        assert booking1.customer_id == booking2.customer_id

        # Cleanup
        db_session.delete(booking1)
        db_session.delete(booking2)
        db_session.commit()


# =============================================================================
# Integration Tests: Manual Booking via db_service (no API auth required)
# =============================================================================

class TestManualBookingSnapshot:
    """Test that the manual booking code path snapshots customer name."""

    def test_manual_booking_code_path_snapshots_name(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """
        Verify that the code path used by manual bookings (direct Booking creation)
        includes the customer name snapshot when fields are provided.
        """
        from db_models import Booking, BookingStatus
        from datetime import date, time

        customer = create_test_customer("Manual", "Booker", f"manual.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        # This mirrors how main.py creates manual bookings
        booking = Booking(
            reference=f"TAG-TEST{uuid.uuid4().hex[:4].upper()}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=customer.first_name,  # Snapshot at creation
            customer_last_name=customer.last_name,    # Snapshot at creation
            dropoff_date=date(2026, 7, 15),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 22),
            pickup_time=time(14, 0),
            package="quick",
            status=BookingStatus.PENDING,
            booking_source="manual",
        )
        db_session.add(booking)
        db_session.commit()

        # Verify snapshot
        assert booking.customer_first_name == "Manual"
        assert booking.customer_last_name == "Booker"

        # Update customer and verify snapshot unchanged
        customer.first_name = "Changed"
        customer.last_name = "Name"
        db_session.commit()
        db_session.refresh(booking)

        assert booking.customer_first_name == "Manual"
        assert booking.customer_last_name == "Booker"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()


# =============================================================================
# Test: API Response Logic (Fallback Behavior)
# =============================================================================

class TestAPIResponseLogic:
    """Test the logic for choosing between snapshot and customer name."""

    def test_snapshot_or_fallback_logic(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """
        Test the 'snapshot or fallback' pattern used in API responses:
        booking.customer_first_name or booking.customer.first_name
        """
        customer = create_test_customer("Original", "Name", f"original.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        # Create booking with snapshot
        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        # Update customer name
        customer.first_name = "Updated"
        customer.last_name = "Person"
        db_session.commit()
        db_session.refresh(booking)

        # This is the pattern used in main.py for API responses
        display_first_name = booking.customer_first_name or booking.customer.first_name
        display_last_name = booking.customer_last_name or booking.customer.last_name

        # Should use snapshot, not updated customer name
        assert display_first_name == "Original"
        assert display_last_name == "Name"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()

    def test_fallback_when_snapshot_is_null(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """
        When snapshot fields are NULL (pre-migration bookings),
        the fallback should use customer relationship.
        """
        customer = create_test_customer("Current", "Customer", f"current.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        # Create booking then set snapshot to NULL (simulating old booking)
        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )
        booking.customer_first_name = None
        booking.customer_last_name = None
        db_session.commit()
        db_session.refresh(booking)

        # This is the pattern used in main.py for API responses
        display_first_name = booking.customer_first_name or booking.customer.first_name
        display_last_name = booking.customer_last_name or booking.customer.last_name

        # Should fall back to customer relationship
        assert display_first_name == "Current"
        assert display_last_name == "Customer"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()


# =============================================================================
# Integration Tests: Admin API Endpoints (with mocked auth)
# =============================================================================

class TestAdminAPISnapshot:
    """Test admin API endpoints use snapshot name correctly."""

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_manual_booking_api_snapshots_name(
        self, mock_send_email, authenticated_client, db_session
    ):
        """POST /api/admin/manual-booking should snapshot customer name."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]

        request_data = {
            "first_name": "APITest",
            "last_name": "Booker",
            "email": f"apitest.{unique_id}@example.com",
            "phone": "+44 7700 900123",
            "billing_address1": "123 Test Street",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "billing_country": "United Kingdom",
            "registration": f"API{unique_id[:5].upper()}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": "2026-07-15",
            "dropoff_time": "10:00",
            "pickup_date": "2026-07-22",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test_abc123",
            "amount_pence": 9900,
        }

        response = await authenticated_client.post(
            "/api/admin/manual-booking",
            json=request_data
        )

        assert response.status_code == 200
        reference = response.json()["booking_reference"]

        # Verify snapshot in database
        booking = db_session.query(Booking).filter(
            Booking.reference == reference
        ).first()

        assert booking is not None
        assert booking.customer_first_name == "APITest"
        assert booking.customer_last_name == "Booker"

    @pytest.mark.asyncio
    @patch('email_service.send_manual_booking_payment_email')
    async def test_admin_bookings_list_returns_snapshot_name(
        self, mock_send_email, authenticated_client, db_session
    ):
        """GET /api/admin/bookings should return snapshot name, not current customer name."""
        mock_send_email.return_value = True
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"listtest.{unique_id}@example.com"

        # Create booking
        request_data = {
            "first_name": "OriginalFirst",
            "last_name": "OriginalLast",
            "email": test_email,
            "phone": "+44 7700 900123",
            "billing_address1": "123 Test Street",
            "billing_city": "Bournemouth",
            "billing_postcode": "BH1 1AA",
            "billing_country": "United Kingdom",
            "registration": f"LST{unique_id[:5].upper()}",
            "make": "Toyota",
            "model": "Corolla",
            "colour": "Silver",
            "dropoff_date": "2026-10-01",
            "dropoff_time": "10:00",
            "pickup_date": "2026-10-08",
            "pickup_time": "14:00",
            "stripe_payment_link": "https://buy.stripe.com/test_abc123",
            "amount_pence": 9900,
        }

        create_response = await authenticated_client.post(
            "/api/admin/manual-booking",
            json=request_data
        )
        assert create_response.status_code == 200
        reference = create_response.json()["booking_reference"]

        # Update customer name in database
        customer = db_session.query(Customer).filter(
            Customer.email == test_email
        ).first()
        customer.first_name = "UpdatedFirst"
        customer.last_name = "UpdatedLast"
        db_session.commit()

        # Fetch bookings via API
        bookings_response = await authenticated_client.get("/api/admin/bookings")
        assert bookings_response.status_code == 200

        bookings = bookings_response.json()["bookings"]
        our_booking = next(
            (b for b in bookings if b["reference"] == reference),
            None
        )

        assert our_booking is not None
        # Should show snapshot name, not updated customer name
        assert our_booking["customer"]["first_name"] == "OriginalFirst"
        assert our_booking["customer"]["last_name"] == "OriginalLast"


# =============================================================================
# Edge Cases
# =============================================================================

class TestSnapshotEdgeCases:
    """Edge case tests for customer name snapshot."""

    def test_snapshot_handles_special_characters(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """Should handle names with special characters."""
        customer = create_test_customer(
            "José-María",
            "O'Connor-Smith",
            f"jose.{uuid.uuid4().hex[:8]}@test.com"
        )
        vehicle = create_test_vehicle(customer.id)

        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        assert booking.customer_first_name == "José-María"
        assert booking.customer_last_name == "O'Connor-Smith"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()

    def test_snapshot_handles_empty_last_name(
        self, db_session, create_test_customer, create_test_vehicle
    ):
        """Should handle customers with empty/missing last name."""
        unique_id = uuid.uuid4().hex[:8]
        # Create customer directly with empty last name
        customer = Customer(
            first_name="Madonna",
            last_name="",  # Empty last name
            email=f"madonna.{unique_id}@test.com",
            phone="+44 7700 900000",
            billing_address1="123 Test Street",
            billing_city="Test City",
            billing_postcode="TE1 1ST",
        )
        db_session.add(customer)
        db_session.commit()

        vehicle = Vehicle(
            customer_id=customer.id,
            registration=f"MAD{unique_id[:4].upper()}",
            make="Toyota",
            model="Corolla",
            colour="Silver",
        )
        db_session.add(vehicle)
        db_session.commit()

        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        assert booking.customer_first_name == "Madonna"
        assert booking.customer_last_name == ""

        # Cleanup
        db_session.delete(booking)
        db_session.delete(vehicle)
        db_session.delete(customer)
        db_session.commit()

    def test_snapshot_fallback_when_null(self, db_session, create_test_customer, create_test_vehicle):
        """
        For backwards compatibility, when snapshot is NULL,
        the API should fall back to the customer relationship name.
        """
        customer = create_test_customer("Fallback", "Test", f"fallback.{uuid.uuid4().hex[:8]}@test.com")
        vehicle = create_test_vehicle(customer.id)

        # Create booking and manually set snapshot to NULL (simulating old booking)
        booking = db_service.create_booking(
            db=db_session,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            dropoff_date=date(2026, 7, 1),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 7, 8),
        )

        # Manually set snapshot to NULL (simulating pre-migration booking)
        booking.customer_first_name = None
        booking.customer_last_name = None
        db_session.commit()

        # The fallback logic uses: snapshot or customer.name
        # So when snapshot is None, it should use customer.first_name
        first_name = booking.customer_first_name or booking.customer.first_name
        last_name = booking.customer_last_name or booking.customer.last_name

        assert first_name == "Fallback"
        assert last_name == "Test"

        # Cleanup
        db_session.delete(booking)
        db_session.commit()
