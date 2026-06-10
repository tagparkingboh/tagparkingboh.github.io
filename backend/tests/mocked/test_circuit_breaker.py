"""
Unit tests for the database connection pool circuit breaker.

Tests cover:
- Circuit breaker state transitions (CLOSED -> HALF_OPEN -> OPEN)
- Request filtering based on endpoint criticality
- Snapshot recording on state changes
- Middleware integration
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json


class TestPoolCircuitBreakerStates:
    """Tests for circuit breaker state management."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        from circuit_breaker import PoolCircuitBreaker
        cb = PoolCircuitBreaker()
        assert cb.state == "CLOSED"

    def test_state_remains_closed_when_usage_below_threshold(self):
        """State stays CLOSED when pool usage is below 70%."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        state = cb.update_state(50)

        assert state == "CLOSED"
        assert cb.state == "CLOSED"

    def test_state_changes_to_half_open_at_85_percent(self):
        """State changes to HALF_OPEN when usage hits 85%."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        with patch.object(cb, '_record_snapshot'):  # Don't actually record
            state = cb.update_state(85)

        assert state == "HALF_OPEN"
        assert cb.state == "HALF_OPEN"

    def test_state_changes_to_open_at_95_percent(self):
        """State changes to OPEN when usage hits 95%."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        with patch.object(cb, '_record_snapshot'):
            state = cb.update_state(95)

        assert state == "OPEN"
        assert cb.state == "OPEN"

    def test_state_recovers_from_open_to_closed(self):
        """State recovers from OPEN to CLOSED when usage drops."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        cb.state = "OPEN"  # Start in OPEN state

        with patch.object(cb, '_record_snapshot'):
            state = cb.update_state(30)  # Pool recovered

        assert state == "CLOSED"
        assert cb.state == "CLOSED"


class TestEndpointClassification:
    """Tests for endpoint criticality classification."""

    def test_health_endpoint_is_critical(self):
        """Health check endpoint should always be allowed."""
        from circuit_breaker import is_critical_endpoint
        assert is_critical_endpoint("/api/health") is True

    def test_db_health_endpoint_is_critical(self):
        """DB health monitoring endpoint should always be allowed."""
        from circuit_breaker import is_critical_endpoint
        assert is_critical_endpoint("/api/admin/db-health") is True

    def test_db_health_history_endpoint_is_critical(self):
        """DB health history endpoint should always be allowed."""
        from circuit_breaker import is_critical_endpoint
        assert is_critical_endpoint("/api/admin/db-health/history") is True

    def test_regular_endpoint_is_not_critical(self):
        """Regular API endpoints are not critical."""
        from circuit_breaker import is_critical_endpoint
        assert is_critical_endpoint("/api/bookings") is False
        assert is_critical_endpoint("/api/customers") is False

    def test_admin_endpoints_are_high_priority(self):
        """Admin endpoints are high priority."""
        from circuit_breaker import is_high_priority_endpoint
        assert is_high_priority_endpoint("/api/admin/bookings") is True
        assert is_high_priority_endpoint("/api/admin/customers") is True

    def test_auth_endpoints_are_high_priority(self):
        """Auth endpoints are high priority."""
        from circuit_breaker import is_high_priority_endpoint
        assert is_high_priority_endpoint("/api/auth/login") is True
        assert is_high_priority_endpoint("/api/auth/logout") is True


class TestRequestFiltering:
    """Tests for request allow/reject logic."""

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_allows_all_requests_when_closed(self, mock_usage):
        """All requests allowed when circuit is CLOSED."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 30

        cb = PoolCircuitBreaker()

        allowed, reason = cb.should_allow_request("/api/bookings")
        assert allowed is True
        assert reason == "circuit_closed"

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_allows_critical_endpoints_when_open(self, mock_usage):
        """Critical endpoints allowed even when circuit is OPEN."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 98

        cb = PoolCircuitBreaker()
        cb.state = "OPEN"

        with patch.object(cb, 'update_state', return_value="OPEN"):
            allowed, reason = cb.should_allow_request("/api/admin/db-health")

        assert allowed is True
        assert reason == "critical_endpoint"

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_rejects_regular_endpoints_when_half_open(self, mock_usage):
        """Regular endpoints rejected when circuit is HALF_OPEN."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 87

        cb = PoolCircuitBreaker()

        with patch.object(cb, 'update_state', return_value="HALF_OPEN"):
            cb.state = "HALF_OPEN"
            allowed, reason = cb.should_allow_request("/api/bookings")

        assert allowed is False
        assert "circuit_half_open" in reason

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_allows_high_priority_when_half_open(self, mock_usage):
        """High priority endpoints allowed when circuit is HALF_OPEN."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 87

        cb = PoolCircuitBreaker()

        with patch.object(cb, 'update_state', return_value="HALF_OPEN"):
            cb.state = "HALF_OPEN"
            allowed, reason = cb.should_allow_request("/api/admin/bookings")

        assert allowed is True
        assert reason == "high_priority"

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_tracks_rejected_count(self, mock_usage):
        """Circuit breaker tracks number of rejected requests."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 90

        cb = PoolCircuitBreaker()
        cb.state = "HALF_OPEN"

        with patch.object(cb, 'update_state', return_value="HALF_OPEN"):
            cb.should_allow_request("/api/bookings")
            cb.should_allow_request("/api/customers")
            cb.should_allow_request("/api/vehicles")

        assert cb.rejected_count == 3

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_allows_high_priority_during_open_with_emergency_reason(self, mock_usage):
        """High-priority admin/auth paths are allowed during OPEN with warning."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 98

        cb = PoolCircuitBreaker()
        with patch.object(cb, 'update_state', return_value="OPEN"):
            cb.state = "OPEN"
            allowed, reason = cb.should_allow_request("/api/auth/login")

        assert allowed is True
        assert reason == "high_priority_emergency"

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_rejects_regular_endpoints_when_open(self, mock_usage):
        """Regular paths are rejected when the circuit is fully OPEN."""
        from circuit_breaker import PoolCircuitBreaker
        mock_usage.return_value = 96

        cb = PoolCircuitBreaker()
        with patch.object(cb, 'update_state', return_value="OPEN"):
            cb.state = "OPEN"
            allowed, reason = cb.should_allow_request("/api/bookings")

        assert allowed is False
        assert "circuit_open" in reason


class TestSnapshotRecording:
    """Tests for pool snapshot recording on state changes."""

    @patch('database.SessionLocal')
    @patch('database.get_pool_status')
    def test_records_snapshot_on_state_change(self, mock_status, mock_session):
        """Snapshot is recorded when state changes."""
        from circuit_breaker import PoolCircuitBreaker

        mock_status.return_value = {
            "pool_size": 10,
            "max_overflow": 20,
            "checked_out": 25,
            "overflow": 5,
            "checked_in": 0,
            "usage_percent": 85,
        }

        mock_db = MagicMock()
        mock_session.return_value = mock_db

        cb = PoolCircuitBreaker()
        cb._record_snapshot(85)

        # Verify snapshot was added to database
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch('database.SessionLocal')
    @patch('database.get_pool_status')
    def test_snapshot_has_correct_health_status_warning(self, mock_status, mock_session):
        """Snapshot records WARNING status for 70-90% usage."""
        from circuit_breaker import PoolCircuitBreaker
        from db_models import PoolHealthStatus

        mock_status.return_value = {
            "pool_size": 10,
            "max_overflow": 20,
            "checked_out": 20,
            "overflow": 5,
            "checked_in": 5,
            "usage_percent": 75,
        }

        mock_db = MagicMock()
        mock_session.return_value = mock_db

        cb = PoolCircuitBreaker()
        cb._record_snapshot(75)

        # Get the snapshot that was added
        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.WARNING
        assert snapshot.trigger == "warning"

    @patch('database.SessionLocal')
    @patch('database.get_pool_status')
    def test_snapshot_has_correct_health_status_critical(self, mock_status, mock_session):
        """Snapshot records CRITICAL status for 90%+ usage."""
        from circuit_breaker import PoolCircuitBreaker
        from db_models import PoolHealthStatus

        mock_status.return_value = {
            "pool_size": 10,
            "max_overflow": 20,
            "checked_out": 27,
            "overflow": 3,
            "checked_in": 0,
            "usage_percent": 95,
        }

        mock_db = MagicMock()
        mock_session.return_value = mock_db

        cb = PoolCircuitBreaker()
        cb._record_snapshot(95)

        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.CRITICAL
        assert snapshot.trigger == "critical"

    @patch('database.SessionLocal')
    @patch('database.get_pool_status')
    def test_snapshot_has_correct_health_status_recovery(self, mock_status, mock_session):
        """Snapshot records HEALTHY recovery status below warning threshold."""
        from circuit_breaker import PoolCircuitBreaker
        from db_models import PoolHealthStatus

        mock_status.return_value = {
            "pool_size": 10,
            "max_overflow": 20,
            "checked_out": 1,
            "overflow": 0,
            "checked_in": 9,
            "usage_percent": 10,
        }
        mock_db = MagicMock()
        mock_session.return_value = mock_db

        cb = PoolCircuitBreaker()
        cb._record_snapshot(10)

        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.HEALTHY
        assert snapshot.trigger == "recovery"

    @patch('database.SessionLocal')
    @patch('database.get_pool_status')
    def test_snapshot_failure_is_swallowed(self, mock_status, mock_session):
        """Snapshot errors should not propagate into request handling."""
        from circuit_breaker import PoolCircuitBreaker

        mock_status.side_effect = RuntimeError("pool unavailable")
        cb = PoolCircuitBreaker()

        cb._record_snapshot(80)

        mock_session.assert_not_called()


class TestPoolUsageFailure:
    """Tests for defensive pool-status handling."""

    @patch('database.get_pool_status')
    def test_get_pool_usage_returns_zero_when_database_check_fails(self, mock_status):
        from circuit_breaker import PoolCircuitBreaker

        mock_status.side_effect = RuntimeError("database down")
        cb = PoolCircuitBreaker()

        assert cb.get_pool_usage() == 0


class TestCircuitBreakerStats:
    """Tests for circuit breaker statistics."""

    def test_get_stats_returns_all_fields(self):
        """Stats include all expected fields."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        cb.rejected_count = 5
        cb.total_requests = 100

        stats = cb.get_stats()

        assert "state" in stats
        assert "last_state_change" in stats
        assert "rejected_count" in stats
        assert "total_requests" in stats
        assert "rejection_rate" in stats
        assert stats["rejected_count"] == 5
        assert stats["total_requests"] == 100
        assert stats["rejection_rate"] == 5.0

    def test_rejection_rate_zero_when_no_requests(self):
        """Rejection rate is 0 when no requests processed."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        stats = cb.get_stats()

        assert stats["rejection_rate"] == 0


class TestCircuitBreakerMiddleware:
    """Integration tests for the FastAPI middleware."""

    @pytest.mark.asyncio
    @patch('circuit_breaker.circuit_breaker')
    async def test_middleware_allows_request_when_permitted(self, mock_cb):
        """Middleware calls next when request is allowed."""
        from circuit_breaker import CircuitBreakerMiddleware

        mock_cb.should_allow_request.return_value = (True, "circuit_closed")

        middleware = CircuitBreakerMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.url.path = "/api/bookings"

        mock_response = MagicMock()
        mock_call_next = MagicMock(return_value=mock_response)

        # Make call_next awaitable
        async def async_call_next(request):
            return mock_response

        result = await middleware.dispatch(mock_request, async_call_next)

        assert result == mock_response

    @pytest.mark.asyncio
    @patch('circuit_breaker.circuit_breaker')
    async def test_middleware_returns_503_when_rejected(self, mock_cb):
        """Middleware returns 503 when request is rejected."""
        from circuit_breaker import CircuitBreakerMiddleware
        from fastapi.responses import JSONResponse

        mock_cb.should_allow_request.return_value = (False, "circuit_open (pool at 95%)")

        middleware = CircuitBreakerMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.url.path = "/api/bookings"

        async def async_call_next(request):
            return MagicMock()

        result = await middleware.dispatch(mock_request, async_call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 503
        assert result.headers["retry-after"] == "5"
        body = json.loads(result.body.decode())
        assert body["retry_after"] == 5
        assert "high load" in body["detail"]

    @pytest.mark.asyncio
    @patch('circuit_breaker.circuit_breaker')
    async def test_middleware_skips_non_api_paths(self, mock_cb):
        """Middleware skips non-API paths like static files."""
        from circuit_breaker import CircuitBreakerMiddleware

        middleware = CircuitBreakerMiddleware(app=MagicMock())

        mock_request = MagicMock()
        mock_request.url.path = "/static/style.css"

        mock_response = MagicMock()

        async def async_call_next(request):
            return mock_response

        result = await middleware.dispatch(mock_request, async_call_next)

        # Should not call should_allow_request for non-API paths
        mock_cb.should_allow_request.assert_not_called()
        assert result == mock_response


class TestGetCircuitBreakerStats:
    """Tests for the stats helper function."""

    @patch('circuit_breaker.circuit_breaker')
    def test_get_circuit_breaker_stats_includes_pool_usage(self, mock_cb):
        """Stats include current pool usage."""
        from circuit_breaker import get_circuit_breaker_stats

        mock_cb.get_stats.return_value = {
            "state": "CLOSED",
            "rejected_count": 0,
            "total_requests": 50,
            "rejection_rate": 0,
        }
        mock_cb.get_pool_usage.return_value = 45.5

        stats = get_circuit_breaker_stats()

        assert "pool_usage" in stats
        assert stats["pool_usage"] == 45.5
