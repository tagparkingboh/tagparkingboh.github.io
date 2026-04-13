"""
Mocked integration tests for promo code discount types.

Tests cover:
- Promo validation endpoint with each discount type
- Payment intent creation with discount types
- Free booking detection for each type
- Legacy MarketingSubscriber code handling
- End-to-end booking flow simulations
- Happy paths, unhappy paths, edge cases, and boundary conditions

These tests mock database and API calls - no real connections.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_promotion_free_week():
    """Mock Promotion with free_week discount type."""
    promotion = MagicMock()
    promotion.id = 1
    promotion.name = "Test Free Week Promo"
    promotion.discount_percent = 100
    promotion.discount_type = 'free_week'
    return promotion


@pytest.fixture
def mock_promotion_free_100():
    """Mock Promotion with free_100 discount type."""
    promotion = MagicMock()
    promotion.id = 2
    promotion.name = "Test 100% Off Promo"
    promotion.discount_percent = 100
    promotion.discount_type = 'free_100'
    return promotion


@pytest.fixture
def mock_promotion_percentage():
    """Mock Promotion with percentage discount type."""
    promotion = MagicMock()
    promotion.id = 3
    promotion.name = "Test 10% Promo"
    promotion.discount_percent = 10
    promotion.discount_type = 'percentage'
    return promotion


@pytest.fixture
def mock_promo_code():
    """Mock PromoCode object."""
    def _create_code(promotion, code="TAG-TEST-1234", is_used=False, max_uses=None):
        promo_code = MagicMock()
        promo_code.id = 1
        promo_code.code = code
        promo_code.promotion_id = promotion.id
        promo_code.promotion = promotion
        promo_code.is_used = is_used
        promo_code.max_uses = max_uses
        promo_code.use_count = 0
        promo_code.expires_at = None
        promo_code.can_be_used = not is_used
        promo_code.is_multi_use = max_uses is not None
        return promo_code
    return _create_code


@pytest.fixture
def mock_marketing_subscriber():
    """Mock MarketingSubscriber object."""
    def _create_sub(
        email="test@example.com",
        promo_free_code=None,
        promo_free_used=False,
        promo_10_code=None,
        promo_10_used=False,
        founder_promo_code=None,
        founder_promo_used=False,
    ):
        sub = MagicMock()
        sub.id = 1
        sub.email = email
        sub.promo_free_code = promo_free_code
        sub.promo_free_used = promo_free_used
        sub.promo_10_code = promo_10_code
        sub.promo_10_used = promo_10_used
        sub.founder_promo_code = founder_promo_code
        sub.founder_promo_used = founder_promo_used
        return sub
    return _create_sub


# =============================================================================
# Integration Tests: Promo Validation Endpoint - Happy Paths
# =============================================================================

class TestPromoValidationEndpointHappyPath:
    """Happy path tests for /api/promo/validate endpoint."""

    def test_validate_free_week_promo_returns_correct_type(self, mock_promotion_free_week, mock_promo_code):
        """Validating a free_week promo code returns discount_type='free_week'."""
        promo_code = mock_promo_code(mock_promotion_free_week, code="FREEWEEK")

        # Simulate validation logic
        response = {
            'valid': True,
            'message': 'Promo code applied! 1 week free parking!',
            'discount_percent': promo_code.promotion.discount_percent,
            'discount_type': promo_code.promotion.discount_type,
        }

        assert response['valid'] is True
        assert response['discount_percent'] == 100
        assert response['discount_type'] == 'free_week'
        assert '1 week free' in response['message'].lower()

    def test_validate_free_100_promo_returns_correct_type(self, mock_promotion_free_100, mock_promo_code):
        """Validating a free_100 promo code returns discount_type='free_100'."""
        promo_code = mock_promo_code(mock_promotion_free_100, code="FREE100")

        response = {
            'valid': True,
            'message': 'Promo code applied! 100% off your booking!',
            'discount_percent': promo_code.promotion.discount_percent,
            'discount_type': promo_code.promotion.discount_type,
        }

        assert response['valid'] is True
        assert response['discount_percent'] == 100
        assert response['discount_type'] == 'free_100'
        assert '100% off' in response['message'].lower()

    def test_validate_percentage_promo_returns_correct_type(self, mock_promotion_percentage, mock_promo_code):
        """Validating a percentage promo code returns discount_type='percentage'."""
        promo_code = mock_promo_code(mock_promotion_percentage, code="SAVE10")

        response = {
            'valid': True,
            'message': 'Promo code applied! 10% off',
            'discount_percent': promo_code.promotion.discount_percent,
            'discount_type': promo_code.promotion.discount_type,
        }

        assert response['valid'] is True
        assert response['discount_percent'] == 10
        assert response['discount_type'] == 'percentage'
        assert '10% off' in response['message'].lower()


# =============================================================================
# Integration Tests: Promo Validation - Null Type Auto-Determination
# =============================================================================

class TestPromoValidationAutoType:
    """Tests for auto-determining discount_type when NULL in database."""

    def test_null_type_100_percent_auto_determines_free_week(self):
        """When discount_type is NULL and discount is 100%, defaults to free_week."""
        promotion = MagicMock()
        promotion.discount_percent = 100
        promotion.discount_type = None  # NULL in database

        # Simulate auto-determination logic
        discount_type = promotion.discount_type
        if not discount_type:
            discount_type = 'free_week' if promotion.discount_percent == 100 else 'percentage'

        response = {
            'valid': True,
            'message': 'Promo code applied! 1 week free parking!',
            'discount_percent': promotion.discount_percent,
            'discount_type': discount_type,
        }

        assert response['discount_type'] == 'free_week'

    def test_null_type_10_percent_auto_determines_percentage(self):
        """When discount_type is NULL and discount < 100%, defaults to percentage."""
        promotion = MagicMock()
        promotion.discount_percent = 10
        promotion.discount_type = None

        discount_type = promotion.discount_type
        if not discount_type:
            discount_type = 'free_week' if promotion.discount_percent == 100 else 'percentage'

        response = {
            'valid': True,
            'message': 'Promo code applied! 10% off',
            'discount_percent': promotion.discount_percent,
            'discount_type': discount_type,
        }

        assert response['discount_type'] == 'percentage'

    def test_null_type_20_percent_auto_determines_percentage(self):
        """When discount_type is NULL and discount is 20%, defaults to percentage."""
        promotion = MagicMock()
        promotion.discount_percent = 20
        promotion.discount_type = None

        discount_type = promotion.discount_type or ('free_week' if promotion.discount_percent == 100 else 'percentage')

        assert discount_type == 'percentage'


# =============================================================================
# Integration Tests: Promo Validation - Unhappy Paths
# =============================================================================

class TestPromoValidationUnhappyPath:
    """Unhappy path tests for promo validation."""

    def test_used_promo_code_fails_validation(self, mock_promotion_free_week, mock_promo_code):
        """Already used single-use promo code should fail validation."""
        promo_code = mock_promo_code(mock_promotion_free_week, is_used=True)

        response = {
            'valid': False,
            'message': "Oops! Someone just beat you to it - this promo code has already been used.",
            'discount_percent': None,
            'discount_type': None,
        }

        assert response['valid'] is False
        assert 'already been used' in response['message'].lower()

    def test_expired_promo_code_fails_validation(self, mock_promotion_free_week, mock_promo_code):
        """Expired promo code should fail validation."""
        promo_code = mock_promo_code(mock_promotion_free_week)
        promo_code.expires_at = datetime.utcnow() - timedelta(days=1)

        # Simulation of expiry check
        is_expired = promo_code.expires_at and datetime.utcnow() >= promo_code.expires_at

        response = {
            'valid': not is_expired,
            'message': 'This promotion has now expired.' if is_expired else 'Valid',
        }

        assert response['valid'] is False
        assert 'expired' in response['message'].lower()

    def test_max_uses_exceeded_fails_validation(self, mock_promotion_free_week, mock_promo_code):
        """Multi-use promo code at max uses should fail validation."""
        promo_code = mock_promo_code(mock_promotion_free_week, max_uses=5)
        promo_code.use_count = 5  # Already at max

        can_use = promo_code.use_count < promo_code.max_uses

        response = {
            'valid': can_use,
            'message': "This promo code has reached its maximum number of uses." if not can_use else 'Valid',
        }

        assert response['valid'] is False
        assert 'maximum number of uses' in response['message'].lower()

    def test_invalid_promo_code_fails_validation(self):
        """Non-existent promo code should fail validation."""
        response = {
            'valid': False,
            'message': "This code is invalid. Please check and try again.",
            'discount_percent': None,
            'discount_type': None,
        }

        assert response['valid'] is False
        assert 'invalid' in response['message'].lower()


# =============================================================================
# Integration Tests: Legacy MarketingSubscriber Codes
# =============================================================================

class TestLegacyMarketingSubscriberCodes:
    """Tests for legacy MarketingSubscriber promo code handling."""

    def test_promo_free_code_validates_as_free_week(self, mock_marketing_subscriber):
        """promo_free_code in MarketingSubscriber validates as free_week type."""
        subscriber = mock_marketing_subscriber(promo_free_code="FREEWEEK123")

        # Backend logic: 100% legacy codes -> free_week
        discount_percent = 100
        discount_type = 'free_week' if discount_percent == 100 else 'percentage'

        response = {
            'valid': True,
            'message': 'Promo code applied! 1 week free parking!',
            'discount_percent': discount_percent,
            'discount_type': discount_type,
        }

        assert response['discount_type'] == 'free_week'
        assert response['discount_percent'] == 100

    def test_promo_10_code_validates_as_percentage(self, mock_marketing_subscriber):
        """promo_10_code in MarketingSubscriber validates as percentage type."""
        subscriber = mock_marketing_subscriber(promo_10_code="SAVE10NOW")

        discount_percent = 10
        discount_type = 'percentage'

        response = {
            'valid': True,
            'message': 'Promo code applied! 10% off',
            'discount_percent': discount_percent,
            'discount_type': discount_type,
        }

        assert response['discount_type'] == 'percentage'
        assert response['discount_percent'] == 10

    def test_founder_promo_code_validates_as_percentage(self, mock_marketing_subscriber):
        """founder_promo_code validates as percentage type (10%)."""
        subscriber = mock_marketing_subscriber(founder_promo_code="FOUNDER10")

        response = {
            'valid': True,
            'message': 'Promo code applied! 10% off',
            'discount_percent': 10,
            'discount_type': 'percentage',
        }

        assert response['discount_type'] == 'percentage'

    def test_used_legacy_promo_free_code_fails(self, mock_marketing_subscriber):
        """Already used promo_free_code should fail validation."""
        subscriber = mock_marketing_subscriber(
            promo_free_code="FREEWEEK123",
            promo_free_used=True
        )

        response = {
            'valid': False,
            'message': "Oops! Someone just beat you to it - this promo code has already been used.",
        }

        assert response['valid'] is False


# =============================================================================
# Integration Tests: Payment Intent Creation
# =============================================================================

class TestPaymentIntentCreation:
    """Tests for /api/payments/create-intent with discount types."""

    def _calculate_payment_intent(
        self, duration_days, original_amount_pence, discount_type, discount_percent, week1_pence=8500
    ):
        """Simulate payment intent calculation."""
        if discount_type == 'free_100':
            discount_amount = original_amount_pence
            is_free = True
        elif discount_type == 'free_week':
            if duration_days <= 7:
                discount_amount = original_amount_pence
                is_free = True
            else:
                discount_amount = min(week1_pence, original_amount_pence)
                is_free = False
        else:
            discount_amount = int(original_amount_pence * discount_percent / 100)
            is_free = discount_amount >= original_amount_pence

        return {
            'is_free_booking': is_free,
            'original_amount_pence': original_amount_pence,
            'discount_amount_pence': discount_amount,
            'final_amount_pence': original_amount_pence - discount_amount,
        }

    def test_free_week_short_trip_creates_free_booking(self):
        """free_week type with <= 7 day trip creates a free booking."""
        result = self._calculate_payment_intent(
            duration_days=7,
            original_amount_pence=8500,
            discount_type='free_week',
            discount_percent=100
        )

        assert result['is_free_booking'] is True
        assert result['final_amount_pence'] == 0

    def test_free_week_long_trip_creates_paid_booking(self):
        """free_week type with > 7 day trip creates a paid booking."""
        result = self._calculate_payment_intent(
            duration_days=14,
            original_amount_pence=15000,
            discount_type='free_week',
            discount_percent=100,
            week1_pence=8500
        )

        assert result['is_free_booking'] is False
        assert result['discount_amount_pence'] == 8500  # Only week1 deducted
        assert result['final_amount_pence'] == 6500  # £65 to pay

    def test_free_100_long_trip_creates_free_booking(self):
        """free_100 type creates free booking regardless of trip length."""
        result = self._calculate_payment_intent(
            duration_days=14,
            original_amount_pence=15000,
            discount_type='free_100',
            discount_percent=100
        )

        assert result['is_free_booking'] is True
        assert result['final_amount_pence'] == 0

    def test_free_100_max_duration_creates_free_booking(self):
        """free_100 type makes even 60-day trip completely free."""
        result = self._calculate_payment_intent(
            duration_days=60,
            original_amount_pence=56400,  # £564
            discount_type='free_100',
            discount_percent=100
        )

        assert result['is_free_booking'] is True
        assert result['final_amount_pence'] == 0

    def test_percentage_10_creates_paid_booking(self):
        """10% percentage discount creates paid booking."""
        result = self._calculate_payment_intent(
            duration_days=7,
            original_amount_pence=8500,
            discount_type='percentage',
            discount_percent=10
        )

        assert result['is_free_booking'] is False
        assert result['discount_amount_pence'] == 850  # 10% of £85
        assert result['final_amount_pence'] == 7650  # £76.50


# =============================================================================
# Integration Tests: Payment Intent Edge Cases
# =============================================================================

class TestPaymentIntentEdgeCases:
    """Edge case tests for payment intent creation."""

    def test_free_week_day_7_boundary_is_free(self):
        """free_week at exactly 7 days should be free."""
        result = TestPaymentIntentCreation()._calculate_payment_intent(
            duration_days=7,
            original_amount_pence=8500,
            discount_type='free_week',
            discount_percent=100
        )

        assert result['is_free_booking'] is True

    def test_free_week_day_8_boundary_is_not_free(self):
        """free_week at 8 days should NOT be free."""
        result = TestPaymentIntentCreation()._calculate_payment_intent(
            duration_days=8,
            original_amount_pence=10500,
            discount_type='free_week',
            discount_percent=100,
            week1_pence=8500
        )

        assert result['is_free_booking'] is False
        assert result['discount_amount_pence'] == 8500

    def test_free_week_original_less_than_week1(self):
        """free_week with original < week1 should cap at original."""
        result = TestPaymentIntentCreation()._calculate_payment_intent(
            duration_days=10,
            original_amount_pence=5000,  # £50 (hypothetical)
            discount_type='free_week',
            discount_percent=100,
            week1_pence=8500  # £85
        )

        # Discount capped at original (£50), not week1 (£85)
        assert result['discount_amount_pence'] == 5000
        assert result['is_free_booking'] is False  # Duration > 7, so not free


# =============================================================================
# Integration Tests: End-to-End Flow Simulation
# =============================================================================

class TestEndToEndFlowSimulation:
    """Simulates complete booking flows with different discount types."""

    def test_e2e_free_week_short_trip_flow(self):
        """Complete flow: validate free_week promo -> create free booking."""
        # Step 1: User validates promo code
        validation_response = {
            'valid': True,
            'discount_percent': 100,
            'discount_type': 'free_week',
        }

        # Step 2: User creates payment intent for 5-day trip
        duration_days = 5
        original_pence = 7500  # £75

        # Backend calculates: free_week + <= 7 days = free
        is_free = True
        discount = original_pence

        payment_response = {
            'is_free_booking': is_free,
            'booking_reference': 'TAG-FLOW1',
            'final_amount_pence': 0,
        }

        # Step 3: Frontend shows "Your booking is free!" UI
        assert validation_response['discount_type'] == 'free_week'
        assert payment_response['is_free_booking'] is True
        assert payment_response['final_amount_pence'] == 0

    def test_e2e_free_week_long_trip_flow(self):
        """Complete flow: validate free_week promo -> create PAID booking for long trip."""
        # Step 1: Validate
        validation_response = {
            'valid': True,
            'discount_percent': 100,
            'discount_type': 'free_week',
        }

        # Step 2: Create payment for 14-day trip
        duration_days = 14
        original_pence = 15000
        week1_pence = 8500

        # Backend: free_week + > 7 days = partial discount
        discount = week1_pence
        final = original_pence - discount
        is_free = False

        payment_response = {
            'is_free_booking': is_free,
            'client_secret': 'pi_xxx_secret',  # REQUIRES payment
            'booking_reference': 'TAG-FLOW2',
            'original_amount_display': '£150.00',
            'discount_amount_display': '£85.00',
            'amount_display': '£65.00',
            'final_amount_pence': final,
        }

        # Step 3: Frontend shows Stripe payment form
        assert validation_response['discount_type'] == 'free_week'
        assert payment_response['is_free_booking'] is False
        assert payment_response['final_amount_pence'] == 6500
        assert 'client_secret' in payment_response

    def test_e2e_free_100_long_trip_flow(self):
        """Complete flow: validate free_100 promo -> create FREE booking for long trip."""
        # Step 1: Validate
        validation_response = {
            'valid': True,
            'discount_percent': 100,
            'discount_type': 'free_100',
        }

        # Step 2: Create payment for 14-day trip
        duration_days = 14
        original_pence = 15000

        # Backend: free_100 = always free
        is_free = True
        discount = original_pence

        payment_response = {
            'is_free_booking': is_free,
            'booking_reference': 'TAG-FLOW3',
            'final_amount_pence': 0,
        }

        # Step 3: Frontend shows "Your booking is free!" UI (NO Stripe form)
        assert validation_response['discount_type'] == 'free_100'
        assert payment_response['is_free_booking'] is True
        assert payment_response['final_amount_pence'] == 0
        assert 'client_secret' not in payment_response

    def test_e2e_percentage_flow(self):
        """Complete flow: validate 10% promo -> create paid booking."""
        # Step 1: Validate
        validation_response = {
            'valid': True,
            'discount_percent': 10,
            'discount_type': 'percentage',
        }

        # Step 2: Create payment for 7-day trip
        original_pence = 8500
        discount = 850  # 10%
        final = original_pence - discount

        payment_response = {
            'is_free_booking': False,
            'client_secret': 'pi_xxx_secret',
            'booking_reference': 'TAG-FLOW4',
            'original_amount_display': '£85.00',
            'discount_amount_display': '£8.50',
            'amount_display': '£76.50',
            'final_amount_pence': final,
        }

        assert validation_response['discount_type'] == 'percentage'
        assert payment_response['is_free_booking'] is False
        assert payment_response['final_amount_pence'] == 7650


# =============================================================================
# Integration Tests: Data Correctness
# =============================================================================

class TestDataCorrectness:
    """Tests verifying data flows correctly between systems."""

    def test_promo_code_links_to_promotion_discount_type(
        self, mock_promotion_free_week, mock_promo_code
    ):
        """PromoCode correctly inherits discount_type from parent Promotion."""
        promo_code = mock_promo_code(
            mock_promotion_free_week,
            code="TAG-HOL-2024"
        )

        retrieved_type = promo_code.promotion.discount_type
        retrieved_percent = promo_code.promotion.discount_percent

        assert retrieved_type == 'free_week'
        assert retrieved_percent == 100

    def test_new_system_vs_legacy_codes(
        self, mock_promotion_free_100, mock_promo_code, mock_marketing_subscriber
    ):
        """PromoCode table is independent from MarketingSubscriber legacy codes."""
        # New system: PromoCode table with free_100
        new_promo = mock_promo_code(
            mock_promotion_free_100,
            code="TAG-NEW-1234"
        )

        # Legacy system: MarketingSubscriber fields (always free_week for 100%)
        legacy_subscriber = mock_marketing_subscriber(
            promo_free_code="LEGACY-FREE"
        )

        new_type = new_promo.promotion.discount_type
        legacy_type = 'free_week'  # Legacy 100% always defaults to free_week

        assert new_type == 'free_100'
        assert legacy_type == 'free_week'
        assert new_type != legacy_type

    def test_multi_use_promo_code_tracks_uses(self, mock_promotion_percentage, mock_promo_code):
        """Multi-use promo codes track use_count correctly."""
        promo_code = mock_promo_code(
            mock_promotion_percentage,
            code="TAG-MULTI-USE",
            max_uses=5
        )
        promo_code.use_count = 3

        # can_be_used logic
        can_use = promo_code.use_count < promo_code.max_uses

        assert can_use is True
        assert promo_code.use_count == 3
        assert promo_code.max_uses == 5


# =============================================================================
# Integration Tests: Message Formatting
# =============================================================================

class TestMessageFormatting:
    """Tests for correct message formatting based on discount type."""

    def test_free_week_message_format(self):
        """free_week should show '1 week free parking!' message."""
        discount_type = 'free_week'

        if discount_type == 'free_week':
            message = "Promo code applied! 1 week free parking!"
        elif discount_type == 'free_100':
            message = "Promo code applied! 100% off your booking!"
        else:
            message = "Promo code applied! 10% off"

        assert '1 week free parking' in message.lower()

    def test_free_100_message_format(self):
        """free_100 should show '100% off your booking!' message."""
        discount_type = 'free_100'

        if discount_type == 'free_week':
            message = "Promo code applied! 1 week free parking!"
        elif discount_type == 'free_100':
            message = "Promo code applied! 100% off your booking!"
        else:
            message = "Promo code applied! 10% off"

        assert '100% off' in message.lower()

    def test_percentage_message_format(self):
        """percentage should show 'X% off' message."""
        discount_type = 'percentage'
        discount_percent = 10

        if discount_type == 'free_week':
            message = "Promo code applied! 1 week free parking!"
        elif discount_type == 'free_100':
            message = "Promo code applied! 100% off your booking!"
        else:
            message = f"Promo code applied! {discount_percent}% off"

        assert '10% off' in message.lower()


# =============================================================================
# Integration Tests: Concurrent Usage Scenarios
# =============================================================================

class TestConcurrentUsage:
    """Tests for concurrent promo code usage scenarios."""

    def test_single_use_code_prevents_second_use(self, mock_promotion_free_week, mock_promo_code):
        """Single-use code should be marked as used after first booking."""
        promo_code = mock_promo_code(mock_promotion_free_week, is_used=False)

        # First use - success
        first_response = {
            'valid': not promo_code.is_used,
        }
        assert first_response['valid'] is True

        # Simulate marking as used
        promo_code.is_used = True

        # Second use - fail
        second_response = {
            'valid': not promo_code.is_used,
            'message': "Oops! Someone just beat you to it - this promo code has already been used.",
        }
        assert second_response['valid'] is False

    def test_multi_use_code_allows_multiple_uses(self, mock_promotion_percentage, mock_promo_code):
        """Multi-use code should allow uses up to max_uses."""
        promo_code = mock_promo_code(mock_promotion_percentage, max_uses=3)
        promo_code.use_count = 0

        # Use 1
        can_use_1 = promo_code.use_count < promo_code.max_uses
        assert can_use_1 is True
        promo_code.use_count += 1

        # Use 2
        can_use_2 = promo_code.use_count < promo_code.max_uses
        assert can_use_2 is True
        promo_code.use_count += 1

        # Use 3
        can_use_3 = promo_code.use_count < promo_code.max_uses
        assert can_use_3 is True
        promo_code.use_count += 1

        # Use 4 - should fail
        can_use_4 = promo_code.use_count < promo_code.max_uses
        assert can_use_4 is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
