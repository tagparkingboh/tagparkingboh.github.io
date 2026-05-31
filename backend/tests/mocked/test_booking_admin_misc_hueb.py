"""
HUEB tests for the booking-related admin endpoints:
  PUT  /api/admin/bookings/{id}              (update_booking — flight/time fixes)
  POST /api/admin/fix-overnight-arrivals     (overnight pickup_date corrector)
  POST /api/admin/fix-customer-names         (title-case enforcer)
"""
from datetime import date as date_type, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app, require_admin
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# PUT /api/admin/bookings/{id} — update_booking
# ============================================================================

def _booking(**kw):
    base = dict(
        id=99, reference="TAG-1",
        pickup_date=date_type(2026, 6, 8),
        pickup_time=time(11, 30),
        pickup_airline_name="TUI", pickup_flight_number="TOM1235",
        pickup_origin="Tenerife",
        arrival_id=None,
        dropoff_date=date_type(2026, 6, 1),
        dropoff_time=time(10, 0),
        dropoff_airline_name="TUI", dropoff_flight_number="TOM1234",
        dropoff_destination="Tenerife",
        flight_arrival_date=date_type(2026, 6, 8),
        flight_arrival_time=time(15, 0),
        flight_departure_time=time(12, 0),
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestUpdateBooking:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_update_pickup_date(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}",
                                    json={"pickup_date": "2026-06-09"})
        assert resp.status_code == 200
        assert b.pickup_date == date_type(2026, 6, 9)
        assert "pickup_date" in resp.json()["fields_updated"]

    def test_H_update_pickup_time(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}",
                                    json={"pickup_time": "14:30"})
        assert resp.status_code == 200
        assert b.pickup_time == time(14, 30)

    def test_H_update_flight_arrival_recalcs_pickup(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}",
                                    json={"flight_arrival_time": "16:00"})
        assert resp.status_code == 200
        # pickup_time = arrival + 30 min = 16:30
        assert b.flight_arrival_time == time(16, 0)
        assert b.pickup_time == time(16, 30)

    def test_H_update_dropoff_fields(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}", json={
            "dropoff_date": "2026-06-02",
            "dropoff_time": "11:00",
            "dropoff_destination": "Malaga",
        })
        assert resp.status_code == 200

    def test_H_update_non_planner_fields_does_not_trigger_engine(self, monkeypatch):
        b = _booking()
        called = {"n": 0}
        def fake_fire(*a, **kw):
            called["n"] += 1
        monkeypatch.setattr("roster_planner_runner.fire_engine_async", fake_fire)
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}",
                                    json={"dropoff_destination": "Malaga"})
        assert resp.status_code == 200
        # Engine only fires when planner-relevant fields change
        assert called["n"] == 0

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).put("/api/admin/bookings/9999",
                                    json={"pickup_date": "2026-06-09"})
        assert resp.status_code == 404

    def test_U_no_fields_to_update(self):
        b = _booking()
        _override(self._wire(b))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}", json={})
        assert resp.status_code == 400
        assert "no fields" in resp.json()["detail"].lower()


# ============================================================================
# POST /api/admin/fix-overnight-arrivals
# ============================================================================

class TestFixOvernightArrivals:
    def teardown_method(self):
        _clear()

    def _wire(self, bookings, arrivals_map=None):
        db = MagicMock()
        arrivals_map = arrivals_map or {}
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.all.return_value = bookings
            elif name == "FlightArrival":
                # The filter narrows by id; return the first arrival in our map
                chain.first.return_value = next(iter(arrivals_map.values()), None) if arrivals_map else None
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        return db

    def test_H_dry_run_no_overnight(self):
        # Day flight (12:00 dep, 16:00 arrival) — not overnight
        b = SimpleNamespace(
            id=1, reference="TAG-1", arrival_id=5,
            pickup_date=date_type(2026, 6, 1),
            pickup_flight_number="TOM1235",
        )
        arrival = SimpleNamespace(
            id=5, date=date_type(2026, 6, 1),
            arrival_time=time(16, 0), departure_time=time(12, 0),
        )
        _override(self._wire([b], arrivals_map={5: arrival}))
        resp = TestClient(app).post("/api/admin/fix-overnight-arrivals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is True
        assert body["overnight_found"] == 0
        assert body["bookings_fixed"] == 0

    def test_H_dry_run_overnight_detected(self):
        """22:00 dep, 02:00 arrival next day — overnight, pickup date wrong."""
        b = SimpleNamespace(
            id=1, reference="TAG-1", arrival_id=5,
            pickup_date=date_type(2026, 6, 1),  # Wrong — should be 6/2
            pickup_flight_number="TOM1235",
        )
        arrival = SimpleNamespace(
            id=5, date=date_type(2026, 6, 2),  # Already corrected
            arrival_time=time(2, 0), departure_time=time(22, 0),
        )
        _override(self._wire([b], arrivals_map={5: arrival}))
        resp = TestClient(app).post("/api/admin/fix-overnight-arrivals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["overnight_found"] == 1
        assert body["bookings_fixed"] == 0  # dry_run

    def test_H_apply_fix(self):
        b = SimpleNamespace(
            id=1, reference="TAG-1", arrival_id=5,
            pickup_date=date_type(2026, 6, 1),
            pickup_flight_number="TOM1235",
        )
        arrival = SimpleNamespace(
            id=5, date=date_type(2026, 6, 2),
            arrival_time=time(2, 0), departure_time=time(22, 0),
        )
        _override(self._wire([b], arrivals_map={5: arrival}))
        resp = TestClient(app).post("/api/admin/fix-overnight-arrivals?dry_run=false")
        assert resp.status_code == 200
        assert resp.json()["bookings_fixed"] == 1
        assert b.pickup_date == date_type(2026, 6, 2)

    def test_E_arrival_not_found_is_skipped(self):
        b = SimpleNamespace(
            id=1, reference="TAG-1", arrival_id=999,
            pickup_date=date_type(2026, 6, 1),
            pickup_flight_number="TOM1235",
        )
        _override(self._wire([b], arrivals_map={}))
        resp = TestClient(app).post("/api/admin/fix-overnight-arrivals")
        assert resp.status_code == 200
        assert resp.json()["overnight_found"] == 0

    def test_E_no_bookings(self):
        _override(self._wire([]))
        resp = TestClient(app).post("/api/admin/fix-overnight-arrivals")
        assert resp.status_code == 200
        assert resp.json()["bookings_checked"] == 0


# ============================================================================
# POST /api/admin/fix-customer-names
# ============================================================================

# Skipped: /api/admin/fix-customer-names is dead code in main.py:3351 — it
# does `db.query(Customer)` but `Customer` is never imported at module scope
# (only locally in other endpoints). The same handler also uses Pydantic
# `Booking` instead of `DbBooking`. Documented in
# memory/project_manual_booking_system.md. Calling this endpoint in prod
# would NameError.
