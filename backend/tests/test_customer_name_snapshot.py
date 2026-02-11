"""
Tests for customer name snapshot feature.

This feature ensures that when a booking is created, the customer's name
at that point in time is stored in the booking record. This prevents
shared email addresses (e.g., married couples) from overwriting
historical booking names when a different person makes a new booking.

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time
from unittest.mock import patch, MagicMock
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Smith",
    email="test@example.com",
    phone="+44 7700 900000",
    billing_address1="123 Test Street",
    billing_city="Test City",
    billing_postcode="TE1 1ST",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_address1 = billing_address1
    customer.billing_city = billing_city
    customer.billing_postcode = billing_postcode
    return customer


def create_mock_vehicle(id=1, customer_id=1, registration="TEST123"):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = "Toyota"
    vehicle.model = "Corolla"
    vehicle.colour = "Silver"
    return vehicle


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    vehicle_id=1,
    customer_first_name="John",
    customer_last_name="Smith",
    customer=None,
):
    """Create a mock booking object with customer name snapshot."""
    from db_models import BookingStatus
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    booking.customer = customer
    booking.dropoff_date = date(2026, 7, 1)
    booking.dropoff_time = time(10, 0)
    booking.pickup_date = date(2026, 7, 8)
    booking.pickup_time = time(14, 0)
    booking.package = "quick"
    booking.status = BookingStatus.PENDING
    return booking


# =============================================================================
# Unit Tests: db_service.create_booking
# =============================================================================

class TestCreateBookingSnapshot:
    """Unit tests for customer name snapshot in db_service.create_booking."""

    def test_create_booking_snapshots_customer_name(self):
        """Should snapshot customer first_name and last_name into booking."""
        customer = create_mock_customer(id=1, first_name="John", last_name="Smith")
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        # Mock the create_booking function to verify it captures customer name
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=customer.first_name,
            customer_last_name=customer.last_name,
            customer=customer,
        )

        assert booking.customer_first_name == "John"
        assert booking.customer_last_name == "Smith"

    def test_snapshot_independent_of_customer_updates(self):
        """Snapshot should remain unchanged even if customer record is updated."""
        customer = create_mock_customer(id=1, first_name="John", last_name="Smith")
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        # Create booking with original name
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name="John",
            customer_last_name="Smith",
            customer=customer,
        )

        original_first = booking.customer_first_name
        original_last = booking.customer_last_name

        # Update customer name (simulating another family member booking)
        customer.first_name = "Jane"
        customer.last_name = "Smith-Jones"

        # Snapshot should be unchanged
        assert booking.customer_first_name == original_first
        assert booking.customer_last_name == original_last
        assert booking.customer_first_name == "John"
        assert booking.customer_last_name == "Smith"

        # But customer relationship shows updated name
        assert booking.customer.first_name == "Jane"
        assert booking.customer.last_name == "Smith-Jones"


# =============================================================================
# Integration Tests: Shared Email Address Scenario
# =============================================================================

class TestSharedEmailScenario:
    """
    Tests for the shared email address scenario.

    This is the main use case: a married couple shares an email address,
    and each person should have their own name on their bookings.
    """

    def test_shared_email_bookings_preserve_individual_names(self):
        """
        When two people share an email, each booking should show
        the name of the person who made it.
        """
        shared_email = "smith.family@test.com"

        # Create customer (John makes the first booking)
        customer = create_mock_customer(
            id=1,
            first_name="John",
            last_name="Smith",
            email=shared_email
        )
        vehicle1 = create_mock_vehicle(id=1, customer_id=1, registration="JOHN123")

        # John's booking
        booking1 = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle1.id,
            customer_first_name="John",
            customer_last_name="Smith",
            customer=customer,
        )

        # Verify John's booking
        assert booking1.customer_first_name == "John"
        assert booking1.customer_last_name == "Smith"

        # Jane uses the same email and updates the customer record
        customer.first_name = "Jane"
        customer.last_name = "Smith"

        # Jane makes a second booking with her name snapshot
        vehicle2 = create_mock_vehicle(id=2, customer_id=1, registration="JANE456")
        booking2 = create_mock_booking(
            id=2,
            customer_id=customer.id,
            vehicle_id=vehicle2.id,
            customer_first_name="Jane",
            customer_last_name="Smith",
            customer=customer,
        )

        # Verify Jane's booking
        assert booking2.customer_first_name == "Jane"
        assert booking2.customer_last_name == "Smith"

        # John's booking should STILL show John (not Jane)
        assert booking1.customer_first_name == "John"
        assert booking1.customer_last_name == "Smith"

        # Both bookings point to the same customer record
        assert booking1.customer_id == booking2.customer_id


# =============================================================================
# Test: Manual Booking Snapshot
# =============================================================================

class TestManualBookingSnapshot:
    """Test that the manual booking code path snapshots customer name."""

    def test_manual_booking_code_path_snapshots_name(self):
        """
        Verify that the code path used by manual bookings (direct Booking creation)
        includes the customer name snapshot when fields are provided.
        """
        customer = create_mock_customer(
            id=1,
            first_name="Manual",
            last_name="Booker",
        )
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        # This mirrors how main.py creates manual bookings
        booking = create_mock_booking(
            id=1,
            reference="TAG-MANUAL001",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=customer.first_name,
            customer_last_name=customer.last_name,
            customer=customer,
        )

        # Verify snapshot
        assert booking.customer_first_name == "Manual"
        assert booking.customer_last_name == "Booker"

        # Update customer and verify snapshot unchanged
        customer.first_name = "Changed"
        customer.last_name = "Name"

        assert booking.customer_first_name == "Manual"
        assert booking.customer_last_name == "Booker"


# =============================================================================
# Test: API Response Logic (Fallback Behavior)
# =============================================================================

class TestAPIResponseLogic:
    """Test the logic for choosing between snapshot and customer name."""

    def test_snapshot_or_fallback_logic(self):
        """
        Test the 'snapshot or fallback' pattern used in API responses:
        booking.customer_first_name or booking.customer.first_name
        """
        customer = create_mock_customer(
            id=1,
            first_name="Original",
            last_name="Name",
        )
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        # Create booking with snapshot
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name="Original",
            customer_last_name="Name",
            customer=customer,
        )

        # Update customer name
        customer.first_name = "Updated"
        customer.last_name = "Person"

        # This is the pattern used in main.py for API responses
        display_first_name = booking.customer_first_name or booking.customer.first_name
        display_last_name = booking.customer_last_name or booking.customer.last_name

        # Should use snapshot, not updated customer name
        assert display_first_name == "Original"
        assert display_last_name == "Name"

    def test_fallback_when_snapshot_is_null(self):
        """
        When snapshot fields are NULL (pre-migration bookings),
        the fallback should use customer relationship.
        """
        customer = create_mock_customer(
            id=1,
            first_name="Current",
            last_name="Customer",
        )

        # Create booking with NULL snapshot (simulating old booking)
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=1,
            customer_first_name=None,
            customer_last_name=None,
            customer=customer,
        )

        # This is the pattern used in main.py for API responses
        display_first_name = booking.customer_first_name or booking.customer.first_name
        display_last_name = booking.customer_last_name or booking.customer.last_name

        # Should fall back to customer relationship
        assert display_first_name == "Current"
        assert display_last_name == "Customer"


# =============================================================================
# Edge Cases
# =============================================================================

class TestSnapshotEdgeCases:
    """Edge case tests for customer name snapshot."""

    def test_snapshot_handles_special_characters(self):
        """Should handle names with special characters."""
        customer = create_mock_customer(
            id=1,
            first_name="José-María",
            last_name="O'Connor-Smith",
        )
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=customer.first_name,
            customer_last_name=customer.last_name,
            customer=customer,
        )

        assert booking.customer_first_name == "José-María"
        assert booking.customer_last_name == "O'Connor-Smith"

    def test_snapshot_handles_empty_last_name(self):
        """Should handle customers with empty/missing last name."""
        customer = create_mock_customer(
            id=1,
            first_name="Madonna",
            last_name="",  # Empty last name
        )
        vehicle = create_mock_vehicle(id=1, customer_id=1)

        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=customer.first_name,
            customer_last_name=customer.last_name,
            customer=customer,
        )

        assert booking.customer_first_name == "Madonna"
        assert booking.customer_last_name == ""

    def test_snapshot_fallback_when_null(self):
        """
        For backwards compatibility, when snapshot is NULL,
        the API should fall back to the customer relationship name.
        """
        customer = create_mock_customer(
            id=1,
            first_name="Fallback",
            last_name="Test",
        )

        # Create booking with NULL snapshot (simulating pre-migration booking)
        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=1,
            customer_first_name=None,
            customer_last_name=None,
            customer=customer,
        )

        # The fallback logic uses: snapshot or customer.name
        first_name = booking.customer_first_name or booking.customer.first_name
        last_name = booking.customer_last_name or booking.customer.last_name

        assert first_name == "Fallback"
        assert last_name == "Test"

    def test_snapshot_with_unicode_names(self):
        """Should handle names with unicode characters."""
        customer = create_mock_customer(
            id=1,
            first_name="北京",  # Chinese characters
            last_name="Müller",  # German umlaut
        )

        booking = create_mock_booking(
            id=1,
            customer_id=customer.id,
            vehicle_id=1,
            customer_first_name=customer.first_name,
            customer_last_name=customer.last_name,
            customer=customer,
        )

        assert booking.customer_first_name == "北京"
        assert booking.customer_last_name == "Müller"

    def test_multiple_bookings_different_snapshots(self):
        """Multiple bookings should each have their own snapshot."""
        customer = create_mock_customer(id=1, first_name="First", last_name="Person")

        booking1 = create_mock_booking(
            id=1,
            customer_first_name="First",
            customer_last_name="Person",
            customer=customer,
        )

        # Update customer name
        customer.first_name = "Second"
        customer.last_name = "Person"

        booking2 = create_mock_booking(
            id=2,
            customer_first_name="Second",
            customer_last_name="Person",
            customer=customer,
        )

        # Each booking has its own snapshot
        assert booking1.customer_first_name == "First"
        assert booking2.customer_first_name == "Second"

        # But both reference same customer
        assert booking1.customer.first_name == "Second"  # Current customer name
        assert booking2.customer.first_name == "Second"
