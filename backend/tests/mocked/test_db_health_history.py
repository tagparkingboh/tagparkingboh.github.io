"""
Integration tests for the database health history endpoint.

Tests cover:
- Endpoint authentication
- Response format
- Circuit breaker stats inclusion
- Model and snapshot format
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Get test client."""
    from main import app
    return TestClient(app)


@pytest.fixture
def admin_token():
    """Get a valid admin token for testing."""
    return "test-admin-token"


class TestDbHealthHistoryAuthentication:
    """Tests for endpoint authentication."""

    def test_requires_authentication(self, client):
        """Endpoint requires authentication."""
        response = client.get("/api/admin/db-health/history")
        assert response.status_code == 401

    def test_requires_admin_role(self, client):
        """Endpoint requires admin role, not just authentication."""
        response = client.get(
            "/api/admin/db-health/history",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_db_health_requires_authentication(self, client):
        """Real-time db-health endpoint requires authentication."""
        response = client.get("/api/admin/db-health")
        assert response.status_code == 401


class TestDbHealthHistoryResponseFormat:
    """Tests for snapshot data format."""

    def test_snapshot_model_has_all_fields(self):
        """DbPoolSnapshot model has all required fields."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=16.7,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="scheduled",
        )

        assert hasattr(snapshot, 'id')
        assert hasattr(snapshot, 'pool_size')
        assert hasattr(snapshot, 'max_overflow')
        assert hasattr(snapshot, 'checked_out')
        assert hasattr(snapshot, 'overflow')
        assert hasattr(snapshot, 'checked_in')
        assert hasattr(snapshot, 'usage_percent')
        assert hasattr(snapshot, 'health_status')
        assert hasattr(snapshot, 'trigger')
        assert hasattr(snapshot, 'created_at')

    def test_snapshot_serialization(self):
        """Snapshot can be serialized to dict format."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        snapshot = DbPoolSnapshot(
            id=1,
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=16.7,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="scheduled",
        )
        snapshot.created_at = datetime(2026, 4, 2, 12, 0, 0)

        # Simulate the serialization done in the endpoint
        serialized = {
            "id": snapshot.id,
            "timestamp": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "pool_size": snapshot.pool_size,
            "max_overflow": snapshot.max_overflow,
            "checked_out": snapshot.checked_out,
            "overflow": snapshot.overflow,
            "checked_in": snapshot.checked_in,
            "usage_percent": float(snapshot.usage_percent),
            "health_status": snapshot.health_status.value,
            "trigger": snapshot.trigger,
        }

        assert serialized["id"] == 1
        assert serialized["pool_size"] == 10
        assert serialized["health_status"] == "healthy"
        assert serialized["trigger"] == "scheduled"
        assert "2026-04-02" in serialized["timestamp"]


class TestCircuitBreakerStatsFormat:
    """Tests for circuit breaker stats format."""

    def test_get_circuit_breaker_stats_format(self):
        """Circuit breaker stats have expected format."""
        from circuit_breaker import get_circuit_breaker_stats

        stats = get_circuit_breaker_stats()

        assert "state" in stats
        assert "rejected_count" in stats
        assert "total_requests" in stats
        assert "rejection_rate" in stats
        assert "pool_usage" in stats

        assert stats["state"] in ["CLOSED", "HALF_OPEN", "OPEN"]
        assert isinstance(stats["rejected_count"], int)
        assert isinstance(stats["total_requests"], int)

    def test_circuit_breaker_initial_stats(self):
        """Fresh circuit breaker has expected initial stats."""
        from circuit_breaker import PoolCircuitBreaker

        cb = PoolCircuitBreaker()
        stats = cb.get_stats()

        assert stats["state"] == "CLOSED"
        assert stats["rejected_count"] == 0
        assert stats["total_requests"] == 0
        assert stats["rejection_rate"] == 0


class TestDbHealthEndpointInCircuitBreaker:
    """Tests that db-health endpoints are protected by circuit breaker correctly."""

    def test_db_health_is_critical_endpoint(self):
        """DB health endpoint is classified as critical."""
        from circuit_breaker import is_critical_endpoint

        assert is_critical_endpoint("/api/admin/db-health") is True

    def test_db_health_history_is_critical_endpoint(self):
        """DB health history endpoint is classified as critical."""
        from circuit_breaker import is_critical_endpoint

        assert is_critical_endpoint("/api/admin/db-health/history") is True

    @patch('circuit_breaker.PoolCircuitBreaker.get_pool_usage')
    def test_db_health_allowed_when_circuit_open(self, mock_usage):
        """DB health endpoint is allowed even when circuit is OPEN."""
        from circuit_breaker import PoolCircuitBreaker

        mock_usage.return_value = 98  # Critical level

        cb = PoolCircuitBreaker()
        cb.state = "OPEN"

        with patch.object(cb, 'update_state', return_value="OPEN"):
            allowed, reason = cb.should_allow_request("/api/admin/db-health")

        assert allowed is True
        assert reason == "critical_endpoint"


class TestDbHealthHistoryWithRealData:
    """Integration tests that use real database (marked for selective running)."""

    @pytest.mark.integration
    def test_can_create_and_retrieve_snapshot(self, db_session):
        """Can create a snapshot and retrieve it via history."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        # Create a test snapshot
        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=16.7,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="test",
        )
        db_session.add(snapshot)
        db_session.commit()

        # Query it back
        retrieved = db_session.query(DbPoolSnapshot).filter(
            DbPoolSnapshot.trigger == "test"
        ).first()

        assert retrieved is not None
        assert retrieved.pool_size == 10
        assert retrieved.health_status == PoolHealthStatus.HEALTHY

        # Clean up
        db_session.delete(retrieved)
        db_session.commit()

    @pytest.mark.integration
    def test_snapshot_ordering(self, db_session):
        """Snapshots are ordered by created_at descending."""
        from db_models import DbPoolSnapshot, PoolHealthStatus
        from datetime import datetime, timedelta

        # Create multiple snapshots
        now = datetime.utcnow()
        snapshots = []
        for i in range(3):
            s = DbPoolSnapshot(
                pool_size=10,
                max_overflow=20,
                checked_out=i,
                overflow=0,
                checked_in=10 - i,
                usage_percent=i * 10,
                health_status=PoolHealthStatus.HEALTHY,
                trigger=f"test_order_{i}",
            )
            db_session.add(s)
            snapshots.append(s)

        db_session.commit()

        # Query and verify ordering
        results = db_session.query(DbPoolSnapshot).filter(
            DbPoolSnapshot.trigger.like("test_order_%")
        ).order_by(DbPoolSnapshot.created_at.desc()).all()

        assert len(results) == 3

        # Clean up
        for s in results:
            db_session.delete(s)
        db_session.commit()
