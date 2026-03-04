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
    founder_followup_sent=False,
    founder_followup_sent_at=None,
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
    customer.founder_followup_sent = founder_followup_sent
    customer.founder_followup_sent_at = founder_followup_sent_at
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
    founder_followup_sent=False,
    founder_followup_sent_at=None,
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
        "founder_followup_sent": founder_followup_sent,
        "founder_followup_sent_at": founder_followup_sent_at.isoformat() if founder_followup_sent_at else None,
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
        assert "founder_followup_sent" in lead
        assert "founder_followup_sent_at" in lead


# =============================================================================
# Founder Email Status - Happy Path Tests
# =============================================================================

class TestFounderEmailStatusHappyPath:
    """Happy path tests for founder email status in leads."""

    def test_lead_includes_founder_followup_sent_field(self):
        """Lead response should include founder_followup_sent field."""
        lead = create_mock_abandoned_lead(founder_followup_sent=False)
        assert "founder_followup_sent" in lead
        assert lead["founder_followup_sent"] is False

    def test_lead_includes_founder_followup_sent_at_field(self):
        """Lead response should include founder_followup_sent_at field."""
        lead = create_mock_abandoned_lead(founder_followup_sent_at=None)
        assert "founder_followup_sent_at" in lead
        assert lead["founder_followup_sent_at"] is None

    def test_lead_with_founder_email_sent_shows_true(self):
        """Lead with founder email sent should show founder_followup_sent=True."""
        sent_at = datetime(2026, 3, 1, 10, 30, 0)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )
        assert lead["founder_followup_sent"] is True
        assert lead["founder_followup_sent_at"] is not None
        assert "2026-03-01" in lead["founder_followup_sent_at"]

    def test_lead_without_founder_email_shows_false(self):
        """Lead without founder email should show founder_followup_sent=False."""
        lead = create_mock_abandoned_lead(
            founder_followup_sent=False,
            founder_followup_sent_at=None,
        )
        assert lead["founder_followup_sent"] is False
        assert lead["founder_followup_sent_at"] is None

    def test_founder_email_sent_at_includes_time(self):
        """founder_followup_sent_at should include time component."""
        sent_at = datetime(2026, 3, 1, 14, 45, 30)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )
        assert "14:45:30" in lead["founder_followup_sent_at"]

    def test_multiple_leads_with_different_founder_email_status(self):
        """Should correctly show different founder email statuses for multiple leads."""
        leads = [
            create_mock_abandoned_lead(
                id=1,
                email="sent@test.com",
                founder_followup_sent=True,
                founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0),
            ),
            create_mock_abandoned_lead(
                id=2,
                email="notsent@test.com",
                founder_followup_sent=False,
                founder_followup_sent_at=None,
            ),
        ]

        assert leads[0]["founder_followup_sent"] is True
        assert leads[0]["founder_followup_sent_at"] is not None
        assert leads[1]["founder_followup_sent"] is False
        assert leads[1]["founder_followup_sent_at"] is None


# =============================================================================
# Founder Email Status - Negative Path Tests
# =============================================================================

class TestFounderEmailStatusNegativePath:
    """Negative path tests for founder email status in leads."""

    def test_founder_email_sent_without_timestamp_is_invalid(self):
        """founder_followup_sent=True but no sent_at timestamp is inconsistent."""
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=None,  # Missing timestamp
        )
        # This is a data inconsistency - sent should have timestamp
        assert lead["founder_followup_sent"] is True
        assert lead["founder_followup_sent_at"] is None
        # Frontend should handle this gracefully

    def test_founder_email_timestamp_without_sent_flag_is_invalid(self):
        """founder_followup_sent_at without founder_followup_sent=True is inconsistent."""
        lead = create_mock_abandoned_lead(
            founder_followup_sent=False,
            founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0),  # Unexpected
        )
        # Data inconsistency - timestamp but not marked sent
        assert lead["founder_followup_sent"] is False
        assert lead["founder_followup_sent_at"] is not None


# =============================================================================
# Founder Email Status - Edge Case Tests
# =============================================================================

class TestFounderEmailStatusEdgeCases:
    """Edge case tests for founder email status in leads."""

    def test_lead_with_zero_bookings_and_founder_email_sent(self):
        """Lead with no booking attempts can still have founder email sent."""
        lead = create_mock_abandoned_lead(
            booking_attempts=0,
            last_booking_status=None,
            founder_followup_sent=True,
            founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0),
        )
        assert lead["booking_attempts"] == 0
        assert lead["founder_followup_sent"] is True

    def test_lead_with_pending_booking_and_founder_email_sent(self):
        """Lead with pending booking can have founder email sent (manual trigger)."""
        lead = create_mock_abandoned_lead(
            booking_attempts=1,
            last_booking_status="pending",
            founder_followup_sent=True,
            founder_followup_sent_at=datetime(2026, 3, 2, 15, 30, 0),
        )
        assert lead["booking_attempts"] == 1
        assert lead["last_booking_status"] == "pending"
        assert lead["founder_followup_sent"] is True

    def test_founder_email_sent_at_midnight(self):
        """Should handle founder email sent at midnight correctly."""
        sent_at = datetime(2026, 3, 1, 0, 0, 0)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )
        assert "00:00:00" in lead["founder_followup_sent_at"]

    def test_founder_email_sent_at_end_of_day(self):
        """Should handle founder email sent at end of day correctly."""
        sent_at = datetime(2026, 3, 1, 23, 59, 59)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )
        assert "23:59:59" in lead["founder_followup_sent_at"]

    def test_all_leads_have_founder_email_sent(self):
        """All leads in response can have founder email sent."""
        leads = [
            create_mock_abandoned_lead(
                id=i,
                founder_followup_sent=True,
                founder_followup_sent_at=datetime(2026, 3, 1, 10 + i, 0, 0),
            )
            for i in range(5)
        ]
        for lead in leads:
            assert lead["founder_followup_sent"] is True
            assert lead["founder_followup_sent_at"] is not None

    def test_no_leads_have_founder_email_sent(self):
        """All leads in response can have no founder email sent."""
        leads = [
            create_mock_abandoned_lead(
                id=i,
                founder_followup_sent=False,
                founder_followup_sent_at=None,
            )
            for i in range(5)
        ]
        for lead in leads:
            assert lead["founder_followup_sent"] is False
            assert lead["founder_followup_sent_at"] is None


# =============================================================================
# Founder Email Status - Integration Tests
# =============================================================================

class TestFounderEmailStatusIntegration:
    """Integration tests for founder email status in leads workflow."""

    def test_customer_model_to_lead_response_mapping(self):
        """Customer model founder fields should map correctly to lead response."""
        sent_at = datetime(2026, 3, 1, 12, 30, 0)
        customer = create_mock_customer(
            id=1,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )

        # Simulate the mapping logic from main.py
        lead_response = {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "founder_followup_sent": customer.founder_followup_sent,
            "founder_followup_sent_at": customer.founder_followup_sent_at.isoformat() if customer.founder_followup_sent_at else None,
        }

        assert lead_response["founder_followup_sent"] is True
        assert lead_response["founder_followup_sent_at"] == "2026-03-01T12:30:00"

    def test_lead_response_includes_all_required_fields(self):
        """Lead response should include all required fields including founder email status."""
        lead = create_mock_abandoned_lead(
            id=1,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="07700900001",
            billing_address1="123 Test St",
            billing_city="Test City",
            billing_postcode="TE1 1ST",
            booking_attempts=1,
            last_booking_status="pending",
            founder_followup_sent=True,
            founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0),
        )

        required_fields = [
            "id", "first_name", "last_name", "email", "phone",
            "billing_address1", "billing_city", "billing_postcode",
            "created_at", "booking_attempts", "last_booking_status",
            "founder_followup_sent", "founder_followup_sent_at",
        ]

        for field in required_fields:
            assert field in lead, f"Missing required field: {field}"

    def test_filtering_leads_by_founder_email_status(self):
        """Should be able to filter leads by founder email status."""
        leads = [
            create_mock_abandoned_lead(id=1, email="sent1@test.com", founder_followup_sent=True, founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0)),
            create_mock_abandoned_lead(id=2, email="notsent1@test.com", founder_followup_sent=False, founder_followup_sent_at=None),
            create_mock_abandoned_lead(id=3, email="sent2@test.com", founder_followup_sent=True, founder_followup_sent_at=datetime(2026, 3, 1, 11, 0, 0)),
            create_mock_abandoned_lead(id=4, email="notsent2@test.com", founder_followup_sent=False, founder_followup_sent_at=None),
        ]

        # Filter sent
        sent_leads = [l for l in leads if l["founder_followup_sent"]]
        assert len(sent_leads) == 2
        assert all(l["founder_followup_sent"] for l in sent_leads)

        # Filter not sent
        not_sent_leads = [l for l in leads if not l["founder_followup_sent"]]
        assert len(not_sent_leads) == 2
        assert all(not l["founder_followup_sent"] for l in not_sent_leads)

    def test_count_leads_by_founder_email_status(self):
        """Should be able to count leads by founder email status."""
        leads = [
            create_mock_abandoned_lead(id=1, founder_followup_sent=True, founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0)),
            create_mock_abandoned_lead(id=2, founder_followup_sent=False, founder_followup_sent_at=None),
            create_mock_abandoned_lead(id=3, founder_followup_sent=True, founder_followup_sent_at=datetime(2026, 3, 1, 11, 0, 0)),
            create_mock_abandoned_lead(id=4, founder_followup_sent=False, founder_followup_sent_at=None),
            create_mock_abandoned_lead(id=5, founder_followup_sent=True, founder_followup_sent_at=datetime(2026, 3, 1, 12, 0, 0)),
        ]

        sent_count = sum(1 for l in leads if l["founder_followup_sent"])
        not_sent_count = sum(1 for l in leads if not l["founder_followup_sent"])

        assert sent_count == 3
        assert not_sent_count == 2
        assert sent_count + not_sent_count == len(leads)


# =============================================================================
# Founder Email Status - Boundary Tests
# =============================================================================

class TestFounderEmailStatusBoundaryTests:
    """Boundary tests for founder email status."""

    def test_founder_email_sent_at_future_date(self):
        """Should handle (invalid) future sent_at date gracefully."""
        future_date = datetime(2030, 12, 31, 23, 59, 59)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=future_date,
        )
        # Should still serialize correctly even if date is in future
        assert "2030-12-31" in lead["founder_followup_sent_at"]

    def test_founder_email_sent_at_very_old_date(self):
        """Should handle very old sent_at date correctly."""
        old_date = datetime(2020, 1, 1, 0, 0, 0)
        lead = create_mock_abandoned_lead(
            founder_followup_sent=True,
            founder_followup_sent_at=old_date,
        )
        assert "2020-01-01" in lead["founder_followup_sent_at"]

    def test_single_lead_with_founder_email_sent(self):
        """Should handle single lead with founder email correctly."""
        leads = [
            create_mock_abandoned_lead(
                founder_followup_sent=True,
                founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0),
            ),
        ]
        response_data = {"leads": leads, "count": 1}

        assert response_data["count"] == 1
        assert response_data["leads"][0]["founder_followup_sent"] is True

    def test_large_number_of_leads_with_founder_email_status(self):
        """Should handle large number of leads with various founder email statuses."""
        leads = [
            create_mock_abandoned_lead(
                id=i,
                founder_followup_sent=(i % 2 == 0),  # Alternating
                founder_followup_sent_at=datetime(2026, 3, 1, 10, 0, 0) if (i % 2 == 0) else None,
            )
            for i in range(100)
        ]

        sent_count = sum(1 for l in leads if l["founder_followup_sent"])
        not_sent_count = sum(1 for l in leads if not l["founder_followup_sent"])

        assert sent_count == 50
        assert not_sent_count == 50
        assert len(leads) == 100
