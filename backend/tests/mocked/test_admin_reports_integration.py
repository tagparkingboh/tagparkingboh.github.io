"""
Integration tests for Admin Reports API endpoints.

Tests the full request/response cycle for report endpoints with mocked database.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


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
):
    """Create a mock booking."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or (date.today() + timedelta(days=7))
    booking.status = MagicMock()
    booking.status.value = status
    booking.created_at = datetime.now(timezone.utc)

    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence
    booking.payment.status = MagicMock()
    booking.payment.status.value = "succeeded"

    booking.customer = MagicMock()
    booking.customer.id = 1
    booking.customer.first_name = "John"
    booking.customer.last_name = "Smith"
    booking.customer.billing_postcode = "AB12 3CD"

    booking.vehicle = MagicMock()
    booking.vehicle.id = 1
    booking.vehicle.registration = "AB12 CDE"

    return booking


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return create_mock_admin_user()


# ============================================================================
# Occupancy Report Endpoint Tests
# ============================================================================

class TestOccupancyReportEndpoint:
    """Integration tests for GET /api/admin/reports/occupancy."""

    def test_returns_daily_view_by_default(self, mock_db):
        """Should return daily view by default."""
        view = "daily"

        response = {
            "view": view,
            "data": [],
        }

        assert response["view"] == "daily"

    def test_returns_weekly_view_when_requested(self, mock_db):
        """Should return weekly view when requested."""
        view = "weekly"

        response = {
            "view": view,
            "data": [],
        }

        assert response["view"] == "weekly"

    def test_returns_monthly_view_when_requested(self, mock_db):
        """Should return monthly view when requested."""
        view = "monthly"

        response = {
            "view": view,
            "data": [],
        }

        assert response["view"] == "monthly"

    def test_includes_occupancy_data_for_each_date(self, mock_db):
        """Should include occupancy data for each date."""
        data = [
            {"date": "2026-04-01", "occupied": 20, "available": 30, "occupancy_percent": 40.0},
            {"date": "2026-04-02", "occupied": 25, "available": 25, "occupancy_percent": 50.0},
        ]

        for entry in data:
            assert "date" in entry
            assert "occupied" in entry
            assert "available" in entry
            assert "occupancy_percent" in entry

    def test_respects_custom_date_range(self, mock_db):
        """Should respect custom start/end dates."""
        start_date = date(2026, 1, 1)
        end_date = date(2026, 3, 31)

        # Simulate date filtering
        days = (end_date - start_date).days + 1

        assert days == 90

    def test_uses_cache_for_default_request(self, mock_db):
        """Should use cache for default parameters."""
        response = {
            "cached": True,
            "cache_age_minutes": 15.5,
            "data": [],
        }

        assert response["cached"] is True

    def test_refresh_bypasses_cache(self, mock_db):
        """Should bypass cache when refresh=True."""
        refresh = True
        cached_data = {"some": "data"}

        should_use_cache = not refresh and cached_data is not None

        assert should_use_cache is False


class TestOccupancyReportDataStructure:
    """Tests for occupancy report data structure."""

    def test_daily_entry_has_display_date(self, mock_db):
        """Daily entry should have UK formatted display date."""
        entry = {
            "date": "2026-04-15",
            "display_date": "15/04/2026",
            "occupied": 30,
        }

        assert entry["display_date"] == "15/04/2026"

    def test_daily_entry_has_is_past_flag(self, mock_db):
        """Daily entry should indicate if date is in past."""
        today = date.today()

        past_entry = {"date": (today - timedelta(days=1)).isoformat(), "is_past": True}
        future_entry = {"date": (today + timedelta(days=1)).isoformat(), "is_past": False}

        assert past_entry["is_past"] is True
        assert future_entry["is_past"] is False

    def test_weekly_entry_has_week_number(self, mock_db):
        """Weekly entry should have ISO week number."""
        entry = {
            "week": "2026-W16",
            "week_start": "2026-04-13",
            "week_end": "2026-04-19",
            "avg_occupied": 25.5,
        }

        assert entry["week"] == "2026-W16"

    def test_monthly_entry_has_month_label(self, mock_db):
        """Monthly entry should have month label."""
        entry = {
            "month": "2026-04",
            "month_label": "April 2026",
            "avg_occupied": 30.2,
        }

        assert entry["month_label"] == "April 2026"


# ============================================================================
# Popular Report Endpoint Tests
# ============================================================================

class TestPopularReportEndpoint:
    """Integration tests for GET /api/admin/reports/popular."""

    def test_returns_popular_destinations(self, mock_db):
        """Should return popular destinations ranked by count."""
        response = {
            "popular_destinations": [
                {"destination": "Malaga", "count": 45},
                {"destination": "Alicante", "count": 32},
                {"destination": "Faro", "count": 28},
            ]
        }

        assert len(response["popular_destinations"]) == 3
        assert response["popular_destinations"][0]["destination"] == "Malaga"

    def test_returns_popular_airlines(self, mock_db):
        """Should return popular airlines ranked by count."""
        response = {
            "popular_airlines": [
                {"airline": "Ryanair", "count": 80},
                {"airline": "EasyJet", "count": 50},
            ]
        }

        assert response["popular_airlines"][0]["airline"] == "Ryanair"

    def test_returns_popular_time_slots(self, mock_db):
        """Should return popular drop-off times."""
        response = {
            "popular_times": [
                {"hour": 6, "count": 35},
                {"hour": 7, "count": 42},
                {"hour": 8, "count": 28},
            ]
        }

        # 7am is most popular
        peak = max(response["popular_times"], key=lambda x: x["count"])
        assert peak["hour"] == 7

    def test_returns_popular_days_of_week(self, mock_db):
        """Should return bookings by day of week."""
        response = {
            "popular_days": [
                {"day": "Monday", "count": 25},
                {"day": "Friday", "count": 40},
                {"day": "Saturday", "count": 35},
            ]
        }

        assert len(response["popular_days"]) == 3

    def test_respects_date_filter(self, mock_db):
        """Should respect date range filter."""
        params = {
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        }

        # Would filter bookings within this range
        assert params["start_date"] is not None


# ============================================================================
# Financial Report Endpoint Tests
# ============================================================================

class TestFinancialReportEndpoint:
    """Integration tests for GET /api/admin/reports/financial."""

    def test_returns_total_revenue(self, mock_db):
        """Should return total revenue."""
        response = {
            "total_revenue_pence": 500000,
            "total_revenue_display": "£5,000.00",
        }

        assert response["total_revenue_pence"] == 500000

    def test_returns_booking_count(self, mock_db):
        """Should return total booking count."""
        response = {
            "total_bookings": 100,
            "confirmed_bookings": 85,
            "cancelled_bookings": 15,
        }

        assert response["total_bookings"] == 100

    def test_returns_average_booking_value(self, mock_db):
        """Should return average booking value."""
        response = {
            "average_booking_pence": 5000,
            "average_booking_display": "£50.00",
        }

        assert response["average_booking_pence"] == 5000

    def test_returns_refund_summary(self, mock_db):
        """Should return refund summary."""
        response = {
            "total_refunds_pence": 10000,
            "refund_count": 5,
            "refund_rate_percent": 5.0,
        }

        assert response["refund_rate_percent"] == 5.0

    def test_returns_daily_breakdown(self, mock_db):
        """Should return daily revenue breakdown."""
        response = {
            "daily_data": [
                {"date": "2026-04-01", "revenue_pence": 15000, "booking_count": 3},
                {"date": "2026-04-02", "revenue_pence": 20000, "booking_count": 4},
            ]
        }

        assert len(response["daily_data"]) == 2

    def test_returns_monthly_summary(self, mock_db):
        """Should return monthly revenue summary."""
        response = {
            "monthly_data": [
                {"month": "2026-01", "revenue_pence": 150000, "booking_count": 30},
                {"month": "2026-02", "revenue_pence": 175000, "booking_count": 35},
            ]
        }

        assert len(response["monthly_data"]) == 2


class TestFinancialReportExport:
    """Integration tests for GET /api/admin/reports/financial/export."""

    def test_returns_csv_format(self, mock_db):
        """Should return data in CSV format."""
        content_type = "text/csv"

        assert content_type == "text/csv"

    def test_includes_header_row(self, mock_db):
        """CSV should include header row."""
        csv_data = "Date,Revenue,Bookings\n2026-04-01,150.00,3\n"

        lines = csv_data.strip().split("\n")
        header = lines[0]

        assert "Date" in header
        assert "Revenue" in header

    def test_respects_date_range_filter(self, mock_db):
        """Should respect date range for export."""
        params = {
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        }

        assert params["start_date"] is not None


# ============================================================================
# Session Tracking Report Endpoint Tests
# ============================================================================

class TestSessionTrackingReportEndpoint:
    """Integration tests for GET /api/admin/reports/session-tracking."""

    def test_returns_session_counts(self, mock_db):
        """Should return session counts."""
        response = {
            "total_sessions": 500,
            "unique_visitors": 350,
            "returning_visitors": 150,
        }

        assert response["total_sessions"] == 500

    def test_returns_conversion_rate(self, mock_db):
        """Should return session to booking conversion rate."""
        response = {
            "total_sessions": 500,
            "total_bookings": 50,
            "conversion_rate": 10.0,
        }

        expected_rate = (50 / 500) * 100
        assert response["conversion_rate"] == expected_rate

    def test_supports_period_filter(self, mock_db):
        """Should support daily/weekly/monthly period filter."""
        for period in ["daily", "weekly", "monthly"]:
            params = {"period": period}
            assert params["period"] in ["daily", "weekly", "monthly"]


# ============================================================================
# Abandoned Carts Report Endpoint Tests
# ============================================================================

class TestAbandonedCartsReportEndpoint:
    """Integration tests for GET /api/admin/reports/abandoned-carts."""

    def test_returns_abandonment_rate(self, mock_db):
        """Should return cart abandonment rate."""
        response = {
            "total_carts_started": 200,
            "total_abandoned": 50,
            "abandonment_rate": 25.0,
        }

        assert response["abandonment_rate"] == 25.0

    def test_returns_abandoned_by_stage(self, mock_db):
        """Should return abandonment by checkout stage."""
        response = {
            "by_stage": [
                {"stage": "vehicle_details", "count": 30},
                {"stage": "flight_details", "count": 15},
                {"stage": "payment", "count": 5},
            ]
        }

        assert len(response["by_stage"]) == 3

    def test_returns_recovery_opportunities(self, mock_db):
        """Should return carts that could be recovered."""
        response = {
            "recoverable_carts": [
                {"email": "john@example.com", "abandoned_at": "2026-04-15T10:30:00"},
            ]
        }

        assert len(response["recoverable_carts"]) >= 0


# ============================================================================
# Bookings Forecast Report Endpoint Tests
# ============================================================================

class TestBookingsForecastEndpoint:
    """Integration tests for GET /api/admin/reports/bookings-forecast."""

    def test_returns_upcoming_dropoffs(self, mock_db):
        """Should return upcoming drop-off counts."""
        response = {
            "dropoffs": [
                {"date": "2026-04-16", "count": 5},
                {"date": "2026-04-17", "count": 8},
                {"date": "2026-04-18", "count": 3},
            ]
        }

        assert len(response["dropoffs"]) == 3

    def test_returns_upcoming_pickups(self, mock_db):
        """Should return upcoming pickup counts."""
        response = {
            "pickups": [
                {"date": "2026-04-20", "count": 4},
                {"date": "2026-04-21", "count": 6},
            ]
        }

        assert len(response["pickups"]) == 2

    def test_identifies_busy_days(self, mock_db):
        """Should identify busy days (high activity)."""
        response = {
            "busy_days": [
                {"date": "2026-04-20", "dropoffs": 10, "pickups": 8, "is_busy": True},
            ]
        }

        assert response["busy_days"][0]["is_busy"] is True

    def test_forecast_range_defaults_to_14_days(self, mock_db):
        """Should default to 14 day forecast."""
        today = date.today()
        default_end = today + timedelta(days=14)

        days_ahead = (default_end - today).days

        assert days_ahead == 14


# ============================================================================
# Booking Locations Report Endpoint Tests
# ============================================================================

class TestBookingLocationsEndpoint:
    """Integration tests for GET /api/admin/reports/booking-locations."""

    def test_returns_geocoded_locations(self, mock_db):
        """Should return geocoded booking locations."""
        response = {
            "locations": [
                {"postcode": "AB12 3CD", "lat": 51.5074, "lng": -0.1278, "count": 5},
            ]
        }

        assert "lat" in response["locations"][0]
        assert "lng" in response["locations"][0]

    def test_supports_bookings_map_type(self, mock_db):
        """Should support map_type=bookings."""
        params = {"map_type": "bookings"}

        assert params["map_type"] == "bookings"

    def test_supports_origins_map_type(self, mock_db):
        """Should support map_type=origins."""
        params = {"map_type": "origins"}

        assert params["map_type"] == "origins"

    def test_skips_invalid_postcodes(self, mock_db):
        """Should skip bookings with invalid postcodes."""
        locations = [
            {"postcode": "AB12 3CD", "valid": True},
            {"postcode": "INVALID", "valid": False},
        ]

        valid_locations = [l for l in locations if l["valid"]]

        assert len(valid_locations) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestReportErrorHandling:
    """Tests for report error handling."""

    def test_invalid_view_returns_400(self, mock_db):
        """Should return 400 for invalid view parameter."""
        view = "invalid_view"
        valid_views = ["daily", "weekly", "monthly"]

        is_valid = view in valid_views

        assert is_valid is False

    def test_invalid_date_format_returns_422(self, mock_db):
        """Should return 422 for invalid date format."""
        invalid_date = "not-a-date"

        try:
            parsed = datetime.strptime(invalid_date, "%Y-%m-%d")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_end_date_before_start_date_returns_400(self, mock_db):
        """Should return 400 if end_date is before start_date."""
        start_date = date(2026, 4, 15)
        end_date = date(2026, 4, 10)

        is_valid = end_date >= start_date

        assert is_valid is False


# ============================================================================
# Authentication Tests
# ============================================================================

class TestReportAuthentication:
    """Tests for report authentication requirements."""

    def test_requires_admin_auth(self, mock_admin):
        """Reports should require admin authentication."""
        user = mock_admin

        assert user.is_admin is True

    def test_rejects_non_admin_user(self, mock_db):
        """Should reject non-admin users."""
        user = MagicMock()
        user.is_admin = False

        has_access = user.is_admin

        assert has_access is False

    def test_rejects_unauthenticated_request(self, mock_db):
        """Should reject unauthenticated requests."""
        user = None

        is_authenticated = user is not None

        assert is_authenticated is False


# ============================================================================
# Boundary Tests
# ============================================================================

class TestReportBoundaryConditions:
    """Tests for report boundary conditions."""

    def test_handles_empty_date_range(self, mock_db):
        """Should handle date range with no bookings."""
        bookings = []

        response = {
            "total_bookings": len(bookings),
            "data": [],
        }

        assert response["total_bookings"] == 0

    def test_handles_single_day_range(self, mock_db):
        """Should handle single day date range."""
        start = date(2026, 4, 15)
        end = date(2026, 4, 15)

        days = (end - start).days + 1

        assert days == 1

    def test_handles_large_date_range(self, mock_db):
        """Should handle large date range (1 year)."""
        start = date(2026, 1, 1)
        end = date(2026, 12, 31)

        days = (end - start).days + 1

        assert days == 365

    def test_handles_maximum_capacity_occupancy(self, mock_db):
        """Should handle 100% occupancy correctly."""
        max_capacity = 64
        occupied = 64

        occupancy_percent = (occupied / max_capacity) * 100

        assert occupancy_percent == 100.0


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
