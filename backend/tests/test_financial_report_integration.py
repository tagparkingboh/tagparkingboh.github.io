"""
Integration tests for Admin Financial Report.

These tests verify the full workflow from bookings data to API response.
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
        # All - include confirmed, completed
        bookings = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]

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
        paid_date = booking.payment.paid_at.date()
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
        bookings_on_day = sum(1 for b in bookings if b.payment and b.payment.paid_at and b.payment.paid_at.date() == top_day[0])
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
        month_key = booking.payment.paid_at.strftime("%Y-%m")

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
            "paidDate": booking.payment.paid_at.strftime("%d/%m/%Y"),
            "paidDateSort": booking.payment.paid_at.date().isoformat(),
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
        """Mixed status bookings should filter correctly."""
        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
        ]

        response = simulate_financial_report_endpoint(bookings)

        # Only confirmed and completed (default filter)
        assert response["summary"]["totalBookings"] == 2

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
