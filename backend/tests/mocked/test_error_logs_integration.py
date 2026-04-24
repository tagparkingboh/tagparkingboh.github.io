"""
REAL Mocked Integration tests for Error Logs endpoints.

These tests actually import and execute code from main.py, increasing coverage.
Only the database and auth are mocked - the endpoint logic runs for real.

This is the CORRECT way to write mocked integration tests.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Import the REAL app - this is what makes it an integration test
from main import app, get_db, require_admin
from db_models import ErrorLog, ErrorSeverity


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_error_log(
    id=1,
    severity=ErrorSeverity.ERROR,
    error_type="api_error",
    error_code="500",
    message="Test error message",
    stack_trace=None,
    request_data=None,
    endpoint="/api/test",
    booking_reference=None,
    session_id=None,
    ip_address="127.0.0.1",
    user_agent="TestClient",
    created_at=None,
):
    """Create a mock error log that matches the real ErrorLog model."""
    log = MagicMock(spec=ErrorLog)
    log.id = id
    log.severity = severity
    log.error_type = error_type
    log.error_code = error_code
    log.message = message
    log.stack_trace = stack_trace
    log.request_data = request_data
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
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return create_mock_admin_user()


@pytest.fixture
def client(mock_db, mock_admin):
    """Create a test client with mocked dependencies."""
    # Override the database dependency
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    # Override the admin auth dependency
    async def override_require_admin():
        return mock_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_require_admin

    with TestClient(app) as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.clear()


# ============================================================================
# GET /api/admin/error-logs Tests
# ============================================================================

class TestGetErrorLogsEndpoint:
    """Integration tests for GET /api/admin/error-logs."""

    def test_returns_200_with_empty_logs(self, client, mock_db):
        """Should return 200 with empty list when no logs exist."""
        # Setup mock query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs")

        assert response.status_code == 200
        data = response.json()
        assert "error_logs" in data or "logs" in data or isinstance(data, list)

    def test_returns_error_logs_list(self, client, mock_db):
        """Should return list of error logs."""
        logs = [
            create_mock_error_log(id=1, error_type="api_error"),
            create_mock_error_log(id=2, error_type="validation_error"),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = len(logs)
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs")

        assert response.status_code == 200

    def test_filters_by_severity(self, client, mock_db):
        """Should filter by severity parameter."""
        logs = [create_mock_error_log(severity=ErrorSeverity.ERROR)]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs?severity=error")

        assert response.status_code == 200

    def test_filters_by_error_type(self, client, mock_db):
        """Should filter by error_type parameter."""
        logs = [create_mock_error_log(error_type="stripe")]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs?error_type=stripe")

        assert response.status_code == 200

    def test_pagination_with_limit(self, client, mock_db):
        """Should respect limit parameter."""
        logs = [create_mock_error_log(id=i) for i in range(5)]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 100
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs?limit=5")

        assert response.status_code == 200

    def test_pagination_with_offset(self, client, mock_db):
        """Should respect offset parameter."""
        logs = [create_mock_error_log(id=i) for i in range(10, 15)]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 100
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs?offset=10&limit=5")

        assert response.status_code == 200


# ============================================================================
# GET /api/admin/error-logs/severities Tests
# ============================================================================

class TestGetErrorSeveritiesEndpoint:
    """Integration tests for GET /api/admin/error-logs/severities."""

    def test_returns_severity_list(self, client, mock_db):
        """Should return list of severity levels."""
        response = client.get("/api/admin/error-logs/severities")

        # This endpoint should return the enum values
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "severities" in data


# ============================================================================
# GET /api/admin/error-logs/types Tests
# ============================================================================

class TestGetErrorTypesEndpoint:
    """Integration tests for GET /api/admin/error-logs/types."""

    def test_returns_error_types_list(self, client, mock_db):
        """Should return list of distinct error types."""
        mock_query = MagicMock()
        mock_query.distinct.return_value = mock_query
        mock_query.all.return_value = [("api_error",), ("validation_error",), ("stripe",)]
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/error-logs/types")

        assert response.status_code == 200


# ============================================================================
# Authentication Tests
# ============================================================================

class TestErrorLogsAuthentication:
    """Integration tests for authentication on error logs endpoints."""

    def test_rejects_unauthenticated_request(self, mock_db):
        """Should reject request without authentication."""
        # Clear any existing overrides
        app.dependency_overrides.clear()

        # Override only the database, not auth
        def override_get_db():
            try:
                yield mock_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.get("/api/admin/error-logs")
            # Should return 401 or 403 without auth
            assert response.status_code in [401, 403, 422]

        app.dependency_overrides.clear()


class TestLogErrorSeverityEnumSerialization:
    """Regression guard for the errorseverity enum serialization bug.

    Bug: ErrorLog.severity column was declared as Column(Enum(ErrorSeverity))
    without values_callable, so SQLAlchemy sent enum names (uppercase, e.g.
    'WARNING') to Postgres while the errorseverity enum type only accepts
    lowercase values. Every insert raised InvalidTextRepresentation, which
    log_error()'s try/except swallowed — silently dropping all error logs
    for ~12 days before detection.

    This test inserts a real ErrorLog via log_error() against a real DB and
    asserts the row is retrievable. If the column serialization breaks again,
    this fails loudly.
    """

    def test_log_error_inserts_row_with_warning_severity(self, db_session):
        """log_error must actually persist a row — not silently swallow exceptions."""
        from main import log_error

        marker = f"regression_probe_{datetime.now(timezone.utc).isoformat()}"
        log_error(
            db=db_session,
            error_type="regression_probe",
            message=marker,
            severity=ErrorSeverity.WARNING,
        )

        row = (
            db_session.query(ErrorLog)
            .filter(ErrorLog.message == marker)
            .one_or_none()
        )
        assert row is not None, "log_error silently failed — row did not land in error_logs"
        assert row.severity == ErrorSeverity.WARNING

        db_session.delete(row)
        db_session.commit()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
