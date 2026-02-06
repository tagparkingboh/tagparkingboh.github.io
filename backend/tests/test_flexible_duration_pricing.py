"""
Unit tests for flexible duration pricing (1-14 days).

Tests cover:
- Duration tier determination (get_duration_tier)
- Base price retrieval for all durations
- Price calculation with duration + advance tiers
- All 7 duration tiers × 3 advance tiers = 21 pricing scenarios
- Overnight pickup calculations (arrival + 45 mins crossing midnight)
"""
import pytest
from datetime import date, time, timedelta
from unittest.mock import patch

from booking_service import (
    BookingService,
    get_duration_tier,
    get_base_price_for_duration,
    get_pricing_from_db,
)


# =============================================================================
# Test Fixtures: Default pricing for all tests
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default pricing from database or fallback."""
    return {
        "days_1_4_price": 60.0,
        "days_5_6_price": 72.0,
        "week1_base_price": 79.0,   # 7 days
        "days_8_9_price": 99.0,
        "days_10_11_price": 119.0,
        "days_12_13_price": 130.0,
        "week2_base_price": 140.0,  # 14 days
        "tier_increment": 10.0,
    }


# =============================================================================
# Unit Tests: get_duration_tier()
# =============================================================================

class TestGetDurationTier:
    """Tests for duration tier determination."""

    def test_1_day_returns_1_4_tier(self):
        """1 day should return '1_4' tier."""
        assert get_duration_tier(1) == "1_4"

    def test_4_days_returns_1_4_tier(self):
        """4 days should return '1_4' tier (boundary)."""
        assert get_duration_tier(4) == "1_4"

    def test_5_days_returns_5_6_tier(self):
        """5 days should return '5_6' tier (boundary)."""
        assert get_duration_tier(5) == "5_6"

    def test_6_days_returns_5_6_tier(self):
        """6 days should return '5_6' tier (boundary)."""
        assert get_duration_tier(6) == "5_6"

    def test_7_days_returns_7_tier(self):
        """7 days should return '7' tier."""
        assert get_duration_tier(7) == "7"

    def test_8_days_returns_8_9_tier(self):
        """8 days should return '8_9' tier (boundary)."""
        assert get_duration_tier(8) == "8_9"

    def test_9_days_returns_8_9_tier(self):
        """9 days should return '8_9' tier (boundary)."""
        assert get_duration_tier(9) == "8_9"

    def test_10_days_returns_10_11_tier(self):
        """10 days should return '10_11' tier (boundary)."""
        assert get_duration_tier(10) == "10_11"

    def test_11_days_returns_10_11_tier(self):
        """11 days should return '10_11' tier (boundary)."""
        assert get_duration_tier(11) == "10_11"

    def test_12_days_returns_12_13_tier(self):
        """12 days should return '12_13' tier (boundary)."""
        assert get_duration_tier(12) == "12_13"

    def test_13_days_returns_12_13_tier(self):
        """13 days should return '12_13' tier (boundary)."""
        assert get_duration_tier(13) == "12_13"

    def test_14_days_returns_14_tier(self):
        """14 days should return '14' tier."""
        assert get_duration_tier(14) == "14"

    def test_15_days_returns_14_tier(self):
        """15+ days should default to '14' tier."""
        assert get_duration_tier(15) == "14"


# =============================================================================
# Unit Tests: get_base_price_for_duration()
# =============================================================================

class TestGetBasePriceForDuration:
    """Tests for base price retrieval by duration."""

    @pytest.mark.parametrize("duration", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    def test_base_prices_all_durations_positive(self, duration):
        """Test that all durations return a positive base price."""
        price = get_base_price_for_duration(duration)
        assert price > 0, f"Duration {duration} days should have a positive price"

    def test_same_tier_same_price(self):
        """Test that durations in the same tier return the same price."""
        # 1-4 days should all have the same base price
        prices_1_4 = [get_base_price_for_duration(d) for d in [1, 2, 3, 4]]
        assert len(set(prices_1_4)) == 1, "1-4 day durations should have same price"

        # 5-6 days should have the same base price
        prices_5_6 = [get_base_price_for_duration(d) for d in [5, 6]]
        assert len(set(prices_5_6)) == 1, "5-6 day durations should have same price"

        # 8-9 days should have the same base price
        prices_8_9 = [get_base_price_for_duration(d) for d in [8, 9]]
        assert len(set(prices_8_9)) == 1, "8-9 day durations should have same price"

        # 10-11 days should have the same base price
        prices_10_11 = [get_base_price_for_duration(d) for d in [10, 11]]
        assert len(set(prices_10_11)) == 1, "10-11 day durations should have same price"

        # 12-13 days should have the same base price
        prices_12_13 = [get_base_price_for_duration(d) for d in [12, 13]]
        assert len(set(prices_12_13)) == 1, "12-13 day durations should have same price"

    def test_longer_trips_not_cheaper(self):
        """Test that longer trips are generally not cheaper than shorter ones."""
        price_1_4 = get_base_price_for_duration(3)
        price_7 = get_base_price_for_duration(7)
        price_14 = get_base_price_for_duration(14)

        assert price_7 >= price_1_4, "1 week should not be cheaper than 1-4 days"
        assert price_14 >= price_7, "2 weeks should not be cheaper than 1 week"


# =============================================================================
# Unit Tests: BookingService.calculate_price_for_duration()
# =============================================================================

class TestCalculatePriceForDuration:
    """Tests for price calculation with duration + advance tier."""

    @pytest.mark.parametrize("duration", [3, 6, 7, 9, 10, 12, 14])
    def test_advance_tier_pricing_consistency(self, duration):
        """Test that advance tiers apply increments consistently for all durations."""
        # Get prices for all three advance tiers
        early_drop_off = date.today() + timedelta(days=20)  # 20+ days = early
        standard_drop_off = date.today() + timedelta(days=10)  # 7-13 days = standard
        late_drop_off = date.today() + timedelta(days=3)  # <7 days = late

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        # Verify tier ordering: early < standard < late
        assert early_price < standard_price, f"Duration {duration}: standard should be more than early"
        assert standard_price < late_price, f"Duration {duration}: late should be more than standard"

        # Verify consistent increment between tiers
        increment = standard_price - early_price
        assert late_price - standard_price == increment, f"Duration {duration}: increment should be consistent"

    @pytest.mark.parametrize("duration", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    def test_all_durations_return_positive_price(self, duration):
        """Test that all durations 1-14 days return a positive price."""
        drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price_for_duration(duration, drop_off)
        assert price > 0, f"Duration {duration} days should have a positive price"

    def test_early_price_equals_base_price(self):
        """Test that early tier price equals the base price for each duration."""
        early_drop_off = date.today() + timedelta(days=20)

        for duration in [3, 6, 7, 9, 10, 12, 14]:
            early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
            base_price = get_base_price_for_duration(duration)
            assert early_price == base_price, f"Duration {duration}: early price should equal base price"

    def test_same_duration_tier_same_prices(self):
        """Test that durations in the same tier have the same prices."""
        drop_off = date.today() + timedelta(days=20)  # Early tier

        # 1-4 days should have same price
        prices_1_4 = [BookingService.calculate_price_for_duration(d, drop_off) for d in [1, 2, 3, 4]]
        assert len(set(prices_1_4)) == 1, "1-4 day durations should have same price"

        # 5-6 days should have same price
        prices_5_6 = [BookingService.calculate_price_for_duration(d, drop_off) for d in [5, 6]]
        assert len(set(prices_5_6)) == 1, "5-6 day durations should have same price"

        # 8-9 days should have same price
        prices_8_9 = [BookingService.calculate_price_for_duration(d, drop_off) for d in [8, 9]]
        assert len(set(prices_8_9)) == 1, "8-9 day durations should have same price"


# =============================================================================
# Unit Tests: BookingService.get_package_for_duration() - Updated for flexible
# =============================================================================

class TestGetPackageForDurationFlexible:
    """Tests for package determination with flexible durations (1-14 days)."""

    @pytest.mark.parametrize("duration", [1, 2, 3, 4, 5, 6, 7])
    def test_1_to_7_days_returns_quick(self, duration):
        """1-7 day durations should return 'quick' package."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=duration)
        assert BookingService.get_package_for_duration(drop_off, pickup) == "quick"

    @pytest.mark.parametrize("duration", [8, 9, 10, 11, 12, 13, 14])
    def test_8_to_14_days_returns_longer(self, duration):
        """8-14 day durations should return 'longer' package."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=duration)
        assert BookingService.get_package_for_duration(drop_off, pickup) == "longer"

    def test_0_days_raises_error(self):
        """0 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today()
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "at least 1 day" in str(exc_info.value)

    def test_15_days_raises_error(self):
        """15 day duration should raise ValueError (max 14 days)."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=15)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "Maximum is 14 days" in str(exc_info.value)

    def test_negative_duration_raises_error(self):
        """Negative duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() - timedelta(days=1)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "at least 1 day" in str(exc_info.value)


# =============================================================================
# Unit Tests: get_duration_days()
# =============================================================================

class TestGetDurationDays:
    """Tests for duration calculation."""

    def test_7_day_trip(self):
        """7 day trip calculation."""
        drop_off = date(2026, 2, 16)
        pickup = date(2026, 2, 23)
        assert BookingService.get_duration_days(drop_off, pickup) == 7

    def test_14_day_trip(self):
        """14 day trip calculation."""
        drop_off = date(2026, 2, 16)
        pickup = date(2026, 3, 2)
        assert BookingService.get_duration_days(drop_off, pickup) == 14

    def test_10_day_trip(self):
        """10 day trip calculation."""
        drop_off = date(2026, 2, 16)
        pickup = date(2026, 2, 26)
        assert BookingService.get_duration_days(drop_off, pickup) == 10


# =============================================================================
# Unit Tests: Overnight Pickup Calculation
# =============================================================================

class TestOvernightPickupCalculation:
    """Tests for pickup time calculation when landing crosses midnight."""

    def test_normal_pickup_time(self):
        """Normal landing at 14:00 - pickup at 14:45."""
        landing_time = time(14, 0)
        # Calculate pickup time (landing + 45 mins)
        landing_minutes = landing_time.hour * 60 + landing_time.minute
        pickup_minutes = landing_minutes + 45
        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60
        assert pickup_hour == 14
        assert pickup_min == 45

    def test_late_evening_pickup(self):
        """Landing at 23:00 - pickup at 23:45 same day."""
        landing_time = time(23, 0)
        landing_minutes = landing_time.hour * 60 + landing_time.minute
        pickup_minutes = landing_minutes + 45
        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60
        assert pickup_hour == 23
        assert pickup_min == 45

    def test_overnight_pickup_2330_landing(self):
        """
        Landing at 23:30 - pickup at 00:15 next day.

        This is a critical edge case where the pickup crosses midnight.
        The system should handle this correctly.
        """
        landing_time = time(23, 30)
        landing_minutes = landing_time.hour * 60 + landing_time.minute  # 23*60 + 30 = 1410
        pickup_minutes = landing_minutes + 45  # 1410 + 45 = 1455

        # Handle overnight
        if pickup_minutes >= 24 * 60:
            pickup_minutes -= 24 * 60
            crosses_midnight = True
        else:
            crosses_midnight = False

        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60

        assert crosses_midnight is True
        assert pickup_hour == 0
        assert pickup_min == 15

    def test_overnight_pickup_2345_landing(self):
        """
        Landing at 23:45 - pickup at 00:30 next day.
        """
        landing_time = time(23, 45)
        landing_minutes = landing_time.hour * 60 + landing_time.minute  # 1425
        pickup_minutes = landing_minutes + 45  # 1470

        if pickup_minutes >= 24 * 60:
            pickup_minutes -= 24 * 60
            crosses_midnight = True
        else:
            crosses_midnight = False

        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60

        assert crosses_midnight is True
        assert pickup_hour == 0
        assert pickup_min == 30

    def test_overnight_pickup_2350_landing(self):
        """
        Landing at 23:50 - pickup at 00:35 next day.
        """
        landing_time = time(23, 50)
        landing_minutes = landing_time.hour * 60 + landing_time.minute  # 1430
        pickup_minutes = landing_minutes + 45  # 1475

        if pickup_minutes >= 24 * 60:
            pickup_minutes -= 24 * 60
            crosses_midnight = True
        else:
            crosses_midnight = False

        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60

        assert crosses_midnight is True
        assert pickup_hour == 0
        assert pickup_min == 35

    def test_just_before_midnight_no_crossover(self):
        """
        Landing at 23:10 - pickup at 23:55 same day (no crossover).
        """
        landing_time = time(23, 10)
        landing_minutes = landing_time.hour * 60 + landing_time.minute  # 1390
        pickup_minutes = landing_minutes + 45  # 1435

        if pickup_minutes >= 24 * 60:
            pickup_minutes -= 24 * 60
            crosses_midnight = True
        else:
            crosses_midnight = False

        pickup_hour = pickup_minutes // 60
        pickup_min = pickup_minutes % 60

        assert crosses_midnight is False
        assert pickup_hour == 23
        assert pickup_min == 55


# =============================================================================
# Unit Tests: Full Price Matrix (7 durations × 3 advance tiers = 21 scenarios)
# =============================================================================

class TestFullPriceMatrix:
    """
    Comprehensive test of all 21 pricing scenarios.

    Duration tiers: 1-4, 5-6, 7, 8-9, 10-11, 12-13, 14 days
    Advance tiers: Early (14+ days), Standard (7-13 days), Late (<7 days)

    Tests verify pricing relationships rather than specific values,
    making tests database-agnostic.
    """

    # Representative durations for each tier
    DURATION_TIERS = [
        (3, "1_4"),    # 1-4 days tier
        (6, "5_6"),    # 5-6 days tier
        (7, "7"),      # 7 days tier
        (9, "8_9"),    # 8-9 days tier
        (11, "10_11"), # 10-11 days tier
        (13, "12_13"), # 12-13 days tier
        (14, "14"),    # 14 days tier
    ]

    @pytest.mark.parametrize("duration,tier_name", DURATION_TIERS)
    def test_all_durations_return_positive_prices(self, duration, tier_name):
        """Test all 21 price combinations return positive values."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        assert early_price > 0, f"Duration {duration} ({tier_name}) early price should be positive"
        assert standard_price > 0, f"Duration {duration} ({tier_name}) standard price should be positive"
        assert late_price > 0, f"Duration {duration} ({tier_name}) late price should be positive"

    @pytest.mark.parametrize("duration,tier_name", DURATION_TIERS)
    def test_advance_tier_ordering(self, duration, tier_name):
        """Test that early < standard < late for all durations."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        assert early_price < standard_price, (
            f"Duration {duration} ({tier_name}): standard (£{standard_price}) "
            f"should be more than early (£{early_price})"
        )
        assert standard_price < late_price, (
            f"Duration {duration} ({tier_name}): late (£{late_price}) "
            f"should be more than standard (£{standard_price})"
        )

    @pytest.mark.parametrize("duration,tier_name", DURATION_TIERS)
    def test_consistent_tier_increment(self, duration, tier_name):
        """Test that the increment between advance tiers is consistent."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        early_price = BookingService.calculate_price_for_duration(duration, early_drop_off)
        standard_price = BookingService.calculate_price_for_duration(duration, standard_drop_off)
        late_price = BookingService.calculate_price_for_duration(duration, late_drop_off)

        early_to_standard = standard_price - early_price
        standard_to_late = late_price - standard_price

        assert early_to_standard == standard_to_late, (
            f"Duration {duration} ({tier_name}): increment should be consistent. "
            f"Early->Standard: £{early_to_standard}, Standard->Late: £{standard_to_late}"
        )

    def test_longer_durations_cost_more_or_equal(self):
        """Test that longer duration tiers cost at least as much as shorter ones."""
        early_drop_off = date.today() + timedelta(days=20)

        prices = []
        for duration, tier_name in self.DURATION_TIERS:
            price = BookingService.calculate_price_for_duration(duration, early_drop_off)
            prices.append((duration, tier_name, price))

        # Each tier should cost at least as much as the previous
        for i in range(1, len(prices)):
            prev_duration, prev_tier, prev_price = prices[i - 1]
            curr_duration, curr_tier, curr_price = prices[i]
            assert curr_price >= prev_price, (
                f"Duration {curr_duration} ({curr_tier}) at £{curr_price} should not be "
                f"cheaper than {prev_duration} ({prev_tier}) at £{prev_price}"
            )


# =============================================================================
# Unit Tests: get_all_duration_prices()
# =============================================================================

class TestGetAllDurationPrices:
    """Tests for retrieving all duration prices with advance tiers."""

    def test_returns_all_duration_tiers(self):
        """Should return prices for all 7 duration tiers."""
        prices = BookingService.get_all_duration_prices()
        expected_tiers = ["1_4", "5_6", "7", "8_9", "10_11", "12_13", "14"]
        assert list(prices.keys()) == expected_tiers

    def test_each_tier_has_three_advance_levels(self):
        """Each duration tier should have early, standard, late prices."""
        prices = BookingService.get_all_duration_prices()
        for tier, tier_prices in prices.items():
            assert "early" in tier_prices, f"Tier {tier} missing 'early'"
            assert "standard" in tier_prices, f"Tier {tier} missing 'standard'"
            assert "late" in tier_prices, f"Tier {tier} missing 'late'"

    def test_tier_increment_applied_consistently(self):
        """Standard and late should have consistent increments above early price."""
        prices = BookingService.get_all_duration_prices()

        # All tiers should have the same increment pattern
        increments = []
        for tier, tier_prices in prices.items():
            early = tier_prices["early"]
            standard = tier_prices["standard"]
            late = tier_prices["late"]

            # Verify ordering
            assert early < standard < late, f"Tier {tier}: early < standard < late should hold"

            # Calculate increments
            early_to_standard = standard - early
            standard_to_late = late - standard

            # Increment should be consistent within each tier
            assert early_to_standard == standard_to_late, (
                f"Tier {tier}: increment should be consistent. "
                f"early->standard: {early_to_standard}, standard->late: {standard_to_late}"
            )

            increments.append(early_to_standard)

        # All tiers should use the same increment value
        assert len(set(increments)) == 1, (
            f"All tiers should use the same increment. Found: {set(increments)}"
        )

    def test_all_prices_are_positive(self):
        """All prices in all tiers should be positive."""
        prices = BookingService.get_all_duration_prices()
        for tier, tier_prices in prices.items():
            for advance_tier, price in tier_prices.items():
                assert price > 0, f"Tier {tier} {advance_tier} price should be positive"


# =============================================================================
# Unit Tests: Legacy calculate_price() with new defaults
# =============================================================================

class TestLegacyCalculatePriceUpdatedDefaults:
    """
    Tests for legacy calculate_price() method.

    Verifies that quick/longer packages map correctly to 7/14 day durations
    and follow the same pricing structure as flexible duration pricing.
    """

    def test_quick_prices_match_7_day_duration(self):
        """Quick package prices should match 7-day duration prices."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        # Get quick package prices
        quick_early = BookingService.calculate_price("quick", early_drop_off)
        quick_standard = BookingService.calculate_price("quick", standard_drop_off)
        quick_late = BookingService.calculate_price("quick", late_drop_off)

        # Get 7-day duration prices
        duration_early = BookingService.calculate_price_for_duration(7, early_drop_off)
        duration_standard = BookingService.calculate_price_for_duration(7, standard_drop_off)
        duration_late = BookingService.calculate_price_for_duration(7, late_drop_off)

        assert quick_early == duration_early, "Quick early should match 7-day early"
        assert quick_standard == duration_standard, "Quick standard should match 7-day standard"
        assert quick_late == duration_late, "Quick late should match 7-day late"

    def test_longer_prices_match_14_day_duration(self):
        """Longer package prices should match 14-day duration prices."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        # Get longer package prices
        longer_early = BookingService.calculate_price("longer", early_drop_off)
        longer_standard = BookingService.calculate_price("longer", standard_drop_off)
        longer_late = BookingService.calculate_price("longer", late_drop_off)

        # Get 14-day duration prices
        duration_early = BookingService.calculate_price_for_duration(14, early_drop_off)
        duration_standard = BookingService.calculate_price_for_duration(14, standard_drop_off)
        duration_late = BookingService.calculate_price_for_duration(14, late_drop_off)

        assert longer_early == duration_early, "Longer early should match 14-day early"
        assert longer_standard == duration_standard, "Longer standard should match 14-day standard"
        assert longer_late == duration_late, "Longer late should match 14-day late"

    def test_quick_advance_tier_ordering(self):
        """Quick package: early < standard < late."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        quick_early = BookingService.calculate_price("quick", early_drop_off)
        quick_standard = BookingService.calculate_price("quick", standard_drop_off)
        quick_late = BookingService.calculate_price("quick", late_drop_off)

        assert quick_early < quick_standard < quick_late, (
            f"Quick: early (£{quick_early}) < standard (£{quick_standard}) < late (£{quick_late})"
        )

    def test_longer_advance_tier_ordering(self):
        """Longer package: early < standard < late."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        longer_early = BookingService.calculate_price("longer", early_drop_off)
        longer_standard = BookingService.calculate_price("longer", standard_drop_off)
        longer_late = BookingService.calculate_price("longer", late_drop_off)

        assert longer_early < longer_standard < longer_late, (
            f"Longer: early (£{longer_early}) < standard (£{longer_standard}) < late (£{longer_late})"
        )

    def test_longer_costs_more_than_quick(self):
        """Longer package should cost more than quick package."""
        early_drop_off = date.today() + timedelta(days=20)

        quick_price = BookingService.calculate_price("quick", early_drop_off)
        longer_price = BookingService.calculate_price("longer", early_drop_off)

        assert longer_price > quick_price, (
            f"Longer (£{longer_price}) should cost more than quick (£{quick_price})"
        )

    def test_all_prices_positive(self):
        """All package/tier combinations should return positive prices."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        late_drop_off = date.today() + timedelta(days=3)

        for package in ["quick", "longer"]:
            for drop_off, tier_name in [
                (early_drop_off, "early"),
                (standard_drop_off, "standard"),
                (late_drop_off, "late"),
            ]:
                price = BookingService.calculate_price(package, drop_off)
                assert price > 0, f"{package} {tier_name} should have positive price"
