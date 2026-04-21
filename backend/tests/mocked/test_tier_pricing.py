"""
Mocked unit tests for advance booking tier pricing.

Tests cover:
- Tier determination based on days in advance
- Tier increment applied to base prices
- Tier pricing combined with peak day increment
- All durations (1-14+ days) with all tiers

Advance Booking Tiers:
- Early: ≥14 days in advance → base price
- Standard: 7-13 days in advance → base + tier_increment
- Late: <7 days in advance → base + (2 × tier_increment)

Test Coverage:
1. Happy path - Correct tier determination and pricing
2. Unhappy path - Edge cases for tier boundaries
3. Edge cases - 0, 6, 7, 13, 14 days in advance
4. Boundaries - Min/max tier increments
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from booking_service import (
    BookingService,
    get_pricing_from_db,
    get_base_price_for_duration,
)


# =============================================================================
# Helper Functions for Test Dates
# =============================================================================

def get_non_peak_date_for_tier(tier: str, duration_days: int = 7) -> tuple[date, date]:
    """
    Get a drop-off and pickup date pair for the specified tier, avoiding peak days.

    Peak days:
    - Drop-off: Fri/Sat
    - Pickup: Sun/Mon/Tue

    Args:
        tier: 'early' (>=14 days), 'standard' (7-13 days), or 'late' (<7 days)
        duration_days: Trip duration in days

    Returns:
        (drop_off, pickup) date tuple
    """
    # Define tier boundaries
    if tier == "early":
        min_offset = 14
        max_offset = 60  # Plenty of room
    elif tier == "standard":
        min_offset = 7
        max_offset = 13
    else:  # late
        min_offset = 1
        max_offset = 6

    # Try each day in the tier range until we find a non-peak combination
    for offset in range(min_offset, max_offset + 1):
        drop_off = date.today() + timedelta(days=offset)
        pickup = drop_off + timedelta(days=duration_days)

        is_peak_dropoff = drop_off.weekday() in [4, 5]  # Fri/Sat
        is_peak_pickup = pickup.weekday() in [0, 1, 6]  # Sun/Mon/Tue

        if not is_peak_dropoff and not is_peak_pickup:
            return drop_off, pickup

    # Fallback: return a date in tier (may be peak - test will handle)
    drop_off = date.today() + timedelta(days=min_offset)
    pickup = drop_off + timedelta(days=duration_days)
    return drop_off, pickup


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default pricing configuration."""
    return {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 9.0,
        "tier_increment": 10.0,
        "peak_day_increment": 10.0,
    }


@pytest.fixture
def mock_pricing(default_pricing):
    """Mock get_pricing_from_db to return default pricing."""
    with patch('booking_service.get_pricing_from_db', return_value=default_pricing):
        yield default_pricing


@pytest.fixture
def mock_pricing_high_tier():
    """Mock pricing with high tier increment (£20)."""
    pricing = {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 9.0,
        "tier_increment": 20.0,
        "peak_day_increment": 10.0,
    }
    with patch('booking_service.get_pricing_from_db', return_value=pricing):
        yield pricing


@pytest.fixture
def mock_pricing_zero_tier():
    """Mock pricing with zero tier increment."""
    pricing = {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 9.0,
        "tier_increment": 0.0,
        "peak_day_increment": 10.0,
    }
    with patch('booking_service.get_pricing_from_db', return_value=pricing):
        yield pricing


# =============================================================================
# Unit Tests: Tier Determination (get_advance_tier)
# =============================================================================

class TestTierDetermination:
    """Tests for get_advance_tier - determining tier based on days in advance."""

    def test_early_tier_exactly_14_days(self):
        """Booking exactly 14 days in advance should be Early tier."""
        drop_off = date.today() + timedelta(days=14)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "early"

    def test_early_tier_15_days(self):
        """Booking 15 days in advance should be Early tier."""
        drop_off = date.today() + timedelta(days=15)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "early"

    def test_early_tier_30_days(self):
        """Booking 30 days in advance should be Early tier."""
        drop_off = date.today() + timedelta(days=30)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "early"

    def test_early_tier_60_days(self):
        """Booking 60 days in advance should be Early tier."""
        drop_off = date.today() + timedelta(days=60)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "early"

    def test_standard_tier_exactly_7_days(self):
        """Booking exactly 7 days in advance should be Standard tier."""
        drop_off = date.today() + timedelta(days=7)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "standard"

    def test_standard_tier_10_days(self):
        """Booking 10 days in advance should be Standard tier."""
        drop_off = date.today() + timedelta(days=10)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "standard"

    def test_standard_tier_13_days(self):
        """Booking 13 days in advance should be Standard tier."""
        drop_off = date.today() + timedelta(days=13)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "standard"

    def test_late_tier_6_days(self):
        """Booking 6 days in advance should be Late tier."""
        drop_off = date.today() + timedelta(days=6)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "late"

    def test_late_tier_5_days(self):
        """Booking 5 days in advance should be Late tier."""
        drop_off = date.today() + timedelta(days=5)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "late"

    def test_late_tier_1_day(self):
        """Booking 1 day in advance should be Late tier."""
        drop_off = date.today() + timedelta(days=1)
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "late"

    def test_late_tier_0_days_same_day(self):
        """Same-day booking should be Late tier."""
        drop_off = date.today()
        tier = BookingService.get_advance_tier(drop_off)
        assert tier == "late"


# =============================================================================
# Unit Tests: Tier Boundaries
# =============================================================================

class TestTierBoundaries:
    """Tests for tier boundary conditions (6→7 and 13→14 days)."""

    def test_boundary_6_to_7_days(self):
        """6 days = late, 7 days = standard."""
        drop_off_6 = date.today() + timedelta(days=6)
        drop_off_7 = date.today() + timedelta(days=7)

        assert BookingService.get_advance_tier(drop_off_6) == "late"
        assert BookingService.get_advance_tier(drop_off_7) == "standard"

    def test_boundary_13_to_14_days(self):
        """13 days = standard, 14 days = early."""
        drop_off_13 = date.today() + timedelta(days=13)
        drop_off_14 = date.today() + timedelta(days=14)

        assert BookingService.get_advance_tier(drop_off_13) == "standard"
        assert BookingService.get_advance_tier(drop_off_14) == "early"


# =============================================================================
# Unit Tests: Tier Pricing Calculation
# =============================================================================

class TestTierPriceCalculation:
    """Tests for price calculation with tier increments."""

    def test_early_tier_7_day_trip_no_increment(self, mock_pricing):
        """Early tier should use base price without increment."""
        drop_off = date.today() + timedelta(days=21)  # Early tier
        pickup = drop_off + timedelta(days=7)

        # Avoid peak days for this test (Wed drop, Wed pickup)
        while drop_off.weekday() in [4, 5]:  # Skip Fri/Sat
            drop_off += timedelta(days=1)
        pickup = drop_off + timedelta(days=7)
        while pickup.weekday() in [0, 1, 6]:  # Skip Sun/Mon/Tue
            drop_off += timedelta(days=1)
            pickup = drop_off + timedelta(days=7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)

        # Early tier = base price (85.0)
        assert price == 85.0

    def test_standard_tier_7_day_trip_one_increment(self, mock_pricing):
        """Standard tier should add tier_increment to base price."""
        drop_off, pickup = get_non_peak_date_for_tier("standard", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)

        # Standard tier = base (85) + tier_increment (10) = 95
        assert price == 95.0

    def test_late_tier_7_day_trip_two_increments(self, mock_pricing):
        """Late tier should add 2× tier_increment to base price."""
        drop_off, pickup = get_non_peak_date_for_tier("late", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)

        # Late tier = base (85) + 2 × tier_increment (20) = 105
        assert price == 105.0

    def test_tier_increment_difference(self, mock_pricing):
        """Standard price should be exactly tier_increment more than early."""
        early_drop, early_pickup = get_non_peak_date_for_tier("early", 7)
        standard_drop, standard_pickup = get_non_peak_date_for_tier("standard", 7)

        early_price = BookingService.calculate_price_for_duration(7, early_drop, early_pickup)
        standard_price = BookingService.calculate_price_for_duration(7, standard_drop, standard_pickup)

        # Difference should be exactly tier_increment (10)
        assert standard_price - early_price == 10.0


# =============================================================================
# Unit Tests: High Tier Increment
# =============================================================================

class TestHighTierIncrement:
    """Tests with high tier increment (£20)."""

    def test_early_tier_with_high_increment(self, mock_pricing_high_tier):
        """Early tier should still be base price with high increment."""
        drop_off, pickup = get_non_peak_date_for_tier("early", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 85.0  # Base price

    def test_standard_tier_with_high_increment(self, mock_pricing_high_tier):
        """Standard tier with £20 increment = base + 20."""
        drop_off, pickup = get_non_peak_date_for_tier("standard", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 105.0  # 85 + 20

    def test_late_tier_with_high_increment(self, mock_pricing_high_tier):
        """Late tier with £20 increment = base + 40."""
        drop_off, pickup = get_non_peak_date_for_tier("late", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 125.0  # 85 + (20 × 2)


# =============================================================================
# Unit Tests: Zero Tier Increment
# =============================================================================

class TestZeroTierIncrement:
    """Tests with zero tier increment (all tiers same price)."""

    def test_early_tier_zero_increment(self, mock_pricing_zero_tier):
        """Early tier with zero increment = base price."""
        drop_off, pickup = get_non_peak_date_for_tier("early", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 85.0

    def test_standard_tier_zero_increment(self, mock_pricing_zero_tier):
        """Standard tier with zero increment = base price (same as early)."""
        drop_off, pickup = get_non_peak_date_for_tier("standard", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 85.0  # No increment added

    def test_late_tier_zero_increment(self, mock_pricing_zero_tier):
        """Late tier with zero increment = base price (same as early)."""
        drop_off, pickup = get_non_peak_date_for_tier("late", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        assert price == 85.0  # No increment added

    def test_all_tiers_equal_with_zero_increment(self, mock_pricing_zero_tier):
        """All tiers should be same price when tier_increment is 0."""
        early_drop, early_pickup = get_non_peak_date_for_tier("early", 7)
        standard_drop, standard_pickup = get_non_peak_date_for_tier("standard", 7)
        late_drop, late_pickup = get_non_peak_date_for_tier("late", 7)

        early_price = BookingService.calculate_price_for_duration(7, early_drop, early_pickup)
        standard_price = BookingService.calculate_price_for_duration(7, standard_drop, standard_pickup)
        late_price = BookingService.calculate_price_for_duration(7, late_drop, late_pickup)

        assert early_price == standard_price == late_price == 85.0


# =============================================================================
# Unit Tests: Tier with Different Durations
# =============================================================================

class TestTierWithDurations:
    """Tests for tier pricing with different trip durations."""

    def test_early_tier_14_day_trip(self, mock_pricing):
        """Early tier 14-day trip = week2_base_price."""
        drop_off, pickup = get_non_peak_date_for_tier("early", 14)

        price = BookingService.calculate_price_for_duration(14, drop_off, pickup)
        assert price == 150.0  # week2_base_price

    def test_standard_tier_14_day_trip(self, mock_pricing):
        """Standard tier 14-day trip = week2_base_price + tier_increment."""
        drop_off, pickup = get_non_peak_date_for_tier("standard", 14)

        price = BookingService.calculate_price_for_duration(14, drop_off, pickup)
        assert price == 160.0  # 150 + 10

    def test_late_tier_14_day_trip(self, mock_pricing):
        """Late tier 14-day trip = week2_base_price + 2×tier_increment."""
        drop_off, pickup = get_non_peak_date_for_tier("late", 14)

        price = BookingService.calculate_price_for_duration(14, drop_off, pickup)
        assert price == 170.0  # 150 + 20

    def test_early_tier_4_day_trip(self, mock_pricing):
        """Early tier 4-day trip = days_1_4_price."""
        drop_off, pickup = get_non_peak_date_for_tier("early", 4)

        price = BookingService.calculate_price_for_duration(4, drop_off, pickup)
        assert price == 65.0  # days_1_4_price

    def test_standard_tier_4_day_trip(self, mock_pricing):
        """Standard tier 4-day trip = days_1_4_price + tier_increment."""
        drop_off, pickup = get_non_peak_date_for_tier("standard", 4)

        price = BookingService.calculate_price_for_duration(4, drop_off, pickup)
        assert price == 75.0  # 65 + 10


# =============================================================================
# Unit Tests: Tier Combined with Peak Day
# =============================================================================

class TestTierWithPeakDay:
    """Tests for tier pricing combined with peak day increment."""

    def test_early_tier_peak_friday_dropoff(self, mock_pricing):
        """Early tier + Friday dropoff = base + peak_increment."""
        # Explicitly find a Friday drop-off in early tier range
        drop_off = date.today() + timedelta(days=21)
        while drop_off.weekday() != 4:  # Find Friday
            drop_off += timedelta(days=1)
        pickup = drop_off + timedelta(days=7)  # Friday

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        # base (85) + peak (10) = 95
        assert price == 95.0

    def test_standard_tier_peak_friday_dropoff(self, mock_pricing):
        """Standard tier + Friday dropoff = base + tier + peak."""
        # Explicitly find a Friday drop-off in standard tier range (7-13 days)
        drop_off = date.today() + timedelta(days=7)
        while drop_off.weekday() != 4:  # Find Friday
            drop_off += timedelta(days=1)
        pickup = drop_off + timedelta(days=7)  # Friday

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        # base (85) + tier (10) + peak (10) = 105
        assert price == 105.0

    def test_late_tier_peak_sunday_pickup(self, mock_pricing):
        """Late tier + Sunday pickup = base + 2×tier + peak."""
        # Explicitly find a Thursday drop-off in late tier range (<7 days)
        drop_off = date.today() + timedelta(days=1)
        while drop_off.weekday() != 3:  # Find Thursday
            drop_off += timedelta(days=1)
        pickup = drop_off + timedelta(days=3)  # Sunday

        price = BookingService.calculate_price_for_duration(3, drop_off, pickup)
        # 3 days = days_1_4_price (65) + 2×tier (20) + peak (10) = 95
        assert price == 95.0

    def test_late_tier_non_peak(self, mock_pricing):
        """Late tier + non-peak = base + 2×tier (no peak)."""
        drop_off, pickup = get_non_peak_date_for_tier("late", 7)

        price = BookingService.calculate_price_for_duration(7, drop_off, pickup)
        # base (85) + 2×tier (20) = 105 (no peak)
        assert price == 105.0


# =============================================================================
# Unit Tests: get_all_duration_prices
# =============================================================================

class TestGetAllDurationPrices:
    """Tests for get_all_duration_prices - returns all tier prices."""

    def test_returns_all_tiers_for_7_days(self, mock_pricing):
        """Should return early, standard, late prices for 7-day trips."""
        prices = BookingService.get_all_duration_prices()

        assert "7" in prices
        assert prices["7"]["early"] == 85.0
        assert prices["7"]["standard"] == 95.0
        assert prices["7"]["late"] == 105.0

    def test_returns_all_tiers_for_14_days(self, mock_pricing):
        """Should return early, standard, late prices for 14-day trips."""
        prices = BookingService.get_all_duration_prices()

        assert "14" in prices
        assert prices["14"]["early"] == 150.0
        assert prices["14"]["standard"] == 160.0
        assert prices["14"]["late"] == 170.0

    def test_returns_all_tiers_for_1_day(self, mock_pricing):
        """Should return prices for 1-day trips."""
        prices = BookingService.get_all_duration_prices()

        assert "1" in prices
        assert prices["1"]["early"] == 65.0  # days_1_4_price
        assert prices["1"]["standard"] == 75.0
        assert prices["1"]["late"] == 85.0

    def test_tier_increment_consistent(self, mock_pricing):
        """Tier increment should be consistent across all durations."""
        prices = BookingService.get_all_duration_prices()

        for day in range(1, 15):
            day_str = str(day)
            early = prices[day_str]["early"]
            standard = prices[day_str]["standard"]
            late = prices[day_str]["late"]

            # Standard = Early + tier_increment
            assert standard - early == 10.0, f"Day {day}: standard-early mismatch"
            # Late = Standard + tier_increment
            assert late - standard == 10.0, f"Day {day}: late-standard mismatch"


# =============================================================================
# Unit Tests: get_package_prices (legacy)
# =============================================================================

class TestGetPackagePrices:
    """Tests for legacy get_package_prices method."""

    def test_quick_package_prices(self, mock_pricing):
        """Quick package (1 week) should return correct tier prices."""
        prices = BookingService.get_package_prices()

        assert prices["quick"]["early"] == 85.0
        assert prices["quick"]["standard"] == 95.0
        assert prices["quick"]["late"] == 105.0

    def test_longer_package_prices(self, mock_pricing):
        """Longer package (2 weeks) should return correct tier prices."""
        prices = BookingService.get_package_prices()

        assert prices["longer"]["early"] == 150.0
        assert prices["longer"]["standard"] == 160.0
        assert prices["longer"]["late"] == 170.0
