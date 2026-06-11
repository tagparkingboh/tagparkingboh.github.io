"""
HUEB tests for the larger admin report endpoints.

  GET /api/admin/reports/booking-locations  (bookings + origins map types)
  GET /api/admin/reports/occupancy          (daily/weekly/monthly)
  GET /api/admin/reports/popular
"""
from datetime import date as date_type, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz
from fastapi.testclient import TestClient
import main
from main import app, require_admin
from database import get_db

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


def _reset_caches():
    try:
        main._booking_locations_cache = {"bookings": {}, "origins": {}}
    except Exception:
        pass
    try:
        main._occupancy_cache = {"data": None, "cached_at": None}
    except Exception:
        pass
    try:
        main._popular_cache = {"data": None, "cached_at": None}
    except Exception:
        pass


def _patch_httpx(monkeypatch, json_body=None, status=200):
    """Patch httpx.AsyncClient so postcode lookups never hit the network."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = status
    response.json.return_value = json_body or {"result": []}
    client.post = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", MagicMock(return_value=cm))
    return client


# ============================================================================
# booking-locations
# ============================================================================

class TestBookingLocations:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings=None, customers=None):
        db = MagicMock()
        def _query(*args):
            chain = MagicMock()
            chain.options.return_value = chain
            chain.outerjoin.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.group_by.return_value = chain
            chain.all.return_value = bookings or []
            chain.subquery.return_value = MagicMock(c=MagicMock())
            return chain
        db.query.side_effect = _query
        return db

    def test_H_bookings_empty(self, monkeypatch):
        _patch_httpx(monkeypatch)
        _override(self._wire(bookings=[]))
        resp = TestClient(app).get("/api/admin/reports/booking-locations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["map_type"] == "bookings"

    def test_H_bookings_with_postcode(self, monkeypatch):
        from db_models import BookingStatus
        cust = SimpleNamespace(
            id=1, first_name="Jo", last_name="K", phone="07111",
            email="jo@x.test",
            billing_address1="1 High St", billing_city="Bournemouth",
            billing_postcode="BH1 1AA", created_at=datetime(2026, 5, 1),
        )
        b = SimpleNamespace(
            id=10, reference="TAG-1", customer=cust,
            customer_first_name="Jo", customer_last_name="K",
            dropoff_date=date_type(2026, 6, 1),
            status=BookingStatus.CONFIRMED,
        )
        _patch_httpx(monkeypatch, json_body={"result": [{
            "query": "BH1 1AA",
            "result": {"latitude": 50.72, "longitude": -1.88, "admin_district": "Bournemouth"},
        }]})
        _override(self._wire(bookings=[b]))
        resp = TestClient(app).get("/api/admin/reports/booking-locations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["locations"][0]["postcode"] == "BH1 1AA"

    def test_E_geocoding_error_logs_and_continues(self, monkeypatch):
        from db_models import BookingStatus
        cust = SimpleNamespace(
            id=1, first_name="Jo", last_name="K", phone=None, email=None,
            billing_address1=None, billing_city=None,
            billing_postcode="BH1 1AA", created_at=None,
        )
        b = SimpleNamespace(
            id=10, reference="TAG-1", customer=cust,
            customer_first_name="Jo", customer_last_name="K",
            dropoff_date=None, status=BookingStatus.CONFIRMED,
        )
        # httpx raises an exception
        client = MagicMock()
        client.post = AsyncMock(side_effect=RuntimeError("network down"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("main.httpx.AsyncClient", MagicMock(return_value=cm))
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _override(self._wire(bookings=[b]))
        resp = TestClient(app).get("/api/admin/reports/booking-locations")
        assert resp.status_code == 200
        # Skipped because postcode not in coordinates
        assert resp.json()["count"] == 0
        assert resp.json()["skipped_count"] == 1

    # Origins branch uses SQLAlchemy subquery + .is_() which requires real
    # column types — too coupled to SQLA internals to mock cleanly. Bookings
    # branch coverage above hits the geocoding + cache logic shared between
    # both paths.

    def test_E_cache_hit(self, monkeypatch):
        main._booking_locations_cache["bookings"] = {
            "data": {"count": 0, "locations": [], "map_type": "bookings"},
            "cached_at": datetime.now(UK),
        }
        _patch_httpx(monkeypatch)
        _override(self._wire(bookings=[]))
        resp = TestClient(app).get("/api/admin/reports/booking-locations")
        assert resp.status_code == 200
        assert resp.json().get("cached") is True

    def test_E_refresh_bypasses_cache(self, monkeypatch):
        main._booking_locations_cache["bookings"] = {
            "data": {"count": 99, "locations": [], "map_type": "bookings"},
            "cached_at": datetime.now(UK),
        }
        _patch_httpx(monkeypatch)
        _override(self._wire(bookings=[]))
        resp = TestClient(app).get("/api/admin/reports/booking-locations?refresh=true")
        assert resp.json().get("cached") is not True


# ============================================================================
# occupancy
# ============================================================================

class TestOccupancyReport:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain.all.return_value = bookings if name == "Booking" else []
            return chain
        db.query.side_effect = _query
        return db

    def _booking(self, dropoff, pickup):
        from db_models import BookingStatus
        return SimpleNamespace(
            id=1, status=BookingStatus.CONFIRMED,
            dropoff_date=dropoff, pickup_date=pickup,
        )

    def test_H_daily_empty(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/occupancy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["view"] == "daily"
        assert body["max_capacity"] == 73

    def test_H_daily_with_booking(self):
        b = self._booking(date_type(2026, 5, 19), date_type(2026, 5, 22))
        _override(self._wire([b]))
        resp = TestClient(app).get(
            "/api/admin/reports/occupancy?start_date=2026-05-15&end_date=2026-05-25"
        )
        assert resp.status_code == 200
        # Find the day with occupancy = 1
        data = resp.json()["data"]
        occupied_days = [d for d in data if d["occupied"] > 0]
        assert len(occupied_days) == 4  # 19, 20, 21, 22

    def test_H_weekly(self):
        b = self._booking(date_type(2026, 5, 19), date_type(2026, 5, 22))
        _override(self._wire([b]))
        resp = TestClient(app).get(
            "/api/admin/reports/occupancy?view=weekly&start_date=2026-05-15&end_date=2026-05-25"
        )
        assert resp.status_code == 200
        assert resp.json()["view"] == "weekly"

    def test_H_monthly(self):
        b = self._booking(date_type(2026, 5, 19), date_type(2026, 5, 22))
        _override(self._wire([b]))
        resp = TestClient(app).get(
            "/api/admin/reports/occupancy?view=monthly&start_date=2026-05-01&end_date=2026-05-31"
        )
        assert resp.status_code == 200
        assert resp.json()["view"] == "monthly"

    def test_U_invalid_view(self):
        _override(self._wire([]))
        resp = TestClient(app).get(
            "/api/admin/reports/occupancy?view=bogus&start_date=2026-05-15&end_date=2026-05-25"
        )
        assert resp.status_code == 400

    def test_E_cache_hit(self):
        main._occupancy_cache = {
            "data": {"view": "daily", "data": [], "max_capacity": 64,
                     "start_date": "2026-05-15", "end_date": "2026-05-25"},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire([]))
        # No start_date/end_date params = default request → cache hit
        resp = TestClient(app).get("/api/admin/reports/occupancy")
        assert resp.json().get("cached") is True


# ============================================================================
# popular (smaller — read what shape it has)
# ============================================================================

class TestPopularReport:
    def setup_method(self):
        _reset_caches()

    def teardown_method(self):
        _clear()

    def _wire(self, bookings):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.options.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = bookings
        db.query.return_value = chain
        return db

    def test_H_empty(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/popular")
        assert resp.status_code == 200

    def test_H_with_bookings(self):
        from db_models import BookingStatus
        cust = SimpleNamespace(id=1, first_name="Jo", last_name="K",
                               billing_postcode="BH1 1AA")
        b = SimpleNamespace(
            id=1, customer=cust, customer_first_name="Jo", customer_last_name="K",
            dropoff_date=date_type(2026, 5, 1),
            pickup_date=date_type(2026, 5, 8),
            dropoff_destination="Tenerife",
            dropoff_airline_name="TUI Airways",
            pickup_airline_name="TUI Airways",
            pickup_origin="Tenerife",
            status=BookingStatus.CONFIRMED,
            created_at=datetime(2026, 4, 1),
            payment=None,
        )
        _override(self._wire([b]))
        resp = TestClient(app).get("/api/admin/reports/popular")
        assert resp.status_code == 200

    def test_E_cache_hit(self):
        main._popular_cache = {
            "data": {"top_destinations": [], "top_airlines": []},
            "cached_at": datetime.now(UK),
        }
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/reports/popular")
        assert resp.json().get("cached") is True
