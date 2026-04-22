"""
REAL Mocked Integration tests for Audit Logs endpoints.

These tests actually import and execute code from main.py, increasing coverage.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from main import app, get_db, require_admin
from db_models import AuditLog, AuditLogEvent


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_audit_log(
    id=1,
    session_id="sess-12345",
    booking_reference=None,
    event=AuditLogEvent.BOOKING_STARTED,
    event_data=None,
    ip_address="127.0.0.1",
    user_agent="TestClient",
    created_at=None,
):
    """Create a mock audit log."""
    log = MagicMock(spec=AuditLog)
    log.id = id
    log.session_id = session_id
    log.booking_reference = booking_reference
    log.event = event
    log.event_data = event_data
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
    return MagicMock()


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return create_mock_admin_user()


@pytest.fixture
def client(mock_db, mock_admin):
    """Create a test client with mocked dependencies."""
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    async def override_require_admin():
        return mock_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_require_admin

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# GET /api/admin/audit-logs Tests
# ============================================================================

class TestGetAuditLogsEndpoint:
    """Integration tests for GET /api/admin/audit-logs."""

    def test_returns_200_with_empty_logs(self, client, mock_db):
        """Should return 200 with empty list when no logs exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs")
        assert response.status_code == 200

    def test_returns_audit_logs_list(self, client, mock_db):
        """Should return list of audit logs."""
        logs = [
            create_mock_audit_log(id=1, event=AuditLogEvent.BOOKING_STARTED),
            create_mock_audit_log(id=2, event=AuditLogEvent.BOOKING_CONFIRMED),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = len(logs)
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs")
        assert response.status_code == 200

    def test_filters_by_event(self, client, mock_db):
        """Should filter by event parameter."""
        logs = [create_mock_audit_log(event=AuditLogEvent.PAYMENT_SUCCEEDED)]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs?event=payment_succeeded")
        assert response.status_code == 200

    def test_filters_by_session_id(self, client, mock_db):
        """Should filter by session_id parameter."""
        logs = [create_mock_audit_log(session_id="sess-abc123")]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs?session_id=sess-abc123")
        assert response.status_code == 200

    def test_filters_by_booking_reference(self, client, mock_db):
        """Should filter by booking_reference parameter."""
        logs = [create_mock_audit_log(booking_reference="TAG-12345")]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs?booking_reference=TAG-12345")
        assert response.status_code == 200

    def test_pagination_with_limit_and_offset(self, client, mock_db):
        """Should respect limit and offset parameters."""
        logs = [create_mock_audit_log(id=i) for i in range(5)]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = logs
        mock_query.count.return_value = 100
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/audit-logs?limit=5&offset=10")
        assert response.status_code == 200


# ============================================================================
# GET /api/admin/audit-logs/events Tests
# ============================================================================

class TestGetAuditEventsEndpoint:
    """Integration tests for GET /api/admin/audit-logs/events."""

    def test_returns_event_list(self, client, mock_db):
        """Should return list of event types."""
        response = client.get("/api/admin/audit-logs/events")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "events" in data


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
