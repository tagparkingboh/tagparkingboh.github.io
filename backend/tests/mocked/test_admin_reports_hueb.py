"""
HUEB tests for the large admin report endpoints in main.py.

These endpoints are read-only aggregations, so the test surface is:
  - empty data path
  - data path (with 1-2 rows of stub data)
  - parameter validation
  - cache hit/miss branches

Endpoints:
  GET /api/admin/bookings/stats
  GET /api/admin/reports/financial
  GET /api/admin/reports/financial/export
  GET /api/admin/reports/abandoned-carts
  GET /api/admin/reports/bookings-forecast
"""
from datetime import date as date_type, datetime, time, timedelta
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
from db_models import BookingStatus, PaymentStatus

UK = pytz.timezone("Europe/London")


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


def _booking(**kw):
    """Stub for DbBooking row with all attrs the stats endpoint reads."""
    base = dict(
        id=1, reference="TAG-1",
        status=BookingStatus.CONFIRMED,
        created_at=datetime(2026, 5, 1, 9, 0),
        dropoff_date=date_type(2026, 6, 1),
        pickup_date=date_type(2026, 6, 8),
        dropoff_time=time(10, 0),
        pickup_time=time(11, 30),
        dropoff_destination="Tenerife",
        dropoff_airline_name="TUI Airways",
        customer_first_name="Jo", customer_last_name="K",
        flight_arrival_time=time(15, 0),
        flight_number="TOM1",
        flight_departure_time=time(12, 0),
        airline_code="TOM",
        return_destination=None,
        payment=SimpleNamespace(
            amount_pence=9900, status=PaymentStatus.SUCCEEDED,
            paid_at=datetime(2026, 5, 1, 10, 0),
        ),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _reset_caches():
    """Clear in-memory caches between tests so previous tests don't poison the next one."""
    try:
        main._financial_cache = {"data": None, "cached_at": None}
    except Exception:
        pass
    try:
        main._abandoned_carts_cache = {"data": None, "cached_at": None}
    except Exception:
        pass
    try:
        main._forecast_cache = {"data": None, "cached_at": None}
    except Exception:
        pass


# ============================================================================
# GET /api/admin/bookings/stats
# ============================================================================

class TestBookingStats:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings, audit_logs=None):
        """Booking queries return `bookings`. AuditLog queries return `audit_logs`."""
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.all.return_value = bookings
            elif name == "AuditLog":
                chain.all.return_value = audit_logs or []
            else:
                chain.all.return_value = []
            return chain
        db.query.side_effect = _query
        return db

    def test_H_empty_bookings(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/bookings/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["daily"] == []
        assert body["monthly"] == []

    def test_H_with_bookings(self):
        b1 = _booking(id=1, status=BookingStatus.CONFIRMED,
                      created_at=datetime(2026, 5, 1, 9, 0))
        b2 = _booking(id=2, status=BookingStatus.COMPLETED,
                      created_at=datetime(2026, 5, 2, 10, 0))
        _override(self._wire([b1, b2]))
        resp = TestClient(app).get("/api/admin/bookings/stats")
        assert resp.status_code == 200
        body = resp.json()
        # Daily entries cover 2 dates
        assert len(body["daily"]) == 2
        assert body["status_totals"]["confirmed"] >= 1

    def test_E_booking_without_payment(self):
        b = _booking(id=5, payment=None)
        _override(self._wire([b]))
        resp = TestClient(app).get("/api/admin/bookings/stats")
        assert resp.status_code == 200

    def test_E_booking_with_status_none(self):
        b = _booking(id=6, status=None)
        _override(self._wire([b]))
        resp = TestClient(app).get("/api/admin/bookings/stats")
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/reports/financial
# ============================================================================

class TestFinancialReport:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings, promo_codes=None):
        db = MagicMock()
        def _query(*args):
            chain = MagicMock()
            chain.join.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = bookings
            # PromoCode lookup
            chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        return db

    def test_H_default_request(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial")
        assert resp.status_code == 200

    def test_H_with_status_filter_confirmed(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?status_filter=confirmed")
        assert resp.status_code == 200

    def test_H_with_status_filter_completed(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?status_filter=completed")
        assert resp.status_code == 200

    def test_H_with_status_filter_refunded(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?status_filter=refunded")
        assert resp.status_code == 200

    def test_H_with_date_filters(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?from_date=01/01/2026&to_date=31/12/2026")
        assert resp.status_code == 200

    def test_E_invalid_date_silently_ignored(self):
        """Bad date strings are caught by inner try/except and ignored."""
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?from_date=bogus")
        assert resp.status_code == 200

    def test_H_promo_filter_yes(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?promo_filter=yes")
        assert resp.status_code == 200

    def test_H_promo_filter_no(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?promo_filter=no")
        assert resp.status_code == 200

    def test_E_cache_hit_returns_cached_response(self):
        """Second default request within cache TTL returns cached data."""
        _override(self._wire([]))
        TestClient(app).get("/api/admin/reports/financial")
        # Force a cache write by manually injecting
        main._financial_cache = {
            "data": {"bookings": [], "stats": {}},
            "cached_at": datetime.now(UK),
        }
        resp = TestClient(app).get("/api/admin/reports/financial")
        assert resp.status_code == 200
        assert resp.json().get("cached") is True

    def test_E_refresh_bypasses_cache(self):
        main._financial_cache = {
            "data": {"bookings": [], "stats": {}},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial?refresh=true")
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/reports/financial/export
# ============================================================================

class TestFinancialExport:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings):
        db = MagicMock()
        def _query(*args):
            chain = MagicMock()
            chain.join.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = bookings
            return chain
        db.query.side_effect = _query
        return db

    def test_H_empty_export(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/financial/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    def test_H_with_filters(self):
        _override(self._wire([]))
        resp = TestClient(app).get(
            "/api/admin/reports/financial/export?status_filter=refunded&from_date=01/01/2026&to_date=31/12/2026"
        )
        assert resp.status_code == 200

    def test_E_invalid_dates_silently_ignored(self):
        _override(self._wire([]))
        resp = TestClient(app).get(
            "/api/admin/reports/financial/export?from_date=bogus&to_date=alsobad"
        )
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/reports/abandoned-carts
# ============================================================================

class TestAbandonedCarts:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, started_logs=None, completed_logs=None):
        db = MagicMock()
        call_n = {"i": 0}
        def _query(*args):
            call_n["i"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.distinct.return_value = chain
            # First call = started_sessions, second = completed_sessions
            if call_n["i"] == 1:
                chain.all.return_value = started_logs or []
            else:
                chain.all.return_value = completed_logs or []
            return chain
        db.query.side_effect = _query
        return db

    def test_H_daily_empty(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/abandoned-carts")
        assert resp.status_code == 200

    def test_H_weekly(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/abandoned-carts?period=weekly")
        assert resp.status_code == 200

    def test_H_monthly(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/abandoned-carts?period=monthly")
        assert resp.status_code == 200

    def test_E_cache_hit(self):
        main._abandoned_carts_cache = {
            "data": {"total_abandoned": 5, "by_period": []},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/abandoned-carts")
        assert resp.status_code == 200
        assert resp.json().get("cached") is True

    def test_E_refresh_bypasses_cache(self):
        main._abandoned_carts_cache = {
            "data": {"total_abandoned": 99},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/abandoned-carts?refresh=true")
        assert resp.status_code == 200
        # Refresh bypasses cache → "cached" missing or false
        assert resp.json().get("cached") is not True


# ============================================================================
# GET /api/admin/reports/bookings-forecast
# ============================================================================

class TestBookingsForecast:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, historical=None, abandoned=None):
        db = MagicMock()
        call_n = {"i": 0}
        def _query(*args):
            call_n["i"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.distinct.return_value = chain
            if call_n["i"] == 1:
                chain.all.return_value = historical or []
            else:
                chain.all.return_value = abandoned or []
            return chain
        db.query.side_effect = _query
        return db

    def test_H_empty(self):
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/bookings-forecast")
        assert resp.status_code == 200

    def test_H_with_historical_data(self):
        b1 = _booking(id=1, dropoff_destination="Tenerife",
                      created_at=datetime(2026, 4, 1, 10, 0))
        b2 = _booking(id=2, dropoff_destination="Malaga",
                      created_at=datetime(2026, 4, 15, 10, 0))
        _override(self._wire(historical=[b1, b2]))
        resp = TestClient(app).get("/api/admin/reports/bookings-forecast")
        assert resp.status_code == 200

    def test_E_cache_hit(self):
        main._forecast_cache = {
            "data": {"predictions": [], "destinations": []},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/bookings-forecast")
        assert resp.status_code == 200
        assert resp.json().get("cached") is True

    def test_E_refresh_bypasses_cache(self):
        main._forecast_cache = {
            "data": {"predictions": []},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire())
        resp = TestClient(app).get("/api/admin/reports/bookings-forecast?refresh=true")
        assert resp.status_code == 200
        assert resp.json().get("cached") is not True
