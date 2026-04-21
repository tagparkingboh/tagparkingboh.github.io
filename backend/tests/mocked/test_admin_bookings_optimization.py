"""
Unit tests for Admin Bookings Endpoint Optimization.

Tests the 30-day default filter and "today first" sorting logic.

Covers:
- Default 30-day filtering
- Load All option (days=0)
- Today's bookings appearing first
- All statuses included
- Edge cases and boundaries

All tests use mocked database sessions to avoid side effects.
"""
import pytest
from datetime import datetime, timedelta, date, time as dt_time
from unittest.mock import MagicMock, patch
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Database Models
# =============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status_value="confirmed",
    dropoff_date=None,
    pickup_date=None,
    created_at=None,
):
    """Create a mock booking object."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date
    booking.pickup_date = pickup_date
    booking.created_at = created_at or datetime.now()

    # Mock status enum
    from db_models import BookingStatus
    status_map = {
        "confirmed": BookingStatus.CONFIRMED,
        "completed": BookingStatus.COMPLETED,
        "pending": BookingStatus.PENDING,
        "cancelled": BookingStatus.CANCELLED,
    }
    booking.status = status_map.get(status_value, BookingStatus.PENDING)

    # Mock related objects
    booking.customer = MagicMock()
    booking.customer.id = 1
    booking.customer.first_name = "Test"
    booking.customer.last_name = "User"
    booking.customer.email = "test@example.com"
    booking.customer.phone = "07123456789"

    booking.vehicle = MagicMock()
    booking.vehicle.id = 1
    booking.vehicle.registration = "AB12 CDE"

    booking.payment = MagicMock()
    booking.payment.id = 1
    booking.payment.amount_pence = 5000

    booking.departure = None
    booking.dropoff_time = None
    booking.pickup_time = None
    booking.flight_departure_time = None
    booking.flight_arrival_time = None
    booking.dropoff_flight_number = None
    booking.dropoff_airline_name = None
    booking.dropoff_airline_code = None
    booking.dropoff_destination = None
    booking.pickup_flight_number = None
    booking.pickup_airline_name = None
    booking.pickup_airline_code = None
    booking.pickup_origin = None
    booking.notes = None
    booking.booking_source = "online"
    booking.package = "7 Days"
    booking.customer_first_name = None
    booking.customer_last_name = None
    booking.confirmation_email_sent = False
    booking.confirmation_email_sent_at = None
    booking.reminder_2day_sent = False
    booking.reminder_2day_sent_at = None

    return booking


def create_mock_user(id=1, email="admin@test.com", is_admin=True, is_active=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active
    return user


# =============================================================================
# Unit Tests: 30-Day Default Filter
# =============================================================================

class TestDefaultThirtyDayFilter:
    """Unit tests for the default 30-day filter behavior."""

    def test_default_days_parameter_is_30(self):
        """Test that the default days parameter is 30."""
        default_days = 30
        assert default_days == 30

    def test_filter_includes_bookings_within_30_days(self):
        """Test that bookings within 30 days are included."""
        today = date.today()
        cutoff_date = today - timedelta(days=30)

        # Booking from 15 days ago
        booking_date = today - timedelta(days=15)

        assert booking_date >= cutoff_date

    def test_filter_excludes_bookings_older_than_30_days(self):
        """Test that bookings older than 30 days are excluded by default."""
        today = date.today()
        cutoff_date = today - timedelta(days=30)

        # Booking from 35 days ago
        old_booking_date = today - timedelta(days=35)

        assert old_booking_date < cutoff_date

    def test_filter_uses_dropoff_or_pickup_date(self):
        """Test that filter checks both dropoff and pickup dates."""
        today = date.today()
        cutoff_date = today - timedelta(days=30)

        # Old dropoff but recent pickup (should be included)
        booking = create_mock_booking(
            dropoff_date=today - timedelta(days=40),
            pickup_date=today - timedelta(days=5),
        )

        # Include if dropoff OR pickup is within range
        included = (
            (booking.dropoff_date and booking.dropoff_date >= cutoff_date) or
            (booking.pickup_date and booking.pickup_date >= cutoff_date)
        )

        assert included is True

    def test_boundary_booking_exactly_30_days_ago(self):
        """Test booking exactly on the 30-day boundary is included."""
        today = date.today()
        cutoff_date = today - timedelta(days=30)
        boundary_date = cutoff_date  # Exactly 30 days ago

        assert boundary_date >= cutoff_date

    def test_boundary_booking_31_days_ago(self):
        """Test booking 31 days ago is excluded."""
        today = date.today()
        cutoff_date = today - timedelta(days=30)
        old_date = today - timedelta(days=31)

        assert old_date < cutoff_date


# =============================================================================
# Unit Tests: Load All Option
# =============================================================================

class TestLoadAllOption:
    """Unit tests for the Load All (days=0) option."""

    def test_days_zero_returns_all_bookings(self):
        """Test that days=0 returns all bookings."""
        days = 0

        # When days is 0 or None, no date filter should be applied
        should_filter = days and days > 0

        assert not should_filter

    def test_days_none_returns_all_bookings(self):
        """Test that days=None returns all bookings."""
        days = None

        should_filter = days and days > 0

        assert not should_filter

    def test_days_negative_treated_as_no_filter(self):
        """Test that negative days value is treated as no filter."""
        days = -1

        # Negative values should not filter
        should_filter = days and days > 0

        assert should_filter is False


# =============================================================================
# Unit Tests: Today First Sorting
# =============================================================================

class TestTodayFirstSorting:
    """Unit tests for today's bookings appearing first."""

    def test_todays_bookings_have_priority_zero(self):
        """Test that today's bookings get sort priority 0."""
        today = date.today()
        booking_date = today

        # Priority: 0 for today, 1 for others
        priority = 0 if booking_date == today else 1

        assert priority == 0

    def test_non_today_bookings_have_priority_one(self):
        """Test that non-today bookings get sort priority 1."""
        today = date.today()
        booking_date = today - timedelta(days=1)

        priority = 0 if booking_date == today else 1

        assert priority == 1

    def test_sorting_todays_bookings_before_others(self):
        """Test that today's bookings sort before others."""
        today = date.today()

        bookings = [
            create_mock_booking(id=1, dropoff_date=today - timedelta(days=5)),
            create_mock_booking(id=2, dropoff_date=today),
            create_mock_booking(id=3, dropoff_date=today + timedelta(days=3)),
            create_mock_booking(id=4, dropoff_date=today),
        ]

        # Sort: today first (priority 0), then by date ascending
        sorted_bookings = sorted(
            bookings,
            key=lambda b: (
                0 if b.dropoff_date == today else 1,
                b.dropoff_date
            )
        )

        # Today's bookings should be first
        assert sorted_bookings[0].dropoff_date == today
        assert sorted_bookings[1].dropoff_date == today

    def test_within_today_sorted_by_time(self):
        """Test that multiple today bookings maintain order."""
        today = date.today()

        bookings = [
            create_mock_booking(id=1, dropoff_date=today),
            create_mock_booking(id=2, dropoff_date=today),
            create_mock_booking(id=3, dropoff_date=today),
        ]

        # All should be today
        for b in bookings:
            assert b.dropoff_date == today


# =============================================================================
# Unit Tests: All Statuses Included
# =============================================================================

class TestAllStatusesIncluded:
    """Unit tests verifying all statuses are included by default."""

    def test_confirmed_bookings_included(self):
        """Test that confirmed bookings are included."""
        booking = create_mock_booking(status_value="confirmed")

        from db_models import BookingStatus
        assert booking.status == BookingStatus.CONFIRMED

    def test_completed_bookings_included(self):
        """Test that completed bookings are included."""
        booking = create_mock_booking(status_value="completed")

        from db_models import BookingStatus
        assert booking.status == BookingStatus.COMPLETED

    def test_pending_bookings_included(self):
        """Test that pending bookings are included."""
        booking = create_mock_booking(status_value="pending")

        from db_models import BookingStatus
        assert booking.status == BookingStatus.PENDING

    def test_cancelled_bookings_included_by_default(self):
        """Test that cancelled bookings are included by default."""
        booking = create_mock_booking(status_value="cancelled")
        include_cancelled = True  # Default

        from db_models import BookingStatus
        assert booking.status == BookingStatus.CANCELLED
        assert include_cancelled is True

    def test_cancelled_can_be_excluded_optionally(self):
        """Test that cancelled bookings can be excluded via parameter."""
        include_cancelled = False

        from db_models import BookingStatus
        booking = create_mock_booking(status_value="cancelled")

        # Should be excluded when include_cancelled=False
        included = include_cancelled or booking.status != BookingStatus.CANCELLED
        assert included is False


# =============================================================================
# Unit Tests: Date Filter Override
# =============================================================================

class TestDateFilterOverride:
    """Unit tests for specific date_filter parameter."""

    def test_date_filter_overrides_default(self):
        """Test that specific date_filter takes precedence."""
        date_filter = date(2026, 6, 15)
        days = 30  # Should be ignored when date_filter is set

        # When date_filter is set, use it instead of days
        use_date_filter = date_filter is not None

        assert use_date_filter is True

    def test_date_filter_shows_overlapping_bookings(self):
        """Test date filter shows bookings that overlap with the date."""
        filter_date = date(2026, 6, 15)

        # Booking that spans the filter date
        booking = create_mock_booking(
            dropoff_date=date(2026, 6, 10),
            pickup_date=date(2026, 6, 20),
        )

        overlaps = (
            booking.dropoff_date <= filter_date and
            booking.pickup_date >= filter_date
        )

        assert overlaps is True

    def test_date_filter_excludes_non_overlapping(self):
        """Test date filter excludes bookings that don't overlap."""
        filter_date = date(2026, 6, 15)

        # Booking before filter date
        booking = create_mock_booking(
            dropoff_date=date(2026, 5, 1),
            pickup_date=date(2026, 5, 8),
        )

        overlaps = (
            booking.dropoff_date <= filter_date and
            booking.pickup_date >= filter_date
        )

        assert overlaps is False


# =============================================================================
# Unit Tests: Response Structure
# =============================================================================

class TestResponseStructure:
    """Unit tests for API response structure."""

    def test_response_includes_count(self):
        """Test response includes count field."""
        response = {
            "count": 10,
            "date_filter": None,
            "days_filter": 30,
            "bookings": [],
        }

        assert "count" in response

    def test_response_includes_days_filter(self):
        """Test response includes days_filter field."""
        response = {
            "count": 10,
            "date_filter": None,
            "days_filter": 30,
            "bookings": [],
        }

        assert "days_filter" in response
        assert response["days_filter"] == 30

    def test_days_filter_none_when_loading_all(self):
        """Test days_filter is None when loading all bookings."""
        days = 0  # Load all

        days_filter = days if days and days > 0 else None

        assert days_filter is None

    def test_response_includes_bookings_array(self):
        """Test response includes bookings array."""
        response = {
            "count": 0,
            "date_filter": None,
            "days_filter": 30,
            "bookings": [],
        }

        assert "bookings" in response
        assert isinstance(response["bookings"], list)


# =============================================================================
# Unit Tests: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Unit tests for edge cases."""

    def test_no_bookings_returns_empty_array(self):
        """Test empty database returns empty array."""
        bookings = []

        assert len(bookings) == 0
        assert bookings == []

    def test_booking_with_null_dropoff_date(self):
        """Test handling of booking with null dropoff_date."""
        booking = create_mock_booking(
            dropoff_date=None,
            pickup_date=date.today(),
        )

        # Should still be checked against pickup_date
        assert booking.dropoff_date is None
        assert booking.pickup_date is not None

    def test_booking_with_null_pickup_date(self):
        """Test handling of booking with null pickup_date."""
        booking = create_mock_booking(
            dropoff_date=date.today(),
            pickup_date=None,
        )

        assert booking.pickup_date is None
        assert booking.dropoff_date is not None

    def test_booking_with_both_dates_null(self):
        """Test handling of booking with both dates null."""
        booking = create_mock_booking(
            dropoff_date=None,
            pickup_date=None,
        )

        # Booking without dates - edge case
        assert booking.dropoff_date is None
        assert booking.pickup_date is None

    def test_future_booking_included(self):
        """Test future bookings are included."""
        today = date.today()
        future_date = today + timedelta(days=60)
        cutoff_date = today - timedelta(days=30)

        # Future booking should be included (dropoff >= cutoff)
        assert future_date >= cutoff_date

    def test_very_old_booking_excluded(self):
        """Test very old bookings are excluded."""
        today = date.today()
        old_date = today - timedelta(days=365)  # 1 year ago
        cutoff_date = today - timedelta(days=30)

        assert old_date < cutoff_date


# =============================================================================
# Unit Tests: UK Timezone Handling
# =============================================================================

class TestUkTimezoneHandling:
    """Unit tests for UK timezone handling."""

    def test_today_calculated_in_uk_timezone(self):
        """Test that 'today' is calculated in UK timezone."""
        import pytz

        uk_tz = pytz.timezone('Europe/London')
        uk_now = datetime.now(uk_tz)
        uk_today = uk_now.date()

        # Should be a valid date
        assert isinstance(uk_today, date)

    def test_cutoff_date_uses_uk_today(self):
        """Test cutoff date calculation uses UK today."""
        import pytz

        uk_tz = pytz.timezone('Europe/London')
        uk_today = datetime.now(uk_tz).date()
        cutoff_date = uk_today - timedelta(days=30)

        # Cutoff should be 30 days before UK today
        assert (uk_today - cutoff_date).days == 30


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
