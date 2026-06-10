"""
Integration tests for Admin Financial Report.

These tests verify the full workflow from bookings data to API response.
All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
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


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    dropoff_date=None,
    pickup_date=None,
    customer=None,
    payment=None,
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
        "refunded": BookingStatus.REFUNDED,
    }
    booking.status = status_map.get(status, BookingStatus.CONFIRMED)

    booking.dropoff_date = dropoff_date or date.today()
    booking.pickup_date = pickup_date or (date.today() + timedelta(days=7))
    booking.customer = customer or create_mock_customer(id=id)
    booking.payment = payment or create_mock_payment(booking_id=id)

    return booking


def simulate_financial_report_endpoint(
    bookings,
    promo_codes=None,
    from_date=None,
    to_date=None,
    status_filter="all",
    promo_filter="all",
):
    """Simulate the financial report endpoint logic."""
    from db_models import BookingStatus, PaymentStatus
    from main import to_uk_datetime

    if promo_codes is None:
        promo_codes = {}

    # Filter by payment status
    valid_payment_statuses = [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
    bookings = [b for b in bookings if b.payment and b.payment.status in valid_payment_statuses]

    # Status filter
    if status_filter == "confirmed":
        bookings = [b for b in bookings if b.status == BookingStatus.CONFIRMED]
    elif status_filter == "completed":
        bookings = [b for b in bookings if b.status == BookingStatus.COMPLETED]
    elif status_filter == "refunded":
        bookings = [b for b in bookings if b.payment.status in [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]]
    else:
        # All - include confirmed, completed, cancelled, refunded.
        # Mirrors the real endpoint: refunded bookings have negative revenue
        # impact and belong in the default view.
        bookings = [b for b in bookings if b.status in [
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.REFUNDED,
        ]]

    # Date filters
    if from_date:
        bookings = [b for b in bookings if b.payment.paid_at >= from_date]
    if to_date:
        bookings = [b for b in bookings if b.payment.paid_at <= to_date]

    # Promo filter
    if promo_filter == "yes":
        bookings = [b for b in bookings if b.id in promo_codes]
    elif promo_filter == "no":
        bookings = [b for b in bookings if b.id not in promo_codes]

    # Calculate revenue by period
    revenue_by_day = defaultdict(int)
    revenue_by_week = defaultdict(int)
    revenue_by_month = defaultdict(int)

    for booking in bookings:
        if not booking.payment or not booking.payment.paid_at:
            continue
        paid_date = to_uk_datetime(booking.payment.paid_at).date()
        amount = booking.payment.amount_pence or 0
        refund = booking.payment.refund_amount_pence or 0
        net = amount - refund

        revenue_by_day[paid_date] += net
        year, week, _ = paid_date.isocalendar()
        week_key = f"{year}-W{week:02d}"
        revenue_by_week[week_key] += net
        month_key = paid_date.strftime("%Y-%m")
        revenue_by_month[month_key] += net

    # Build fun facts
    fun_facts = {
        "topRevenueDay": None,
        "topRevenueWeek": None,
        "topRevenueMonth": None,
    }

    if revenue_by_day:
        top_day = max(revenue_by_day.items(), key=lambda x: x[1])
        bookings_on_day = sum(
            1
            for b in bookings
            if b.payment and b.payment.paid_at and to_uk_datetime(b.payment.paid_at).date() == top_day[0]
        )
        fun_facts["topRevenueDay"] = {
            "date": top_day[0].strftime("%a %d %b %Y"),
            "amount": f"£{top_day[1] / 100:.2f}",
            "bookings": bookings_on_day,
        }

    if revenue_by_week:
        top_week = max(revenue_by_week.items(), key=lambda x: x[1])
        fun_facts["topRevenueWeek"] = {
            "week": top_week[0],
            "amount": f"£{top_week[1] / 100:.2f}",
        }

    if revenue_by_month:
        top_month = max(revenue_by_month.items(), key=lambda x: x[1])
        month_date = datetime.strptime(top_month[0], "%Y-%m")
        fun_facts["topRevenueMonth"] = {
            "month": month_date.strftime("%B %Y"),
            "amount": f"£{top_month[1] / 100:.2f}",
        }

    # Group bookings by month
    bookings_by_month = defaultdict(list)
    for booking in bookings:
        if not booking.payment or not booking.payment.paid_at:
            continue
        paid_at_uk = to_uk_datetime(booking.payment.paid_at)
        month_key = paid_at_uk.strftime("%Y-%m")

        gross_pence = booking.payment.amount_pence or 0
        refund_pence = booking.payment.refund_amount_pence or 0
        net_pence = gross_pence - refund_pence

        trip_days = None
        if booking.dropoff_date and booking.pickup_date:
            trip_days = (booking.pickup_date - booking.dropoff_date).days

        promo_info = promo_codes.get(booking.id)
        discount_percent = promo_info["discount_percent"] if promo_info else 0

        original_pence = gross_pence
        discount_pence = 0
        if discount_percent and discount_percent < 100:
            original_pence = int(gross_pence / (1 - discount_percent / 100))
            discount_pence = original_pence - gross_pence

        bookings_by_month[month_key].append({
            "id": booking.id,
            "reference": booking.reference,
            "paidDate": paid_at_uk.strftime("%d/%m/%Y"),
            "paidDateSort": paid_at_uk.date().isoformat(),
            "customerName": f"{booking.customer.first_name} {booking.customer.last_name}",
            "tripDays": trip_days,
            "grossPrice": f"£{gross_pence / 100:.2f}",
            "grossPence": gross_pence,
            "promoCode": promo_info["code"] if promo_info else None,
            "discountPercent": discount_percent,
            "discountAmount": f"£{discount_pence / 100:.2f}" if discount_pence else None,
            "discountPence": discount_pence,
            "refundAmount": f"£{refund_pence / 100:.2f}" if refund_pence else None,
            "refundPence": refund_pence,
            "netRevenue": f"£{net_pence / 100:.2f}",
            "netPence": net_pence,
            "status": booking.status.value,
            "paymentStatus": booking.payment.status.value,
        })

    # Sort bookings within each month by date ASC
    for month_key in bookings_by_month:
        bookings_by_month[month_key].sort(key=lambda x: x["paidDateSort"])

    # Build monthly data sorted DESC
    months_sorted = sorted(bookings_by_month.keys(), reverse=True)
    monthly_data = []

    for month_key in months_sorted:
        month_date = datetime.strptime(month_key, "%Y-%m")
        month_bookings = bookings_by_month[month_key]
        month_total = sum(b["netPence"] for b in month_bookings)
        month_gross = sum(b["grossPence"] for b in month_bookings)

        monthly_data.append({
            "monthKey": month_key,
            "monthLabel": month_date.strftime("%B %Y"),
            "bookingCount": len(month_bookings),
            "totalGross": f"£{month_gross / 100:.2f}",
            "totalNet": f"£{month_total / 100:.2f}",
            "bookings": month_bookings,
        })

    # Calculate totals
    total_gross = sum(b.payment.amount_pence or 0 for b in bookings if b.payment)
    total_refunds = sum(b.payment.refund_amount_pence or 0 for b in bookings if b.payment)
    total_net = total_gross - total_refunds

    return {
        "funFacts": fun_facts,
        "monthlyData": monthly_data,
        "summary": {
            "totalBookings": len(bookings),
            "totalGross": f"£{total_gross / 100:.2f}",
            "totalRefunds": f"£{total_refunds / 100:.2f}",
            "totalNet": f"£{total_net / 100:.2f}",
        }
    }


# =============================================================================
# Integration Tests - Full API Response
# =============================================================================

class TestFinancialReportIntegration:
    """Integration tests for financial report endpoint."""

    def test_full_response_structure(self):
        """Full API response should have correct structure."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000)),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert "funFacts" in response
        assert "monthlyData" in response
        assert "summary" in response
        assert "topRevenueDay" in response["funFacts"]
        assert "topRevenueWeek" in response["funFacts"]
        assert "topRevenueMonth" in response["funFacts"]
        assert "totalBookings" in response["summary"]
        assert "totalGross" in response["summary"]
        assert "totalRefunds" in response["summary"]
        assert "totalNet" in response["summary"]

    def test_fun_facts_populated(self):
        """Fun facts should be populated with actual data."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 15, 10, 0))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 1, 15, 14, 0))),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 1, 16, 10, 0))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Top day should be Jan 15 with £80
        assert response["funFacts"]["topRevenueDay"]["date"] == "Mon 15 Jan 2024"
        assert response["funFacts"]["topRevenueDay"]["amount"] == "£80.00"
        assert response["funFacts"]["topRevenueDay"]["bookings"] == 2


# =============================================================================
# Integration Tests - Complete Workflow
# =============================================================================

class TestCompleteWorkflow:
    """Integration tests for complete data processing workflow."""

    def test_bookings_to_monthly_breakdown(self):
        """Test complete workflow from bookings to monthly breakdown."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 15, 10, 0))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 1, 20, 10, 0))),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 2, 5, 10, 0))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Should have 2 months
        assert len(response["monthlyData"]) == 2

        # February should be first (sorted DESC)
        assert response["monthlyData"][0]["monthKey"] == "2024-02"
        assert response["monthlyData"][0]["bookingCount"] == 1

        # January should be second
        assert response["monthlyData"][1]["monthKey"] == "2024-01"
        assert response["monthlyData"][1]["bookingCount"] == 2

    def test_bookings_sorted_within_month(self):
        """Bookings within a month should be sorted by date ASC."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2024, 1, 20, 10, 0))),
            create_mock_booking(id=2, payment=create_mock_payment(paid_at=datetime(2024, 1, 5, 10, 0))),
            create_mock_booking(id=3, payment=create_mock_payment(paid_at=datetime(2024, 1, 15, 10, 0))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        month_bookings = response["monthlyData"][0]["bookings"]
        assert month_bookings[0]["id"] == 2  # Jan 5
        assert month_bookings[1]["id"] == 3  # Jan 15
        assert month_bookings[2]["id"] == 1  # Jan 20

    def test_revenue_calculation_with_refunds(self):
        """Revenue should correctly subtract refunds."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=10000, refund_amount_pence=2000)),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=5000, refund_amount_pence=0)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["summary"]["totalGross"] == "£150.00"
        assert response["summary"]["totalRefunds"] == "£20.00"
        assert response["summary"]["totalNet"] == "£130.00"

    def test_promo_code_information_included(self):
        """Promo code information should be included in booking data."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=9000)),  # £90 after 10% off
        ]
        promo_codes = {
            1: {"code": "SUMMER10", "discount_percent": 10}
        }

        response = simulate_financial_report_endpoint(bookings, promo_codes=promo_codes)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["promoCode"] == "SUMMER10"
        assert booking["discountPercent"] == 10
        assert booking["discountAmount"] == "£10.00"  # Original £100 - £90 = £10 discount


# =============================================================================
# Integration Tests - Filtering
# =============================================================================

class TestFilteringIntegration:
    """Integration tests for filter combinations."""

    def test_filter_by_date_range(self):
        """Should filter by date range correctly."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2024, 1, 10))),
            create_mock_booking(id=2, payment=create_mock_payment(paid_at=datetime(2024, 1, 20))),
            create_mock_booking(id=3, payment=create_mock_payment(paid_at=datetime(2024, 2, 5))),
        ]

        from_date = datetime(2024, 1, 15)
        to_date = datetime(2024, 1, 31, 23, 59, 59)

        response = simulate_financial_report_endpoint(
            bookings,
            from_date=from_date,
            to_date=to_date,
        )

        # Only Jan 20 should be included
        assert response["summary"]["totalBookings"] == 1

    def test_filter_by_status_confirmed(self):
        """Should filter to confirmed only."""
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="confirmed"),
        ]

        response = simulate_financial_report_endpoint(bookings, status_filter="confirmed")

        assert response["summary"]["totalBookings"] == 2

    def test_filter_by_status_completed(self):
        """Should filter to completed only."""
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="completed"),
        ]

        response = simulate_financial_report_endpoint(bookings, status_filter="completed")

        assert response["summary"]["totalBookings"] == 2

    def test_filter_by_status_refunded(self):
        """Should filter to refunded only."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(status="succeeded")),
            create_mock_booking(id=2, payment=create_mock_payment(status="refunded")),
            create_mock_booking(id=3, payment=create_mock_payment(status="partially_refunded")),
        ]

        response = simulate_financial_report_endpoint(bookings, status_filter="refunded")

        assert response["summary"]["totalBookings"] == 2

    def test_filter_by_promo_yes(self):
        """Should filter to bookings with promo codes."""
        bookings = [
            create_mock_booking(id=1),
            create_mock_booking(id=2),
            create_mock_booking(id=3),
        ]
        promo_codes = {
            1: {"code": "PROMO1", "discount_percent": 10},
            3: {"code": "PROMO2", "discount_percent": 20},
        }

        response = simulate_financial_report_endpoint(
            bookings,
            promo_codes=promo_codes,
            promo_filter="yes",
        )

        assert response["summary"]["totalBookings"] == 2

    def test_filter_by_promo_no(self):
        """Should filter to bookings without promo codes."""
        bookings = [
            create_mock_booking(id=1),
            create_mock_booking(id=2),
            create_mock_booking(id=3),
        ]
        promo_codes = {
            1: {"code": "PROMO1", "discount_percent": 10},
        }

        response = simulate_financial_report_endpoint(
            bookings,
            promo_codes=promo_codes,
            promo_filter="no",
        )

        assert response["summary"]["totalBookings"] == 2

    def test_combined_filters(self):
        """Should apply multiple filters together."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment=create_mock_payment(paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, status="completed", payment=create_mock_payment(paid_at=datetime(2024, 1, 20))),
            create_mock_booking(id=3, status="confirmed", payment=create_mock_payment(paid_at=datetime(2024, 2, 5))),
        ]
        promo_codes = {
            1: {"code": "PROMO1", "discount_percent": 10},
            3: {"code": "PROMO2", "discount_percent": 20},
        }

        response = simulate_financial_report_endpoint(
            bookings,
            promo_codes=promo_codes,
            from_date=datetime(2024, 1, 1),
            to_date=datetime(2024, 1, 31, 23, 59, 59),
            status_filter="confirmed",
            promo_filter="yes",
        )

        # Only booking 1 matches: confirmed, has promo, in Jan
        assert response["summary"]["totalBookings"] == 1


# =============================================================================
# Integration Tests - Edge Cases
# =============================================================================

class TestIntegrationEdgeCases:
    """Integration tests for edge cases."""

    def test_empty_bookings(self):
        """Empty bookings list should return empty data."""
        response = simulate_financial_report_endpoint([])

        assert response["summary"]["totalBookings"] == 0
        assert response["summary"]["totalGross"] == "£0.00"
        assert response["summary"]["totalNet"] == "£0.00"
        assert len(response["monthlyData"]) == 0
        assert response["funFacts"]["topRevenueDay"] is None
        assert response["funFacts"]["topRevenueWeek"] is None
        assert response["funFacts"]["topRevenueMonth"] is None

    def test_single_booking(self):
        """Single booking should work correctly."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["summary"]["totalBookings"] == 1
        assert response["summary"]["totalGross"] == "£50.00"
        assert len(response["monthlyData"]) == 1

    def test_all_refunded_bookings(self):
        """All refunded bookings should show zero net."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, refund_amount_pence=5000, status="refunded")),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, refund_amount_pence=3000, status="refunded")),
        ]

        response = simulate_financial_report_endpoint(bookings, status_filter="refunded")

        assert response["summary"]["totalGross"] == "£80.00"
        assert response["summary"]["totalRefunds"] == "£80.00"
        assert response["summary"]["totalNet"] == "£0.00"

    def test_bookings_without_payment_excluded(self):
        """Bookings without payment should be excluded."""
        booking1 = create_mock_booking(id=1)
        booking2 = create_mock_booking(id=2)
        booking2.payment = None

        bookings = [booking1, booking2]

        response = simulate_financial_report_endpoint(bookings)

        assert response["summary"]["totalBookings"] == 1

    def test_large_number_of_bookings(self):
        """Large number of bookings should be handled."""
        base_date = datetime(2024, 1, 1)
        bookings = [
            create_mock_booking(
                id=i,
                payment=create_mock_payment(
                    id=i,
                    amount_pence=5000,
                    paid_at=base_date + timedelta(days=i % 30)
                )
            )
            for i in range(1, 101)
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["summary"]["totalBookings"] == 100
        # Format may or may not have comma separator
        assert response["summary"]["totalGross"] in ["£5,000.00", "£5000.00"]

    def test_mixed_status_bookings(self):
        """Mixed status bookings should filter correctly under the default 'all' view.

        The 'all' view now includes confirmed, completed, cancelled, and refunded
        (refunds carry negative revenue impact and should not silently disappear).
        Only PENDING is excluded because pending bookings have no completed
        payment to attribute revenue from.
        """
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
            create_mock_booking(id=5, status="refunded", payment=create_mock_payment(status="refunded", refund_amount_pence=6800)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # confirmed + completed + cancelled + refunded — pending excluded
        assert response["summary"]["totalBookings"] == 4

    def test_refunded_booking_appears_in_default_all_view(self):
        """Regression: a booking with status='refunded' must surface in the
        default Financial view, not silently drop out. (2026-05 fix — the
        'all' branch previously filtered to [CONFIRMED, COMPLETED, CANCELLED]
        and excluded REFUNDED, so backfilled refunds disappeared from the
        Financial table even though Total Refunds counted them elsewhere.)
        """
        bookings = [
            create_mock_booking(
                id=1,
                reference="TAG-DYC21950",
                status="refunded",
                payment=create_mock_payment(
                    booking_id=1,
                    status="refunded",
                    amount_pence=6800,
                    refund_amount_pence=6800,
                ),
            ),
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["summary"]["totalBookings"] == 1
        # And the booking is visible in the monthly breakdown
        all_refs = [
            b["reference"]
            for month in response["monthlyData"]
            for b in month["bookings"]
        ]
        assert "TAG-DYC21950" in all_refs

    def test_trip_days_calculation(self):
        """Trip days should be calculated correctly."""
        bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2024, 1, 1),
                pickup_date=date(2024, 1, 8),
            ),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["tripDays"] == 7

    def test_customer_name_concatenation(self):
        """Customer name should be properly concatenated."""
        customer = create_mock_customer(first_name="Jane", last_name="Smith")
        bookings = [
            create_mock_booking(id=1, customer=customer),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["customerName"] == "Jane Smith"


# =============================================================================
# Integration Tests - Revenue Fun Facts
# =============================================================================

class TestRevenueFunFacts:
    """Integration tests for revenue fun facts."""

    def test_top_revenue_day_calculation(self):
        """Top revenue day should be correctly identified."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 16))),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 1, 16))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Jan 16 has £70 (2 bookings), Jan 15 has £30
        assert "16" in response["funFacts"]["topRevenueDay"]["date"]
        assert response["funFacts"]["topRevenueDay"]["amount"] == "£70.00"
        assert response["funFacts"]["topRevenueDay"]["bookings"] == 2

    def test_top_revenue_week_calculation(self):
        """Top revenue week should be correctly identified."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 8))),  # Week 2
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 1, 10))),  # Week 2
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 1, 15))),  # Week 3
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["funFacts"]["topRevenueWeek"]["week"] == "2024-W02"
        assert response["funFacts"]["topRevenueWeek"]["amount"] == "£80.00"

    def test_top_revenue_month_calculation(self):
        """Top revenue month should be correctly identified."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 1, 20))),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 2, 5))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        assert response["funFacts"]["topRevenueMonth"]["month"] == "January 2024"
        assert response["funFacts"]["topRevenueMonth"]["amount"] == "£80.00"

    def test_fun_facts_with_refunds(self):
        """Fun facts should use net revenue (after refunds)."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=10000, refund_amount_pence=5000, paid_at=datetime(2024, 1, 15))),  # Net £50
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=6000, refund_amount_pence=0, paid_at=datetime(2024, 1, 16))),  # Net £60
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Jan 16 has higher net revenue
        assert "16" in response["funFacts"]["topRevenueDay"]["date"]
        assert response["funFacts"]["topRevenueDay"]["amount"] == "£60.00"


# =============================================================================
# Integration Tests - Monthly Summary
# =============================================================================

class TestMonthlySummary:
    """Integration tests for monthly summary calculations."""

    def test_monthly_totals_correct(self):
        """Monthly totals should be calculated correctly."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, refund_amount_pence=0, paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, refund_amount_pence=500, paid_at=datetime(2024, 1, 20))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        month = response["monthlyData"][0]
        assert month["totalGross"] == "£80.00"
        assert month["totalNet"] == "£75.00"  # £80 - £5 refund
        assert month["bookingCount"] == 2

    def test_multiple_months_summary(self):
        """Multiple months should each have correct summaries."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, paid_at=datetime(2024, 1, 15))),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, paid_at=datetime(2024, 2, 15))),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, paid_at=datetime(2024, 2, 20))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # February first (DESC order)
        assert response["monthlyData"][0]["monthLabel"] == "February 2024"
        assert response["monthlyData"][0]["bookingCount"] == 2
        assert response["monthlyData"][0]["totalGross"] == "£50.00"

        # January second
        assert response["monthlyData"][1]["monthLabel"] == "January 2024"
        assert response["monthlyData"][1]["bookingCount"] == 1
        assert response["monthlyData"][1]["totalGross"] == "£50.00"


# =============================================================================
# Integration Tests - Discount Calculation
# =============================================================================

class TestDiscountCalculationIntegration:
    """Integration tests for discount calculations."""

    def test_discount_amount_calculated(self):
        """Discount amount should be calculated from promo percentage."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=9000)),  # £90 after 10% off
        ]
        promo_codes = {
            1: {"code": "SUMMER10", "discount_percent": 10}
        }

        response = simulate_financial_report_endpoint(bookings, promo_codes=promo_codes)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["discountPercent"] == 10
        assert booking["discountAmount"] == "£10.00"

    def test_no_promo_no_discount(self):
        """Booking without promo should have no discount."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=10000)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["promoCode"] is None
        assert booking["discountPercent"] == 0
        assert booking["discountAmount"] is None

    def test_large_discount(self):
        """Large discount percentage should calculate correctly."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000)),  # £50 after 50% off
        ]
        promo_codes = {
            1: {"code": "HALF", "discount_percent": 50}
        }

        response = simulate_financial_report_endpoint(bookings, promo_codes=promo_codes)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["discountPercent"] == 50
        assert booking["discountAmount"] == "£50.00"  # Original £100 - £50 = £50


# =============================================================================
# Integration Tests - Data Integrity
# =============================================================================

class TestDataIntegrity:
    """Integration tests for data integrity."""

    def test_booking_reference_preserved(self):
        """Booking reference should be preserved in response."""
        bookings = [
            create_mock_booking(id=1, reference="TAG-ABC123"),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["reference"] == "TAG-ABC123"

    def test_payment_date_format(self):
        """Payment date should be in DD/MM/YYYY format."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(paid_at=datetime(2024, 1, 15))),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["paidDate"] == "15/01/2024"

    @pytest.mark.parametrize(
        "paid_at_utc, expected_uk_display, expected_in_10_june_filter",
        [
            (datetime(2026, 6, 9, 22, 59, tzinfo=timezone.utc), "09/06/2026 23:59", False),
            (datetime(2026, 6, 9, 23, 0, tzinfo=timezone.utc), "10/06/2026 00:00", True),
            (datetime(2026, 6, 9, 23, 59, tzinfo=timezone.utc), "10/06/2026 00:59", True),
            (datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc), "10/06/2026 01:00", True),
            (datetime(2026, 6, 10, 0, 1, tzinfo=timezone.utc), "10/06/2026 01:01", True),
        ],
    )
    def test_payment_date_uses_uk_boundary_for_bst_midnight(
        self,
        paid_at_utc,
        expected_uk_display,
        expected_in_10_june_filter,
    ):
        """Financial reports should display and filter paid_at by UK local date."""
        from main import parse_uk_date_end, parse_uk_date_start, to_uk_datetime

        paid_at_uk = to_uk_datetime(paid_at_utc)
        assert paid_at_uk.strftime("%d/%m/%Y %H:%M") == expected_uk_display

        filter_start = parse_uk_date_start("10/06/2026")
        filter_end = parse_uk_date_end("10/06/2026")
        assert (filter_start <= paid_at_utc <= filter_end) is expected_in_10_june_filter

    def test_financial_report_groups_late_utc_payment_under_next_uk_day(self):
        """A 23:00+ UTC payment during BST should appear on the following UK date."""
        bookings = [
            create_mock_booking(
                id=1,
                reference="TAG-LGG16579",
                payment=create_mock_payment(
                    amount_pence=6300,
                    paid_at=datetime(2026, 6, 9, 23, 32, tzinfo=timezone.utc),
                ),
            ),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["reference"] == "TAG-LGG16579"
        assert booking["paidDate"] == "10/06/2026"
        assert booking["paidDateSort"] == "2026-06-10"

    @pytest.mark.parametrize(
        "paid_at_utc, expected_uk_display",
        [
            # Winter: UK is GMT, so UTC midnight boundaries do not shift.
            (datetime(2026, 1, 9, 22, 59, tzinfo=timezone.utc), "09/01/2026 22:59"),
            (datetime(2026, 1, 9, 23, 0, tzinfo=timezone.utc), "09/01/2026 23:00"),
            (datetime(2026, 1, 9, 23, 59, tzinfo=timezone.utc), "09/01/2026 23:59"),
            (datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc), "10/01/2026 00:00"),
            (datetime(2026, 1, 10, 0, 1, tzinfo=timezone.utc), "10/01/2026 00:01"),
            # Spring forward: 01:00 UTC skips to 02:00 UK local time.
            (datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc), "29/03/2026 00:59"),
            (datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc), "29/03/2026 02:00"),
            # Autumn back: 01:00 UTC returns to 01:00 UK local time.
            (datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc), "25/10/2026 01:59"),
            (datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc), "25/10/2026 01:00"),
        ],
    )
    def test_payment_date_uses_uk_clock_changes(self, paid_at_utc, expected_uk_display):
        """UK display should follow GMT/BST clock changes from timezone data."""
        from main import to_uk_datetime

        assert to_uk_datetime(paid_at_utc).strftime("%d/%m/%Y %H:%M") == expected_uk_display

    def test_uk_date_filter_bounds_change_with_gmt_and_bst(self):
        """A DD/MM/YYYY filter should map to the correct UTC span for that UK day."""
        from main import parse_uk_date_end, parse_uk_date_start

        winter_start = parse_uk_date_start("10/01/2026").astimezone(timezone.utc)
        winter_end = parse_uk_date_end("10/01/2026").astimezone(timezone.utc)
        assert winter_start == datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert winter_end == datetime(2026, 1, 10, 23, 59, 59, 999999, tzinfo=timezone.utc)

        summer_start = parse_uk_date_start("10/06/2026").astimezone(timezone.utc)
        summer_end = parse_uk_date_end("10/06/2026").astimezone(timezone.utc)
        assert summer_start == datetime(2026, 6, 9, 23, 0, tzinfo=timezone.utc)
        assert summer_end == datetime(2026, 6, 10, 22, 59, 59, 999999, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "paid_at_utc, expected_uk_display",
        [
            # BST month end: the last UTC hour of June is already July in the UK.
            (datetime(2026, 6, 30, 22, 59, tzinfo=timezone.utc), "30/06/2026 23:59"),
            (datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc), "01/07/2026 00:00"),
            (datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc), "01/07/2026 00:59"),
            (datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc), "01/07/2026 01:00"),
            # GMT month end: UTC and UK dates roll together.
            (datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc), "31/01/2026 23:59"),
            (datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc), "01/02/2026 00:00"),
            # GMT year end: 31 December rolls to 1 January at the UTC/UK boundary.
            (datetime(2026, 12, 31, 22, 59, tzinfo=timezone.utc), "31/12/2026 22:59"),
            (datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc), "31/12/2026 23:00"),
            (datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), "31/12/2026 23:59"),
            (datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc), "01/01/2027 00:00"),
            (datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc), "01/01/2027 00:01"),
        ],
    )
    def test_payment_date_uses_uk_end_of_month_boundaries(self, paid_at_utc, expected_uk_display):
        """Financial date display should roll month boundaries in UK local time."""
        from main import to_uk_datetime

        assert to_uk_datetime(paid_at_utc).strftime("%d/%m/%Y %H:%M") == expected_uk_display

    def test_financial_report_groups_late_utc_month_end_payment_under_next_uk_month(self):
        """A BST month-end payment after 23:00 UTC should group under the next UK month."""
        bookings = [
            create_mock_booking(
                id=1,
                reference="TAG-MONTHEND",
                payment=create_mock_payment(
                    amount_pence=6300,
                    paid_at=datetime(2026, 6, 30, 23, 15, tzinfo=timezone.utc),
                ),
            ),
        ]

        response = simulate_financial_report_endpoint(bookings)

        month = response["monthlyData"][0]
        booking = month["bookings"][0]
        assert month["monthKey"] == "2026-07"
        assert month["monthLabel"] == "July 2026"
        assert booking["paidDate"] == "01/07/2026"
        assert booking["paidDateSort"] == "2026-07-01"

    def test_financial_report_groups_year_end_payment_under_next_uk_year(self):
        """A payment at 00:00 UTC on 1 January should group under the new UK year."""
        bookings = [
            create_mock_booking(
                id=1,
                reference="TAG-YEAREND",
                payment=create_mock_payment(
                    amount_pence=6300,
                    paid_at=datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc),
                ),
            ),
        ]

        response = simulate_financial_report_endpoint(bookings)

        month = response["monthlyData"][0]
        booking = month["bookings"][0]
        assert month["monthKey"] == "2027-01"
        assert month["monthLabel"] == "January 2027"
        assert booking["paidDate"] == "01/01/2027"
        assert booking["paidDateSort"] == "2027-01-01"

    @pytest.mark.parametrize(
        "paid_at_utc, expected_uk_display",
        [
            (datetime(2024, 2, 28, 23, 59, tzinfo=timezone.utc), "28/02/2024 23:59"),
            (datetime(2024, 2, 29, 0, 0, tzinfo=timezone.utc), "29/02/2024 00:00"),
            (datetime(2024, 2, 29, 0, 1, tzinfo=timezone.utc), "29/02/2024 00:01"),
            (datetime(2024, 2, 29, 23, 59, tzinfo=timezone.utc), "29/02/2024 23:59"),
            (datetime(2024, 3, 1, 0, 0, tzinfo=timezone.utc), "01/03/2024 00:00"),
        ],
    )
    def test_payment_date_uses_uk_leap_year_boundaries(self, paid_at_utc, expected_uk_display):
        """Leap day should be represented and grouped as a real UK calendar day."""
        from main import to_uk_datetime

        assert to_uk_datetime(paid_at_utc).strftime("%d/%m/%Y %H:%M") == expected_uk_display

    def test_uk_date_filter_bounds_include_full_leap_day(self):
        """A 29/02/YYYY filter should include the whole leap day and exclude neighbours."""
        from main import parse_uk_date_end, parse_uk_date_start

        leap_start = parse_uk_date_start("29/02/2024")
        leap_end = parse_uk_date_end("29/02/2024")
        assert leap_start.astimezone(timezone.utc) == datetime(2024, 2, 29, 0, 0, tzinfo=timezone.utc)
        assert leap_end.astimezone(timezone.utc) == datetime(
            2024, 2, 29, 23, 59, 59, 999999, tzinfo=timezone.utc
        )

        assert datetime(2024, 2, 28, 23, 59, 59, 999999, tzinfo=timezone.utc) < leap_start
        assert leap_start <= datetime(2024, 2, 29, 0, 0, tzinfo=timezone.utc) <= leap_end
        assert leap_start <= datetime(2024, 2, 29, 23, 59, 59, tzinfo=timezone.utc) <= leap_end
        assert datetime(2024, 3, 1, 0, 0, tzinfo=timezone.utc) > leap_end

    def test_uk_date_filter_bounds_include_full_year_end_day(self):
        """A 31/12/YYYY filter should include the full UK calendar day and exclude New Year."""
        from main import parse_uk_date_end, parse_uk_date_start

        year_end_start = parse_uk_date_start("31/12/2026")
        year_end_end = parse_uk_date_end("31/12/2026")
        assert year_end_start.astimezone(timezone.utc) == datetime(2026, 12, 31, 0, 0, tzinfo=timezone.utc)
        assert year_end_end.astimezone(timezone.utc) == datetime(
            2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc
        )

        assert datetime(2026, 12, 30, 23, 59, 59, 999999, tzinfo=timezone.utc) < year_end_start
        assert year_end_start <= datetime(2026, 12, 31, 0, 0, tzinfo=timezone.utc) <= year_end_end
        assert year_end_start <= datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc) <= year_end_end
        assert datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc) > year_end_end

    def test_status_value_preserved(self):
        """Booking and payment status should be preserved."""
        bookings = [
            create_mock_booking(id=1, status="confirmed", payment=create_mock_payment(status="succeeded")),
        ]

        response = simulate_financial_report_endpoint(bookings)

        booking = response["monthlyData"][0]["bookings"][0]
        assert booking["status"] == "confirmed"
        assert booking["paymentStatus"] == "succeeded"

    def test_gross_and_net_consistency(self):
        """Total gross - refunds should equal total net."""
        bookings = [
            create_mock_booking(id=1, payment=create_mock_payment(amount_pence=5000, refund_amount_pence=500)),
            create_mock_booking(id=2, payment=create_mock_payment(amount_pence=3000, refund_amount_pence=300)),
            create_mock_booking(id=3, payment=create_mock_payment(amount_pence=2000, refund_amount_pence=0)),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Parse the formatted values back to verify
        gross = float(response["summary"]["totalGross"].replace("£", "").replace(",", ""))
        refunds = float(response["summary"]["totalRefunds"].replace("£", "").replace(",", ""))
        net = float(response["summary"]["totalNet"].replace("£", "").replace(",", ""))

        assert abs((gross - refunds) - net) < 0.01  # Allow for rounding
