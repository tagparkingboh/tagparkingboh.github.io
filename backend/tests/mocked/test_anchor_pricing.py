"""
Unit tests for anchor-based pricing with daily increments.

Tests cover:
- Anchor pricing: 1-4 days, 7 days, 14 days
- Daily increment calculations for in-between durations (5-6, 8-13, 15+)
- Advance booking tiers: Early (14+), Standard (7-13), Late (<7 days)
- Extended stay pricing beyond 14 days
- Happy paths, unhappy paths, edge cases, and boundary conditions

Pricing Model:
- 3 anchor prices: 1-4 days ($65), 7 days ($85), 14 days ($150) - default values
- Daily increment ($8 default) applied for days between anchors
- Tier increment ($5 default) applied for Standard (+$5) and Late (+$10) bookings
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from booking_service import (
    BookingService,
    get_base_price_for_duration,
    get_pricing_from_db,
)


# =============================================================================
# Test Fixtures: Default and custom pricing
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default anchor pricing configuration."""
    return {
        "days_1_4_price": 65.0,       # 1-4 days anchor
        "week1_base_price": 85.0,     # 7 days anchor
        "week2_base_price": 150.0,    # 14 days anchor
        "daily_increment": 8.0,       # Daily increment between anchors
        "tier_increment": 5.0,        # Advance tier increment
        "peak_day_increment": 0.0,    # Peak day increment (Fri/Sat drop-off, Sun/Mon/Tue pickup)
    }


@pytest.fixture
def mock_default_pricing(default_pricing):
    """Mock get_pricing_from_db to return default pricing."""
    with patch('booking_service.get_pricing_from_db', return_value=default_pricing):
        yield default_pricing


# =============================================================================
# Unit Tests: get_base_price_for_duration() - Happy Paths
# =============================================================================

class TestGetBasePriceForDurationHappy:
    """Happy path tests for base price calculation."""

    def test_1_day_returns_anchor_price(self, mock_default_pricing):
        """1 day should return 1-4 days anchor price ($65)."""
        assert get_base_price_for_duration(1) == 65.0

    def test_4_days_returns_anchor_price(self, mock_default_pricing):
        """4 days (boundary) should return 1-4 days anchor price ($65)."""
        assert get_base_price_for_duration(4) == 65.0

    def test_5_days_returns_anchor_plus_1_increment(self, mock_default_pricing):
        """5 days should return 1-4 anchor + 1 daily increment ($65 + $8 = $73)."""
        expected = 65.0 + 8.0  # 1-4 anchor + 1 increment
        assert get_base_price_for_duration(5) == expected

    def test_6_days_returns_anchor_plus_2_increments(self, mock_default_pricing):
        """6 days should return 1-4 anchor + 2 daily increments ($65 + $16 = $81)."""
        expected = 65.0 + (2 * 8.0)  # 1-4 anchor + 2 increments
        assert get_base_price_for_duration(6) == expected

    def test_7_days_returns_week1_anchor(self, mock_default_pricing):
        """7 days should return week1 anchor price ($85)."""
        assert get_base_price_for_duration(7) == 85.0

    def test_8_days_returns_week1_plus_1_increment(self, mock_default_pricing):
        """8 days should return week1 anchor + 1 daily increment ($85 + $8 = $93)."""
        expected = 85.0 + 8.0
        assert get_base_price_for_duration(8) == expected

    def test_13_days_returns_week1_plus_6_increments(self, mock_default_pricing):
        """13 days should return week1 anchor + 6 daily increments ($85 + $48 = $133)."""
        expected = 85.0 + (6 * 8.0)  # week1 + 6 increments for days 8-13
        assert get_base_price_for_duration(13) == expected

    def test_14_days_returns_week2_anchor(self, mock_default_pricing):
        """14 days should return week2 anchor price ($150)."""
        assert get_base_price_for_duration(14) == 150.0

    def test_15_days_returns_week2_plus_1_increment(self, mock_default_pricing):
        """15 days should return week2 anchor + 1 daily increment ($150 + $8 = $158)."""
        expected = 150.0 + 8.0
        assert get_base_price_for_duration(15) == expected

    def test_21_days_returns_week2_plus_7_increments(self, mock_default_pricing):
        """21 days should return week2 anchor + 7 daily increments ($150 + $56 = $206)."""
        expected = 150.0 + (7 * 8.0)  # week2 + 7 increments for days 15-21
        assert get_base_price_for_duration(21) == expected


# =============================================================================
# Unit Tests: get_base_price_for_duration() - Boundary Cases
# =============================================================================

class TestGetBasePriceForDurationBoundaries:
    """Boundary tests for anchor transitions."""

    def test_transition_4_to_5_days(self, mock_default_pricing):
        """Boundary: 4 days is anchor, 5 days adds increment."""
        price_4 = get_base_price_for_duration(4)
        price_5 = get_base_price_for_duration(5)
        assert price_4 == 65.0  # 1-4 anchor
        assert price_5 == 73.0  # 1-4 anchor + 1 increment
        assert price_5 == price_4 + 8.0

    def test_transition_6_to_7_days(self, mock_default_pricing):
        """Boundary: 6 days uses increments, 7 days uses week1 anchor."""
        price_6 = get_base_price_for_duration(6)
        price_7 = get_base_price_for_duration(7)
        assert price_6 == 81.0  # 1-4 anchor + 2 increments
        assert price_7 == 85.0  # week1 anchor

    def test_transition_13_to_14_days(self, mock_default_pricing):
        """Boundary: 13 days uses increments, 14 days uses week2 anchor."""
        price_13 = get_base_price_for_duration(13)
        price_14 = get_base_price_for_duration(14)
        assert price_13 == 133.0  # week1 + 6 increments
        assert price_14 == 150.0  # week2 anchor

    def test_minimum_duration_1_day(self, mock_default_pricing):
        """Minimum valid duration: 1 day."""
        price = get_base_price_for_duration(1)
        assert price == 65.0
        assert price > 0

    def test_maximum_duration_60_days(self, mock_default_pricing):
        """Maximum supported duration: 60 days."""
        # 60 days = week2 (150) + 46 increments (46 * 8 = 368) = 518
        expected = 150.0 + (46 * 8.0)
        price = get_base_price_for_duration(60)
        assert price == expected


# =============================================================================
# Unit Tests: get_base_price_for_duration() - Edge Cases
# =============================================================================

class TestGetBasePriceForDurationEdgeCases:
    """Edge case tests for unusual inputs."""

    def test_zero_days_returns_anchor(self, mock_default_pricing):
        """0 days edge case - should return anchor price (handled as 1-4 tier)."""
        # The function handles <= 4 as 1-4 anchor
        price = get_base_price_for_duration(0)
        assert price == 65.0

    def test_negative_days_returns_anchor(self, mock_default_pricing):
        """Negative days edge case - should return anchor price."""
        price = get_base_price_for_duration(-1)
        assert price == 65.0

    def test_very_long_stay_100_days(self, mock_default_pricing):
        """Very long stay: 100 days (beyond normal max)."""
        # 100 days = week2 (150) + 86 increments (86 * 8 = 688) = 838
        expected = 150.0 + (86 * 8.0)
        price = get_base_price_for_duration(100)
        assert price == expected

    def test_custom_pricing_respected(self):
        """Custom pricing values should be used when passed."""
        custom_pricing = {
            "days_1_4_price": 50.0,
            "week1_base_price": 70.0,
            "week2_base_price": 120.0,
            "daily_increment": 10.0,
            "tier_increment": 5.0,
            "peak_day_increment": 0.0,
        }
        # 5 days with custom pricing = 50 + 1*10 = 60
        price = get_base_price_for_duration(5, custom_pricing)
        assert price == 60.0


# =============================================================================
# Unit Tests: BookingService.calculate_price_for_duration() - Happy Paths
# =============================================================================

class TestCalculatePriceForDurationHappy:
    """Happy path tests for price calculation with advance tiers."""

    def test_early_tier_uses_base_price(self, mock_default_pricing):
        """Early tier (14+ days advance) should use base price."""
        early_drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(7, early_drop_off)
        assert price == 85.0  # week1 base, no increment

    def test_standard_tier_adds_one_increment(self, mock_default_pricing):
        """Standard tier (7-13 days advance) should add one tier increment."""
        standard_drop_off = date.today() + timedelta(days=10)
        price = BookingService.calculate_price_for_duration(7, standard_drop_off)
        assert price == 90.0  # week1 (85) + tier_increment (5)

    def test_late_tier_adds_two_increments(self, mock_default_pricing):
        """Late tier (<7 days advance) should add two tier increments."""
        late_drop_off = date.today() + timedelta(days=3)
        price = BookingService.calculate_price_for_duration(7, late_drop_off)
        assert price == 95.0  # week1 (85) + 2*tier_increment (10)

    @pytest.mark.parametrize("duration", [1, 4, 5, 6, 7, 8, 13, 14, 15, 21])
    def test_all_durations_return_positive_price(self, mock_default_pricing, duration):
        """All durations should return positive prices."""
        drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(duration, drop_off)
        assert price > 0


# =============================================================================
# Unit Tests: Advance Tier Consistency
# =============================================================================

class TestAdvanceTierConsistency:
    """Tests for consistent advance tier pricing across all durations."""

    @pytest.mark.parametrize("duration", [3, 6, 7, 9, 10, 12, 14, 20])
    def test_advance_tier_ordering(self, mock_default_pricing, duration):
        """Test early < standard < late for all durations."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        assert early_price < standard_price, f"Duration {duration}: standard should be more than early"
        assert standard_price < late_price, f"Duration {duration}: late should be more than standard"

    @pytest.mark.parametrize("duration", [3, 6, 7, 9, 10, 12, 14, 20])
    def test_consistent_tier_increment(self, mock_default_pricing, duration):
        """Verify tier increment is consistent (5.0) across all durations."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        early_to_standard = standard_price - early_price
        standard_to_late = late_price - standard_price

        assert early_to_standard == 5.0, f"Duration {duration}: early->standard should be 5.0"
        assert standard_to_late == 5.0, f"Duration {duration}: standard->late should be 5.0"


# =============================================================================
# Unit Tests: Extended Stay Pricing (15-60 days)
# =============================================================================

class TestExtendedStayPricing:
    """Tests for extended stay pricing beyond 14 days using daily increment."""

    def test_15_day_stay_formula(self, mock_default_pricing):
        """15-day stay = week2 anchor + 1 daily increment."""
        early_drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(15, early_drop_off)
        expected = 150.0 + 8.0  # week2 + 1 increment
        assert price == expected

    def test_21_day_stay_formula(self, mock_default_pricing):
        """21-day stay = week2 anchor + 7 daily increments (3 weeks)."""
        early_drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(21, early_drop_off)
        expected = 150.0 + (7 * 8.0)  # week2 + 7 increments
        assert price == expected

    def test_28_day_stay_formula(self, mock_default_pricing):
        """28-day stay = week2 anchor + 14 daily increments (4 weeks)."""
        early_drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(28, early_drop_off)
        expected = 150.0 + (14 * 8.0)  # week2 + 14 increments
        assert price == expected

    def test_60_day_stay_formula(self, mock_default_pricing):
        """60-day stay = week2 anchor + 46 daily increments."""
        early_drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(60, early_drop_off)
        expected = 150.0 + (46 * 8.0)  # week2 + 46 increments = 518
        assert price == expected

    def test_extended_stay_linear_progression(self, mock_default_pricing):
        """Extended stays should increase linearly at daily_increment rate."""
        early_drop_off = date.today() + timedelta(days=20)

        price_14 = BookingService.calculate_price_for_duration(14, early_drop_off)
        price_15 = BookingService.calculate_price_for_duration(15, early_drop_off)
        price_16 = BookingService.calculate_price_for_duration(16, early_drop_off)
        price_17 = BookingService.calculate_price_for_duration(17, early_drop_off)

        assert price_15 - price_14 == 8.0, "15 - 14 should be daily increment"
        assert price_16 - price_15 == 8.0, "16 - 15 should be daily increment"
        assert price_17 - price_16 == 8.0, "17 - 16 should be daily increment"

    @pytest.mark.parametrize("duration", [15, 21, 28, 45, 60])
    def test_extended_stay_advance_tiers(self, mock_default_pricing, duration):
        """Extended stays should still apply advance tier increments."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        assert early_price < standard_price < late_price


# =============================================================================
# Unit Tests: get_all_duration_prices()
# =============================================================================

class TestGetAllDurationPrices:
    """Tests for retrieving all duration prices."""

    def test_returns_prices_for_days_1_to_21(self, mock_default_pricing):
        """Should return prices for days 1-21."""
        prices = BookingService.get_all_duration_prices()
        for day in range(1, 22):
            assert str(day) in prices, f"Day {day} should be in prices"

    def test_each_day_has_three_tiers(self, mock_default_pricing):
        """Each day should have early, standard, late prices."""
        prices = BookingService.get_all_duration_prices()
        for day_str, tier_prices in prices.items():
            assert "early" in tier_prices, f"Day {day_str} missing 'early'"
            assert "standard" in tier_prices, f"Day {day_str} missing 'standard'"
            assert "late" in tier_prices, f"Day {day_str} missing 'late'"

    def test_all_prices_positive(self, mock_default_pricing):
        """All prices should be positive."""
        prices = BookingService.get_all_duration_prices()
        for day_str, tier_prices in prices.items():
            for tier, price in tier_prices.items():
                assert price > 0, f"Day {day_str} {tier} should have positive price"

    def test_tier_increment_consistent_across_days(self, mock_default_pricing):
        """Tier increment should be consistent (5.0) for all days."""
        prices = BookingService.get_all_duration_prices()
        for day_str, tier_prices in prices.items():
            early = tier_prices["early"]
            standard = tier_prices["standard"]
            late = tier_prices["late"]

            assert standard - early == 5.0, f"Day {day_str}: standard - early should be 5.0"
            assert late - standard == 5.0, f"Day {day_str}: late - standard should be 5.0"

    def test_week1_price_at_day_7(self, mock_default_pricing):
        """Day 7 early price should match week1_base_price."""
        prices = BookingService.get_all_duration_prices()
        assert prices["7"]["early"] == 85.0

    def test_week2_price_at_day_14(self, mock_default_pricing):
        """Day 14 early price should match week2_base_price."""
        prices = BookingService.get_all_duration_prices()
        assert prices["14"]["early"] == 150.0


# =============================================================================
# Unit Tests: Legacy Package Compatibility
# =============================================================================

class TestLegacyPackageCompatibility:
    """Tests for legacy quick/longer package compatibility."""

    def test_quick_matches_7_day_pricing(self, mock_default_pricing):
        """Quick package should match 7-day duration pricing."""
        early_drop_off = date.today() + timedelta(days=20)

        quick_price = BookingService.calculate_price("quick", early_drop_off)
        duration_price = BookingService.calculate_price_for_duration(7, early_drop_off)

        assert quick_price == duration_price

    def test_longer_matches_14_day_pricing(self, mock_default_pricing):
        """Longer package should match 14-day duration pricing."""
        early_drop_off = date.today() + timedelta(days=20)

        longer_price = BookingService.calculate_price("longer", early_drop_off)
        duration_price = BookingService.calculate_price_for_duration(14, early_drop_off)

        assert longer_price == duration_price

    def test_get_package_for_duration_1_to_7_days(self, mock_default_pricing):
        """1-7 days should return 'quick' package."""
        for duration in range(1, 8):
            drop_off = date.today()
            pickup = drop_off + timedelta(days=duration)
            assert BookingService.get_package_for_duration(drop_off, pickup) == "quick"

    def test_get_package_for_duration_8_to_60_days(self, mock_default_pricing):
        """8-60 days should return 'longer' package."""
        for duration in [8, 10, 14, 20, 30, 45, 60]:
            drop_off = date.today()
            pickup = drop_off + timedelta(days=duration)
            assert BookingService.get_package_for_duration(drop_off, pickup) == "longer"


# =============================================================================
# Unit Tests: Unhappy Paths / Error Cases
# =============================================================================

class TestUnhappyPaths:
    """Unhappy path tests for error conditions."""

    def test_zero_day_duration_raises_error(self, mock_default_pricing):
        """0 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = drop_off
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "at least 1 day" in str(exc_info.value)

    def test_negative_duration_raises_error(self, mock_default_pricing):
        """Negative duration should raise ValueError."""
        drop_off = date.today()
        pickup = drop_off - timedelta(days=1)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "at least 1 day" in str(exc_info.value)

    def test_61_day_duration_raises_error(self, mock_default_pricing):
        """61+ day duration should raise ValueError (max 60 days)."""
        drop_off = date.today()
        pickup = drop_off + timedelta(days=61)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "Maximum is 60 days" in str(exc_info.value)


# =============================================================================
# Unit Tests: Database Pricing Retrieval
# =============================================================================

class TestDatabasePricingRetrieval:
    """Tests for pricing retrieval from database."""

    def test_get_pricing_returns_required_keys(self):
        """get_pricing_from_db should return all required keys when no database."""
        # When DATABASE_URL is not set, get_pricing_from_db returns defaults
        with patch.dict('os.environ', {'DATABASE_URL': ''}, clear=False):
            with patch('booking_service.os.getenv', return_value=None):
                pricing = get_pricing_from_db()

                required_keys = [
                    "days_1_4_price",
                    "week1_base_price",
                    "week2_base_price",
                    "daily_increment",
                    "tier_increment",
                ]
                for key in required_keys:
                    assert key in pricing, f"Pricing should contain '{key}'"

    def test_defaults_when_no_database_record(self):
        """Should use sensible defaults when no database connection."""
        with patch('booking_service.os.getenv', return_value=None):
            pricing = get_pricing_from_db()

            # Verify defaults are reasonable
            assert pricing["days_1_4_price"] > 0
            assert pricing["week1_base_price"] > pricing["days_1_4_price"]
            assert pricing["week2_base_price"] > pricing["week1_base_price"]
            assert pricing["daily_increment"] > 0
            assert pricing["tier_increment"] > 0


# =============================================================================
# Unit Tests: Specific Price Calculations (Documentation Examples)
# =============================================================================

class TestSpecificPriceCalculations:
    """Tests verifying specific price calculations for documentation."""

    def test_5_day_early_price(self, mock_default_pricing):
        """5 days early = 1-4 anchor (65) + 1 increment (8) = 73."""
        drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(5, drop_off)
        assert price == 73.0

    def test_6_day_late_price(self, mock_default_pricing):
        """6 days late = 1-4 anchor (65) + 2 increments (16) + 2 tier (10) = 91."""
        drop_off = date.today() + timedelta(days=3)
        price = BookingService.calculate_price_for_duration(6, drop_off)
        # base: 65 + 16 = 81, then + 10 (late tier) = 91
        assert price == 91.0

    def test_10_day_standard_price(self, mock_default_pricing):
        """10 days standard = week1 (85) + 3 increments (24) + 1 tier (5) = 114."""
        drop_off = date.today() + timedelta(days=10)
        price = BookingService.calculate_price_for_duration(10, drop_off)
        # base: 85 + 24 = 109, then + 5 (standard tier) = 114
        assert price == 114.0

    def test_week1_all_tiers(self, mock_default_pricing):
        """1 week prices: early=85, standard=90, late=95."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        assert BookingService.calculate_price_for_duration(7, early_drop_off) == 85.0
        assert BookingService.calculate_price_for_duration(7, standard_drop_off) == 90.0
        assert BookingService.calculate_price_for_duration(7, late_drop_off) == 95.0

    def test_week2_all_tiers(self, mock_default_pricing):
        """2 week prices: early=150, standard=155, late=160."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        assert BookingService.calculate_price_for_duration(14, early_drop_off) == 150.0
        assert BookingService.calculate_price_for_duration(14, standard_drop_off) == 155.0
        assert BookingService.calculate_price_for_duration(14, late_drop_off) == 160.0


# =============================================================================
# Unit Tests: Full Price Matrix for Reference
# =============================================================================

class TestFullPriceMatrix:
    """
    Comprehensive test generating full price matrix for all days 1-21.

    This test documents expected prices for easy reference and verification.
    """

    def test_complete_price_matrix(self, mock_default_pricing):
        """
        Generate and verify complete price matrix.

        Expected prices (early tier):
        - Days 1-4: $65 (anchor)
        - Day 5: $73 (65 + 8)
        - Day 6: $81 (65 + 16)
        - Day 7: $85 (anchor)
        - Day 8: $93 (85 + 8)
        - Day 9: $101 (85 + 16)
        - Day 10: $109 (85 + 24)
        - Day 11: $117 (85 + 32)
        - Day 12: $125 (85 + 40)
        - Day 13: $133 (85 + 48)
        - Day 14: $150 (anchor)
        - Day 15: $158 (150 + 8)
        - Day 16: $166 (150 + 16)
        - ...etc
        """
        expected_early_prices = {
            1: 65.0, 2: 65.0, 3: 65.0, 4: 65.0,  # 1-4 days anchor
            5: 73.0, 6: 81.0,                     # 1-4 + increments
            7: 85.0,                              # week1 anchor
            8: 93.0, 9: 101.0, 10: 109.0, 11: 117.0, 12: 125.0, 13: 133.0,  # week1 + increments
            14: 150.0,                            # week2 anchor
            15: 158.0, 16: 166.0, 17: 174.0, 18: 182.0, 19: 190.0, 20: 198.0, 21: 206.0,  # week2 + increments
        }

        early_drop_off = date.today() + timedelta(days=20)

        for days, expected_price in expected_early_prices.items():
            actual_price = BookingService.calculate_price_for_duration(days, early_drop_off)
            assert actual_price == expected_price, (
                f"Day {days}: expected ${expected_price}, got ${actual_price}"
            )
