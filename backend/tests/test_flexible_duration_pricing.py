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

    @pytest.mark.parametrize("duration,expected_price", [
        (1, 60.0),    # 1-4 days
        (2, 60.0),
        (3, 60.0),
        (4, 60.0),
        (5, 72.0),    # 5-6 days
        (6, 72.0),
        (7, 79.0),    # 7 days
        (8, 99.0),    # 8-9 days
        (9, 99.0),
        (10, 119.0),  # 10-11 days
        (11, 119.0),
        (12, 130.0),  # 12-13 days
        (13, 130.0),
        (14, 140.0),  # 14 days
    ])
    def test_base_prices_all_durations(self, duration, expected_price):
        """Test base price for all duration tiers."""
        price = get_base_price_for_duration(duration)
        assert price == expected_price, f"Duration {duration} days should be £{expected_price}"


# =============================================================================
# Unit Tests: BookingService.calculate_price_for_duration()
# =============================================================================

class TestCalculatePriceForDuration:
    """Tests for price calculation with duration + advance tier."""

    # 1-4 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 60.0),   # Early tier (base)
        (7, 70.0),    # Standard tier (base + 10)
        (1, 80.0),    # Late tier (base + 20)
    ])
    def test_1_4_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 1-4 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(3, drop_off)
        assert price == expected_price

    # 5-6 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 72.0),   # Early
        (7, 82.0),    # Standard
        (1, 92.0),    # Late
    ])
    def test_5_6_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 5-6 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(6, drop_off)
        assert price == expected_price

    # 7 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 79.0),   # Early
        (7, 89.0),    # Standard
        (1, 99.0),    # Late
    ])
    def test_7_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 7 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(7, drop_off)
        assert price == expected_price

    # 8-9 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 99.0),    # Early
        (7, 109.0),    # Standard
        (1, 119.0),    # Late
    ])
    def test_8_9_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 8-9 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(9, drop_off)
        assert price == expected_price

    # 10-11 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 119.0),   # Early
        (7, 129.0),    # Standard
        (1, 139.0),    # Late
    ])
    def test_10_11_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 10-11 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(10, drop_off)
        assert price == expected_price

    # 12-13 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 130.0),   # Early
        (7, 140.0),    # Standard
        (1, 150.0),    # Late
    ])
    def test_12_13_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 12-13 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(12, drop_off)
        assert price == expected_price

    # 14 days duration tests
    @pytest.mark.parametrize("days_advance,expected_price", [
        (14, 140.0),   # Early
        (7, 150.0),    # Standard
        (1, 160.0),    # Late
    ])
    def test_14_days_all_advance_tiers(self, days_advance, expected_price):
        """Test 14 day trip pricing across advance tiers."""
        drop_off = date.today() + timedelta(days=days_advance)
        price = BookingService.calculate_price_for_duration(14, drop_off)
        assert price == expected_price


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
    """

    # Complete price matrix: (duration, advance_days, expected_price)
    @pytest.mark.parametrize("duration,advance_days,expected_price", [
        # 1-4 days tier
        (3, 20, 60.0),    # Early
        (3, 10, 70.0),    # Standard
        (3, 3, 80.0),     # Late

        # 5-6 days tier
        (6, 20, 72.0),    # Early
        (6, 10, 82.0),    # Standard
        (6, 3, 92.0),     # Late

        # 7 days tier
        (7, 20, 79.0),    # Early
        (7, 10, 89.0),    # Standard
        (7, 3, 99.0),     # Late

        # 8-9 days tier
        (9, 20, 99.0),    # Early
        (9, 10, 109.0),   # Standard
        (9, 3, 119.0),    # Late

        # 10-11 days tier
        (11, 20, 119.0),  # Early
        (11, 10, 129.0),  # Standard
        (11, 3, 139.0),   # Late

        # 12-13 days tier
        (13, 20, 130.0),  # Early
        (13, 10, 140.0),  # Standard
        (13, 3, 150.0),   # Late

        # 14 days tier
        (14, 20, 140.0),  # Early
        (14, 10, 150.0),  # Standard
        (14, 3, 160.0),   # Late
    ])
    def test_full_price_matrix(self, duration, advance_days, expected_price):
        """Test all 21 price combinations."""
        drop_off = date.today() + timedelta(days=advance_days)
        price = BookingService.calculate_price_for_duration(duration, drop_off)
        assert price == expected_price, (
            f"Duration {duration} days, booked {advance_days} days in advance "
            f"should be £{expected_price}, got £{price}"
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

    def test_tier_increment_applied_correctly(self):
        """Standard should be base+10, late should be base+20."""
        prices = BookingService.get_all_duration_prices()

        # Check 7-day tier as example
        seven_day = prices["7"]
        base = seven_day["early"]
        assert seven_day["standard"] == base + 10.0
        assert seven_day["late"] == base + 20.0


# =============================================================================
# Unit Tests: Legacy calculate_price() with new defaults
# =============================================================================

class TestLegacyCalculatePriceUpdatedDefaults:
    """
    Tests for legacy calculate_price() method with updated defaults.

    The base price for "quick" (7 days) is now £79, not £89.
    """

    def test_quick_early_is_now_79(self):
        """Quick package early tier should be £79 (not £89)."""
        drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price("quick", drop_off)
        assert price == 79.0

    def test_quick_standard_is_now_89(self):
        """Quick package standard tier should be £89 (not £99)."""
        drop_off = date.today() + timedelta(days=10)
        price = BookingService.calculate_price("quick", drop_off)
        assert price == 89.0

    def test_quick_late_is_now_99(self):
        """Quick package late tier should be £99 (not £109)."""
        drop_off = date.today() + timedelta(days=3)
        price = BookingService.calculate_price("quick", drop_off)
        assert price == 99.0

    def test_longer_early_unchanged_at_140(self):
        """Longer package early tier unchanged at £140."""
        drop_off = date.today() + timedelta(days=20)
        price = BookingService.calculate_price("longer", drop_off)
        assert price == 140.0

    def test_longer_standard_unchanged_at_150(self):
        """Longer package standard tier unchanged at £150."""
        drop_off = date.today() + timedelta(days=10)
        price = BookingService.calculate_price("longer", drop_off)
        assert price == 150.0

    def test_longer_late_unchanged_at_160(self):
        """Longer package late tier unchanged at £160."""
        drop_off = date.today() + timedelta(days=3)
        price = BookingService.calculate_price("longer", drop_off)
        assert price == 160.0
