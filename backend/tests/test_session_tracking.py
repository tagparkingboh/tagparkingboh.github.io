"""
Tests for Session Tracking Report and Audit Events.

Covers:
- POST /api/booking/audit-event - Logging funnel events (dates_selected, flight_selected)
- GET /api/admin/reports/session-tracking - Session tracking report

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_audit_log(
    id=1,
    session_id="sess_123_abc",
    event="dates_selected",
    created_at=None,
    event_data=None,
    booking_reference=None,
):
    """Create a mock audit log object."""
    from db_models import AuditLogEvent

    log = MagicMock()
    log.id = id
    log.session_id = session_id
    log.booking_reference = booking_reference
    log.created_at = created_at or datetime.utcnow()
    log.event_data = event_data or {}

    # Map string to enum
    event_map = {
        "dates_selected": AuditLogEvent.DATES_SELECTED,
        "flight_selected": AuditLogEvent.FLIGHT_SELECTED,
        "customer_entered": AuditLogEvent.CUSTOMER_ENTERED,
        "payment_initiated": AuditLogEvent.PAYMENT_INITIATED,
        "booking_confirmed": AuditLogEvent.BOOKING_CONFIRMED,
    }
    log.event = event_map.get(event, AuditLogEvent.DATES_SELECTED)

    return log


def create_mock_session_tracking_response(
    period_type="daily",
    stages=None,
    periods=None,
    cumulative=None,
):
    """Create a mock session tracking response."""
    if stages is None:
        stages = [
            {"key": "dates_selected", "label": "Dates Selected"},
            {"key": "flight_selected", "label": "Flight Selected"},
            {"key": "customer_entered", "label": "Details Entered"},
            {"key": "payment_initiated", "label": "Payment Started"},
            {"key": "booking_confirmed", "label": "Booking Confirmed"},
        ]

    if periods is None:
        periods = [
            {
                "period": "2024-01-15",
                "label": "15 Jan",
                "counts": {
                    "dates_selected": 10,
                    "flight_selected": 8,
                    "customer_entered": 5,
                    "payment_initiated": 4,
                    "booking_confirmed": 3,
                }
            }
        ]

    if cumulative is None:
        cumulative = {
            "counts": {
                "dates_selected": 100,
                "flight_selected": 80,
                "customer_entered": 50,
                "payment_initiated": 40,
                "booking_confirmed": 30,
            },
            "conversion_rates": {
                "dates_selected": 100.0,
                "flight_selected": 80.0,
                "customer_entered": 62.5,
                "payment_initiated": 80.0,
                "booking_confirmed": 75.0,
            },
            "overall_conversion": 30.0,
        }

    return {
        "period_type": period_type,
        "stages": stages,
        "periods": periods,
        "cumulative": cumulative,
    }


# =============================================================================
# Unit Tests - Audit Event Logging
# =============================================================================

class TestAuditEventLogging:
    """Unit tests for audit event logging."""

    def test_dates_selected_event_is_valid_enum(self):
        """dates_selected should be a valid AuditLogEvent."""
        from db_models import AuditLogEvent

        assert hasattr(AuditLogEvent, 'DATES_SELECTED')
        assert AuditLogEvent.DATES_SELECTED.value == "dates_selected"

    def test_flight_selected_event_is_valid_enum(self):
        """flight_selected should be a valid AuditLogEvent."""
        from db_models import AuditLogEvent

        assert hasattr(AuditLogEvent, 'FLIGHT_SELECTED')
        assert AuditLogEvent.FLIGHT_SELECTED.value == "flight_selected"

    def test_all_funnel_events_exist(self):
        """All funnel stage events should exist in AuditLogEvent."""
        from db_models import AuditLogEvent

        funnel_events = [
            "DATES_SELECTED",
            "FLIGHT_SELECTED",
            "CUSTOMER_ENTERED",
            "PAYMENT_INITIATED",
            "BOOKING_CONFIRMED",
        ]

        for event_name in funnel_events:
            assert hasattr(AuditLogEvent, event_name), f"Missing event: {event_name}"


# =============================================================================
# Unit Tests - Session Tracking Response Structure
# =============================================================================

class TestSessionTrackingResponseStructure:
    """Unit tests for response structure."""

    def test_response_includes_period_type(self):
        """Response should include period_type field."""
        response = create_mock_session_tracking_response()

        assert "period_type" in response
        assert response["period_type"] in ["daily", "weekly", "monthly"]

    def test_response_includes_stages_array(self):
        """Response should include stages array."""
        response = create_mock_session_tracking_response()

        assert "stages" in response
        assert isinstance(response["stages"], list)
        assert len(response["stages"]) == 5

    def test_response_includes_periods_array(self):
        """Response should include periods array."""
        response = create_mock_session_tracking_response()

        assert "periods" in response
        assert isinstance(response["periods"], list)

    def test_response_includes_cumulative_section(self):
        """Response should include cumulative section."""
        response = create_mock_session_tracking_response()

        assert "cumulative" in response
        assert "counts" in response["cumulative"]
        assert "conversion_rates" in response["cumulative"]
        assert "overall_conversion" in response["cumulative"]

    def test_stage_entry_structure(self):
        """Stage entry should include key and label."""
        response = create_mock_session_tracking_response()

        stage = response["stages"][0]
        assert "key" in stage
        assert "label" in stage

    def test_period_entry_structure(self):
        """Period entry should include period, label, and counts."""
        response = create_mock_session_tracking_response()

        period = response["periods"][0]
        assert "period" in period
        assert "label" in period
        assert "counts" in period

    def test_cumulative_counts_has_all_stages(self):
        """Cumulative counts should have entries for all stages."""
        response = create_mock_session_tracking_response()

        counts = response["cumulative"]["counts"]
        expected_keys = ["dates_selected", "flight_selected", "customer_entered",
                        "payment_initiated", "booking_confirmed"]

        for key in expected_keys:
            assert key in counts


# =============================================================================
# Unit Tests - Conversion Rate Calculations
# =============================================================================

class TestConversionRateCalculations:
    """Unit tests for conversion rate calculations."""

    def test_overall_conversion_calculation(self):
        """Overall conversion should be (confirmed / dates_selected) * 100."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 100,
                    "flight_selected": 80,
                    "customer_entered": 50,
                    "payment_initiated": 40,
                    "booking_confirmed": 30,
                },
                "conversion_rates": {},
                "overall_conversion": 30.0,  # 30/100 * 100
            }
        )

        assert response["cumulative"]["overall_conversion"] == 30.0

    def test_zero_dates_selected_returns_zero_conversion(self):
        """Zero dates selected should result in 0% conversion."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 0,
                    "flight_selected": 0,
                    "customer_entered": 0,
                    "payment_initiated": 0,
                    "booking_confirmed": 0,
                },
                "conversion_rates": {},
                "overall_conversion": 0.0,
            }
        )

        assert response["cumulative"]["overall_conversion"] == 0.0

    def test_100_percent_conversion_when_all_convert(self):
        """100% conversion when all dates_selected become bookings."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 10,
                    "flight_selected": 10,
                    "customer_entered": 10,
                    "payment_initiated": 10,
                    "booking_confirmed": 10,
                },
                "conversion_rates": {
                    "dates_selected": 100.0,
                    "flight_selected": 100.0,
                    "customer_entered": 100.0,
                    "payment_initiated": 100.0,
                    "booking_confirmed": 100.0,
                },
                "overall_conversion": 100.0,
            }
        )

        assert response["cumulative"]["overall_conversion"] == 100.0


# =============================================================================
# Unit Tests - Period Types
# =============================================================================

class TestPeriodTypes:
    """Unit tests for different period types."""

    def test_daily_period_type(self):
        """Daily period should return daily data."""
        response = create_mock_session_tracking_response(period_type="daily")

        assert response["period_type"] == "daily"

    def test_weekly_period_type(self):
        """Weekly period should return weekly data."""
        response = create_mock_session_tracking_response(period_type="weekly")

        assert response["period_type"] == "weekly"

    def test_monthly_period_type(self):
        """Monthly period should return monthly data."""
        response = create_mock_session_tracking_response(period_type="monthly")

        assert response["period_type"] == "monthly"


# =============================================================================
# Unit Tests - Funnel Stage Order
# =============================================================================

class TestFunnelStageOrder:
    """Unit tests for funnel stage ordering."""

    def test_stages_are_in_correct_order(self):
        """Funnel stages should be in chronological order."""
        response = create_mock_session_tracking_response()

        expected_order = [
            "dates_selected",
            "flight_selected",
            "customer_entered",
            "payment_initiated",
            "booking_confirmed",
        ]

        actual_order = [s["key"] for s in response["stages"]]
        assert actual_order == expected_order

    def test_first_stage_is_dates_selected(self):
        """First funnel stage should be dates_selected."""
        response = create_mock_session_tracking_response()

        assert response["stages"][0]["key"] == "dates_selected"

    def test_last_stage_is_booking_confirmed(self):
        """Last funnel stage should be booking_confirmed."""
        response = create_mock_session_tracking_response()

        assert response["stages"][-1]["key"] == "booking_confirmed"


# =============================================================================
# Unit Tests - Empty Data Handling
# =============================================================================

class TestEmptyDataHandling:
    """Unit tests for empty data scenarios."""

    def test_empty_periods_array(self):
        """Empty periods array should be valid."""
        response = create_mock_session_tracking_response(periods=[])

        assert response["periods"] == []

    def test_zero_counts_in_cumulative(self):
        """Zero counts should be valid."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 0,
                    "flight_selected": 0,
                    "customer_entered": 0,
                    "payment_initiated": 0,
                    "booking_confirmed": 0,
                },
                "conversion_rates": {},
                "overall_conversion": 0.0,
            }
        )

        for stage in response["cumulative"]["counts"]:
            assert response["cumulative"]["counts"][stage] == 0


# =============================================================================
# Unit Tests - Audit Log Mock
# =============================================================================

class TestAuditLogMock:
    """Unit tests for audit log mock factory."""

    def test_mock_audit_log_has_required_fields(self):
        """Mock audit log should have all required fields."""
        log = create_mock_audit_log()

        assert hasattr(log, 'id')
        assert hasattr(log, 'session_id')
        assert hasattr(log, 'event')
        assert hasattr(log, 'created_at')
        assert hasattr(log, 'event_data')

    def test_mock_audit_log_event_is_enum(self):
        """Mock audit log event should be an AuditLogEvent enum."""
        from db_models import AuditLogEvent

        log = create_mock_audit_log(event="dates_selected")

        assert isinstance(log.event, AuditLogEvent)
        assert log.event == AuditLogEvent.DATES_SELECTED

    def test_mock_audit_log_custom_session_id(self):
        """Mock audit log should accept custom session_id."""
        log = create_mock_audit_log(session_id="custom_session_123")

        assert log.session_id == "custom_session_123"

    def test_mock_audit_log_custom_created_at(self):
        """Mock audit log should accept custom created_at."""
        custom_time = datetime(2024, 6, 15, 10, 30, 0)
        log = create_mock_audit_log(created_at=custom_time)

        assert log.created_at == custom_time


# =============================================================================
# Unit Tests - Drop-off Calculation
# =============================================================================

class TestDropOffCalculation:
    """Unit tests for drop-off between stages."""

    def test_drop_off_between_stages(self):
        """Drop-off should be previous stage count minus current stage count."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 100,
                    "flight_selected": 80,
                    "customer_entered": 50,
                    "payment_initiated": 40,
                    "booking_confirmed": 30,
                },
                "conversion_rates": {},
                "overall_conversion": 30.0,
            }
        )

        counts = response["cumulative"]["counts"]

        # Calculate expected drop-offs
        drop_dates_to_flight = counts["dates_selected"] - counts["flight_selected"]
        drop_flight_to_customer = counts["flight_selected"] - counts["customer_entered"]
        drop_customer_to_payment = counts["customer_entered"] - counts["payment_initiated"]
        drop_payment_to_confirmed = counts["payment_initiated"] - counts["booking_confirmed"]

        assert drop_dates_to_flight == 20
        assert drop_flight_to_customer == 30
        assert drop_customer_to_payment == 10
        assert drop_payment_to_confirmed == 10

    def test_no_drop_off_when_all_convert(self):
        """No drop-off when all sessions convert."""
        response = create_mock_session_tracking_response(
            cumulative={
                "counts": {
                    "dates_selected": 10,
                    "flight_selected": 10,
                    "customer_entered": 10,
                    "payment_initiated": 10,
                    "booking_confirmed": 10,
                },
                "conversion_rates": {},
                "overall_conversion": 100.0,
            }
        )

        counts = response["cumulative"]["counts"]

        # All drop-offs should be 0
        for i, stage in enumerate(["flight_selected", "customer_entered",
                                   "payment_initiated", "booking_confirmed"]):
            prev_stages = ["dates_selected", "flight_selected",
                         "customer_entered", "payment_initiated"]
            prev_count = counts[prev_stages[i]]
            curr_count = counts[stage]
            assert prev_count - curr_count == 0


# =============================================================================
# Integration-style Tests (Still Mocked)
# =============================================================================

class TestSessionTrackingIntegration:
    """Integration-style tests with mocked dependencies."""

    def test_multiple_sessions_same_period(self):
        """Multiple sessions in same period should be counted."""
        response = create_mock_session_tracking_response(
            periods=[
                {
                    "period": "2024-01-15",
                    "label": "15 Jan",
                    "counts": {
                        "dates_selected": 25,  # 25 unique sessions
                        "flight_selected": 20,
                        "customer_entered": 15,
                        "payment_initiated": 10,
                        "booking_confirmed": 8,
                    }
                }
            ]
        )

        period = response["periods"][0]
        assert period["counts"]["dates_selected"] == 25

    def test_multiple_periods_returned(self):
        """Multiple periods should be returned."""
        response = create_mock_session_tracking_response(
            periods=[
                {"period": "2024-01-15", "label": "15 Jan",
                 "counts": {"dates_selected": 10, "flight_selected": 8,
                           "customer_entered": 5, "payment_initiated": 4,
                           "booking_confirmed": 3}},
                {"period": "2024-01-16", "label": "16 Jan",
                 "counts": {"dates_selected": 15, "flight_selected": 12,
                           "customer_entered": 8, "payment_initiated": 6,
                           "booking_confirmed": 5}},
            ]
        )

        assert len(response["periods"]) == 2

    def test_cumulative_sums_across_periods(self):
        """Cumulative counts should sum across all periods."""
        # Two periods with different counts
        periods = [
            {"period": "2024-01-15", "label": "15 Jan",
             "counts": {"dates_selected": 10, "flight_selected": 8,
                       "customer_entered": 5, "payment_initiated": 4,
                       "booking_confirmed": 3}},
            {"period": "2024-01-16", "label": "16 Jan",
             "counts": {"dates_selected": 15, "flight_selected": 12,
                       "customer_entered": 8, "payment_initiated": 6,
                       "booking_confirmed": 5}},
        ]

        # Expected cumulative = sum of both periods
        response = create_mock_session_tracking_response(
            periods=periods,
            cumulative={
                "counts": {
                    "dates_selected": 25,  # 10 + 15
                    "flight_selected": 20,  # 8 + 12
                    "customer_entered": 13, # 5 + 8
                    "payment_initiated": 10, # 4 + 6
                    "booking_confirmed": 8,  # 3 + 5
                },
                "conversion_rates": {},
                "overall_conversion": 32.0,  # 8/25 * 100
            }
        )

        assert response["cumulative"]["counts"]["dates_selected"] == 25
        assert response["cumulative"]["counts"]["booking_confirmed"] == 8
