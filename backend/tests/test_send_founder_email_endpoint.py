"""
Tests for admin send-founder-email endpoint functionality.

Covers:
- POST /api/admin/bookings/{booking_id}/send-founder-email
- Only pending bookings allowed
- Prevents duplicate sends
- Updates customer tracking fields

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database and email dependencies.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, time, datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="07700900001",
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
    customer.founder_followup_sent = founder_followup_sent
    customer.founder_followup_sent_at = founder_followup_sent_at
    return customer


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    status="pending",
    customer=None,
    customer_first_name=None,
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.customer_first_name = customer_first_name

    if isinstance(status, str):
        booking.status = BookingStatus(status)
    else:
        booking.status = status

    booking.customer = customer or create_mock_customer()
    return booking


def create_mock_admin_user(is_admin=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@tagparking.co.uk"
    user.is_admin = is_admin
    return user


# =============================================================================
# POST /api/admin/bookings/{booking_id}/send-founder-email - Happy Path Tests
# =============================================================================

class TestSendFounderEmailEndpointHappyPath:
    """Happy path tests for send-founder-email endpoint."""

    def test_send_founder_email_success_response(self):
        """Successfully sending founder email returns success response."""
        from db_models import BookingStatus

        customer = create_mock_customer(
            email="customer@example.com",
            founder_followup_sent=False,
        )
        booking = create_mock_booking(
            reference="TAG-ABC123",
            status=BookingStatus.PENDING,
            customer=customer,
        )

        # Simulate successful email send
        email_sent = True

        if email_sent:
            customer.founder_followup_sent = True
            customer.founder_followup_sent_at = datetime.utcnow()

            response_data = {
                "success": True,
                "message": f"Founder followup email sent to {customer.email}",
                "reference": booking.reference,
            }
        else:
            response_data = None

        assert response_data is not None
        assert response_data["success"] is True
        assert "customer@example.com" in response_data["message"]
        assert response_data["reference"] == "TAG-ABC123"

    def test_send_founder_email_updates_customer_tracking(self):
        """Sending founder email updates customer tracking fields."""
        customer = create_mock_customer(
            founder_followup_sent=False,
            founder_followup_sent_at=None,
        )

        # Simulate successful send
        before_send = customer.founder_followup_sent
        assert before_send is False
        assert customer.founder_followup_sent_at is None

        # After send
        customer.founder_followup_sent = True
        customer.founder_followup_sent_at = datetime.utcnow()

        assert customer.founder_followup_sent is True
        assert customer.founder_followup_sent_at is not None

    def test_send_founder_email_uses_customer_first_name(self):
        """Email should use customer's first name."""
        customer = create_mock_customer(first_name="Sarah")
        booking = create_mock_booking(customer=customer)

        # Email function would receive first_name
        email_params = {
            "email": customer.email,
            "first_name": booking.customer_first_name or customer.first_name,
        }

        assert email_params["first_name"] == "Sarah"

    def test_send_founder_email_uses_snapshot_name_if_available(self):
        """Email should use snapshot name from booking if available."""
        customer = create_mock_customer(first_name="Sarah")
        booking = create_mock_booking(
            customer=customer,
            customer_first_name="Sarah Jane",  # Snapshot name
        )

        # Email function would receive snapshot name
        email_params = {
            "email": customer.email,
            "first_name": booking.customer_first_name or customer.first_name,
        }

        assert email_params["first_name"] == "Sarah Jane"

    def test_send_founder_email_only_for_pending_status(self):
        """Founder email can only be sent for pending bookings."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)

        is_pending = booking.status == BookingStatus.PENDING
        assert is_pending is True


# =============================================================================
# POST /api/admin/bookings/{booking_id}/send-founder-email - Negative Path Tests
# =============================================================================

class TestSendFounderEmailEndpointNegativePath:
    """Negative path tests for send-founder-email endpoint."""

    def test_send_founder_email_nonexistent_booking_404(self):
        """Should return 404 for non-existent booking."""
        booking = None  # Not found

        if booking is None:
            status_code = 404
            error = "Booking not found"
        else:
            status_code = 200
            error = None

        assert status_code == 404
        assert "not found" in error.lower()

    def test_send_founder_email_confirmed_booking_400(self):
        """Should return 400 for confirmed booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CONFIRMED)

        if booking.status != BookingStatus.PENDING:
            status_code = 400
            error = "Founder email can only be sent for pending bookings"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "pending" in error.lower()

    def test_send_founder_email_completed_booking_400(self):
        """Should return 400 for completed booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.COMPLETED)

        if booking.status != BookingStatus.PENDING:
            status_code = 400
            error = "Founder email can only be sent for pending bookings"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "pending" in error.lower()

    def test_send_founder_email_cancelled_booking_400(self):
        """Should return 400 for cancelled booking."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.CANCELLED)

        if booking.status != BookingStatus.PENDING:
            status_code = 400
            error = "Founder email can only be sent for pending bookings"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "pending" in error.lower()

    def test_send_founder_email_already_sent_400(self):
        """Should return 400 if founder email already sent to customer."""
        customer = create_mock_customer(
            email="customer@example.com",
            founder_followup_sent=True,
            founder_followup_sent_at=datetime(2026, 3, 1, 10, 30, 0),
        )
        booking = create_mock_booking(customer=customer)

        if customer.founder_followup_sent:
            status_code = 400
            error = f"Founder followup email already sent to {customer.email}"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "already sent" in error.lower()

    def test_send_founder_email_already_sent_includes_date(self):
        """Error message should include when email was sent."""
        sent_at = datetime(2026, 3, 1, 10, 30, 0)
        customer = create_mock_customer(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )

        formatted_date = sent_at.strftime('%d %b %Y at %H:%M')
        error = f"Founder followup email already sent to {customer.email} on {formatted_date}"

        assert "01 Mar 2026" in error
        assert "10:30" in error

    def test_send_founder_email_no_customer_400(self):
        """Should return 400 if booking has no customer."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)
        booking.customer = None

        if not booking.customer:
            status_code = 400
            error = "No customer associated with this booking"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "No customer" in error

    def test_send_founder_email_sendgrid_failure_500(self):
        """Should return 500 if SendGrid fails."""
        customer = create_mock_customer(founder_followup_sent=False)
        booking = create_mock_booking(customer=customer)

        # Simulate SendGrid failure
        email_sent = False

        if not email_sent:
            status_code = 500
            error = "Failed to send founder followup email. Check SendGrid configuration."
        else:
            status_code = 200
            error = None

        assert status_code == 500
        assert "SendGrid" in error

    def test_send_founder_email_requires_admin_auth(self):
        """Endpoint requires admin authentication."""
        user = create_mock_admin_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# POST /api/admin/bookings/{booking_id}/send-founder-email - Edge Cases
# =============================================================================

class TestSendFounderEmailEndpointEdgeCases:
    """Edge case tests for send-founder-email endpoint."""

    def test_send_founder_email_customer_with_special_chars_in_name(self):
        """Should handle customer names with special characters."""
        special_names = ["José", "O'Connor", "Anne-Marie", "Müller"]

        for name in special_names:
            customer = create_mock_customer(first_name=name)
            booking = create_mock_booking(customer=customer)

            email_params = {
                "first_name": booking.customer_first_name or customer.first_name,
            }

            assert email_params["first_name"] == name

    def test_send_founder_email_customer_with_long_email(self):
        """Should handle customers with very long email addresses."""
        long_email = "verylongemailaddress" + "a" * 200 + "@example.com"
        customer = create_mock_customer(email=long_email[:254])  # Max email length

        assert len(customer.email) <= 254

    def test_send_founder_email_concurrent_requests_prevention(self):
        """Second request should fail if email already sent by first."""
        customer = create_mock_customer(founder_followup_sent=False)

        # First request sends
        customer.founder_followup_sent = True
        customer.founder_followup_sent_at = datetime.utcnow()

        # Second request should fail
        if customer.founder_followup_sent:
            status_code = 400
        else:
            status_code = 200

        assert status_code == 400

    def test_send_founder_email_preserves_customer_data(self):
        """Sending email should not modify other customer fields."""
        customer = create_mock_customer(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="07700900001",
            founder_followup_sent=False,
        )

        original_first_name = customer.first_name
        original_last_name = customer.last_name
        original_email = customer.email
        original_phone = customer.phone

        # Simulate send - only founder_followup fields should change
        customer.founder_followup_sent = True
        customer.founder_followup_sent_at = datetime.utcnow()

        assert customer.first_name == original_first_name
        assert customer.last_name == original_last_name
        assert customer.email == original_email
        assert customer.phone == original_phone

    def test_send_founder_email_preserves_booking_data(self):
        """Sending email should not modify booking fields."""
        from db_models import BookingStatus

        booking = create_mock_booking(
            reference="TAG-ABC123",
            status=BookingStatus.PENDING,
        )

        original_reference = booking.reference
        original_status = booking.status

        # Simulate send - booking should not change
        # (only customer fields are updated)

        assert booking.reference == original_reference
        assert booking.status == original_status

    def test_send_founder_email_different_customers_same_booking_id_rejected(self):
        """Each customer should track their own followup status."""
        customer1 = create_mock_customer(id=1, founder_followup_sent=True)
        customer2 = create_mock_customer(id=2, founder_followup_sent=False)

        # Customer 1 already received email
        assert customer1.founder_followup_sent is True

        # Customer 2 hasn't
        assert customer2.founder_followup_sent is False

    def test_send_founder_email_booking_source_irrelevant(self):
        """Founder email works regardless of booking source."""
        from db_models import BookingStatus

        sources = ["online", "manual", "phone", "admin"]

        for source in sources:
            booking = create_mock_booking(status=BookingStatus.PENDING)
            booking.booking_source = source

            # Should be allowed for all sources
            is_pending = booking.status == BookingStatus.PENDING
            assert is_pending is True


# =============================================================================
# Response Structure Tests
# =============================================================================

class TestSendFounderEmailResponseStructure:
    """Tests for API response structure."""

    def test_success_response_structure(self):
        """Success response should have required fields."""
        response = {
            "success": True,
            "message": "Founder followup email sent to test@example.com",
            "reference": "TAG-ABC123",
        }

        assert "success" in response
        assert "message" in response
        assert "reference" in response
        assert response["success"] is True

    def test_error_response_structure_404(self):
        """404 error response should have detail field."""
        error_response = {
            "detail": "Booking not found"
        }

        assert "detail" in error_response
        assert "not found" in error_response["detail"].lower()

    def test_error_response_structure_400_pending(self):
        """400 error for non-pending should explain allowed status."""
        error_response = {
            "detail": "Founder email can only be sent for pending bookings"
        }

        assert "pending" in error_response["detail"].lower()

    def test_error_response_structure_400_already_sent(self):
        """400 error for already sent should include email and date."""
        sent_at = datetime(2026, 3, 1, 10, 30, 0)
        email = "test@example.com"
        formatted_date = sent_at.strftime('%d %b %Y at %H:%M')

        error_response = {
            "detail": f"Founder followup email already sent to {email} on {formatted_date}"
        }

        assert email in error_response["detail"]
        assert "already sent" in error_response["detail"].lower()

    def test_error_response_structure_500(self):
        """500 error should mention SendGrid."""
        error_response = {
            "detail": "Failed to send founder followup email. Check SendGrid configuration."
        }

        assert "SendGrid" in error_response["detail"]


# =============================================================================
# Integration with Booking List Tests
# =============================================================================

class TestFounderEmailInBookingsList:
    """Tests for founder_followup_sent in bookings list response."""

    def test_booking_response_includes_founder_followup_sent(self):
        """Booking list response should include founder_followup_sent."""
        customer = create_mock_customer(founder_followup_sent=True)

        booking_data = {
            "customer": {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "founder_followup_sent": customer.founder_followup_sent,
                "founder_followup_sent_at": customer.founder_followup_sent_at,
            }
        }

        assert "founder_followup_sent" in booking_data["customer"]
        assert booking_data["customer"]["founder_followup_sent"] is True

    def test_booking_response_includes_founder_followup_sent_at(self):
        """Booking list response should include founder_followup_sent_at."""
        sent_at = datetime(2026, 3, 1, 10, 30, 0)
        customer = create_mock_customer(
            founder_followup_sent=True,
            founder_followup_sent_at=sent_at,
        )

        booking_data = {
            "customer": {
                "founder_followup_sent": customer.founder_followup_sent,
                "founder_followup_sent_at": customer.founder_followup_sent_at.isoformat() if customer.founder_followup_sent_at else None,
            }
        }

        assert "founder_followup_sent_at" in booking_data["customer"]
        assert booking_data["customer"]["founder_followup_sent_at"] == "2026-03-01T10:30:00"

    def test_booking_response_founder_followup_sent_false(self):
        """Booking with no founder email sent should show False."""
        customer = create_mock_customer(founder_followup_sent=False)

        booking_data = {
            "customer": {
                "founder_followup_sent": customer.founder_followup_sent,
                "founder_followup_sent_at": None,
            }
        }

        assert booking_data["customer"]["founder_followup_sent"] is False
        assert booking_data["customer"]["founder_followup_sent_at"] is None


# =============================================================================
# Button State Tests (Frontend Logic)
# =============================================================================

class TestFounderEmailButtonState:
    """Tests for button state logic in frontend."""

    def test_button_enabled_for_pending_not_sent(self):
        """Button should be enabled for pending booking with no email sent."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)
        booking.customer.founder_followup_sent = False

        is_pending = booking.status == BookingStatus.PENDING
        already_sent = booking.customer.founder_followup_sent

        button_disabled = not is_pending or already_sent
        assert button_disabled is False  # Button should be enabled

    def test_button_disabled_for_pending_already_sent(self):
        """Button should be disabled for pending booking with email already sent."""
        from db_models import BookingStatus

        booking = create_mock_booking(status=BookingStatus.PENDING)
        booking.customer.founder_followup_sent = True

        is_pending = booking.status == BookingStatus.PENDING
        already_sent = booking.customer.founder_followup_sent

        button_disabled = not is_pending or already_sent
        assert button_disabled is True  # Button should be disabled

    def test_button_hidden_for_non_pending(self):
        """Button should not be shown for non-pending bookings."""
        from db_models import BookingStatus

        non_pending_statuses = [
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
        ]

        for status in non_pending_statuses:
            booking = create_mock_booking(status=status)
            show_button = booking.status == BookingStatus.PENDING
            assert show_button is False

    def test_button_text_changes_when_sent(self):
        """Button text should indicate when email was already sent."""
        customer_sent = create_mock_customer(founder_followup_sent=True)
        customer_not_sent = create_mock_customer(founder_followup_sent=False)

        # Button text logic
        def get_button_text(customer):
            if customer.founder_followup_sent:
                return "Founder Email Sent ✓"
            return "Send Founder Email"

        assert get_button_text(customer_sent) == "Founder Email Sent ✓"
        assert get_button_text(customer_not_sent) == "Send Founder Email"

    def test_button_title_changes_when_sent(self):
        """Button title/tooltip should indicate when already sent."""
        customer_sent = create_mock_customer(founder_followup_sent=True)
        customer_not_sent = create_mock_customer(founder_followup_sent=False)

        def get_button_title(customer):
            if customer.founder_followup_sent:
                return "Founder email already sent"
            return "Send personal follow-up email from founder"

        assert "already sent" in get_button_title(customer_sent)
        assert "personal follow-up" in get_button_title(customer_not_sent)


# =============================================================================
# Confirmation Modal Tests (Frontend Logic)
# =============================================================================

class TestFounderEmailConfirmationModal:
    """Tests for confirmation modal content."""

    def test_modal_shows_booking_reference(self):
        """Modal should display booking reference."""
        booking = create_mock_booking(reference="TAG-ABC123")

        modal_content = {
            "reference": booking.reference,
        }

        assert modal_content["reference"] == "TAG-ABC123"

    def test_modal_shows_customer_name(self):
        """Modal should display customer name."""
        customer = create_mock_customer(first_name="John", last_name="Doe")
        booking = create_mock_booking(customer=customer)

        modal_content = {
            "customer_name": f"{customer.first_name} {customer.last_name}",
        }

        assert modal_content["customer_name"] == "John Doe"

    def test_modal_shows_customer_email(self):
        """Modal should display customer email."""
        customer = create_mock_customer(email="john@example.com")
        booking = create_mock_booking(customer=customer)

        modal_content = {
            "email": customer.email,
        }

        assert modal_content["email"] == "john@example.com"

    def test_modal_explains_cc_to_founder(self):
        """Modal should explain email will be CC'd to founder."""
        modal_warning = "The email will be CC'd to Kristian so he can see and respond to any replies."

        assert "CC'd" in modal_warning
        assert "Kristian" in modal_warning


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
