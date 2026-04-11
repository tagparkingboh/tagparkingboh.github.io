"""
Mocked unit tests for peak day pricing increment.

Tests cover:
- Peak day detection logic: Fri/Sat drop-off OR Sun/Mon/Tue pickup
- Peak day increment applied to price calculations
- Peak day increment disabled when set to 0
- Integration with existing tier and duration pricing
- Happy paths, unhappy paths, edge cases, and boundary conditions

Peak Day Criteria (OR logic - either condition triggers peak):
- Drop-off on Friday (4) or Saturday (5)
- OR Pickup on Sunday (6), Monday (0), or Tuesday (1)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from booking_service import (
    BookingService,
    is_peak_day_booking,
    get_pricing_from_db,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default pricing configuration with peak day increment."""
    return {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 8.0,
        "tier_increment": 5.0,
        "peak_day_increment": 10.0,
    }


@pytest.fixture
def pricing_no_peak():
    """Pricing with peak day increment disabled (0)."""
    return {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 8.0,
        "tier_increment": 5.0,
        "peak_day_increment": 0.0,
    }


@pytest.fixture
def mock_peak_pricing(default_pricing):
    """Mock get_pricing_from_db to return pricing with peak day increment."""
    with patch('booking_service.get_pricing_from_db', return_value=default_pricing):
        yield default_pricing


@pytest.fixture
def mock_no_peak_pricing(pricing_no_peak):
    """Mock get_pricing_from_db to return pricing with peak day disabled."""
    with patch('booking_service.get_pricing_from_db', return_value=pricing_no_peak):
        yield pricing_no_peak


# =============================================================================
# Unit Tests: Peak Drop-off Days (Fri/Sat) - Always Peak regardless of pickup
# =============================================================================

class TestPeakDropoffDays:
    """Tests for peak drop-off days (Friday/Saturday) - always peak."""

    def test_friday_dropoff_sunday_pickup_is_peak(self):
        """Friday drop-off with Sunday pickup should be peak (both conditions)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_wednesday_pickup_is_peak(self):
        """Friday drop-off with Wednesday pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_thursday_pickup_is_peak(self):
        """Friday drop-off with Thursday pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 16)    # Thursday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_friday_pickup_is_peak(self):
        """Friday drop-off with Friday pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 17)    # Friday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_sunday_pickup_is_peak(self):
        """Saturday drop-off with Sunday pickup should be peak (both conditions)."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_wednesday_pickup_is_peak(self):
        """Saturday drop-off with Wednesday pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_thursday_pickup_is_peak(self):
        """Saturday drop-off with Thursday pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 16)    # Thursday
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Peak Pickup Days (Sun/Mon/Tue) - Always Peak regardless of drop-off
# =============================================================================

class TestPeakPickupDays:
    """Tests for peak pickup days (Sun/Mon/Tue) - always peak."""

    def test_monday_dropoff_sunday_pickup_is_peak(self):
        """Monday drop-off with Sunday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_tuesday_dropoff_monday_pickup_is_peak(self):
        """Tuesday drop-off with Monday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 7)   # Tuesday
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_wednesday_dropoff_tuesday_pickup_is_peak(self):
        """Wednesday drop-off with Tuesday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_thursday_dropoff_sunday_pickup_is_peak(self):
        """Thursday drop-off with Sunday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 9)   # Thursday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_sunday_dropoff_tuesday_pickup_is_peak(self):
        """Sunday drop-off with Tuesday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 12)  # Sunday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_monday_dropoff_monday_pickup_is_peak(self):
        """Monday drop-off with Monday pickup should be peak (pickup condition)."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Non-Peak Scenarios (no peak drop-off AND no peak pickup)
# =============================================================================

class TestNonPeakScenarios:
    """Tests for non-peak bookings (neither condition met)."""

    def test_monday_dropoff_wednesday_pickup_not_peak(self):
        """Monday drop-off with Wednesday pickup should NOT be peak."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 8)     # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_tuesday_dropoff_thursday_pickup_not_peak(self):
        """Tuesday drop-off with Thursday pickup should NOT be peak."""
        drop_off = date(2026, 4, 7)   # Tuesday
        pickup = date(2026, 4, 9)     # Thursday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_wednesday_dropoff_friday_pickup_not_peak(self):
        """Wednesday drop-off with Friday pickup should NOT be peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 10)    # Friday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_thursday_dropoff_saturday_pickup_not_peak(self):
        """Thursday drop-off with Saturday pickup should NOT be peak."""
        drop_off = date(2026, 4, 9)   # Thursday
        pickup = date(2026, 4, 11)    # Saturday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_sunday_dropoff_wednesday_pickup_not_peak(self):
        """Sunday drop-off with Wednesday pickup should NOT be peak."""
        drop_off = date(2026, 4, 12)  # Sunday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_sunday_dropoff_friday_pickup_not_peak(self):
        """Sunday drop-off with Friday pickup should NOT be peak."""
        drop_off = date(2026, 4, 12)  # Sunday
        pickup = date(2026, 4, 17)    # Friday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_monday_dropoff_saturday_pickup_not_peak(self):
        """Monday drop-off with Saturday pickup should NOT be peak."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 11)    # Saturday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_wednesday_dropoff_saturday_pickup_not_peak(self):
        """Wednesday drop-off with Saturday pickup should NOT be peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 11)    # Saturday
        assert is_peak_day_booking(drop_off, pickup) is False


# =============================================================================
# Unit Tests: calculate_price_for_duration() with Peak Day
# =============================================================================

class TestCalculatePriceWithPeakDay:
    """Tests for price calculation with peak day increment."""

    def test_peak_dropoff_adds_increment(self, mock_peak_pricing):
        """Peak drop-off (Friday) should add peak_day_increment to base price."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday (non-peak pickup)
        duration = 5

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # base (65 + 8) + peak increment = 73 + 10 = 83
        expected = 65.0 + 8.0 + 10.0
        assert price == expected

    def test_peak_pickup_adds_increment(self, mock_peak_pricing):
        """Peak pickup (Sunday) should add peak_day_increment to base price."""
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak drop-off)
        pickup = date(2026, 4, 12)    # Sunday (peak pickup)
        duration = 4

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # base 65 + peak increment = 75
        expected = 65.0 + 10.0
        assert price == expected

    def test_both_peak_conditions_adds_increment_once(self, mock_peak_pricing):
        """Both peak drop-off and pickup should only add increment once."""
        drop_off = date(2026, 4, 10)  # Friday (peak drop-off)
        pickup = date(2026, 4, 12)    # Sunday (peak pickup)
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # base 65 + peak increment = 75 (only added once despite both conditions)
        expected = 65.0 + 10.0
        assert price == expected

    def test_non_peak_no_increment(self, mock_peak_pricing):
        """Non-peak booking should not add peak increment."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 8)     # Wednesday
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0  # base only, no peak
        assert price == expected

    def test_peak_day_with_tier_increment(self, mock_peak_pricing):
        """Peak day should stack with tier increment."""
        drop_off = date(2026, 4, 11)  # Saturday (peak drop-off)
        pickup = date(2026, 4, 13)    # Monday (peak pickup)
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='late'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # base + late tier (2x) + peak = 65 + 10 + 10 = 85
        expected = 65.0 + (5.0 * 2) + 10.0
        assert price == expected


# =============================================================================
# Unit Tests: Peak Day Disabled (increment = 0)
# =============================================================================

class TestPeakDayDisabled:
    """Tests when peak day increment is set to 0."""

    def test_peak_day_zero_increment_no_change(self, mock_no_peak_pricing):
        """Peak day booking with 0 increment should not add to price."""
        drop_off = date(2026, 4, 10)  # Friday (peak)
        pickup = date(2026, 4, 12)    # Sunday (peak)
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0  # base only, no peak (increment is 0)
        assert price == expected


# =============================================================================
# Unit Tests: Boundary Conditions
# =============================================================================

class TestPeakDayBoundaries:
    """Boundary condition tests for peak day pricing."""

    def test_friday_boundary_peak_dropoff(self):
        """Friday (weekday=4) is first peak drop-off day."""
        drop_off = date(2026, 4, 10)  # Friday (4)
        pickup = date(2026, 4, 15)    # Wednesday (non-peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_thursday_boundary_not_peak_dropoff(self):
        """Thursday (weekday=3) is NOT peak drop-off."""
        drop_off = date(2026, 4, 9)   # Thursday (3)
        pickup = date(2026, 4, 15)    # Wednesday (non-peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_saturday_boundary_peak_dropoff(self):
        """Saturday (weekday=5) is last peak drop-off day."""
        drop_off = date(2026, 4, 11)  # Saturday (5)
        pickup = date(2026, 4, 15)    # Wednesday (non-peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_sunday_boundary_not_peak_dropoff_but_peak_overall(self):
        """Sunday drop-off is not peak, but Sunday pickup would be peak."""
        drop_off = date(2026, 4, 12)  # Sunday (not peak drop-off)
        pickup = date(2026, 4, 15)    # Wednesday (not peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_sunday_boundary_peak_pickup(self):
        """Sunday (weekday=6) is first peak pickup day."""
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak drop-off)
        pickup = date(2026, 4, 12)    # Sunday (6)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_tuesday_boundary_peak_pickup(self):
        """Tuesday (weekday=1) is last peak pickup day."""
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak drop-off)
        pickup = date(2026, 4, 14)    # Tuesday (1)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_wednesday_boundary_not_peak_pickup(self):
        """Wednesday (weekday=2) is NOT peak pickup."""
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak drop-off)
        pickup = date(2026, 4, 15)    # Wednesday (2)
        assert is_peak_day_booking(drop_off, pickup) is False


# =============================================================================
# Unit Tests: Midnight Crossover Boundary Tests
# =============================================================================

class TestMidnightBoundaries:
    """
    Midnight crossover boundary tests.

    Peak day detection is based on DATE only, not time.
    These tests verify the date boundary at midnight.
    """

    def test_pickup_tuesday_is_peak(self):
        """Pickup on Tuesday should be peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_pickup_wednesday_with_non_peak_dropoff_not_peak(self):
        """Pickup on Wednesday with non-peak drop-off should NOT be peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_dropoff_thursday_with_non_peak_pickup_not_peak(self):
        """Drop-off on Thursday with non-peak pickup should NOT be peak."""
        drop_off = date(2026, 4, 9)   # Thursday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_dropoff_friday_with_non_peak_pickup_is_peak(self):
        """Drop-off on Friday with non-peak pickup should be peak (drop-off condition)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Week Crossover Scenarios
# =============================================================================

class TestWeekCrossoverScenarios:
    """Test peak day detection across different weeks."""

    def test_friday_to_next_sunday_is_peak(self):
        """Friday drop-off to next week Sunday pickup is peak (both conditions)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 19)    # Sunday (9 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_to_next_monday_is_peak(self):
        """Saturday drop-off to next week Monday pickup is peak (both conditions)."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 20)    # Monday (9 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_to_next_wednesday_is_peak(self):
        """Friday drop-off to next week Wednesday pickup is peak (drop-off condition)."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 22)    # Wednesday (12 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_monday_to_next_wednesday_not_peak(self):
        """Monday drop-off to next week Wednesday is NOT peak."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 15)    # Wednesday (9 days later)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_wednesday_to_next_sunday_is_peak(self):
        """Wednesday drop-off to next week Sunday is peak (pickup condition)."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 19)    # Sunday (11 days later)
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Overnight Arrival Scenarios (Late Flight to Next Day)
# =============================================================================

class TestOvernightArrivalScenarios:
    """
    Test scenarios where return flight arrives late and pickup rolls to next day.

    The booking system calculates pickup_date when the pickup
    time (arrival + 30 min) crosses midnight.
    """

    def test_late_tuesday_flight_pickup_wednesday_not_peak(self):
        """
        Late Tuesday arrival (23:50) results in Wednesday pickup (00:20).
        Wednesday pickup with non-peak drop-off is NOT peak.
        """
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak)
        pickup = date(2026, 4, 15)    # Wednesday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_late_saturday_flight_pickup_sunday_is_peak(self):
        """
        Late Saturday arrival (23:50) results in Sunday pickup (00:20).
        Sunday pickup IS peak.
        """
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak drop-off)
        pickup = date(2026, 4, 12)    # Sunday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_late_tuesday_pickup_wednesday_is_peak(self):
        """
        Friday drop-off with late Tuesday flight becoming Wednesday pickup.
        Peak due to Friday drop-off.
        """
        drop_off = date(2026, 4, 10)  # Friday (peak drop-off)
        pickup = date(2026, 4, 15)    # Wednesday (rolled from late Tue)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_wednesday_dropoff_late_monday_flight_pickup_tuesday_is_peak(self):
        """
        Wednesday drop-off with late Monday flight becoming Tuesday pickup.
        Peak due to Tuesday pickup.
        """
        drop_off = date(2026, 4, 8)   # Wednesday (non-peak)
        pickup = date(2026, 4, 14)    # Tuesday (rolled from late Mon)
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for peak day pricing."""

    def test_pickup_date_calculated_from_duration_friday(self, mock_peak_pricing):
        """When pickup_date is None, calculated Fri drop-off is peak."""
        drop_off = date(2026, 4, 10)  # Friday
        duration = 5  # Wed pickup (non-peak)

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off)

        # Friday drop-off makes it peak
        expected = 65.0 + 8.0 + 10.0  # base + 1 daily + peak
        assert price == expected

    def test_pickup_date_calculated_from_duration_sunday(self, mock_peak_pricing):
        """When pickup_date is None, calculated Sun pickup is peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        duration = 4  # Sunday pickup

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off)

        # Sunday pickup makes it peak
        expected = 65.0 + 10.0  # base + peak
        assert price == expected

    def test_same_day_friday_is_peak(self):
        """Same-day Friday booking should be peak."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 10)    # Friday (same day)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_same_day_sunday_is_peak(self):
        """Same-day Sunday booking should be peak."""
        drop_off = date(2026, 4, 12)  # Sunday
        pickup = date(2026, 4, 12)    # Sunday (same day)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_same_day_wednesday_not_peak(self):
        """Same-day Wednesday booking should NOT be peak."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 8)     # Wednesday (same day)
        assert is_peak_day_booking(drop_off, pickup) is False
