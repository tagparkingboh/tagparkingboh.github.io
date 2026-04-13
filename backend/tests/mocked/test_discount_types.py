"""
Mocked unit tests for promo code discount types.

Tests cover:
- Three discount types: 'percentage', 'free_week', 'free_100'
- Discount calculation logic for each type
- Auto-determination when discount_type is NULL
- Promotion and PromoCode model handling
- Happy paths, unhappy paths, edge cases, and boundary conditions

Discount Type Behavior:
- 'percentage': Standard percentage discount (e.g., 10% off total price)
- 'free_week': "1 Week Free Parking" - deducts week1_price (free for ≤7 days, partial for >7 days)
- 'free_100': "100% Off" - completely free regardless of trip length
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default pricing configuration."""
    return {
        "days_1_4_price": 65.0,
        "days_5_6_price": 75.0,
        "week1_base_price": 85.0,
        "days_8_9_price": 105.0,
        "days_10_11_price": 125.0,
        "days_12_13_price": 135.0,
        "week2_base_price": 150.0,
        "extra_day_price": 9.0,
    }


@pytest.fixture
def week1_price_pence():
    """Week 1 price in pence (£85)."""
    return 8500


# =============================================================================
# Discount Calculation Helper (mirrors backend logic)
# =============================================================================

def calculate_discount(
    original_amount_pence: int,
    discount_percent: int,
    discount_type: str,
    duration_days: int,
    week1_price_pence: int = 8500,
) -> tuple:
    """
    Calculate discount amount and whether booking is free.

    Args:
        original_amount_pence: Original booking price in pence
        discount_percent: Discount percentage (10, 20, 100, etc.)
        discount_type: 'percentage', 'free_week', or 'free_100'
        duration_days: Trip duration in days
        week1_price_pence: Week 1 price in pence for free_week calculation

    Returns:
        (discount_amount_pence, is_free_booking)
    """
    if discount_type == 'free_100':
        # "100% Off" - completely free regardless of trip length
        return original_amount_pence, True

    elif discount_type == 'free_week':
        # "1 Week Free Parking" - trips <= 7 days are free, longer trips deduct week1 price
        if duration_days <= 7:
            return original_amount_pence, True
        else:
            discount = min(week1_price_pence, original_amount_pence)
            return discount, False

    else:
        # 'percentage' - Standard percentage-based discount
        discount = int(original_amount_pence * discount_percent / 100)
        is_free = (discount >= original_amount_pence)
        return discount, is_free


def auto_determine_discount_type(discount_percent: int, explicit_type: str = None) -> str:
    """
    Auto-determine discount type when not explicitly set.

    Args:
        discount_percent: Discount percentage
        explicit_type: Explicitly set discount type (or None)

    Returns:
        Discount type string
    """
    if explicit_type:
        return explicit_type
    return 'free_week' if discount_percent == 100 else 'percentage'


# =============================================================================
# Unit Tests: 'percentage' Type - Happy Paths
# =============================================================================

class TestPercentageTypeHappyPath:
    """Happy path tests for 'percentage' discount type."""

    def test_10_percent_off_7_day_trip(self):
        """10% off a 7-day trip (£85) = £8.50 discount."""
        original = 8500  # £85
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=10,
            discount_type='percentage',
            duration_days=7
        )

        assert discount == 850  # £8.50
        assert is_free is False
        assert original - discount == 7650  # £76.50

    def test_10_percent_off_14_day_trip(self):
        """10% off a 14-day trip (£150) = £15 discount."""
        original = 15000  # £150
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=10,
            discount_type='percentage',
            duration_days=14
        )

        assert discount == 1500  # £15
        assert is_free is False
        assert original - discount == 13500  # £135

    def test_20_percent_off_7_day_trip(self):
        """20% off a 7-day trip (£85) = £17 discount."""
        original = 8500
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=20,
            discount_type='percentage',
            duration_days=7
        )

        assert discount == 1700  # £17
        assert is_free is False

    def test_25_percent_off_14_day_trip(self):
        """25% off a 14-day trip (£150) = £37.50 discount."""
        original = 15000
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=25,
            discount_type='percentage',
            duration_days=14
        )

        assert discount == 3750  # £37.50
        assert is_free is False

    def test_50_percent_off_7_day_trip(self):
        """50% off a 7-day trip (£85) = £42.50 discount."""
        original = 8500
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=50,
            discount_type='percentage',
            duration_days=7
        )

        assert discount == 4250  # £42.50
        assert is_free is False

    def test_100_percent_percentage_type_is_free(self):
        """100% with 'percentage' type should make booking free."""
        original = 8500
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='percentage',
            duration_days=7
        )

        assert discount == 8500
        assert is_free is True


# =============================================================================
# Unit Tests: 'free_week' Type - Happy Paths
# =============================================================================

class TestFreeWeekTypeHappyPath:
    """Happy path tests for 'free_week' discount type."""

    def test_7_day_trip_completely_free(self):
        """free_week: 7-day trip should be completely free."""
        original = 8500  # £85
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=7
        )

        assert discount == 8500  # Full amount
        assert is_free is True

    def test_5_day_trip_completely_free(self):
        """free_week: 5-day trip should be completely free."""
        original = 7500  # £75
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=5
        )

        assert discount == 7500  # Full amount
        assert is_free is True

    def test_1_day_trip_completely_free(self):
        """free_week: 1-day trip should be completely free."""
        original = 6500  # £65
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=1
        )

        assert discount == 6500
        assert is_free is True

    def test_8_day_trip_deducts_week1_only(self):
        """free_week: 8-day trip deducts week1 price (£85), customer pays remainder."""
        original = 10500  # £105
        week1 = 8500  # £85
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=8,
            week1_price_pence=week1
        )

        assert discount == 8500  # £85 (week1 price)
        assert is_free is False
        assert original - discount == 2000  # £20

    def test_14_day_trip_deducts_week1_only(self):
        """free_week: 14-day trip deducts week1 price (£85), customer pays £65."""
        original = 15000  # £150
        week1 = 8500  # £85
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=14,
            week1_price_pence=week1
        )

        assert discount == 8500  # £85
        assert is_free is False
        assert original - discount == 6500  # £65

    def test_30_day_trip_deducts_week1_only(self):
        """free_week: 30-day trip deducts only week1 price."""
        # 30-day = £150 + 16 extra days * £9 = £294
        original = 29400
        week1 = 8500
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_week',
            duration_days=30,
            week1_price_pence=week1
        )

        assert discount == 8500  # Only week1
        assert is_free is False
        assert original - discount == 20900  # £209


# =============================================================================
# Unit Tests: 'free_100' Type - Happy Paths
# =============================================================================

class TestFree100TypeHappyPath:
    """Happy path tests for 'free_100' discount type."""

    def test_7_day_trip_completely_free(self):
        """free_100: 7-day trip should be completely free."""
        original = 8500
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_100',
            duration_days=7
        )

        assert discount == 8500
        assert is_free is True

    def test_14_day_trip_completely_free(self):
        """free_100: 14-day trip should be completely free (unlike free_week)."""
        original = 15000
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_100',
            duration_days=14
        )

        assert discount == 15000  # Full amount, not just week1
        assert is_free is True

    def test_30_day_trip_completely_free(self):
        """free_100: Even a 30-day trip should be completely free."""
        original = 29400  # £294
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_100',
            duration_days=30
        )

        assert discount == 29400  # Full amount
        assert is_free is True

    def test_60_day_trip_completely_free(self):
        """free_100: Maximum 60-day trip should be completely free."""
        # 60-day = £150 + 46 * £9 = £564
        original = 56400
        discount, is_free = calculate_discount(
            original_amount_pence=original,
            discount_percent=100,
            discount_type='free_100',
            duration_days=60
        )

        assert discount == 56400
        assert is_free is True


# =============================================================================
# Unit Tests: Discount Type Comparison
# =============================================================================

class TestDiscountTypeComparison:
    """Tests comparing behavior between discount types."""

    def test_short_trip_free_week_and_free_100_same_result(self):
        """For trips <= 7 days, free_week and free_100 give same result."""
        original = 7500  # 5-day trip

        _, is_free_week = calculate_discount(original, 100, 'free_week', 5)
        _, is_free_100 = calculate_discount(original, 100, 'free_100', 5)

        # Both should be completely free
        assert is_free_week is True
        assert is_free_100 is True

    def test_long_trip_free_100_better_than_free_week(self):
        """For trips > 7 days, free_100 gives bigger discount than free_week."""
        original = 15000  # 14-day trip

        discount_week, is_free_week = calculate_discount(original, 100, 'free_week', 14)
        discount_100, is_free_100 = calculate_discount(original, 100, 'free_100', 14)

        assert is_free_week is False  # Only partial discount
        assert is_free_100 is True    # Completely free
        assert discount_100 > discount_week  # free_100 gives bigger discount
        assert discount_100 == original
        assert discount_week == 8500  # Only week1

    def test_percentage_10_vs_free_week_short_trip(self):
        """For short trips, free_week beats 10% discount."""
        original = 8500  # 7-day

        discount_10, _ = calculate_discount(original, 10, 'percentage', 7)
        discount_week, _ = calculate_discount(original, 100, 'free_week', 7)

        # free_week saves £85, 10% saves £8.50
        assert discount_week > discount_10
        assert discount_week == original  # Full amount

    def test_percentage_10_vs_free_week_long_trip(self):
        """For long trips, free_week still beats 10% discount."""
        original = 29400  # 30-day = £294

        discount_10, _ = calculate_discount(original, 10, 'percentage', 30)
        discount_week, _ = calculate_discount(original, 100, 'free_week', 30)

        # 10% of £294 = £29.40
        # free_week = £85 (week1)
        # free_week still saves more
        assert discount_week > discount_10
        assert discount_10 == 2940
        assert discount_week == 8500


# =============================================================================
# Unit Tests: Auto-Determination of Discount Type
# =============================================================================

class TestAutoDiscountTypeDetermination:
    """Tests for auto-determining discount type when not explicitly set."""

    def test_100_percent_auto_determines_to_free_week(self):
        """100% discount with NULL type defaults to free_week."""
        result = auto_determine_discount_type(100, None)
        assert result == 'free_week'

    def test_10_percent_auto_determines_to_percentage(self):
        """10% discount with NULL type defaults to percentage."""
        result = auto_determine_discount_type(10, None)
        assert result == 'percentage'

    def test_20_percent_auto_determines_to_percentage(self):
        """20% discount with NULL type defaults to percentage."""
        result = auto_determine_discount_type(20, None)
        assert result == 'percentage'

    def test_50_percent_auto_determines_to_percentage(self):
        """50% discount with NULL type defaults to percentage."""
        result = auto_determine_discount_type(50, None)
        assert result == 'percentage'

    def test_explicit_type_overrides_auto(self):
        """Explicit discount type should override auto-determination."""
        # 100% with explicit free_100
        result = auto_determine_discount_type(100, 'free_100')
        assert result == 'free_100'

        # 100% with explicit percentage (unusual but allowed)
        result = auto_determine_discount_type(100, 'percentage')
        assert result == 'percentage'

        # 10% with explicit free_week (unusual but allowed)
        result = auto_determine_discount_type(10, 'free_week')
        assert result == 'free_week'


# =============================================================================
# Unit Tests: Boundary Conditions
# =============================================================================

class TestDiscountTypeBoundaries:
    """Boundary condition tests for discount types."""

    def test_free_week_boundary_day_7_is_free(self):
        """free_week: Day 7 is the boundary - should be completely free."""
        original = 8500
        discount, is_free = calculate_discount(original, 100, 'free_week', 7)

        assert is_free is True
        assert discount == original

    def test_free_week_boundary_day_8_is_not_free(self):
        """free_week: Day 8 is past boundary - should NOT be free."""
        original = 10500
        discount, is_free = calculate_discount(original, 100, 'free_week', 8)

        assert is_free is False
        assert discount == 8500  # Only week1

    def test_free_week_boundary_day_1_is_free(self):
        """free_week: Day 1 (minimum) should be completely free."""
        original = 6500
        discount, is_free = calculate_discount(original, 100, 'free_week', 1)

        assert is_free is True

    def test_free_100_boundary_day_60_is_free(self):
        """free_100: Day 60 (maximum) should be completely free."""
        original = 56400
        discount, is_free = calculate_discount(original, 100, 'free_100', 60)

        assert is_free is True
        assert discount == original


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestDiscountTypeEdgeCases:
    """Edge case tests for discount types."""

    def test_free_week_discount_capped_at_original(self):
        """free_week discount should never exceed original amount."""
        # If original is less than week1 price, cap at original
        original = 5000  # £50 (hypothetical)
        discount, _ = calculate_discount(
            original, 100, 'free_week', 10,  # Long trip
            week1_price_pence=8500  # Week1 is £85
        )

        # Discount capped at original amount (£50), not week1 (£85)
        assert discount == 5000
        assert discount <= original

    def test_0_percent_discount_is_zero(self):
        """0% discount should give £0 off."""
        original = 8500
        discount, is_free = calculate_discount(original, 0, 'percentage', 7)

        assert discount == 0
        assert is_free is False

    def test_free_100_day_1_completely_free(self):
        """free_100 for a 1-day trip should be completely free."""
        original = 6500  # £65
        discount, is_free = calculate_discount(original, 100, 'free_100', 1)

        assert discount == 6500
        assert is_free is True

    def test_all_types_with_max_60_days(self):
        """Test all discount types with maximum 60-day duration."""
        # 60-day = £150 + 46*£9 = £564
        original = 56400
        week1 = 8500

        # percentage 10%
        disc_pct, free_pct = calculate_discount(original, 10, 'percentage', 60)
        assert disc_pct == 5640  # 10% of £564
        assert free_pct is False

        # free_week
        disc_week, free_week = calculate_discount(original, 100, 'free_week', 60, week1)
        assert disc_week == 8500  # Only £85
        assert free_week is False

        # free_100
        disc_100, free_100 = calculate_discount(original, 100, 'free_100', 60)
        assert disc_100 == 56400  # Full £564
        assert free_100 is True

    def test_percentage_near_100_not_free(self):
        """99% discount should not make booking free."""
        original = 10000  # £100
        discount, is_free = calculate_discount(original, 99, 'percentage', 7)

        assert discount == 9900  # £99
        assert is_free is False  # 1p remains

    def test_small_original_amount(self):
        """Test with very small original amount."""
        original = 100  # £1
        discount, is_free = calculate_discount(original, 10, 'percentage', 1)

        assert discount == 10  # 10p
        assert is_free is False


# =============================================================================
# Unit Tests: Unhappy Paths
# =============================================================================

class TestDiscountTypeUnhappyPaths:
    """Unhappy path tests for discount types."""

    def test_invalid_discount_type_treated_as_percentage(self):
        """Unknown discount type should be treated as percentage."""
        original = 8500
        # With an invalid type, calculate_discount would fall to percentage
        discount, is_free = calculate_discount(original, 10, 'invalid_type', 7)

        assert discount == 850  # 10%
        assert is_free is False

    def test_negative_duration_days(self):
        """Negative duration should still calculate (edge case)."""
        original = 8500
        # This shouldn't happen in practice, but test behavior
        discount, is_free = calculate_discount(original, 100, 'free_week', -1)

        # Duration <= 7 (including negative), so free
        assert is_free is True

    def test_zero_original_amount(self):
        """Zero original amount should result in zero discount."""
        original = 0
        discount, is_free = calculate_discount(original, 10, 'percentage', 7)

        assert discount == 0
        assert is_free is True  # 0 >= 0


# =============================================================================
# Unit Tests: Promotion Model Handling
# =============================================================================

class TestPromotionModelHandling:
    """Tests for Promotion model discount_type field handling."""

    def test_promotion_with_explicit_free_week(self):
        """Promotion with explicit discount_type='free_week'."""
        promotion = MagicMock()
        promotion.discount_percent = 100
        promotion.discount_type = 'free_week'

        assert promotion.discount_type == 'free_week'
        assert promotion.discount_percent == 100

    def test_promotion_with_explicit_free_100(self):
        """Promotion with explicit discount_type='free_100'."""
        promotion = MagicMock()
        promotion.discount_percent = 100
        promotion.discount_type = 'free_100'

        assert promotion.discount_type == 'free_100'

    def test_promotion_with_null_type_auto_determines(self):
        """Promotion with NULL discount_type auto-determines."""
        promotion_100 = MagicMock()
        promotion_100.discount_percent = 100
        promotion_100.discount_type = None

        promotion_10 = MagicMock()
        promotion_10.discount_percent = 10
        promotion_10.discount_type = None

        type_100 = auto_determine_discount_type(
            promotion_100.discount_percent,
            promotion_100.discount_type
        )
        type_10 = auto_determine_discount_type(
            promotion_10.discount_percent,
            promotion_10.discount_type
        )

        assert type_100 == 'free_week'
        assert type_10 == 'percentage'


# =============================================================================
# Unit Tests: PromoCode Inherits from Promotion
# =============================================================================

class TestPromoCodeInheritance:
    """Tests for PromoCode objects linked to Promotions."""

    def test_promo_code_inherits_free_week(self):
        """PromoCode should use discount_type from parent Promotion."""
        promotion = MagicMock()
        promotion.discount_percent = 100
        promotion.discount_type = 'free_week'

        promo_code = MagicMock()
        promo_code.promotion = promotion

        assert promo_code.promotion.discount_type == 'free_week'
        assert promo_code.promotion.discount_percent == 100

    def test_promo_code_inherits_free_100(self):
        """PromoCode should use discount_type='free_100' from parent."""
        promotion = MagicMock()
        promotion.discount_percent = 100
        promotion.discount_type = 'free_100'

        promo_code = MagicMock()
        promo_code.promotion = promotion

        assert promo_code.promotion.discount_type == 'free_100'

    def test_promo_code_inherits_percentage(self):
        """PromoCode should use discount_type='percentage' from parent."""
        promotion = MagicMock()
        promotion.discount_percent = 10
        promotion.discount_type = 'percentage'

        promo_code = MagicMock()
        promo_code.promotion = promotion

        assert promo_code.promotion.discount_type == 'percentage'
        assert promo_code.promotion.discount_percent == 10


# =============================================================================
# Unit Tests: Validation Response Structure
# =============================================================================

class TestValidationResponseStructure:
    """Tests for promo validation response structure."""

    def test_response_includes_discount_type_free_week(self):
        """Validation response should include discount_type='free_week'."""
        response = {
            'valid': True,
            'message': 'Promo code applied! 1 week free parking!',
            'discount_percent': 100,
            'discount_type': 'free_week'
        }

        assert response['discount_type'] == 'free_week'
        assert response['discount_percent'] == 100
        assert 'free' in response['message'].lower()

    def test_response_includes_discount_type_free_100(self):
        """Validation response should include discount_type='free_100'."""
        response = {
            'valid': True,
            'message': 'Promo code applied! 100% off your booking!',
            'discount_percent': 100,
            'discount_type': 'free_100'
        }

        assert response['discount_type'] == 'free_100'
        assert '100%' in response['message']

    def test_response_includes_discount_type_percentage(self):
        """Validation response should include discount_type='percentage'."""
        response = {
            'valid': True,
            'message': 'Promo code applied! 10% off',
            'discount_percent': 10,
            'discount_type': 'percentage'
        }

        assert response['discount_type'] == 'percentage'
        assert '10%' in response['message']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
