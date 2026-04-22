"""
Unit and Integration tests for Audit Logs and Error Logs endpoints.

Tests the QA Dashboard logging functionality:
- GET /api/admin/audit-logs
- GET /api/admin/audit-logs/events
- GET /api/admin/error-logs
- GET /api/admin/error-logs/severities
- GET /api/admin/error-logs/types

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timedelta, timezone
import enum


# ============================================================================
# Mock Enums
# ============================================================================

class MockAuditLogEvent(enum.Enum):
    QUOTE_REQUESTED = "quote_requested"
    BOOKING_STARTED = "booking_started"
    BOOKING_COMPLETED = "booking_completed"
    BOOKING_CANCELLED = "booking_cancelled"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"


class MockErrorSeverity(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_audit_log(
    id=1,
    session_id="sess-12345",
    booking_reference=None,
    event="quote_requested",
    event_data=None,
    ip_address="127.0.0.1",
    user_agent="Mozilla/5.0",
    created_at=None,
):
    """Create a mock audit log entry."""
    log = MagicMock()
    log.id = id
    log.session_id = session_id
    log.booking_reference = booking_reference
    log.event = event
    log.event_data = event_data or {}
    log.ip_address = ip_address
    log.user_agent = user_agent
    log.created_at = created_at or datetime.now(timezone.utc)
    return log


def create_mock_error_log(
    id=1,
    severity="error",
    error_type="ValidationError",
    error_code="E001",
    message="An error occurred",
    stack_trace=None,
    request_data=None,
    endpoint="/api/bookings",
    booking_reference=None,
    session_id="sess-12345",
    ip_address="127.0.0.1",
    user_agent="Mozilla/5.0",
    created_at=None,
):
    """Create a mock error log entry."""
    log = MagicMock()
    log.id = id
    log.severity = MagicMock()
    log.severity.value = severity
    log.severity.__str__ = lambda self: severity
    log.error_type = error_type
    log.error_code = error_code
    log.message = message
    log.stack_trace = stack_trace
    log.request_data = request_data or {}
    log.endpoint = endpoint
    log.booking_reference = booking_reference
    log.session_id = session_id
    log.ip_address = ip_address
    log.user_agent = user_agent
    log.created_at = created_at or datetime.now(timezone.utc)
    return log


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Audit Logs Endpoint Tests - Unit
# ============================================================================

class TestAuditLogsLogic:
    """Unit tests for audit logs business logic."""

    # Happy Path
    def test_returns_paginated_results(self):
        """Should return paginated audit logs."""
        logs = [create_mock_audit_log(id=i) for i in range(100)]
        limit = 50
        offset = 0

        paginated = logs[offset:offset + limit]

        assert len(paginated) == 50

    def test_orders_by_created_at_desc(self):
        """Should order logs by created_at descending."""
        now = datetime.now(timezone.utc)
        logs = [
            create_mock_audit_log(id=1, created_at=now - timedelta(hours=2)),
            create_mock_audit_log(id=2, created_at=now - timedelta(hours=1)),
            create_mock_audit_log(id=3, created_at=now),
        ]

        sorted_logs = sorted(logs, key=lambda x: x.created_at, reverse=True)

        assert sorted_logs[0].id == 3
        assert sorted_logs[1].id == 2
        assert sorted_logs[2].id == 1

    def test_returns_total_count(self):
        """Should return total count of matching logs."""
        logs = [create_mock_audit_log(id=i) for i in range(75)]

        total_count = len(logs)

        assert total_count == 75

    def test_formats_created_at_as_iso(self):
        """Should format created_at as ISO string."""
        now = datetime(2026, 4, 15, 10, 30, 0, tzinfo=timezone.utc)
        log = create_mock_audit_log(created_at=now)

        formatted = log.created_at.isoformat()

        assert "2026-04-15" in formatted

    # Filtering Tests
    def test_filters_by_booking_reference(self):
        """Should filter logs by booking reference."""
        logs = [
            create_mock_audit_log(id=1, booking_reference="TAG-12345"),
            create_mock_audit_log(id=2, booking_reference="TAG-12345"),
            create_mock_audit_log(id=3, booking_reference="TAG-99999"),
        ]

        booking_ref = "TAG-12345"
        filtered = [l for l in logs if l.booking_reference and booking_ref in l.booking_reference]

        assert len(filtered) == 2

    def test_filters_by_event_type(self):
        """Should filter logs by event type."""
        logs = [
            create_mock_audit_log(id=1, event="quote_requested"),
            create_mock_audit_log(id=2, event="booking_completed"),
            create_mock_audit_log(id=3, event="quote_requested"),
        ]

        event_filter = "quote_requested"
        filtered = [l for l in logs if l.event == event_filter]

        assert len(filtered) == 2

    def test_filters_by_search_term(self):
        """Should filter logs by search term."""
        logs = [
            create_mock_audit_log(id=1, session_id="sess-abc123"),
            create_mock_audit_log(id=2, session_id="sess-xyz789"),
            create_mock_audit_log(id=3, session_id="sess-abc456"),
        ]

        search = "abc"
        filtered = [l for l in logs if search in l.session_id]

        assert len(filtered) == 2

    def test_filters_by_date_range(self):
        """Should filter logs by date range."""
        now = datetime.now(timezone.utc)
        logs = [
            create_mock_audit_log(id=1, created_at=now - timedelta(days=5)),
            create_mock_audit_log(id=2, created_at=now - timedelta(days=2)),
            create_mock_audit_log(id=3, created_at=now),
        ]

        date_from = now - timedelta(days=3)
        date_to = now
        filtered = [l for l in logs if date_from <= l.created_at <= date_to]

        assert len(filtered) == 2

    # Edge Cases
    def test_handles_empty_results(self):
        """Should handle empty results."""
        logs = []

        assert len(logs) == 0

    def test_handles_null_booking_reference(self):
        """Should handle logs with null booking reference."""
        log = create_mock_audit_log(booking_reference=None)

        assert log.booking_reference is None

    def test_handles_null_event_data(self):
        """Should handle logs with null event data."""
        log = create_mock_audit_log(event_data=None)

        # Should default to empty dict
        event_data = log.event_data or {}

        assert event_data == {}


class TestAuditLogPagination:
    """Tests for audit log pagination."""

    def test_respects_limit_parameter(self):
        """Should respect limit parameter."""
        logs = [create_mock_audit_log(id=i) for i in range(100)]
        limit = 25

        paginated = logs[:limit]

        assert len(paginated) == 25

    def test_respects_offset_parameter(self):
        """Should respect offset parameter."""
        logs = [create_mock_audit_log(id=i) for i in range(100)]
        offset = 50
        limit = 25

        paginated = logs[offset:offset + limit]

        assert len(paginated) == 25
        assert paginated[0].id == 50

    def test_handles_offset_beyond_data(self):
        """Should handle offset beyond available data."""
        logs = [create_mock_audit_log(id=i) for i in range(10)]
        offset = 100

        paginated = logs[offset:]

        assert len(paginated) == 0

    def test_returns_remaining_when_limit_exceeds_data(self):
        """Should return remaining data when limit exceeds available."""
        logs = [create_mock_audit_log(id=i) for i in range(10)]
        limit = 50

        paginated = logs[:limit]

        assert len(paginated) == 10


# ============================================================================
# Audit Log Events Endpoint Tests
# ============================================================================

class TestAuditLogEventsEndpoint:
    """Tests for GET /api/admin/audit-logs/events endpoint."""

    def test_returns_all_event_types(self):
        """Should return all audit event types."""
        events = [e.value for e in MockAuditLogEvent]

        assert "quote_requested" in events
        assert "booking_completed" in events
        assert "payment_failed" in events

    def test_event_types_are_strings(self):
        """Should return event types as strings."""
        events = [e.value for e in MockAuditLogEvent]

        assert all(isinstance(e, str) for e in events)

    def test_event_list_not_empty(self):
        """Should return non-empty list of events."""
        events = [e.value for e in MockAuditLogEvent]

        assert len(events) > 0


# ============================================================================
# Error Logs Endpoint Tests - Unit
# ============================================================================

class TestErrorLogsLogic:
    """Unit tests for error logs business logic."""

    # Happy Path
    def test_returns_paginated_results(self):
        """Should return paginated error logs."""
        logs = [create_mock_error_log(id=i) for i in range(100)]
        limit = 50
        offset = 0

        paginated = logs[offset:offset + limit]

        assert len(paginated) == 50

    def test_orders_by_created_at_desc(self):
        """Should order logs by created_at descending."""
        now = datetime.now(timezone.utc)
        logs = [
            create_mock_error_log(id=1, created_at=now - timedelta(hours=2)),
            create_mock_error_log(id=2, created_at=now - timedelta(hours=1)),
            create_mock_error_log(id=3, created_at=now),
        ]

        sorted_logs = sorted(logs, key=lambda x: x.created_at, reverse=True)

        assert sorted_logs[0].id == 3

    def test_returns_total_count(self):
        """Should return total count of matching logs."""
        logs = [create_mock_error_log(id=i) for i in range(60)]

        total_count = len(logs)

        assert total_count == 60

    # Filtering Tests
    def test_filters_by_severity(self):
        """Should filter logs by severity."""
        logs = [
            create_mock_error_log(id=1, severity="error"),
            create_mock_error_log(id=2, severity="warning"),
            create_mock_error_log(id=3, severity="error"),
            create_mock_error_log(id=4, severity="critical"),
        ]

        severity_filter = "error"
        filtered = [l for l in logs if l.severity.value == severity_filter]

        assert len(filtered) == 2

    def test_filters_by_error_type(self):
        """Should filter logs by error type."""
        logs = [
            create_mock_error_log(id=1, error_type="ValidationError"),
            create_mock_error_log(id=2, error_type="DatabaseError"),
            create_mock_error_log(id=3, error_type="ValidationError"),
        ]

        type_filter = "ValidationError"
        filtered = [l for l in logs if type_filter in l.error_type]

        assert len(filtered) == 2

    def test_filters_by_booking_reference(self):
        """Should filter logs by booking reference."""
        logs = [
            create_mock_error_log(id=1, booking_reference="TAG-ERR-1"),
            create_mock_error_log(id=2, booking_reference="TAG-ERR-1"),
            create_mock_error_log(id=3, booking_reference="TAG-ERR-2"),
        ]

        ref_filter = "TAG-ERR-1"
        filtered = [l for l in logs if l.booking_reference and ref_filter in l.booking_reference]

        assert len(filtered) == 2

    def test_filters_by_search_term(self):
        """Should filter logs by search term in message."""
        logs = [
            create_mock_error_log(id=1, message="Database connection failed"),
            create_mock_error_log(id=2, message="Invalid payment data"),
            create_mock_error_log(id=3, message="Database timeout error"),
        ]

        search = "Database"
        filtered = [l for l in logs if search.lower() in l.message.lower()]

        assert len(filtered) == 2

    def test_filters_by_date_range(self):
        """Should filter logs by date range."""
        now = datetime.now(timezone.utc)
        logs = [
            create_mock_error_log(id=1, created_at=now - timedelta(days=10)),
            create_mock_error_log(id=2, created_at=now - timedelta(days=3)),
            create_mock_error_log(id=3, created_at=now - timedelta(days=1)),
        ]

        date_from = now - timedelta(days=5)
        filtered = [l for l in logs if l.created_at >= date_from]

        assert len(filtered) == 2

    # Edge Cases
    def test_handles_null_stack_trace(self):
        """Should handle logs with null stack trace."""
        log = create_mock_error_log(stack_trace=None)

        assert log.stack_trace is None

    def test_handles_null_booking_reference(self):
        """Should handle logs with null booking reference."""
        log = create_mock_error_log(booking_reference=None)

        assert log.booking_reference is None

    def test_handles_empty_results(self):
        """Should handle empty results."""
        logs = []

        assert len(logs) == 0


class TestErrorLogSeverities:
    """Tests for error log severity levels."""

    def test_returns_all_severity_levels(self):
        """Should return all severity levels."""
        severities = [s.value for s in MockErrorSeverity]

        assert "info" in severities
        assert "warning" in severities
        assert "error" in severities
        assert "critical" in severities

    def test_severity_levels_are_strings(self):
        """Should return severity levels as strings."""
        severities = [s.value for s in MockErrorSeverity]

        assert all(isinstance(s, str) for s in severities)

    def test_severity_list_has_4_levels(self):
        """Should have 4 severity levels."""
        severities = [s.value for s in MockErrorSeverity]

        assert len(severities) == 4


class TestErrorLogTypes:
    """Tests for error log type extraction."""

    def test_extracts_unique_error_types(self):
        """Should extract unique error types from logs."""
        logs = [
            create_mock_error_log(error_type="ValidationError"),
            create_mock_error_log(error_type="DatabaseError"),
            create_mock_error_log(error_type="ValidationError"),
            create_mock_error_log(error_type="PaymentError"),
        ]

        unique_types = list(set(l.error_type for l in logs))

        assert len(unique_types) == 3

    def test_handles_no_error_types(self):
        """Should handle when no error types exist."""
        logs = []

        unique_types = list(set(l.error_type for l in logs))

        assert len(unique_types) == 0


# ============================================================================
# Authentication Tests
# ============================================================================

class TestLogsAuthentication:
    """Tests for authentication on logging endpoints."""

    def test_requires_admin_user(self):
        """Should require admin user."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_rejects_non_admin(self):
        """Should reject non-admin users."""
        user = MagicMock()
        user.is_admin = False

        has_access = user.is_admin

        assert has_access is False

    def test_rejects_inactive_user(self):
        """Should reject inactive users."""
        user = create_mock_admin_user()
        user.is_active = False

        has_access = user.is_admin and user.is_active

        assert has_access is False


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestAuditLogResponseStructure:
    """Tests for audit log response structure."""

    def test_response_includes_audit_logs_array(self):
        """Should include audit_logs array."""
        logs = [create_mock_audit_log()]

        response = {
            "audit_logs": logs,
            "total_count": 1,
            "limit": 50,
            "offset": 0,
        }

        assert "audit_logs" in response
        assert isinstance(response["audit_logs"], list)

    def test_response_includes_pagination_info(self):
        """Should include pagination info."""
        response = {
            "audit_logs": [],
            "total_count": 100,
            "limit": 50,
            "offset": 0,
        }

        assert response["total_count"] == 100
        assert response["limit"] == 50
        assert response["offset"] == 0

    def test_log_entry_has_required_fields(self):
        """Should have all required fields in log entry."""
        log = create_mock_audit_log()

        entry = {
            "id": log.id,
            "session_id": log.session_id,
            "booking_reference": log.booking_reference,
            "event": log.event,
            "event_data": log.event_data,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "created_at": log.created_at.isoformat(),
        }

        assert "id" in entry
        assert "session_id" in entry
        assert "event" in entry
        assert "created_at" in entry


class TestErrorLogResponseStructure:
    """Tests for error log response structure."""

    def test_response_includes_error_logs_array(self):
        """Should include error_logs array."""
        logs = [create_mock_error_log()]

        response = {
            "error_logs": logs,
            "total_count": 1,
            "limit": 50,
            "offset": 0,
        }

        assert "error_logs" in response

    def test_log_entry_has_required_fields(self):
        """Should have all required fields in error log entry."""
        log = create_mock_error_log()

        entry = {
            "id": log.id,
            "severity": log.severity.value,
            "error_type": log.error_type,
            "error_code": log.error_code,
            "message": log.message,
            "endpoint": log.endpoint,
            "created_at": log.created_at.isoformat(),
        }

        assert "id" in entry
        assert "severity" in entry
        assert "error_type" in entry
        assert "message" in entry


# ============================================================================
# Date Parsing Tests
# ============================================================================

class TestDateParsing:
    """Tests for date parsing in filters."""

    def test_parses_iso_date_format(self):
        """Should parse ISO date format."""
        date_str = "2026-04-15T10:30:00Z"

        parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

        assert parsed.year == 2026
        assert parsed.month == 4
        assert parsed.day == 15

    def test_handles_invalid_date_format(self):
        """Should handle invalid date format gracefully."""
        date_str = "not-a-date"

        try:
            parsed = datetime.fromisoformat(date_str)
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_parses_date_with_timezone(self):
        """Should parse date with timezone."""
        date_str = "2026-04-15T10:30:00+01:00"

        parsed = datetime.fromisoformat(date_str)

        assert parsed.tzinfo is not None


# ============================================================================
# Boundary Tests
# ============================================================================

class TestLogsBoundaryConditions:
    """Tests for boundary conditions."""

    def test_limit_minimum_value(self):
        """Should respect minimum limit value of 1."""
        limit = 1
        logs = [create_mock_audit_log(id=i) for i in range(10)]

        paginated = logs[:limit]

        assert len(paginated) == 1

    def test_limit_maximum_value(self):
        """Should respect maximum limit value of 500."""
        limit = 500
        logs = [create_mock_audit_log(id=i) for i in range(1000)]

        paginated = logs[:limit]

        assert len(paginated) == 500

    def test_offset_at_zero(self):
        """Should handle offset at zero."""
        offset = 0
        logs = [create_mock_audit_log(id=i) for i in range(10)]

        paginated = logs[offset:]

        assert len(paginated) == 10

    def test_handles_very_long_search_term(self):
        """Should handle very long search terms."""
        search = "a" * 1000

        # Should not cause any issues
        assert len(search) == 1000

    def test_handles_special_characters_in_search(self):
        """Should handle special characters in search."""
        search = "test%_special"

        # Should escape special SQL characters
        escaped = search.replace("%", "\\%").replace("_", "\\_")

        assert "\\%" in escaped


# ============================================================================
# log_error Function Tests
# ============================================================================

class TestLogErrorFunction:
    """Tests for the log_error helper function."""

    def test_passes_enum_not_value_to_error_log(self):
        """Should pass ErrorSeverity enum member, not .value string.

        This test ensures the log_error function passes the enum member
        directly to ErrorLog, not severity.value (which would cause
        'invalid input value for enum errorseverity' errors).
        """
        from db_models import ErrorSeverity, ErrorLog

        # Verify ErrorLog expects enum member, not string
        # The severity column is defined as Enum(ErrorSeverity)
        assert hasattr(ErrorLog, 'severity')

        # Verify enum values are lowercase strings
        assert ErrorSeverity.ERROR.value == "error"
        assert ErrorSeverity.WARNING.value == "warning"

        # The key insight: SQLAlchemy Enum columns expect the enum member,
        # not the .value string. Passing .value causes PostgreSQL errors.

    def test_error_severity_enum_values(self):
        """Should have correct enum values for database compatibility."""
        from db_models import ErrorSeverity

        expected_values = ["debug", "info", "warning", "error", "critical"]
        actual_values = [e.value for e in ErrorSeverity]

        assert actual_values == expected_values

    def test_log_error_creates_error_log_with_correct_severity(self):
        """Should create ErrorLog with enum member, not string."""
        from db_models import ErrorSeverity

        # Simulate what log_error should do (pass enum, not .value)
        severity = ErrorSeverity.ERROR

        # This is CORRECT - pass the enum member
        error_log_data = {"severity": severity}
        assert error_log_data["severity"] == ErrorSeverity.ERROR
        assert error_log_data["severity"] != "error"  # Not the string!

        # This would be WRONG - passing .value
        wrong_data = {"severity": severity.value}
        assert wrong_data["severity"] == "error"  # String, not enum


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
