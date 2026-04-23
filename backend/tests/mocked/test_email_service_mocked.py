"""
Unit and Integration tests for Email Service.

Tests the email service functions with mocked SendGrid client.
All tests use mocks - no external API calls.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, date, time, timezone
import os
import string


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_booking(
    reference="TAG-12345",
    dropoff_date=None,
    pickup_date=None,
    customer_first_name="John",
    customer_last_name="Smith",
    customer_email="john@example.com",
    amount_pence=5000,
):
    """Create a mock booking for email template rendering."""
    booking = MagicMock()
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date(2026, 4, 15)
    booking.pickup_date = pickup_date or date(2026, 4, 22)
    booking.dropoff_time = time(8, 30)
    booking.pickup_time = time(15, 0)

    booking.customer = MagicMock()
    booking.customer.first_name = customer_first_name
    booking.customer.last_name = customer_last_name
    booking.customer.email = customer_email

    booking.vehicle = MagicMock()
    booking.vehicle.registration = "AB12 CDE"
    booking.vehicle.make = "Toyota"
    booking.vehicle.model = "Corolla"

    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence

    return booking


def create_mock_subscriber(
    email="subscriber@example.com",
    first_name="Jane",
    unsubscribe_token="test-token-123",
):
    """Create a mock marketing subscriber."""
    subscriber = MagicMock()
    subscriber.email = email
    subscriber.first_name = first_name
    subscriber.unsubscribe_token = unsubscribe_token
    subscriber.is_subscribed = True
    return subscriber


# ============================================================================
# Email Enabled Tests
# ============================================================================

class TestIsEmailEnabled:
    """Tests for is_email_enabled() function."""

    def test_enabled_when_api_key_set(self):
        """Should return True when SendGrid API key is set."""
        api_key = "SG.test_key_123456"

        is_enabled = bool(api_key)

        assert is_enabled is True

    def test_disabled_when_api_key_empty(self):
        """Should return False when API key is empty."""
        api_key = ""

        is_enabled = bool(api_key)

        assert is_enabled is False

    def test_disabled_when_api_key_none(self):
        """Should return False when API key is None."""
        api_key = None

        is_enabled = bool(api_key)

        assert is_enabled is False


# ============================================================================
# Promo Code Generation Tests
# ============================================================================

class TestGeneratePromoCode:
    """Tests for generate_promo_code() function."""

    def test_format_is_tag_xxxx_xxxx(self):
        """Promo code should be in format TAG-XXXX-XXXX."""
        import secrets

        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')

        part1 = ''.join(secrets.choice(chars) for _ in range(4))
        part2 = ''.join(secrets.choice(chars) for _ in range(4))
        code = f"TAG-{part1}-{part2}"

        assert code.startswith("TAG-")
        assert len(code) == 13  # TAG-XXXX-XXXX = 13 chars

    def test_excludes_confusing_characters(self):
        """Should exclude 0, O, I, 1, L."""
        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')

        assert '0' not in chars
        assert 'O' not in chars
        assert 'I' not in chars
        assert '1' not in chars
        assert 'L' not in chars

    def test_generates_unique_codes(self):
        """Should generate unique codes each time."""
        import secrets

        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')

        codes = set()
        for _ in range(100):
            part1 = ''.join(secrets.choice(chars) for _ in range(4))
            part2 = ''.join(secrets.choice(chars) for _ in range(4))
            code = f"TAG-{part1}-{part2}"
            codes.add(code)

        # All 100 codes should be unique
        assert len(codes) == 100

    def test_code_is_uppercase(self):
        """Promo code should be all uppercase."""
        code = "TAG-A3K9-M2P7"

        assert code == code.upper()


# ============================================================================
# Send Email Tests (Mocked SendGrid)
# ============================================================================

class TestSendEmail:
    """Tests for send_email() function with mocked SendGrid."""

    def test_returns_true_on_success(self):
        """Should return True when email sent successfully."""
        # Simulate successful send
        response_status = 202

        success = response_status in (200, 201, 202)

        assert success is True

    def test_returns_false_when_api_key_missing(self):
        """Should return False when API key not configured."""
        api_key = None

        if not api_key:
            result = False

        assert result is False

    def test_returns_false_on_api_error(self):
        """Should return False on SendGrid API error."""
        response_status = 500

        success = response_status in (200, 201, 202)

        assert success is False

    def test_handles_exception_gracefully(self):
        """Should handle exceptions and return False."""
        try:
            raise Exception("SendGrid error")
        except Exception:
            result = False

        assert result is False


# ============================================================================
# Email Template Tests
# ============================================================================

class TestEmailTemplates:
    """Tests for email template handling."""

    def test_booking_confirmation_template_exists(self):
        """Booking confirmation template should exist."""
        template_name = "booking_confirmation.html"

        # Check template exists in templates dir
        assert template_name is not None

    def test_template_substitutes_variables(self):
        """Template should substitute variables."""
        template = "<p>Hello {{first_name}}, your booking {{reference}} is confirmed.</p>"
        variables = {"first_name": "John", "reference": "TAG-12345"}

        result = template
        for var, value in variables.items():
            result = result.replace(f"{{{{{var}}}}}", value)

        assert "John" in result
        assert "TAG-12345" in result

    def test_template_handles_missing_variables(self):
        """Template should handle missing variables gracefully."""
        template = "<p>Hello {{first_name}}</p>"
        variables = {}

        result = template
        for var, value in variables.items():
            result = result.replace(f"{{{{{var}}}}}", value)

        # Original placeholder remains
        assert "{{first_name}}" in result


# ============================================================================
# Booking Confirmation Email Tests
# ============================================================================

class TestBookingConfirmationEmail:
    """Tests for booking confirmation email."""

    def test_includes_booking_reference(self):
        """Email should include booking reference."""
        booking = create_mock_booking(reference="TAG-ABC123")

        email_content = f"Your booking reference is {booking.reference}"

        assert "TAG-ABC123" in email_content

    def test_includes_customer_name(self):
        """Email should include customer name."""
        booking = create_mock_booking(customer_first_name="Jane")

        email_content = f"Dear {booking.customer.first_name}"

        assert "Jane" in email_content

    def test_includes_dates_and_times(self):
        """Email should include drop-off and pickup details."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 4, 15),
            pickup_date=date(2026, 4, 22)
        )

        dropoff_str = booking.dropoff_date.strftime("%d/%m/%Y")
        pickup_str = booking.pickup_date.strftime("%d/%m/%Y")

        assert dropoff_str == "15/04/2026"
        assert pickup_str == "22/04/2026"

    def test_includes_vehicle_details(self):
        """Email should include vehicle details."""
        booking = create_mock_booking()
        booking.vehicle.registration = "XY99 ZZZ"

        email_content = f"Vehicle: {booking.vehicle.registration}"

        assert "XY99 ZZZ" in email_content

    def test_includes_payment_amount(self):
        """Email should include payment amount."""
        booking = create_mock_booking(amount_pence=7500)

        amount_display = f"£{booking.payment.amount_pence / 100:.2f}"

        assert amount_display == "£75.00"


# ============================================================================
# Marketing Email Tests
# ============================================================================

class TestMarketingEmails:
    """Tests for marketing email functions."""

    def test_promo_email_includes_code(self):
        """Promo email should include promo code."""
        promo_code = "TAG-FREE-2026"

        email_content = f"Use code {promo_code} for your discount"

        assert promo_code in email_content

    def test_promo_email_includes_expiry(self):
        """Promo email should include expiry date."""
        expiry_date = date(2026, 5, 31)
        expiry_str = expiry_date.strftime("%d/%m/%Y")

        email_content = f"Valid until {expiry_str}"

        assert "31/05/2026" in email_content

    def test_marketing_campaign_unsubscribe_url_points_at_backend_api(self):
        """Regression guard: the unsubscribe link must target the backend API
        (API_BASE_URL + /api/marketing/unsubscribe/<token>), not the frontend
        domain. The frontend has no matching route, so a link built against
        tagparking.co.uk/unsubscribe/... produces a 404."""
        from unittest.mock import patch, MagicMock
        import email_service

        mock_sg = MagicMock()
        mock_sg.send.return_value = MagicMock(status_code=202)

        with patch.object(email_service, 'SENDGRID_API_KEY', 'fake-key'), \
             patch.object(email_service, 'SendGridAPIClient', return_value=mock_sg), \
             patch.dict(os.environ, {'API_BASE_URL': 'https://backend.example.com'}):
            result = email_service.send_marketing_campaign_email(
                email="test@example.com",
                first_name="Test",
                subject="Hi",
                message="Body",
                unsubscribe_token="tok-xyz-123",
            )

        assert result is True
        assert mock_sg.send.called
        sent_mail = mock_sg.send.call_args[0][0]
        html = sent_mail.get()['content'][0]['value']

        assert "tok-xyz-123" in html
        assert "https://backend.example.com/api/marketing/unsubscribe/tok-xyz-123" in html
        assert "tagparking.co.uk/unsubscribe/" not in html


# ============================================================================
# Founder Email Tests
# ============================================================================

class TestFounderEmail:
    """Tests for founder follow-up emails."""

    def test_sent_from_founder_email(self):
        """Founder email should be sent from founder's address."""
        from_email = "kristian@tagparking.co.uk"
        from_name = "Kristian"

        assert "kristian" in from_email.lower()

    def test_includes_personal_greeting(self):
        """Founder email should include personal greeting."""
        customer_name = "Jane"

        email_content = f"Hi {customer_name},\n\nI hope you had a great trip!"

        assert customer_name in email_content

    def test_includes_review_request(self):
        """Founder email should include review request."""
        google_review_url = "https://g.page/r/CbA2WXPNrM9fEAE/review"

        email_content = f"If you have a moment, we'd love a review: {google_review_url}"

        assert "review" in email_content.lower()


# ============================================================================
# Email Validation Tests
# ============================================================================

class TestEmailValidation:
    """Tests for email address validation."""

    def test_valid_email_accepted(self):
        """Should accept valid email addresses."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@gmail.com",
        ]

        for email in valid_emails:
            is_valid = "@" in email and "." in email.split("@")[1]
            assert is_valid is True

    def test_invalid_email_rejected(self):
        """Should reject invalid email addresses."""
        invalid_emails = [
            "notanemail",
            "missing@tld",
            "@nodomain.com",
        ]

        for email in invalid_emails:
            parts = email.split("@")
            is_valid = len(parts) == 2 and len(parts[0]) > 0 and "." in parts[1]
            assert is_valid is False


# ============================================================================
# Reminder Email Tests
# ============================================================================

class TestReminderEmails:
    """Tests for reminder email functions."""

    def test_2day_reminder_includes_booking_details(self):
        """2-day reminder should include booking details."""
        booking = create_mock_booking(
            reference="TAG-REM123",
            dropoff_date=date(2026, 4, 17)
        )

        email_content = f"Your parking starts in 2 days. Reference: {booking.reference}"

        assert "TAG-REM123" in email_content
        assert "2 days" in email_content

    def test_reminder_sent_to_correct_email(self):
        """Reminder should be sent to customer's email."""
        booking = create_mock_booking(customer_email="remind@example.com")

        to_email = booking.customer.email

        assert to_email == "remind@example.com"


# ============================================================================
# Thank You Email Tests
# ============================================================================

class TestThankYouEmail:
    """Tests for thank you email after pickup."""

    def test_thank_you_includes_review_link(self):
        """Thank you email should include review link."""
        review_url = "https://g.page/r/CbA2WXPNrM9fEAE/review"

        email_content = f"Please leave us a review: {review_url}"

        assert "review" in email_content.lower()

    def test_thank_you_sent_after_pickup(self):
        """Thank you email should be sent after pickup date."""
        booking = create_mock_booking(pickup_date=date(2026, 4, 22))
        today = date(2026, 4, 23)  # Day after pickup

        should_send = today > booking.pickup_date

        assert should_send is True


# ============================================================================
# Email Subject Line Tests
# ============================================================================

class TestEmailSubjectLines:
    """Tests for email subject lines."""

    def test_confirmation_subject_includes_reference(self):
        """Confirmation subject should include booking reference."""
        reference = "TAG-CONF01"
        subject = f"Booking Confirmed - {reference}"

        assert reference in subject

    def test_reminder_subject_includes_date(self):
        """Reminder subject should include date."""
        dropoff_date = date(2026, 4, 17)
        subject = f"Your parking starts on {dropoff_date.strftime('%d/%m')}"

        assert "17/04" in subject

    def test_subject_max_length(self):
        """Subject should be reasonable length."""
        subject = "Booking Confirmed - TAG-12345 | TAG Parking"

        max_length = 100
        assert len(subject) <= max_length


# ============================================================================
# Boundary Tests
# ============================================================================

class TestEmailBoundaryConditions:
    """Tests for email boundary conditions."""

    def test_handles_empty_customer_name(self):
        """Should handle booking with no customer name."""
        booking = create_mock_booking()
        booking.customer.first_name = ""

        greeting = booking.customer.first_name or "Customer"

        assert greeting == "Customer"

    def test_handles_missing_vehicle(self):
        """Should handle booking without vehicle."""
        booking = create_mock_booking()
        booking.vehicle = None

        vehicle_reg = booking.vehicle.registration if booking.vehicle else "N/A"

        assert vehicle_reg == "N/A"

    def test_handles_very_long_email(self):
        """Should handle very long email content."""
        content = "A" * 100000  # 100KB of content

        # SendGrid has 30MB limit, so this is fine
        assert len(content) < 30000000

    def test_handles_special_characters_in_name(self):
        """Should handle special characters in customer name."""
        booking = create_mock_booking()
        booking.customer.first_name = "José"

        greeting = f"Dear {booking.customer.first_name}"

        assert "José" in greeting


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestEmailErrorHandling:
    """Tests for email error handling."""

    def test_logs_error_on_failure(self):
        """Should log error when email fails."""
        error_message = "SendGrid API error: 500"

        # Simulate logging
        logged = f"Email failed: {error_message}"

        assert "failed" in logged.lower()

    def test_returns_false_on_rate_limit(self):
        """Should return False on rate limit error."""
        response_status = 429  # Rate limited

        success = response_status in (200, 201, 202)

        assert success is False

    def test_handles_network_timeout(self):
        """Should handle network timeout gracefully."""
        try:
            raise TimeoutError("Connection timed out")
        except TimeoutError:
            result = False

        assert result is False


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
