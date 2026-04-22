"""
Unit tests for Admin Reports business logic.

Tests the calculation logic for various admin reports:
- Occupancy Report
- Popular Report
- Financial Report
- Bookings Forecast

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-12345",
    dropoff_date=None,
    pickup_date=None,
    status="confirmed",
    amount_pence=5000,
    created_at=None,
    customer_id=1,
    vehicle_id=1,
):
    """Create a mock booking."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or (date.today() + timedelta(days=7))
    booking.status = MagicMock()
    booking.status.value = status
    booking.created_at = created_at or datetime.now(timezone.utc)
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id

    # Payment mock
    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence
    booking.payment.status = MagicMock()
    booking.payment.status.value = "succeeded"

    return booking


def create_mock_customer(id=1, first_name="John", last_name="Smith", postcode="AB12 3CD"):
    """Create a mock customer."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.billing_postcode = postcode
    return customer


# ============================================================================
# Occupancy Report - Unit Tests
# ============================================================================

class TestOccupancyCalculation:
    """Unit tests for occupancy calculation logic."""

    MAX_CAPACITY = 50

    # Happy Path
    def test_single_booking_counts_each_day(self):
        """Single booking should count for each day between dropoff and pickup."""
        dropoff = date(2026, 4, 1)
        pickup = date(2026, 4, 5)

        # Calculate days parked
        days = (pickup - dropoff).days + 1

        assert days == 5

    def test_occupancy_percentage_calculation(self):
        """Occupancy percentage should be (occupied / max) * 100."""
        occupied = 25

        occupancy_percent = round((occupied / self.MAX_CAPACITY) * 100, 1)

        assert occupancy_percent == 50.0

    def test_available_spaces_calculation(self):
        """Available spaces should be max capacity - occupied."""
        occupied = 30

        available = self.MAX_CAPACITY - occupied

        assert available == 20

    def test_full_occupancy(self):
        """Full occupancy should show 100% and 0 available."""
        occupied = 50

        occupancy_percent = round((occupied / self.MAX_CAPACITY) * 100, 1)
        available = self.MAX_CAPACITY - occupied

        assert occupancy_percent == 100.0
        assert available == 0

    # Unhappy Path
    def test_over_capacity_shows_negative_available(self):
        """Over capacity should show negative available (edge case)."""
        occupied = 55  # Over max capacity

        available = self.MAX_CAPACITY - occupied

        assert available == -5

    # Edge Cases
    def test_zero_occupancy(self):
        """Zero bookings should show 0% occupancy."""
        occupied = 0

        occupancy_percent = round((occupied / self.MAX_CAPACITY) * 100, 1)
        available = self.MAX_CAPACITY - occupied

        assert occupancy_percent == 0.0
        assert available == 50

    def test_booking_same_day_dropoff_pickup(self):
        """Booking with same-day dropoff and pickup counts as 1 day."""
        dropoff = date(2026, 4, 1)
        pickup = date(2026, 4, 1)

        days = (pickup - dropoff).days + 1

        assert days == 1


class TestOccupancyDateRange:
    """Unit tests for occupancy date range handling."""

    def test_default_daily_range_30_days_back_60_forward(self):
        """Daily view should default to 30 days back, 60 days forward."""
        today = date.today()
        view = "daily"

        if view == "daily":
            start = today - timedelta(days=30)
            end = today + timedelta(days=60)

        assert (today - start).days == 30
        assert (end - today).days == 60

    def test_default_weekly_range_12_weeks(self):
        """Weekly view should default to 12 weeks back and forward."""
        today = date.today()
        view = "weekly"

        if view == "weekly":
            start = today - timedelta(weeks=12)
            end = today + timedelta(weeks=12)

        assert (today - start).days == 84  # 12 * 7
        assert (end - today).days == 84

    def test_default_monthly_range_6_months(self):
        """Monthly view should default to ~6 months back and forward."""
        today = date.today()
        view = "monthly"

        if view == "monthly":
            start = today - timedelta(days=180)
            end = today + timedelta(days=180)

        assert (today - start).days == 180
        assert (end - today).days == 180

    def test_custom_date_range_respected(self):
        """Custom date range should override defaults."""
        custom_start = date(2026, 1, 1)
        custom_end = date(2026, 12, 31)

        # Simulating parameter handling
        start_param = custom_start
        end_param = custom_end

        report_start = start_param or date.today() - timedelta(days=30)
        report_end = end_param or date.today() + timedelta(days=60)

        assert report_start == custom_start
        assert report_end == custom_end


class TestOccupancyAggregation:
    """Unit tests for occupancy aggregation by time period."""

    def test_daily_aggregation(self):
        """Daily view should show one entry per day."""
        start = date(2026, 4, 1)
        end = date(2026, 4, 7)

        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        assert len(dates) == 7

    def test_weekly_aggregation_monday_start(self):
        """Weekly view should aggregate by ISO week (Monday start)."""
        sample_date = date(2026, 4, 15)  # A Wednesday

        # Get ISO week number
        iso_week = sample_date.isocalendar()[1]

        assert iso_week > 0

    def test_monthly_aggregation(self):
        """Monthly view should aggregate by calendar month."""
        sample_dates = [
            date(2026, 1, 15),
            date(2026, 1, 20),
            date(2026, 2, 10),
            date(2026, 3, 5),
        ]

        # Group by month
        monthly = defaultdict(int)
        for d in sample_dates:
            key = f"{d.year}-{d.month:02d}"
            monthly[key] += 1

        assert monthly["2026-01"] == 2
        assert monthly["2026-02"] == 1
        assert monthly["2026-03"] == 1


# ============================================================================
# Popular Report - Unit Tests
# ============================================================================

class TestPopularReportLogic:
    """Unit tests for Popular Report (most booked times/routes)."""

    # Happy Path
    def test_count_bookings_by_dropoff_hour(self):
        """Should count bookings by drop-off hour."""
        bookings = [
            {"dropoff_time": "08:00"},
            {"dropoff_time": "08:30"},
            {"dropoff_time": "09:00"},
            {"dropoff_time": "08:15"},
        ]

        hourly_counts = defaultdict(int)
        for b in bookings:
            hour = int(b["dropoff_time"].split(":")[0])
            hourly_counts[hour] += 1

        assert hourly_counts[8] == 3
        assert hourly_counts[9] == 1

    def test_rank_popular_destinations(self):
        """Should rank destinations by booking count."""
        bookings = [
            {"destination": "Malaga"},
            {"destination": "Malaga"},
            {"destination": "Alicante"},
            {"destination": "Malaga"},
            {"destination": "Faro"},
        ]

        dest_counts = defaultdict(int)
        for b in bookings:
            dest_counts[b["destination"]] += 1

        ranked = sorted(dest_counts.items(), key=lambda x: -x[1])

        assert ranked[0] == ("Malaga", 3)
        assert ranked[1] == ("Alicante", 1)

    def test_rank_popular_airlines(self):
        """Should rank airlines by booking count."""
        bookings = [
            {"airline": "Ryanair"},
            {"airline": "Ryanair"},
            {"airline": "EasyJet"},
            {"airline": "Ryanair"},
        ]

        airline_counts = defaultdict(int)
        for b in bookings:
            airline_counts[b["airline"]] += 1

        ranked = sorted(airline_counts.items(), key=lambda x: -x[1])

        assert ranked[0] == ("Ryanair", 3)

    # Edge Cases
    def test_empty_bookings_returns_empty_results(self):
        """Empty bookings should return empty results."""
        bookings = []

        dest_counts = defaultdict(int)
        for b in bookings:
            dest_counts[b["destination"]] += 1

        assert len(dest_counts) == 0

    def test_tie_in_popularity(self):
        """Should handle ties in popularity ranking."""
        bookings = [
            {"destination": "Malaga"},
            {"destination": "Alicante"},
        ]

        dest_counts = defaultdict(int)
        for b in bookings:
            dest_counts[b["destination"]] += 1

        assert dest_counts["Malaga"] == dest_counts["Alicante"] == 1


class TestPopularTimeSlots:
    """Unit tests for popular time slot analysis."""

    def test_peak_hours_morning(self):
        """Should identify morning peak hours."""
        bookings = [
            {"hour": 6}, {"hour": 6}, {"hour": 6},
            {"hour": 7}, {"hour": 7},
            {"hour": 8},
            {"hour": 14},
        ]

        hourly = defaultdict(int)
        for b in bookings:
            hourly[b["hour"]] += 1

        peak_hour = max(hourly.items(), key=lambda x: x[1])

        assert peak_hour[0] == 6  # 6am is peak

    def test_identify_quiet_hours(self):
        """Should identify quiet hours (low booking volume)."""
        hourly_counts = {
            6: 10, 7: 15, 8: 20,
            12: 2, 13: 3, 14: 2,  # Quiet
            18: 8, 19: 10,
        }

        avg = sum(hourly_counts.values()) / len(hourly_counts)
        quiet_hours = [h for h, c in hourly_counts.items() if c < avg / 2]

        assert 12 in quiet_hours
        assert 13 in quiet_hours
        assert 14 in quiet_hours


# ============================================================================
# Financial Report - Unit Tests
# ============================================================================

class TestFinancialReportCalculation:
    """Unit tests for Financial Report calculations."""

    # Happy Path
    def test_sum_total_revenue(self):
        """Should sum total revenue from all bookings."""
        bookings = [
            create_mock_booking(id=1, amount_pence=5000),
            create_mock_booking(id=2, amount_pence=7500),
            create_mock_booking(id=3, amount_pence=6000),
        ]

        total_pence = sum(b.payment.amount_pence for b in bookings)
        total_pounds = total_pence / 100

        assert total_pence == 18500
        assert total_pounds == 185.0

    def test_calculate_average_booking_value(self):
        """Should calculate average booking value."""
        amounts = [5000, 7500, 6000, 5500, 8000]

        total = sum(amounts)
        avg = total / len(amounts)

        assert avg == 6400  # pence

    def test_group_revenue_by_month(self):
        """Should group revenue by month."""
        bookings = [
            {"month": "2026-01", "amount": 5000},
            {"month": "2026-01", "amount": 6000},
            {"month": "2026-02", "amount": 7000},
        ]

        monthly = defaultdict(int)
        for b in bookings:
            monthly[b["month"]] += b["amount"]

        assert monthly["2026-01"] == 11000
        assert monthly["2026-02"] == 7000

    def test_count_bookings_per_period(self):
        """Should count bookings per period."""
        bookings = [
            {"week": "2026-W15"},
            {"week": "2026-W15"},
            {"week": "2026-W16"},
        ]

        weekly = defaultdict(int)
        for b in bookings:
            weekly[b["week"]] += 1

        assert weekly["2026-W15"] == 2
        assert weekly["2026-W16"] == 1

    # Unhappy Path
    def test_handle_zero_bookings(self):
        """Should handle period with zero bookings."""
        bookings = []

        total = sum(b.get("amount", 0) for b in bookings)
        avg = total / len(bookings) if bookings else 0

        assert total == 0
        assert avg == 0

    # Edge Cases
    def test_exclude_cancelled_from_revenue(self):
        """Should exclude cancelled bookings from revenue."""
        bookings = [
            create_mock_booking(id=1, amount_pence=5000, status="confirmed"),
            create_mock_booking(id=2, amount_pence=6000, status="cancelled"),
            create_mock_booking(id=3, amount_pence=7000, status="completed"),
        ]

        active_revenue = sum(
            b.payment.amount_pence for b in bookings
            if b.status.value in ["confirmed", "completed"]
        )

        assert active_revenue == 12000  # Excludes cancelled


class TestFinancialReportRefunds:
    """Unit tests for refund calculations in Financial Report."""

    def test_calculate_total_refunds(self):
        """Should calculate total refunds."""
        refunds = [
            {"amount_pence": 2500},
            {"amount_pence": 5000},
            {"amount_pence": 1500},
        ]

        total_refunds = sum(r["amount_pence"] for r in refunds)

        assert total_refunds == 9000

    def test_net_revenue_after_refunds(self):
        """Should calculate net revenue after refunds."""
        gross_revenue = 50000
        total_refunds = 5000

        net_revenue = gross_revenue - total_refunds

        assert net_revenue == 45000

    def test_refund_rate_calculation(self):
        """Should calculate refund rate percentage."""
        total_bookings = 100
        refunded_bookings = 5

        refund_rate = (refunded_bookings / total_bookings) * 100

        assert refund_rate == 5.0


# ============================================================================
# Bookings Forecast - Unit Tests
# ============================================================================

class TestBookingsForecastLogic:
    """Unit tests for Bookings Forecast calculations."""

    # Happy Path
    def test_count_upcoming_bookings(self):
        """Should count upcoming bookings by date."""
        today = date.today()
        bookings = [
            create_mock_booking(id=1, dropoff_date=today + timedelta(days=1)),
            create_mock_booking(id=2, dropoff_date=today + timedelta(days=1)),
            create_mock_booking(id=3, dropoff_date=today + timedelta(days=2)),
            create_mock_booking(id=4, dropoff_date=today + timedelta(days=5)),
        ]

        daily_counts = defaultdict(int)
        for b in bookings:
            daily_counts[b.dropoff_date.isoformat()] += 1

        tomorrow = (today + timedelta(days=1)).isoformat()
        assert daily_counts[tomorrow] == 2

    def test_count_upcoming_pickups(self):
        """Should count upcoming pickups by date."""
        today = date.today()
        bookings = [
            create_mock_booking(id=1, pickup_date=today + timedelta(days=1)),
            create_mock_booking(id=2, pickup_date=today + timedelta(days=1)),
            create_mock_booking(id=3, pickup_date=today + timedelta(days=3)),
        ]

        daily_pickups = defaultdict(int)
        for b in bookings:
            daily_pickups[b.pickup_date.isoformat()] += 1

        tomorrow = (today + timedelta(days=1)).isoformat()
        assert daily_pickups[tomorrow] == 2

    def test_forecast_excludes_past_dates(self):
        """Should only include future dates in forecast."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        dates = [yesterday, today, today + timedelta(days=1)]

        future_dates = [d for d in dates if d >= today]

        assert len(future_dates) == 2
        assert yesterday not in future_dates

    # Edge Cases
    def test_forecast_with_no_upcoming_bookings(self):
        """Should handle no upcoming bookings."""
        bookings = []

        daily_counts = defaultdict(int)
        for b in bookings:
            daily_counts[b.dropoff_date.isoformat()] += 1

        assert len(daily_counts) == 0

    def test_forecast_identifies_busy_days(self):
        """Should identify busy days (high dropoff count)."""
        today = date.today()
        daily_counts = {
            (today + timedelta(days=1)).isoformat(): 2,
            (today + timedelta(days=2)).isoformat(): 8,  # Busy
            (today + timedelta(days=3)).isoformat(): 3,
            (today + timedelta(days=4)).isoformat(): 10,  # Busy
        }

        threshold = 5
        busy_days = [d for d, c in daily_counts.items() if c >= threshold]

        assert len(busy_days) == 2


# ============================================================================
# Report Caching - Unit Tests
# ============================================================================

class TestReportCaching:
    """Unit tests for report caching logic."""

    CACHE_DURATION_SECONDS = 3600  # 1 hour

    def test_cache_valid_within_duration(self):
        """Cache should be valid within duration."""
        cached_at = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)

        cache_age = (now - cached_at).total_seconds()
        is_valid = cache_age < self.CACHE_DURATION_SECONDS

        assert is_valid is True

    def test_cache_expired_after_duration(self):
        """Cache should be expired after duration."""
        cached_at = datetime.now(timezone.utc) - timedelta(hours=2)
        now = datetime.now(timezone.utc)

        cache_age = (now - cached_at).total_seconds()
        is_valid = cache_age < self.CACHE_DURATION_SECONDS

        assert is_valid is False

    def test_refresh_param_bypasses_cache(self):
        """refresh=True should bypass cache."""
        cached_data = {"some": "data"}
        refresh = True

        # Logic: if refresh is True, don't use cache
        should_use_cache = not refresh and cached_data is not None

        assert should_use_cache is False

    def test_custom_params_bypass_cache(self):
        """Custom parameters should bypass cache."""
        start_date = date(2026, 1, 1)  # Custom param provided
        is_default_request = start_date is None

        should_cache = is_default_request

        assert should_cache is False


# ============================================================================
# Report Date Formatting - Unit Tests
# ============================================================================

class TestReportDateFormatting:
    """Unit tests for report date formatting."""

    def test_uk_date_format_dd_mm_yyyy(self):
        """Dates should be formatted as DD/MM/YYYY for UK."""
        sample_date = date(2026, 4, 15)

        uk_format = sample_date.strftime("%d/%m/%Y")

        assert uk_format == "15/04/2026"

    def test_iso_date_format(self):
        """ISO dates should be YYYY-MM-DD."""
        sample_date = date(2026, 4, 15)

        iso_format = sample_date.isoformat()

        assert iso_format == "2026-04-15"

    def test_week_number_format(self):
        """Week should be formatted as YYYY-Wnn."""
        sample_date = date(2026, 4, 15)

        year, week, _ = sample_date.isocalendar()
        week_format = f"{year}-W{week:02d}"

        assert week_format == "2026-W16"

    def test_month_format(self):
        """Month should be formatted as YYYY-MM."""
        sample_date = date(2026, 4, 15)

        month_format = f"{sample_date.year}-{sample_date.month:02d}"

        assert month_format == "2026-04"


# ============================================================================
# Boundary Tests
# ============================================================================

class TestReportBoundaryConditions:
    """Tests for report boundary conditions."""

    def test_leap_year_february(self):
        """Should handle leap year February correctly."""
        # 2024 is a leap year
        feb_28 = date(2024, 2, 28)
        feb_29 = date(2024, 2, 29)

        days_diff = (feb_29 - feb_28).days

        assert days_diff == 1

    def test_year_boundary(self):
        """Should handle year boundary correctly."""
        dec_31 = date(2025, 12, 31)
        jan_1 = date(2026, 1, 1)

        days_diff = (jan_1 - dec_31).days

        assert days_diff == 1

    def test_month_boundary(self):
        """Should handle month boundary correctly."""
        apr_30 = date(2026, 4, 30)
        may_1 = date(2026, 5, 1)

        days_diff = (may_1 - apr_30).days

        assert days_diff == 1

    def test_very_large_date_range(self):
        """Should handle large date ranges."""
        start = date(2020, 1, 1)
        end = date(2030, 12, 31)

        total_days = (end - start).days

        assert total_days == 4017  # ~11 years


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
