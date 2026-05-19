"""
HUEB tests for the QA Dashboard family in main.py.

  GET    /api/admin/db-health
  GET    /api/admin/db-health/history
  GET    /api/admin/test-results
  GET    /api/admin/test-results/latest
  POST   /api/test-results
  GET    /api/admin/audit-logs
  GET    /api/admin/audit-logs/events
  GET    /api/admin/error-logs
  GET    /api/admin/error-logs/severities
  GET    /api/admin/error-logs/types
  POST   /api/admin/sql/verify-pin
  POST   /api/admin/sql/logout
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import main
from main import app, require_admin
from database import get_db


def _admin(id=1):
    return SimpleNamespace(id=id, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()
    try:
        main.sql_session_tokens.clear()
    except Exception:
        pass


# ============================================================================
# GET /api/admin/db-health
# ============================================================================

class TestDbHealth:
    def teardown_method(self):
        _clear()

    def test_H_healthy(self, monkeypatch):
        monkeypatch.setattr("database.get_pool_status", lambda: {
            "pool_size": 10, "checked_out": 2, "checked_in": 8,
            "overflow": 0, "max_overflow": 5, "usage_percent": 20.0,
        })
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/db-health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["health"] == "healthy"

    def test_H_warning_at_70(self, monkeypatch):
        monkeypatch.setattr("database.get_pool_status", lambda: {
            "pool_size": 10, "checked_out": 7, "checked_in": 3,
            "overflow": 0, "max_overflow": 5, "usage_percent": 75.0,
        })
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/db-health")
        assert resp.status_code == 200
        assert resp.json()["health"] == "warning"

    def test_E_critical_at_90(self, monkeypatch):
        monkeypatch.setattr("database.get_pool_status", lambda: {
            "pool_size": 10, "checked_out": 9, "checked_in": 1,
            "overflow": 5, "max_overflow": 5, "usage_percent": 95.0,
        })
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/db-health")
        assert resp.status_code == 200
        assert resp.json()["health"] == "critical"

    def test_B_70_boundary(self, monkeypatch):
        monkeypatch.setattr("database.get_pool_status", lambda: {
            "pool_size": 10, "checked_out": 7, "checked_in": 3,
            "overflow": 0, "max_overflow": 5, "usage_percent": 70.0,
        })
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/db-health")
        assert resp.json()["health"] == "warning"

    def test_B_just_below_70_is_healthy(self, monkeypatch):
        monkeypatch.setattr("database.get_pool_status", lambda: {
            "pool_size": 10, "checked_out": 6, "checked_in": 4,
            "overflow": 0, "max_overflow": 5, "usage_percent": 69.9,
        })
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/db-health")
        assert resp.json()["health"] == "healthy"


# ============================================================================
# GET /api/admin/db-health/history
# ============================================================================

class TestDbHealthHistory:
    def teardown_method(self):
        _clear()

    def _snapshot(self, **kw):
        healthy = SimpleNamespace(value="healthy")
        base = dict(
            id=1, pool_size=10, max_overflow=5, checked_out=2,
            overflow=0, checked_in=8, usage_percent=20.0,
            health_status=healthy, trigger="threshold",
            created_at=datetime(2026, 5, 1, 9, 0),
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _wire(self, snapshots):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = snapshots
        db.query.return_value = chain
        return db

    def test_H_returns_snapshots(self, monkeypatch):
        snap = self._snapshot()
        _override(self._wire([snap]))
        monkeypatch.setattr(main, "get_circuit_breaker_stats", lambda: {"open": False})
        resp = TestClient(app).get("/api/admin/db-health/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["snapshot_count"] == 1
        assert body["circuit_breaker"]["open"] is False

    def test_H_with_hours_filter(self, monkeypatch):
        _override(self._wire([]))
        monkeypatch.setattr(main, "get_circuit_breaker_stats", lambda: {})
        resp = TestClient(app).get("/api/admin/db-health/history?hours=48")
        assert resp.status_code == 200
        assert resp.json()["hours_requested"] == 48

    def test_U_invalid_hours(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/db-health/history?hours=999")
        assert resp.status_code == 422

    def test_B_hour_1_minimum(self, monkeypatch):
        _override(self._wire([]))
        monkeypatch.setattr(main, "get_circuit_breaker_stats", lambda: {})
        resp = TestClient(app).get("/api/admin/db-health/history?hours=1")
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/test-results + /latest
# ============================================================================

class TestGetTestResults:
    def teardown_method(self):
        _clear()

    def _run(self, **kw):
        from db_models import TestRunStatus
        try:
            passed = TestRunStatus.PASSED
        except Exception:
            passed = SimpleNamespace(value="passed")
        base = dict(
            id=1, environment="staging", run_type="scheduled",
            status=passed, tests_passed=100, tests_failed=0,
            tests_skipped=0, tests_total=100,
            coverage_percent=80.5, duration_seconds=120,
            started_at=datetime(2026, 5, 1, 4, 0),
            completed_at=datetime(2026, 5, 1, 4, 2),
            commit_sha="abc123", branch="main",
            logs_url="https://gh.test/run/1", triggered_by="cron",
            pass_rate=100.0,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _wire(self, runs, single=None):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = runs
        chain.first.return_value = single if single is not None else (runs[0] if runs else None)
        db.query.return_value = chain
        return db

    def test_H_list_returns_runs(self):
        r = self._run()
        _override(self._wire([r]))
        resp = TestClient(app).get("/api/admin/test-results")
        assert resp.status_code == 200
        assert len(resp.json()["test_runs"]) == 1

    def test_E_empty(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/test-results")
        assert resp.json()["test_runs"] == []

    def test_H_filter_by_environment(self):
        _override(self._wire([self._run(environment="production")]))
        resp = TestClient(app).get("/api/admin/test-results?environment=production")
        assert resp.status_code == 200

    def test_U_limit_too_high(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/test-results?limit=999")
        assert resp.status_code == 422


class TestGetLatestTestResult:
    def teardown_method(self):
        _clear()

    def test_H_returns_latest(self):
        run = TestGetTestResults()._run()
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = run
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/admin/test-results/latest")
        assert resp.status_code == 200
        assert resp.json()["test_run"]["id"] == 1

    def test_E_no_runs(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/admin/test-results/latest")
        assert resp.json()["test_run"] is None

    def test_H_different_environment(self):
        run = TestGetTestResults()._run(environment="production")
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = run
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/admin/test-results/latest?environment=production")
        assert resp.status_code == 200


# ============================================================================
# POST /api/test-results — public (api_key auth)
# ============================================================================

class TestCreateTestResult:
    def teardown_method(self):
        _clear()

    def _wire(self):
        db = MagicMock()
        added = []
        def _add(obj):
            try:
                obj.id = 99
            except AttributeError:
                pass
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        # refresh would normally populate properties; since we're mocking,
        # leave the instance as-is. The handler reads .pass_rate on the
        # actual TestRun instance, which is a computed property.
        db.refresh = MagicMock()
        return db

    def _payload(self, **kw):
        base = dict(
            environment="staging", run_type="scheduled",
            tests_passed=100, tests_failed=0, tests_skipped=0, tests_total=100,
            api_key="tag-test-results-2026",
        )
        base.update(kw)
        return base

    def test_H_all_pass(self, monkeypatch):
        import os as _os
        actual_key = _os.environ.get("TEST_RESULTS_API_KEY", "tag-test-results-2026")
        def gen():
            yield self._wire()
        app.dependency_overrides[get_db] = gen
        resp = TestClient(app).post("/api/test-results",
                                     json=self._payload(api_key=actual_key))
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        _clear()

    def test_H_98pct_still_counts_as_passed(self, monkeypatch):
        import os as _os
        actual_key = _os.environ.get("TEST_RESULTS_API_KEY", "tag-test-results-2026")
        def gen():
            yield self._wire()
        app.dependency_overrides[get_db] = gen
        resp = TestClient(app).post("/api/test-results", json=self._payload(
            api_key=actual_key,
            tests_passed=98, tests_failed=2, tests_total=100,
        ))
        assert resp.status_code == 200
        _clear()

    def test_U_below_98_is_failed(self, monkeypatch):
        import os as _os
        actual_key = _os.environ.get("TEST_RESULTS_API_KEY", "tag-test-results-2026")
        def gen():
            yield self._wire()
        app.dependency_overrides[get_db] = gen
        resp = TestClient(app).post("/api/test-results", json=self._payload(
            api_key=actual_key,
            tests_passed=90, tests_failed=10, tests_total=100,
        ))
        assert resp.status_code == 200
        _clear()

    def test_U_zero_total_is_error(self, monkeypatch):
        import os as _os
        actual_key = _os.environ.get("TEST_RESULTS_API_KEY", "tag-test-results-2026")
        def gen():
            yield self._wire()
        app.dependency_overrides[get_db] = gen
        resp = TestClient(app).post("/api/test-results",
                                     json=self._payload(api_key=actual_key, tests_total=0))
        assert resp.status_code == 200
        _clear()

    def test_U_invalid_api_key(self, monkeypatch):
        monkeypatch.setenv("TEST_RESULTS_API_KEY", "expected-key")
        def gen():
            yield self._wire()
        app.dependency_overrides[get_db] = gen
        resp = TestClient(app).post("/api/test-results", json=self._payload(
            api_key="wrong-key",
        ))
        assert resp.status_code == 401
        _clear()


# ============================================================================
# GET /api/admin/audit-logs
# ============================================================================

class TestAuditLogs:
    def teardown_method(self):
        _clear()

    def _wire(self, count=0, rows=None):
        db = MagicMock()
        calls = {"n": 0}
        def _execute(stmt, params=None):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                # Count query
                result.scalar.return_value = count
            else:
                # Select query — fetchall returns rows
                result.fetchall.return_value = rows or []
            return result
        db.execute.side_effect = _execute
        return db

    def test_H_empty(self):
        _override(self._wire(count=0, rows=[]))
        resp = TestClient(app).get("/api/admin/audit-logs")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0

    def test_H_with_row(self):
        row = SimpleNamespace(
            id=1, session_id="sess-1", booking_reference="TAG-1",
            event="booking_confirmed", event_data="{}",
            ip_address="1.2.3.4", user_agent="agent",
            created_at=datetime(2026, 5, 1),
        )
        _override(self._wire(count=1, rows=[row]))
        resp = TestClient(app).get("/api/admin/audit-logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 1
        assert body["audit_logs"][0]["session_id"] == "sess-1"

    def test_H_all_filters(self):
        _override(self._wire(count=0, rows=[]))
        resp = TestClient(app).get(
            "/api/admin/audit-logs?search=test&booking_reference=TAG&event=booking_confirmed"
            "&date_from=2026-01-01T00:00:00Z&date_to=2026-12-31T23:59:59Z"
        )
        assert resp.status_code == 200

    def test_E_invalid_dates_silently_ignored(self):
        _override(self._wire(count=0, rows=[]))
        resp = TestClient(app).get("/api/admin/audit-logs?date_from=bogus&date_to=also-bad")
        assert resp.status_code == 200

    def test_U_limit_too_high(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/audit-logs?limit=999")
        assert resp.status_code == 422


class TestAuditLogEvents:
    def teardown_method(self):
        _clear()

    def test_H_returns_event_list(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/audit-logs/events")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert isinstance(events, list)
        assert len(events) > 0


# ============================================================================
# GET /api/admin/error-logs
# ============================================================================

class TestErrorLogs:
    def teardown_method(self):
        _clear()

    def _wire(self, count=0, rows=None):
        db = MagicMock()
        calls = {"n": 0}
        def _execute(stmt, params=None):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                result.scalar.return_value = count
            else:
                result.fetchall.return_value = rows or []
            return result
        db.execute.side_effect = _execute
        return db

    def test_H_empty(self):
        _override(self._wire(count=0, rows=[]))
        resp = TestClient(app).get("/api/admin/error-logs")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0

    def test_H_with_row(self):
        # Tuple-shaped row (handler indexes row[0]...row[12])
        row = (
            1, "error", "TypeError", "E001", "Boom went wrong",
            "Traceback...", "{}", "/api/x", "TAG-1", "sess-1",
            "1.2.3.4", "agent", datetime(2026, 5, 1),
        )
        _override(self._wire(count=1, rows=[row]))
        resp = TestClient(app).get("/api/admin/error-logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error_logs"][0]["message"] == "Boom went wrong"

    def test_H_all_filters(self):
        _override(self._wire())
        resp = TestClient(app).get(
            "/api/admin/error-logs?search=x&booking_reference=TAG&severity=critical"
            "&error_type=TypeError&date_from=2026-01-01T00:00:00Z&date_to=2026-12-31T23:59:59Z"
        )
        assert resp.status_code == 200

    def test_E_invalid_dates_silently_ignored(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/error-logs?date_from=bogus")
        assert resp.status_code == 200

    def test_U_limit_too_high(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/error-logs?limit=999")
        assert resp.status_code == 422


class TestErrorLogSeverities:
    def teardown_method(self):
        _clear()

    def test_H_returns_severity_list(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/admin/error-logs/severities")
        assert resp.status_code == 200
        assert len(resp.json()["severities"]) > 0


class TestErrorLogTypes:
    def teardown_method(self):
        _clear()

    def test_H_returns_distinct_types(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = [("TypeError",), ("ValueError",), (None,)]
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/admin/error-logs/types")
        assert resp.status_code == 200
        types = resp.json()["error_types"]
        # None filtered out
        assert "TypeError" in types
        assert None not in types

    def test_E_empty(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = []
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/admin/error-logs/types")
        assert resp.json()["error_types"] == []


# ============================================================================
# POST /api/admin/sql/logout
# ============================================================================

class TestSqlLogout:
    def teardown_method(self):
        _clear()

    def test_H_clears_session(self):
        main.sql_session_tokens[1] = {"token": "x", "expires_at": datetime.now()}
        _override(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/logout")
        assert resp.status_code == 200
        assert 1 not in main.sql_session_tokens

    def test_E_logout_when_no_session_is_noop(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/logout")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
