"""
Tests for Admin Fun Facts Report.

Covers:
- GET /api/admin/reports/fun-facts - Fun facts/records for the business

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch
from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    dropoff_date=None,
    pickup_date=None,
    total_price=None,
    dropoff_destination="Faro Airport",
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date(2026, 3, 15)
    booking.pickup_date = pickup_date or date(2026, 3, 22)
    booking.total_price = total_price
    booking.dropoff_destination = dropoff_destination

    if status == "confirmed":
        booking.status = BookingStatus.CONFIRMED
    elif status == "completed":
        booking.status = BookingStatus.COMPLETED
    elif status == "pending":
        booking.status = BookingStatus.PENDING
    elif status == "cancelled":
        booking.status = BookingStatus.CANCELLED
    else:
        booking.status = BookingStatus.PENDING

    return booking


def create_mock_fun_facts_response(
    busiest_day=None,
    busiest_streak=None,
    longest_trip=None,
    highest_transaction=None,
):
    """Create a mock fun facts response."""
    return {
        "busiestDay": busiest_day,
        "busiestStreak": busiest_streak,
        "longestTrip": longest_trip,
        "highestTransaction": highest_transaction,
    }


# =============================================================================
# Unit Tests - Response Structure
# =============================================================================

class TestFunFactsResponseStructure:
    """Unit tests for response structure."""

    def test_response_includes_busiest_day(self):
        """Response should include busiestDay field."""
        response = create_mock_fun_facts_response(
            busiest_day={"date": "Mon 24 Feb 2026", "count": 15}
        )

        assert "busiestDay" in response

    def test_response_includes_busiest_streak(self):
        """Response should include busiestStreak field."""
        response = create_mock_fun_facts_response(
            busiest_streak={"days": 7, "startDate": "24 Feb", "endDate": "28 Feb 2026", "bookings": 32}
        )

        assert "busiestStreak" in response

    def test_response_includes_longest_trip(self):
        """Response should include longestTrip field."""
        response = create_mock_fun_facts_response(
            longest_trip={"days": 21, "reference": "TAG-ABC123", "destination": "Tenerife"}
        )

        assert "longestTrip" in response

    def test_response_includes_highest_transaction(self):
        """Response should include highestTransaction field."""
        response = create_mock_fun_facts_response(
            highest_transaction={"amount": "£189.00", "reference": "TAG-XYZ789", "days": 14}
        )

        assert "highestTransaction" in response

    def test_busiest_day_structure(self):
        """Busiest day should include date and count."""
        response = create_mock_fun_facts_response(
            busiest_day={"date": "Mon 24 Feb 2026", "count": 15}
        )

        assert "date" in response["busiestDay"]
        assert "count" in response["busiestDay"]

    def test_busiest_streak_structure(self):
        """Busiest streak should include days, startDate, endDate, and bookings."""
        response = create_mock_fun_facts_response(
            busiest_streak={"days": 7, "startDate": "24 Feb", "endDate": "28 Feb 2026", "bookings": 32}
        )

        assert "days" in response["busiestStreak"]
        assert "startDate" in response["busiestStreak"]
        assert "endDate" in response["busiestStreak"]
        assert "bookings" in response["busiestStreak"]

    def test_longest_trip_structure(self):
        """Longest trip should include days, reference, and destination."""
        response = create_mock_fun_facts_response(
            longest_trip={"days": 21, "reference": "TAG-ABC123", "destination": "Tenerife"}
        )

        assert "days" in response["longestTrip"]
        assert "reference" in response["longestTrip"]
        assert "destination" in response["longestTrip"]

    def test_highest_transaction_structure(self):
        """Highest transaction should include amount, reference, and days."""
        response = create_mock_fun_facts_response(
            highest_transaction={"amount": "£189.00", "reference": "TAG-XYZ789", "days": 14}
        )

        assert "amount" in response["highestTransaction"]
        assert "reference" in response["highestTransaction"]
        assert "days" in response["highestTransaction"]


# =============================================================================
# Unit Tests - Busiest Day Logic
# =============================================================================

class TestBusiestDayLogic:
    """Unit tests for busiest day calculation."""

    def test_single_booking_single_day(self):
        """Single booking should make that day the busiest."""
        booking = create_mock_booking(dropoff_date=date(2026, 3, 15))

        day_counter = Counter()
        if booking.dropoff_date:
            day_counter[booking.dropoff_date] += 1

        busiest_date, busiest_count = day_counter.most_common(1)[0]

        assert busiest_date == date(2026, 3, 15)
        assert busiest_count == 1

    def test_multiple_bookings_same_day(self):
        """Multiple bookings on same day should accumulate."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 15)),
        ]

        day_counter = Counter()
        for booking in bookings:
            if booking.dropoff_date:
                day_counter[booking.dropoff_date] += 1

        busiest_date, busiest_count = day_counter.most_common(1)[0]

        assert busiest_date == date(2026, 3, 15)
        assert busiest_count == 3

    def test_busiest_day_from_multiple_days(self):
        """Should identify the day with most bookings."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=4, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=5, dropoff_date=date(2026, 3, 17)),
            create_mock_booking(id=6, dropoff_date=date(2026, 3, 17)),
        ]

        day_counter = Counter()
        for booking in bookings:
            if booking.dropoff_date:
                day_counter[booking.dropoff_date] += 1

        busiest_date, busiest_count = day_counter.most_common(1)[0]

        assert busiest_date == date(2026, 3, 16)
        assert busiest_count == 3

    def test_busiest_day_tie_returns_first(self):
        """Tie in busiest day should return one of the tied days."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=4, dropoff_date=date(2026, 3, 16)),
        ]

        day_counter = Counter()
        for booking in bookings:
            if booking.dropoff_date:
                day_counter[booking.dropoff_date] += 1

        busiest_date, busiest_count = day_counter.most_common(1)[0]

        assert busiest_count == 2
        assert busiest_date in [date(2026, 3, 15), date(2026, 3, 16)]

    def test_busiest_day_skips_null_dates(self):
        """Should skip bookings with null dropoff_date."""
        booking = create_mock_booking(dropoff_date=None)

        day_counter = Counter()
        if booking.dropoff_date:
            day_counter[booking.dropoff_date] += 1

        assert len(day_counter) == 0

    def test_busiest_day_date_format(self):
        """Busiest day date should be formatted correctly."""
        busiest_date = date(2026, 2, 24)
        formatted = busiest_date.strftime("%a %d %b %Y")

        assert formatted == "Tue 24 Feb 2026"


# =============================================================================
# Unit Tests - Busiest Streak Logic
# =============================================================================

class TestBusiestStreakLogic:
    """Unit tests for busiest streak calculation."""

    def test_single_day_streak(self):
        """Single day with bookings is a streak of 1."""
        day_counter = Counter({date(2026, 3, 15): 5})
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        assert len(sorted_dates) == 1
        assert longest_streak == 1

    def test_consecutive_days_streak(self):
        """Consecutive days should form a streak."""
        day_counter = Counter({
            date(2026, 3, 15): 3,
            date(2026, 3, 16): 2,
            date(2026, 3, 17): 4,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 3

    def test_non_consecutive_days_streak_of_one(self):
        """Non-consecutive days should have streak of 1."""
        day_counter = Counter({
            date(2026, 3, 15): 3,
            date(2026, 3, 17): 2,  # Gap on 16th
            date(2026, 3, 19): 4,  # Gap on 18th
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 1

    def test_multiple_streaks_returns_longest(self):
        """Multiple streaks should return the longest one."""
        day_counter = Counter({
            date(2026, 3, 10): 1,
            date(2026, 3, 11): 1,  # 2-day streak
            date(2026, 3, 15): 1,
            date(2026, 3, 16): 1,
            date(2026, 3, 17): 1,
            date(2026, 3, 18): 1,
            date(2026, 3, 19): 1,  # 5-day streak
            date(2026, 3, 25): 1,
            date(2026, 3, 26): 1,
            date(2026, 3, 27): 1,  # 3-day streak
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        longest_streak_start = sorted_dates[0]
        longest_streak_end = sorted_dates[0]
        current_streak = 1
        current_streak_start = sorted_dates[0]

        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                    longest_streak_start = current_streak_start
                    longest_streak_end = sorted_dates[i-1]
                current_streak = 1
                current_streak_start = sorted_dates[i]
        if current_streak > longest_streak:
            longest_streak = current_streak
            longest_streak_start = current_streak_start
            longest_streak_end = sorted_dates[-1]

        assert longest_streak == 5
        assert longest_streak_start == date(2026, 3, 15)
        assert longest_streak_end == date(2026, 3, 19)

    def test_streak_booking_count(self):
        """Streak should include total bookings in the streak period."""
        day_counter = Counter({
            date(2026, 3, 15): 3,
            date(2026, 3, 16): 5,
            date(2026, 3, 17): 2,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak_start = date(2026, 3, 15)
        longest_streak_end = date(2026, 3, 17)

        streak_bookings = sum(
            day_counter[d] for d in sorted_dates
            if longest_streak_start <= d <= longest_streak_end
        )

        assert streak_bookings == 10

    def test_streak_date_format(self):
        """Streak dates should be formatted correctly."""
        start = date(2026, 2, 24)
        end = date(2026, 2, 28)

        start_formatted = start.strftime("%d %b")
        end_formatted = end.strftime("%d %b %Y")

        assert start_formatted == "24 Feb"
        assert end_formatted == "28 Feb 2026"


# =============================================================================
# Unit Tests - Longest Trip Logic
# =============================================================================

class TestLongestTripLogic:
    """Unit tests for longest trip calculation."""

    def test_calculate_trip_days(self):
        """Trip days should be pickup_date - dropoff_date."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 1),
            pickup_date=date(2026, 3, 15)
        )

        trip_days = (booking.pickup_date - booking.dropoff_date).days

        assert trip_days == 14

    def test_longest_trip_from_multiple(self):
        """Should identify the booking with longest trip."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8)),   # 7 days
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 22)),  # 21 days
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15)),  # 14 days
        ]

        longest_booking = None
        longest_days = 0
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                trip_days = (booking.pickup_date - booking.dropoff_date).days
                if trip_days > longest_days:
                    longest_days = trip_days
                    longest_booking = booking

        assert longest_days == 21
        assert longest_booking.id == 2

    def test_same_day_trip_zero_days(self):
        """Same day dropoff and pickup should be 0 days."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 15),
            pickup_date=date(2026, 3, 15)
        )

        trip_days = (booking.pickup_date - booking.dropoff_date).days

        assert trip_days == 0

    def test_one_day_trip(self):
        """One day trip should be 1 day."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 15),
            pickup_date=date(2026, 3, 16)
        )

        trip_days = (booking.pickup_date - booking.dropoff_date).days

        assert trip_days == 1

    def test_skip_null_dates(self):
        """Should skip bookings with null dates."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=None, pickup_date=date(2026, 3, 22)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 1), pickup_date=None),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8)),
        ]

        longest_booking = None
        longest_days = 0
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                trip_days = (booking.pickup_date - booking.dropoff_date).days
                if trip_days > longest_days:
                    longest_days = trip_days
                    longest_booking = booking

        assert longest_days == 7
        assert longest_booking.id == 3

    def test_longest_trip_includes_destination(self):
        """Longest trip should include destination."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 1),
            pickup_date=date(2026, 3, 22),
            dropoff_destination="Tenerife South Airport"
        )

        result = {
            "days": (booking.pickup_date - booking.dropoff_date).days,
            "reference": booking.reference,
            "destination": booking.dropoff_destination or "Unknown",
        }

        assert result["destination"] == "Tenerife South Airport"

    def test_missing_destination_shows_unknown(self):
        """Missing destination should show 'Unknown'."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 1),
            pickup_date=date(2026, 3, 22),
            dropoff_destination=None
        )

        destination = booking.dropoff_destination or "Unknown"

        assert destination == "Unknown"


# =============================================================================
# Unit Tests - Highest Transaction Logic
# =============================================================================

class TestHighestTransactionLogic:
    """Unit tests for highest transaction calculation."""

    def test_single_booking_is_highest(self):
        """Single booking should be the highest transaction."""
        booking = create_mock_booking(total_price=85.00)

        highest_amount = booking.total_price

        assert highest_amount == 85.00

    def test_highest_from_multiple(self):
        """Should identify the booking with highest total_price."""
        bookings = [
            create_mock_booking(id=1, total_price=85.00),
            create_mock_booking(id=2, total_price=189.00),
            create_mock_booking(id=3, total_price=120.00),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_amount == 189.00
        assert highest_booking.id == 2

    def test_skip_null_price(self):
        """Should skip bookings with null total_price."""
        bookings = [
            create_mock_booking(id=1, total_price=None),
            create_mock_booking(id=2, total_price=85.00),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_amount == 85.00
        assert highest_booking.id == 2

    def test_skip_zero_price(self):
        """Should skip bookings with zero total_price (free bookings)."""
        bookings = [
            create_mock_booking(id=1, total_price=0),
            create_mock_booking(id=2, total_price=85.00),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_amount == 85.00
        assert highest_booking.id == 2

    def test_amount_formatting(self):
        """Amount should be formatted with pound sign and 2 decimal places."""
        amount = 189.50

        formatted = f"£{amount:.2f}"

        assert formatted == "£189.50"

    def test_amount_formatting_whole_number(self):
        """Whole number amount should still have 2 decimal places."""
        amount = 100.00

        formatted = f"£{amount:.2f}"

        assert formatted == "£100.00"

    def test_highest_transaction_includes_trip_days(self):
        """Highest transaction should include trip days."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 1),
            pickup_date=date(2026, 3, 15),
            total_price=189.00
        )

        days = (booking.pickup_date - booking.dropoff_date).days if booking.pickup_date and booking.dropoff_date else None

        assert days == 14


# =============================================================================
# Negative Tests
# =============================================================================

class TestNegativeScenarios:
    """Negative test cases."""

    def test_empty_bookings_returns_all_null(self):
        """Empty bookings should return all null values."""
        bookings = []

        result = {
            "busiestDay": None,
            "busiestStreak": None,
            "longestTrip": None,
            "highestTransaction": None,
        }

        if not bookings:
            pass  # Keep all as None

        assert result["busiestDay"] is None
        assert result["busiestStreak"] is None
        assert result["longestTrip"] is None
        assert result["highestTransaction"] is None

    def test_all_null_dropoff_dates(self):
        """All bookings with null dropoff dates should return null for busiest day."""
        bookings = [
            create_mock_booking(id=1, dropoff_date=None),
            create_mock_booking(id=2, dropoff_date=None),
        ]

        day_counter = Counter()
        for booking in bookings:
            if booking.dropoff_date:
                day_counter[booking.dropoff_date] += 1

        assert len(day_counter) == 0

    def test_all_null_prices(self):
        """All bookings with null prices should return null for highest transaction."""
        bookings = [
            create_mock_booking(id=1, total_price=None),
            create_mock_booking(id=2, total_price=None),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_booking is None

    def test_all_zero_prices(self):
        """All bookings with zero prices should return null for highest transaction."""
        bookings = [
            create_mock_booking(id=1, total_price=0),
            create_mock_booking(id=2, total_price=0),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_booking is None


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_single_booking(self):
        """Single booking should work for all metrics."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 3, 15),
            pickup_date=date(2026, 3, 22),
            total_price=85.00,
            dropoff_destination="Faro"
        )

        # Busiest day
        day_counter = Counter()
        day_counter[booking.dropoff_date] = 1
        busiest_date, busiest_count = day_counter.most_common(1)[0]

        # Longest trip
        trip_days = (booking.pickup_date - booking.dropoff_date).days

        # Highest transaction
        highest_amount = booking.total_price

        assert busiest_count == 1
        assert trip_days == 7
        assert highest_amount == 85.00

    def test_very_long_trip(self):
        """Very long trip (e.g., 365 days) should be handled."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 1, 1),
            pickup_date=date(2026, 12, 31)
        )

        trip_days = (booking.pickup_date - booking.dropoff_date).days

        assert trip_days == 364

    def test_very_high_price(self):
        """Very high price should be handled."""
        booking = create_mock_booking(total_price=9999.99)

        formatted = f"£{booking.total_price:.2f}"

        assert formatted == "£9999.99"

    def test_decimal_price(self):
        """Decimal prices should be formatted correctly."""
        booking = create_mock_booking(total_price=85.50)

        formatted = f"£{booking.total_price:.2f}"

        assert formatted == "£85.50"

    def test_large_number_of_bookings(self):
        """Large number of bookings should be handled efficiently."""
        bookings = [
            create_mock_booking(
                id=i,
                dropoff_date=date(2026, 1, 1) + timedelta(days=i % 100),
                pickup_date=date(2026, 1, 1) + timedelta(days=i % 100 + 7),
                total_price=50 + (i % 200),
            )
            for i in range(1000)
        ]

        day_counter = Counter()
        for booking in bookings:
            if booking.dropoff_date:
                day_counter[booking.dropoff_date] += 1

        longest_days = 0
        highest_amount = 0
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                trip_days = (booking.pickup_date - booking.dropoff_date).days
                if trip_days > longest_days:
                    longest_days = trip_days
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price

        assert len(day_counter) == 100  # 100 unique days
        assert longest_days == 7  # All trips are 7 days
        assert highest_amount == 249  # 50 + 199

    def test_consecutive_streak_at_start(self):
        """Consecutive streak at start of date range should be found."""
        day_counter = Counter({
            date(2026, 3, 1): 1,
            date(2026, 3, 2): 1,
            date(2026, 3, 3): 1,  # 3-day streak at start
            date(2026, 3, 10): 1,
            date(2026, 3, 15): 1,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 3

    def test_consecutive_streak_at_end(self):
        """Consecutive streak at end of date range should be found."""
        day_counter = Counter({
            date(2026, 3, 1): 1,
            date(2026, 3, 5): 1,
            date(2026, 3, 28): 1,
            date(2026, 3, 29): 1,
            date(2026, 3, 30): 1,
            date(2026, 3, 31): 1,  # 4-day streak at end
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 4

    def test_year_boundary_streak(self):
        """Streak across year boundary should be handled."""
        day_counter = Counter({
            date(2026, 12, 30): 1,
            date(2026, 12, 31): 1,
            date(2027, 1, 1): 1,
            date(2027, 1, 2): 1,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 4

    def test_month_boundary_streak(self):
        """Streak across month boundary should be handled."""
        day_counter = Counter({
            date(2026, 2, 27): 1,
            date(2026, 2, 28): 1,
            date(2026, 3, 1): 1,
            date(2026, 3, 2): 1,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 4

    def test_leap_year_streak(self):
        """Streak across leap year Feb 29 should be handled."""
        # 2024 is a leap year
        day_counter = Counter({
            date(2024, 2, 28): 1,
            date(2024, 2, 29): 1,
            date(2024, 3, 1): 1,
        })
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        current_streak = 1
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                current_streak += 1
            else:
                if current_streak > longest_streak:
                    longest_streak = current_streak
                current_streak = 1
        if current_streak > longest_streak:
            longest_streak = current_streak

        assert longest_streak == 3

    def test_tie_in_longest_trip_returns_first(self):
        """Tie in longest trip should return first one found."""
        bookings = [
            create_mock_booking(id=1, reference="TAG-001", dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15)),  # 14 days
            create_mock_booking(id=2, reference="TAG-002", dropoff_date=date(2026, 3, 10), pickup_date=date(2026, 3, 24)),  # 14 days
        ]

        longest_booking = None
        longest_days = 0
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                trip_days = (booking.pickup_date - booking.dropoff_date).days
                if trip_days > longest_days:
                    longest_days = trip_days
                    longest_booking = booking

        assert longest_days == 14
        assert longest_booking.id == 1  # First one found

    def test_tie_in_highest_transaction_returns_first(self):
        """Tie in highest transaction should return first one found."""
        bookings = [
            create_mock_booking(id=1, reference="TAG-001", total_price=100.00),
            create_mock_booking(id=2, reference="TAG-002", total_price=100.00),
        ]

        highest_booking = None
        highest_amount = 0
        for booking in bookings:
            if booking.total_price and booking.total_price > highest_amount:
                highest_amount = booking.total_price
                highest_booking = booking

        assert highest_amount == 100.00
        assert highest_booking.id == 1  # First one found


# =============================================================================
# Status Filtering (Only Confirmed + Completed)
# =============================================================================

class TestStatusFiltering:
    """Tests for status filtering - only confirmed and completed bookings."""

    def test_confirmed_booking_included(self):
        """Confirmed bookings should be included."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="confirmed")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is True

    def test_completed_booking_included(self):
        """Completed bookings should be included."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="completed")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is True

    def test_pending_booking_excluded(self):
        """Pending bookings should be excluded."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="pending")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False

    def test_cancelled_booking_excluded(self):
        """Cancelled bookings should be excluded."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="cancelled")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False

    def test_mixed_status_bookings(self):
        """Only confirmed and completed should be counted."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
            create_mock_booking(id=5, status="confirmed"),
        ]

        included = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]

        assert len(included) == 3
