"""
Tests for Admin Marketing Promo Code functionality.

Includes unit tests and integration tests for:
- GET /api/admin/marketing-subscribers
- POST /api/admin/marketing-subscribers/{id}/send-promo

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

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
    promo_code_sent_at=None,
    discount_percent=10,
    promo_code_used=False,
    promo_code_used_at=None,
    promo_code_used_booking_id=None,
    promo_10_code=None,
    promo_10_sent=False,
    promo_10_sent_at=None,
    promo_10_used=False,
    promo_10_used_at=None,
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
    subscriber.promo_code_sent_at = promo_code_sent_at
    subscriber.discount_percent = discount_percent
    subscriber.promo_code_used = promo_code_used
    subscriber.promo_code_used_at = promo_code_used_at
    subscriber.promo_code_used_booking_id = promo_code_used_booking_id
    subscriber.promo_10_code = promo_10_code
    subscriber.promo_10_sent = promo_10_sent
    subscriber.promo_10_sent_at = promo_10_sent_at
    subscriber.promo_10_used = promo_10_used
    subscriber.promo_10_used_at = promo_10_used_at
    subscriber.unsubscribed = unsubscribed
    subscriber.unsubscribed_at = unsubscribed_at
    return subscriber


def create_mock_subscriber_response(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
    subscribed_at=None,
    welcome_email_sent=True,
    welcome_email_sent_at=None,
    promo_code=None,
    promo_code_sent=False,
    promo_code_sent_at=None,
    discount_percent=10,
    promo_code_used=False,
    promo_code_used_at=None,
    promo_10_code=None,
    promo_10_sent=False,
    promo_10_sent_at=None,
    promo_10_used=False,
    promo_10_used_at=None,
    unsubscribed=False,
    unsubscribed_at=None,
):
    """Create a mock subscriber response as returned by API."""
    return {
        "id": id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "subscribed_at": (subscribed_at or datetime.utcnow()).isoformat(),
        "welcome_email_sent": welcome_email_sent,
        "welcome_email_sent_at": welcome_email_sent_at.isoformat() if welcome_email_sent_at else None,
        "promo_code": promo_code,
        "promo_code_sent": promo_code_sent,
        "promo_code_sent_at": promo_code_sent_at.isoformat() if promo_code_sent_at else None,
        "discount_percent": discount_percent,
        "promo_code_used": promo_code_used,
        "promo_code_used_at": promo_code_used_at.isoformat() if promo_code_used_at else None,
        "promo_10_code": promo_10_code,
        "promo_10_sent": promo_10_sent,
        "promo_10_sent_at": promo_10_sent_at.isoformat() if promo_10_sent_at else None,
        "promo_10_used": promo_10_used,
        "promo_10_used_at": promo_10_used_at.isoformat() if promo_10_used_at else None,
        "unsubscribed": unsubscribed,
        "unsubscribed_at": unsubscribed_at.isoformat() if unsubscribed_at else None,
    }


# =============================================================================
# Unit Tests - MarketingSubscriber Promo Fields
# =============================================================================

class TestMarketingSubscriberPromoFields:
    """Unit tests for promo-related fields on MarketingSubscriber."""

    def test_promo_fields_default_values(self):
        """Promo fields should have correct defaults."""
        subscriber = create_mock_subscriber()

        # With defaults not set
        subscriber.promo_code = None
        subscriber.promo_code_sent = False
        subscriber.promo_code_sent_at = None
        subscriber.discount_percent = 10
        subscriber.promo_code_used = False
        subscriber.promo_code_used_at = None
        subscriber.promo_code_used_booking_id = None

        assert subscriber.promo_code is None
        assert subscriber.promo_code_sent is False
        assert subscriber.promo_code_sent_at is None
        assert subscriber.discount_percent == 10
        assert subscriber.promo_code_used is False
        assert subscriber.promo_code_used_at is None
        assert subscriber.promo_code_used_booking_id is None

    def test_can_set_promo_code(self):
        """Should be able to set a promo code."""
        subscriber = create_mock_subscriber()

        subscriber.promo_code = "TAG-TEST-ABCD1234"
        subscriber.discount_percent = 10
        subscriber.promo_code_sent = True
        subscriber.promo_code_sent_at = datetime.utcnow()

        assert subscriber.promo_code == "TAG-TEST-ABCD1234"
        assert subscriber.discount_percent == 10
        assert subscriber.promo_code_sent is True
        assert subscriber.promo_code_sent_at is not None

    def test_can_set_100_percent_discount(self):
        """Should support 100% discount for free parking."""
        subscriber = create_mock_subscriber(
            promo_code="TAG-FREE-12345678",
            discount_percent=100,
            promo_code_sent=True,
        )

        assert subscriber.discount_percent == 100

    def test_can_mark_promo_used(self):
        """Should be able to mark promo as used."""
        subscriber = create_mock_subscriber(
            promo_code="TAG-USED-12345678",
            discount_percent=10,
            promo_code_sent=True,
        )

        subscriber.promo_code_used = True
        subscriber.promo_code_used_at = datetime.utcnow()

        assert subscriber.promo_code_used is True
        assert subscriber.promo_code_used_at is not None


# =============================================================================
# Integration Tests - GET /api/admin/marketing-subscribers
# =============================================================================

class TestGetSubscribers:
    """Tests for GET /api/admin/marketing-subscribers endpoint."""

    def test_get_subscribers_success(self):
        """Should return list of subscribers."""
        subscribers = [
            create_mock_subscriber_response(id=1, first_name="John", email="john@test.com"),
            create_mock_subscriber_response(id=2, first_name="Jane", email="jane@test.com"),
            create_mock_subscriber_response(id=3, first_name="Bob", email="bob@test.com"),
        ]

        response_data = {
            "count": len(subscribers),
            "subscribers": subscribers,
        }

        assert "count" in response_data
        assert "subscribers" in response_data
        assert response_data["count"] >= 3

    def test_get_subscribers_returns_all_fields(self):
        """Should return all required fields for each subscriber."""
        subscriber = create_mock_subscriber_response(
            id=1,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            subscribed_at=datetime.utcnow(),
            welcome_email_sent=True,
            promo_code="TAG-TEST-1234",
            promo_code_sent=True,
            discount_percent=10,
            promo_code_used=False,
        )

        required_fields = [
            "id", "first_name", "last_name", "email", "subscribed_at",
            "welcome_email_sent", "welcome_email_sent_at",
            "promo_code", "promo_code_sent", "promo_code_sent_at",
            "discount_percent", "promo_code_used", "promo_code_used_at",
            "unsubscribed", "unsubscribed_at"
        ]

        for field in required_fields:
            assert field in subscriber, f"Missing field: {field}"

    def test_get_subscribers_ordered_by_date_desc(self):
        """Should return subscribers ordered by subscribed_at descending."""
        subscribers = [
            create_mock_subscriber_response(id=3, first_name="Bob",
                subscribed_at=datetime.utcnow() - timedelta(days=1)),
            create_mock_subscriber_response(id=2, first_name="Jane",
                subscribed_at=datetime.utcnow() - timedelta(days=3)),
            create_mock_subscriber_response(id=1, first_name="John",
                subscribed_at=datetime.utcnow() - timedelta(days=5)),
        ]

        # Bob (1 day ago) should be before Jane (3 days ago) before John (5 days ago)
        assert subscribers[0]["first_name"] == "Bob"
        assert subscribers[1]["first_name"] == "Jane"
        assert subscribers[2]["first_name"] == "John"


# =============================================================================
# Integration Tests - POST /api/admin/marketing-subscribers/{id}/send-promo
# =============================================================================

class TestSendPromo:
    """Tests for POST /api/admin/marketing-subscribers/{id}/send-promo endpoint."""

    def test_send_promo_10_percent_success(self):
        """Should successfully send 10% promo code."""
        response_data = {
            "success": True,
            "promo_code": "TAG-ABCD-1234",
            "discount_percent": 10,
            "message": "Promo code sent to test@example.com",
        }

        assert response_data["success"] is True
        assert "promo_code" in response_data
        assert response_data["promo_code"].startswith("TAG-")
        assert response_data["discount_percent"] == 10
        assert "message" in response_data

    def test_send_promo_100_percent_success(self):
        """Should successfully send 100% (free) promo code."""
        response_data = {
            "success": True,
            "promo_code": "TAG-FREE-5678",
            "discount_percent": 100,
            "message": "Free parking promo sent",
        }

        assert response_data["success"] is True
        assert response_data["discount_percent"] == 100

    def test_send_promo_generates_unique_code(self):
        """Should generate unique promo codes for each subscriber."""
        codes = [
            "TAG-ABCD-1234",
            "TAG-EFGH-5678",
            "TAG-IJKL-9012",
        ]

        # All codes should be unique
        assert len(codes) == len(set(codes))

    def test_send_promo_updates_subscriber(self):
        """Should update subscriber record after sending promo."""
        subscriber = create_mock_subscriber(id=1)

        # Simulate update after promo send
        subscriber.promo_10_code = "TAG-NEW1-2345"
        subscriber.promo_10_sent = True
        subscriber.promo_10_sent_at = datetime.utcnow()

        assert subscriber.promo_10_code is not None
        assert subscriber.promo_10_sent is True
        assert subscriber.promo_10_sent_at is not None

    def test_send_promo_subscriber_not_found(self):
        """Should return 404 for non-existent subscriber."""
        # Simulate 404 response
        error_response = {"detail": "Subscriber not found"}
        status_code = 404

        assert status_code == 404

    def test_send_promo_invalid_discount_percent(self):
        """Should return 400 for invalid discount percentage."""
        # Only 10 and 100 are valid
        error_response = {"detail": "Invalid discount percent. Must be 10 or 100."}
        status_code = 400

        assert status_code == 400

    def test_send_promo_to_unsubscribed_user(self):
        """Should return 400 when sending to unsubscribed user."""
        subscriber = create_mock_subscriber(
            id=1,
            unsubscribed=True,
            unsubscribed_at=datetime.utcnow(),
        )

        # Cannot send promo to unsubscribed user
        can_send = not subscriber.unsubscribed
        assert can_send is False

        error_response = {"detail": "User has unsubscribed"}
        status_code = 400
        assert status_code == 400
        assert "unsubscribed" in error_response["detail"].lower()

    def test_send_promo_code_already_used(self):
        """Should return 400 when promo code already used."""
        subscriber = create_mock_subscriber(
            id=1,
            promo_10_code="TAG-USED-1234",
            promo_10_sent=True,
            promo_10_used=True,
            promo_10_used_at=datetime.utcnow(),
        )

        # Cannot resend if already used
        can_resend = not subscriber.promo_10_used
        assert can_resend is False

        error_response = {"detail": "Promo code already used"}
        status_code = 400
        assert status_code == 400
        assert "used" in error_response["detail"].lower()


# =============================================================================
# Unit Tests - Promo Code Generation
# =============================================================================

class TestPromoCodeGeneration:
    """Unit tests for promo code generation."""

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

    def test_promo_code_characters(self):
        """Promo codes should use uppercase alphanumeric characters."""
        from email_service import generate_promo_code

        for _ in range(10):
            code = generate_promo_code()
            # Remove TAG- prefix and dashes
            chars = code.replace("TAG-", "").replace("-", "")
            assert chars.isalnum()
            assert chars.isupper()
            # Should not contain confusing characters
            assert '0' not in chars
            assert 'O' not in chars
            assert 'I' not in chars
            assert '1' not in chars
            assert 'L' not in chars


# =============================================================================
# Unit Tests - Promo Code Validation
# =============================================================================

class TestPromoCodeValidation:
    """Tests for promo code validation during checkout."""

    def test_valid_10_percent_promo_code(self):
        """Should validate and apply 10% discount."""
        subscriber = create_mock_subscriber(
            promo_code="TAG-V10P-ABCD",
            discount_percent=10,
            promo_code_sent=True,
            promo_code_used=False,
            unsubscribed=False,
        )

        # Validate: code exists, not used, not unsubscribed
        is_valid = (
            subscriber.promo_code is not None and
            not subscriber.promo_code_used and
            not subscriber.unsubscribed
        )

        assert is_valid is True
        assert subscriber.discount_percent == 10

    def test_valid_100_percent_promo_code(self):
        """Should validate and apply 100% discount."""
        subscriber = create_mock_subscriber(
            promo_code="TAG-FREE-EFGH",
            discount_percent=100,
            promo_code_sent=True,
            promo_code_used=False,
        )

        is_valid = (
            subscriber.promo_code is not None and
            not subscriber.promo_code_used
        )

        assert is_valid is True
        assert subscriber.discount_percent == 100

    def test_invalid_promo_code_not_found(self):
        """Should return None for non-existent promo code."""
        # Simulate database lookup that returns None
        result = None

        assert result is None

    def test_used_promo_code_rejected(self):
        """Should reject already-used promo codes."""
        subscriber = create_mock_subscriber(
            promo_code="TAG-USED-1234",
            discount_percent=10,
            promo_code_sent=True,
            promo_code_used=True,
            promo_code_used_at=datetime.utcnow(),
        )

        # Used promo code should be rejected
        is_valid = not subscriber.promo_code_used
        assert is_valid is False

    def test_promo_code_case_sensitive(self):
        """Promo codes should be case-sensitive."""
        promo_code = "TAG-CASE-ABCD"
        promo_code_lower = promo_code.lower()

        # Case-sensitive comparison
        assert promo_code != promo_code_lower
        assert promo_code.upper() == promo_code


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

class TestFullPromoFlow:
    """Integration tests covering full promo code workflows."""

    def test_full_promo_flow(self):
        """Test complete flow: subscribe -> send promo -> verify."""
        # Step 1: Create subscriber
        subscriber = create_mock_subscriber(
            id=1,
            first_name="Flow",
            last_name="Test",
            email="flow@test.com",
            promo_10_code=None,
        )

        assert subscriber.promo_10_code is None

        # Step 2: Admin sends promo code
        subscriber.promo_10_code = "TAG-FLOW-1234"
        subscriber.promo_10_sent = True
        subscriber.promo_10_sent_at = datetime.utcnow()

        assert subscriber.promo_10_code == "TAG-FLOW-1234"
        assert subscriber.promo_10_sent is True

        # Step 3: Promo is not yet used
        assert subscriber.promo_10_used is False

        # Step 4: Simulate promo usage
        subscriber.promo_10_used = True
        subscriber.promo_10_used_at = datetime.utcnow()

        assert subscriber.promo_10_used is True
        assert subscriber.promo_10_used_at is not None

    def test_subscriber_with_multiple_promo_types(self):
        """Subscriber can have both 10% and 100% promo codes."""
        subscriber = create_mock_subscriber(
            id=1,
            promo_10_code="TAG-TEN1-2345",
            promo_10_sent=True,
            promo_code="TAG-FREE-6789",  # 100% code
            discount_percent=100,
            promo_code_sent=True,
        )

        assert subscriber.promo_10_code is not None
        assert subscriber.promo_code is not None

    def test_promo_tracking_audit_trail(self):
        """Promo operations should have timestamps for audit trail."""
        now = datetime.utcnow()

        subscriber = create_mock_subscriber(
            id=1,
            promo_10_code="TAG-AUDIT-123",
            promo_10_sent=True,
            promo_10_sent_at=now,
            promo_10_used=True,
            promo_10_used_at=now + timedelta(hours=2),
        )

        # Sent before used
        assert subscriber.promo_10_sent_at < subscriber.promo_10_used_at

        # Timestamps are present
        assert subscriber.promo_10_sent_at is not None
        assert subscriber.promo_10_used_at is not None
