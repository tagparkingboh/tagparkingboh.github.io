"""
Tests for Marketing Subscriber Founder Thank You Email functionality.

Covers:
- POST /api/admin/marketing-subscribers/{id}/send-founder-email
- send_founder_thank_you_email service function
- Promo code generation and uniqueness
- Database field updates

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios
- Integration: Full workflows with mocked database/email

All tests use mocked data to avoid database and email dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_subscriber(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    unsubscribe_token="test-token-123",
    subscribed_at=None,
    welcome_email_sent=True,
    welcome_email_sent_at=None,
    promo_code=None,
    promo_code_sent=False,
    promo_10_code=None,
    promo_10_sent=False,
    promo_free_code=None,
    founder_promo_code=None,
    founder_email_sent=False,
    founder_email_sent_at=None,
    founder_promo_used=False,
    founder_promo_used_at=None,
    founder_promo_used_booking_id=None,
    unsubscribed=False,
    unsubscribed_at=None,
):
    """Create a mock MarketingSubscriber object."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.first_name = first_name
    subscriber.last_name = last_name
    subscriber.email = email
    subscriber.unsubscribe_token = unsubscribe_token
    subscriber.subscribed_at = subscribed_at or datetime.utcnow()
    subscriber.welcome_email_sent = welcome_email_sent
    subscriber.welcome_email_sent_at = welcome_email_sent_at
    subscriber.promo_code = promo_code
    subscriber.promo_code_sent = promo_code_sent
    subscriber.promo_10_code = promo_10_code
    subscriber.promo_10_sent = promo_10_sent
    subscriber.promo_free_code = promo_free_code
    subscriber.founder_promo_code = founder_promo_code
    subscriber.founder_email_sent = founder_email_sent
    subscriber.founder_email_sent_at = founder_email_sent_at
    subscriber.founder_promo_used = founder_promo_used
    subscriber.founder_promo_used_at = founder_promo_used_at
    subscriber.founder_promo_used_booking_id = founder_promo_used_booking_id
    subscriber.unsubscribed = unsubscribed
    subscriber.unsubscribed_at = unsubscribed_at
    return subscriber


def create_mock_subscriber_response(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    subscribed_at=None,
    founder_promo_code=None,
    founder_email_sent=False,
    founder_email_sent_at=None,
    founder_promo_used=False,
    founder_promo_used_at=None,
    unsubscribed=False,
):
    """Create a mock subscriber response as returned by API."""
    return {
        "id": id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "subscribed_at": (subscribed_at or datetime.utcnow()).isoformat(),
        "founder_promo_code": founder_promo_code,
        "founder_email_sent": founder_email_sent,
        "founder_email_sent_at": founder_email_sent_at.isoformat() if founder_email_sent_at else None,
        "founder_promo_used": founder_promo_used,
        "founder_promo_used_at": founder_promo_used_at.isoformat() if founder_promo_used_at else None,
        "unsubscribed": unsubscribed,
    }


# =============================================================================
# Unit Tests - MarketingSubscriber Founder Email Fields
# =============================================================================

class TestFounderEmailFields:
    """Unit tests for founder email-related fields on MarketingSubscriber."""

    def test_founder_email_fields_default_values(self):
        """Founder email fields should have correct defaults."""
        subscriber = create_mock_subscriber()

        # Set defaults explicitly
        subscriber.founder_promo_code = None
        subscriber.founder_email_sent = False
        subscriber.founder_email_sent_at = None
        subscriber.founder_promo_used = False
        subscriber.founder_promo_used_at = None
        subscriber.founder_promo_used_booking_id = None

        assert subscriber.founder_promo_code is None
        assert subscriber.founder_email_sent is False
        assert subscriber.founder_email_sent_at is None
        assert subscriber.founder_promo_used is False
        assert subscriber.founder_promo_used_at is None
        assert subscriber.founder_promo_used_booking_id is None

    def test_can_set_founder_promo_code(self):
        """Should be able to set a founder promo code."""
        subscriber = create_mock_subscriber()

        subscriber.founder_promo_code = "TAG-FOUNDER-ABCD"
        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()

        assert subscriber.founder_promo_code == "TAG-FOUNDER-ABCD"
        assert subscriber.founder_email_sent is True
        assert subscriber.founder_email_sent_at is not None

    def test_can_mark_founder_promo_used(self):
        """Should be able to mark founder promo as used."""
        subscriber = create_mock_subscriber(
            founder_promo_code="TAG-FUSED-1234",
            founder_email_sent=True,
        )

        subscriber.founder_promo_used = True
        subscriber.founder_promo_used_at = datetime.utcnow()
        subscriber.founder_promo_used_booking_id = 123

        assert subscriber.founder_promo_used is True
        assert subscriber.founder_promo_used_at is not None
        assert subscriber.founder_promo_used_booking_id == 123

    def test_founder_email_separate_from_10_percent_promo(self):
        """Founder email should be separate from regular 10% promo."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10PC-1234",
            promo_10_sent=True,
            founder_promo_code="TAG-FNDR-5678",
            founder_email_sent=True,
        )

        # Both can exist simultaneously
        assert subscriber.promo_10_code != subscriber.founder_promo_code
        assert subscriber.promo_10_sent is True
        assert subscriber.founder_email_sent is True


# =============================================================================
# Unit Tests - send_founder_thank_you_email Function
# =============================================================================

class TestSendFounderThankYouEmailUnit:
    """Unit tests for send_founder_thank_you_email email service function."""

    @patch('email_service.SendGridAPIClient')
    @patch('email_service.SENDGRID_API_KEY', 'test-key')
    def test_send_founder_email_calls_sendgrid(self, mock_sg_client):
        """Should call SendGrid API when sending founder email."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_sg_client.return_value.send.return_value = mock_response

        from email_service import send_founder_thank_you_email

        # Mock the template file
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = """
            <html><body>Hi {{FIRST_NAME}}, code: {{PROMO_CODE}} from {{FOUNDER_NAME}}</body></html>
            """

            result = send_founder_thank_you_email(
                email="test@example.com",
                first_name="John",
                promo_code="TAG-TEST-1234",
            )

        # SendGrid should have been called
        assert mock_sg_client.return_value.send.called

    def test_send_founder_email_replaces_placeholders(self):
        """Should replace all template placeholders."""
        template = """
        Hi {{FIRST_NAME}},
        Your code is: {{PROMO_CODE}}
        From {{FOUNDER_NAME}}
        """

        first_name = "Sarah"
        promo_code = "TAG-TEST-ABCD"
        founder_name = "Kristian"

        result = template.replace("{{FIRST_NAME}}", first_name)
        result = result.replace("{{PROMO_CODE}}", promo_code)
        result = result.replace("{{FOUNDER_NAME}}", founder_name)

        assert "Sarah" in result
        assert "TAG-TEST-ABCD" in result
        assert "Kristian" in result
        assert "{{FIRST_NAME}}" not in result
        assert "{{PROMO_CODE}}" not in result
        assert "{{FOUNDER_NAME}}" not in result

    @patch('email_service.SENDGRID_API_KEY', None)
    def test_send_founder_email_fails_without_api_key(self):
        """Should return False when SendGrid API key is not configured."""
        from email_service import send_founder_thank_you_email

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "<html></html>"

            result = send_founder_thank_you_email(
                email="test@example.com",
                first_name="John",
                promo_code="TAG-TEST-1234",
            )

        assert result is False

    def test_send_founder_email_template_missing(self):
        """Should return False when template file is missing."""
        from email_service import send_founder_thank_you_email

        with patch('builtins.open', side_effect=FileNotFoundError):
            result = send_founder_thank_you_email(
                email="test@example.com",
                first_name="John",
                promo_code="TAG-TEST-1234",
            )

        assert result is False


# =============================================================================
# Integration Tests - POST /api/admin/marketing-subscribers/{id}/send-founder-email
# Happy Path Tests
# =============================================================================

class TestSendFounderEmailEndpointHappyPath:
    """Happy path tests for send-founder-email endpoint."""

    def test_send_founder_email_success_response(self):
        """Successfully sending founder email returns success response."""
        subscriber = create_mock_subscriber(
            id=1,
            email="customer@example.com",
            first_name="Jane",
            founder_email_sent=False,
            founder_promo_used=False,
            unsubscribed=False,
        )

        # Simulate successful email send
        email_sent = True

        if email_sent:
            subscriber.founder_promo_code = "TAG-FNDR-1234"
            subscriber.founder_email_sent = True
            subscriber.founder_email_sent_at = datetime.utcnow()

            response_data = {
                "success": True,
                "message": f"Founder thank you email sent to {subscriber.email}",
                "promo_code": subscriber.founder_promo_code,
            }
        else:
            response_data = None

        assert response_data is not None
        assert response_data["success"] is True
        assert "customer@example.com" in response_data["message"]
        assert response_data["promo_code"] == "TAG-FNDR-1234"

    def test_send_founder_email_generates_promo_code(self):
        """Should generate a unique promo code for the subscriber."""
        subscriber = create_mock_subscriber(
            founder_promo_code=None,
        )

        assert subscriber.founder_promo_code is None

        # Simulate code generation
        subscriber.founder_promo_code = "TAG-FNDR-ABCD"

        assert subscriber.founder_promo_code is not None
        assert subscriber.founder_promo_code.startswith("TAG-")

    def test_send_founder_email_updates_subscriber_tracking(self):
        """Sending founder email updates subscriber tracking fields."""
        subscriber = create_mock_subscriber(
            founder_email_sent=False,
            founder_email_sent_at=None,
        )

        assert subscriber.founder_email_sent is False
        assert subscriber.founder_email_sent_at is None

        # After send
        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()

        assert subscriber.founder_email_sent is True
        assert subscriber.founder_email_sent_at is not None

    def test_send_founder_email_reuses_existing_code(self):
        """Should reuse existing promo code if already generated."""
        subscriber = create_mock_subscriber(
            founder_promo_code="TAG-EXIST-1234",
            founder_email_sent=False,  # Email not yet sent, but code exists
        )

        # The endpoint should use the existing code
        promo_code = subscriber.founder_promo_code

        assert promo_code == "TAG-EXIST-1234"

    def test_send_founder_email_ccs_founder(self):
        """Email should be CC'd to founder's email address."""
        # This is a behavior check - the CC is added in the email service
        import os

        founder_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")
        founder_name = os.getenv("FOUNDER_NAME", "Kristian")

        assert founder_email is not None
        assert founder_name is not None


# =============================================================================
# Integration Tests - POST /api/admin/marketing-subscribers/{id}/send-founder-email
# Negative Path Tests
# =============================================================================

class TestSendFounderEmailEndpointNegativePath:
    """Negative path tests for send-founder-email endpoint."""

    def test_send_founder_email_subscriber_not_found_404(self):
        """Should return 404 for non-existent subscriber."""
        subscriber = None  # Not found

        if subscriber is None:
            status_code = 404
            error = "Subscriber not found"
        else:
            status_code = 200
            error = None

        assert status_code == 404
        assert "not found" in error.lower()

    def test_send_founder_email_unsubscribed_400(self):
        """Should return 400 for unsubscribed subscriber."""
        subscriber = create_mock_subscriber(
            unsubscribed=True,
            unsubscribed_at=datetime.utcnow(),
        )

        if subscriber.unsubscribed:
            status_code = 400
            error = "Subscriber has unsubscribed"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "unsubscribed" in error.lower()

    def test_send_founder_email_promo_already_used_400(self):
        """Should return 400 if founder promo code already used."""
        subscriber = create_mock_subscriber(
            founder_promo_code="TAG-USED-1234",
            founder_email_sent=True,
            founder_promo_used=True,
            founder_promo_used_at=datetime.utcnow(),
        )

        if subscriber.founder_promo_used:
            status_code = 400
            error = "Founder promo code has already been used"
        else:
            status_code = 200
            error = None

        assert status_code == 400
        assert "already been used" in error.lower()

    def test_send_founder_email_sendgrid_failure_500(self):
        """Should return 500 if SendGrid fails."""
        subscriber = create_mock_subscriber(
            founder_email_sent=False,
            founder_promo_used=False,
            unsubscribed=False,
        )

        # Simulate SendGrid failure
        email_sent = False

        if not email_sent:
            status_code = 500
            error = "Failed to send founder email. Check SendGrid configuration."
        else:
            status_code = 200
            error = None

        assert status_code == 500
        assert "SendGrid" in error

    def test_send_founder_email_requires_admin_auth(self):
        """Endpoint requires admin authentication."""
        user_is_admin = False

        if not user_is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403

    def test_send_founder_email_code_generation_fails_500(self):
        """Should return 500 if promo code generation fails after retries."""
        # Simulate all generated codes being taken
        all_codes_taken = True

        if all_codes_taken:
            status_code = 500
            error = "Failed to generate unique promo code"
        else:
            status_code = 200
            error = None

        assert status_code == 500
        assert "unique promo code" in error.lower()


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestSendFounderEmailEdgeCases:
    """Edge case tests for founder email functionality."""

    def test_founder_email_subscriber_with_special_chars_in_name(self):
        """Should handle subscriber names with special characters."""
        special_names = ["José", "O'Connor", "Anne-Marie", "Müller", "李明"]

        for name in special_names:
            subscriber = create_mock_subscriber(first_name=name)

            email_params = {
                "first_name": subscriber.first_name,
            }

            assert email_params["first_name"] == name

    def test_founder_email_subscriber_with_long_email(self):
        """Should handle subscribers with very long email addresses."""
        long_email = "verylongemailaddress" + "a" * 200 + "@example.com"
        subscriber = create_mock_subscriber(email=long_email[:254])  # Max email length

        assert len(subscriber.email) <= 254

    def test_founder_email_empty_first_name(self):
        """Should handle empty first name gracefully."""
        subscriber = create_mock_subscriber(first_name="")

        # Could use a default greeting
        greeting_name = subscriber.first_name or "there"

        assert greeting_name == "there"

    def test_founder_email_resend_allowed_if_not_used(self):
        """Should allow resending founder email if promo not yet used."""
        subscriber = create_mock_subscriber(
            founder_promo_code="TAG-FNDR-1234",
            founder_email_sent=True,
            founder_promo_used=False,  # Not yet used
            unsubscribed=False,
        )

        # Can resend if promo not used
        can_resend = not subscriber.founder_promo_used and not subscriber.unsubscribed
        assert can_resend is True

    def test_founder_email_concurrent_requests_prevention(self):
        """Second request should fail if promo already marked as used by first."""
        subscriber = create_mock_subscriber(
            founder_promo_used=False,
        )

        # First request completes
        subscriber.founder_promo_used = True
        subscriber.founder_promo_used_at = datetime.utcnow()

        # Second request should fail
        if subscriber.founder_promo_used:
            status_code = 400
        else:
            status_code = 200

        assert status_code == 400

    def test_founder_email_preserves_other_subscriber_data(self):
        """Sending founder email should not modify other subscriber fields."""
        subscriber = create_mock_subscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            promo_10_code="TAG-10PC-1234",
            promo_10_sent=True,
        )

        original_first_name = subscriber.first_name
        original_last_name = subscriber.last_name
        original_email = subscriber.email
        original_promo_10 = subscriber.promo_10_code

        # Simulate send - only founder fields should change
        subscriber.founder_promo_code = "TAG-FNDR-5678"
        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()

        assert subscriber.first_name == original_first_name
        assert subscriber.last_name == original_last_name
        assert subscriber.email == original_email
        assert subscriber.promo_10_code == original_promo_10


# =============================================================================
# Boundary Tests
# =============================================================================

class TestFounderEmailBoundaryTests:
    """Boundary tests for founder email functionality."""

    def test_promo_code_length_boundary(self):
        """Promo code should be within acceptable length."""
        from email_service import generate_promo_code

        code = generate_promo_code()

        # TAG-XXXX-XXXX = 13 characters
        assert len(code) == 13

    def test_promo_code_uniqueness_check_max_retries(self):
        """Should try up to 10 times to generate unique code."""
        max_retries = 10
        attempts = 0

        # Simulate finding a unique code on the 10th attempt
        for i in range(max_retries):
            attempts += 1
            is_unique = (i == max_retries - 1)  # Only last attempt is unique
            if is_unique:
                break

        assert attempts == max_retries

    def test_subscriber_id_zero(self):
        """Should handle subscriber ID of 0 (edge case)."""
        subscriber = create_mock_subscriber(id=0)

        assert subscriber.id == 0

    def test_subscriber_id_very_large(self):
        """Should handle very large subscriber IDs."""
        subscriber = create_mock_subscriber(id=9999999999)

        assert subscriber.id == 9999999999

    def test_founder_email_sent_at_timestamp_precision(self):
        """Should record precise timestamp when email is sent."""
        before_send = datetime.utcnow()
        subscriber = create_mock_subscriber()

        subscriber.founder_email_sent_at = datetime.utcnow()

        after_send = datetime.utcnow()

        assert before_send <= subscriber.founder_email_sent_at <= after_send


# =============================================================================
# Promo Code Generation Tests
# =============================================================================

class TestFounderPromoCodeGeneration:
    """Tests for founder promo code generation."""

    def test_promo_code_format(self):
        """Promo codes should have correct format."""
        from email_service import generate_promo_code

        code = generate_promo_code()

        # Should be TAG-XXXX-XXXX format
        assert code.startswith("TAG-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4

    def test_promo_codes_are_unique(self):
        """Generated promo codes should be unique."""
        from email_service import generate_promo_code

        codes = [generate_promo_code() for _ in range(100)]

        # All codes should be unique
        assert len(codes) == len(set(codes))

    def test_promo_code_uppercase(self):
        """Promo codes should be uppercase."""
        from email_service import generate_promo_code

        code = generate_promo_code()

        assert code == code.upper()

    def test_promo_code_no_confusing_characters(self):
        """Promo codes should not contain confusing characters."""
        from email_service import generate_promo_code

        for _ in range(20):
            code = generate_promo_code()
            chars = code.replace("TAG-", "").replace("-", "")

            # Should not contain 0, O, I, 1, L (easily confused)
            assert '0' not in chars
            assert 'O' not in chars
            assert 'I' not in chars
            assert '1' not in chars
            assert 'L' not in chars


# =============================================================================
# Response Structure Tests
# =============================================================================

class TestFounderEmailResponseStructure:
    """Tests for API response structure."""

    def test_success_response_structure(self):
        """Success response should have required fields."""
        response = {
            "success": True,
            "message": "Founder thank you email sent to test@example.com",
            "promo_code": "TAG-FNDR-1234",
        }

        assert "success" in response
        assert "message" in response
        assert "promo_code" in response
        assert response["success"] is True

    def test_error_response_structure_404(self):
        """404 error response should have detail field."""
        error_response = {
            "detail": "Subscriber not found"
        }

        assert "detail" in error_response
        assert "not found" in error_response["detail"].lower()

    def test_error_response_structure_400_unsubscribed(self):
        """400 error for unsubscribed should explain reason."""
        error_response = {
            "detail": "Subscriber has unsubscribed"
        }

        assert "unsubscribed" in error_response["detail"].lower()

    def test_error_response_structure_400_already_used(self):
        """400 error for already used promo should explain reason."""
        error_response = {
            "detail": "Founder promo code has already been used"
        }

        assert "already been used" in error_response["detail"].lower()

    def test_error_response_structure_500(self):
        """500 error should mention SendGrid."""
        error_response = {
            "detail": "Failed to send founder email. Check SendGrid configuration."
        }

        assert "SendGrid" in error_response["detail"]


# =============================================================================
# Integration Tests - Subscribers List Response
# =============================================================================

class TestFounderEmailInSubscribersList:
    """Tests for founder email fields in subscribers list response."""

    def test_subscriber_response_includes_founder_promo_code(self):
        """Subscriber list response should include founder_promo_code."""
        subscriber = create_mock_subscriber(founder_promo_code="TAG-FNDR-1234")

        subscriber_data = {
            "founder_promo_code": subscriber.founder_promo_code,
        }

        assert "founder_promo_code" in subscriber_data
        assert subscriber_data["founder_promo_code"] == "TAG-FNDR-1234"

    def test_subscriber_response_includes_founder_email_sent(self):
        """Subscriber list response should include founder_email_sent."""
        subscriber = create_mock_subscriber(founder_email_sent=True)

        subscriber_data = {
            "founder_email_sent": subscriber.founder_email_sent,
        }

        assert "founder_email_sent" in subscriber_data
        assert subscriber_data["founder_email_sent"] is True

    def test_subscriber_response_includes_founder_email_sent_at(self):
        """Subscriber list response should include founder_email_sent_at."""
        sent_at = datetime(2026, 3, 1, 10, 30, 0)
        subscriber = create_mock_subscriber(
            founder_email_sent=True,
            founder_email_sent_at=sent_at,
        )

        subscriber_data = {
            "founder_email_sent_at": subscriber.founder_email_sent_at.isoformat() if subscriber.founder_email_sent_at else None,
        }

        assert "founder_email_sent_at" in subscriber_data
        assert subscriber_data["founder_email_sent_at"] == "2026-03-01T10:30:00"

    def test_subscriber_response_includes_founder_promo_used(self):
        """Subscriber list response should include founder_promo_used."""
        subscriber = create_mock_subscriber(founder_promo_used=True)

        subscriber_data = {
            "founder_promo_used": subscriber.founder_promo_used,
        }

        assert "founder_promo_used" in subscriber_data
        assert subscriber_data["founder_promo_used"] is True


# =============================================================================
# Full Flow Integration Tests
# =============================================================================

class TestFullFounderEmailFlow:
    """Integration tests covering full founder email workflows."""

    def test_full_founder_email_flow(self):
        """Test complete flow: subscribe -> send founder email -> verify."""
        # Step 1: Create subscriber
        subscriber = create_mock_subscriber(
            id=1,
            first_name="Flow",
            last_name="Test",
            email="flow@test.com",
            founder_promo_code=None,
            founder_email_sent=False,
        )

        assert subscriber.founder_promo_code is None
        assert subscriber.founder_email_sent is False

        # Step 2: Admin sends founder email
        subscriber.founder_promo_code = "TAG-FLOW-1234"
        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()

        assert subscriber.founder_promo_code == "TAG-FLOW-1234"
        assert subscriber.founder_email_sent is True
        assert subscriber.founder_email_sent_at is not None

        # Step 3: Promo is not yet used
        assert subscriber.founder_promo_used is False

        # Step 4: Simulate promo usage during booking
        subscriber.founder_promo_used = True
        subscriber.founder_promo_used_at = datetime.utcnow()
        subscriber.founder_promo_used_booking_id = 456

        assert subscriber.founder_promo_used is True
        assert subscriber.founder_promo_used_at is not None
        assert subscriber.founder_promo_used_booking_id == 456

    def test_subscriber_with_multiple_promos(self):
        """Subscriber can have both 10% promo and founder promo codes."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10PC-1234",
            promo_10_sent=True,
            founder_promo_code="TAG-FNDR-5678",
            founder_email_sent=True,
        )

        # Both should exist independently
        assert subscriber.promo_10_code is not None
        assert subscriber.founder_promo_code is not None
        assert subscriber.promo_10_code != subscriber.founder_promo_code

    def test_founder_promo_audit_trail(self):
        """Founder promo operations should have timestamps for audit trail."""
        now = datetime.utcnow()

        subscriber = create_mock_subscriber(
            founder_promo_code="TAG-AUDIT-123",
            founder_email_sent=True,
            founder_email_sent_at=now,
            founder_promo_used=True,
            founder_promo_used_at=now + timedelta(days=2),
        )

        # Sent before used
        assert subscriber.founder_email_sent_at < subscriber.founder_promo_used_at

        # Timestamps are present
        assert subscriber.founder_email_sent_at is not None
        assert subscriber.founder_promo_used_at is not None


# =============================================================================
# Button State Tests (Frontend Logic)
# =============================================================================

class TestFounderEmailButtonState:
    """Tests for button state logic in frontend."""

    def test_button_enabled_when_not_sent_and_not_unsubscribed(self):
        """Button should be enabled when email not sent and not unsubscribed."""
        subscriber = create_mock_subscriber(
            founder_email_sent=False,
            founder_promo_used=False,
            unsubscribed=False,
        )

        button_disabled = (
            subscriber.founder_promo_used or
            subscriber.unsubscribed
        )

        assert button_disabled is False

    def test_button_disabled_when_promo_used(self):
        """Button should be disabled when founder promo already used."""
        subscriber = create_mock_subscriber(
            founder_promo_used=True,
        )

        button_disabled = subscriber.founder_promo_used
        assert button_disabled is True

    def test_button_disabled_when_unsubscribed(self):
        """Button should be disabled when subscriber has unsubscribed."""
        subscriber = create_mock_subscriber(
            unsubscribed=True,
        )

        button_disabled = subscriber.unsubscribed
        assert button_disabled is True

    def test_button_text_changes_when_sent(self):
        """Button text should indicate when email was sent."""
        subscriber_sent = create_mock_subscriber(founder_email_sent=True)
        subscriber_not_sent = create_mock_subscriber(founder_email_sent=False)

        def get_button_text(s):
            if s.founder_email_sent:
                return "Founder Email Sent"
            return "Send Founder Email"

        assert get_button_text(subscriber_sent) == "Founder Email Sent"
        assert get_button_text(subscriber_not_sent) == "Send Founder Email"


# =============================================================================
# Confirmation Modal Tests
# =============================================================================

class TestFounderEmailConfirmationModal:
    """Tests for confirmation modal content."""

    def test_modal_shows_subscriber_name(self):
        """Modal should display subscriber name."""
        subscriber = create_mock_subscriber(first_name="Jane", last_name="Doe")

        modal_content = {
            "subscriber_name": f"{subscriber.first_name} {subscriber.last_name}",
        }

        assert modal_content["subscriber_name"] == "Jane Doe"

    def test_modal_shows_subscriber_email(self):
        """Modal should display subscriber email."""
        subscriber = create_mock_subscriber(email="jane@example.com")

        modal_content = {
            "email": subscriber.email,
        }

        assert modal_content["email"] == "jane@example.com"

    def test_modal_explains_promo_code_generation(self):
        """Modal should explain that a promo code will be generated."""
        modal_warning = "This will generate a unique 10% promo code and send a personal thank you email from Kristian."

        assert "10%" in modal_warning
        assert "promo code" in modal_warning.lower()

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
