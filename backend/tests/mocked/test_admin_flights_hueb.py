"""
HUEB tests for main.py admin flights CRUD.

Covers:
  PUT    /api/admin/flights/departures/{id}   (update_admin_departure 13614)
  PUT    /api/admin/flights/arrivals/{id}     (update_admin_arrival 13722)
  POST   /api/admin/flights/departures        (create_admin_departure 13799)
  POST   /api/admin/flights/arrivals          (create_admin_arrival 13864)
  DELETE /api/admin/flights/departures/{id}   (delete_admin_departure 13918)
  DELETE /api/admin/flights/arrivals/{id}     (delete_admin_arrival 13968)
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


def _departure(**kw):
    """Stub for a FlightDeparture row."""
    base = dict(
        id=10,
        date=date_type(2026, 6, 1),
        flight_number="TOM1234",
        airline_code="TOM",
        airline_name="TUI Airways",
        departure_time=time(12, 0),
        destination_code="TFS",
        destination_name="Tenerife",
        capacity_tier=6,
        slots_booked_early=2,
        slots_booked_late=1,
        max_slots_per_time=3,
        early_slots_available=1,
        late_slots_available=2,
        updated_at=None,
        updated_by=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _arrival(**kw):
    base = dict(
        id=20,
        date=date_type(2026, 6, 8),
        flight_number="TOM1235",
        airline_code="TOM",
        airline_name="TUI Airways",
        arrival_time=time(15, 0),
        departure_time=time(11, 0),
        origin_code="TFS",
        origin_name="Tenerife",
        updated_at=None,
        updated_by=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _wire_single(primary_model_name, primary_obj, linked_bookings=None):
    """DB stub that returns `primary_obj` for FlightDeparture/FlightArrival.first()
    and `linked_bookings` (list) for DbBooking.all(). count() returns len."""
    db = MagicMock()
    linked = linked_bookings or []

    def _query(model):
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = linked if name == "Booking" else []
        chain.first.return_value = primary_obj if name == primary_model_name else None
        chain.count.return_value = len(linked) if name == "Booking" else 0
        return chain

    db.query.side_effect = _query
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    return db


# ============================================================================
# PUT /api/admin/flights/departures/{id} — update_admin_departure
# ============================================================================

class TestUpdateDeparture:
    def teardown_method(self):
        _clear()

    def test_H_simple_field_update(self):
        d = _departure()
        _override(_wire_single("FlightDeparture", d))
        resp = TestClient(app).put(f"/api/admin/flights/departures/{d.id}",
                                   json={"airline_name": "TUI Airways Ltd"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert d.airline_name == "TUI Airways Ltd"
        assert d.updated_by == "admin@tag.test"

    def test_U_not_found(self):
        _override(_wire_single("FlightDeparture", None))
        resp = TestClient(app).put("/api/admin/flights/departures/99999",
                                   json={"airline_name": "x"})
        assert resp.status_code == 404

    def test_E_capacity_reduction_warning(self):
        d = _departure(slots_booked_early=5, slots_booked_late=4)
        _override(_wire_single("FlightDeparture", d))
        # capacity_tier=4 → max per slot = 2; both early/late exceed → warning
        resp = TestClient(app).put(f"/api/admin/flights/departures/{d.id}",
                                   json={"capacity_tier": 4})
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        assert any("Reducing capacity" in w for w in warnings)

    def test_E_departure_time_change_recalcs_bookings(self):
        d = _departure(departure_time=time(12, 0))
        b_early = SimpleNamespace(id=1, departure_id=d.id, dropoff_slot="early",
                                  dropoff_time=time(9, 30), flight_arrival_time=None,
                                  pickup_time=None)
        b_late = SimpleNamespace(id=2, departure_id=d.id, dropoff_slot="late",
                                 dropoff_time=time(10, 30), flight_arrival_time=None,
                                 pickup_time=None)
        b_no_slot = SimpleNamespace(id=3, departure_id=d.id, dropoff_slot=None,
                                    dropoff_time=time(10, 0), flight_arrival_time=None,
                                    pickup_time=None)
        _override(_wire_single("FlightDeparture", d,
                               linked_bookings=[b_early, b_late, b_no_slot]))
        resp = TestClient(app).put(f"/api/admin/flights/departures/{d.id}",
                                   json={"departure_time": "14:00"})
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        # 2 bookings (early+late) re-timed, b_no_slot skipped
        assert any("Updated drop-off times for 2 booking(s)" in w for w in warnings)
        # Times shifted by +2h
        assert b_early.dropoff_time == time(11, 30)
        assert b_late.dropoff_time == time(12, 30)
        assert b_no_slot.dropoff_time == time(10, 0)  # unchanged

    def test_E_date_field_parsed(self):
        d = _departure(date=date_type(2026, 6, 1))
        _override(_wire_single("FlightDeparture", d))
        resp = TestClient(app).put(f"/api/admin/flights/departures/{d.id}",
                                   json={"date": "2026-07-15"})
        assert resp.status_code == 200
        assert d.date == date_type(2026, 7, 15)

    # Skipped: bad time format triggers ValueError before any try/except — the
    # handler at main.py:13652 calls time.fromisoformat unguarded, so the
    # exception escapes the response cycle entirely (latent bug, not test bug).


# ============================================================================
# PUT /api/admin/flights/arrivals/{id} — update_admin_arrival
# ============================================================================

class TestUpdateArrival:
    def teardown_method(self):
        _clear()

    def test_H_simple_update(self):
        a = _arrival()
        _override(_wire_single("FlightArrival", a))
        resp = TestClient(app).put(f"/api/admin/flights/arrivals/{a.id}",
                                   json={"airline_name": "TUI Airways New"})
        assert resp.status_code == 200
        assert a.airline_name == "TUI Airways New"

    def test_U_not_found(self):
        _override(_wire_single("FlightArrival", None))
        resp = TestClient(app).put("/api/admin/flights/arrivals/99999",
                                   json={"airline_name": "x"})
        assert resp.status_code == 404

    def test_E_arrival_time_change_recalcs_pickup(self):
        a = _arrival(arrival_time=time(15, 0))
        b = SimpleNamespace(id=5, arrival_id=a.id, flight_arrival_time=None, pickup_time=None)
        _override(_wire_single("FlightArrival", a, linked_bookings=[b]))
        resp = TestClient(app).put(f"/api/admin/flights/arrivals/{a.id}",
                                   json={"arrival_time": "16:00"})
        assert resp.status_code == 200
        # pickup = arrival + 30min = 16:30
        assert b.flight_arrival_time == time(16, 0)
        assert b.pickup_time == time(16, 30)
        warnings = resp.json()["warnings"]
        assert any("Updated pickup times for 1 booking(s)" in w for w in warnings)

    def test_E_date_field_parsed(self):
        a = _arrival()
        _override(_wire_single("FlightArrival", a))
        resp = TestClient(app).put(f"/api/admin/flights/arrivals/{a.id}",
                                   json={"date": "2026-08-20"})
        assert resp.status_code == 200
        assert a.date == date_type(2026, 8, 20)


# ============================================================================
# POST /api/admin/flights/departures — create_admin_departure
# ============================================================================

class TestCreateDeparture:
    def teardown_method(self):
        _clear()

    _payload = dict(
        date="2026-09-01",
        flight_number="ezy1234",
        airline_code="ezy",
        airline_name="easyJet",
        departure_time="07:30",
        destination_code="agp",
        destination_name="Malaga",
        capacity_tier=6,
    )

    def test_H_creates_uppercase_codes(self):
        added = []
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None  # no duplicate
        db.query.return_value = chain
        def _add(obj):
            obj.id = 100
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override(db)
        resp = TestClient(app).post("/api/admin/flights/departures", json=self._payload)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["departure"]["flight_number"] == "EZY1234"  # uppercased
        assert body["departure"]["airline_code"] == "EZY"
        assert body["departure"]["destination_code"] == "AGP"

    def test_U_duplicate_returns_400(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = _departure()  # duplicate found
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).post("/api/admin/flights/departures", json=self._payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_U_invalid_capacity_tier(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        _override(db)
        payload = dict(self._payload, capacity_tier=3)  # invalid (must be 0,2,4,6,8)
        resp = TestClient(app).post("/api/admin/flights/departures", json=payload)
        assert resp.status_code == 400
        assert "capacity tier" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("tier", [0, 2, 4, 6, 8])
    def test_B_all_valid_capacity_tiers(self, tier):
        added = []
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        def _add(obj):
            obj.id = 99
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override(db)
        payload = dict(self._payload, capacity_tier=tier)
        resp = TestClient(app).post("/api/admin/flights/departures", json=payload)
        assert resp.status_code == 201

    def test_U_missing_required_field_returns_422(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).post("/api/admin/flights/departures",
                                    json={"date": "2026-09-01"})
        assert resp.status_code == 422


# ============================================================================
# POST /api/admin/flights/arrivals — create_admin_arrival
# ============================================================================

class TestCreateArrival:
    def teardown_method(self):
        _clear()

    _payload = dict(
        date="2026-09-08",
        flight_number="ezy1235",
        airline_code="ezy",
        airline_name="easyJet",
        arrival_time="22:30",
        origin_code="agp",
        origin_name="Malaga",
        departure_time="20:00",
    )

    def test_H_creates(self):
        added = []
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        def _add(obj):
            obj.id = 101
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override(db)
        resp = TestClient(app).post("/api/admin/flights/arrivals", json=self._payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["arrival"]["flight_number"] == "EZY1235"
        assert body["arrival"]["origin_code"] == "AGP"
        assert body["arrival"]["arrival_time"] == "22:30"

    def test_U_duplicate_returns_400(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = _arrival()
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).post("/api/admin/flights/arrivals", json=self._payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_E_no_departure_time_optional(self):
        added = []
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        def _add(obj):
            obj.id = 102
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override(db)
        payload = dict(self._payload)
        payload.pop("departure_time")
        resp = TestClient(app).post("/api/admin/flights/arrivals", json=payload)
        assert resp.status_code == 201
        assert resp.json()["arrival"]["departure_time"] is None


# ============================================================================
# DELETE /api/admin/flights/departures/{id} — delete_admin_departure
# ============================================================================

class TestDeleteDeparture:
    def teardown_method(self):
        _clear()

    # Latent bug: main.py:13942 references `FlightDepartureHistory` which is
    # never imported. The happy-path delete would NameError in prod. The
    # blocked-when-linked-bookings test below still passes because the
    # HTTPException short-circuits before reaching the broken line.

    def test_U_not_found(self):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).delete("/api/admin/flights/departures/99999")
        assert resp.status_code == 404

    def test_U_blocked_when_linked_bookings_exist(self):
        d = _departure()
        db = MagicMock()
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            if name == "FlightDeparture":
                chain.first.return_value = d
            elif name == "Booking":
                chain.count.return_value = 3
            return chain
        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).delete(f"/api/admin/flights/departures/{d.id}")
        assert resp.status_code == 400
        assert "3 booking" in resp.json()["detail"]


# ============================================================================
# DELETE /api/admin/flights/arrivals/{id} — delete_admin_arrival
# ============================================================================

class TestDeleteArrival:
    def teardown_method(self):
        _clear()

    # Latent bug: main.py:13992 references `FlightArrivalHistory` which is
    # never imported (same shape as the departures bug above).

    def test_U_not_found(self):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).delete("/api/admin/flights/arrivals/99999")
        assert resp.status_code == 404

    def test_U_blocked_when_linked_bookings_exist(self):
        a = _arrival()
        db = MagicMock()
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            if name == "FlightArrival":
                chain.first.return_value = a
            elif name == "Booking":
                chain.count.return_value = 5
            return chain
        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).delete(f"/api/admin/flights/arrivals/{a.id}")
        assert resp.status_code == 400
        assert "5 booking" in resp.json()["detail"]
