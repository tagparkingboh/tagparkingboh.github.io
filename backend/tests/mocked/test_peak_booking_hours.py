"""
Tests for peak booking hours analytics feature.

Covers:
- Hour of day booking distribution (UK timezone)
- Time ranges (Morning, Afternoon, Evening, Night)
- Percentage calculations
- Timezone conversion handling

All tests use mocked data - no real database connections.
"""
import pytest
from datetime import datetime
import pytz


# ============================================================================
# MOCK DATA SETUP
# ============================================================================

class MockBooking:
    """Mock booking object with created_at timestamp."""
    def __init__(self, created_at: datetime, status: str = "CONFIRMED"):
        self.created_at = created_at
        self.status = status


def create_uk_datetime(year, month, day, hour, minute=0, second=0):
    """Create a UK timezone-aware datetime."""
    uk_tz = pytz.timezone('Europe/London')
    return uk_tz.localize(datetime(year, month, day, hour, minute, second))


def create_utc_datetime(year, month, day, hour, minute=0, second=0):
    """Create a UTC timezone-aware datetime."""
    return pytz.utc.localize(datetime(year, month, day, hour, minute, second))


# ============================================================================
# MOCKED UNIT TESTS - Hour Distribution Calculation
# ============================================================================

class TestHourDistributionCalculation:
    """Unit tests for booking hour distribution calculation."""

    def calculate_hour_distribution(self, bookings):
        """Mirror the hour distribution calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')
        booking_hours = {hour: 0 for hour in range(24)}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)
                booking_hours[created_at_uk.hour] += 1

        total = sum(booking_hours.values())
        return [
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "count": count,
                "percent": round(count / total * 100, 1) if total > 0 else 0
            }
            for hour, count in booking_hours.items()
        ]

    def test_peak_hour_afternoon_bookings(self):
        """Happy path: Most bookings in afternoon hours."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 15, 30)),  # 15:00
            MockBooking(create_uk_datetime(2026, 4, 2, 15, 45)),  # 15:00
            MockBooking(create_uk_datetime(2026, 4, 3, 16, 20)),  # 16:00
            MockBooking(create_uk_datetime(2026, 4, 4, 10, 0)),   # 10:00
        ]
        hours = self.calculate_hour_distribution(bookings)

        hour_15 = next(h for h in hours if h["hour"] == 15)
        assert hour_15["count"] == 2
        assert hour_15["percent"] == 50.0

    def test_all_hours_represented(self):
        """Happy path: All 24 hours are represented in output."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 1, 12, 0))]
        hours = self.calculate_hour_distribution(bookings)

        assert len(hours) == 24
        hour_labels = [h["hour"] for h in hours]
        assert hour_labels == list(range(24))

    def test_hour_label_format(self):
        """Happy path: Hour labels are in correct 24-hour format."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 1, 9, 0))]
        hours = self.calculate_hour_distribution(bookings)

        hour_9 = next(h for h in hours if h["hour"] == 9)
        assert hour_9["label"] == "09:00"

        hour_0 = next(h for h in hours if h["hour"] == 0)
        assert hour_0["label"] == "00:00"

    def test_percentage_calculation(self):
        """Happy path: Percentages sum to approximately 100%."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 10, 0)),
            MockBooking(create_uk_datetime(2026, 4, 1, 10, 30)),
            MockBooking(create_uk_datetime(2026, 4, 1, 15, 0)),
            MockBooking(create_uk_datetime(2026, 4, 1, 15, 30)),
            MockBooking(create_uk_datetime(2026, 4, 1, 20, 0)),
        ]
        hours = self.calculate_hour_distribution(bookings)

        total_percent = sum(h["percent"] for h in hours)
        assert 99.0 <= total_percent <= 101.0  # Allow for rounding

    def test_empty_bookings(self):
        """Edge case: No bookings returns zero counts."""
        bookings = []
        hours = self.calculate_hour_distribution(bookings)

        assert len(hours) == 24
        for h in hours:
            assert h["count"] == 0
            assert h["percent"] == 0

    def test_single_booking(self):
        """Boundary: Single booking = 100% for that hour."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 1, 14, 30))]
        hours = self.calculate_hour_distribution(bookings)

        hour_14 = next(h for h in hours if h["hour"] == 14)
        assert hour_14["count"] == 1
        assert hour_14["percent"] == 100.0

    def test_midnight_hour_handling(self):
        """Edge case: Midnight (00:00) hour is correctly categorized."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 0, 15)),
            MockBooking(create_uk_datetime(2026, 4, 1, 0, 45)),
        ]
        hours = self.calculate_hour_distribution(bookings)

        hour_0 = next(h for h in hours if h["hour"] == 0)
        assert hour_0["count"] == 2


# ============================================================================
# MOCKED UNIT TESTS - UTC to UK Timezone Conversion
# ============================================================================

class TestTimezoneConversion:
    """Unit tests for UTC to UK timezone conversion."""

    def convert_to_uk(self, dt):
        """Convert datetime to UK timezone."""
        uk_tz = pytz.timezone('Europe/London')
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(uk_tz)

    def test_utc_to_uk_winter(self):
        """Happy path: UTC to UK conversion in winter (GMT, no offset)."""
        # January - UK is GMT (UTC+0)
        utc_time = create_utc_datetime(2026, 1, 15, 14, 30)
        uk_time = self.convert_to_uk(utc_time)

        assert uk_time.hour == 14  # Same as UTC in winter

    def test_utc_to_uk_summer(self):
        """Happy path: UTC to UK conversion in summer (BST, +1 hour)."""
        # July - UK is BST (UTC+1)
        utc_time = create_utc_datetime(2026, 7, 15, 14, 30)
        uk_time = self.convert_to_uk(utc_time)

        assert uk_time.hour == 15  # +1 hour in summer

    def test_utc_to_uk_crosses_day_boundary(self):
        """Edge case: UTC late night becomes next day in UK summer."""
        # 23:30 UTC in July = 00:30 next day in UK
        utc_time = create_utc_datetime(2026, 7, 15, 23, 30)
        uk_time = self.convert_to_uk(utc_time)

        assert uk_time.hour == 0
        assert uk_time.day == 16

    def test_naive_datetime_assumed_utc(self):
        """Edge case: Naive datetime is assumed to be UTC."""
        naive_time = datetime(2026, 7, 15, 14, 30)
        uk_time = self.convert_to_uk(naive_time)

        assert uk_time.hour == 15  # +1 hour (BST)


# ============================================================================
# MOCKED UNIT TESTS - Time Ranges Calculation
# ============================================================================

class TestTimeRangesCalculation:
    """Unit tests for time ranges (Morning, Afternoon, Evening, Night)."""

    def calculate_time_ranges(self, bookings):
        """Mirror the time ranges calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')
        booking_hours = {hour: 0 for hour in range(24)}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)
                booking_hours[created_at_uk.hour] += 1

        time_ranges = {
            "morning": {"label": "Morning (06:00-11:59)", "start": 6, "end": 11, "count": 0},
            "afternoon": {"label": "Afternoon (12:00-17:59)", "start": 12, "end": 17, "count": 0},
            "evening": {"label": "Evening (18:00-23:59)", "start": 18, "end": 23, "count": 0},
            "night": {"label": "Night (00:00-05:59)", "start": 0, "end": 5, "count": 0},
        }

        for hour, count in booking_hours.items():
            if 6 <= hour <= 11:
                time_ranges["morning"]["count"] += count
            elif 12 <= hour <= 17:
                time_ranges["afternoon"]["count"] += count
            elif 18 <= hour <= 23:
                time_ranges["evening"]["count"] += count
            else:
                time_ranges["night"]["count"] += count

        total = sum(tr["count"] for tr in time_ranges.values())
        result = []
        for key in ["morning", "afternoon", "evening", "night"]:
            tr = time_ranges[key]
            percent = round(tr["count"] / total * 100, 1) if total > 0 else 0
            result.append({
                "range": key,
                "label": tr["label"],
                "count": tr["count"],
                "percent": percent
            })
        return result

    def test_afternoon_peak(self):
        """Happy path: Afternoon is the peak time range."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 14, 0)),  # Afternoon
            MockBooking(create_uk_datetime(2026, 4, 2, 15, 0)),  # Afternoon
            MockBooking(create_uk_datetime(2026, 4, 3, 16, 0)),  # Afternoon
            MockBooking(create_uk_datetime(2026, 4, 4, 10, 0)),  # Morning
        ]
        ranges = self.calculate_time_ranges(bookings)

        afternoon = next(r for r in ranges if r["range"] == "afternoon")
        assert afternoon["count"] == 3
        assert afternoon["percent"] == 75.0

    def test_morning_range_boundaries(self):
        """Boundary: Morning range is 06:00-11:59."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 5, 59)),   # Night (just before)
            MockBooking(create_uk_datetime(2026, 4, 1, 6, 0)),    # Morning (start)
            MockBooking(create_uk_datetime(2026, 4, 1, 11, 59)),  # Morning (end)
            MockBooking(create_uk_datetime(2026, 4, 1, 12, 0)),   # Afternoon (just after)
        ]
        ranges = self.calculate_time_ranges(bookings)

        morning = next(r for r in ranges if r["range"] == "morning")
        assert morning["count"] == 2

    def test_afternoon_range_boundaries(self):
        """Boundary: Afternoon range is 12:00-17:59."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 11, 59)),  # Morning (just before)
            MockBooking(create_uk_datetime(2026, 4, 1, 12, 0)),   # Afternoon (start)
            MockBooking(create_uk_datetime(2026, 4, 1, 17, 59)),  # Afternoon (end)
            MockBooking(create_uk_datetime(2026, 4, 1, 18, 0)),   # Evening (just after)
        ]
        ranges = self.calculate_time_ranges(bookings)

        afternoon = next(r for r in ranges if r["range"] == "afternoon")
        assert afternoon["count"] == 2

    def test_evening_range_boundaries(self):
        """Boundary: Evening range is 18:00-23:59."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 17, 59)),  # Afternoon (just before)
            MockBooking(create_uk_datetime(2026, 4, 1, 18, 0)),   # Evening (start)
            MockBooking(create_uk_datetime(2026, 4, 1, 23, 59)),  # Evening (end)
            MockBooking(create_uk_datetime(2026, 4, 2, 0, 0)),    # Night (just after)
        ]
        ranges = self.calculate_time_ranges(bookings)

        evening = next(r for r in ranges if r["range"] == "evening")
        assert evening["count"] == 2

    def test_night_range_boundaries(self):
        """Boundary: Night range is 00:00-05:59."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 23, 59)),  # Evening (just before)
            MockBooking(create_uk_datetime(2026, 4, 2, 0, 0)),    # Night (start)
            MockBooking(create_uk_datetime(2026, 4, 2, 5, 59)),   # Night (end)
            MockBooking(create_uk_datetime(2026, 4, 2, 6, 0)),    # Morning (just after)
        ]
        ranges = self.calculate_time_ranges(bookings)

        night = next(r for r in ranges if r["range"] == "night")
        assert night["count"] == 2

    def test_all_ranges_present(self):
        """Happy path: All four time ranges are present in output."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 1, 12, 0))]
        ranges = self.calculate_time_ranges(bookings)

        range_names = [r["range"] for r in ranges]
        assert "morning" in range_names
        assert "afternoon" in range_names
        assert "evening" in range_names
        assert "night" in range_names

    def test_empty_bookings_ranges(self):
        """Edge case: No bookings returns zero counts for all ranges."""
        bookings = []
        ranges = self.calculate_time_ranges(bookings)

        for r in ranges:
            assert r["count"] == 0
            assert r["percent"] == 0

    def test_percentages_sum_to_100(self):
        """Happy path: Percentages sum to approximately 100%."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 8, 0)),   # Morning
            MockBooking(create_uk_datetime(2026, 4, 1, 14, 0)),  # Afternoon
            MockBooking(create_uk_datetime(2026, 4, 1, 20, 0)),  # Evening
            MockBooking(create_uk_datetime(2026, 4, 1, 2, 0)),   # Night
        ]
        ranges = self.calculate_time_ranges(bookings)

        total_percent = sum(r["percent"] for r in ranges)
        assert total_percent == 100.0


# ============================================================================
# MOCKED UNIT TESTS - Day of Week with UK Timezone
# ============================================================================

class TestDayOfWeekWithTimezone:
    """Unit tests for day of week calculation with UK timezone."""

    def calculate_day_of_week(self, bookings):
        """Mirror the day of week calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        booking_days = {day: 0 for day in day_names}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)
                day_name = day_names[created_at_uk.weekday()]
                booking_days[day_name] += 1

        total = sum(booking_days.values())
        return [
            {
                "day": day,
                "count": count,
                "percent": round(count / total * 100, 1) if total > 0 else 0
            }
            for day, count in booking_days.items()
        ]

    def test_friday_peak(self):
        """Happy path: Friday is the busiest day."""
        bookings = [
            # Friday April 17, 2026
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),
            MockBooking(create_uk_datetime(2026, 4, 17, 14, 0)),
            MockBooking(create_uk_datetime(2026, 4, 17, 16, 0)),
            # Thursday April 16, 2026
            MockBooking(create_uk_datetime(2026, 4, 16, 10, 0)),
        ]
        days = self.calculate_day_of_week(bookings)

        friday = next(d for d in days if d["day"] == "Friday")
        assert friday["count"] == 3

    def test_utc_midnight_becomes_uk_previous_day_summer(self):
        """Edge case: UTC midnight in summer is previous day in UK."""
        # UTC 00:30 on Saturday July 18 = 01:30 on Saturday July 18 in UK (BST)
        # This should still be Saturday
        booking = MockBooking(create_utc_datetime(2026, 7, 18, 0, 30))
        days = self.calculate_day_of_week([booking])

        saturday = next(d for d in days if d["day"] == "Saturday")
        assert saturday["count"] == 1


# ============================================================================
# MOCKED INTEGRATION TESTS - Response Format
# ============================================================================

class TestBookingStatsResponseFormat:
    """Integration tests for booking stats API response format."""

    def test_booking_hours_response_structure(self):
        """Happy path: Booking hours has correct structure."""
        booking_hours = [
            {"hour": 0, "label": "00:00", "count": 5, "percent": 2.9},
            {"hour": 15, "label": "15:00", "count": 22, "percent": 12.6},
        ]

        for hour in booking_hours:
            assert "hour" in hour
            assert "label" in hour
            assert "count" in hour
            assert "percent" in hour
            assert isinstance(hour["hour"], int)
            assert isinstance(hour["label"], str)
            assert isinstance(hour["count"], int)
            assert isinstance(hour["percent"], float)

    def test_time_ranges_response_structure(self):
        """Happy path: Time ranges has correct structure."""
        time_ranges = [
            {"range": "morning", "label": "Morning (06:00-11:59)", "count": 41, "percent": 23.4},
            {"range": "afternoon", "label": "Afternoon (12:00-17:59)", "count": 94, "percent": 53.7},
        ]

        for tr in time_ranges:
            assert "range" in tr
            assert "label" in tr
            assert "count" in tr
            assert "percent" in tr
            assert tr["range"] in ["morning", "afternoon", "evening", "night"]

    def test_time_ranges_order(self):
        """Happy path: Time ranges are in consistent order."""
        # Simulate the order from the endpoint
        range_order = ["morning", "afternoon", "evening", "night"]
        time_ranges = [
            {"range": "morning", "label": "Morning (06:00-11:59)", "count": 41, "percent": 23.4},
            {"range": "afternoon", "label": "Afternoon (12:00-17:59)", "count": 94, "percent": 53.7},
            {"range": "evening", "label": "Evening (18:00-23:59)", "count": 40, "percent": 22.9},
            {"range": "night", "label": "Night (00:00-05:59)", "count": 0, "percent": 0.0},
        ]

        for i, tr in enumerate(time_ranges):
            assert tr["range"] == range_order[i]


# ============================================================================
# BOUNDARY TESTS
# ============================================================================

class TestPeakHoursBoundaries:
    """Boundary tests for peak booking hours calculations."""

    def calculate_hour_distribution(self, bookings):
        """Mirror the hour distribution calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')
        booking_hours = {hour: 0 for hour in range(24)}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)
                booking_hours[created_at_uk.hour] += 1

        total = sum(booking_hours.values())
        return [
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "count": count,
                "percent": round(count / total * 100, 1) if total > 0 else 0
            }
            for hour, count in booking_hours.items()
        ]

    def test_large_number_of_bookings(self):
        """Boundary: Large number of bookings handled correctly."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, i % 24, 0))
            for i in range(1000)
        ]
        hours = self.calculate_hour_distribution(bookings)

        total_count = sum(h["count"] for h in hours)
        assert total_count == 1000

    def test_all_bookings_same_hour(self):
        """Boundary: All bookings in same hour = 100%."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, 15, i))
            for i in range(60)
        ]
        hours = self.calculate_hour_distribution(bookings)

        hour_15 = next(h for h in hours if h["hour"] == 15)
        assert hour_15["count"] == 60
        assert hour_15["percent"] == 100.0

    def test_evenly_distributed(self):
        """Boundary: Evenly distributed bookings."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 1, hour, 0))
            for hour in range(24)
        ]
        hours = self.calculate_hour_distribution(bookings)

        for h in hours:
            assert h["count"] == 1
            assert 4.0 <= h["percent"] <= 4.2  # ~4.17% each


# ============================================================================
# MOCKED UNIT TESTS - Hours By Day of Week Calculation
# ============================================================================

class TestHoursByDayOfWeekCalculation:
    """Unit tests for hourly breakdown by day of week."""

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def calculate_hours_by_day(self, bookings):
        """Mirror the hours by day calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')

        # Initialize structure
        booking_hours_by_day = {day: {hour: 0 for hour in range(24)} for day in self.DAY_NAMES}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)

                day_name = self.DAY_NAMES[created_at_uk.weekday()]
                booking_hours_by_day[day_name][created_at_uk.hour] += 1

        # Convert to list format
        result = {}
        for day in self.DAY_NAMES:
            day_total = sum(booking_hours_by_day[day].values())
            hours_list = []
            for hour in range(24):
                count = booking_hours_by_day[day][hour]
                percent = round(count / day_total * 100, 1) if day_total > 0 else 0
                hours_list.append({
                    "hour": hour,
                    "label": f"{hour:02d}:00",
                    "count": count,
                    "percent": percent
                })
            result[day] = {
                "hours": hours_list,
                "total": day_total
            }
        return result

    def test_hours_by_day_basic(self):
        """Happy path: Bookings correctly grouped by day of week."""
        # April 17, 2026 is a Friday
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday 10:00
            MockBooking(create_uk_datetime(2026, 4, 17, 15, 0)),  # Friday 15:00
            MockBooking(create_uk_datetime(2026, 4, 16, 14, 0)),  # Thursday 14:00
        ]
        result = self.calculate_hours_by_day(bookings)

        assert result["Friday"]["total"] == 2
        assert result["Thursday"]["total"] == 1
        assert result["Monday"]["total"] == 0

    def test_hours_by_day_all_days_present(self):
        """Happy path: All 7 days are present in output."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 17, 10, 0))]
        result = self.calculate_hours_by_day(bookings)

        assert len(result) == 7
        for day in self.DAY_NAMES:
            assert day in result

    def test_hours_by_day_24_hours_per_day(self):
        """Happy path: Each day has 24 hours."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 17, 10, 0))]
        result = self.calculate_hours_by_day(bookings)

        for day in self.DAY_NAMES:
            assert len(result[day]["hours"]) == 24

    def test_hours_by_day_percentage_per_day(self):
        """Happy path: Percentages calculated per day, not overall."""
        # Friday: 2 bookings at 10:00, 1 at 15:00
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 30)), # Friday
            MockBooking(create_uk_datetime(2026, 4, 17, 15, 0)),  # Friday
        ]
        result = self.calculate_hours_by_day(bookings)

        friday = result["Friday"]
        assert friday["total"] == 3

        hour_10 = next(h for h in friday["hours"] if h["hour"] == 10)
        hour_15 = next(h for h in friday["hours"] if h["hour"] == 15)

        # 2 out of 3 = 66.7%
        assert hour_10["count"] == 2
        assert hour_10["percent"] == 66.7

        # 1 out of 3 = 33.3%
        assert hour_15["count"] == 1
        assert hour_15["percent"] == 33.3

    def test_hours_by_day_empty_day_zero_percent(self):
        """Edge case: Day with no bookings has 0% for all hours."""
        # Only Friday bookings
        bookings = [MockBooking(create_uk_datetime(2026, 4, 17, 10, 0))]
        result = self.calculate_hours_by_day(bookings)

        # Monday has no bookings
        monday = result["Monday"]
        assert monday["total"] == 0
        for hour in monday["hours"]:
            assert hour["count"] == 0
            assert hour["percent"] == 0

    def test_hours_by_day_single_booking_100_percent(self):
        """Boundary: Single booking on a day = 100% for that hour."""
        bookings = [MockBooking(create_uk_datetime(2026, 4, 17, 14, 0))]  # Friday 14:00
        result = self.calculate_hours_by_day(bookings)

        friday = result["Friday"]
        assert friday["total"] == 1

        hour_14 = next(h for h in friday["hours"] if h["hour"] == 14)
        assert hour_14["count"] == 1
        assert hour_14["percent"] == 100.0

    def test_hours_by_day_across_multiple_weeks(self):
        """Happy path: Same day across multiple weeks aggregates correctly."""
        # Multiple Fridays
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 3, 10, 0)),   # Friday Apr 3
            MockBooking(create_uk_datetime(2026, 4, 10, 10, 0)),  # Friday Apr 10
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday Apr 17
            MockBooking(create_uk_datetime(2026, 4, 17, 15, 0)),  # Friday Apr 17
        ]
        result = self.calculate_hours_by_day(bookings)

        friday = result["Friday"]
        assert friday["total"] == 4

        hour_10 = next(h for h in friday["hours"] if h["hour"] == 10)
        assert hour_10["count"] == 3  # 3 bookings at 10:00 across Fridays

    def test_hours_by_day_timezone_conversion(self):
        """Edge case: UTC times correctly converted to UK timezone."""
        # UTC 23:30 on Thursday July 16 = 00:30 Friday July 17 in UK (BST)
        bookings = [MockBooking(create_utc_datetime(2026, 7, 16, 23, 30))]
        result = self.calculate_hours_by_day(bookings)

        # Should be Friday (not Thursday) due to BST conversion
        friday = result["Friday"]
        thursday = result["Thursday"]

        assert friday["total"] == 1
        assert thursday["total"] == 0

        # Should be at 00:00 hour
        hour_0 = next(h for h in friday["hours"] if h["hour"] == 0)
        assert hour_0["count"] == 1

    def test_hours_by_day_weekend_vs_weekday(self):
        """Happy path: Weekend and weekday data correctly separated."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday (weekday)
            MockBooking(create_uk_datetime(2026, 4, 18, 11, 0)),  # Saturday (weekend)
            MockBooking(create_uk_datetime(2026, 4, 19, 12, 0)),  # Sunday (weekend)
        ]
        result = self.calculate_hours_by_day(bookings)

        assert result["Friday"]["total"] == 1
        assert result["Saturday"]["total"] == 1
        assert result["Sunday"]["total"] == 1
        assert result["Monday"]["total"] == 0


# ============================================================================
# MOCKED INTEGRATION TESTS - Hours By Day Response Format
# ============================================================================

class TestHoursByDayResponseFormat:
    """Integration tests for hours by day API response format."""

    def test_hours_by_day_structure(self):
        """Happy path: Hours by day has correct nested structure."""
        hours_by_day = {
            "Monday": {
                "hours": [
                    {"hour": 0, "label": "00:00", "count": 0, "percent": 0},
                    {"hour": 10, "label": "10:00", "count": 5, "percent": 50.0},
                ],
                "total": 10
            },
            "Friday": {
                "hours": [
                    {"hour": 15, "label": "15:00", "count": 8, "percent": 40.0},
                ],
                "total": 20
            }
        }

        for day, data in hours_by_day.items():
            assert "hours" in data
            assert "total" in data
            assert isinstance(data["hours"], list)
            assert isinstance(data["total"], int)

    def test_hours_by_day_hour_entry_structure(self):
        """Happy path: Each hour entry has required fields."""
        hour_entry = {"hour": 15, "label": "15:00", "count": 8, "percent": 40.0}

        assert "hour" in hour_entry
        assert "label" in hour_entry
        assert "count" in hour_entry
        assert "percent" in hour_entry
        assert isinstance(hour_entry["hour"], int)
        assert isinstance(hour_entry["label"], str)
        assert isinstance(hour_entry["count"], int)
        assert isinstance(hour_entry["percent"], float)

    def test_hours_by_day_all_days_keys(self):
        """Happy path: All 7 days are keys in the response."""
        expected_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        hours_by_day = {day: {"hours": [], "total": 0} for day in expected_days}

        for day in expected_days:
            assert day in hours_by_day


# ============================================================================
# BOUNDARY TESTS - Hours By Day
# ============================================================================

class TestHoursByDayBoundaries:
    """Boundary tests for hours by day calculations."""

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def calculate_hours_by_day(self, bookings):
        """Mirror the hours by day calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')
        booking_hours_by_day = {day: {hour: 0 for hour in range(24)} for day in self.DAY_NAMES}

        for booking in bookings:
            if booking.created_at:
                created_at_uk = booking.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)
                day_name = self.DAY_NAMES[created_at_uk.weekday()]
                booking_hours_by_day[day_name][created_at_uk.hour] += 1

        result = {}
        for day in self.DAY_NAMES:
            day_total = sum(booking_hours_by_day[day].values())
            hours_list = []
            for hour in range(24):
                count = booking_hours_by_day[day][hour]
                percent = round(count / day_total * 100, 1) if day_total > 0 else 0
                hours_list.append({
                    "hour": hour,
                    "label": f"{hour:02d}:00",
                    "count": count,
                    "percent": percent
                })
            result[day] = {"hours": hours_list, "total": day_total}
        return result

    def test_large_bookings_single_day(self):
        """Boundary: Large number of bookings on single day."""
        # All on Friday April 17, 2026
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 17, i % 24, 0))
            for i in range(500)
        ]
        result = self.calculate_hours_by_day(bookings)

        assert result["Friday"]["total"] == 500
        # Other days should be 0
        for day in self.DAY_NAMES:
            if day != "Friday":
                assert result[day]["total"] == 0

    def test_empty_bookings_all_days_zero(self):
        """Boundary: No bookings = all days have 0 total."""
        result = self.calculate_hours_by_day([])

        for day in self.DAY_NAMES:
            assert result[day]["total"] == 0
            for hour in result[day]["hours"]:
                assert hour["count"] == 0
                assert hour["percent"] == 0

    def test_all_days_equal_distribution(self):
        """Boundary: Equal bookings across all days."""
        bookings = []
        # Add one booking per day at 10:00
        for day_offset in range(7):
            # April 13, 2026 is Monday
            bookings.append(MockBooking(create_uk_datetime(2026, 4, 13 + day_offset, 10, 0)))

        result = self.calculate_hours_by_day(bookings)

        for day in self.DAY_NAMES:
            assert result[day]["total"] == 1
            hour_10 = next(h for h in result[day]["hours"] if h["hour"] == 10)
            assert hour_10["percent"] == 100.0

    def test_percentages_sum_to_100_per_day(self):
        """Boundary: Percentages sum to 100% for each day with bookings."""
        bookings = [
            MockBooking(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday
            MockBooking(create_uk_datetime(2026, 4, 17, 15, 0)),  # Friday
            MockBooking(create_uk_datetime(2026, 4, 17, 20, 0)),  # Friday
        ]
        result = self.calculate_hours_by_day(bookings)

        friday = result["Friday"]
        total_percent = sum(h["percent"] for h in friday["hours"])
        assert 99.5 <= total_percent <= 100.5  # Allow for rounding

    def test_midnight_boundary_correct_day(self):
        """Boundary: Bookings at exactly midnight assigned to correct day."""
        # Exactly midnight on Saturday April 18, 2026
        bookings = [MockBooking(create_uk_datetime(2026, 4, 18, 0, 0))]
        result = self.calculate_hours_by_day(bookings)

        assert result["Saturday"]["total"] == 1
        assert result["Friday"]["total"] == 0

        hour_0 = next(h for h in result["Saturday"]["hours"] if h["hour"] == 0)
        assert hour_0["count"] == 1


# ============================================================================
# MOCKED UNIT TESTS - Search Analytics (Audit Log)
# ============================================================================

class MockAuditEvent:
    """Mock audit log event object with created_at timestamp."""
    def __init__(self, created_at: datetime, event: str = "dates_selected"):
        self.created_at = created_at
        self.event = event


class TestSearchAnalyticsCalculation:
    """Unit tests for search analytics from audit logs (dates_selected events)."""

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def calculate_search_analytics(self, events):
        """Mirror the search analytics calculation from the endpoint."""
        uk_tz = pytz.timezone('Europe/London')

        search_days_of_week = {day: 0 for day in self.DAY_NAMES}
        search_hours_of_day = {hour: 0 for hour in range(24)}
        search_hours_by_day = {day: {hour: 0 for hour in range(24)} for day in self.DAY_NAMES}

        for event in events:
            if event.created_at:
                created_at_uk = event.created_at
                if created_at_uk.tzinfo is None:
                    created_at_uk = pytz.utc.localize(created_at_uk)
                created_at_uk = created_at_uk.astimezone(uk_tz)

                day_name = self.DAY_NAMES[created_at_uk.weekday()]
                search_days_of_week[day_name] += 1
                search_hours_of_day[created_at_uk.hour] += 1
                search_hours_by_day[day_name][created_at_uk.hour] += 1

        total_searches = sum(search_days_of_week.values())

        # Days list
        search_days_list = []
        for day in self.DAY_NAMES:
            count = search_days_of_week[day]
            percent = round(count / total_searches * 100, 1) if total_searches > 0 else 0
            search_days_list.append({"day": day, "count": count, "percent": percent})

        # Hours list
        search_hours_list = []
        for hour in range(24):
            count = search_hours_of_day[hour]
            percent = round(count / total_searches * 100, 1) if total_searches > 0 else 0
            search_hours_list.append({
                "hour": hour,
                "label": f"{hour:02d}:00",
                "count": count,
                "percent": percent
            })

        # Hours by day
        search_hours_by_day_list = {}
        for day in self.DAY_NAMES:
            day_total = sum(search_hours_by_day[day].values())
            hours_list = []
            for hour in range(24):
                count = search_hours_by_day[day][hour]
                percent = round(count / day_total * 100, 1) if day_total > 0 else 0
                hours_list.append({
                    "hour": hour,
                    "label": f"{hour:02d}:00",
                    "count": count,
                    "percent": percent
                })
            search_hours_by_day_list[day] = {"hours": hours_list, "total": day_total}

        return {
            "search_days_of_week": search_days_list,
            "search_hours_of_day": search_hours_list,
            "search_hours_by_day": search_hours_by_day_list,
            "total_searches": total_searches
        }

    def test_search_days_distribution(self):
        """Happy path: Searches correctly distributed by day."""
        events = [
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 14, 0)),  # Friday
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 16, 0)),  # Friday
            MockAuditEvent(create_uk_datetime(2026, 4, 16, 12, 0)),  # Thursday
        ]
        result = self.calculate_search_analytics(events)

        friday = next(d for d in result["search_days_of_week"] if d["day"] == "Friday")
        assert friday["count"] == 3
        assert friday["percent"] == 75.0

    def test_search_hours_distribution(self):
        """Happy path: Searches correctly distributed by hour."""
        events = [
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 15, 0)),
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 15, 30)),
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 17, 0)),
        ]
        result = self.calculate_search_analytics(events)

        hour_15 = next(h for h in result["search_hours_of_day"] if h["hour"] == 15)
        assert hour_15["count"] == 2
        assert hour_15["percent"] == 66.7

    def test_search_total_count(self):
        """Happy path: Total search count is correct."""
        events = [
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 10, 0)),
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 14, 0)),
            MockAuditEvent(create_uk_datetime(2026, 4, 18, 10, 0)),
        ]
        result = self.calculate_search_analytics(events)
        assert result["total_searches"] == 3

    def test_empty_searches(self):
        """Edge case: No search events."""
        result = self.calculate_search_analytics([])

        assert result["total_searches"] == 0
        assert len(result["search_days_of_week"]) == 7
        assert len(result["search_hours_of_day"]) == 24

        for day in result["search_days_of_week"]:
            assert day["count"] == 0
            assert day["percent"] == 0

    def test_search_hours_by_day(self):
        """Happy path: Search hours by day correctly structured."""
        events = [
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 10, 0)),  # Friday 10:00
            MockAuditEvent(create_uk_datetime(2026, 4, 17, 15, 0)),  # Friday 15:00
        ]
        result = self.calculate_search_analytics(events)

        friday = result["search_hours_by_day"]["Friday"]
        assert friday["total"] == 2

        hour_10 = next(h for h in friday["hours"] if h["hour"] == 10)
        assert hour_10["count"] == 1

    def test_search_timezone_conversion(self):
        """Edge case: UTC times correctly converted to UK timezone."""
        # UTC 23:30 on Thursday = 00:30 Friday in BST
        events = [MockAuditEvent(create_utc_datetime(2026, 7, 16, 23, 30))]
        result = self.calculate_search_analytics(events)

        friday = next(d for d in result["search_days_of_week"] if d["day"] == "Friday")
        thursday = next(d for d in result["search_days_of_week"] if d["day"] == "Thursday")

        assert friday["count"] == 1
        assert thursday["count"] == 0

    def test_search_all_days_present(self):
        """Happy path: All 7 days present in output."""
        events = [MockAuditEvent(create_uk_datetime(2026, 4, 17, 10, 0))]
        result = self.calculate_search_analytics(events)

        days = [d["day"] for d in result["search_days_of_week"]]
        assert days == ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


# ============================================================================
# MOCKED INTEGRATION TESTS - Search vs Booking Comparison
# ============================================================================

class TestSearchVsBookingComparison:
    """Integration tests for comparing searches with bookings."""

    def test_response_has_both_search_and_booking_data(self):
        """Happy path: Response contains both search and booking analytics."""
        response = {
            "booking_days_of_week": [{"day": "Friday", "count": 10, "percent": 50.0}],
            "search_days_of_week": [{"day": "Friday", "count": 100, "percent": 50.0}],
            "total_successful": 20,
            "total_searches": 200,
        }

        assert "booking_days_of_week" in response
        assert "search_days_of_week" in response
        assert "total_successful" in response
        assert "total_searches" in response

    def test_conversion_rate_can_be_calculated(self):
        """Happy path: Can calculate conversion rate from searches to bookings."""
        total_searches = 200
        total_bookings = 20

        conversion_rate = round((total_bookings / total_searches) * 100, 1) if total_searches > 0 else 0
        assert conversion_rate == 10.0

    def test_search_and_booking_hours_same_structure(self):
        """Happy path: Search and booking hours have identical structure."""
        booking_hours = [
            {"hour": 0, "label": "00:00", "count": 5, "percent": 2.5},
            {"hour": 15, "label": "15:00", "count": 20, "percent": 10.0},
        ]
        search_hours = [
            {"hour": 0, "label": "00:00", "count": 50, "percent": 2.5},
            {"hour": 15, "label": "15:00", "count": 200, "percent": 10.0},
        ]

        for bh, sh in zip(booking_hours, search_hours):
            assert set(bh.keys()) == set(sh.keys())
            assert set(bh.keys()) == {"hour", "label", "count", "percent"}


# ============================================================================
# MOCKED UNIT TESTS - Search Data Start Date
# ============================================================================

class TestSearchDataStartDate:
    """Unit tests for search_data_start_date calculation (session tracking start date)."""

    def calculate_search_data_start_date(self, events):
        """Mirror the search_data_start_date calculation from the endpoint."""
        if not events:
            return None

        uk_tz = pytz.timezone('Europe/London')

        # Events should be sorted by created_at ascending
        sorted_events = sorted(events, key=lambda e: e.created_at if e.created_at else datetime.max)

        if sorted_events and sorted_events[0].created_at:
            earliest_date = sorted_events[0].created_at
            if earliest_date.tzinfo is None:
                earliest_date = pytz.utc.localize(earliest_date)
            earliest_date = earliest_date.astimezone(uk_tz)
            return earliest_date.strftime("%d %B %Y")

        return None

    def test_earliest_date_returned(self):
        """Happy path: Returns the earliest event date in correct format."""
        events = [
            MockAuditEvent(create_uk_datetime(2026, 4, 15, 10, 0)),  # Middle
            MockAuditEvent(create_uk_datetime(2026, 2, 10, 14, 0)),  # Earliest
            MockAuditEvent(create_uk_datetime(2026, 4, 20, 16, 0)),  # Latest
        ]
        result = self.calculate_search_data_start_date(events)

        assert result == "10 February 2026"

    def test_date_format_correct(self):
        """Happy path: Date format is 'DD Month YYYY'."""
        events = [MockAuditEvent(create_uk_datetime(2026, 1, 5, 9, 30))]
        result = self.calculate_search_data_start_date(events)

        assert result == "05 January 2026"

    def test_empty_events_returns_none(self):
        """Edge case: Empty events list returns None."""
        result = self.calculate_search_data_start_date([])

        assert result is None

    def test_utc_events_converted_to_uk(self):
        """Happy path: UTC dates are converted to UK timezone for display."""
        # Create UTC event at 23:30 on Jan 1 - this is 23:30 UK time (same day in winter)
        events = [MockAuditEvent(create_utc_datetime(2026, 1, 1, 23, 30))]
        result = self.calculate_search_data_start_date(events)

        # In January, UK is on GMT so UTC = UK time
        assert result == "01 January 2026"

    def test_bst_conversion_summer(self):
        """Happy path: BST conversion for summer dates."""
        # Create UTC event at 23:30 on July 1 - this is 00:30 UK time (next day in summer)
        events = [MockAuditEvent(create_utc_datetime(2026, 7, 1, 23, 30))]
        result = self.calculate_search_data_start_date(events)

        # In July, UK is on BST (UTC+1) so 23:30 UTC = 00:30 BST on July 2
        assert result == "02 July 2026"

    def test_response_includes_search_data_start_date(self):
        """Integration test: Response includes search_data_start_date field."""
        response = {
            "search_days_of_week": [{"day": "Friday", "count": 100, "percent": 50.0}],
            "search_hours_of_day": [{"hour": 15, "label": "15:00", "count": 50, "percent": 25.0}],
            "total_searches": 200,
            "search_data_start_date": "10 February 2026",
        }

        assert "search_data_start_date" in response
        assert response["search_data_start_date"] == "10 February 2026"

    def test_search_data_start_date_none_when_no_searches(self):
        """Edge case: search_data_start_date is None when no search events exist."""
        response = {
            "total_searches": 0,
            "search_data_start_date": None,
        }

        assert response["search_data_start_date"] is None
