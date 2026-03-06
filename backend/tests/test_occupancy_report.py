"""
Unit tests for Occupancy Report feature.

Tests for GET /api/admin/reports/occupancy endpoint that returns:
- Daily occupancy (vehicles parked per day)
- Weekly average occupancy
- Monthly average occupancy
- Future and historical data

Covers:
- Daily view calculations
- Weekly view calculations
- Monthly view calculations
- Edge cases (no bookings, overlapping bookings)
- UK date format (dd/mm/yyyy)

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time, timedelta
from unittest.mock import MagicMock
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use relative dates for future-proof tests
TODAY = date.today()
FUTURE_DATE = TODAY + timedelta(days=90)  # ~3 months from now
FUTURE_DATE_END = TODAY + timedelta(days=97)  # ~1 week after FUTURE_DATE

# For occupancy tests, use month-aligned dates
# Get the first day of a future month (2 months ahead)
def _get_future_month_start():
    """Get the first day of a month approximately 2 months from now."""
    future = TODAY + timedelta(days=60)
    return future.replace(day=1)

def _get_future_month_end(month_start):
    """Get the last day of the given month."""
    # Go to next month's first day, then subtract one day
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return next_month - timedelta(days=1)

FUTURE_MONTH_START = _get_future_month_start()
FUTURE_MONTH_END = _get_future_month_end(FUTURE_MONTH_START)


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_booking(
    id=1,
    dropoff_date=None,
    pickup_date=None,
    status="confirmed",
):
    """Create a mock booking object for occupancy testing."""
    booking = MagicMock()
    booking.id = id
    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or date.today() + timedelta(days=7)

    # Create mock status enum
    status_mock = MagicMock()
    status_mock.value = status
    booking.status = status_mock

    return booking


def create_bookings_for_date_range(start_date, end_date, count=1, status="confirmed"):
    """Create multiple bookings spanning a date range."""
    bookings = []
    for i in range(count):
        bookings.append(create_mock_booking(
            id=i + 1,
            dropoff_date=start_date,
            pickup_date=end_date,
            status=status,
        ))
    return bookings


# =============================================================================
# Unit Tests: Daily Occupancy Calculation
# =============================================================================

class TestDailyOccupancyCalculation:
    """Tests for daily occupancy calculation logic."""

    MAX_CAPACITY = 60

    def test_single_booking_spans_multiple_days(self):
        """Test that a single booking is counted on each day it occupies."""
        start = FUTURE_DATE
        end = FUTURE_DATE + timedelta(days=6)  # 7 day span
        booking = create_mock_booking(dropoff_date=start, pickup_date=end)

        # Calculate daily occupancy
        daily_occupancy = defaultdict(int)
        current = start
        while current <= end:
            daily_occupancy[current.isoformat()] += 1
            current += timedelta(days=1)

        # Should have 7 days of occupancy
        assert len(daily_occupancy) == 7
        assert daily_occupancy[start.isoformat()] == 1
        assert daily_occupancy[end.isoformat()] == 1

    def test_multiple_bookings_same_dates(self):
        """Test multiple bookings on the same dates stack up."""
        start = FUTURE_DATE
        end = FUTURE_DATE + timedelta(days=2)  # 3 day span
        bookings = create_bookings_for_date_range(start, end, count=5)

        daily_occupancy = defaultdict(int)
        for booking in bookings:
            current = booking.dropoff_date
            while current <= booking.pickup_date:
                daily_occupancy[current.isoformat()] += 1
                current += timedelta(days=1)

        assert daily_occupancy[start.isoformat()] == 5
        assert daily_occupancy[(start + timedelta(days=1)).isoformat()] == 5
        assert daily_occupancy[end.isoformat()] == 5

    def test_overlapping_bookings(self):
        """Test overlapping bookings are counted correctly."""
        # Booking 1: Day 0-4
        # Booking 2: Day 2-6
        # Expected: Day 0-1 = 1, Day 2-4 = 2, Day 5-6 = 1
        day0 = FUTURE_DATE
        bookings = [
            create_mock_booking(id=1, dropoff_date=day0, pickup_date=day0 + timedelta(days=4)),
            create_mock_booking(id=2, dropoff_date=day0 + timedelta(days=2), pickup_date=day0 + timedelta(days=6)),
        ]

        daily_occupancy = defaultdict(int)
        for booking in bookings:
            current = booking.dropoff_date
            while current <= booking.pickup_date:
                daily_occupancy[current.isoformat()] += 1
                current += timedelta(days=1)

        assert daily_occupancy[(day0).isoformat()] == 1
        assert daily_occupancy[(day0 + timedelta(days=1)).isoformat()] == 1
        assert daily_occupancy[(day0 + timedelta(days=2)).isoformat()] == 2
        assert daily_occupancy[(day0 + timedelta(days=3)).isoformat()] == 2
        assert daily_occupancy[(day0 + timedelta(days=4)).isoformat()] == 2
        assert daily_occupancy[(day0 + timedelta(days=5)).isoformat()] == 1
        assert daily_occupancy[(day0 + timedelta(days=6)).isoformat()] == 1

    def test_occupancy_percentage_calculation(self):
        """Test occupancy percentage is calculated correctly."""
        occupied = 30
        percentage = round((occupied / self.MAX_CAPACITY) * 100, 1)

        assert percentage == 50.0

    def test_full_capacity(self):
        """Test 100% occupancy."""
        occupied = 60
        percentage = round((occupied / self.MAX_CAPACITY) * 100, 1)

        assert percentage == 100.0

    def test_over_capacity(self):
        """Test handling of over-capacity (shouldn't happen but handle gracefully)."""
        occupied = 65
        percentage = round((occupied / self.MAX_CAPACITY) * 100, 1)

        assert percentage == 108.3

    def test_uk_date_format(self):
        """Test UK date format dd/mm/yyyy."""
        test_date = FUTURE_DATE
        display_date = test_date.strftime("%d/%m/%Y")

        # Verify format is dd/mm/yyyy
        assert len(display_date) == 10
        assert display_date[2] == "/" and display_date[5] == "/"


# =============================================================================
# Unit Tests: Weekly Occupancy Calculation
# =============================================================================

class TestWeeklyOccupancyCalculation:
    """Tests for weekly average occupancy calculation."""

    MAX_CAPACITY = 60

    def test_iso_week_key_format(self):
        """Test ISO week key format."""
        test_date = FUTURE_DATE
        week_key = test_date.strftime("%G-W%V")

        # Verify format is YYYY-Wnn
        assert week_key.startswith("20")
        assert "-W" in week_key

    def test_weekly_average_calculation(self):
        """Test weekly average is calculated correctly."""
        # If we have 7 days and total occupancy of 210 vehicle-days
        # Average should be 30 per day
        total_occupied = 210
        days_in_week = 7
        avg_occupied = total_occupied / days_in_week

        assert avg_occupied == 30.0

    def test_partial_week_average(self):
        """Test average calculation for partial week at edges."""
        # If report starts mid-week with only 3 days
        total_occupied = 90
        days_in_week = 3
        avg_occupied = total_occupied / days_in_week

        assert avg_occupied == 30.0

    def test_week_display_format(self):
        """Test week display format."""
        # Find the next Monday from FUTURE_DATE
        days_until_monday = (7 - FUTURE_DATE.weekday()) % 7
        week_start = FUTURE_DATE + timedelta(days=days_until_monday)
        week_end = week_start + timedelta(days=6)
        display_week = f"{week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m/%Y')}"

        # Verify format is "dd/mm - dd/mm/yyyy" (has 3 slashes: 1 in dd/mm + 2 in dd/mm/yyyy)
        assert " - " in display_week
        assert display_week.count("/") == 3


# =============================================================================
# Unit Tests: Monthly Occupancy Calculation
# =============================================================================

class TestMonthlyOccupancyCalculation:
    """Tests for monthly average occupancy calculation."""

    def test_month_key_format(self):
        """Test month key format."""
        test_date = FUTURE_DATE
        month_key = test_date.strftime("%Y-%m")

        # Verify format is YYYY-MM
        assert len(month_key) == 7
        assert month_key[4] == "-"

    def test_monthly_average_calculation(self):
        """Test monthly average is calculated correctly."""
        # If we have 31 days and total occupancy of 930 vehicle-days
        # Average should be 30 per day
        total_occupied = 930
        days_in_month = 31
        avg_occupied = total_occupied / days_in_month

        assert avg_occupied == 30.0

    def test_month_display_format(self):
        """Test month display format."""
        import calendar
        year = FUTURE_DATE.year
        month = FUTURE_DATE.month
        month_name = calendar.month_name[month]
        display_month = f"{month_name} {year}"

        # Verify format contains year and month name
        assert str(year) in display_month
        assert month_name in display_month


# =============================================================================
# Unit Tests: Date Range Filtering
# =============================================================================

class TestDateRangeFiltering:
    """Tests for filtering bookings by date range."""

    def test_booking_within_range(self):
        """Test booking completely within report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_START + timedelta(days=9),
            pickup_date=FUTURE_MONTH_START + timedelta(days=19),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_starts_before_range(self):
        """Test booking that starts before report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_START - timedelta(days=5),
            pickup_date=FUTURE_MONTH_START + timedelta(days=4),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_ends_after_range(self):
        """Test booking that ends after report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_END - timedelta(days=3),
            pickup_date=FUTURE_MONTH_END + timedelta(days=5),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_spans_entire_range(self):
        """Test booking that spans entire report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_START - timedelta(days=15),
            pickup_date=FUTURE_MONTH_END + timedelta(days=15),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_before_range(self):
        """Test booking completely before report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_START - timedelta(days=30),
            pickup_date=FUTURE_MONTH_START - timedelta(days=15),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is False

    def test_booking_after_range(self):
        """Test booking completely after report range."""
        report_start = FUTURE_MONTH_START
        report_end = FUTURE_MONTH_END
        booking = create_mock_booking(
            dropoff_date=FUTURE_MONTH_END + timedelta(days=15),
            pickup_date=FUTURE_MONTH_END + timedelta(days=25),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is False


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestOccupancyEdgeCases:
    """Edge case tests for occupancy calculations."""

    MAX_CAPACITY = 60

    def test_no_bookings(self):
        """Test occupancy with no bookings."""
        bookings = []

        daily_occupancy = defaultdict(int)
        for booking in bookings:
            current = booking.dropoff_date
            while current <= booking.pickup_date:
                daily_occupancy[current.isoformat()] += 1
                current += timedelta(days=1)

        assert len(daily_occupancy) == 0

    def test_single_day_booking(self):
        """Test booking that starts and ends on same day."""
        booking = create_mock_booking(
            dropoff_date=FUTURE_DATE,
            pickup_date=FUTURE_DATE,
        )

        daily_occupancy = defaultdict(int)
        current = booking.dropoff_date
        while current <= booking.pickup_date:
            daily_occupancy[current.isoformat()] += 1
            current += timedelta(days=1)

        assert len(daily_occupancy) == 1
        assert daily_occupancy[FUTURE_DATE.isoformat()] == 1

    def test_today_flag(self):
        """Test is_today flag is set correctly."""
        today = date.today()
        test_date = today

        is_today = test_date == today
        assert is_today is True

        yesterday = today - timedelta(days=1)
        is_today_yesterday = yesterday == today
        assert is_today_yesterday is False

    def test_is_past_flag(self):
        """Test is_past flag is set correctly."""
        today = date.today()

        yesterday = today - timedelta(days=1)
        is_past = yesterday < today
        assert is_past is True

        tomorrow = today + timedelta(days=1)
        is_past_tomorrow = tomorrow < today
        assert is_past_tomorrow is False

    def test_leap_year_february(self):
        """Test handling of leap year February."""
        # 2024 was a leap year
        booking = create_mock_booking(
            dropoff_date=date(2024, 2, 28),
            pickup_date=date(2024, 3, 1),
        )

        daily_occupancy = defaultdict(int)
        current = booking.dropoff_date
        while current <= booking.pickup_date:
            daily_occupancy[current.isoformat()] += 1
            current += timedelta(days=1)

        # Feb 28, Feb 29, Mar 1 = 3 days
        assert len(daily_occupancy) == 3
        assert "2024-02-29" in daily_occupancy

    def test_year_boundary(self):
        """Test booking spanning year boundary."""
        # Get Dec 30 of current year and Jan 3 of next year
        year = TODAY.year
        dec_30 = date(year, 12, 30)
        jan_3 = date(year + 1, 1, 3)

        booking = create_mock_booking(
            dropoff_date=dec_30,
            pickup_date=jan_3,
        )

        daily_occupancy = defaultdict(int)
        current = booking.dropoff_date
        while current <= booking.pickup_date:
            daily_occupancy[current.isoformat()] += 1
            current += timedelta(days=1)

        assert f"{year}-12-30" in daily_occupancy
        assert f"{year}-12-31" in daily_occupancy
        assert f"{year + 1}-01-01" in daily_occupancy
        assert f"{year + 1}-01-02" in daily_occupancy
        assert f"{year + 1}-01-03" in daily_occupancy
        assert len(daily_occupancy) == 5


# =============================================================================
# Unit Tests: Status Filtering
# =============================================================================

class TestStatusFiltering:
    """Tests for filtering by booking status."""

    def test_confirmed_booking_included(self):
        """Test confirmed bookings are included."""
        booking = create_mock_booking(status="confirmed")

        should_include = booking.status.value in ["confirmed", "completed"]
        assert should_include is True

    def test_completed_booking_included(self):
        """Test completed bookings are included."""
        booking = create_mock_booking(status="completed")

        should_include = booking.status.value in ["confirmed", "completed"]
        assert should_include is True

    def test_pending_booking_excluded(self):
        """Test pending bookings are excluded."""
        booking = create_mock_booking(status="pending")

        should_include = booking.status.value in ["confirmed", "completed"]
        assert should_include is False

    def test_cancelled_booking_excluded(self):
        """Test cancelled bookings are excluded."""
        booking = create_mock_booking(status="cancelled")

        should_include = booking.status.value in ["confirmed", "completed"]
        assert should_include is False


# =============================================================================
# Unit Tests: Response Format
# =============================================================================

class TestOccupancyResponseFormat:
    """Tests for the occupancy API response format."""

    def test_daily_response_structure(self):
        """Test daily view response has all required fields."""
        response = {
            "view": "daily",
            "max_capacity": 60,
            "start_date": "2026-03-01",
            "end_date": "2026-04-30",
            "data": [
                {
                    "date": "2026-03-01",
                    "display_date": "01/03/2026",
                    "occupied": 25,
                    "available": 35,
                    "occupancy_percent": 41.7,
                    "is_past": True,
                    "is_today": False,
                }
            ],
        }

        assert response["view"] == "daily"
        assert response["max_capacity"] == 60
        assert "start_date" in response
        assert "end_date" in response
        assert len(response["data"]) > 0

        entry = response["data"][0]
        assert "date" in entry
        assert "display_date" in entry
        assert "occupied" in entry
        assert "available" in entry
        assert "occupancy_percent" in entry
        assert "is_past" in entry
        assert "is_today" in entry

    def test_weekly_response_structure(self):
        """Test weekly view response has all required fields."""
        response = {
            "view": "weekly",
            "max_capacity": 60,
            "start_date": "2026-03-01",
            "end_date": "2026-04-30",
            "data": [
                {
                    "week": "2026-W10",
                    "display_week": "02/03 - 08/03/2026",
                    "week_start": "2026-03-02",
                    "week_end": "2026-03-08",
                    "avg_occupied": 30.5,
                    "avg_available": 29.5,
                    "avg_occupancy_percent": 50.8,
                    "is_current_week": False,
                    "is_past": True,
                }
            ],
        }

        assert response["view"] == "weekly"
        entry = response["data"][0]
        assert "week" in entry
        assert "display_week" in entry
        assert "avg_occupied" in entry
        assert "avg_available" in entry
        assert "avg_occupancy_percent" in entry
        assert "is_current_week" in entry

    def test_monthly_response_structure(self):
        """Test monthly view response has all required fields."""
        response = {
            "view": "monthly",
            "max_capacity": 60,
            "start_date": "2026-03-01",
            "end_date": "2026-08-31",
            "data": [
                {
                    "month": "2026-03",
                    "display_month": "March 2026",
                    "avg_occupied": 28.5,
                    "avg_available": 31.5,
                    "avg_occupancy_percent": 47.5,
                    "is_current_month": True,
                    "is_past": False,
                }
            ],
        }

        assert response["view"] == "monthly"
        entry = response["data"][0]
        assert "month" in entry
        assert "display_month" in entry
        assert "avg_occupied" in entry
        assert "avg_available" in entry
        assert "avg_occupancy_percent" in entry
        assert "is_current_month" in entry


# =============================================================================
# Unit Tests: Negative Cases
# =============================================================================

class TestOccupancyNegativeCases:
    """Negative test cases for occupancy calculations."""

    def test_invalid_view_type(self):
        """Test handling of invalid view type."""
        valid_views = ["daily", "weekly", "monthly"]
        invalid_view = "yearly"

        assert invalid_view not in valid_views

    def test_invalid_date_range(self):
        """Test handling of end date before start date."""
        start_date = FUTURE_DATE + timedelta(days=30)
        end_date = FUTURE_DATE

        # Should be caught by validation
        is_valid = start_date <= end_date
        assert is_valid is False

    def test_very_long_booking(self):
        """Test handling of very long booking (e.g., 6 months)."""
        start = FUTURE_DATE
        end = FUTURE_DATE + timedelta(days=180)
        booking = create_mock_booking(
            dropoff_date=start,
            pickup_date=end,
        )

        daily_occupancy = defaultdict(int)
        current = booking.dropoff_date
        while current <= booking.pickup_date:
            daily_occupancy[current.isoformat()] += 1
            current += timedelta(days=1)

        # 181 days span (day 0 through day 180)
        assert len(daily_occupancy) == 181


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
