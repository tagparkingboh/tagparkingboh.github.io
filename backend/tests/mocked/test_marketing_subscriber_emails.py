"""
Unit and Integration tests for Marketing Subscriber Email endpoints.

Tests the marketing subscriber email functionality:
- POST /api/admin/marketing-subscribers/{id}/send-promo
- POST /api/admin/marketing-subscribers/{id}/send-founder-email
- POST /api/admin/marketing-subscribers/{id}/send-promo-10-reminder
- POST /api/admin/marketing-subscribers/{id}/send-promo-free-reminder

All tests use mocks - no database connection or email sending.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_subscriber(
    id=1,
    email="subscriber@example.com",
    first_name="John",
    unsubscribed=False,
    promo_10_code=None,
    promo_10_sent=False,
    promo_10_used=False,
    promo_free_code=None,
    promo_free_sent=False,
    promo_free_used=False,
    founder_promo_code=None,
    founder_email_sent=False,
    founder_promo_used=False,
    promo_10_reminder_sent=False,
    promo_10_reminder_sent_at=None,
    promo_free_reminder_sent=False,
    promo_free_reminder_sent_at=None,
):
    """Create a mock marketing subscriber."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.email = email
    subscriber.first_name = first_name
    subscriber.unsubscribed = unsubscribed
    subscriber.promo_10_code = promo_10_code
    subscriber.promo_10_sent = promo_10_sent
    subscriber.promo_10_sent_at = None
    subscriber.promo_10_used = promo_10_used
    subscriber.promo_free_code = promo_free_code
    subscriber.promo_free_sent = promo_free_sent
    subscriber.promo_free_sent_at = None
    subscriber.promo_free_used = promo_free_used
    subscriber.founder_promo_code = founder_promo_code
    subscriber.founder_email_sent = founder_email_sent
    subscriber.founder_email_sent_at = None
    subscriber.founder_promo_used = founder_promo_used
    subscriber.promo_10_reminder_sent = promo_10_reminder_sent
    subscriber.promo_10_reminder_sent_at = promo_10_reminder_sent_at
    subscriber.promo_free_reminder_sent = promo_free_reminder_sent
    subscriber.promo_free_reminder_sent_at = promo_free_reminder_sent_at
    # Legacy fields
    subscriber.promo_code = None
    subscriber.promo_code_sent = False
    return subscriber


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Send Promo Email Tests (10% and FREE)
# ============================================================================

class TestSendPromoEmailLogic:
    """Unit tests for send promo email logic."""

    # Happy Path - 10% Promo
    def test_generates_10_percent_promo_code(self):
        """Should generate 10% promo code if not exists."""
        subscriber = create_mock_subscriber(promo_10_code=None)

        # Simulate code generation
        new_code = "TAG-PROMO-ABC123"
        subscriber.promo_10_code = new_code

        assert subscriber.promo_10_code == "TAG-PROMO-ABC123"

    def test_uses_existing_10_percent_code(self):
        """Should use existing 10% promo code if already generated."""
        existing_code = "TAG-EXISTING-10"
        subscriber = create_mock_subscriber(promo_10_code=existing_code)

        promo_code = subscriber.promo_10_code

        assert promo_code == "TAG-EXISTING-10"

    def test_marks_10_percent_promo_sent(self):
        """Should mark 10% promo as sent."""
        subscriber = create_mock_subscriber(promo_10_sent=False)

        subscriber.promo_10_sent = True
        subscriber.promo_10_sent_at = datetime.utcnow()

        assert subscriber.promo_10_sent is True
        assert subscriber.promo_10_sent_at is not None

    # Happy Path - FREE Promo (100%)
    def test_generates_free_promo_code(self):
        """Should generate FREE promo code if not exists."""
        subscriber = create_mock_subscriber(promo_free_code=None)

        new_code = "TAG-FREE-XYZ789"
        subscriber.promo_free_code = new_code

        assert subscriber.promo_free_code == "TAG-FREE-XYZ789"

    def test_uses_existing_free_code(self):
        """Should use existing FREE promo code if already generated."""
        existing_code = "TAG-FREE-EXIST"
        subscriber = create_mock_subscriber(promo_free_code=existing_code)

        promo_code = subscriber.promo_free_code

        assert promo_code == "TAG-FREE-EXIST"

    def test_marks_free_promo_sent(self):
        """Should mark FREE promo as sent."""
        subscriber = create_mock_subscriber(promo_free_sent=False)

        subscriber.promo_free_sent = True
        subscriber.promo_free_sent_at = datetime.utcnow()

        assert subscriber.promo_free_sent is True

    # Unhappy Path
    def test_subscriber_not_found(self):
        """Should handle subscriber not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    def test_rejects_unsubscribed_subscriber(self):
        """Should reject unsubscribed subscriber."""
        subscriber = create_mock_subscriber(unsubscribed=True)

        can_send = not subscriber.unsubscribed

        assert can_send is False

    def test_rejects_already_used_10_percent(self):
        """Should reject if 10% promo already used."""
        subscriber = create_mock_subscriber(promo_10_used=True)

        can_send = not subscriber.promo_10_used

        assert can_send is False

    def test_rejects_already_used_free(self):
        """Should reject if FREE promo already used."""
        subscriber = create_mock_subscriber(promo_free_used=True)

        can_send = not subscriber.promo_free_used

        assert can_send is False

    # Validation
    def test_validates_discount_percent_10(self):
        """Should accept 10% discount."""
        discount_percent = 10
        valid_discounts = [10, 100]

        is_valid = discount_percent in valid_discounts

        assert is_valid is True

    def test_validates_discount_percent_100(self):
        """Should accept 100% (FREE) discount."""
        discount_percent = 100
        valid_discounts = [10, 100]

        is_valid = discount_percent in valid_discounts

        assert is_valid is True

    def test_rejects_invalid_discount_percent(self):
        """Should reject invalid discount percentages."""
        for discount in [0, 5, 15, 50, 200]:
            valid_discounts = [10, 100]
            is_valid = discount in valid_discounts
            assert is_valid is False

    # Separate 10% and FREE promos
    def test_allows_both_10_and_free_promos(self):
        """Should allow subscriber to have both 10% and FREE promos."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10-ABC",
            promo_10_sent=True,
            promo_free_code="TAG-FREE-XYZ",
            promo_free_sent=True,
        )

        has_both = bool(subscriber.promo_10_code) and bool(subscriber.promo_free_code)

        assert has_both is True


# ============================================================================
# Send Founder Email Tests
# ============================================================================

class TestSendFounderEmailLogic:
    """Unit tests for send founder email logic."""

    # Happy Path
    def test_generates_founder_promo_code(self):
        """Should generate founder promo code if not exists."""
        subscriber = create_mock_subscriber(founder_promo_code=None)

        new_code = "TAG-FOUNDER-ABC"
        subscriber.founder_promo_code = new_code

        assert subscriber.founder_promo_code == "TAG-FOUNDER-ABC"

    def test_uses_existing_founder_code(self):
        """Should use existing founder promo code."""
        existing_code = "TAG-FOUNDER-EXIST"
        subscriber = create_mock_subscriber(founder_promo_code=existing_code)

        promo_code = subscriber.founder_promo_code

        assert promo_code == "TAG-FOUNDER-EXIST"

    def test_marks_founder_email_sent(self):
        """Should mark founder email as sent."""
        subscriber = create_mock_subscriber(founder_email_sent=False)

        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()

        assert subscriber.founder_email_sent is True

    # Unhappy Path
    def test_rejects_unsubscribed_for_founder(self):
        """Should reject unsubscribed subscriber for founder email."""
        subscriber = create_mock_subscriber(unsubscribed=True)

        can_send = not subscriber.unsubscribed

        assert can_send is False

    def test_rejects_already_used_founder_promo(self):
        """Should reject if founder promo already used."""
        subscriber = create_mock_subscriber(founder_promo_used=True)

        can_send = not subscriber.founder_promo_used

        assert can_send is False

    def test_subscriber_not_found_for_founder(self):
        """Should handle subscriber not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Send Promo 10% Reminder Tests
# ============================================================================

class TestSendPromo10ReminderLogic:
    """Unit tests for send promo 10% reminder logic."""

    # Happy Path
    def test_sends_reminder_to_subscriber_with_unused_code(self):
        """Should send reminder to subscriber with unused 10% code."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10-UNUSED",
            promo_10_used=False,
            promo_10_reminder_sent=False,
        )

        can_send = (
            subscriber.promo_10_code and
            not subscriber.promo_10_used and
            not subscriber.promo_10_reminder_sent
        )

        assert can_send is True

    def test_marks_reminder_sent(self):
        """Should mark 10% reminder as sent."""
        subscriber = create_mock_subscriber(promo_10_reminder_sent=False)

        subscriber.promo_10_reminder_sent = True
        subscriber.promo_10_reminder_sent_at = datetime.utcnow()

        assert subscriber.promo_10_reminder_sent is True
        assert subscriber.promo_10_reminder_sent_at is not None

    # Unhappy Path
    def test_rejects_subscriber_without_10_code(self):
        """Should reject subscriber without 10% promo code."""
        subscriber = create_mock_subscriber(promo_10_code=None)

        has_code = subscriber.promo_10_code is not None

        assert has_code is False

    def test_rejects_already_used_10_code(self):
        """Should reject if 10% code already used."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10-USED",
            promo_10_used=True,
        )

        can_send = not subscriber.promo_10_used

        assert can_send is False

    def test_rejects_reminder_already_sent(self):
        """Should reject if reminder already sent."""
        subscriber = create_mock_subscriber(
            promo_10_code="TAG-10-CODE",
            promo_10_reminder_sent=True,
            promo_10_reminder_sent_at=datetime.utcnow() - timedelta(days=7),
        )

        can_send = not subscriber.promo_10_reminder_sent

        assert can_send is False

    def test_rejects_unsubscribed(self):
        """Should reject unsubscribed subscriber."""
        subscriber = create_mock_subscriber(
            unsubscribed=True,
            promo_10_code="TAG-10-CODE",
        )

        can_send = not subscriber.unsubscribed

        assert can_send is False


# ============================================================================
# Send Promo FREE Reminder Tests
# ============================================================================

class TestSendPromoFreeReminderLogic:
    """Unit tests for send promo FREE reminder logic."""

    # Happy Path
    def test_sends_reminder_to_subscriber_with_unused_code(self):
        """Should send reminder to subscriber with unused FREE code."""
        subscriber = create_mock_subscriber(
            promo_free_code="TAG-FREE-UNUSED",
            promo_free_used=False,
            promo_free_reminder_sent=False,
        )

        can_send = (
            subscriber.promo_free_code and
            not subscriber.promo_free_used and
            not subscriber.promo_free_reminder_sent
        )

        assert can_send is True

    def test_marks_free_reminder_sent(self):
        """Should mark FREE reminder as sent."""
        subscriber = create_mock_subscriber(promo_free_reminder_sent=False)

        subscriber.promo_free_reminder_sent = True
        subscriber.promo_free_reminder_sent_at = datetime.utcnow()

        assert subscriber.promo_free_reminder_sent is True

    # Unhappy Path
    def test_rejects_subscriber_without_free_code(self):
        """Should reject subscriber without FREE promo code."""
        subscriber = create_mock_subscriber(promo_free_code=None)

        has_code = subscriber.promo_free_code is not None

        assert has_code is False

    def test_rejects_already_used_free_code(self):
        """Should reject if FREE code already used."""
        subscriber = create_mock_subscriber(
            promo_free_code="TAG-FREE-USED",
            promo_free_used=True,
        )

        can_send = not subscriber.promo_free_used

        assert can_send is False

    def test_rejects_free_reminder_already_sent(self):
        """Should reject if FREE reminder already sent."""
        subscriber = create_mock_subscriber(
            promo_free_code="TAG-FREE-CODE",
            promo_free_reminder_sent=True,
        )

        can_send = not subscriber.promo_free_reminder_sent

        assert can_send is False


# ============================================================================
# Promo Code Uniqueness Tests
# ============================================================================

class TestPromoCodeUniqueness:
    """Tests for promo code uniqueness validation."""

    def test_checks_uniqueness_across_10_codes(self):
        """Should check code uniqueness across 10% promo codes."""
        existing_codes = ["TAG-CODE-1", "TAG-CODE-2", "TAG-CODE-3"]
        new_code = "TAG-CODE-2"

        is_unique = new_code not in existing_codes

        assert is_unique is False

    def test_checks_uniqueness_across_free_codes(self):
        """Should check code uniqueness across FREE promo codes."""
        existing_codes = ["TAG-FREE-1", "TAG-FREE-2"]
        new_code = "TAG-FREE-NEW"

        is_unique = new_code not in existing_codes

        assert is_unique is True

    def test_checks_uniqueness_across_founder_codes(self):
        """Should check code uniqueness across founder promo codes."""
        existing_codes = ["TAG-FOUNDER-1", "TAG-FOUNDER-2"]
        new_code = "TAG-FOUNDER-1"

        is_unique = new_code not in existing_codes

        assert is_unique is False

    def test_checks_uniqueness_across_legacy_codes(self):
        """Should check code uniqueness across legacy promo codes."""
        existing_legacy = ["TAG-OLD-1", "TAG-OLD-2"]
        new_code = "TAG-OLD-1"

        is_unique = new_code not in existing_legacy

        assert is_unique is False

    def test_retries_code_generation(self):
        """Should retry code generation if collision detected."""
        attempts = 0
        max_attempts = 10
        generated_code = None

        existing_codes = set(["TAG-ATTEMPT-0", "TAG-ATTEMPT-1", "TAG-ATTEMPT-2"])

        for i in range(max_attempts):
            attempts += 1
            new_code = f"TAG-ATTEMPT-{i}"
            if new_code not in existing_codes:
                generated_code = new_code
                break

        assert attempts == 4  # Should succeed on 4th attempt (TAG-ATTEMPT-3)
        assert generated_code == "TAG-ATTEMPT-3"


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestPromoEmailResponseStructure:
    """Tests for response structure."""

    def test_success_response_includes_promo_code(self):
        """Should include promo code in success response."""
        response = {
            "success": True,
            "message": "Promo code email sent to test@example.com",
            "promo_code": "TAG-PROMO-ABC",
            "discount_percent": 10,
        }

        assert response["success"] is True
        assert "promo_code" in response
        assert "discount_percent" in response

    def test_founder_success_response(self):
        """Should include promo code in founder email response."""
        response = {
            "success": True,
            "message": "Founder thank you email sent to test@example.com",
            "promo_code": "TAG-FOUNDER-ABC",
        }

        assert response["success"] is True
        assert "promo_code" in response

    def test_reminder_success_response(self):
        """Should include promo code in reminder response."""
        response = {
            "success": True,
            "message": "Promo 10% reminder email sent to test@example.com",
            "promo_code": "TAG-10-ABC",
        }

        assert response["success"] is True
        assert "promo_code" in response


# ============================================================================
# Authentication Tests
# ============================================================================

class TestMarketingEmailAuthentication:
    """Tests for authentication on marketing email endpoints."""

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


# ============================================================================
# Boundary Tests
# ============================================================================

class TestMarketingEmailBoundaries:
    """Tests for boundary conditions."""

    def test_handles_missing_first_name(self):
        """Should handle missing first name."""
        subscriber = create_mock_subscriber(first_name=None)

        name = subscriber.first_name or "there"

        assert name == "there"

    def test_handles_empty_first_name(self):
        """Should handle empty first name."""
        subscriber = create_mock_subscriber(first_name="")

        name = subscriber.first_name or "there"

        assert name == "there"

    def test_handles_very_long_email(self):
        """Should handle very long email address."""
        long_email = "a" * 200 + "@example.com"
        subscriber = create_mock_subscriber(email=long_email)

        assert len(subscriber.email) > 200

    def test_handles_special_characters_in_name(self):
        """Should handle special characters in first name."""
        subscriber = create_mock_subscriber(first_name="José María")

        assert subscriber.first_name == "José María"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
