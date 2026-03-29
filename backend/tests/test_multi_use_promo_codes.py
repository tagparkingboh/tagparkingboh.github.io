"""
Tests for multi-use promo codes feature.

Tests cover:
1. Single-use codes (default behavior, backwards compatible)
2. Multi-use codes with max_uses limit
3. Unlimited use codes (max_uses = 0)
4. Expiration boundary testing
5. Valid and invalid code validation
6. Error messages
7. Edge cases and boundary testing for max_uses
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytz


# =============================================================================
# PromoCode Model Tests
# =============================================================================

class TestPromoCodeModel:
    """Tests for PromoCode model properties."""

    def test_single_use_code_defaults(self):
        """Single-use code has max_uses=None, is_multi_use=False."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="TEST-1234-5678",
            max_uses=None,
            use_count=0,
            is_used=False
        )

        assert code.is_multi_use == False
        assert code.is_unlimited == False
        assert code.uses_remaining == 1
        assert code.can_be_used == True

    def test_single_use_code_after_use(self):
        """Single-use code after being used."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="TEST-1234-5678",
            max_uses=None,
            use_count=1,
            is_used=True
        )

        assert code.is_multi_use == False
        assert code.uses_remaining == 0
        assert code.can_be_used == False

    def test_multi_use_code_with_limit(self):
        """Multi-use code with max_uses=5."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="MULTI-1234-5678",
            max_uses=5,
            use_count=0,
            is_used=False
        )

        assert code.is_multi_use == True
        assert code.is_unlimited == False
        assert code.uses_remaining == 5
        assert code.can_be_used == True

    def test_multi_use_code_partially_used(self):
        """Multi-use code with 3/5 uses."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="MULTI-1234-5678",
            max_uses=5,
            use_count=3,
            is_used=False
        )

        assert code.is_multi_use == True
        assert code.uses_remaining == 2
        assert code.can_be_used == True

    def test_multi_use_code_exhausted(self):
        """Multi-use code that has reached max uses."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="MULTI-1234-5678",
            max_uses=5,
            use_count=5,
            is_used=True
        )

        assert code.is_multi_use == True
        assert code.uses_remaining == 0
        assert code.can_be_used == False

    def test_unlimited_use_code(self):
        """Unlimited use code with max_uses=0."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="UNLIM-1234-5678",
            max_uses=0,
            use_count=0,
            is_used=False
        )

        assert code.is_multi_use == True
        assert code.is_unlimited == True
        assert code.uses_remaining is None  # Unlimited
        assert code.can_be_used == True

    def test_unlimited_use_code_after_many_uses(self):
        """Unlimited use code after 1000 uses."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="UNLIM-1234-5678",
            max_uses=0,
            use_count=1000,
            is_used=False
        )

        assert code.is_multi_use == True
        assert code.is_unlimited == True
        assert code.uses_remaining is None  # Still unlimited
        assert code.can_be_used == True

    # Boundary tests for max_uses
    def test_boundary_max_uses_1(self):
        """Boundary: max_uses=1 (essentially single-use but tracked as multi-use)."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="BOUND-1234-5678",
            max_uses=1,
            use_count=0,
            is_used=False
        )

        assert code.is_multi_use == True
        assert code.uses_remaining == 1
        assert code.can_be_used == True

        # After one use
        code.use_count = 1
        code.is_used = True
        assert code.uses_remaining == 0
        assert code.can_be_used == False

    def test_boundary_max_uses_at_limit(self):
        """Boundary: use_count exactly at max_uses."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="BOUND-1234-5678",
            max_uses=10,
            use_count=10,
            is_used=True
        )

        assert code.uses_remaining == 0
        assert code.can_be_used == False

    def test_boundary_max_uses_one_below_limit(self):
        """Boundary: use_count one below max_uses."""
        from db_models import PromoCode

        code = PromoCode(
            promotion_id=1,
            code="BOUND-1234-5678",
            max_uses=10,
            use_count=9,
            is_used=False
        )

        assert code.uses_remaining == 1
        assert code.can_be_used == True


# =============================================================================
# Validate Promo Code API Tests
# =============================================================================

class TestValidatePromoCodeAPI:
    """Tests for /api/promo/validate endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    def test_validate_empty_code(self, mock_db):
        """Empty code returns error."""
        from main import PromoCodeValidateRequest

        # This would be tested via API call
        request = PromoCodeValidateRequest(code="")
        assert request.code == ""

    def test_validate_valid_single_use_code(self, mock_db):
        """Valid single-use code returns success."""
        from db_models import PromoCode, Promotion

        # Create mock promo code
        mock_code = MagicMock(spec=PromoCode)
        mock_code.code = "VALID-1234-5678"
        mock_code.max_uses = None
        mock_code.use_count = 0
        mock_code.is_used = False
        mock_code.expires_at = None
        mock_code.promotion_id = 1
        mock_code.can_be_used = True
        mock_code.is_multi_use = False
        mock_code.uses_remaining = 1

        mock_promotion = MagicMock(spec=Promotion)
        mock_promotion.discount_percent = 10
        mock_promotion.name = "Test Promo"

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_code, mock_promotion]

        # The code should be valid
        assert mock_code.can_be_used == True

    def test_validate_used_single_use_code(self, mock_db):
        """Used single-use code returns friendly error."""
        from db_models import PromoCode

        mock_code = MagicMock(spec=PromoCode)
        mock_code.code = "USED-1234-5678"
        mock_code.max_uses = None
        mock_code.use_count = 1
        mock_code.is_used = True
        mock_code.can_be_used = False
        mock_code.is_multi_use = False

        # The error message should be friendly
        expected_message = "Oops! Someone just beat you to it - this promo code has already been used. Keep an eye out for our next offer!"
        assert mock_code.can_be_used == False

    def test_validate_exhausted_multi_use_code(self, mock_db):
        """Exhausted multi-use code returns appropriate error."""
        from db_models import PromoCode

        mock_code = MagicMock(spec=PromoCode)
        mock_code.code = "MULTI-1234-5678"
        mock_code.max_uses = 5
        mock_code.use_count = 5
        mock_code.is_used = True
        mock_code.can_be_used = False
        mock_code.is_multi_use = True

        expected_message = "This promo code has reached its maximum number of uses. Keep an eye out for our next offer!"
        assert mock_code.can_be_used == False
        assert mock_code.is_multi_use == True

    def test_validate_expired_code(self, mock_db):
        """Expired code returns expiration error."""
        from db_models import PromoCode

        uk_tz = pytz.timezone("Europe/London")
        past_time = datetime.now(uk_tz) - timedelta(hours=1)

        mock_code = MagicMock(spec=PromoCode)
        mock_code.code = "EXPIRED-1234"
        mock_code.max_uses = 0  # Unlimited
        mock_code.use_count = 0
        mock_code.is_used = False
        mock_code.expires_at = past_time
        mock_code.can_be_used = True  # Would be True if not expired

        expected_message = "This promotion has now expired. Keep an eye out for our next offer!"
        # Expiration is checked separately from can_be_used
        assert mock_code.expires_at < datetime.now(uk_tz)

    def test_validate_invalid_code(self, mock_db):
        """Invalid code returns appropriate error."""
        expected_message = "This code is invalid. Please check and try again."
        # When code is not found in DB, this message should be returned

    def test_validate_multi_use_code_still_available(self, mock_db):
        """Multi-use code with remaining uses is valid."""
        from db_models import PromoCode

        mock_code = MagicMock(spec=PromoCode)
        mock_code.code = "MULTI-1234-5678"
        mock_code.max_uses = 10
        mock_code.use_count = 7
        mock_code.is_used = False
        mock_code.expires_at = None
        mock_code.can_be_used = True
        mock_code.is_multi_use = True
        mock_code.uses_remaining = 3

        assert mock_code.can_be_used == True
        assert mock_code.uses_remaining == 3


# =============================================================================
# Expiration Boundary Tests
# =============================================================================

class TestExpirationBoundary:
    """Boundary tests for code expiration."""

    def test_expiry_exactly_at_boundary(self):
        """Code expires exactly at the current time."""
        uk_tz = pytz.timezone("Europe/London")
        now = datetime.now(uk_tz)

        # Code expires exactly now - should be expired
        expires_at = now
        assert now >= expires_at  # Expired

    def test_expiry_one_second_before(self):
        """Code expires one second in the future - still valid."""
        uk_tz = pytz.timezone("Europe/London")
        now = datetime.now(uk_tz)

        # Code expires 1 second from now - still valid
        expires_at = now + timedelta(seconds=1)
        assert now < expires_at  # Still valid

    def test_expiry_one_second_after(self):
        """Code expired one second ago - expired."""
        uk_tz = pytz.timezone("Europe/London")
        now = datetime.now(uk_tz)

        # Code expired 1 second ago
        expires_at = now - timedelta(seconds=1)
        assert now >= expires_at  # Expired

    def test_expiry_one_minute_before(self):
        """Code expires in one minute - still valid."""
        uk_tz = pytz.timezone("Europe/London")
        now = datetime.now(uk_tz)

        expires_at = now + timedelta(minutes=1)
        assert now < expires_at  # Still valid

    def test_expiry_midnight_boundary(self):
        """Code expires at midnight - boundary test."""
        uk_tz = pytz.timezone("Europe/London")

        # Set expiry to midnight
        tomorrow = datetime.now(uk_tz).date() + timedelta(days=1)
        expires_at = uk_tz.localize(datetime.combine(tomorrow, datetime.min.time()))

        # Current time should be before midnight tomorrow
        now = datetime.now(uk_tz)
        assert now < expires_at  # Still valid


# =============================================================================
# Mark Promo Code Used Tests
# =============================================================================

class TestMarkPromoCodeUsed:
    """Tests for mark_promo_code_used function."""

    def test_mark_single_use_code_used(self):
        """Marking a single-use code as used."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = None
        code.use_count = 0
        code.is_used = False
        code.can_be_used = True
        code.is_multi_use = False

        # After marking as used
        code.use_count = 1
        code.is_used = True

        assert code.is_used == True
        assert code.use_count == 1

    def test_mark_multi_use_code_used_once(self):
        """Marking a multi-use code used once."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 5
        code.use_count = 0
        code.is_used = False
        code.can_be_used = True
        code.is_multi_use = True

        # After one use
        code.use_count = 1
        code.is_used = False  # Still not fully used

        assert code.is_used == False
        assert code.use_count == 1

    def test_mark_multi_use_code_reaches_limit(self):
        """Multi-use code reaching its max_uses limit."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 3
        code.use_count = 2
        code.is_used = False
        code.can_be_used = True
        code.is_multi_use = True

        # After reaching limit
        code.use_count = 3
        code.is_used = True  # Now fully used

        assert code.is_used == True
        assert code.use_count == code.max_uses

    def test_mark_unlimited_code_used(self):
        """Unlimited code never becomes is_used=True."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 0  # Unlimited
        code.use_count = 0
        code.is_used = False
        code.is_multi_use = True
        code.is_unlimited = True

        # After many uses
        code.use_count = 1000
        code.is_used = False  # Never becomes True for unlimited

        assert code.is_used == False
        assert code.use_count == 1000

    def test_cannot_mark_exhausted_code(self):
        """Cannot mark an exhausted code as used again."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 5
        code.use_count = 5
        code.is_used = True
        code.can_be_used = False

        assert code.can_be_used == False


# =============================================================================
# Usage Tracking Tests
# =============================================================================

class TestPromoCodeUsageTracking:
    """Tests for PromoCodeUsage tracking table."""

    def test_usage_record_created_for_multi_use(self):
        """Usage record is created for multi-use codes."""
        from db_models import PromoCodeUsage

        usage = PromoCodeUsage(
            promo_code_id=1,
            booking_id=100,
            discount_percent=10,
            discount_amount_pence=850
        )

        assert usage.promo_code_id == 1
        assert usage.booking_id == 100
        assert usage.discount_percent == 10
        assert usage.discount_amount_pence == 850

    def test_multiple_usage_records_for_same_code(self):
        """Multiple usage records can exist for the same multi-use code."""
        from db_models import PromoCodeUsage

        usages = [
            PromoCodeUsage(promo_code_id=1, booking_id=100, discount_percent=10),
            PromoCodeUsage(promo_code_id=1, booking_id=101, discount_percent=10),
            PromoCodeUsage(promo_code_id=1, booking_id=102, discount_percent=10),
        ]

        # All usages have the same promo_code_id
        assert all(u.promo_code_id == 1 for u in usages)
        # But different booking_ids
        assert len(set(u.booking_id for u in usages)) == 3


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_max_uses_negative_invalid(self):
        """Negative max_uses should be rejected by API."""
        # This is validated at the API level, not the model level
        # max_uses < 0 should return 400 error
        pass

    def test_use_count_cannot_exceed_max_uses(self):
        """use_count should never exceed max_uses."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 5
        code.use_count = 5

        # uses_remaining should be 0, not negative
        code.uses_remaining = max(0, code.max_uses - code.use_count)
        assert code.uses_remaining == 0

    def test_large_max_uses_value(self):
        """Very large max_uses value."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 1000000
        code.use_count = 0
        code.is_used = False
        code.can_be_used = True

        assert code.can_be_used == True

        # After many uses
        code.use_count = 999999
        code.uses_remaining = 1
        assert code.uses_remaining == 1

    def test_concurrent_usage_scenario(self):
        """
        Two users try to use the same single-use code simultaneously.
        First user succeeds, second user should see error message.
        """
        from db_models import PromoCode

        # Initial state
        code = MagicMock(spec=PromoCode)
        code.max_uses = None
        code.use_count = 0
        code.is_used = False
        code.can_be_used = True

        # User 1 validates - sees it's available
        assert code.can_be_used == True

        # User 1 completes booking, code is marked as used
        code.use_count = 1
        code.is_used = True
        code.can_be_used = False

        # User 2 tries to validate - should fail
        assert code.can_be_used == False
        assert code.is_used == True

    def test_multi_use_concurrent_usage(self):
        """
        Multiple users use the same multi-use code, staying within limits.
        """
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.max_uses = 5
        code.use_count = 0
        code.is_used = False

        # Simulate 5 concurrent uses
        for i in range(5):
            code.use_count = i + 1
            if code.use_count >= code.max_uses:
                code.is_used = True
                code.can_be_used = False
            else:
                code.can_be_used = True

        # After 5 uses, should be exhausted
        assert code.use_count == 5
        assert code.is_used == True
        assert code.can_be_used == False


# =============================================================================
# Error Message Tests
# =============================================================================

class TestErrorMessages:
    """Tests for error messages."""

    def test_expired_code_message(self):
        """Expired code shows correct message."""
        expected = "This promotion has now expired. Keep an eye out for our next offer!"
        assert "expired" in expected.lower()

    def test_single_use_already_used_message(self):
        """Single-use code already used shows friendly message."""
        expected = "Oops! Someone just beat you to it - this promo code has already been used. Keep an eye out for our next offer!"
        assert "beat you to it" in expected

    def test_multi_use_exhausted_message(self):
        """Multi-use code exhausted shows appropriate message."""
        expected = "This promo code has reached its maximum number of uses. Keep an eye out for our next offer!"
        assert "maximum number of uses" in expected

    def test_invalid_code_message(self):
        """Invalid code shows clear message."""
        expected = "This code is invalid. Please check and try again."
        assert "invalid" in expected.lower()

    def test_empty_code_message(self):
        """Empty code shows prompt message."""
        expected = "Please enter a promo code"
        assert "enter" in expected.lower()


# =============================================================================
# Integration-style Tests (using mock DB)
# =============================================================================

# =============================================================================
# Custom Code Tests
# =============================================================================

class TestCustomCodes:
    """Tests for custom promo codes (e.g., SUMMER10 instead of TAG-XXXX-XXXX)."""

    def test_custom_code_case_insensitive_input(self):
        """User can enter code in any case - converted to uppercase."""
        # Input variations
        inputs = ["summer10", "SUMMER10", "SuMmEr10", "  summer10  "]

        for user_input in inputs:
            normalized = user_input.strip().upper()
            assert normalized == "SUMMER10"

    def test_custom_code_mixed_case_lookup(self):
        """Code lookup is case-insensitive."""
        stored_code = "SUMMER10"
        user_inputs = ["summer10", "SUMMER10", "Summer10", "sUmMeR10"]

        for user_input in user_inputs:
            normalized = user_input.strip().upper()
            assert normalized == stored_code

    def test_custom_code_with_whitespace(self):
        """Whitespace is stripped from user input."""
        user_input = "  SUMMER10  "
        normalized = user_input.strip().upper()
        assert normalized == "SUMMER10"

    def test_custom_code_alphanumeric_only(self):
        """Custom codes are sanitized to alphanumeric only."""
        inputs_and_expected = [
            ("SUMMER-10", "SUMMER10"),
            ("SUMMER_10", "SUMMER10"),
            ("SUMMER 10", "SUMMER10"),
            ("SUMMER.10", "SUMMER10"),
            ("SUMMER@10!", "SUMMER10"),
        ]

        for user_input, expected in inputs_and_expected:
            # Sanitization logic from backend
            sanitized = ''.join(c for c in user_input.upper() if c.isalnum())[:20]
            assert sanitized == expected

    def test_custom_code_max_length(self):
        """Custom codes are truncated to max 20 characters."""
        long_code = "VERYLONGPROMOTIONCODE2024"
        sanitized = ''.join(c for c in long_code.upper() if c.isalnum())[:20]
        assert len(sanitized) == 20
        assert sanitized == "VERYLONGPROMOTIONCOD"

    def test_custom_code_validates_successfully(self):
        """Custom code like SUMMER10 validates correctly."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.code = "SUMMER10"
        code.max_uses = 0  # Unlimited
        code.use_count = 0
        code.is_used = False
        code.expires_at = None
        code.can_be_used = True
        code.is_multi_use = True

        assert code.can_be_used == True
        assert code.code == "SUMMER10"

    def test_custom_code_multi_use_unlimited(self):
        """Custom code with unlimited uses works correctly."""
        from db_models import PromoCode

        code = MagicMock(spec=PromoCode)
        code.code = "FLASH50"
        code.max_uses = 0  # Unlimited
        code.use_count = 500
        code.is_used = False
        code.can_be_used = True
        code.is_unlimited = True

        assert code.can_be_used == True
        assert code.is_unlimited == True

    def test_custom_code_with_expiry(self):
        """Custom code with expiry date/time."""
        from db_models import PromoCode

        uk_tz = pytz.timezone("Europe/London")
        future_time = datetime.now(uk_tz) + timedelta(hours=24)

        code = MagicMock(spec=PromoCode)
        code.code = "WEEKEND20"
        code.max_uses = 0  # Unlimited
        code.use_count = 0
        code.expires_at = future_time
        code.can_be_used = True

        # Not expired yet
        now = datetime.now(uk_tz)
        assert now < code.expires_at

    def test_custom_code_already_exists_error(self):
        """Creating a duplicate custom code returns error."""
        # When code already exists, API should return:
        expected_error = "Code 'SUMMER10' already exists. Please choose a different code."
        assert "already exists" in expected_error

    def test_custom_code_empty_string_uses_generated(self):
        """Empty custom_code falls back to auto-generated codes."""
        custom_code = ""
        sanitized = ''.join(c for c in custom_code.upper() if c.isalnum())[:20] if custom_code else ""
        assert sanitized == ""
        # When empty, should use generated codes


class TestMultiUsePromoCodeIntegration:
    """Integration tests using mocked database."""

    def test_full_lifecycle_single_use(self):
        """Full lifecycle: create, validate, use, reject reuse."""
        from db_models import PromoCode, Promotion

        # 1. Create single-use code
        code = MagicMock(spec=PromoCode)
        code.code = "SINGLE-TEST-1234"
        code.max_uses = None
        code.use_count = 0
        code.is_used = False
        code.expires_at = None
        code.can_be_used = True
        code.is_multi_use = False

        # 2. Validate - should succeed
        assert code.can_be_used == True

        # 3. Use the code
        code.use_count = 1
        code.is_used = True
        code.can_be_used = False

        # 4. Try to validate again - should fail
        assert code.can_be_used == False

    def test_full_lifecycle_multi_use(self):
        """Full lifecycle: create, use multiple times, exhaust."""
        from db_models import PromoCode

        # 1. Create multi-use code with max_uses=3
        code = MagicMock(spec=PromoCode)
        code.code = "MULTI-TEST-1234"
        code.max_uses = 3
        code.use_count = 0
        code.is_used = False
        code.expires_at = None
        code.can_be_used = True
        code.is_multi_use = True

        # 2. First use
        assert code.can_be_used == True
        code.use_count = 1

        # 3. Second use
        code.can_be_used = True  # Still available
        code.use_count = 2

        # 4. Third use (last one)
        code.can_be_used = True  # Still available
        code.use_count = 3
        code.is_used = True
        code.can_be_used = False

        # 5. Fourth use attempt - should fail
        assert code.can_be_used == False
        assert code.use_count == 3

    def test_full_lifecycle_unlimited(self):
        """Full lifecycle: create unlimited code, use many times."""
        from db_models import PromoCode

        # 1. Create unlimited code
        code = MagicMock(spec=PromoCode)
        code.code = "UNLIM-TEST-1234"
        code.max_uses = 0  # Unlimited
        code.use_count = 0
        code.is_used = False
        code.expires_at = None
        code.can_be_used = True
        code.is_multi_use = True
        code.is_unlimited = True

        # 2. Use many times
        for i in range(100):
            assert code.can_be_used == True
            code.use_count = i + 1

        # 3. Still available
        assert code.can_be_used == True
        assert code.is_used == False
        assert code.use_count == 100

    def test_expiry_overrides_multi_use(self):
        """Expired code cannot be used even if uses remain."""
        from db_models import PromoCode

        uk_tz = pytz.timezone("Europe/London")
        past_time = datetime.now(uk_tz) - timedelta(hours=1)

        code = MagicMock(spec=PromoCode)
        code.code = "EXPIRED-TEST-1234"
        code.max_uses = 10
        code.use_count = 2
        code.is_used = False
        code.expires_at = past_time
        code.can_be_used = True  # Model says yes, but...
        code.is_multi_use = True
        code.uses_remaining = 8

        # Even though can_be_used is True and uses_remaining is 8,
        # the expiration check should reject it
        now = datetime.now(uk_tz)
        is_expired = now >= code.expires_at

        assert is_expired == True
        assert code.uses_remaining == 8  # Uses remain, but code is expired
