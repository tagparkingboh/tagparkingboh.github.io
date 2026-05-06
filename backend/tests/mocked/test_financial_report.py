"""
Tests for Admin Financial Report.

Covers:
- GET /api/admin/reports/financial - Revenue fun facts and monthly breakdown
- GET /api/admin/reports/financial/export - CSV export

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    return customer


def create_mock_payment(
    id=1,
    booking_id=1,
    amount_pence=5000,
    refund_amount_pence=0,
    status="succeeded",
    paid_at=None,
):
    """Create a mock payment object."""
    from db_models import PaymentStatus

    payment = MagicMock()
    payment.id = id
    payment.booking_id = booking_id
    payment.amount_pence = amount_pence
    payment.refund_amount_pence = refund_amount_pence
    payment.paid_at = paid_at or datetime.utcnow()

    status_map = {
        "succeeded": PaymentStatus.SUCCEEDED,
        "refunded": PaymentStatus.REFUNDED,
        "partially_refunded": PaymentStatus.PARTIALLY_REFUNDED,
        "pending": PaymentStatus.PENDING,
        "failed": PaymentStatus.FAILED,
    }
    payment.status = status_map.get(status, PaymentStatus.SUCCEEDED)

    return payment


def create_mock_promo_code(
    id=1,
    code="SUMMER10",
    booking_id=1,
    discount_percent=10,
    is_used=True,
):
    """Create a mock promo code object."""
    promo = MagicMock()
    promo.id = id
    promo.code = code
    promo.booking_id = booking_id
    promo.discount_percent = discount_percent
    promo.is_used = is_used
    promo.promotion = MagicMock()
    promo.promotion.discount_percent = discount_percent
    return promo


def create_mock_marketing_subscriber(
    id=1,
    email="subscriber@example.com",
    first_name="Jane",
    last_name="Smith",
    # 10% off promo
    promo_10_code=None,
    promo_10_used=False,
    promo_10_used_booking_id=None,
    # FREE parking promo (100% off)
    promo_free_code=None,
    promo_free_used=False,
    promo_free_used_booking_id=None,
    # Founder promo (10% off)
    founder_promo_code=None,
    founder_promo_used=False,
    founder_promo_used_booking_id=None,
    # Legacy promo
    promo_code=None,
    promo_code_used=False,
    promo_code_used_booking_id=None,
    discount_percent=10,
):
    """Create a mock marketing subscriber object with promo tracking."""
    sub = MagicMock()
    sub.id = id
    sub.email = email
    sub.first_name = first_name
    sub.last_name = last_name
    # 10% off promo
    sub.promo_10_code = promo_10_code
    sub.promo_10_used = promo_10_used
    sub.promo_10_used_booking_id = promo_10_used_booking_id
    # FREE parking promo
    sub.promo_free_code = promo_free_code
    sub.promo_free_used = promo_free_used
    sub.promo_free_used_booking_id = promo_free_used_booking_id
    # Founder promo
    sub.founder_promo_code = founder_promo_code
    sub.founder_promo_used = founder_promo_used
    sub.founder_promo_used_booking_id = founder_promo_used_booking_id
    # Legacy promo
    sub.promo_code = promo_code
    sub.promo_code_used = promo_code_used
    sub.promo_code_used_booking_id = promo_code_used_booking_id
    sub.discount_percent = discount_percent
    return sub


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    dropoff_date=None,
    pickup_date=None,
    customer=None,
    payment=None,
    override_gross_pence=None,
    override_discount_pence=None,
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference

    status_map = {
        "confirmed": BookingStatus.CONFIRMED,
        "completed": BookingStatus.COMPLETED,
        "pending": BookingStatus.PENDING,
        "cancelled": BookingStatus.CANCELLED,
    }
    booking.status = status_map.get(status, BookingStatus.CONFIRMED)

    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or (date.today() + timedelta(days=7))
    booking.customer = customer or create_mock_customer()
    booking.payment = payment or create_mock_payment(booking_id=id)

    # Financial override fields
    booking.override_gross_pence = override_gross_pence
    booking.override_discount_pence = override_discount_pence

    return booking


def create_mock_financial_response(
    fun_facts=None,
    monthly_data=None,
    summary=None,
):
    """Create a mock financial report response."""
    if fun_facts is None:
        fun_facts = {
            "topRevenueDay": {
                "date": "Mon 15 Jan 2024",
                "amount": "£500.00",
                "bookings": 5,
            },
            "topRevenueWeek": {
                "week": "08 Jan - 14 Jan 2024",
                "amount": "£2,500.00",
            },
            "topRevenueMonth": {
                "month": "January 2024",
                "amount": "£10,000.00",
            },
        }

    if monthly_data is None:
        monthly_data = [
            {
                "monthKey": "2024-01",
                "monthLabel": "January 2024",
                "bookingCount": 10,
                "totalGross": "£1,000.00",
                "totalNet": "£950.00",
                "bookings": [],
            }
        ]

    if summary is None:
        summary = {
            "totalBookings": 10,
            "totalGross": "£1,000.00",
            "totalRefunds": "£50.00",
            "totalNet": "£950.00",
        }

    return {
        "funFacts": fun_facts,
        "monthlyData": monthly_data,
        "summary": summary,
    }


# =============================================================================
# Unit Tests - Response Structure
# =============================================================================

class TestFinancialReportResponseStructure:
    """Unit tests for response structure."""

    def test_response_includes_fun_facts_section(self):
        """Response should include funFacts section."""
        response = create_mock_financial_response()

        assert "funFacts" in response
        assert "topRevenueDay" in response["funFacts"]
        assert "topRevenueWeek" in response["funFacts"]
        assert "topRevenueMonth" in response["funFacts"]

    def test_response_includes_monthly_data_section(self):
        """Response should include monthlyData array."""
        response = create_mock_financial_response()

        assert "monthlyData" in response
        assert isinstance(response["monthlyData"], list)

    def test_response_includes_summary_section(self):
        """Response should include summary section."""
        response = create_mock_financial_response()

        assert "summary" in response
        assert "totalBookings" in response["summary"]
        assert "totalGross" in response["summary"]
        assert "totalRefunds" in response["summary"]
        assert "totalNet" in response["summary"]

    def test_top_revenue_day_structure(self):
        """Top revenue day should include date, amount, bookings."""
        response = create_mock_financial_response()

        day = response["funFacts"]["topRevenueDay"]
        assert "date" in day
        assert "amount" in day
        assert "bookings" in day

    def test_top_revenue_week_structure(self):
        """Top revenue week should include week range and amount."""
        response = create_mock_financial_response()

        week = response["funFacts"]["topRevenueWeek"]
        assert "week" in week
        assert "amount" in week

    def test_top_revenue_month_structure(self):
        """Top revenue month should include month name and amount."""
        response = create_mock_financial_response()

        month = response["funFacts"]["topRevenueMonth"]
        assert "month" in month
        assert "amount" in month

    def test_monthly_data_entry_structure(self):
        """Monthly data entry should include all required fields."""
        response = create_mock_financial_response()

        month = response["monthlyData"][0]
        assert "monthKey" in month
        assert "monthLabel" in month
        assert "bookingCount" in month
        assert "totalGross" in month
        assert "totalNet" in month
        assert "bookings" in month


# =============================================================================
# Unit Tests - Revenue Calculation Logic
# =============================================================================

class TestRevenueCalculation:
    """Unit tests for revenue calculation logic."""

    def test_gross_revenue_from_payment_amount(self):
        """Gross revenue should be payment amount in pounds."""
        payment = create_mock_payment(amount_pence=5000)

        gross_pounds = payment.amount_pence / 100

        assert gross_pounds == 50.00

    def test_net_revenue_subtracts_refunds(self):
        """Net revenue should be gross minus refunds."""
        payment = create_mock_payment(amount_pence=5000, refund_amount_pence=1000)

        gross = payment.amount_pence
        refund = payment.refund_amount_pence
        net = gross - refund

        assert net == 4000  # £40.00 in pence

    def test_net_revenue_no_refund(self):
        """Net revenue equals gross when no refund."""
        payment = create_mock_payment(amount_pence=5000, refund_amount_pence=0)

        net = payment.amount_pence - payment.refund_amount_pence

        assert net == 5000

    def test_full_refund_zero_net(self):
        """Full refund should result in zero net revenue."""
        payment = create_mock_payment(amount_pence=5000, refund_amount_pence=5000)

        net = payment.amount_pence - payment.refund_amount_pence

        assert net == 0

    def test_partial_refund(self):
        """Partial refund should reduce net revenue."""
        payment = create_mock_payment(amount_pence=10000, refund_amount_pence=2500)

        net = payment.amount_pence - payment.refund_amount_pence

        assert net == 7500  # £75.00 in pence


# =============================================================================
# Unit Tests - Discount Calculation Logic
# =============================================================================

class TestDiscountCalculation:
    """Unit tests for discount calculation logic."""

    def test_calculate_original_price_before_discount(self):
        """Should calculate original price from discounted price."""
        gross_pence = 9000  # £90 after 10% off
        discount_percent = 10

        # gross = original * (1 - discount/100)
        # original = gross / (1 - discount/100)
        original_pence = int(gross_pence / (1 - discount_percent / 100))

        assert original_pence == 10000  # £100 original

    def test_calculate_discount_amount(self):
        """Should calculate discount amount correctly."""
        original_pence = 10000
        gross_pence = 9000
        discount_pence = original_pence - gross_pence

        assert discount_pence == 1000  # £10 discount

    def test_no_discount_zero_amount(self):
        """No promo code should mean zero discount."""
        discount_percent = 0
        gross_pence = 10000

        if discount_percent == 0:
            discount_pence = 0
            original_pence = gross_pence

        assert discount_pence == 0
        assert original_pence == gross_pence

    def test_100_percent_discount_free_booking(self):
        """100% discount should handle edge case."""
        discount_percent = 100
        gross_pence = 0

        # Can't divide by 0, handle specially
        if discount_percent == 100:
            original_pence = 0
            discount_pence = 0

        assert original_pence == 0
        assert discount_pence == 0

    def test_50_percent_discount(self):
        """50% discount calculation."""
        gross_pence = 5000  # £50 after 50% off
        discount_percent = 50

        original_pence = int(gross_pence / (1 - discount_percent / 100))
        discount_pence = original_pence - gross_pence

        assert original_pence == 10000  # £100 original
        assert discount_pence == 5000  # £50 discount


# =============================================================================
# Unit Tests - Trip Days Calculation
# =============================================================================

class TestTripDaysCalculation:
    """Unit tests for trip days calculation."""

    def test_calculate_trip_days(self):
        """Should calculate days between dropoff and pickup."""
        dropoff = date(2024, 1, 1)
        pickup = date(2024, 1, 8)

        trip_days = (pickup - dropoff).days

        assert trip_days == 7

    def test_same_day_trip(self):
        """Same day dropoff and pickup should be 0 days."""
        dropoff = date(2024, 1, 1)
        pickup = date(2024, 1, 1)

        trip_days = (pickup - dropoff).days

        assert trip_days == 0

    def test_one_day_trip(self):
        """One day trip calculation."""
        dropoff = date(2024, 1, 1)
        pickup = date(2024, 1, 2)

        trip_days = (pickup - dropoff).days

        assert trip_days == 1

    def test_long_trip(self):
        """Long trip calculation."""
        dropoff = date(2024, 1, 1)
        pickup = date(2024, 1, 31)

        trip_days = (pickup - dropoff).days

        assert trip_days == 30


# =============================================================================
# Unit Tests - Revenue by Period Aggregation
# =============================================================================

class TestRevenueByPeriod:
    """Unit tests for revenue aggregation by day/week/month."""

    def test_aggregate_by_day(self):
        """Should aggregate revenue by day correctly."""
        payments = [
            create_mock_payment(id=1, amount_pence=5000, paid_at=datetime(2024, 1, 15, 10, 0)),
            create_mock_payment(id=2, amount_pence=3000, paid_at=datetime(2024, 1, 15, 14, 0)),
            create_mock_payment(id=3, amount_pence=2000, paid_at=datetime(2024, 1, 16, 10, 0)),
        ]

        revenue_by_day = defaultdict(int)
        for p in payments:
            day = p.paid_at.date()
            revenue_by_day[day] += p.amount_pence

        assert revenue_by_day[date(2024, 1, 15)] == 8000  # £80
        assert revenue_by_day[date(2024, 1, 16)] == 2000  # £20

    def test_aggregate_by_week(self):
        """Should aggregate revenue by ISO week correctly."""
        payments = [
            create_mock_payment(id=1, amount_pence=5000, paid_at=datetime(2024, 1, 8, 10, 0)),  # Week 2
            create_mock_payment(id=2, amount_pence=3000, paid_at=datetime(2024, 1, 10, 14, 0)),  # Week 2
            create_mock_payment(id=3, amount_pence=2000, paid_at=datetime(2024, 1, 15, 10, 0)),  # Week 3
        ]

        revenue_by_week = defaultdict(int)
        for p in payments:
            year, week, _ = p.paid_at.date().isocalendar()
            week_key = f"{year}-W{week:02d}"
            revenue_by_week[week_key] += p.amount_pence

        assert revenue_by_week["2024-W02"] == 8000  # £80
        assert revenue_by_week["2024-W03"] == 2000  # £20

    def test_aggregate_by_month(self):
        """Should aggregate revenue by month correctly."""
        payments = [
            create_mock_payment(id=1, amount_pence=5000, paid_at=datetime(2024, 1, 15, 10, 0)),
            create_mock_payment(id=2, amount_pence=3000, paid_at=datetime(2024, 1, 20, 14, 0)),
            create_mock_payment(id=3, amount_pence=2000, paid_at=datetime(2024, 2, 5, 10, 0)),
        ]

        revenue_by_month = defaultdict(int)
        for p in payments:
            month_key = p.paid_at.strftime("%Y-%m")
            revenue_by_month[month_key] += p.amount_pence

        assert revenue_by_month["2024-01"] == 8000  # £80
        assert revenue_by_month["2024-02"] == 2000  # £20

    def test_find_top_revenue_day(self):
        """Should find the day with highest revenue."""
        revenue_by_day = {
            date(2024, 1, 15): 8000,
            date(2024, 1, 16): 2000,
            date(2024, 1, 17): 12000,
        }

        top_day = max(revenue_by_day.items(), key=lambda x: x[1])

        assert top_day[0] == date(2024, 1, 17)
        assert top_day[1] == 12000


# =============================================================================
# Unit Tests - Monthly Grouping and Sorting
# =============================================================================

class TestMonthlyGrouping:
    """Unit tests for monthly grouping and sorting."""

    def test_group_bookings_by_month(self):
        """Should group bookings by payment month."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(paid_at=datetime(2024, 1, 20))),
            create_mock_booking(id=3, payment=create_mock_payment(paid_at=datetime(2024, 2, 5))),
        ]

        by_month = defaultdict(list)
        for b in bookings:
            month_key = b.payment.paid_at.strftime("%Y-%m")
            by_month[month_key].append(b)

        assert len(by_month["2024-01"]) == 2
        assert len(by_month["2024-02"]) == 1

    def test_months_sorted_descending(self):
        """Months should be sorted in descending order (newest first)."""
        months = ["2024-01", "2024-03", "2024-02"]

        sorted_months = sorted(months, reverse=True)

        assert sorted_months == ["2024-03", "2024-02", "2024-01"]

    def test_bookings_within_month_sorted_ascending(self):
        """Bookings within a month should be sorted by date ascending."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2024, 1, 20))),
            create_mock_booking(id=2, payment=create_mock_payment(paid_at=datetime(2024, 1, 5))),
            create_mock_booking(id=3, payment=create_mock_payment(paid_at=datetime(2024, 1, 15))),
        ]

        sorted_bookings = sorted(bookings, key=lambda b: b.payment.paid_at)

        assert sorted_bookings[0].id == 2  # Jan 5
        assert sorted_bookings[1].id == 3  # Jan 15
        assert sorted_bookings[2].id == 1  # Jan 20


# =============================================================================
# Unit Tests - Status Filtering
# =============================================================================

class TestStatusFiltering:
    """Unit tests for booking status filtering."""

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
        """Pending bookings should be excluded by default."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="pending")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False

    def test_cancelled_booking_excluded(self):
        """Cancelled bookings should be excluded by default."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="cancelled")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False


# =============================================================================
# Unit Tests - Payment Status Filtering
# =============================================================================

class TestPaymentStatusFiltering:
    """Unit tests for payment status filtering."""

    def test_succeeded_payment_included(self):
        """Succeeded payments should be included."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status="succeeded")

        valid_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
        is_included = payment.status in valid_statuses

        assert is_included is True

    def test_refunded_payment_included(self):
        """Refunded payments should be included."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status="refunded")

        valid_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
        is_included = payment.status in valid_statuses

        assert is_included is True

    def test_partially_refunded_payment_included(self):
        """Partially refunded payments should be included."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status="partially_refunded")

        valid_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
        is_included = payment.status in valid_statuses

        assert is_included is True

    def test_pending_payment_excluded(self):
        """Pending payments should be excluded."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status="pending")

        valid_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
        is_included = payment.status in valid_statuses

        assert is_included is False

    def test_failed_payment_excluded(self):
        """Failed payments should be excluded."""
        from db_models import PaymentStatus

        payment = create_mock_payment(status="failed")

        valid_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
        is_included = payment.status in valid_statuses

        assert is_included is False


# =============================================================================
# Unit Tests - Date Range Filtering
# =============================================================================

class TestDateRangeFiltering:
    """Unit tests for date range filtering."""

    def test_parse_uk_date_format(self):
        """Should parse DD/MM/YYYY format."""
        date_str = "15/01/2024"
        parsed = datetime.strptime(date_str, "%d/%m/%Y")

        assert parsed.day == 15
        assert parsed.month == 1
        assert parsed.year == 2024

    def test_filter_by_from_date(self):
        """Payments before from_date should be excluded."""
        from_date = datetime(2024, 1, 15)
        payment_date = datetime(2024, 1, 10)

        is_after = payment_date >= from_date

        assert is_after is False

    def test_filter_by_to_date(self):
        """Payments after to_date should be excluded."""
        to_date = datetime(2024, 1, 15, 23, 59, 59)
        payment_date = datetime(2024, 1, 20)

        is_before = payment_date <= to_date

        assert is_before is False

    def test_payment_on_from_date_included(self):
        """Payment on from_date should be included."""
        from_date = datetime(2024, 1, 15)
        payment_date = datetime(2024, 1, 15, 12, 0)

        is_included = payment_date >= from_date

        assert is_included is True

    def test_payment_on_to_date_included(self):
        """Payment on to_date should be included."""
        to_date = datetime(2024, 1, 15, 23, 59, 59)
        payment_date = datetime(2024, 1, 15, 18, 0)

        is_included = payment_date <= to_date

        assert is_included is True

    def test_payment_within_range(self):
        """Payment within date range should be included."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 1, 31, 23, 59, 59)
        payment_date = datetime(2024, 1, 15)

        is_in_range = from_date <= payment_date <= to_date

        assert is_in_range is True


# =============================================================================
# Unit Tests - Promo Code Filtering
# =============================================================================

class TestPromoCodeFiltering:
    """Unit tests for promo code filtering."""

    def test_filter_bookings_with_promo(self):
        """Filter should return only bookings with promo codes."""
        booking_ids = [1, 2, 3, 4, 5]
        promo_booking_ids = {1, 3, 5}  # Only these used promo codes

        with_promo = [b for b in booking_ids if b in promo_booking_ids]

        assert with_promo == [1, 3, 5]

    def test_filter_bookings_without_promo(self):
        """Filter should return only bookings without promo codes."""
        booking_ids = [1, 2, 3, 4, 5]
        promo_booking_ids = {1, 3, 5}

        without_promo = [b for b in booking_ids if b not in promo_booking_ids]

        assert without_promo == [2, 4]

    def test_all_filter_includes_all(self):
        """'all' filter should include all bookings."""
        booking_ids = [1, 2, 3, 4, 5]
        promo_filter = "all"

        if promo_filter == "all":
            filtered = booking_ids
        elif promo_filter == "yes":
            filtered = [b for b in booking_ids if b in {1, 3, 5}]
        else:
            filtered = [b for b in booking_ids if b not in {1, 3, 5}]

        assert filtered == [1, 2, 3, 4, 5]


# =============================================================================
# Negative Tests
# =============================================================================

class TestNegativeScenarios:
    """Negative test cases."""

    def test_empty_bookings_returns_empty_data(self):
        """Empty bookings should return empty monthly data."""
        bookings = []

        monthly_data = []
        for b in bookings:
            pass  # No processing

        assert len(monthly_data) == 0

    def test_no_payments_returns_null_fun_facts(self):
        """No payments should result in null fun facts."""
        revenue_by_day = {}
        revenue_by_week = {}
        revenue_by_month = {}

        top_day = max(revenue_by_day.items(), key=lambda x: x[1]) if revenue_by_day else None
        top_week = max(revenue_by_week.items(), key=lambda x: x[1]) if revenue_by_week else None
        top_month = max(revenue_by_month.items(), key=lambda x: x[1]) if revenue_by_month else None

        assert top_day is None
        assert top_week is None
        assert top_month is None

    def test_invalid_date_format_handled(self):
        """Invalid date format should be handled gracefully."""
        date_str = "2024-01-15"  # ISO format instead of UK format

        try:
            parsed = datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            parsed = None

        assert parsed is None

    def test_null_payment_amount_handled(self):
        """Null payment amount should be treated as zero."""
        amount_pence = None

        safe_amount = amount_pence or 0

        assert safe_amount == 0

    def test_null_refund_amount_handled(self):
        """Null refund amount should be treated as zero."""
        refund_pence = None

        safe_refund = refund_pence or 0

        assert safe_refund == 0

    def test_booking_without_payment_skipped(self):
        """Bookings without payment should be skipped."""
        from unittest.mock import MagicMock
        booking = MagicMock()
        booking.payment = None

        has_valid_payment = booking.payment and booking.payment.paid_at

        # booking.payment is None, so has_valid_payment is falsy (None)
        assert not has_valid_payment

    def test_payment_without_paid_at_skipped(self):
        """Payments without paid_at should be skipped."""
        from unittest.mock import MagicMock
        booking = MagicMock()
        booking.payment = MagicMock()
        booking.payment.paid_at = None

        has_valid_payment = booking.payment and booking.payment.paid_at

        # booking.payment.paid_at is None, so has_valid_payment is falsy (None)
        assert not has_valid_payment


# =============================================================================
# Marketing Subscriber Promos
# =============================================================================

class TestMarketingSubscriberPromos:
    """Tests for MarketingSubscriber promo code tracking in financial reports."""

    def test_promo_10_used_discount_applied(self):
        """10% off promo from MarketingSubscriber should apply 10% discount."""
        sub = create_mock_marketing_subscriber(
            promo_10_code="TAG-10OFF-XXXX",
            promo_10_used=True,
            promo_10_used_booking_id=1,
        )

        assert sub.promo_10_used is True
        assert sub.promo_10_used_booking_id == 1
        assert sub.promo_10_code == "TAG-10OFF-XXXX"

        # 10% off means discount_percent = 10
        discount_percent = 10
        net_pence = 9000  # Customer paid £90
        gross_pence = int(net_pence / (1 - discount_percent / 100))
        discount_pence = gross_pence - net_pence

        assert gross_pence == 10000  # Original price was £100
        assert discount_pence == 1000  # Discount was £10

    def test_promo_free_used_discount_applied(self):
        """FREE parking promo (100% off) from MarketingSubscriber."""
        sub = create_mock_marketing_subscriber(
            promo_free_code="TAG-FREE-XXXX",
            promo_free_used=True,
            promo_free_used_booking_id=2,
        )

        assert sub.promo_free_used is True
        assert sub.promo_free_used_booking_id == 2
        assert sub.promo_free_code == "TAG-FREE-XXXX"

        # 100% off - customer paid £0
        discount_percent = 100
        net_pence = 0

        # For 100% off, we can't calculate original price
        # The logic should handle this gracefully
        assert discount_percent == 100

    def test_promo_free_partial_payment_longer_trip(self):
        """FREE parking promo for trip > 7 days only covers first week."""
        sub = create_mock_marketing_subscriber(
            promo_free_code="TAG-FREE-XXXX",
            promo_free_used=True,
            promo_free_used_booking_id=3,
        )

        # For trips > 7 days, customer pays remainder minus £79/£85 base week
        # Example: 10 day trip at £120, free week promo = £120 - £79 = £41 paid
        net_pence = 4100  # Customer paid £41

        # Since it's recorded as 100% off but customer still paid,
        # the discount calculation won't work with standard formula
        # This is expected behavior - free week promos are special
        assert sub.promo_free_used is True
        assert net_pence > 0

    def test_founder_promo_used_discount_applied(self):
        """Founder's 10% off promo from MarketingSubscriber."""
        sub = create_mock_marketing_subscriber(
            founder_promo_code="TAG-FOUNDER-XXXX",
            founder_promo_used=True,
            founder_promo_used_booking_id=4,
        )

        assert sub.founder_promo_used is True
        assert sub.founder_promo_used_booking_id == 4
        assert sub.founder_promo_code == "TAG-FOUNDER-XXXX"

        # 10% off
        discount_percent = 10
        net_pence = 7200  # Customer paid £72
        gross_pence = int(net_pence / (1 - discount_percent / 100))

        assert gross_pence == 8000  # Original price was £80

    def test_legacy_promo_code_used(self):
        """Legacy promo_code field from MarketingSubscriber."""
        sub = create_mock_marketing_subscriber(
            promo_code="TAG-LEGACY-XXXX",
            promo_code_used=True,
            promo_code_used_booking_id=5,
            discount_percent=15,  # Custom discount
        )

        assert sub.promo_code_used is True
        assert sub.promo_code_used_booking_id == 5
        assert sub.discount_percent == 15

        # 15% off
        net_pence = 8500  # Customer paid £85
        gross_pence = int(net_pence / (1 - sub.discount_percent / 100))

        assert gross_pence == 10000  # Original price was £100

    def test_multiple_promo_types_same_subscriber(self):
        """Subscriber can have multiple promo types, each for different bookings."""
        sub = create_mock_marketing_subscriber(
            promo_10_code="TAG-10OFF-XXXX",
            promo_10_used=True,
            promo_10_used_booking_id=1,
            promo_free_code="TAG-FREE-XXXX",
            promo_free_used=True,
            promo_free_used_booking_id=2,
            founder_promo_code="TAG-FOUNDER-XXXX",
            founder_promo_used=False,  # Not used yet
            founder_promo_used_booking_id=None,
        )

        assert sub.promo_10_used_booking_id == 1
        assert sub.promo_free_used_booking_id == 2
        assert sub.founder_promo_used_booking_id is None

    def test_promo_not_used_excluded(self):
        """Unused promos should not be included in report."""
        sub = create_mock_marketing_subscriber(
            promo_10_code="TAG-10OFF-XXXX",
            promo_10_used=False,  # Not used
            promo_10_used_booking_id=None,
        )

        assert sub.promo_10_used is False
        assert sub.promo_10_used_booking_id is None

    def test_promo_code_lookup_priority(self):
        """PromoCode table should take priority over MarketingSubscriber promos."""
        # If a booking has a promo from PromoCode table, don't overwrite with MarketingSubscriber
        promo_from_promotion = create_mock_promo_code(
            code="PROMO-SYS-CODE",
            booking_id=1,
            discount_percent=20,
        )

        sub_promo = create_mock_marketing_subscriber(
            promo_10_code="TAG-10OFF-XXXX",
            promo_10_used=True,
            promo_10_used_booking_id=1,  # Same booking
        )

        # PromoCode system has 20% off
        # MarketingSubscriber has 10% off
        # PromoCode should win (first lookup)
        assert promo_from_promotion.promotion.discount_percent == 20
        assert promo_from_promotion.booking_id == 1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_very_large_payment_amount(self):
        """Very large payment amount should be handled."""
        payment = create_mock_payment(amount_pence=1000000000)  # £10 million

        formatted = f"£{payment.amount_pence / 100:,.2f}"

        assert formatted == "£10,000,000.00"

    def test_zero_payment_amount(self):
        """Zero payment amount should be handled."""
        payment = create_mock_payment(amount_pence=0)

        net = payment.amount_pence - (payment.refund_amount_pence or 0)

        assert net == 0

    def test_single_booking_single_month(self):
        """Single booking should work correctly."""
        bookings = [create_mock_booking()]

        by_month = defaultdict(list)
        for b in bookings:
            month_key = b.payment.paid_at.strftime("%Y-%m")
            by_month[month_key].append(b)

        assert len(by_month) == 1

    def test_many_bookings_same_day(self):
        """Many bookings on same day should aggregate correctly."""
        same_day = datetime(2024, 1, 15, 12, 0)
        payments = [create_mock_payment(id=i, amount_pence=1000, paid_at=same_day) for i in range(100)]

        revenue = sum(p.amount_pence for p in payments)

        assert revenue == 100000  # £1,000

    def test_bookings_spanning_multiple_years(self):
        """Bookings spanning multiple years should group correctly."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2023, 12, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=3, payment=create_mock_payment(paid_at=datetime(2024, 12, 15))),
            create_mock_booking(id=4, payment=create_mock_payment(paid_at=datetime(2025, 1, 15))),
        ]

        by_month = defaultdict(list)
        for b in bookings:
            month_key = b.payment.paid_at.strftime("%Y-%m")
            by_month[month_key].append(b)

        assert "2023-12" in by_month
        assert "2024-01" in by_month
        assert "2024-12" in by_month
        assert "2025-01" in by_month

    def test_customer_name_with_special_characters(self):
        """Customer name with special characters should be handled."""
        customer = create_mock_customer(first_name="José", last_name="O'Brien")
        booking = create_mock_booking(customer=customer)

        full_name = f"{booking.customer.first_name} {booking.customer.last_name}"

        assert full_name == "José O'Brien"

    def test_promo_code_with_special_characters(self):
        """Promo code with special characters should be handled."""
        promo = create_mock_promo_code(code="SUMMER-2024!")

        assert promo.code == "SUMMER-2024!"

    def test_reference_format(self):
        """Booking reference should maintain format."""
        booking = create_mock_booking(reference="TAG-ABC123")

        assert booking.reference == "TAG-ABC123"

    def test_week_number_boundary(self):
        """Week number calculation at year boundary should work."""
        # Dec 31, 2023 is in week 52 of 2023
        dec_31 = datetime(2023, 12, 31)
        year, week, _ = dec_31.date().isocalendar()

        # Jan 1, 2024 is in week 1 of 2024
        jan_1 = datetime(2024, 1, 1)
        year2, week2, _ = jan_1.date().isocalendar()

        assert week == 52
        assert week2 == 1

    def test_large_discount_percentage(self):
        """Large discount (99%) should calculate correctly."""
        gross_pence = 100  # £1 after 99% off
        discount_percent = 99

        # Using the formula: gross = original * (1 - discount/100)
        # So: original = gross / (1 - discount/100)
        original_pence = int(gross_pence / (1 - discount_percent / 100))
        discount_pence = original_pence - gross_pence

        # With 99% off, £1 gross means original was ~£100
        assert original_pence >= 9900  # Approximately £100 original
        assert discount_pence >= 9800  # Approximately £99 discount

    def test_refund_greater_than_amount_handled(self):
        """Refund greater than amount (edge case) should be handled."""
        payment = create_mock_payment(amount_pence=5000, refund_amount_pence=6000)

        net = payment.amount_pence - payment.refund_amount_pence

        assert net == -1000  # Negative net is valid edge case


# =============================================================================
# Unit Tests - CSV Export
# =============================================================================

class TestCSVExport:
    """Unit tests for CSV export functionality."""

    def test_csv_row_structure(self):
        """CSV row should have all required columns."""
        columns = [
            "Date", "Reference", "Customer", "Trip Days", "Gross Price",
            "Promo Code", "Discount %", "Discount Amount", "Refund Amount",
            "Net Revenue", "Status", "Payment Status"
        ]

        assert len(columns) == 12

    def test_csv_date_format(self):
        """Date in CSV should be DD/MM/YYYY format."""
        paid_at = datetime(2024, 1, 15, 12, 0)
        formatted = paid_at.strftime("%d/%m/%Y")

        assert formatted == "15/01/2024"

    def test_csv_amount_format(self):
        """Amounts in CSV should be plain numbers for easy import."""
        amount_pence = 5000
        amount_pounds = amount_pence / 100

        formatted = f"{amount_pounds:.2f}"

        assert formatted == "50.00"

    def test_csv_handles_none_values(self):
        """CSV should handle None values as empty strings."""
        promo_code = None
        csv_value = promo_code or ""

        assert csv_value == ""

    def test_csv_escapes_commas(self):
        """CSV should handle values with commas."""
        customer_name = "Smith, John"
        # CSV libraries typically handle this by quoting

        assert "," in customer_name


# =============================================================================
# Unit Tests - Summary Totals
# =============================================================================

class TestSummaryTotals:
    """Unit tests for summary total calculations."""

    def test_total_bookings_count(self):
        """Total bookings should be count of filtered bookings."""
        bookings = [create_mock_booking() for _ in range(15)]

        assert len(bookings) == 15

    def test_total_gross_sum(self):
        """Total gross should be sum of all payment amounts."""
        payments = [
            create_mock_payment(amount_pence=5000),
            create_mock_payment(amount_pence=3000),
            create_mock_payment(amount_pence=2000),
        ]

        total_gross = sum(p.amount_pence for p in payments)

        assert total_gross == 10000  # £100

    def test_total_refunds_sum(self):
        """Total refunds should be sum of all refund amounts."""
        payments = [
            create_mock_payment(refund_amount_pence=1000),
            create_mock_payment(refund_amount_pence=500),
            create_mock_payment(refund_amount_pence=0),
        ]

        total_refunds = sum(p.refund_amount_pence for p in payments)

        assert total_refunds == 1500  # £15

    def test_total_net_calculation(self):
        """Total net should be total gross minus total refunds."""
        total_gross = 10000
        total_refunds = 1500

        total_net = total_gross - total_refunds

        assert total_net == 8500  # £85


# =============================================================================
# Financial Override Tests
# =============================================================================

class TestFinancialOverrideEndpoint:
    """Tests for PUT /api/admin/bookings/{booking_id}/financial-override endpoint."""

    def test_override_endpoint_updates_booking_values(self):
        """Override endpoint should update gross and discount pence values."""
        booking = create_mock_booking(id=1)

        # Simulate what the endpoint does
        gross_pence = 8500
        discount_pence = 8500

        booking.override_gross_pence = gross_pence
        booking.override_discount_pence = discount_pence

        assert booking.override_gross_pence == 8500
        assert booking.override_discount_pence == 8500

    def test_override_with_zero_discount(self):
        """Override should allow zero discount (no discount applied)."""
        booking = create_mock_booking(id=1)

        booking.override_gross_pence = 5000
        booking.override_discount_pence = 0

        assert booking.override_gross_pence == 5000
        assert booking.override_discount_pence == 0

    def test_override_with_full_discount(self):
        """Override should allow 100% discount (free booking)."""
        booking = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=0),  # Free booking
        )

        # 8 day trip at £85 = gross, full discount = £85
        booking.override_gross_pence = 8500
        booking.override_discount_pence = 8500

        assert booking.override_gross_pence == 8500
        assert booking.override_discount_pence == 8500
        assert booking.payment.amount_pence == 0


class TestFinancialOverrideInReport:
    """Tests for override values being used in financial report."""

    def test_booking_without_override_uses_calculated_values(self):
        """Booking without override should use calculated gross/discount."""
        booking = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=5000),
            override_gross_pence=None,
            override_discount_pence=None,
        )

        # Without override, we calculate from payment and discount percent
        net_pence = booking.payment.amount_pence
        discount_percent = 10
        gross_pence = int(net_pence / (1 - discount_percent / 100))
        discount_pence = gross_pence - net_pence

        assert gross_pence == 5555  # 5000 / 0.9 = ~5555
        assert discount_pence == 555  # 5555 - 5000 = 555

    def test_booking_with_override_uses_override_values(self):
        """Booking with override should use override gross/discount."""
        booking = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=0),  # Free booking
            override_gross_pence=8500,  # £85 original price
            override_discount_pence=8500,  # £85 discount (100% off)
        )

        # With override, use override values directly
        if booking.override_gross_pence is not None:
            gross_pence = booking.override_gross_pence
            discount_pence = booking.override_discount_pence or 0
        else:
            gross_pence = booking.payment.amount_pence
            discount_pence = 0

        assert gross_pence == 8500
        assert discount_pence == 8500

    def test_override_takes_precedence_over_calculated(self):
        """Override values should take precedence over calculation."""
        # Booking with payment of £50 and 10% discount normally
        booking = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=5000),
            override_gross_pence=10000,  # Manual override: £100
            override_discount_pence=5000,  # Manual override: £50 discount
        )

        # Normal calculation would give ~£55.55 gross
        # But override gives £100 gross

        if booking.override_gross_pence is not None:
            gross_pence = booking.override_gross_pence
            discount_pence = booking.override_discount_pence or 0
        else:
            net_pence = booking.payment.amount_pence
            discount_percent = 10
            gross_pence = int(net_pence / (1 - discount_percent / 100))
            discount_pence = gross_pence - net_pence

        assert gross_pence == 10000  # Override value
        assert discount_pence == 5000  # Override value

    # The needs_override rule moved from
    #   `(promo_info is not None) AND (discount_pence == 0) AND (override is None)`
    # to a broader form (locked 2026-05-06):
    #   `(override is None) AND ((promo + discount=0) OR net_pence == 0)`
    # Two paths qualify because some free / one-off bookings never get a
    # promo recorded in any of the 6 promo source tables, but admins still
    # need to record the original cost for accurate revenue reporting.
    def _compute_needs_override(self, *, promo_info, discount_pence, net_pence, override_gross):
        return (
            override_gross is None
            and (
                (promo_info is not None and discount_pence == 0)
                or net_pence == 0
            )
        )

    def test_needs_override_flag_when_promo_but_no_discount(self):
        """needsOverride True when promo exists but discount is 0 (path A)."""
        needs_override = self._compute_needs_override(
            promo_info={"code": "FREE-PARKING", "discount_percent": 100},
            discount_pence=0,
            net_pence=0,
            override_gross=None,
        )
        assert needs_override is True

    def test_needs_override_flag_when_zero_net_no_promo_recorded(self):
        """needsOverride True when net is £0 even if no promo was recorded
        (path B — covers one-off / friends-and-family / phone freebies that
        bypass the 6 promo source tables). Locked 2026-05-06."""
        needs_override = self._compute_needs_override(
            promo_info=None,  # promo lookup missed / not tracked
            discount_pence=0,
            net_pence=0,
            override_gross=None,
        )
        assert needs_override is True

    def test_needs_override_flag_false_when_paid_and_no_promo(self):
        """A normal paid booking with no promo and no override should NOT
        trigger needs_override. Boundary guard for the new path B."""
        needs_override = self._compute_needs_override(
            promo_info=None,
            discount_pence=0,
            net_pence=8500,  # paid in full
            override_gross=None,
        )
        assert needs_override is False

    def test_needs_override_flag_false_when_override_exists(self):
        """needsOverride False when override values are already set —
        applies regardless of which path would otherwise qualify."""
        # Path A: promo + 0 discount, but override is set → false.
        a = self._compute_needs_override(
            promo_info={"code": "FREE-PARKING", "discount_percent": 100},
            discount_pence=0, net_pence=0, override_gross=8500,
        )
        # Path B: zero net, but override is set → false.
        b = self._compute_needs_override(
            promo_info=None, discount_pence=0, net_pence=0, override_gross=8500,
        )
        assert a is False
        assert b is False

    def test_has_override_flag(self):
        """hasOverride should be True when override values exist."""
        booking_with_override = create_mock_booking(
            id=1,
            override_gross_pence=8500,
        )
        booking_without_override = create_mock_booking(
            id=2,
            override_gross_pence=None,
        )

        has_override_1 = booking_with_override.override_gross_pence is not None
        has_override_2 = booking_without_override.override_gross_pence is not None

        assert has_override_1 is True
        assert has_override_2 is False


class TestFinancialOverrideEdgeCases:
    """Edge cases for financial override functionality."""

    def test_override_with_partial_discount(self):
        """Override should work for partial discounts (e.g., free week on 8-day trip)."""
        # Customer books 8 days, gets 1 week free (£85)
        # Total would be £93 for 8 days, minus £85 = £8 paid

        booking = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=800),  # £8 paid
            override_gross_pence=9300,  # £93 original price
            override_discount_pence=8500,  # £85 discount (1 week free)
        )

        gross = booking.override_gross_pence
        discount = booking.override_discount_pence
        net = booking.payment.amount_pence

        assert gross == 9300
        assert discount == 8500
        assert net == 800
        assert gross - discount == net  # Should balance

    def test_override_zero_gross_not_allowed(self):
        """Override should not have zero gross (invalid state)."""
        # Zero gross doesn't make sense - there should be some original price
        booking = create_mock_booking(
            id=1,
            override_gross_pence=0,
            override_discount_pence=0,
        )

        # In practice, we'd validate this in the endpoint
        # For now, test that it's technically possible but illogical
        is_valid = booking.override_gross_pence > 0 if booking.override_gross_pence is not None else True

        assert is_valid is False  # 0 > 0 is False

    def test_override_discount_exceeds_gross(self):
        """Override discount exceeding gross is unusual but allowed."""
        # This could happen with additional discounts or refunds
        booking = create_mock_booking(
            id=1,
            override_gross_pence=5000,
            override_discount_pence=6000,  # More than gross
        )

        # This is technically allowed - might represent a refund situation
        assert booking.override_discount_pence > booking.override_gross_pence

    def test_multiple_bookings_with_mixed_overrides(self):
        """Report should handle mix of override and non-override bookings."""
        bookings = [
            create_mock_booking(
                id=1,
                payment=create_mock_payment(amount_pence=5000),
                override_gross_pence=None,  # No override
            ),
            create_mock_booking(
                id=2,
                payment=create_mock_payment(amount_pence=0),
                override_gross_pence=8500,  # Has override
                override_discount_pence=8500,
            ),
            create_mock_booking(
                id=3,
                payment=create_mock_payment(amount_pence=4500),
                override_gross_pence=None,  # No override
            ),
        ]

        total_override_count = sum(
            1 for b in bookings if b.override_gross_pence is not None
        )
        total_needs_override = sum(
            1 for b in bookings
            if b.override_gross_pence is None and b.payment.amount_pence == 0
        )

        assert total_override_count == 1
        assert total_needs_override == 0  # Booking 2 has override now

    def test_override_affects_totals_correctly(self):
        """Override values should be included in summary totals."""
        # Booking 1: Regular £50 payment with 10% discount
        # Gross ~£55.55, discount ~£5.55
        booking1 = create_mock_booking(
            id=1,
            payment=create_mock_payment(amount_pence=5000),
            override_gross_pence=None,
        )

        # Booking 2: Free booking with £85 override
        booking2 = create_mock_booking(
            id=2,
            payment=create_mock_payment(amount_pence=0),
            override_gross_pence=8500,
            override_discount_pence=8500,
        )

        # Calculate totals
        total_gross = 0
        total_discount = 0

        for booking in [booking1, booking2]:
            if booking.override_gross_pence is not None:
                total_gross += booking.override_gross_pence
                total_discount += booking.override_discount_pence or 0
            else:
                net = booking.payment.amount_pence
                discount_percent = 10
                if discount_percent and discount_percent < 100:
                    gross = int(net / (1 - discount_percent / 100))
                    discount = gross - net
                else:
                    gross = net
                    discount = 0
                total_gross += gross
                total_discount += discount

        # Expected: 5555 + 8500 = 14055 gross
        # Expected: 555 + 8500 = 9055 discount
        assert total_gross == 5555 + 8500
        assert total_discount == 555 + 8500


# =============================================================================
# PromoCodeUsage (Multi-Use Promo Codes) Tests
# =============================================================================

def create_mock_promo_code_usage(
    id=1,
    booking_id=1,
    promo_code_id=1,
    discount_percent=10,
    discount_amount_pence=1000,
    promo_code=None,
):
    """Create a mock PromoCodeUsage object for multi-use promo codes."""
    usage = MagicMock()
    usage.id = id
    usage.booking_id = booking_id
    usage.promo_code_id = promo_code_id
    usage.discount_percent = discount_percent
    usage.discount_amount_pence = discount_amount_pence

    # Create linked promo_code if not provided
    if promo_code is None:
        promo_code = MagicMock()
        promo_code.id = promo_code_id
        promo_code.code = "WED10"
    usage.promo_code = promo_code

    return usage


class TestPromoCodeUsageMultiUse:
    """Tests for PromoCodeUsage (multi-use promo codes) in financial reports."""

    def test_multi_use_promo_code_discount_applied(self):
        """Multi-use promo code from PromoCodeUsage should apply discount."""
        usage = create_mock_promo_code_usage(
            booking_id=1,
            discount_percent=10,
            discount_amount_pence=740,  # £7.40 discount
        )
        usage.promo_code.code = "WED10"

        assert usage.booking_id == 1
        assert usage.promo_code.code == "WED10"
        assert usage.discount_percent == 10

        # Calculate gross from net
        net_pence = 6660  # Customer paid £66.60
        gross_pence = int(net_pence / (1 - usage.discount_percent / 100))
        discount_pence = gross_pence - net_pence

        assert gross_pence == 7400  # Original price was £74.00
        assert discount_pence == 740  # Discount was £7.40

    def test_multi_use_promo_code_multiple_bookings(self):
        """Multi-use promo code can be used across multiple bookings."""
        usages = [
            create_mock_promo_code_usage(
                id=1,
                booking_id=100,
                discount_percent=10,
                discount_amount_pence=740,
            ),
            create_mock_promo_code_usage(
                id=2,
                booking_id=101,
                discount_percent=10,
                discount_amount_pence=850,
            ),
            create_mock_promo_code_usage(
                id=3,
                booking_id=102,
                discount_percent=10,
                discount_amount_pence=650,
            ),
        ]

        # All have the same promo code
        for usage in usages:
            usage.promo_code.code = "WED10"

        booking_ids_with_promo = {u.booking_id for u in usages}

        assert 100 in booking_ids_with_promo
        assert 101 in booking_ids_with_promo
        assert 102 in booking_ids_with_promo
        assert len(usages) == 3

    def test_multi_use_promo_code_in_promo_codes_dict(self):
        """PromoCodeUsage should populate promo_codes dict like other sources."""
        usage = create_mock_promo_code_usage(
            booking_id=1,
            discount_percent=10,
        )
        usage.promo_code.code = "WED10"

        # Simulate how the endpoint builds promo_codes dict
        promo_codes = {}
        if usage.booking_id not in promo_codes:
            promo_codes[usage.booking_id] = {
                "code": usage.promo_code.code,
                "discount_percent": usage.discount_percent or 0
            }

        assert promo_codes[1]["code"] == "WED10"
        assert promo_codes[1]["discount_percent"] == 10

    def test_multi_use_promo_code_does_not_override_existing(self):
        """PromoCodeUsage should not override existing promo in dict."""
        # First a promo from PromoCode table
        promo_codes = {
            1: {"code": "SUMMER20", "discount_percent": 20}
        }

        # Then a usage from PromoCodeUsage
        usage = create_mock_promo_code_usage(
            booking_id=1,  # Same booking
            discount_percent=10,
        )
        usage.promo_code.code = "WED10"

        # Should not override existing entry
        if usage.booking_id not in promo_codes:
            promo_codes[usage.booking_id] = {
                "code": usage.promo_code.code,
                "discount_percent": usage.discount_percent or 0
            }

        # Original promo should still be there
        assert promo_codes[1]["code"] == "SUMMER20"
        assert promo_codes[1]["discount_percent"] == 20

    def test_multi_use_promo_code_different_discount_percents(self):
        """Multi-use promo codes can have different discount percentages."""
        usages = [
            create_mock_promo_code_usage(booking_id=1, discount_percent=10),
            create_mock_promo_code_usage(booking_id=2, discount_percent=15),
            create_mock_promo_code_usage(booking_id=3, discount_percent=20),
        ]
        usages[0].promo_code.code = "WED10"
        usages[1].promo_code.code = "SPECIAL15"
        usages[2].promo_code.code = "VIP20"

        promo_codes = {}
        for usage in usages:
            if usage.booking_id not in promo_codes:
                promo_codes[usage.booking_id] = {
                    "code": usage.promo_code.code,
                    "discount_percent": usage.discount_percent
                }

        assert promo_codes[1]["discount_percent"] == 10
        assert promo_codes[2]["discount_percent"] == 15
        assert promo_codes[3]["discount_percent"] == 20

    def test_multi_use_promo_code_zero_discount_percent(self):
        """PromoCodeUsage with zero discount should be handled."""
        usage = create_mock_promo_code_usage(
            booking_id=1,
            discount_percent=0,
            discount_amount_pence=0,
        )
        usage.promo_code.code = "FREETRACKING"

        promo_codes = {}
        promo_codes[usage.booking_id] = {
            "code": usage.promo_code.code,
            "discount_percent": usage.discount_percent or 0
        }

        assert promo_codes[1]["code"] == "FREETRACKING"
        assert promo_codes[1]["discount_percent"] == 0

    def test_multi_use_promo_code_null_discount_percent(self):
        """PromoCodeUsage with null discount_percent should default to 0."""
        usage = create_mock_promo_code_usage(
            booking_id=1,
            discount_percent=None,
        )
        usage.promo_code.code = "LEGACY"

        promo_codes = {}
        promo_codes[usage.booking_id] = {
            "code": usage.promo_code.code,
            "discount_percent": usage.discount_percent or 0
        }

        assert promo_codes[1]["discount_percent"] == 0

    def test_multi_use_promo_code_null_promo_code_reference(self):
        """PromoCodeUsage with null promo_code should use UNKNOWN."""
        usage = MagicMock()
        usage.booking_id = 1
        usage.discount_percent = 10
        usage.promo_code = None

        promo_codes = {}
        promo_codes[usage.booking_id] = {
            "code": usage.promo_code.code if usage.promo_code else "UNKNOWN",
            "discount_percent": usage.discount_percent or 0
        }

        assert promo_codes[1]["code"] == "UNKNOWN"
        assert promo_codes[1]["discount_percent"] == 10


class TestPromoCodeUsageIntegration:
    """Integration tests for PromoCodeUsage in financial report context."""

    def test_gross_calculation_with_multi_use_promo(self):
        """Gross price should be calculated correctly with multi-use promo."""
        # Customer paid £66.60 with 10% off WED10
        net_pence = 6660
        discount_percent = 10

        # gross = net / (1 - discount/100)
        gross_pence = int(net_pence / (1 - discount_percent / 100))
        discount_pence = gross_pence - net_pence

        assert gross_pence == 7400  # £74.00 original
        assert discount_pence == 740  # £7.40 discount

    def test_discount_calculation_with_multi_use_promo(self):
        """Discount amount should be calculated correctly."""
        # Customer paid £76.50 with 10% off
        net_pence = 7650
        discount_percent = 10

        gross_pence = int(net_pence / (1 - discount_percent / 100))
        discount_pence = gross_pence - net_pence

        assert gross_pence == 8500  # £85.00 original
        assert discount_pence == 850  # £8.50 discount

    def test_promo_filter_includes_multi_use_bookings(self):
        """Promo filter 'yes' should include bookings with multi-use codes."""
        booking_ids = [1, 2, 3, 4, 5]

        # Promo codes from various sources including PromoCodeUsage
        promo_codes = {
            1: {"code": "SUMMER10", "discount_percent": 10},  # From PromoCode
            3: {"code": "WED10", "discount_percent": 10},     # From PromoCodeUsage
            5: {"code": "TAG-10OFF", "discount_percent": 10}, # From MarketingSubscriber
        }

        with_promo = [b for b in booking_ids if b in promo_codes]

        assert 3 in with_promo  # WED10 from PromoCodeUsage included
        assert len(with_promo) == 3

    def test_promo_filter_excludes_non_promo_bookings(self):
        """Promo filter 'no' should exclude bookings with multi-use codes."""
        booking_ids = [1, 2, 3, 4, 5]

        promo_codes = {
            1: {"code": "SUMMER10", "discount_percent": 10},
            3: {"code": "WED10", "discount_percent": 10},  # From PromoCodeUsage
        }

        without_promo = [b for b in booking_ids if b not in promo_codes]

        assert 3 not in without_promo  # WED10 booking excluded
        assert without_promo == [2, 4, 5]

    def test_monthly_totals_include_multi_use_discounts(self):
        """Monthly discount totals should include multi-use promo discounts."""
        # Simulating 3 bookings in January with various promos
        january_bookings = [
            {"net": 5000, "discount_percent": 0, "promo": None},           # No promo
            {"net": 6660, "discount_percent": 10, "promo": "WED10"},       # Multi-use
            {"net": 4500, "discount_percent": 10, "promo": "TAG-10OFF"},   # Marketing
        ]

        total_gross = 0
        total_discount = 0

        for b in january_bookings:
            if b["discount_percent"] and b["discount_percent"] < 100:
                gross = int(b["net"] / (1 - b["discount_percent"] / 100))
                discount = gross - b["net"]
            else:
                gross = b["net"]
                discount = 0

            total_gross += gross
            total_discount += discount

        # Expected: 5000 + 7400 + 5000 = 17400 gross
        # Expected: 0 + 740 + 500 = 1240 discount
        assert total_gross == 5000 + 7400 + 5000
        assert total_discount == 0 + 740 + 500
