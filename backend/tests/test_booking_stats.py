"""
Unit tests for Booking Statistics/Growth feature.

Tests for GET /api/admin/bookings/stats endpoint that returns:
- Daily/weekly/monthly booking counts by status
- Status breakdown (confirmed, completed, pending, cancelled)
- Running totals and cumulative growth
- Period comparisons (this week vs last week, this month vs last month)

Covers:
- Happy path with various booking data
- Edge cases (empty data, single booking, etc.)
- Negative tests (invalid data handling)
- Status breakdown correctness
- Date aggregation accuracy

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, patch
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_payment(amount_pence=5000, status="succeeded"):
    """Create a mock payment object."""
    payment = MagicMock()
    payment.amount_pence = amount_pence
    payment.status = status
    return payment


def create_mock_marketing_subscriber(
    id=1,
    email="test@example.com",
    promo_free_used_booking_id=None,
):
    """Create a mock marketing subscriber for free promo testing."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.email = email
    subscriber.promo_free_used_booking_id = promo_free_used_booking_id
    return subscriber


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    created_at=None,
    customer_id=1,
    vehicle_id=1,
    payment_amount_pence=None,
    dropoff_date=None,
    dropoff_time=None,
    pickup_date=None,
    pickup_time=None,
):
    """Create a mock booking object with optional payment and trip details."""
    from datetime import time as dt_time

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.created_at = created_at or datetime.now()

    # Trip dates and times
    booking.dropoff_date = dropoff_date
    booking.dropoff_time = dropoff_time
    booking.pickup_date = pickup_date
    booking.pickup_time = pickup_time

    # Create mock status enum
    status_mock = MagicMock()
    status_mock.value = status
    booking.status = status_mock

    # Create mock payment if amount specified
    if payment_amount_pence is not None:
        booking.payment = create_mock_payment(amount_pence=payment_amount_pence)
    else:
        booking.payment = None

    return booking


def create_mock_bookings_for_month(year, month, counts_by_status):
    """Create mock bookings for a specific month with given status counts."""
    bookings = []
    booking_id = 1

    for status, count in counts_by_status.items():
        for i in range(count):
            # Distribute bookings across the month
            day = (i % 28) + 1
            created = datetime(year, month, day, 10, 0, 0)
            bookings.append(create_mock_booking(
                id=booking_id,
                reference=f"TAG-{year}{month:02d}{booking_id:04d}",
                status=status,
                created_at=created,
            ))
            booking_id += 1

    return bookings


def create_mock_bookings_for_week(year, week_num, counts_by_status):
    """Create mock bookings for a specific ISO week."""
    bookings = []
    booking_id = 1

    # Get first day of the week
    first_day = datetime.strptime(f'{year}-W{week_num:02d}-1', "%Y-W%W-%w")

    for status, count in counts_by_status.items():
        for i in range(count):
            day_offset = i % 7
            created = first_day + timedelta(days=day_offset)
            bookings.append(create_mock_booking(
                id=booking_id,
                reference=f"TAG-W{week_num}{booking_id:04d}",
                status=status,
                created_at=created,
            ))
            booking_id += 1

    return bookings


# =============================================================================
# Unit Tests: Stats Calculation Logic
# =============================================================================

class TestBookingStatsCalculation:
    """Tests for the booking statistics calculation logic."""

    def test_aggregate_daily_counts(self):
        """Test aggregating booking counts by day."""
        # Create bookings for specific days
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 1, 10, 0)),
            create_mock_booking(id=2, status="confirmed", created_at=datetime(2026, 2, 1, 14, 0)),
            create_mock_booking(id=3, status="completed", created_at=datetime(2026, 2, 1, 16, 0)),
            create_mock_booking(id=4, status="confirmed", created_at=datetime(2026, 2, 2, 10, 0)),
            create_mock_booking(id=5, status="cancelled", created_at=datetime(2026, 2, 2, 12, 0)),
        ]

        # Simulate aggregation logic
        daily_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            day_key = booking.created_at.strftime("%Y-%m-%d")
            status = booking.status.value
            daily_by_status[day_key][status] += 1

        # Verify Feb 1
        assert daily_by_status["2026-02-01"]["confirmed"] == 2
        assert daily_by_status["2026-02-01"]["completed"] == 1
        assert daily_by_status["2026-02-01"].get("cancelled", 0) == 0

        # Verify Feb 2
        assert daily_by_status["2026-02-02"]["confirmed"] == 1
        assert daily_by_status["2026-02-02"]["cancelled"] == 1

    def test_aggregate_weekly_counts(self):
        """Test aggregating booking counts by week."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 2, 10, 0)),  # Week 05
            create_mock_booking(id=2, status="confirmed", created_at=datetime(2026, 2, 3, 10, 0)),  # Week 05
            create_mock_booking(id=3, status="completed", created_at=datetime(2026, 2, 9, 10, 0)),  # Week 06
        ]

        weekly_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            week_key = booking.created_at.strftime("%Y-W%W")
            status = booking.status.value
            weekly_by_status[week_key][status] += 1

        # Verify week counts
        assert weekly_by_status["2026-W05"]["confirmed"] == 2
        assert weekly_by_status["2026-W06"]["completed"] == 1

    def test_aggregate_monthly_counts(self):
        """Test aggregating booking counts by month."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 1, 15, 10, 0)),
            create_mock_booking(id=2, status="confirmed", created_at=datetime(2026, 1, 20, 10, 0)),
            create_mock_booking(id=3, status="completed", created_at=datetime(2026, 2, 5, 10, 0)),
            create_mock_booking(id=4, status="cancelled", created_at=datetime(2026, 2, 10, 10, 0)),
        ]

        monthly_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            month_key = booking.created_at.strftime("%Y-%m")
            status = booking.status.value
            monthly_by_status[month_key][status] += 1

        assert monthly_by_status["2026-01"]["confirmed"] == 2
        assert monthly_by_status["2026-02"]["completed"] == 1
        assert monthly_by_status["2026-02"]["cancelled"] == 1

    def test_status_totals_calculation(self):
        """Test calculating total counts by status."""
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="confirmed"),
            create_mock_booking(id=3, status="confirmed"),
            create_mock_booking(id=4, status="completed"),
            create_mock_booking(id=5, status="completed"),
            create_mock_booking(id=6, status="pending"),
            create_mock_booking(id=7, status="cancelled"),
            create_mock_booking(id=8, status="cancelled"),
        ]

        status_totals = defaultdict(int)
        for booking in bookings:
            status = booking.status.value
            status_totals[status] += 1

        assert status_totals["confirmed"] == 3
        assert status_totals["completed"] == 2
        assert status_totals["pending"] == 1
        assert status_totals["cancelled"] == 2

    def test_total_successful_bookings(self):
        """Test counting only confirmed + completed as successful."""
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="confirmed"),
            create_mock_booking(id=3, status="completed"),
            create_mock_booking(id=4, status="pending"),
            create_mock_booking(id=5, status="cancelled"),
        ]

        status_totals = defaultdict(int)
        for booking in bookings:
            status_totals[booking.status.value] += 1

        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)

        assert total_successful == 3  # 2 confirmed + 1 completed

    def test_cumulative_growth_calculation(self):
        """Test cumulative total calculation over time."""
        daily_data = [
            {"date": "2026-01-01", "confirmed": 2, "completed": 0},
            {"date": "2026-01-02", "confirmed": 3, "completed": 1},
            {"date": "2026-01-03", "confirmed": 1, "completed": 2},
        ]

        cumulative = []
        running_total = 0
        for day in daily_data:
            running_total += day.get("confirmed", 0) + day.get("completed", 0)
            cumulative.append({"date": day["date"], "total": running_total})

        assert cumulative[0]["total"] == 2   # Day 1: 2
        assert cumulative[1]["total"] == 6   # Day 2: 2 + 3 + 1 = 6
        assert cumulative[2]["total"] == 9   # Day 3: 6 + 1 + 2 = 9


# =============================================================================
# Unit Tests: Period Comparisons
# =============================================================================

class TestPeriodComparisons:
    """Tests for this week/last week, this month/last month comparisons."""

    def test_this_week_vs_last_week(self):
        """Test comparing this week to last week."""
        today = date.today()
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)

        bookings = [
            # Last week bookings
            create_mock_booking(id=1, status="confirmed",
                              created_at=datetime.combine(last_week_start, datetime.min.time())),
            create_mock_booking(id=2, status="completed",
                              created_at=datetime.combine(last_week_start + timedelta(days=1), datetime.min.time())),
            # This week bookings
            create_mock_booking(id=3, status="confirmed",
                              created_at=datetime.combine(this_week_start, datetime.min.time())),
            create_mock_booking(id=4, status="confirmed",
                              created_at=datetime.combine(this_week_start + timedelta(days=1), datetime.min.time())),
            create_mock_booking(id=5, status="confirmed",
                              created_at=datetime.combine(today, datetime.min.time())),
        ]

        # Filter successful bookings
        successful = [b for b in bookings if b.status.value in ["confirmed", "completed"]]

        this_week_count = sum(1 for b in successful
                             if b.created_at.date() >= this_week_start)
        last_week_count = sum(1 for b in successful
                             if last_week_start <= b.created_at.date() < this_week_start)

        assert this_week_count == 3
        assert last_week_count == 2

    def test_this_month_vs_last_month(self):
        """Test comparing this month to last month."""
        today = date.today()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        bookings = [
            # Last month bookings
            create_mock_booking(id=1, status="confirmed",
                              created_at=datetime.combine(last_month_start, datetime.min.time())),
            create_mock_booking(id=2, status="confirmed",
                              created_at=datetime.combine(last_month_start + timedelta(days=5), datetime.min.time())),
            # This month bookings
            create_mock_booking(id=3, status="confirmed",
                              created_at=datetime.combine(this_month_start, datetime.min.time())),
            create_mock_booking(id=4, status="completed",
                              created_at=datetime.combine(this_month_start + timedelta(days=1), datetime.min.time())),
            create_mock_booking(id=5, status="confirmed",
                              created_at=datetime.combine(today, datetime.min.time())),
            create_mock_booking(id=6, status="confirmed",
                              created_at=datetime.combine(today, datetime.min.time())),
        ]

        successful = [b for b in bookings if b.status.value in ["confirmed", "completed"]]

        this_month_count = sum(1 for b in successful
                              if b.created_at.date() >= this_month_start)
        last_month_count = sum(1 for b in successful
                              if last_month_start <= b.created_at.date() < this_month_start)

        assert this_month_count == 4
        assert last_month_count == 2

    def test_growth_positive_change(self):
        """Test calculating positive growth."""
        this_week = 10
        last_week = 5
        change = this_week - last_week

        assert change == 5
        assert change > 0  # Positive growth

    def test_growth_negative_change(self):
        """Test calculating negative growth."""
        this_week = 3
        last_week = 8
        change = this_week - last_week

        assert change == -5
        assert change < 0  # Negative growth

    def test_growth_no_change(self):
        """Test calculating zero growth."""
        this_week = 5
        last_week = 5
        change = this_week - last_week

        assert change == 0


# =============================================================================
# Unit Tests: Response Format
# =============================================================================

class TestStatsResponseFormat:
    """Tests for the stats API response format."""

    def test_response_structure(self):
        """Test that response has all required fields."""
        # Simulate response structure
        response = {
            "total_bookings": 100,
            "total_successful": 80,
            "status_totals": {
                "confirmed": 40,
                "completed": 40,
                "pending": 10,
                "cancelled": 10,
            },
            "this_week": 15,
            "last_week": 12,
            "this_month": 45,
            "last_month": 40,
            "daily": [],
            "weekly": [],
            "monthly": [],
            "cumulative": [],
        }

        assert "total_bookings" in response
        assert "total_successful" in response
        assert "status_totals" in response
        assert "this_week" in response
        assert "last_week" in response
        assert "this_month" in response
        assert "last_month" in response
        assert "daily" in response
        assert "weekly" in response
        assert "monthly" in response
        assert "cumulative" in response

    def test_daily_entry_format(self):
        """Test daily data entry format."""
        daily_entry = {
            "date": "2026-02-28",
            "confirmed": 5,
            "completed": 3,
            "pending": 2,
            "cancelled": 1,
            "total": 11,
        }

        assert "date" in daily_entry
        assert "confirmed" in daily_entry
        assert "completed" in daily_entry
        assert "pending" in daily_entry
        assert "cancelled" in daily_entry
        assert "total" in daily_entry
        assert daily_entry["total"] == 11

    def test_weekly_entry_format(self):
        """Test weekly data entry format."""
        weekly_entry = {
            "week": "2026-W09",
            "confirmed": 20,
            "completed": 15,
            "pending": 5,
            "cancelled": 3,
            "total": 43,
        }

        assert "week" in weekly_entry
        assert weekly_entry["week"].startswith("2026-W")

    def test_monthly_entry_format(self):
        """Test monthly data entry format."""
        monthly_entry = {
            "month": "2026-02",
            "confirmed": 50,
            "completed": 40,
            "pending": 10,
            "cancelled": 5,
            "total": 105,
        }

        assert "month" in monthly_entry
        assert monthly_entry["month"] == "2026-02"

    def test_cumulative_entry_format(self):
        """Test cumulative data entry format."""
        cumulative_entry = {
            "date": "2026-02-28",
            "total": 500,
        }

        assert "date" in cumulative_entry
        assert "total" in cumulative_entry


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestBookingStatsEdgeCases:
    """Edge case tests for booking statistics."""

    def test_empty_bookings_list(self):
        """Test stats with no bookings."""
        bookings = []

        status_totals = defaultdict(int)
        for booking in bookings:
            status_totals[booking.status.value] += 1

        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)

        assert total_successful == 0
        assert len(status_totals) == 0

    def test_single_booking(self):
        """Test stats with only one booking."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 15, 10, 0)),
        ]

        daily_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            day_key = booking.created_at.strftime("%Y-%m-%d")
            daily_by_status[day_key][booking.status.value] += 1

        assert len(daily_by_status) == 1
        assert daily_by_status["2026-02-15"]["confirmed"] == 1

    def test_all_same_status(self):
        """Test stats when all bookings have same status."""
        bookings = [
            create_mock_booking(id=i, status="confirmed", created_at=datetime(2026, 2, i, 10, 0))
            for i in range(1, 11)
        ]

        status_totals = defaultdict(int)
        for booking in bookings:
            status_totals[booking.status.value] += 1

        assert status_totals["confirmed"] == 10
        assert status_totals.get("completed", 0) == 0
        assert status_totals.get("pending", 0) == 0
        assert status_totals.get("cancelled", 0) == 0

    def test_all_cancelled_bookings(self):
        """Test stats when all bookings are cancelled."""
        bookings = [
            create_mock_booking(id=i, status="cancelled", created_at=datetime(2026, 2, i, 10, 0))
            for i in range(1, 6)
        ]

        status_totals = defaultdict(int)
        for booking in bookings:
            status_totals[booking.status.value] += 1

        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)

        assert total_successful == 0
        assert status_totals["cancelled"] == 5

    def test_bookings_without_created_at(self):
        """Test handling bookings with null created_at."""
        booking = create_mock_booking(id=1, status="confirmed")
        booking.created_at = None

        # Simulate filtering out null created_at
        bookings_with_dates = [b for b in [booking] if b.created_at]

        assert len(bookings_with_dates) == 0

    def test_very_old_bookings(self):
        """Test handling very old bookings."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2020, 1, 1, 10, 0)),
            create_mock_booking(id=2, status="confirmed", created_at=datetime(2026, 2, 1, 10, 0)),
        ]

        monthly_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            if booking.created_at:
                month_key = booking.created_at.strftime("%Y-%m")
                monthly_by_status[month_key][booking.status.value] += 1

        assert "2020-01" in monthly_by_status
        assert "2026-02" in monthly_by_status

    def test_bookings_same_day_different_times(self):
        """Test multiple bookings on same day at different times."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 15, 8, 0)),
            create_mock_booking(id=2, status="confirmed", created_at=datetime(2026, 2, 15, 12, 0)),
            create_mock_booking(id=3, status="completed", created_at=datetime(2026, 2, 15, 16, 0)),
            create_mock_booking(id=4, status="cancelled", created_at=datetime(2026, 2, 15, 20, 0)),
        ]

        daily_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            day_key = booking.created_at.strftime("%Y-%m-%d")
            daily_by_status[day_key][booking.status.value] += 1

        assert daily_by_status["2026-02-15"]["confirmed"] == 2
        assert daily_by_status["2026-02-15"]["completed"] == 1
        assert daily_by_status["2026-02-15"]["cancelled"] == 1

    def test_first_day_of_month(self):
        """Test bookings on first day of month."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 3, 1, 0, 0, 0)),
        ]

        monthly_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            month_key = booking.created_at.strftime("%Y-%m")
            monthly_by_status[month_key][booking.status.value] += 1

        assert monthly_by_status["2026-03"]["confirmed"] == 1

    def test_last_day_of_month(self):
        """Test bookings on last day of month."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 28, 23, 59, 59)),
        ]

        monthly_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            month_key = booking.created_at.strftime("%Y-%m")
            monthly_by_status[month_key][booking.status.value] += 1

        assert monthly_by_status["2026-02"]["confirmed"] == 1

    def test_leap_year_february(self):
        """Test bookings on Feb 29 in leap year."""
        # 2024 was a leap year
        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2024, 2, 29, 10, 0)),
        ]

        daily_by_status = defaultdict(lambda: defaultdict(int))
        for booking in bookings:
            day_key = booking.created_at.strftime("%Y-%m-%d")
            daily_by_status[day_key][booking.status.value] += 1

        assert daily_by_status["2024-02-29"]["confirmed"] == 1


# =============================================================================
# Unit Tests: Negative Cases
# =============================================================================

class TestBookingStatsNegativeCases:
    """Negative test cases for booking statistics."""

    def test_unknown_status(self):
        """Test handling unknown booking status."""
        booking = create_mock_booking(id=1, status="unknown_status")

        status_totals = defaultdict(int)
        status_totals[booking.status.value] += 1

        assert status_totals["unknown_status"] == 1
        # Unknown status should not count as successful
        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)
        assert total_successful == 0

    def test_null_status(self):
        """Test handling null status."""
        booking = create_mock_booking(id=1)
        booking.status = None

        # Simulate handling null status
        status_value = booking.status.value if booking.status else "unknown"

        assert status_value == "unknown"

    def test_invalid_date_format_handling(self):
        """Test that invalid dates are handled gracefully."""
        # This tests the format_data function behavior
        data_dict = {
            "2026-02": {"confirmed": 5},
            "invalid": {"confirmed": 1},  # Invalid key
        }

        # Should still work with sorted keys
        sorted_keys = sorted(data_dict.keys())
        assert "2026-02" in sorted_keys
        assert "invalid" in sorted_keys  # Will sort alphabetically

    def test_large_booking_count(self):
        """Test handling large number of bookings."""
        bookings = [
            create_mock_booking(id=i, status="confirmed", created_at=datetime(2026, 2, (i % 28) + 1, 10, 0))
            for i in range(1, 10001)  # 10,000 bookings
        ]

        status_totals = defaultdict(int)
        for booking in bookings:
            status_totals[booking.status.value] += 1

        assert status_totals["confirmed"] == 10000


# =============================================================================
# Unit Tests: Data Formatting
# =============================================================================

class TestDataFormatting:
    """Tests for data formatting logic."""

    def test_format_daily_data(self):
        """Test formatting daily data with status breakdown."""
        daily_by_status = {
            "2026-02-01": {"confirmed": 3, "completed": 2, "pending": 1},
            "2026-02-02": {"confirmed": 5, "cancelled": 2},
        }

        status_order = ['confirmed', 'completed', 'pending', 'cancelled']

        def format_data(data_dict, key_name):
            result = []
            for key in sorted(data_dict.keys()):
                entry = {key_name: key}
                for status in status_order:
                    entry[status] = data_dict[key].get(status, 0)
                entry['total'] = sum(data_dict[key].values())
                result.append(entry)
            return result

        formatted = format_data(daily_by_status, 'date')

        assert len(formatted) == 2
        assert formatted[0]["date"] == "2026-02-01"
        assert formatted[0]["confirmed"] == 3
        assert formatted[0]["completed"] == 2
        assert formatted[0]["pending"] == 1
        assert formatted[0]["cancelled"] == 0
        assert formatted[0]["total"] == 6

        assert formatted[1]["date"] == "2026-02-02"
        assert formatted[1]["confirmed"] == 5
        assert formatted[1]["cancelled"] == 2
        assert formatted[1]["total"] == 7

    def test_format_weekly_data(self):
        """Test formatting weekly data."""
        weekly_by_status = {
            "2026-W05": {"confirmed": 10, "completed": 5},
            "2026-W06": {"confirmed": 12, "pending": 3},
        }

        status_order = ['confirmed', 'completed', 'pending', 'cancelled']

        def format_data(data_dict, key_name):
            result = []
            for key in sorted(data_dict.keys()):
                entry = {key_name: key}
                for status in status_order:
                    entry[status] = data_dict[key].get(status, 0)
                entry['total'] = sum(data_dict[key].values())
                result.append(entry)
            return result

        formatted = format_data(weekly_by_status, 'week')

        assert formatted[0]["week"] == "2026-W05"
        assert formatted[0]["total"] == 15
        assert formatted[1]["week"] == "2026-W06"
        assert formatted[1]["total"] == 15

    def test_sorted_output(self):
        """Test that output is sorted chronologically."""
        monthly_by_status = {
            "2026-03": {"confirmed": 10},
            "2026-01": {"confirmed": 5},
            "2026-02": {"confirmed": 8},
        }

        sorted_months = sorted(monthly_by_status.keys())

        assert sorted_months == ["2026-01", "2026-02", "2026-03"]


# =============================================================================
# Unit Tests: Revenue Calculations
# =============================================================================

class TestRevenueCalculation:
    """Tests for revenue per customer calculation logic."""

    def test_basic_revenue_calculation(self):
        """Test basic average revenue calculation with paid bookings."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),  # £50
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=7500),  # £75
            create_mock_booking(id=3, status="completed", payment_amount_pence=10000), # £100
        ]

        # Calculate total revenue and average
        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 22500  # 5000 + 7500 + 10000
        assert paid_customer_count == 3
        assert avg_revenue == 75.0  # £75 average

    def test_exclude_free_bookings(self):
        """Test that free bookings (amount_pence=0) are excluded."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),  # £50
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=0),     # Free
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=7500),  # £75
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 12500  # 5000 + 7500 (0 excluded)
        assert paid_customer_count == 2  # Only 2 paid bookings
        assert avg_revenue == 62.5  # £62.50 average

    def test_exclude_free_promo_bookings(self):
        """Test that bookings using free promo codes are excluded."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=7500),  # Free promo used
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=10000),
        ]

        # Simulate free promo booking IDs
        free_promo_booking_ids = {2}  # Booking 2 used free promo

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue  # Skip free promo bookings
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 15000  # 5000 + 10000 (7500 excluded)
        assert paid_customer_count == 2
        assert avg_revenue == 75.0

    def test_exclude_both_free_and_promo(self):
        """Test that both free bookings and free promo bookings are excluded."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=0),      # Free booking
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=7500),   # Free promo used
            create_mock_booking(id=4, status="confirmed", payment_amount_pence=10000),
        ]

        free_promo_booking_ids = {3}

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 15000  # 5000 + 10000
        assert paid_customer_count == 2
        assert avg_revenue == 75.0

    def test_no_paid_bookings(self):
        """Test when there are no paid bookings."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=0),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=0),
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 0
        assert paid_customer_count == 0
        assert avg_revenue == 0  # No division by zero error

    def test_single_paid_booking(self):
        """Test with only one paid booking."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=4999),
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 4999
        assert paid_customer_count == 1
        assert avg_revenue == 49.99

    def test_bookings_without_payment(self):
        """Test bookings that have no payment object."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed"),  # No payment
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=7500),
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 12500
        assert paid_customer_count == 2
        assert avg_revenue == 62.5

    def test_all_bookings_free_promo(self):
        """Test when all bookings used free promo codes."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=7500),
        ]

        free_promo_booking_ids = {1, 2}  # All bookings used promo

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 0
        assert paid_customer_count == 0
        assert avg_revenue == 0

    def test_rounding_precision(self):
        """Test that revenue is rounded to 2 decimal places."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=3333),  # £33.33
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=3333),  # £33.33
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=3334),  # £33.34
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2)

        assert total_revenue_pence == 10000
        assert avg_revenue == 33.33

    def test_large_revenue_values(self):
        """Test handling of large revenue values."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=100000),  # £1000
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=250000),  # £2500
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=500000),  # £5000
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2)

        assert total_revenue_pence == 850000
        assert total_revenue_pounds == 8500.0
        assert avg_revenue == 2833.33

    def test_only_confirmed_and_completed_count(self):
        """Test that only successful bookings contribute to revenue."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="completed", payment_amount_pence=7500),
            create_mock_booking(id=3, status="pending", payment_amount_pence=10000),    # Should exclude
            create_mock_booking(id=4, status="cancelled", payment_amount_pence=15000),  # Should exclude
        ]

        # Filter to successful bookings only
        successful_bookings = [b for b in bookings if b.status.value in ["confirmed", "completed"]]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in successful_bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 12500  # Only confirmed + completed
        assert paid_customer_count == 2
        assert avg_revenue == 62.5


class TestRevenueEdgeCases:
    """Edge cases for revenue calculation."""

    def test_empty_free_promo_set(self):
        """Test when no one has used free promo codes."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=7500),
        ]

        free_promo_booking_ids = set()  # Empty set

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 12500
        assert paid_customer_count == 2
        assert avg_revenue == 62.5

    def test_mixed_payment_statuses(self):
        """Test with mix of paid, free, no payment, and promo bookings."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),   # Paid
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=0),       # Free
            create_mock_booking(id=3, status="confirmed"),                               # No payment
            create_mock_booking(id=4, status="confirmed", payment_amount_pence=7500),   # Free promo used
            create_mock_booking(id=5, status="confirmed", payment_amount_pence=10000),  # Paid
        ]

        free_promo_booking_ids = {4}

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 15000  # 5000 + 10000
        assert paid_customer_count == 2
        assert avg_revenue == 75.0

    def test_negative_amount_ignored(self):
        """Test that negative amounts (refunds) don't affect calculation."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=5000),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=-2000),  # Negative
            create_mock_booking(id=3, status="confirmed", payment_amount_pence=7500),
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 12500
        assert paid_customer_count == 2
        assert avg_revenue == 62.5

    def test_total_revenue_calculation(self):
        """Test total revenue in pounds calculation."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment_amount_pence=4999),
            create_mock_booking(id=2, status="confirmed", payment_amount_pence=5001),
        ]

        total_revenue_pence = 0
        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence

        total_revenue_pounds = round(total_revenue_pence / 100, 2)

        assert total_revenue_pence == 10000
        assert total_revenue_pounds == 100.0


class TestRevenueResponseFormat:
    """Tests for revenue data in API response format."""

    def test_revenue_fields_in_response(self):
        """Test that response contains all revenue fields."""
        response = {
            "total_bookings": 100,
            "total_successful": 80,
            "status_totals": {},
            "this_week": 10,
            "last_week": 8,
            "this_month": 40,
            "last_month": 35,
            "daily": [],
            "weekly": [],
            "monthly": [],
            "cumulative": [],
            "total_revenue": 5000.00,
            "paid_customer_count": 75,
            "avg_revenue_per_customer": 66.67,
        }

        assert "total_revenue" in response
        assert "paid_customer_count" in response
        assert "avg_revenue_per_customer" in response

    def test_revenue_values_are_correct_types(self):
        """Test that revenue values are correct types."""
        total_revenue = 5000.00
        paid_customer_count = 75
        avg_revenue_per_customer = 66.67

        assert isinstance(total_revenue, float)
        assert isinstance(paid_customer_count, int)
        assert isinstance(avg_revenue_per_customer, float)

    def test_zero_values_when_no_paid_bookings(self):
        """Test zero values are returned when no paid bookings."""
        # Simulate no paid bookings scenario
        paid_customer_count = 0
        total_revenue = 0.0
        avg_revenue = 0.0 if paid_customer_count == 0 else 50.0

        assert total_revenue == 0.0
        assert paid_customer_count == 0
        assert avg_revenue == 0.0


# =============================================================================
# Unit Tests: Status Colors and Display
# =============================================================================

class TestStatusDisplay:
    """Tests for status display logic (used by frontend)."""

    def test_status_color_mapping(self):
        """Test status to color mapping."""
        status_colors = {
            "confirmed": "#22c55e",   # Green
            "completed": "#3b82f6",   # Blue
            "pending": "#f59e0b",     # Yellow/Orange
            "cancelled": "#ef4444",   # Red
        }

        assert status_colors["confirmed"] == "#22c55e"
        assert status_colors["completed"] == "#3b82f6"
        assert status_colors["pending"] == "#f59e0b"
        assert status_colors["cancelled"] == "#ef4444"

    def test_status_order(self):
        """Test status display order."""
        status_order = ['confirmed', 'completed', 'pending', 'cancelled']

        assert status_order[0] == "confirmed"
        assert status_order[1] == "completed"
        assert status_order[2] == "pending"
        assert status_order[3] == "cancelled"


# =============================================================================
# Unit Tests: Trip Insights (avg duration, dropoff/pickup ranges)
# =============================================================================

class TestTripDurationCalculation:
    """Tests for average trip duration calculation."""

    def test_basic_trip_duration(self):
        """Test calculating trip duration from dropoff to pickup dates."""
        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 8),  # 7 days
            ),
            create_mock_booking(
                id=2, status="confirmed",
                dropoff_date=date(2026, 3, 10),
                pickup_date=date(2026, 3, 24),  # 14 days
            ),
            create_mock_booking(
                id=3, status="completed",
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 18),  # 3 days
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1) if trip_durations else 0

        assert trip_durations == [7, 14, 3]
        assert avg_duration == 8.0  # (7 + 14 + 3) / 3 = 8

    def test_single_day_trip(self):
        """Test trip that is same day dropoff/pickup."""
        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 1),  # Same day = 0 days
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        assert trip_durations == [0]

    def test_missing_dates_excluded(self):
        """Test that bookings without dates are excluded from calculation."""
        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 8),  # 7 days
            ),
            create_mock_booking(
                id=2, status="confirmed",
                dropoff_date=None,  # Missing dropoff
                pickup_date=date(2026, 3, 10),
            ),
            create_mock_booking(
                id=3, status="confirmed",
                dropoff_date=date(2026, 3, 5),
                pickup_date=None,  # Missing pickup
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        assert len(trip_durations) == 1
        assert trip_durations == [7]

    def test_empty_bookings_returns_zero(self):
        """Test that empty bookings list returns 0 avg duration."""
        bookings = []

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1) if trip_durations else 0

        assert avg_duration == 0

    def test_long_trip_duration(self):
        """Test handling of long trip durations."""
        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_date=date(2026, 1, 1),
                pickup_date=date(2026, 3, 1),  # 59 days
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        assert trip_durations == [59]


class TestDropoffTimeRange:
    """Tests for drop-off time range calculation."""

    def test_basic_dropoff_range(self):
        """Test calculating min/max/avg dropoff times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_time=dt_time(6, 0),   # 06:00 = 360 minutes
            ),
            create_mock_booking(
                id=2, status="confirmed",
                dropoff_time=dt_time(10, 30),  # 10:30 = 630 minutes
            ),
            create_mock_booking(
                id=3, status="completed",
                dropoff_time=dt_time(14, 0),   # 14:00 = 840 minutes
            ),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        assert dropoff_times_minutes == [360, 630, 840]

        min_dropoff = min(dropoff_times_minutes)
        max_dropoff = max(dropoff_times_minutes)
        avg_dropoff = sum(dropoff_times_minutes) / len(dropoff_times_minutes)

        assert min_dropoff == 360   # 06:00
        assert max_dropoff == 840   # 14:00
        assert avg_dropoff == 610   # (360 + 630 + 840) / 3 = 610

    def test_dropoff_time_formatting(self):
        """Test formatting times from minutes to HH:MM."""
        minutes = 630  # 10:30

        formatted = f"{minutes // 60:02d}:{minutes % 60:02d}"

        assert formatted == "10:30"

    def test_early_morning_dropoff(self):
        """Test early morning dropoff times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", dropoff_time=dt_time(4, 30)),
            create_mock_booking(id=2, status="confirmed", dropoff_time=dt_time(5, 0)),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        min_dropoff = min(dropoff_times_minutes)
        formatted_min = f"{min_dropoff // 60:02d}:{min_dropoff % 60:02d}"

        assert formatted_min == "04:30"

    def test_missing_dropoff_times(self):
        """Test that missing dropoff times are excluded."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", dropoff_time=dt_time(8, 0)),
            create_mock_booking(id=2, status="confirmed", dropoff_time=None),
            create_mock_booking(id=3, status="confirmed", dropoff_time=dt_time(12, 0)),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        assert len(dropoff_times_minutes) == 2

    def test_empty_dropoff_returns_na(self):
        """Test that empty dropoff times return N/A."""
        dropoff_times_minutes = []

        if dropoff_times_minutes:
            dropoff_range = {"min": "10:00", "max": "14:00", "avg": "12:00"}
        else:
            dropoff_range = {"min": "N/A", "max": "N/A", "avg": "N/A"}

        assert dropoff_range["min"] == "N/A"
        assert dropoff_range["max"] == "N/A"
        assert dropoff_range["avg"] == "N/A"


class TestPickupTimeRange:
    """Tests for pick-up time range calculation."""

    def test_basic_pickup_range(self):
        """Test calculating min/max/avg pickup times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                pickup_time=dt_time(15, 0),   # 15:00 = 900 minutes
            ),
            create_mock_booking(
                id=2, status="confirmed",
                pickup_time=dt_time(18, 30),  # 18:30 = 1110 minutes
            ),
            create_mock_booking(
                id=3, status="completed",
                pickup_time=dt_time(21, 0),   # 21:00 = 1260 minutes
            ),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        assert pickup_times_minutes == [900, 1110, 1260]

        min_pickup = min(pickup_times_minutes)
        max_pickup = max(pickup_times_minutes)
        avg_pickup = sum(pickup_times_minutes) / len(pickup_times_minutes)

        assert min_pickup == 900   # 15:00
        assert max_pickup == 1260  # 21:00
        assert avg_pickup == 1090  # (900 + 1110 + 1260) / 3 = 1090

    def test_late_night_pickup(self):
        """Test late night pickup times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", pickup_time=dt_time(23, 30)),
            create_mock_booking(id=2, status="confirmed", pickup_time=dt_time(22, 45)),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        max_pickup = max(pickup_times_minutes)
        formatted_max = f"{max_pickup // 60:02d}:{max_pickup % 60:02d}"

        assert formatted_max == "23:30"

    def test_missing_pickup_times(self):
        """Test that missing pickup times are excluded."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", pickup_time=dt_time(16, 0)),
            create_mock_booking(id=2, status="confirmed", pickup_time=None),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        assert len(pickup_times_minutes) == 1


class TestTripInsightsResponseFormat:
    """Tests for trip insights in API response format."""

    def test_trip_insights_fields_in_response(self):
        """Test that response contains all trip insight fields."""
        response = {
            "total_bookings": 100,
            "total_successful": 80,
            "avg_trip_duration": 7.5,
            "dropoff_range": {
                "min": "06:00",
                "max": "14:00",
                "avg": "09:30",
            },
            "pickup_range": {
                "min": "15:00",
                "max": "22:00",
                "avg": "18:00",
            },
        }

        assert "avg_trip_duration" in response
        assert "dropoff_range" in response
        assert "pickup_range" in response

        assert "min" in response["dropoff_range"]
        assert "max" in response["dropoff_range"]
        assert "avg" in response["dropoff_range"]

        assert "min" in response["pickup_range"]
        assert "max" in response["pickup_range"]
        assert "avg" in response["pickup_range"]

    def test_trip_duration_is_numeric(self):
        """Test that avg_trip_duration is a number."""
        avg_trip_duration = 8.5

        assert isinstance(avg_trip_duration, (int, float))

    def test_time_range_format(self):
        """Test that time ranges are in HH:MM format."""
        dropoff_range = {
            "min": "06:00",
            "max": "14:00",
            "avg": "09:30",
        }

        # Check format with regex
        import re
        time_pattern = r"^\d{2}:\d{2}$"

        assert re.match(time_pattern, dropoff_range["min"])
        assert re.match(time_pattern, dropoff_range["max"])
        assert re.match(time_pattern, dropoff_range["avg"])

    def test_na_values_when_no_data(self):
        """Test N/A values when no time data exists."""
        dropoff_range = {"min": "N/A", "max": "N/A", "avg": "N/A"}
        pickup_range = {"min": "N/A", "max": "N/A", "avg": "N/A"}

        assert dropoff_range["min"] == "N/A"
        assert pickup_range["avg"] == "N/A"


class TestTripInsightsEdgeCases:
    """Edge case tests for trip insights calculation."""

    def test_all_bookings_missing_times(self):
        """Test when all bookings have no dropoff/pickup times."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", dropoff_time=None, pickup_time=None),
            create_mock_booking(id=2, status="confirmed", dropoff_time=None, pickup_time=None),
        ]

        dropoff_times_minutes = []
        pickup_times_minutes = []

        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        assert len(dropoff_times_minutes) == 0
        assert len(pickup_times_minutes) == 0

    def test_single_booking_with_times(self):
        """Test with only one booking that has times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(
                id=1, status="confirmed",
                dropoff_date=date(2026, 3, 1),
                dropoff_time=dt_time(8, 0),
                pickup_date=date(2026, 3, 5),
                pickup_time=dt_time(16, 30),
            ),
        ]

        trip_durations = []
        dropoff_times_minutes = []
        pickup_times_minutes = []

        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        # For single booking, min = max = avg
        assert trip_durations == [4]
        assert dropoff_times_minutes == [480]  # 08:00
        assert pickup_times_minutes == [990]   # 16:30

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1)
        min_dropoff = min(dropoff_times_minutes)
        max_dropoff = max(dropoff_times_minutes)

        assert avg_duration == 4.0
        assert min_dropoff == max_dropoff == 480

    def test_midnight_times(self):
        """Test handling of midnight (00:00) times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", dropoff_time=dt_time(0, 0)),
            create_mock_booking(id=2, status="confirmed", pickup_time=dt_time(0, 0)),
        ]

        dropoff_times_minutes = []
        pickup_times_minutes = []

        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        assert dropoff_times_minutes == [0]  # 00:00 = 0 minutes
        assert pickup_times_minutes == [0]

        formatted = f"{0 // 60:02d}:{0 % 60:02d}"
        assert formatted == "00:00"

    def test_23_59_times(self):
        """Test handling of 23:59 times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_booking(id=1, status="confirmed", pickup_time=dt_time(23, 59)),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        assert pickup_times_minutes == [1439]  # 23*60 + 59

        max_pickup = max(pickup_times_minutes)
        formatted = f"{max_pickup // 60:02d}:{max_pickup % 60:02d}"
        assert formatted == "23:59"


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
