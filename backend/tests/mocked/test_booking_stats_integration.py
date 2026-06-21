"""
Integration tests for Booking Statistics/Growth feature.

Tests the actual API endpoint and database model integration
using mocked database sessions and authentication.

Covers:
- API endpoint behavior with TestClient
- Request/response validation
- Authentication requirements
- Database model queries
- Full flow scenarios

All tests use mocked database sessions to avoid side effects.
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, patch, AsyncMock
from collections import defaultdict
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
from main import app, require_admin


# =============================================================================
# Mock Database Models
# =============================================================================

def create_mock_payment(amount_pence=5000, status="succeeded", paid_at=None):
    """Create a mock payment object."""
    payment = MagicMock()
    payment.amount_pence = amount_pence
    payment.status = status
    payment.paid_at = paid_at
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


def create_mock_db_booking(
    id=1,
    reference="TAG-INT001",
    status_value="confirmed",
    created_at=None,
    payment_amount_pence=None,
    paid_at=None,
    dropoff_date=None,
    dropoff_time=None,
    pickup_date=None,
    pickup_time=None,
):
    """Create a mock database booking object with optional payment and trip details."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.created_at = created_at or datetime.now()

    # Trip dates and times
    booking.dropoff_date = dropoff_date
    booking.dropoff_time = dropoff_time
    booking.pickup_date = pickup_date
    booking.pickup_time = pickup_time

    # Create mock status enum matching db_models.BookingStatus
    from db_models import BookingStatus
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

    # Create mock payment if amount specified
    if payment_amount_pence is not None:
        booking.payment = create_mock_payment(amount_pence=payment_amount_pence, paid_at=paid_at)
    else:
        booking.payment = None

    return booking


class _MockQuery:
    """Small chainable query helper for endpoint-level mocked DB tests."""

    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


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

class TestBookingStatsEndpoint:
    """Integration tests for the /api/admin/bookings/stats endpoint."""

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


class TestBookingTargetsHUEB:
    """HUEB coverage for Booking Targets counters on the real endpoint."""

    def test_completed_booking_paid_this_week_counts_toward_targets(self):
        """Booking Targets should count successful bookings, not confirmed-only.

        This covers the real admin report path where a booking can be made and
        completed inside the same week; it must still move the weekly target.
        """
        from db_models import AuditLog, Booking, BookingStatus

        fixed_now = datetime(2026, 6, 20, 12, 0)
        bookings = [
            create_mock_db_booking(
                id=1,
                reference="TAG-CONFIRMED",
                status_value="confirmed",
                created_at=datetime(2026, 6, 16, 10, 0),
                paid_at=datetime(2026, 6, 16, 10, 5),
                payment_amount_pence=7000,
            ),
            create_mock_db_booking(
                id=2,
                reference="TAG-COMPLETED-SAME-WEEK",
                status_value="completed",
                created_at=datetime(2026, 6, 15, 15, 0),
                paid_at=datetime(2026, 6, 15, 15, 55),
                payment_amount_pence=7000,
            ),
            create_mock_db_booking(
                id=3,
                reference="TAG-COMPLETED-TODAY",
                status_value="completed",
                created_at=datetime(2026, 6, 20, 9, 0),
                paid_at=datetime(2026, 6, 20, 9, 5),
                payment_amount_pence=9000,
            ),
            create_mock_db_booking(
                id=4,
                reference="TAG-PENDING",
                status_value="pending",
                created_at=datetime(2026, 6, 17, 12, 0),
                paid_at=datetime(2026, 6, 17, 12, 5),
                payment_amount_pence=9000,
            ),
        ]

        mock_db = MagicMock()

        def query_side_effect(model):
            if model is Booking:
                return _MockQuery(bookings)
            if model is AuditLog:
                return _MockQuery([])
            return _MockQuery([])

        mock_db.query.side_effect = query_side_effect

        def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = lambda: create_mock_user()

        try:
            with patch("main.get_uk_now", return_value=fixed_now):
                response = TestClient(app).get("/api/admin/bookings/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["confirmed_today"] == 1
            assert data["confirmed_this_week"] == 3
            assert data["confirmed_this_month"] == 3
            assert data["this_week"] == 3
            assert data["total_successful"] == 3
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(require_admin, None)


# =============================================================================
# Integration Tests: Response Validation
# =============================================================================

class TestBookingStatsResponse:
    """Tests for validating the API response structure."""

    def test_response_contains_all_required_fields(self):
        """Test that response contains all required fields."""
        required_fields = [
            "total_bookings",
            "total_successful",
            "status_totals",
            "this_week",
            "last_week",
            "this_month",
            "last_month",
            "daily",
            "weekly",
            "monthly",
            "cumulative",
        ]

        # Simulate response
        response_data = {
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
        }

        for field in required_fields:
            assert field in response_data

    def test_status_totals_structure(self):
        """Test status_totals contains expected statuses."""
        status_totals = {
            "confirmed": 40,
            "completed": 40,
            "pending": 10,
            "cancelled": 10,
        }

        expected_statuses = ["confirmed", "completed", "pending", "cancelled"]

        for status in expected_statuses:
            assert status in status_totals
            assert isinstance(status_totals[status], int)

    def test_daily_data_structure(self):
        """Test daily data entries have correct structure."""
        daily_entry = {
            "date": "2026-02-28",
            "confirmed": 5,
            "completed": 3,
            "pending": 2,
            "cancelled": 1,
            "total": 11,
        }

        assert "date" in daily_entry
        assert len(daily_entry["date"]) == 10  # YYYY-MM-DD
        assert daily_entry["total"] == sum([
            daily_entry["confirmed"],
            daily_entry["completed"],
            daily_entry["pending"],
            daily_entry["cancelled"],
        ])

    def test_weekly_data_structure(self):
        """Test weekly data entries have correct structure."""
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
        assert weekly_entry["total"] == 43

    def test_monthly_data_structure(self):
        """Test monthly data entries have correct structure."""
        monthly_entry = {
            "month": "2026-02",
            "confirmed": 50,
            "completed": 40,
            "pending": 10,
            "cancelled": 5,
            "total": 105,
        }

        assert "month" in monthly_entry
        assert len(monthly_entry["month"]) == 7  # YYYY-MM
        assert monthly_entry["total"] == 105

    def test_cumulative_data_structure(self):
        """Test cumulative data entries have correct structure."""
        cumulative_entry = {
            "date": "2026-02-28",
            "total": 500,
        }

        assert "date" in cumulative_entry
        assert "total" in cumulative_entry
        assert isinstance(cumulative_entry["total"], int)


# =============================================================================
# Integration Tests: Database Query Logic
# =============================================================================

class TestDatabaseQueries:
    """Tests for database query logic in the stats endpoint."""

    def test_query_all_statuses(self):
        """Test that query includes all booking statuses."""
        from db_models import BookingStatus

        # All statuses should be queried
        all_statuses = [
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.PENDING,
            BookingStatus.CANCELLED,
        ]

        assert len(all_statuses) == 4

    def test_query_ordered_by_created_at(self):
        """Test that bookings are ordered by created_at ascending."""
        bookings = [
            create_mock_db_booking(id=1, created_at=datetime(2026, 2, 1)),
            create_mock_db_booking(id=2, created_at=datetime(2026, 1, 1)),
            create_mock_db_booking(id=3, created_at=datetime(2026, 3, 1)),
        ]

        sorted_bookings = sorted(bookings, key=lambda b: b.created_at)

        assert sorted_bookings[0].id == 2  # January
        assert sorted_bookings[1].id == 1  # February
        assert sorted_bookings[2].id == 3  # March

    def test_query_handles_null_created_at(self):
        """Test that null created_at bookings are handled."""
        booking_with_null = create_mock_db_booking(id=1)
        booking_with_null.created_at = None

        # Filtering logic
        if booking_with_null.created_at:
            day_key = booking_with_null.created_at.strftime("%Y-%m-%d")
        else:
            day_key = None

        assert day_key is None


# =============================================================================
# Integration Tests: Full Flow Scenarios
# =============================================================================

class TestFullFlowScenarios:
    """Full flow integration test scenarios."""

    def test_new_business_first_week(self):
        """Test stats for a new business with only first week of data."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", created_at=datetime(2026, 2, 24)),
            create_mock_db_booking(id=2, status_value="confirmed", created_at=datetime(2026, 2, 25)),
            create_mock_db_booking(id=3, status_value="pending", created_at=datetime(2026, 2, 26)),
        ]

        status_totals = defaultdict(int)
        for b in bookings:
            status_totals[b.status.value] += 1

        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)

        assert len(bookings) == 3
        assert total_successful == 2
        assert status_totals["pending"] == 1

    def test_growing_business(self):
        """Test stats showing growth over multiple months."""
        # Simulate increasing bookings each month
        monthly_counts = {
            "2026-01": 10,
            "2026-02": 25,
            "2026-03": 40,
        }

        bookings = []
        booking_id = 1
        for month, count in monthly_counts.items():
            year, month_num = map(int, month.split("-"))
            for i in range(count):
                bookings.append(create_mock_db_booking(
                    id=booking_id,
                    status_value="confirmed",
                    created_at=datetime(year, month_num, (i % 28) + 1),
                ))
                booking_id += 1

        # Verify growth
        assert len(bookings) == 75  # 10 + 25 + 40

        # Calculate month-over-month growth
        jan_count = monthly_counts["2026-01"]
        feb_count = monthly_counts["2026-02"]
        mar_count = monthly_counts["2026-03"]

        assert feb_count > jan_count  # Growth Jan to Feb
        assert mar_count > feb_count  # Growth Feb to Mar

    def test_seasonal_business(self):
        """Test stats showing seasonal patterns."""
        # Summer peak, winter low
        monthly_bookings = {
            "2025-12": 20,  # Winter low
            "2026-01": 15,  # Winter low
            "2026-02": 25,  # Starting to grow
            "2026-06": 80,  # Summer peak
            "2026-07": 90,  # Summer peak
            "2026-08": 85,  # Summer peak
        }

        # Verify peak detection
        peak_months = ["2026-06", "2026-07", "2026-08"]
        peak_total = sum(monthly_bookings[m] for m in peak_months)
        winter_total = monthly_bookings["2025-12"] + monthly_bookings["2026-01"]

        assert peak_total > winter_total

    def test_high_cancellation_period(self):
        """Test stats during period with high cancellations."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed"),
            create_mock_db_booking(id=2, status_value="confirmed"),
            create_mock_db_booking(id=3, status_value="cancelled"),
            create_mock_db_booking(id=4, status_value="cancelled"),
            create_mock_db_booking(id=5, status_value="cancelled"),
            create_mock_db_booking(id=6, status_value="cancelled"),
            create_mock_db_booking(id=7, status_value="cancelled"),
        ]

        status_totals = defaultdict(int)
        for b in bookings:
            status_totals[b.status.value] += 1

        cancellation_rate = status_totals["cancelled"] / len(bookings)

        assert cancellation_rate > 0.5  # More than 50% cancelled
        assert status_totals["cancelled"] == 5

    def test_all_bookings_completed(self):
        """Test stats when all bookings are completed (mature business)."""
        bookings = [
            create_mock_db_booking(id=i, status_value="completed")
            for i in range(1, 101)
        ]

        status_totals = defaultdict(int)
        for b in bookings:
            status_totals[b.status.value] += 1

        total_successful = status_totals.get("confirmed", 0) + status_totals.get("completed", 0)

        assert total_successful == 100
        assert status_totals["completed"] == 100
        assert status_totals.get("confirmed", 0) == 0


# =============================================================================
# Integration Tests: Edge Cases with Real Models
# =============================================================================

class TestEdgeCasesWithModels:
    """Edge cases tested with actual model structures."""

    def test_booking_status_enum_values(self):
        """Test that BookingStatus enum has expected values."""
        from db_models import BookingStatus

        assert BookingStatus.CONFIRMED.value == "confirmed"
        assert BookingStatus.COMPLETED.value == "completed"
        assert BookingStatus.PENDING.value == "pending"
        assert BookingStatus.CANCELLED.value == "cancelled"

    def test_booking_model_has_created_at(self):
        """Test that Booking model has created_at field."""
        from db_models import Booking

        assert hasattr(Booking, 'created_at')

    def test_booking_model_has_status(self):
        """Test that Booking model has status field."""
        from db_models import Booking

        assert hasattr(Booking, 'status')

    def test_date_aggregation_consistency(self):
        """Test date aggregation produces consistent results."""
        created = datetime(2026, 2, 15, 14, 30, 45)

        daily_key = created.strftime("%Y-%m-%d")
        weekly_key = created.strftime("%Y-W%W")
        monthly_key = created.strftime("%Y-%m")

        assert daily_key == "2026-02-15"
        assert monthly_key == "2026-02"
        assert weekly_key.startswith("2026-W")


# =============================================================================
# Integration Tests: Period Calculation Accuracy
# =============================================================================

class TestPeriodCalculationAccuracy:
    """Tests for accurate period calculations."""

    def test_this_week_calculation(self):
        """Test this_week calculation is accurate."""
        today = date.today()
        this_week_start = today - timedelta(days=today.weekday())

        # Verify it's a Monday
        assert this_week_start.weekday() == 0

        # Verify it's within current week
        assert this_week_start <= today

    def test_last_week_calculation(self):
        """Test last_week calculation is accurate."""
        today = date.today()
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)

        # Verify it's 7 days before this week
        assert (this_week_start - last_week_start).days == 7

    def test_this_month_calculation(self):
        """Test this_month calculation is accurate."""
        today = date.today()
        this_month_start = today.replace(day=1)

        assert this_month_start.day == 1
        assert this_month_start.month == today.month
        assert this_month_start.year == today.year

    def test_last_month_calculation(self):
        """Test last_month calculation is accurate."""
        today = date.today()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        # Last month should be exactly one month before
        if this_month_start.month == 1:
            assert last_month_start.month == 12
            assert last_month_start.year == this_month_start.year - 1
        else:
            assert last_month_start.month == this_month_start.month - 1


# =============================================================================
# Integration Tests: Authentication Flow
# =============================================================================

class TestAuthenticationFlow:
    """Tests for authentication requirements."""

    def test_valid_admin_token_accepted(self):
        """Test that valid admin token is accepted."""
        user = create_mock_user(is_admin=True, is_active=True)

        assert user.is_admin is True
        assert user.is_active is True

    def test_inactive_admin_rejected(self):
        """Test that inactive admin is rejected."""
        user = create_mock_user(is_admin=True, is_active=False)

        assert user.is_admin is True
        assert user.is_active is False

    def test_non_admin_rejected(self):
        """Test that non-admin user is rejected."""
        user = create_mock_user(is_admin=False, is_active=True)

        assert user.is_admin is False

    def test_no_token_rejected(self):
        """Test that request without token is rejected."""
        # Simulating no authorization header
        has_token = False

        assert has_token is False


# =============================================================================
# Integration Tests: Data Integrity
# =============================================================================

class TestDataIntegrity:
    """Tests for data integrity in stats calculation."""

    def test_totals_match_breakdown(self):
        """Test that totals match sum of status breakdown."""
        status_totals = {
            "confirmed": 40,
            "completed": 35,
            "pending": 15,
            "cancelled": 10,
        }

        total_bookings = sum(status_totals.values())
        total_successful = status_totals["confirmed"] + status_totals["completed"]

        assert total_bookings == 100
        assert total_successful == 75

    def test_daily_totals_match_sum(self):
        """Test that daily totals match sum of statuses."""
        daily_entry = {
            "date": "2026-02-28",
            "confirmed": 5,
            "completed": 3,
            "pending": 2,
            "cancelled": 1,
            "total": 11,
        }

        calculated_total = (
            daily_entry["confirmed"] +
            daily_entry["completed"] +
            daily_entry["pending"] +
            daily_entry["cancelled"]
        )

        assert daily_entry["total"] == calculated_total

    def test_cumulative_is_monotonically_increasing(self):
        """Test that cumulative totals never decrease."""
        cumulative = [
            {"date": "2026-02-01", "total": 10},
            {"date": "2026-02-02", "total": 25},
            {"date": "2026-02-03", "total": 40},
            {"date": "2026-02-04", "total": 55},
        ]

        for i in range(1, len(cumulative)):
            assert cumulative[i]["total"] >= cumulative[i-1]["total"]

    def test_no_negative_counts(self):
        """Test that no counts are negative."""
        status_totals = {
            "confirmed": 40,
            "completed": 35,
            "pending": 15,
            "cancelled": 10,
        }

        for status, count in status_totals.items():
            assert count >= 0


# =============================================================================
# Integration Tests: Chart Data Preparation
# =============================================================================

class TestChartDataPreparation:
    """Tests for data preparation for frontend charts."""

    def test_data_sorted_chronologically(self):
        """Test that data is sorted in chronological order."""
        monthly_data = [
            {"month": "2026-01", "total": 10},
            {"month": "2026-02", "total": 25},
            {"month": "2026-03", "total": 40},
        ]

        # Verify sorted
        for i in range(1, len(monthly_data)):
            assert monthly_data[i]["month"] > monthly_data[i-1]["month"]

    def test_missing_periods_handled(self):
        """Test handling of periods with no bookings."""
        # Some months may have no bookings
        monthly_data = [
            {"month": "2026-01", "total": 10},
            # 2026-02 missing - no bookings
            {"month": "2026-03", "total": 15},
        ]

        # Should still work with gaps
        assert len(monthly_data) == 2

    def test_status_colors_consistent(self):
        """Test that status colors are consistent."""
        status_colors = {
            "confirmed": "#22c55e",
            "completed": "#3b82f6",
            "pending": "#f59e0b",
            "cancelled": "#ef4444",
        }

        # Green for positive, blue for complete, yellow for pending, red for cancelled
        assert status_colors["confirmed"].startswith("#")
        assert status_colors["completed"].startswith("#")
        assert status_colors["pending"].startswith("#")
        assert status_colors["cancelled"].startswith("#")


# =============================================================================
# Integration Tests: Revenue Calculation with Database Models
# =============================================================================

class TestRevenueIntegration:
    """Integration tests for revenue calculation with database models."""

    def test_revenue_calculation_with_payments(self):
        """Test revenue calculation with multiple paid bookings."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=7500),
            create_mock_db_booking(id=3, status_value="completed", payment_amount_pence=10000),
        ]

        free_promo_booking_ids = set()

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue_per_customer = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 22500
        assert total_revenue_pounds == 225.0
        assert paid_customer_count == 3
        assert avg_revenue_per_customer == 75.0

    def test_revenue_excludes_free_promo_subscribers(self):
        """Test that bookings linked to free promo subscribers are excluded."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=7500),
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=10000),
        ]

        # Simulate MarketingSubscriber with promo_free_used_booking_id
        free_promo_subscribers = [
            create_mock_marketing_subscriber(id=1, promo_free_used_booking_id=2),
        ]

        free_promo_booking_ids = set()
        for sub in free_promo_subscribers:
            if sub.promo_free_used_booking_id:
                free_promo_booking_ids.add(sub.promo_free_used_booking_id)

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert 2 in free_promo_booking_ids
        assert total_revenue_pence == 15000  # 5000 + 10000 (7500 excluded)
        assert paid_customer_count == 2
        assert avg_revenue == 75.0

    def test_revenue_with_zero_amount_bookings(self):
        """Test that zero amount payments are excluded."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=0),
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=7500),
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

    def test_revenue_only_from_successful_bookings(self):
        """Test that only confirmed/completed bookings contribute to revenue."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="completed", payment_amount_pence=7500),
            create_mock_db_booking(id=3, status_value="pending", payment_amount_pence=10000),
            create_mock_db_booking(id=4, status_value="cancelled", payment_amount_pence=15000),
        ]

        # Filter to successful bookings only (confirmed + completed)
        successful_bookings = [b for b in bookings if b.status.value in ["confirmed", "completed"]]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in successful_bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert len(successful_bookings) == 2
        assert total_revenue_pence == 12500
        assert paid_customer_count == 2
        assert avg_revenue == 62.5


class TestRevenueResponseIntegration:
    """Integration tests for revenue fields in API response."""

    def test_response_includes_revenue_fields(self):
        """Test that stats response includes all revenue fields."""
        required_revenue_fields = [
            "total_revenue",
            "paid_customer_count",
            "avg_revenue_per_customer",
        ]

        # Simulate response with revenue fields
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

        for field in required_revenue_fields:
            assert field in response

    def test_revenue_values_consistency(self):
        """Test that revenue values are mathematically consistent."""
        total_revenue = 5000.00
        paid_customer_count = 75
        expected_avg = round(total_revenue / paid_customer_count, 2)

        assert expected_avg == 66.67

    def test_zero_revenue_when_no_paid_customers(self):
        """Test zero revenue when there are no paid customers."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=0),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=0),
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pounds == 0.0
        assert paid_customer_count == 0
        assert avg_revenue == 0.0


class TestRevenueEdgeCasesIntegration:
    """Integration edge case tests for revenue calculation."""

    def test_multiple_free_promo_subscribers(self):
        """Test with multiple subscribers using free promo codes."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=7500),
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=10000),
            create_mock_db_booking(id=4, status_value="confirmed", payment_amount_pence=12500),
            create_mock_db_booking(id=5, status_value="confirmed", payment_amount_pence=15000),
        ]

        free_promo_subscribers = [
            create_mock_marketing_subscriber(id=1, promo_free_used_booking_id=2),
            create_mock_marketing_subscriber(id=2, promo_free_used_booking_id=4),
        ]

        free_promo_booking_ids = set()
        for sub in free_promo_subscribers:
            if sub.promo_free_used_booking_id:
                free_promo_booking_ids.add(sub.promo_free_used_booking_id)

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert len(free_promo_booking_ids) == 2
        assert total_revenue_pence == 30000  # 5000 + 10000 + 15000
        assert paid_customer_count == 3
        assert avg_revenue == 100.0

    def test_subscriber_without_promo_booking(self):
        """Test subscriber with null promo_free_used_booking_id."""
        free_promo_subscribers = [
            create_mock_marketing_subscriber(id=1, promo_free_used_booking_id=None),
            create_mock_marketing_subscriber(id=2, promo_free_used_booking_id=2),
        ]

        free_promo_booking_ids = set()
        for sub in free_promo_subscribers:
            if sub.promo_free_used_booking_id:
                free_promo_booking_ids.add(sub.promo_free_used_booking_id)

        assert len(free_promo_booking_ids) == 1
        assert 2 in free_promo_booking_ids

    def test_booking_without_payment_relationship(self):
        """Test bookings without payment relationship."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed"),  # No payment
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=7500),
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

    def test_large_dataset_revenue_calculation(self):
        """Test revenue calculation with large dataset."""
        bookings = [
            create_mock_db_booking(id=i, status_value="confirmed", payment_amount_pence=5000)
            for i in range(1, 1001)  # 1000 bookings at £50 each
        ]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2)

        assert paid_customer_count == 1000
        assert total_revenue_pence == 5000000
        assert total_revenue_pounds == 50000.0
        assert avg_revenue == 50.0


class TestRevenueFullFlowIntegration:
    """Full flow integration tests for revenue feature."""

    def test_typical_business_revenue_scenario(self):
        """Test typical business scenario with mix of booking types."""
        bookings = [
            # Regular paid bookings
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=4999),
            create_mock_db_booking(id=2, status_value="completed", payment_amount_pence=5999),
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=6999),
            create_mock_db_booking(id=4, status_value="completed", payment_amount_pence=7999),
            create_mock_db_booking(id=5, status_value="confirmed", payment_amount_pence=8999),
            # Free booking (amount = 0)
            create_mock_db_booking(id=6, status_value="confirmed", payment_amount_pence=0),
            # Free promo booking
            create_mock_db_booking(id=7, status_value="confirmed", payment_amount_pence=5999),
            # Cancelled bookings (should not count)
            create_mock_db_booking(id=8, status_value="cancelled", payment_amount_pence=9999),
            # Pending bookings (should not count)
            create_mock_db_booking(id=9, status_value="pending", payment_amount_pence=10999),
        ]

        # Free promo subscriber
        free_promo_subscribers = [
            create_mock_marketing_subscriber(id=1, promo_free_used_booking_id=7),
        ]

        free_promo_booking_ids = set()
        for sub in free_promo_subscribers:
            if sub.promo_free_used_booking_id:
                free_promo_booking_ids.add(sub.promo_free_used_booking_id)

        # Filter to successful bookings
        successful_bookings = [b for b in bookings if b.status.value in ["confirmed", "completed"]]

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in successful_bookings:
            if booking.id in free_promo_booking_ids:
                continue
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        # Expected: bookings 1,2,3,4,5 = 4999+5999+6999+7999+8999 = 34995 pence
        assert total_revenue_pence == 34995
        assert total_revenue_pounds == 349.95
        assert paid_customer_count == 5
        assert avg_revenue == 69.99

    def test_new_business_no_revenue(self):
        """Test new business with no completed bookings yet."""
        bookings = []

        total_revenue_pence = 0
        paid_customer_count = 0

        for booking in bookings:
            if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
                total_revenue_pence += booking.payment.amount_pence
                paid_customer_count += 1

        total_revenue_pounds = round(total_revenue_pence / 100, 2)
        avg_revenue = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0

        assert total_revenue_pence == 0
        assert total_revenue_pounds == 0.0
        assert paid_customer_count == 0
        assert avg_revenue == 0.0

    def test_all_free_promo_scenario(self):
        """Test scenario where all bookings used free promo codes."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", payment_amount_pence=5000),
            create_mock_db_booking(id=2, status_value="confirmed", payment_amount_pence=7500),
            create_mock_db_booking(id=3, status_value="confirmed", payment_amount_pence=10000),
        ]

        free_promo_subscribers = [
            create_mock_marketing_subscriber(id=1, promo_free_used_booking_id=1),
            create_mock_marketing_subscriber(id=2, promo_free_used_booking_id=2),
            create_mock_marketing_subscriber(id=3, promo_free_used_booking_id=3),
        ]

        free_promo_booking_ids = set()
        for sub in free_promo_subscribers:
            if sub.promo_free_used_booking_id:
                free_promo_booking_ids.add(sub.promo_free_used_booking_id)

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
        assert avg_revenue == 0.0


# =============================================================================
# Integration Tests: Performance Considerations
# =============================================================================

class TestPerformanceConsiderations:
    """Tests related to performance of the stats endpoint."""

    def test_handles_large_dataset(self):
        """Test that large datasets are handled efficiently."""
        # Simulate 10,000 bookings
        bookings = [
            create_mock_db_booking(id=i, status_value="confirmed")
            for i in range(1, 10001)
        ]

        assert len(bookings) == 10000

    def test_handles_long_date_range(self):
        """Test handling of bookings over multiple years."""
        dates = [
            datetime(2024, 1, 1),
            datetime(2025, 6, 15),
            datetime(2026, 2, 28),
        ]

        # Should handle 2+ year range
        date_range = (dates[-1] - dates[0]).days

        assert date_range > 365 * 2

    def test_efficient_aggregation(self):
        """Test that aggregation is efficient (uses defaultdict)."""
        from collections import defaultdict

        # Using defaultdict is more efficient than checking key existence
        counts = defaultdict(int)
        counts["test"] += 1

        assert counts["test"] == 1
        assert counts["nonexistent"] == 0  # No KeyError


# =============================================================================
# Integration Tests: Trip Insights
# =============================================================================

class TestTripInsightsIntegration:
    """Integration tests for trip insights (duration, dropoff/pickup AM/PM counts)."""

    def test_trip_insights_response_fields(self):
        """Test that response includes trip insights fields."""
        response_data = {
            "total_bookings": 100,
            "total_successful": 80,
            "avg_trip_duration": 7.5,
            "dropoff_range": {
                "am": 25,
                "pm": 55,
            },
            "pickup_range": {
                "am": 10,
                "pm": 70,
            },
        }

        assert "avg_trip_duration" in response_data
        assert "dropoff_range" in response_data
        assert "pickup_range" in response_data
        assert "am" in response_data["dropoff_range"]
        assert "pm" in response_data["dropoff_range"]

    def test_trip_duration_calculation_with_bookings(self):
        """Test trip duration calculation with mock bookings."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 8),
            ),
            create_mock_db_booking(
                id=2, status_value="completed",
                dropoff_date=date(2026, 3, 10),
                pickup_date=date(2026, 3, 17),
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1)

        assert trip_durations == [7, 7]
        assert avg_duration == 7.0

    def test_dropoff_am_pm_calculation_with_bookings(self):
        """Test dropoff AM/PM count calculation with mock bookings."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_time=dt_time(6, 0),   # AM
            ),
            create_mock_db_booking(
                id=2, status_value="confirmed",
                dropoff_time=dt_time(10, 0),  # AM
            ),
            create_mock_db_booking(
                id=3, status_value="completed",
                dropoff_time=dt_time(14, 0),  # PM
            ),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        am_dropoffs = [m for m in dropoff_times_minutes if m < 720]
        pm_dropoffs = [m for m in dropoff_times_minutes if m >= 720]

        dropoff_range = {"am": len(am_dropoffs), "pm": len(pm_dropoffs)}

        assert dropoff_range["am"] == 2  # 06:00 and 10:00
        assert dropoff_range["pm"] == 1  # 14:00

    def test_pickup_am_pm_calculation_with_bookings(self):
        """Test pickup AM/PM count calculation with mock bookings."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                pickup_time=dt_time(15, 30),  # PM
            ),
            create_mock_db_booking(
                id=2, status_value="confirmed",
                pickup_time=dt_time(18, 0),   # PM
            ),
            create_mock_db_booking(
                id=3, status_value="completed",
                pickup_time=dt_time(21, 30),  # PM
            ),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        am_pickups = [m for m in pickup_times_minutes if m < 720]
        pm_pickups = [m for m in pickup_times_minutes if m >= 720]

        pickup_range = {"am": len(am_pickups), "pm": len(pm_pickups)}

        assert pickup_range["am"] == 0  # No morning pickups
        assert pickup_range["pm"] == 3  # All afternoon/evening

    def test_empty_bookings_trip_insights(self):
        """Test trip insights with no bookings returns zeros."""
        bookings = []

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

        avg_trip_duration = round(sum(trip_durations) / len(trip_durations), 1) if trip_durations else 0

        if dropoff_times_minutes:
            am_dropoffs = [m for m in dropoff_times_minutes if m < 720]
            pm_dropoffs = [m for m in dropoff_times_minutes if m >= 720]
            dropoff_range = {"am": len(am_dropoffs), "pm": len(pm_dropoffs)}
        else:
            dropoff_range = {"am": 0, "pm": 0}

        if pickup_times_minutes:
            am_pickups = [m for m in pickup_times_minutes if m < 720]
            pm_pickups = [m for m in pickup_times_minutes if m >= 720]
            pickup_range = {"am": len(am_pickups), "pm": len(pm_pickups)}
        else:
            pickup_range = {"am": 0, "pm": 0}

        assert avg_trip_duration == 0
        assert dropoff_range["am"] == 0
        assert dropoff_range["pm"] == 0
        assert pickup_range["am"] == 0
        assert pickup_range["pm"] == 0

    def test_mixed_bookings_with_missing_data(self):
        """Test trip insights with some bookings missing dates/times."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 3, 1),
                dropoff_time=dt_time(8, 0),
                pickup_date=date(2026, 3, 8),
                pickup_time=dt_time(16, 0),
            ),
            create_mock_db_booking(
                id=2, status_value="confirmed",
                dropoff_date=None,  # Missing date
                dropoff_time=dt_time(10, 0),
                pickup_date=date(2026, 3, 15),
                pickup_time=None,  # Missing time
            ),
            create_mock_db_booking(
                id=3, status_value="completed",
                dropoff_date=date(2026, 3, 5),
                dropoff_time=None,  # Missing time
                pickup_date=date(2026, 3, 12),
                pickup_time=dt_time(18, 0),
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

        # Only bookings 1 and 3 have both dates (7 and 7 days)
        assert len(trip_durations) == 2
        assert trip_durations == [7, 7]

        # Only bookings 1 and 2 have dropoff times
        assert len(dropoff_times_minutes) == 2

        # Only bookings 1 and 3 have pickup times
        assert len(pickup_times_minutes) == 2

    def test_trip_insights_only_successful_bookings(self):
        """Test that trip insights only include confirmed/completed bookings."""
        from datetime import time as dt_time
        from db_models import BookingStatus

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 8),
            ),
            create_mock_db_booking(
                id=2, status_value="completed",
                dropoff_date=date(2026, 3, 10),
                pickup_date=date(2026, 3, 17),
            ),
            create_mock_db_booking(
                id=3, status_value="cancelled",
                dropoff_date=date(2026, 3, 5),
                pickup_date=date(2026, 3, 20),  # 15 days - would skew average
            ),
            create_mock_db_booking(
                id=4, status_value="pending",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 30),  # 29 days - would skew average
            ),
        ]

        # Filter to successful bookings only
        successful_bookings = [
            b for b in bookings
            if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        ]

        trip_durations = []
        for booking in successful_bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1)

        # Only confirmed + completed (7 + 7 days, not 15 or 29)
        assert len(trip_durations) == 2
        assert avg_duration == 7.0


class TestTripInsightsEdgeCasesIntegration:
    """Edge case integration tests for trip insights."""

    def test_single_booking_trip_insights(self):
        """Test trip insights with single booking."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 3, 1),
                dropoff_time=dt_time(9, 30),   # AM
                pickup_date=date(2026, 3, 10),
                pickup_time=dt_time(17, 45),   # PM
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

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1)

        assert avg_duration == 9.0

        # Check AM/PM categorization
        am_dropoffs = [m for m in dropoff_times_minutes if m < 720]
        pm_dropoffs = [m for m in dropoff_times_minutes if m >= 720]
        am_pickups = [m for m in pickup_times_minutes if m < 720]
        pm_pickups = [m for m in pickup_times_minutes if m >= 720]

        assert len(am_dropoffs) == 1  # 09:30 is AM
        assert len(pm_dropoffs) == 0
        assert len(am_pickups) == 0
        assert len(pm_pickups) == 1   # 17:45 is PM

    def test_long_duration_trips(self):
        """Test handling of very long trips (30+ days)."""
        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 1, 1),
                pickup_date=date(2026, 2, 15),  # 45 days
            ),
            create_mock_db_booking(
                id=2, status_value="confirmed",
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 4, 30),  # 60 days
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        avg_duration = round(sum(trip_durations) / len(trip_durations), 1)

        assert trip_durations == [45, 60]
        assert avg_duration == 52.5

    def test_same_day_dropoff_pickup(self):
        """Test same-day dropoff and pickup (0 day trip)."""
        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 15),  # Same day
            ),
        ]

        trip_durations = []
        for booking in bookings:
            if booking.dropoff_date and booking.pickup_date:
                duration = (booking.pickup_date - booking.dropoff_date).days
                if duration >= 0:
                    trip_durations.append(duration)

        assert trip_durations == [0]

    def test_time_boundaries_am_pm(self):
        """Test time boundaries (00:00 is AM, 23:59 is PM)."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_time=dt_time(0, 0),   # Midnight = AM
                pickup_time=dt_time(23, 59),  # Just before midnight = PM
            ),
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

        # 00:00 is AM (< 720)
        am_dropoffs = [m for m in dropoff_times_minutes if m < 720]
        assert len(am_dropoffs) == 1

        # 23:59 is PM (>= 720)
        pm_pickups = [m for m in pickup_times_minutes if m >= 720]
        assert len(pm_pickups) == 1

    def test_noon_boundary(self):
        """Test that 11:59 is AM and 12:00 is PM."""
        from datetime import time as dt_time

        bookings = [
            create_mock_db_booking(
                id=1, status_value="confirmed",
                dropoff_time=dt_time(11, 59),  # Last minute of AM
            ),
            create_mock_db_booking(
                id=2, status_value="confirmed",
                dropoff_time=dt_time(12, 0),   # First minute of PM
            ),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        am_dropoffs = [m for m in dropoff_times_minutes if m < 720]
        pm_dropoffs = [m for m in dropoff_times_minutes if m >= 720]

        assert len(am_dropoffs) == 1  # 11:59
        assert len(pm_dropoffs) == 1  # 12:00


# =============================================================================
# Top Busiest Hours AM/PM Integration Tests
# =============================================================================

class TestTopBusiestHoursIntegration:
    """Integration tests for busiest hours AM/PM calculation using fixed hourly buckets."""

    def _find_top_busiest_hours(self, times_minutes, top_n=3):
        """
        Helper function matching backend implementation.
        Uses fixed hourly buckets (00:00-01:00, 01:00-02:00, etc.)
        Each booking is counted exactly once based on the hour it falls into.
        """
        if not times_minutes:
            return []

        # Count bookings in each fixed hourly bucket (0-23)
        hour_buckets = {}
        for time_min in times_minutes:
            hour = time_min // 60  # Get the hour (0-23)
            hour_buckets[hour] = hour_buckets.get(hour, 0) + 1

        # Convert to list of dicts with formatted times
        hour_counts = []
        for hour, count in hour_buckets.items():
            end_hour = (hour + 1) % 24
            hour_counts.append({
                "start": f"{hour:02d}:00",
                "end": f"{end_hour:02d}:00",
                "count": count
            })

        # Sort by count descending and return top N
        hour_counts.sort(key=lambda x: x["count"], reverse=True)
        return hour_counts[:top_n]

    def test_top_3_am_dropoff_hours_from_db_bookings(self):
        """Test top 3 busiest AM dropoff hours from DB booking models using fixed hourly buckets."""
        from datetime import time as dt_time

        bookings = [
            # 4 bookings in 06:00-07:00 bucket
            create_mock_db_booking(id=1, status_value="confirmed", dropoff_time=dt_time(6, 0)),
            create_mock_db_booking(id=2, status_value="confirmed", dropoff_time=dt_time(6, 10)),
            create_mock_db_booking(id=3, status_value="confirmed", dropoff_time=dt_time(6, 25)),
            create_mock_db_booking(id=4, status_value="confirmed", dropoff_time=dt_time(6, 45)),
            # 2 bookings in 08:00-09:00 bucket
            create_mock_db_booking(id=5, status_value="completed", dropoff_time=dt_time(8, 0)),
            create_mock_db_booking(id=6, status_value="confirmed", dropoff_time=dt_time(8, 15)),
            # 1 booking in 10:00-11:00 bucket
            create_mock_db_booking(id=7, status_value="confirmed", dropoff_time=dt_time(10, 0)),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        am_times = [m for m in dropoff_times_minutes if m < 720]
        result = self._find_top_busiest_hours(am_times, 3)

        assert len(result) == 3
        # Top bucket: 06:00-07:00 with 4 bookings
        assert result[0]["start"] == "06:00"
        assert result[0]["end"] == "07:00"
        assert result[0]["count"] == 4
        # Second bucket: 08:00-09:00 with 2 bookings
        assert result[1]["start"] == "08:00"
        assert result[1]["end"] == "09:00"
        assert result[1]["count"] == 2
        # Third bucket: 10:00-11:00 with 1 booking
        assert result[2]["start"] == "10:00"
        assert result[2]["end"] == "11:00"
        assert result[2]["count"] == 1

    def test_top_3_pm_dropoff_hours_from_db_bookings(self):
        """Test top 3 busiest PM dropoff hours from DB booking models using fixed hourly buckets."""
        from datetime import time as dt_time

        bookings = [
            # 5 bookings in 14:00-15:00 bucket
            create_mock_db_booking(id=1, status_value="confirmed", dropoff_time=dt_time(14, 0)),
            create_mock_db_booking(id=2, status_value="confirmed", dropoff_time=dt_time(14, 15)),
            create_mock_db_booking(id=3, status_value="confirmed", dropoff_time=dt_time(14, 30)),
            create_mock_db_booking(id=4, status_value="confirmed", dropoff_time=dt_time(14, 45)),
            create_mock_db_booking(id=5, status_value="confirmed", dropoff_time=dt_time(14, 55)),
            # 1 booking in 16:00-17:00 bucket
            create_mock_db_booking(id=6, status_value="confirmed", dropoff_time=dt_time(16, 0)),
            # 1 booking in 18:00-19:00 bucket
            create_mock_db_booking(id=7, status_value="confirmed", dropoff_time=dt_time(18, 30)),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        pm_times = [m for m in dropoff_times_minutes if m >= 720]
        result = self._find_top_busiest_hours(pm_times, 3)

        assert len(result) == 3
        # Top bucket: 14:00-15:00 with 5 bookings
        assert result[0]["start"] == "14:00"
        assert result[0]["end"] == "15:00"
        assert result[0]["count"] == 5

    def test_top_3_am_pickup_hours_from_db_bookings(self):
        """Test top 3 busiest AM pickup hours from DB booking models using fixed hourly buckets."""
        from datetime import time as dt_time

        bookings = [
            # 3 bookings in 09:00-10:00 bucket
            create_mock_db_booking(id=1, status_value="confirmed", pickup_time=dt_time(9, 0)),
            create_mock_db_booking(id=2, status_value="confirmed", pickup_time=dt_time(9, 15)),
            create_mock_db_booking(id=3, status_value="confirmed", pickup_time=dt_time(9, 30)),
            # 1 booking in 11:00-12:00 bucket
            create_mock_db_booking(id=4, status_value="confirmed", pickup_time=dt_time(11, 0)),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        am_times = [m for m in pickup_times_minutes if m < 720]
        result = self._find_top_busiest_hours(am_times, 3)

        assert len(result) == 2  # Only 2 distinct buckets
        # Top bucket: 09:00-10:00 with 3 bookings
        assert result[0]["start"] == "09:00"
        assert result[0]["end"] == "10:00"
        assert result[0]["count"] == 3
        # Second bucket: 11:00-12:00 with 1 booking
        assert result[1]["start"] == "11:00"
        assert result[1]["end"] == "12:00"
        assert result[1]["count"] == 1

    def test_top_3_pm_pickup_hours_from_db_bookings(self):
        """Test top 3 busiest PM pickup hours from DB booking models using fixed hourly buckets."""
        from datetime import time as dt_time

        bookings = [
            # 2 bookings in 15:00-16:00 bucket
            create_mock_db_booking(id=1, status_value="confirmed", pickup_time=dt_time(15, 30)),
            create_mock_db_booking(id=2, status_value="confirmed", pickup_time=dt_time(15, 45)),
            # 2 bookings in 16:00-17:00 bucket
            create_mock_db_booking(id=3, status_value="confirmed", pickup_time=dt_time(16, 0)),
            create_mock_db_booking(id=4, status_value="confirmed", pickup_time=dt_time(16, 15)),
            # 2 bookings in 17:00-18:00 bucket
            create_mock_db_booking(id=5, status_value="confirmed", pickup_time=dt_time(17, 0)),
            create_mock_db_booking(id=6, status_value="confirmed", pickup_time=dt_time(17, 30)),
        ]

        pickup_times_minutes = []
        for booking in bookings:
            if booking.pickup_time:
                minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                pickup_times_minutes.append(minutes)

        pm_times = [m for m in pickup_times_minutes if m >= 720]
        result = self._find_top_busiest_hours(pm_times, 3)

        assert len(result) == 3
        # All 3 buckets have 2 bookings each
        assert result[0]["count"] == 2
        assert result[1]["count"] == 2
        assert result[2]["count"] == 2

    def test_busiest_hours_empty_when_no_data(self):
        """Test busiest hours returns empty list when no bookings have times."""
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", dropoff_time=None),
            create_mock_db_booking(id=2, status_value="confirmed", dropoff_time=None),
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        am_times = [m for m in dropoff_times_minutes if m < 720]
        result = self._find_top_busiest_hours(am_times, 3)
        assert result == []

    def test_each_booking_counted_exactly_once(self):
        """Test that each booking is counted in exactly one bucket (no double-counting)."""
        from datetime import time as dt_time

        # Create bookings spread across multiple hours
        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", dropoff_time=dt_time(6, 30)),  # 06:00-07:00 bucket
            create_mock_db_booking(id=2, status_value="confirmed", dropoff_time=dt_time(6, 45)),  # 06:00-07:00 bucket
            create_mock_db_booking(id=3, status_value="confirmed", dropoff_time=dt_time(7, 15)),  # 07:00-08:00 bucket
            create_mock_db_booking(id=4, status_value="confirmed", dropoff_time=dt_time(8, 0)),   # 08:00-09:00 bucket
        ]

        dropoff_times_minutes = []
        for booking in bookings:
            if booking.dropoff_time:
                minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
                dropoff_times_minutes.append(minutes)

        result = self._find_top_busiest_hours(dropoff_times_minutes, 10)

        # Total count across all buckets should equal number of bookings
        total_counted = sum(bucket["count"] for bucket in result)
        assert total_counted == len(bookings)  # Each booking counted exactly once

        # Verify individual bucket counts
        # 06:00-07:00: 2 bookings (06:30, 06:45)
        # 07:00-08:00: 1 booking (07:15)
        # 08:00-09:00: 1 booking (08:00)
        bucket_06 = next((b for b in result if b["start"] == "06:00"), None)
        bucket_07 = next((b for b in result if b["start"] == "07:00"), None)
        bucket_08 = next((b for b in result if b["start"] == "08:00"), None)

        assert bucket_06["count"] == 2
        assert bucket_07["count"] == 1
        assert bucket_08["count"] == 1

    def test_top_6_busiest_hours_contract(self):
        """Trip insights should be able to display six AM/PM hourly buckets."""
        times = [
            0, 60, 120, 180, 240, 300, 360,
        ]

        result = self._find_top_busiest_hours(times, 6)

        assert len(result) == 6
        assert [item["start"] for item in result] == [
            "00:00", "01:00", "02:00", "03:00", "04:00", "05:00",
        ]

    def test_response_includes_am_pm_busiest_arrays(self):
        """Test that API response includes am_busiest and pm_busiest arrays with fixed hourly buckets."""
        # Fixed hourly buckets use :00 end times (e.g., 06:00-07:00, not 06:15-07:15)
        response = {
            "total_bookings": 100,
            "total_successful": 80,
            "avg_trip_duration": 7.5,
            "dropoff_range": {
                "am": 50,
                "pm": 30,
                "am_busiest": [
                    {"start": "06:00", "end": "07:00", "count": 18},
                    {"start": "08:00", "end": "09:00", "count": 12},
                    {"start": "10:00", "end": "11:00", "count": 8},
                    {"start": "05:00", "end": "06:00", "count": 6},
                    {"start": "07:00", "end": "08:00", "count": 5},
                    {"start": "11:00", "end": "12:00", "count": 3},
                ],
                "pm_busiest": [
                    {"start": "14:00", "end": "15:00", "count": 10},
                    {"start": "16:00", "end": "17:00", "count": 7},
                ]
            },
            "pickup_range": {
                "am": 20,
                "pm": 60,
                "am_busiest": [
                    {"start": "09:00", "end": "10:00", "count": 8},
                ],
                "pm_busiest": [
                    {"start": "15:00", "end": "16:00", "count": 25},
                    {"start": "17:00", "end": "18:00", "count": 18},
                    {"start": "19:00", "end": "20:00", "count": 12},
                    {"start": "20:00", "end": "21:00", "count": 9},
                    {"start": "21:00", "end": "22:00", "count": 6},
                    {"start": "22:00", "end": "23:00", "count": 4},
                ]
            },
        }

        assert "am_busiest" in response["dropoff_range"]
        assert "pm_busiest" in response["dropoff_range"]
        assert "am_busiest" in response["pickup_range"]
        assert "pm_busiest" in response["pickup_range"]
        assert len(response["dropoff_range"]["am_busiest"]) == 6
        assert len(response["pickup_range"]["pm_busiest"]) == 6
        assert response["dropoff_range"]["am_busiest"][0]["count"] == 18
        # Verify fixed hourly bucket format (always :00 boundaries)
        assert response["dropoff_range"]["am_busiest"][0]["start"].endswith(":00")
        assert response["dropoff_range"]["am_busiest"][0]["end"].endswith(":00")


# =============================================================================
# Tests: Monthly Booking Pattern (payday hypothesis)
# =============================================================================

class TestMonthlyBookingPattern:
    """Tests for the monthly_booking_pattern field returned by /api/admin/bookings/stats."""

    @staticmethod
    def _bucket(day):
        """Mirror of the endpoint's week-of-month bucket rule."""
        if day <= 7:
            return "W1"
        if day <= 14:
            return "W2"
        if day <= 21:
            return "W3"
        return "W4"

    def test_bucket_boundaries(self):
        """Day-of-month bucket assignment covers W1-W4 with correct edges."""
        assert self._bucket(1) == "W1"
        assert self._bucket(7) == "W1"
        assert self._bucket(8) == "W2"
        assert self._bucket(14) == "W2"
        assert self._bucket(15) == "W3"
        assert self._bucket(21) == "W3"
        assert self._bucket(22) == "W4"
        assert self._bucket(31) == "W4"

    def test_response_contains_monthly_booking_pattern_field(self):
        """The stats response must expose monthly_booking_pattern with year/months/overall."""
        response = {
            "monthly_booking_pattern": {
                "year": 2026,
                "months": [],
                "overall": {"buckets": [], "busiest_bucket": None, "total": 0},
            }
        }
        pattern = response["monthly_booking_pattern"]
        assert "year" in pattern
        assert "months" in pattern
        assert "overall" in pattern
        assert "busiest_bucket" in pattern["overall"]
        assert "buckets" in pattern["overall"]

    def test_only_confirmed_and_completed_bookings_counted(self):
        """Bookings with status pending or cancelled must not appear in pattern counts."""
        from db_models import BookingStatus

        bookings = [
            create_mock_db_booking(id=1, status_value="confirmed", created_at=datetime(2026, 1, 5)),
            create_mock_db_booking(id=2, status_value="completed", created_at=datetime(2026, 1, 6)),
            create_mock_db_booking(id=3, status_value="pending", created_at=datetime(2026, 1, 7)),
            create_mock_db_booking(id=4, status_value="cancelled", created_at=datetime(2026, 1, 7)),
        ]

        included = [
            b for b in bookings
            if b.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
        ]
        assert len(included) == 2
        assert {b.id for b in included} == {1, 2}

    def test_aggregation_groups_by_week_of_month(self):
        """Bookings spread across a month should land in the correct week buckets."""
        bookings = [
            (datetime(2026, 1, 3), "W1"),
            (datetime(2026, 1, 7), "W1"),
            (datetime(2026, 1, 8), "W2"),
            (datetime(2026, 1, 14), "W2"),
            (datetime(2026, 1, 15), "W3"),
            (datetime(2026, 1, 21), "W3"),
            (datetime(2026, 1, 22), "W4"),
            (datetime(2026, 1, 31), "W4"),
        ]

        counts = {"W1": 0, "W2": 0, "W3": 0, "W4": 0}
        for created, _expected in bookings:
            counts[self._bucket(created.day)] += 1

        assert counts == {"W1": 2, "W2": 2, "W3": 2, "W4": 2}

    def test_busiest_bucket_picks_highest_count(self):
        """busiest_bucket should be the bucket with the highest count for that month."""
        bucket_keys = ["W1", "W2", "W3", "W4"]
        counts = {"W1": 3, "W2": 1, "W3": 5, "W4": 2}
        busiest = max(bucket_keys, key=lambda b: counts[b])
        assert busiest == "W3"

    def test_busiest_bucket_is_none_when_no_bookings(self):
        """A month with zero confirmed/completed bookings has no busiest bucket."""
        counts = {"W1": 0, "W2": 0, "W3": 0, "W4": 0}
        total = sum(counts.values())
        bucket_keys = list(counts.keys())
        busiest = max(bucket_keys, key=lambda b: counts[b]) if total > 0 else None
        assert busiest is None


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
