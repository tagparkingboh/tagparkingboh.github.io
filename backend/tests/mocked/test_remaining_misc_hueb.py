"""
HUEB tests for remaining smaller endpoints:

  GET  /api/admin/marketing-sources/summary
  GET  /api/admin/marketing-sources/other
  POST /api/flights/departures/{id}/book-slot
  GET  /api/flights/dates
  POST /api/admin/sql/verify-pin
  GET  /api/admin/sql/session-status
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz
from fastapi.testclient import TestClient
import main
from main import app, require_admin
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override_admin(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()
    try:
        main.sql_session_tokens.clear()
    except Exception:
        pass


# ============================================================================
# GET /api/admin/marketing-sources/summary
# ============================================================================

class TestMarketingSourcesSummary:
    def teardown_method(self):
        _clear()

    def _wire(self, totals):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = totals
        db.query.return_value = chain
        return db

    def _row(self, year_month="2026-05", source="google", count=10):
        return SimpleNamespace(year_month=year_month, source=source, count=count)

    def test_H_no_filters(self):
        _override_admin(self._wire([self._row()]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_responses"] == 10
        assert body["source_totals"]["google"] == 10

    def test_H_with_filters(self):
        _override_admin(self._wire([self._row()]))
        resp = TestClient(app).get(
            "/api/admin/marketing-sources/summary?from_month=04/2026&to_month=06/2026"
        )
        assert resp.status_code == 200

    def test_U_invalid_from_month(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?from_month=bogus")
        assert resp.status_code == 400
        assert "MM/YYYY" in resp.json()["detail"]

    def test_U_invalid_to_month(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary?to_month=bogus")
        assert resp.status_code == 400

    def test_E_empty(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/summary")
        assert resp.json()["total_responses"] == 0


# ============================================================================
# GET /api/admin/marketing-sources/other
# ============================================================================

class TestMarketingSourcesOther:
    def teardown_method(self):
        _clear()

    def _wire(self, results):
        db = MagicMock()
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = results
        db.query.return_value = chain
        return db

    def test_H_returns_other_responses(self):
        ms = SimpleNamespace(source_detail="Friend told me",
                              created_at=datetime(2026, 5, 1))
        cust = SimpleNamespace(email="jo@x.test", first_name="Jo", last_name="K")
        _override_admin(self._wire([(ms, cust)]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["details"][0]["customer_email"] == "jo@x.test"

    def test_H_with_year_month_filter(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?year_month=2026-05")
        assert resp.status_code == 200

    def test_E_invalid_year_month_silently_ignored(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?year_month=bogus")
        # Handler swallows the parse error and just ignores the filter
        assert resp.status_code == 200

    def test_U_invalid_from_date(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?from_date=bogus")
        assert resp.status_code == 400

    def test_U_invalid_to_date(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/marketing-sources/other?to_date=bogus")
        assert resp.status_code == 400


# ============================================================================
# POST /api/flights/departures/{id}/book-slot
# ============================================================================

class TestBookDepartureSlot:
    def teardown_method(self):
        _clear()

    def test_H_books_early(self, monkeypatch):
        monkeypatch.setattr("db_service.book_departure_slot",
                            lambda db, did, st: {"success": True, "remaining": 3})
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/flights/departures/5/book-slot?slot_id=150")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.parametrize("slot_id", ["150", "165", "120", "90"])
    def test_H_each_valid_slot(self, monkeypatch, slot_id):
        monkeypatch.setattr("db_service.book_departure_slot",
                            lambda db, did, st: {"success": True})
        _override_public(MagicMock())
        resp = TestClient(app).post(f"/api/flights/departures/5/book-slot?slot_id={slot_id}")
        assert resp.status_code == 200

    def test_U_invalid_slot_id(self):
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/flights/departures/5/book-slot?slot_id=bogus")
        assert resp.status_code == 400

    def test_U_call_us_only(self, monkeypatch):
        monkeypatch.setattr("db_service.book_departure_slot",
                            lambda db, did, st: {"success": False, "call_us": True,
                                                  "message": "Capacity tier 0"})
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/flights/departures/5/book-slot?slot_id=150")
        assert resp.status_code == 400
        assert "calling to book" in resp.json()["detail"].lower()

    def test_U_full(self, monkeypatch):
        monkeypatch.setattr("db_service.book_departure_slot",
                            lambda db, did, st: {"success": False, "call_us": False,
                                                  "message": "Slot full"})
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/flights/departures/5/book-slot?slot_id=150")
        assert resp.status_code == 400


# ============================================================================
# GET /api/flights/dates
# ============================================================================

class TestFlightsDates:
    def teardown_method(self):
        _clear()

    def test_H_returns_dates(self):
        from datetime import date as date_type
        db = MagicMock()
        chain = MagicMock()
        chain.distinct.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = [(date_type(2026, 6, 1),), (date_type(2026, 6, 2),)]
        db.query.return_value = chain
        _override_public(db)
        resp = TestClient(app).get("/api/flights/dates")
        assert resp.status_code == 200
        assert resp.json() == ["2026-06-01", "2026-06-02"]


# ============================================================================
# POST /api/admin/sql/verify-pin + GET /api/admin/sql/session-status
# ============================================================================

class TestSqlVerifyPin:
    def teardown_method(self):
        _clear()

    def test_H_valid_pin(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings",
                            lambda: SimpleNamespace(admin_sql_pin="1234"))
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/verify-pin", json={"pin": "1234"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "session_token" in resp.json()

    def test_U_invalid_pin(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings",
                            lambda: SimpleNamespace(admin_sql_pin="1234"))
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/verify-pin", json={"pin": "wrong"})
        assert resp.status_code == 401

    def test_U_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings",
                            lambda: SimpleNamespace(admin_sql_pin=None))
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/verify-pin", json={"pin": "1234"})
        assert resp.status_code == 503


class TestSqlSessionStatus:
    def teardown_method(self):
        _clear()

    def test_E_no_session(self):
        _override_admin(MagicMock())
        resp = TestClient(app).get("/api/admin/sql/session-status")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert resp.json()["reason"] == "no_session"

    def test_H_valid_session(self):
        uk = pytz.timezone("Europe/London")
        main.sql_session_tokens[1] = {
            "token": "valid", "expires_at": datetime.now(uk) + timedelta(hours=1),
        }
        _override_admin(MagicMock())
        resp = TestClient(app).get("/api/admin/sql/session-status")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_E_expired_session(self):
        uk = pytz.timezone("Europe/London")
        main.sql_session_tokens[1] = {
            "token": "expired", "expires_at": datetime.now(uk) - timedelta(hours=1),
        }
        _override_admin(MagicMock())
        resp = TestClient(app).get("/api/admin/sql/session-status")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert resp.json()["reason"] == "expired"
        # Token should have been cleaned up
        assert 1 not in main.sql_session_tokens
