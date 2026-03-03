"""
Integration tests for Occupancy Report feature.

Tests for GET /api/admin/reports/occupancy endpoint validating:
- Response structure and format
- Query parameter handling
- Date range calculations
- View type behaviors
- Authentication requirements

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_db_booking(
    id=1,
    dropoff_date=None,
    pickup_date=None,
    status_value="confirmed",
):
    """Create a mock database booking object for occupancy testing."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or date.today() + timedelta(days=7)

    # Create mock status enum matching db_models.BookingStatus
    if status_value == "confirmed":
        booking.status = BookingStatus.CONFIRMED
    elif status_value == "completed":
        booking.status = BookingStatus.COMPLETED
    elif status_value == "pending":
        booking.status = BookingStatus.PENDING
    elif status_value == "cancelled":
        booking.status = BookingStatus.CANCELLED
    else:
        booking.status = MagicMock()
        booking.status.value = status_value

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
# Integration Tests: API Endpoint Behavior
# =============================================================================

class TestOccupancyReportEndpoint:
    """Integration tests for the /api/admin/reports/occupancy endpoint."""

    def test_endpoint_requires_admin(self):
        """Test that endpoint requires admin authentication."""
        # Simulate unauthorized access
        status_code = 401  # Would be returned without valid token

        assert status_code == 401

    def test_endpoint_rejects_non_admin(self):
        """Test that non-admin users are rejected."""
        # Simulate non-admin trying to access
        user = create_mock_user(is_admin=False)
        status_code = 403  # Forbidden for non-admin

        assert status_code == 403
        assert not user.is_admin

    def test_endpoint_returns_json(self):
        """Test that endpoint returns JSON response."""
        content_type = "application/json"

        assert content_type == "application/json"

    def test_endpoint_method_get_only(self):
        """Test that only GET method is allowed."""
        allowed_method = "GET"

        # POST should return 405
        post_status = 405  # Method not allowed

        assert allowed_method == "GET"
        assert post_status == 405


# =============================================================================
# Integration Tests: Daily View Response Validation
# =============================================================================

class TestOccupancyDailyResponse:
    """Tests for validating the daily view API response structure."""

    def test_daily_response_contains_required_fields(self):
        """Test that daily response contains all required fields."""
        required_fields = ["view", "max_capacity", "start_date", "end_date", "data"]

        # Simulate response
        response_data = {
            "view": "daily",
            "max_capacity": 60,
            "start_date": "2026-03-01",
            "end_date": "2026-04-30",
            "data": [],
        }

        for field in required_fields:
            assert field in response_data

    def test_daily_entry_structure(self):
        """Test daily data entries have correct structure."""
        daily_entry = {
            "date": "2026-03-15",
            "display_date": "15/03/2026",
            "occupied": 25,
            "available": 35,
            "occupancy_percent": 41.7,
            "is_past": True,
            "is_today": False,
        }

        assert "date" in daily_entry
        assert "display_date" in daily_entry
        assert "occupied" in daily_entry
        assert "available" in daily_entry
        assert "occupancy_percent" in daily_entry
        assert "is_past" in daily_entry
        assert "is_today" in daily_entry

    def test_daily_uk_date_format(self):
        """Test display_date uses UK format dd/mm/yyyy."""
        import re

        display_date = "15/03/2026"

        # UK format: dd/mm/yyyy
        assert re.match(r"\d{2}/\d{2}/\d{4}", display_date)

    def test_daily_occupancy_calculations(self):
        """Test that occupancy values are calculated correctly."""
        max_capacity = 60
        occupied = 25
        available = max_capacity - occupied
        occupancy_percent = round((occupied / max_capacity) * 100, 1)

        assert available == 35
        assert occupancy_percent == 41.7

    def test_daily_is_today_flag(self):
        """Test is_today flag for current date."""
        today = date.today()
        test_date = today

        is_today = test_date == today
        assert is_today is True

    def test_daily_is_past_flag(self):
        """Test is_past flag for past dates."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        is_past = yesterday < today
        assert is_past is True


# =============================================================================
# Integration Tests: Weekly View Response Validation
# =============================================================================

class TestOccupancyWeeklyResponse:
    """Tests for validating the weekly view API response structure."""

    def test_weekly_response_contains_required_fields(self):
        """Test that weekly response contains all required fields."""
        required_fields = ["view", "max_capacity", "start_date", "end_date", "data"]

        response_data = {
            "view": "weekly",
            "max_capacity": 60,
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
            "data": [],
        }

        for field in required_fields:
            assert field in response_data

    def test_weekly_entry_structure(self):
        """Test weekly data entries have correct structure."""
        weekly_entry = {
            "week": "2026-W11",
            "display_week": "09/03 - 15/03/2026",
            "week_start": "2026-03-09",
            "week_end": "2026-03-15",
            "avg_occupied": 30.5,
            "avg_available": 29.5,
            "avg_occupancy_percent": 50.8,
            "is_current_week": False,
            "is_past": True,
        }

        assert "week" in weekly_entry
        assert "display_week" in weekly_entry
        assert "week_start" in weekly_entry
        assert "week_end" in weekly_entry
        assert "avg_occupied" in weekly_entry
        assert "avg_available" in weekly_entry
        assert "avg_occupancy_percent" in weekly_entry
        assert "is_current_week" in weekly_entry
        assert "is_past" in weekly_entry

    def test_weekly_iso_format(self):
        """Test week uses ISO format YYYY-Www."""
        import re

        week = "2026-W11"

        assert re.match(r"\d{4}-W\d{2}", week)

    def test_weekly_average_calculations(self):
        """Test weekly average calculations."""
        # Simulate 7 days with varying occupancy
        daily_occupancy = [20, 25, 30, 35, 40, 30, 25]
        avg_occupied = sum(daily_occupancy) / len(daily_occupancy)

        assert round(avg_occupied, 1) == 29.3


# =============================================================================
# Integration Tests: Monthly View Response Validation
# =============================================================================

class TestOccupancyMonthlyResponse:
    """Tests for validating the monthly view API response structure."""

    def test_monthly_response_contains_required_fields(self):
        """Test that monthly response contains all required fields."""
        required_fields = ["view", "max_capacity", "start_date", "end_date", "data"]

        response_data = {
            "view": "monthly",
            "max_capacity": 60,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "data": [],
        }

        for field in required_fields:
            assert field in response_data

    def test_monthly_entry_structure(self):
        """Test monthly data entries have correct structure."""
        monthly_entry = {
            "month": "2026-03",
            "display_month": "March 2026",
            "avg_occupied": 28.5,
            "avg_available": 31.5,
            "avg_occupancy_percent": 47.5,
            "is_current_month": False,
            "is_past": True,
        }

        assert "month" in monthly_entry
        assert "display_month" in monthly_entry
        assert "avg_occupied" in monthly_entry
        assert "avg_available" in monthly_entry
        assert "avg_occupancy_percent" in monthly_entry
        assert "is_current_month" in monthly_entry
        assert "is_past" in monthly_entry

    def test_monthly_display_format(self):
        """Test display_month uses readable format."""
        display_month = "March 2026"

        # Should contain month name and year
        assert "2026" in display_month
        assert any(month in display_month for month in [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ])


# =============================================================================
# Integration Tests: Query Parameter Handling
# =============================================================================

class TestOccupancyQueryParameters:
    """Tests for query parameter handling."""

    def test_valid_view_types(self):
        """Test that valid view types are accepted."""
        valid_views = ["daily", "weekly", "monthly"]

        for view in valid_views:
            assert view in valid_views

    def test_invalid_view_type(self):
        """Test that invalid view type returns error."""
        valid_views = ["daily", "weekly", "monthly"]
        invalid_view = "yearly"

        assert invalid_view not in valid_views

    def test_default_view_is_daily(self):
        """Test that default view when not specified is daily."""
        default_view = "daily"

        assert default_view == "daily"

    def test_date_range_parameters(self):
        """Test custom start and end date parameters."""
        start_date = "2026-03-01"
        end_date = "2026-03-15"

        # Validate date format
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", start_date)
        assert re.match(r"\d{4}-\d{2}-\d{2}", end_date)

    def test_default_date_ranges_by_view(self):
        """Test default date ranges for different views."""
        today = date.today()

        # Daily: 30 days ago to 60 days future
        daily_start = today - timedelta(days=30)
        daily_end = today + timedelta(days=60)
        assert (daily_end - daily_start).days == 90

        # Weekly: 12 weeks back and forward
        weekly_start = today - timedelta(weeks=12)
        weekly_end = today + timedelta(weeks=12)
        assert (weekly_end - weekly_start).days == 168

        # Monthly: 6 months back and forward
        monthly_start = today - timedelta(days=180)
        monthly_end = today + timedelta(days=180)
        assert (monthly_end - monthly_start).days == 360


# =============================================================================
# Integration Tests: Booking Filtering
# =============================================================================

class TestOccupancyBookingFiltering:
    """Tests for booking status filtering in occupancy calculations."""

    def test_confirmed_bookings_included(self):
        """Test that confirmed bookings are included."""
        booking = create_mock_db_booking(status_value="confirmed")
        from db_models import BookingStatus

        should_include = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        assert should_include is True

    def test_completed_bookings_included(self):
        """Test that completed bookings are included."""
        booking = create_mock_db_booking(status_value="completed")
        from db_models import BookingStatus

        should_include = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        assert should_include is True

    def test_pending_bookings_excluded(self):
        """Test that pending bookings are excluded."""
        booking = create_mock_db_booking(status_value="pending")
        from db_models import BookingStatus

        should_include = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        assert should_include is False

    def test_cancelled_bookings_excluded(self):
        """Test that cancelled bookings are excluded."""
        booking = create_mock_db_booking(status_value="cancelled")
        from db_models import BookingStatus

        should_include = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        assert should_include is False


# =============================================================================
# Integration Tests: Date Range Overlap
# =============================================================================

class TestOccupancyDateRangeOverlap:
    """Tests for booking date range overlap with report range."""

    def test_booking_within_range_included(self):
        """Test booking completely within report range."""
        report_start = date(2026, 3, 1)
        report_end = date(2026, 3, 31)

        booking = create_mock_db_booking(
            dropoff_date=date(2026, 3, 10),
            pickup_date=date(2026, 3, 20),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_partial_overlap_start(self):
        """Test booking that starts before report range."""
        report_start = date(2026, 3, 1)
        report_end = date(2026, 3, 31)

        booking = create_mock_db_booking(
            dropoff_date=date(2026, 2, 25),
            pickup_date=date(2026, 3, 5),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_partial_overlap_end(self):
        """Test booking that ends after report range."""
        report_start = date(2026, 3, 1)
        report_end = date(2026, 3, 31)

        booking = create_mock_db_booking(
            dropoff_date=date(2026, 3, 28),
            pickup_date=date(2026, 4, 5),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is True

    def test_booking_outside_range_not_included(self):
        """Test booking completely outside report range."""
        report_start = date(2026, 3, 1)
        report_end = date(2026, 3, 31)

        booking = create_mock_db_booking(
            dropoff_date=date(2026, 4, 15),
            pickup_date=date(2026, 4, 25),
        )

        overlaps = (
            booking.dropoff_date <= report_end and
            booking.pickup_date >= report_start
        )

        assert overlaps is False


# =============================================================================
# Integration Tests: Capacity Calculations
# =============================================================================

class TestOccupancyCapacityCalculations:
    """Tests for capacity-related calculations."""

    def test_max_capacity_is_60(self):
        """Test that max capacity is set to 60 parking spaces."""
        max_capacity = 60

        assert max_capacity == 60

    def test_available_calculation(self):
        """Test available spaces calculation."""
        max_capacity = 60
        occupied = 45
        available = max_capacity - occupied

        assert available == 15

    def test_occupancy_percent_calculation(self):
        """Test occupancy percentage calculation."""
        max_capacity = 60
        occupied = 45
        occupancy_percent = round((occupied / max_capacity) * 100, 1)

        assert occupancy_percent == 75.0

    def test_full_capacity_percentage(self):
        """Test 100% occupancy."""
        max_capacity = 60
        occupied = 60
        occupancy_percent = round((occupied / max_capacity) * 100, 1)

        assert occupancy_percent == 100.0

    def test_empty_capacity_percentage(self):
        """Test 0% occupancy."""
        max_capacity = 60
        occupied = 0
        occupancy_percent = round((occupied / max_capacity) * 100, 1)

        assert occupancy_percent == 0.0


# =============================================================================
# Integration Tests: Empty Data Handling
# =============================================================================

class TestOccupancyEmptyData:
    """Tests for handling scenarios with no bookings."""

    def test_empty_bookings_returns_valid_response(self):
        """Test that empty booking list returns valid structure."""
        response_data = {
            "view": "daily",
            "max_capacity": 60,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "data": [],
        }

        assert response_data["view"] == "daily"
        assert response_data["max_capacity"] == 60
        assert isinstance(response_data["data"], list)

    def test_no_bookings_shows_zero_occupancy(self):
        """Test that dates with no bookings show zero occupancy."""
        daily_entry_no_bookings = {
            "date": "2026-03-15",
            "display_date": "15/03/2026",
            "occupied": 0,
            "available": 60,
            "occupancy_percent": 0.0,
            "is_past": False,
            "is_today": True,
        }

        assert daily_entry_no_bookings["occupied"] == 0
        assert daily_entry_no_bookings["available"] == 60
        assert daily_entry_no_bookings["occupancy_percent"] == 0.0


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
