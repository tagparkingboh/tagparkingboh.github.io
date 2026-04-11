"""
Mocked unit tests for peak day pricing increment.

Tests cover:
- Peak day detection logic: Fri/Sat drop-off AND Sun/Mon/Tue pickup
- Peak day increment applied to price calculations
- Peak day increment disabled when set to 0
- Integration with existing tier and duration pricing
- Happy paths, unhappy paths, edge cases, and boundary conditions

Peak Day Criteria:
- Drop-off on Friday (4) or Saturday (5)
- Pickup on Sunday (6), Monday (0), or Tuesday (1)
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
# Unit Tests: is_peak_day_booking() - Happy Paths
# =============================================================================

class TestIsPeakDayBookingHappy:
    """Happy path tests for peak day detection."""

    def test_friday_dropoff_sunday_pickup_is_peak(self):
        """Friday drop-off with Sunday pickup should be peak day."""
        # Friday April 11, 2026 -> Sunday April 13, 2026
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_monday_pickup_is_peak(self):
        """Friday drop-off with Monday pickup should be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_dropoff_tuesday_pickup_is_peak(self):
        """Friday drop-off with Tuesday pickup should be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_sunday_pickup_is_peak(self):
        """Saturday drop-off with Sunday pickup should be peak day."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_monday_pickup_is_peak(self):
        """Saturday drop-off with Monday pickup should be peak day."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_dropoff_tuesday_pickup_is_peak(self):
        """Saturday drop-off with Tuesday pickup should be peak day."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: is_peak_day_booking() - Non-Peak Scenarios
# =============================================================================

class TestIsPeakDayBookingNonPeak:
    """Tests for non-peak day bookings."""

    def test_monday_dropoff_is_not_peak(self):
        """Monday drop-off should not be peak day."""
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_tuesday_dropoff_is_not_peak(self):
        """Tuesday drop-off should not be peak day."""
        drop_off = date(2026, 4, 7)   # Tuesday
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_wednesday_dropoff_is_not_peak(self):
        """Wednesday drop-off should not be peak day."""
        drop_off = date(2026, 4, 8)   # Wednesday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_thursday_dropoff_is_not_peak(self):
        """Thursday drop-off should not be peak day."""
        drop_off = date(2026, 4, 9)   # Thursday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_sunday_dropoff_is_not_peak(self):
        """Sunday drop-off should not be peak day."""
        drop_off = date(2026, 4, 12)  # Sunday
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_friday_dropoff_wednesday_pickup_is_not_peak(self):
        """Friday drop-off with Wednesday pickup should not be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_friday_dropoff_thursday_pickup_is_not_peak(self):
        """Friday drop-off with Thursday pickup should not be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 16)    # Thursday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_friday_dropoff_friday_pickup_is_not_peak(self):
        """Friday drop-off with Friday pickup should not be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 17)    # Friday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_friday_dropoff_saturday_pickup_is_not_peak(self):
        """Friday drop-off with Saturday pickup should not be peak day."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 11)    # Saturday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_saturday_dropoff_wednesday_pickup_is_not_peak(self):
        """Saturday drop-off with Wednesday pickup should not be peak day."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 15)    # Wednesday
        assert is_peak_day_booking(drop_off, pickup) is False


# =============================================================================
# Unit Tests: calculate_price_for_duration() with Peak Day
# =============================================================================

class TestCalculatePriceWithPeakDay:
    """Tests for price calculation with peak day increment."""

    def test_peak_day_adds_increment_to_base_price(self, mock_peak_pricing):
        """Peak day booking should add peak_day_increment to base price."""
        # Friday drop-off, Sunday pickup (2 days, early booking)
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 12)    # Sunday
        duration = 2

        # Far future booking = early tier, base price = 65, peak increment = 10
        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0 + 10.0  # base + peak increment
        assert price == expected

    def test_peak_day_with_tier_increment(self, mock_peak_pricing):
        """Peak day should stack with tier increment."""
        # Saturday drop-off, Monday pickup (2 days, late booking)
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 13)    # Monday
        duration = 2

        # Late tier = base + 2x tier_increment + peak_increment
        with patch.object(BookingService, 'get_advance_tier', return_value='late'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0 + (5.0 * 2) + 10.0  # base + late tier + peak
        assert price == expected

    def test_peak_day_with_standard_tier(self, mock_peak_pricing):
        """Peak day should stack with standard tier increment."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 14)    # Tuesday
        duration = 4

        # Standard tier = base + 1x tier_increment + peak_increment
        with patch.object(BookingService, 'get_advance_tier', return_value='standard'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0 + 5.0 + 10.0  # base + standard tier + peak
        assert price == expected

    def test_non_peak_day_no_increment(self, mock_peak_pricing):
        """Non-peak day booking should not add peak increment."""
        # Monday drop-off, Wednesday pickup
        drop_off = date(2026, 4, 6)   # Monday
        pickup = date(2026, 4, 8)     # Wednesday
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0  # base only, no peak
        assert price == expected


# =============================================================================
# Unit Tests: Peak Day Disabled (increment = 0)
# =============================================================================

class TestPeakDayDisabled:
    """Tests when peak day increment is set to 0."""

    def test_peak_day_zero_increment_no_change(self, mock_no_peak_pricing):
        """Peak day booking with 0 increment should not add to price."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 12)    # Sunday
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        expected = 65.0  # base only, no peak (increment is 0)
        assert price == expected


# =============================================================================
# Unit Tests: Extended Durations with Peak Day
# =============================================================================

class TestPeakDayWithExtendedDurations:
    """Tests for peak day with longer durations."""

    def test_peak_day_7_day_booking(self, mock_peak_pricing):
        """7-day peak day booking should use week1 price + peak increment."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 17)    # Friday (not peak pickup)
        duration = 7

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # Friday pickup is NOT Sun/Mon/Tue, so no peak increment
        expected = 85.0  # week1 base only
        assert price == expected

    def test_peak_day_9_day_fri_to_sun(self, mock_peak_pricing):
        """9-day Fri to Sun booking should apply peak increment."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 19)    # Sunday (9 days later)
        duration = 9

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off, pickup)

        # Week1 + 2 daily increments + peak
        expected = 85.0 + (2 * 8.0) + 10.0
        assert price == expected


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestPeakDayEdgeCases:
    """Edge case tests for peak day pricing."""

    def test_pickup_date_calculated_from_duration(self, mock_peak_pricing):
        """When pickup_date is None, it should be calculated from duration."""
        # Friday drop-off, 2 days = Sunday pickup (peak)
        drop_off = date(2026, 4, 10)  # Friday
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off)

        # Should detect peak: Fri + 2 days = Sun
        expected = 65.0 + 10.0
        assert price == expected

    def test_saturday_to_monday_2_days(self, mock_peak_pricing):
        """Saturday to Monday (2 days) should be peak."""
        drop_off = date(2026, 4, 11)  # Saturday
        duration = 2

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off)

        # Sat + 2 days = Mon (peak)
        expected = 65.0 + 10.0
        assert price == expected

    def test_friday_to_tuesday_4_days(self, mock_peak_pricing):
        """Friday to Tuesday (4 days) should be peak."""
        drop_off = date(2026, 4, 10)  # Friday
        duration = 4

        with patch.object(BookingService, 'get_advance_tier', return_value='early'):
            price = BookingService.calculate_price_for_duration(duration, drop_off)

        # Fri + 4 days = Tue (peak)
        expected = 65.0 + 10.0
        assert price == expected


# =============================================================================
# Unit Tests: Boundary Conditions
# =============================================================================

class TestPeakDayBoundaries:
    """Boundary condition tests for peak day pricing."""

    def test_friday_boundary_peak_dropoff(self):
        """Friday (weekday=4) is boundary for peak drop-off."""
        drop_off = date(2026, 4, 10)  # Friday (4)
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_thursday_boundary_not_peak_dropoff(self):
        """Thursday (weekday=3) is just before peak drop-off boundary."""
        drop_off = date(2026, 4, 9)   # Thursday (3)
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_sunday_boundary_peak_pickup(self):
        """Sunday (weekday=6) is boundary for peak pickup."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 12)    # Sunday (6)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_tuesday_boundary_peak_pickup(self):
        """Tuesday (weekday=1) is boundary for peak pickup."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 14)    # Tuesday (1)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_wednesday_boundary_not_peak_pickup(self):
        """Wednesday (weekday=2) is just after peak pickup boundary."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday (2)
        assert is_peak_day_booking(drop_off, pickup) is False


# =============================================================================
# Unit Tests: Midnight Crossover Boundary Tests
# =============================================================================

class TestMidnightBoundaries:
    """
    Midnight crossover boundary tests.

    Peak day detection is based on DATE only, not time.
    These tests verify that the date boundary is correctly handled.

    Key scenarios:
    - Pickup at 23:59 on peak day (Tue) vs 00:00 on non-peak day (Wed)
    - Drop-off at 23:59 on non-peak day (Thu) vs 00:00 on peak day (Fri)
    """

    def test_pickup_tuesday_last_minute_is_peak(self):
        """
        Pickup on Tuesday (even at 23:59) should be peak.
        The actual time doesn't matter - only the DATE is checked.
        """
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 14)    # Tuesday (last day of peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_pickup_wednesday_first_minute_is_not_peak(self):
        """
        Pickup on Wednesday (even at 00:00) should NOT be peak.
        This is 1 minute after 23:59 Tuesday in real time.
        """
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 15)    # Wednesday (first day after peak)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_dropoff_thursday_last_minute_is_not_peak(self):
        """
        Drop-off on Thursday (even at 23:59) should NOT be peak.
        """
        drop_off = date(2026, 4, 9)   # Thursday
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_dropoff_friday_first_minute_is_peak(self):
        """
        Drop-off on Friday (even at 00:00) should be peak.
        This is 1 minute after 23:59 Thursday in real time.
        """
        drop_off = date(2026, 4, 10)  # Friday (first day of peak drop-off)
        pickup = date(2026, 4, 12)    # Sunday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_pickup_saturday_is_not_peak(self):
        """
        Pickup on Saturday should NOT be peak (only Sun/Mon/Tue are peak pickup).
        """
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 11)    # Saturday
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_pickup_sunday_first_minute_is_peak(self):
        """
        Pickup on Sunday (even at 00:00, first minute) should be peak.
        """
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 12)    # Sunday (first day of peak pickup)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_dropoff_saturday_last_minute_is_peak(self):
        """
        Drop-off on Saturday (even at 23:59) should be peak.
        """
        drop_off = date(2026, 4, 11)  # Saturday (last day of peak drop-off)
        pickup = date(2026, 4, 13)    # Monday
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_dropoff_sunday_first_minute_is_not_peak(self):
        """
        Drop-off on Sunday (even at 00:00) should NOT be peak.
        This is 1 minute after 23:59 Saturday in real time.
        """
        drop_off = date(2026, 4, 12)  # Sunday (first day after peak drop-off)
        pickup = date(2026, 4, 14)    # Tuesday
        assert is_peak_day_booking(drop_off, pickup) is False


# =============================================================================
# Unit Tests: Week Crossover Scenarios
# =============================================================================

class TestWeekCrossoverScenarios:
    """Test peak day detection across different weeks."""

    def test_friday_to_next_sunday_is_peak(self):
        """Friday drop-off to next week Sunday pickup is peak."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 19)    # Sunday (9 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_saturday_to_next_monday_is_peak(self):
        """Saturday drop-off to next week Monday pickup is peak."""
        drop_off = date(2026, 4, 11)  # Saturday
        pickup = date(2026, 4, 20)    # Monday (9 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_to_next_tuesday_is_peak(self):
        """Friday drop-off to next week Tuesday pickup is peak."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 21)    # Tuesday (11 days later)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_friday_to_next_wednesday_is_not_peak(self):
        """Friday drop-off to next week Wednesday pickup is NOT peak."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 22)    # Wednesday (12 days later)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_two_week_fri_to_mon(self):
        """Two-week Friday to Monday booking is peak."""
        drop_off = date(2026, 4, 10)  # Friday
        pickup = date(2026, 4, 27)    # Monday (17 days later)
        assert is_peak_day_booking(drop_off, pickup) is True


# =============================================================================
# Unit Tests: Overnight Arrival Scenarios (Late Flight to Next Day)
# =============================================================================

class TestOvernightArrivalScenarios:
    """
    Test scenarios where return flight arrives late and pickup rolls to next day.

    The booking system calculates pickup_date as arrival_date when the pickup
    time (arrival + 30 min) crosses midnight. For example:
    - Flight arrives 23:50 Tuesday → pickup 00:20 Wednesday → pickup_date = Wednesday

    These tests verify peak day logic works correctly with actual pickup dates.
    """

    def test_late_tuesday_flight_pickup_wednesday_not_peak(self):
        """
        Late Tuesday arrival (23:50) results in Wednesday pickup (00:20).
        Wednesday pickup is NOT peak (only Sun/Mon/Tue are peak pickup).

        Scenario: Customer flight arrives 23:50 Tuesday, pickup is 00:20 Wednesday.
        The pickup_date in the system is Wednesday, not Tuesday.
        """
        drop_off = date(2026, 4, 10)  # Friday
        # Flight arrives 23:50 Tuesday, pickup 00:20 Wednesday
        pickup = date(2026, 4, 15)    # Wednesday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_late_saturday_flight_pickup_sunday_is_peak(self):
        """
        Late Saturday arrival (23:50) results in Sunday pickup (00:20).
        Sunday pickup IS peak.
        """
        drop_off = date(2026, 4, 10)  # Friday
        # Flight arrives 23:50 Saturday, pickup 00:20 Sunday
        pickup = date(2026, 4, 12)    # Sunday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_late_sunday_flight_pickup_monday_is_peak(self):
        """
        Late Sunday arrival (23:50) results in Monday pickup (00:20).
        Monday pickup IS peak.
        """
        drop_off = date(2026, 4, 10)  # Friday
        # Flight arrives 23:50 Sunday, pickup 00:20 Monday
        pickup = date(2026, 4, 13)    # Monday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_late_monday_flight_pickup_tuesday_is_peak(self):
        """
        Late Monday arrival (23:50) results in Tuesday pickup (00:20).
        Tuesday pickup IS peak.
        """
        drop_off = date(2026, 4, 11)  # Saturday
        # Flight arrives 23:50 Monday, pickup 00:20 Tuesday
        pickup = date(2026, 4, 14)    # Tuesday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_late_thursday_flight_pickup_friday_not_peak(self):
        """
        Late Thursday arrival (23:50) results in Friday pickup (00:20).
        Friday pickup is NOT peak (only Sun/Mon/Tue are peak pickup).
        """
        drop_off = date(2026, 4, 10)  # Friday
        # Flight arrives 23:50 Thursday, pickup 00:20 Friday
        pickup = date(2026, 4, 17)    # Friday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_early_morning_tuesday_arrival_same_day_is_peak(self):
        """
        Early Tuesday arrival (06:00) has same-day pickup (06:30).
        Tuesday pickup IS peak.
        """
        drop_off = date(2026, 4, 10)  # Friday
        # Flight arrives 06:00 Tuesday, pickup 06:30 Tuesday (same day)
        pickup = date(2026, 4, 14)    # Tuesday (actual pickup date)
        assert is_peak_day_booking(drop_off, pickup) is True

    def test_late_dropoff_thursday_midnight_not_peak(self):
        """
        Late Thursday drop-off that might feel like Friday is still Thursday.
        The system uses drop_off_date, not drop_off_datetime.
        """
        drop_off = date(2026, 4, 9)   # Thursday (even if at 23:30)
        pickup = date(2026, 4, 12)    # Sunday
        # Thursday drop-off is NOT peak (only Fri/Sat are peak drop-off)
        assert is_peak_day_booking(drop_off, pickup) is False

    def test_early_dropoff_friday_midnight_is_peak(self):
        """
        Early Friday drop-off (just past midnight) IS peak.
        The system uses drop_off_date = Friday.
        """
        drop_off = date(2026, 4, 10)  # Friday (even if at 00:01)
        pickup = date(2026, 4, 12)    # Sunday
        # Friday drop-off IS peak
        assert is_peak_day_booking(drop_off, pickup) is True
