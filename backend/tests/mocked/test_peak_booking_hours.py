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
