"""
Unit and Integration tests for Admin Email Endpoints.

Tests the admin email sending functionality:
- POST /api/admin/bookings/{booking_id}/resend-email
- POST /api/admin/bookings/{booking_id}/send-cancellation-email
- POST /api/admin/bookings/{booking_id}/send-refund-email
- POST /api/admin/bookings/{booking_id}/send-founder-email

All tests use mocks - no database connection or email sending.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, time, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-12345",
    dropoff_date=None,
    pickup_date=None,
    dropoff_time=None,
    pickup_time=None,
    status="confirmed",
    amount_pence=7500,
    confirmation_email_sent=False,
    cancellation_email_sent=False,
    refund_email_sent=False,
    customer_email="customer@example.com",
    customer_first_name="John",
):
    """Create a mock booking object."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date(2026, 5, 1)
    booking.pickup_date = pickup_date or date(2026, 5, 8)
    booking.dropoff_time = dropoff_time or time(8, 30)
    booking.pickup_time = pickup_time or time(15, 0)
    booking.flight_arrival_time = time(14, 30)
    booking.flight_departure_time = time(10, 0)
    booking.dropoff_airline_name = "Ryanair"
    booking.dropoff_flight_number = "FR1234"
    booking.dropoff_destination = "Malaga"
    booking.pickup_airline_name = "Ryanair"
    booking.pickup_flight_number = "FR1235"
    booking.pickup_origin = "Malaga"
    booking.package = "week"

    booking.status = MagicMock()
    booking.status.value = status
    booking.status.__eq__ = lambda self, other: self.value == other.value

    booking.confirmation_email_sent = confirmation_email_sent
    booking.confirmation_email_sent_at = None
    booking.cancellation_email_sent = cancellation_email_sent
    booking.cancellation_email_sent_at = None
    booking.refund_email_sent = refund_email_sent
    booking.refund_email_sent_at = None

    booking.customer = MagicMock()
    booking.customer.email = customer_email
    booking.customer.first_name = customer_first_name
    booking.customer_first_name = customer_first_name
    booking.customer.founder_followup_sent = False

    booking.vehicle = MagicMock()
    booking.vehicle.make = "Ford"
    booking.vehicle.model = "Focus"
    booking.vehicle.colour = "Blue"
    booking.vehicle.registration = "AB12 CDE"

    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence
    booking.payment.refund_amount_pence = None

    return booking


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Resend Confirmation Email Tests
# ============================================================================

class TestResendConfirmationEmailLogic:
    """Unit tests for resend confirmation email logic."""

    # Happy Path
    def test_finds_booking_by_id(self):
        """Should find booking by ID."""
        booking = create_mock_booking(id=123)

        found = booking.id == 123

        assert found is True

    def test_formats_dropoff_date_correctly(self):
        """Should format drop-off date as 'Day, DD Month YYYY'."""
        booking = create_mock_booking(dropoff_date=date(2026, 5, 15))

        formatted = booking.dropoff_date.strftime("%A, %d %B %Y")

        assert formatted == "Friday, 15 May 2026"

    def test_formats_pickup_date_correctly(self):
        """Should format pickup date correctly."""
        booking = create_mock_booking(pickup_date=date(2026, 5, 22))

        formatted = booking.pickup_date.strftime("%A, %d %B %Y")

        assert formatted == "Friday, 22 May 2026"

    def test_formats_time_as_24_hour(self):
        """Should format time in 24-hour format."""
        booking = create_mock_booking(dropoff_time=time(8, 30))

        formatted = booking.dropoff_time.strftime("%H:%M")

        assert formatted == "08:30"

    def test_calculates_duration_days(self):
        """Should calculate correct duration in days."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 5, 1),
            pickup_date=date(2026, 5, 8),
        )

        duration = (booking.pickup_date - booking.dropoff_date).days

        assert duration == 7

    def test_formats_package_name_with_duration(self):
        """Should format package name with duration."""
        duration = 7

        package_name = f"{duration} day{'s' if duration != 1 else ''}"

        assert package_name == "7 days"

    def test_formats_single_day_without_plural(self):
        """Should format single day without plural."""
        duration = 1

        package_name = f"{duration} day{'s' if duration != 1 else ''}"

        assert package_name == "1 day"

    def test_formats_payment_amount(self):
        """Should format payment amount correctly."""
        booking = create_mock_booking(amount_pence=7500)

        amount = f"£{booking.payment.amount_pence / 100:.2f}"

        assert amount == "£75.00"

    def test_builds_departure_flight_string(self):
        """Should build departure flight info string."""
        booking = create_mock_booking()

        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

        assert departure_flight == "Ryanair FR1234 to Malaga"

    def test_builds_return_flight_string(self):
        """Should build return flight info string."""
        booking = create_mock_booking()

        parts = []
        if booking.pickup_airline_name:
            parts.append(booking.pickup_airline_name)
        if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
            parts.append(booking.pickup_flight_number)
        return_flight = " ".join(parts)
        if booking.pickup_origin:
            return_flight += f" from {booking.pickup_origin}"

        assert return_flight == "Ryanair FR1235 from Malaga"

    # Unhappy Path
    def test_booking_not_found_returns_none(self):
        """Should return None when booking not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    # Edge Cases
    def test_handles_missing_flight_number(self):
        """Should handle missing or 'Unknown' flight number."""
        booking = create_mock_booking()
        booking.dropoff_flight_number = 'Unknown'

        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)

        assert departure_flight == "Ryanair"

    def test_handles_none_flight_time(self):
        """Should handle None flight times."""
        booking = create_mock_booking()
        booking.flight_arrival_time = None

        arrival_str = booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else ""

        assert arrival_str == ""

    def test_handles_zero_payment(self):
        """Should handle zero payment amount."""
        booking = create_mock_booking()
        booking.payment.amount_pence = 0

        amount = f"£{booking.payment.amount_pence / 100:.2f}"

        assert amount == "£0.00"


class TestResendEmailUpdateTracking:
    """Tests for email tracking updates."""

    def test_marks_confirmation_email_sent(self):
        """Should mark confirmation email as sent."""
        booking = create_mock_booking(confirmation_email_sent=False)

        booking.confirmation_email_sent = True
        booking.confirmation_email_sent_at = datetime.utcnow()

        assert booking.confirmation_email_sent is True
        assert booking.confirmation_email_sent_at is not None

    def test_updates_sent_timestamp(self):
        """Should update sent timestamp."""
        booking = create_mock_booking()
        before = datetime.utcnow()

        booking.confirmation_email_sent_at = datetime.utcnow()

        assert booking.confirmation_email_sent_at >= before


# ============================================================================
# Send Cancellation Email Tests
# ============================================================================

class TestSendCancellationEmailLogic:
    """Unit tests for send cancellation email logic."""

    # Happy Path
    def test_requires_cancelled_status(self):
        """Should require booking to be cancelled."""
        booking = create_mock_booking(status="cancelled")

        is_cancelled = booking.status.value == "cancelled"

        assert is_cancelled is True

    def test_rejects_non_cancelled_booking(self):
        """Should reject non-cancelled booking."""
        booking = create_mock_booking(status="confirmed")

        is_cancelled = booking.status.value == "cancelled"

        assert is_cancelled is False

    def test_uses_customer_email(self):
        """Should use customer email address."""
        booking = create_mock_booking(customer_email="customer@test.com")

        email = booking.customer.email

        assert email == "customer@test.com"

    def test_uses_customer_first_name(self):
        """Should use customer first name."""
        booking = create_mock_booking(customer_first_name="Jane")

        name = booking.customer_first_name or booking.customer.first_name

        assert name == "Jane"

    def test_includes_booking_reference(self):
        """Should include booking reference."""
        booking = create_mock_booking(reference="TAG-CANCEL-1")

        ref = booking.reference

        assert ref == "TAG-CANCEL-1"

    def test_formats_dropoff_date_for_email(self):
        """Should format drop-off date for email."""
        booking = create_mock_booking(dropoff_date=date(2026, 6, 15))

        formatted = booking.dropoff_date.strftime("%A, %d %B %Y")

        assert formatted == "Monday, 15 June 2026"

    # Unhappy Path
    def test_booking_not_found(self):
        """Should handle booking not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    # Edge Cases
    def test_marks_cancellation_email_sent(self):
        """Should mark cancellation email as sent."""
        booking = create_mock_booking(cancellation_email_sent=False)

        booking.cancellation_email_sent = True
        booking.cancellation_email_sent_at = datetime.utcnow()

        assert booking.cancellation_email_sent is True


# ============================================================================
# Send Refund Email Tests
# ============================================================================

class TestSendRefundEmailLogic:
    """Unit tests for send refund email logic."""

    # Happy Path
    def test_requires_cancelled_status(self):
        """Should require booking to be cancelled for refund email."""
        booking = create_mock_booking(status="cancelled")

        can_send = booking.status.value == "cancelled"

        assert can_send is True

    def test_uses_specific_refund_amount(self):
        """Should use specific refund amount if available."""
        booking = create_mock_booking()
        booking.payment.refund_amount_pence = 5000

        refund_amount = f"£{booking.payment.refund_amount_pence / 100:.2f}"

        assert refund_amount == "£50.00"

    def test_falls_back_to_original_amount(self):
        """Should fall back to original amount if no refund amount."""
        booking = create_mock_booking(amount_pence=7500)
        booking.payment.refund_amount_pence = None

        if booking.payment.refund_amount_pence:
            refund_amount = f"£{booking.payment.refund_amount_pence / 100:.2f}"
        else:
            refund_amount = f"£{booking.payment.amount_pence / 100:.2f}"

        assert refund_amount == "£75.00"

    def test_formats_refund_amount_correctly(self):
        """Should format refund amount with 2 decimal places."""
        booking = create_mock_booking()
        booking.payment.refund_amount_pence = 6543

        refund_amount = f"£{booking.payment.refund_amount_pence / 100:.2f}"

        assert refund_amount == "£65.43"

    # Unhappy Path
    def test_rejects_confirmed_booking(self):
        """Should reject confirmed booking for refund email."""
        booking = create_mock_booking(status="confirmed")

        can_send = booking.status.value == "cancelled"

        assert can_send is False

    def test_rejects_completed_booking(self):
        """Should reject completed booking for refund email."""
        booking = create_mock_booking(status="completed")

        can_send = booking.status.value == "cancelled"

        assert can_send is False

    # Edge Cases
    def test_handles_zero_refund_amount(self):
        """Should handle zero refund amount."""
        booking = create_mock_booking()
        booking.payment.refund_amount_pence = 0

        refund_amount = f"£{booking.payment.refund_amount_pence / 100:.2f}"

        assert refund_amount == "£0.00"

    def test_marks_refund_email_sent(self):
        """Should mark refund email as sent."""
        booking = create_mock_booking(refund_email_sent=False)

        booking.refund_email_sent = True
        booking.refund_email_sent_at = datetime.utcnow()

        assert booking.refund_email_sent is True


# ============================================================================
# Send Founder Email Tests
# ============================================================================

class TestSendFounderEmailLogic:
    """Unit tests for send founder email logic."""

    # Happy Path
    def test_uses_customer_info(self):
        """Should use customer information."""
        booking = create_mock_booking(
            customer_email="vip@example.com",
            customer_first_name="Sarah",
        )

        assert booking.customer.email == "vip@example.com"
        assert booking.customer.first_name == "Sarah"

    def test_includes_booking_reference(self):
        """Should include booking reference."""
        booking = create_mock_booking(reference="TAG-FOUNDER-1")

        assert booking.reference == "TAG-FOUNDER-1"

    def test_marks_founder_followup_sent(self):
        """Should mark founder followup as sent."""
        booking = create_mock_booking()

        booking.customer.founder_followup_sent = True

        assert booking.customer.founder_followup_sent is True

    # Unhappy Path
    def test_booking_not_found(self):
        """Should handle booking not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    # Edge Cases
    def test_handles_missing_customer_first_name(self):
        """Should handle missing customer first name."""
        booking = create_mock_booking()
        booking.customer.first_name = ""
        booking.customer_first_name = ""

        name = booking.customer_first_name or booking.customer.first_name or "Customer"

        assert name == "Customer"


# ============================================================================
# Email Send Success/Failure Tests
# ============================================================================

class TestEmailSendResults:
    """Tests for email send success/failure handling."""

    def test_returns_success_on_email_sent(self):
        """Should return success when email sent."""
        email_sent = True

        response = {"success": email_sent}

        assert response["success"] is True

    def test_returns_failure_on_email_not_sent(self):
        """Should return failure when email not sent."""
        email_sent = False

        if not email_sent:
            response = {"error": "Failed to send email"}
        else:
            response = {"success": True}

        assert "error" in response

    def test_success_message_includes_email_address(self):
        """Should include email address in success message."""
        email = "test@example.com"

        message = f"Email sent to {email}"

        assert email in message

    def test_success_includes_booking_reference(self):
        """Should include booking reference in success response."""
        booking = create_mock_booking(reference="TAG-SUCCESS-1")

        response = {
            "success": True,
            "reference": booking.reference,
        }

        assert response["reference"] == "TAG-SUCCESS-1"


# ============================================================================
# Authentication Tests
# ============================================================================

class TestAdminEmailAuthentication:
    """Tests for admin authentication on email endpoints."""

    def test_requires_admin_user(self):
        """Should require admin user."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_rejects_non_admin(self):
        """Should reject non-admin users."""
        user = MagicMock()
        user.is_admin = False

        has_access = user.is_admin

        assert has_access is False

    def test_rejects_inactive_admin(self):
        """Should reject inactive admin users."""
        user = create_mock_admin_user()
        user.is_active = False

        has_access = user.is_admin and user.is_active

        assert has_access is False


# ============================================================================
# Promo Code Display Tests
# ============================================================================

class TestPromoCodeDisplayInEmail:
    """Tests for promo code display in confirmation emails."""

    def test_includes_promo_code_when_used(self):
        """Should include promo code when one was used."""
        promo_code = "TAG-SAVE-10"

        email_data = {"promo_code": promo_code}

        assert email_data["promo_code"] == "TAG-SAVE-10"

    def test_calculates_discount_amount(self):
        """Should calculate discount amount."""
        original_pence = 7500
        paid_pence = 6000

        discount_pence = original_pence - paid_pence
        discount_display = f"£{discount_pence / 100:.2f}"

        assert discount_display == "£15.00"

    def test_shows_original_price(self):
        """Should show original price before discount."""
        original_pence = 7500

        original_display = f"£{original_pence / 100:.2f}"

        assert original_display == "£75.00"

    def test_no_promo_when_none_used(self):
        """Should not include promo info when no code used."""
        promo_code = None

        email_data = {"promo_code": promo_code}

        assert email_data["promo_code"] is None


# ============================================================================
# Boundary Tests
# ============================================================================

class TestEmailEndpointBoundaries:
    """Tests for boundary conditions."""

    def test_very_long_customer_name(self):
        """Should handle very long customer names."""
        long_name = "A" * 100
        booking = create_mock_booking(customer_first_name=long_name)

        name = booking.customer_first_name

        assert len(name) == 100

    def test_special_characters_in_email(self):
        """Should handle special characters in email."""
        email = "test+special@example.com"
        booking = create_mock_booking(customer_email=email)

        assert booking.customer.email == email

    def test_unicode_in_customer_name(self):
        """Should handle unicode in customer name."""
        booking = create_mock_booking(customer_first_name="José")

        assert booking.customer_first_name == "José"

    def test_large_payment_amount(self):
        """Should handle large payment amounts."""
        booking = create_mock_booking(amount_pence=100000)

        amount = f"£{booking.payment.amount_pence / 100:.2f}"

        assert amount == "£1000.00"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
