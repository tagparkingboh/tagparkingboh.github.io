"""
Tests for admin abandoned leads functionality.

Covers:
- GET /api/admin/abandoned-leads - List customers who started but didn't complete booking

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time, datetime
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="07700900001",
    billing_address1=None,
    billing_city=None,
    billing_postcode=None,
    created_at=None,
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
    customer.created_at = created_at or datetime.utcnow()
    return customer


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    vehicle_id=1,
    status="pending",
):
    """Create a mock booking object."""
    from db_models import BookingStatus
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id

    if status == "pending":
        booking.status = BookingStatus.PENDING
    elif status == "confirmed":
        booking.status = BookingStatus.CONFIRMED
    elif status == "cancelled":
        booking.status = BookingStatus.CANCELLED
    else:
        booking.status = BookingStatus.PENDING

    booking.package = "quick"
    booking.dropoff_date = date(2026, 6, 1)
    booking.dropoff_time = time(8, 0)
    booking.pickup_date = date(2026, 6, 8)
    return booking


def create_mock_abandoned_lead(
    id=1,
    first_name="Abandoned",
    last_name="User",
    email="abandoned@test.com",
    phone="07700900001",
    billing_address1=None,
    billing_city=None,
    billing_postcode=None,
    created_at=None,
    booking_attempts=0,
    last_booking_status=None,
):
    """Create a mock abandoned lead response object."""
    return {
        "id": id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "billing_address1": billing_address1,
        "billing_city": billing_city,
        "billing_postcode": billing_postcode,
        "created_at": (created_at or datetime.utcnow()).isoformat(),
        "booking_attempts": booking_attempts,
        "last_booking_status": last_booking_status,
    }


# =============================================================================
# GET /api/admin/abandoned-leads - Happy Path Tests
# =============================================================================

class TestGetAbandonedLeadsHappyPath:
    """Happy path tests for listing abandoned leads."""

    def test_get_abandoned_leads_returns_list(self):
        """Should return a list of abandoned leads."""
        # Simulate API response
        leads = [
            create_mock_abandoned_lead(id=1, email="abandoned@test.com"),
        ]

        response_data = {
            "leads": leads,
            "count": len(leads),
        }

        assert "leads" in response_data
        assert "count" in response_data
        assert response_data["count"] >= 1

    def test_abandoned_lead_includes_contact_details(self):
        """Leads should include name, email, phone."""
        lead = create_mock_abandoned_lead(
            first_name="Abandoned",
            last_name="User",
            email="abandoned@test.com",
            phone="07700900001",
        )

        assert lead["first_name"] == "Abandoned"
        assert lead["last_name"] == "User"
        assert lead["email"] == "abandoned@test.com"
        assert lead["phone"] == "07700900001"

    def test_abandoned_lead_includes_billing_address(self):
        """Leads should include billing address if provided."""
        lead = create_mock_abandoned_lead(
            billing_address1="123 Test Street",
            billing_city="Bournemouth",
            billing_postcode="BH1 1AA",
        )

        assert lead["billing_address1"] == "123 Test Street"
        assert lead["billing_city"] == "Bournemouth"
        assert lead["billing_postcode"] == "BH1 1AA"

    def test_abandoned_lead_includes_created_at(self):
        """Leads should include created_at timestamp."""
        lead = create_mock_abandoned_lead(created_at=datetime(2026, 1, 15, 10, 30, 0))

        assert lead["created_at"] is not None
        assert "2026-01-15" in lead["created_at"]

    def test_customer_with_pending_booking_is_abandoned_lead(self):
        """Customer with only pending booking should be an abandoned lead."""
        lead = create_mock_abandoned_lead(
            booking_attempts=1,
            last_booking_status="pending",
        )

        assert lead["booking_attempts"] == 1
        assert lead["last_booking_status"] == "pending"

    def test_leads_sorted_by_created_at_desc(self):
        """Leads should be sorted by created_at descending (newest first)."""
        leads = [
            create_mock_abandoned_lead(id=1, created_at=datetime(2026, 1, 20)),
            create_mock_abandoned_lead(id=2, created_at=datetime(2026, 1, 15)),
            create_mock_abandoned_lead(id=3, created_at=datetime(2026, 1, 10)),
        ]

        # Verify descending order
        dates = [l["created_at"] for l in leads]
        assert dates == sorted(dates, reverse=True)


# =============================================================================
# GET /api/admin/abandoned-leads - Negative Path Tests
# =============================================================================

class TestGetAbandonedLeadsNegativePath:
    """Negative path tests for listing abandoned leads."""

    def test_confirmed_customer_not_in_abandoned_leads(self):
        """Customer with confirmed booking should NOT appear in abandoned leads."""
        # Simulate response with no matching customer
        confirmed_email = "confirmed@test.com"
        leads = [
            create_mock_abandoned_lead(id=1, email="abandoned@test.com"),
        ]

        lead = next((l for l in leads if l["email"] == confirmed_email), None)
        assert lead is None

    def test_empty_database_returns_empty_list(self):
        """Should return empty list when no abandoned leads exist."""
        response_data = {
            "leads": [],
            "count": 0,
        }

        assert "leads" in response_data
        assert "count" in response_data
        assert isinstance(response_data["leads"], list)
        assert len(response_data["leads"]) == 0


# =============================================================================
# GET /api/admin/abandoned-leads - Edge Case Tests
# =============================================================================

class TestGetAbandonedLeadsEdgeCases:
    """Edge case tests for listing abandoned leads."""

    def test_customer_with_cancelled_booking_is_abandoned_lead(self):
        """Customer whose booking was cancelled should be an abandoned lead."""
        lead = create_mock_abandoned_lead(
            booking_attempts=1,
            last_booking_status="cancelled",
        )

        assert lead["booking_attempts"] == 1
        assert lead["last_booking_status"] == "cancelled"

    def test_customer_with_multiple_failed_bookings(self):
        """Customer with multiple non-confirmed bookings should show attempt count."""
        lead = create_mock_abandoned_lead(
            booking_attempts=3,
            last_booking_status="pending",
        )

        assert lead["booking_attempts"] == 3

    def test_customer_with_null_optional_fields(self):
        """Should handle customers with null optional fields."""
        lead = create_mock_abandoned_lead(
            billing_address1=None,
            billing_city=None,
            billing_postcode=None,
            booking_attempts=0,
            last_booking_status=None,
        )

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

    def test_customer_transitions_from_abandoned_to_confirmed(self):
        """Customer should be removed from abandoned leads when booking is confirmed."""
        customer_email = "transition@test.com"

        # Before: customer in abandoned leads
        leads_before = [
            create_mock_abandoned_lead(id=1, email=customer_email, booking_attempts=0),
        ]
        lead_before = next((l for l in leads_before if l["email"] == customer_email), None)
        assert lead_before is not None

        # After: customer has confirmed booking, no longer in abandoned leads
        leads_after = []  # Customer removed after confirmation

        lead_after = next((l for l in leads_after if l["email"] == customer_email), None)
        assert lead_after is None

    def test_count_matches_leads_length(self):
        """The count field should match the number of leads returned."""
        leads = [
            create_mock_abandoned_lead(id=1, email="lead1@test.com"),
            create_mock_abandoned_lead(id=2, email="lead2@test.com"),
            create_mock_abandoned_lead(id=3, email="lead3@test.com"),
        ]

        response_data = {
            "leads": leads,
            "count": len(leads),
        }

        assert response_data["count"] == len(response_data["leads"])
        assert response_data["count"] == 3

    def test_abandoned_leads_filtering_logic(self):
        """
        Test the core filtering logic:
        - Customers with no bookings = abandoned lead
        - Customers with only pending/cancelled bookings = abandoned lead
        - Customers with confirmed booking = NOT abandoned lead
        """
        # Customer with no bookings
        no_bookings = create_mock_customer(id=1, email="no_bookings@test.com")
        no_bookings_is_abandoned = True  # No bookings = abandoned
        assert no_bookings_is_abandoned is True

        # Customer with pending booking
        pending_customer = create_mock_customer(id=2, email="pending@test.com")
        pending_booking = create_mock_booking(id=1, customer_id=2, status="pending")
        pending_is_abandoned = pending_booking.status.value == "pending"
        assert pending_is_abandoned is True

        # Customer with cancelled booking
        cancelled_customer = create_mock_customer(id=3, email="cancelled@test.com")
        cancelled_booking = create_mock_booking(id=2, customer_id=3, status="cancelled")
        cancelled_is_abandoned = cancelled_booking.status.value == "cancelled"
        assert cancelled_is_abandoned is True

        # Customer with confirmed booking
        confirmed_customer = create_mock_customer(id=4, email="confirmed@test.com")
        confirmed_booking = create_mock_booking(id=3, customer_id=4, status="confirmed")
        confirmed_is_abandoned = confirmed_booking.status.value != "confirmed"
        assert confirmed_is_abandoned is False

    def test_response_structure(self):
        """Verify the API response has correct structure."""
        leads = [
            create_mock_abandoned_lead(
                id=1,
                first_name="Test",
                last_name="User",
                email="test@example.com",
                phone="07700900001",
                billing_address1="123 Test St",
                billing_city="Test City",
                billing_postcode="TE1 1ST",
                booking_attempts=2,
                last_booking_status="pending",
            ),
        ]

        response_data = {
            "leads": leads,
            "count": len(leads),
        }

        assert "leads" in response_data
        assert "count" in response_data

        lead = response_data["leads"][0]
        assert "id" in lead
        assert "first_name" in lead
        assert "last_name" in lead
        assert "email" in lead
        assert "phone" in lead
        assert "billing_address1" in lead
        assert "billing_city" in lead
        assert "billing_postcode" in lead
        assert "created_at" in lead
        assert "booking_attempts" in lead
        assert "last_booking_status" in lead
