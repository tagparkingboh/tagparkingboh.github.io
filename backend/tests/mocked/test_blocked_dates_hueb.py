"""
HUEB tests for blocked-dates + blocked-time-slots admin CRUD and the
public /api/blocked-dates/check.

Endpoints covered:
  GET    /api/admin/blocked-dates
  POST   /api/admin/blocked-dates
  PUT    /api/admin/blocked-dates/{id}
  DELETE /api/admin/blocked-dates/{id}
  GET    /api/admin/blocked-dates/{id}/time-slots
  POST   /api/admin/blocked-dates/{id}/time-slots
  PUT    /api/admin/blocked-time-slots/{id}
  GET    /api/blocked-dates/check  (public)
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


def _bd(**kw):
    base = dict(
        id=10,
        start_date=date_type(2026, 6, 1),
        end_date=date_type(2026, 6, 7),
        block_dropoffs=True,
        block_pickups=True,
        reason="Maintenance",
        created_by="admin@tag.test",
        created_at=datetime(2026, 5, 1, 9, 0),
        updated_at=None,
        time_slots=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _slot(**kw):
    base = dict(
        id=100,
        blocked_date_id=10,
        start_time=time(10, 0),
        end_time=time(12, 0),
        block_dropoffs=True,
        block_pickups=True,
        reason=None,
        created_at=datetime(2026, 5, 1),
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# GET /api/admin/blocked-dates
# ============================================================================

class TestListBlockedDates:
    def teardown_method(self):
        _clear()

    def _wire(self, blocked_dates):
        db = MagicMock()
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = blocked_dates
        db.query.return_value = chain
        return db

    def test_H_returns_blocked_dates(self):
        _override(self._wire([_bd()]))
        resp = TestClient(app).get("/api/admin/blocked-dates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["blocked_dates"]) == 1

    def test_H_filter_by_date_range(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/blocked-dates?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200

    def test_H_with_time_slots(self):
        bd = _bd()
        bd.time_slots = [_slot()]
        _override(self._wire([bd]))
        resp = TestClient(app).get("/api/admin/blocked-dates")
        assert resp.status_code == 200
        assert len(resp.json()["blocked_dates"][0]["time_slots"]) == 1

    def test_U_invalid_date_from(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/blocked-dates?date_from=bogus")
        assert resp.status_code == 422

    def test_E_empty(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/admin/blocked-dates")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ============================================================================
# POST /api/admin/blocked-dates
# ============================================================================

class TestCreateBlockedDate:
    def teardown_method(self):
        _clear()

    def _wire(self):
        db = MagicMock()
        def _add(obj):
            obj.id = 99
            obj.created_at = datetime(2026, 5, 1)
            obj.updated_at = None
            obj.created_by = "admin@tag.test"
            obj.time_slots = []
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_creates(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/blocked-dates", json={
            "start_date": "2026-07-01", "end_date": "2026-07-07", "reason": "Holiday",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_U_end_before_start(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/blocked-dates", json={
            "start_date": "2026-07-07", "end_date": "2026-07-01",
        })
        assert resp.status_code == 422
        assert "end date" in resp.json()["detail"].lower()

    def test_U_neither_blocked(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/blocked-dates", json={
            "start_date": "2026-07-01", "end_date": "2026-07-07",
            "block_dropoffs": False, "block_pickups": False,
        })
        assert resp.status_code == 422

    def test_U_invalid_date_format(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/blocked-dates", json={
            "start_date": "07/01/2026", "end_date": "07/07/2026",
        })
        assert resp.status_code == 422

    def test_B_single_day_block(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/blocked-dates", json={
            "start_date": "2026-07-01", "end_date": "2026-07-01",
        })
        assert resp.status_code == 200


# ============================================================================
# PUT /api/admin/blocked-dates/{id}
# ============================================================================

class TestUpdateBlockedDate:
    def teardown_method(self):
        _clear()

    def _wire(self, bd):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bd
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_update_reason(self):
        bd = _bd()
        _override(self._wire(bd))
        resp = TestClient(app).put(f"/api/admin/blocked-dates/{bd.id}",
                                   json={"reason": "New reason"})
        assert resp.status_code == 200
        assert bd.reason == "New reason"

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).put("/api/admin/blocked-dates/99999", json={"reason": "x"})
        assert resp.status_code == 404

    def test_U_end_before_start_after_update(self):
        bd = _bd()
        _override(self._wire(bd))
        resp = TestClient(app).put(f"/api/admin/blocked-dates/{bd.id}",
                                   json={"end_date": "2026-05-01"})  # before start
        assert resp.status_code == 422

    def test_U_neither_blocked_after_update(self):
        bd = _bd()
        _override(self._wire(bd))
        resp = TestClient(app).put(f"/api/admin/blocked-dates/{bd.id}",
                                   json={"block_dropoffs": False, "block_pickups": False})
        assert resp.status_code == 422

    def test_E_update_dates(self):
        bd = _bd()
        _override(self._wire(bd))
        resp = TestClient(app).put(f"/api/admin/blocked-dates/{bd.id}",
                                   json={"start_date": "2026-06-10", "end_date": "2026-06-12"})
        assert resp.status_code == 200
        assert bd.start_date == date_type(2026, 6, 10)


# ============================================================================
# DELETE /api/admin/blocked-dates/{id}
# ============================================================================

class TestDeleteBlockedDate:
    def teardown_method(self):
        _clear()

    def _wire(self, bd):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bd
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes(self):
        bd = _bd()
        _override(self._wire(bd))
        resp = TestClient(app).delete(f"/api/admin/blocked-dates/{bd.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).delete("/api/admin/blocked-dates/99999")
        assert resp.status_code == 404


# ============================================================================
# GET /api/admin/blocked-dates/{id}/time-slots
# ============================================================================

class TestGetTimeSlots:
    def teardown_method(self):
        _clear()

    def _wire(self, blocked_date, time_slots):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            name = model.__name__
            if name == "BlockedDate":
                chain.first.return_value = blocked_date
            elif name == "BlockedTimeSlot":
                chain.all.return_value = time_slots
            return chain
        db.query.side_effect = _query
        return db

    def test_H_returns_slots(self):
        _override(self._wire(_bd(), [_slot()]))
        resp = TestClient(app).get("/api/admin/blocked-dates/10/time-slots")
        assert resp.status_code == 200
        assert len(resp.json()["time_slots"]) == 1

    def test_U_blocked_date_not_found(self):
        _override(self._wire(None, []))
        resp = TestClient(app).get("/api/admin/blocked-dates/9999/time-slots")
        assert resp.status_code == 404

    def test_E_no_slots(self):
        _override(self._wire(_bd(), []))
        resp = TestClient(app).get("/api/admin/blocked-dates/10/time-slots")
        assert resp.status_code == 200
        assert resp.json()["time_slots"] == []


# ============================================================================
# POST /api/admin/blocked-dates/{id}/time-slots
# ============================================================================

class TestCreateTimeSlot:
    def teardown_method(self):
        _clear()

    def _wire(self, blocked_date, overlap=None):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__
            if name == "BlockedDate":
                chain.first.return_value = blocked_date
            elif name == "BlockedTimeSlot":
                chain.first.return_value = overlap
            return chain
        db.query.side_effect = _query
        added = []
        def _add(obj):
            obj.id = 50
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_creates(self):
        _override(self._wire(_bd()))
        resp = TestClient(app).post("/api/admin/blocked-dates/10/time-slots", json={
            "start_time": "10:00", "end_time": "12:00",
        })
        assert resp.status_code == 200

    def test_U_blocked_date_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/blocked-dates/9999/time-slots", json={
            "start_time": "10:00", "end_time": "12:00",
        })
        assert resp.status_code == 404

    def test_U_bad_time_format(self):
        _override(self._wire(_bd()))
        resp = TestClient(app).post("/api/admin/blocked-dates/10/time-slots", json={
            "start_time": "bogus", "end_time": "12:00",
        })
        assert resp.status_code == 400

    def test_U_start_after_end(self):
        _override(self._wire(_bd()))
        resp = TestClient(app).post("/api/admin/blocked-dates/10/time-slots", json={
            "start_time": "12:00", "end_time": "10:00",
        })
        assert resp.status_code == 400

    def test_U_neither_blocked(self):
        _override(self._wire(_bd()))
        resp = TestClient(app).post("/api/admin/blocked-dates/10/time-slots", json={
            "start_time": "10:00", "end_time": "12:00",
            "block_dropoffs": False, "block_pickups": False,
        })
        assert resp.status_code == 400

    def test_U_overlapping_slot(self):
        overlap = _slot(start_time=time(11, 0), end_time=time(13, 0))
        _override(self._wire(_bd(), overlap=overlap))
        resp = TestClient(app).post("/api/admin/blocked-dates/10/time-slots", json={
            "start_time": "10:00", "end_time": "12:00",
        })
        assert resp.status_code == 400
        assert "overlap" in resp.json()["detail"].lower()


# ============================================================================
# PUT /api/admin/blocked-time-slots/{id}
# ============================================================================

class TestUpdateTimeSlot:
    def teardown_method(self):
        _clear()

    def _wire(self, slot, overlap=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            # First query returns the slot, second is overlap check
            chain.first.return_value = slot if calls["n"] == 1 else overlap
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_update_time(self):
        s = _slot()
        _override(self._wire(s))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "start_time": "14:00", "end_time": "16:00",
        })
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).put("/api/admin/blocked-time-slots/9999", json={"reason": "x"})
        assert resp.status_code == 404

    def test_U_bad_start_time(self):
        s = _slot()
        _override(self._wire(s))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "start_time": "bogus",
        })
        assert resp.status_code == 400

    def test_U_bad_end_time(self):
        s = _slot()
        _override(self._wire(s))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "end_time": "bogus",
        })
        assert resp.status_code == 400

    def test_U_start_after_end(self):
        s = _slot()
        _override(self._wire(s))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "start_time": "16:00", "end_time": "14:00",
        })
        assert resp.status_code == 400

    def test_U_overlap(self):
        s = _slot()
        overlap = _slot(id=101, start_time=time(15, 0), end_time=time(17, 0))
        _override(self._wire(s, overlap=overlap))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "start_time": "14:00", "end_time": "16:00",
        })
        assert resp.status_code == 400

    def test_U_neither_blocked(self):
        s = _slot()
        _override(self._wire(s))
        resp = TestClient(app).put(f"/api/admin/blocked-time-slots/{s.id}", json={
            "block_dropoffs": False, "block_pickups": False,
        })
        assert resp.status_code == 400


# ============================================================================
# GET /api/blocked-dates/check (public)
# ============================================================================

class TestCheckBlockedDate:
    def teardown_method(self):
        _clear()

    def _wire_db(self, blocked_for_first=None, all_blocked=None):
        """blocked_for_first: returned by .first() (single-date check).
        all_blocked: returned by .all() (date-range check)."""
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = blocked_for_first
        chain.all.return_value = all_blocked or []
        db.query.return_value = chain
        # public endpoint — no auth override
        def gen():
            yield db
        app.dependency_overrides[get_db] = gen
        return db

    # ---- Date-range branch ----

    def test_H_date_range_returns_blocked_dates(self):
        bd = _bd()
        bd.time_slots = []
        self._wire_db(all_blocked=[bd])
        resp = TestClient(app).get("/api/blocked-dates/check?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200
        assert len(resp.json()["blocked_dates"]) == 1

    def test_H_date_range_with_time_slots(self):
        bd = _bd()
        bd.time_slots = [_slot()]
        self._wire_db(all_blocked=[bd])
        resp = TestClient(app).get("/api/blocked-dates/check?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200
        assert len(resp.json()["blocked_dates"][0]["time_slots"]) == 1

    def test_E_date_range_empty(self):
        self._wire_db(all_blocked=[])
        resp = TestClient(app).get("/api/blocked-dates/check?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200
        assert resp.json()["blocked_dates"] == []

    # ---- Single-date checks ----

    def test_H_dropoff_blocked_no_time_slots(self):
        bd = _bd(time_slots=[])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dropoff_blocked"] is True
        assert body["dropoff_reason"] == "Maintenance"

    def test_E_no_blocking_for_date(self):
        self._wire_db(blocked_for_first=None)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is False

    def test_H_dropoff_blocked_inside_time_slot(self):
        slot = _slot(start_time=time(10, 0), end_time=time(12, 0), block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03&dropoff_time=10:30")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is True

    def test_E_dropoff_not_blocked_outside_time_slot(self):
        slot = _slot(start_time=time(10, 0), end_time=time(12, 0), block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03&dropoff_time=08:00")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is False

    def test_E_bad_time_format_treated_as_not_blocked(self):
        slot = _slot(start_time=time(10, 0), end_time=time(12, 0), block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03&dropoff_time=bogus")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is False

    def test_E_no_time_but_slots_exist_check_any_blocks(self):
        """When time is omitted but slots exist, the helper says blocked if
        ANY slot blocks the type."""
        slot = _slot(block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is True

    def test_H_pickup_blocked_branch(self):
        bd = _bd(time_slots=[])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?pickup_date=2026-06-05")
        assert resp.status_code == 200
        assert resp.json()["pickup_blocked"] is True

    def test_B_time_at_slot_start_is_blocked(self):
        """check_time == slot.start_time should hit (start_time <= check_time)."""
        slot = _slot(start_time=time(10, 0), end_time=time(12, 0), block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03&dropoff_time=10:00")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is True

    def test_B_time_at_slot_end_is_not_blocked(self):
        """check_time == slot.end_time is exclusive (check_time < end_time)."""
        slot = _slot(start_time=time(10, 0), end_time=time(12, 0), block_dropoffs=True)
        bd = _bd(time_slots=[slot])
        self._wire_db(blocked_for_first=bd)
        resp = TestClient(app).get("/api/blocked-dates/check?dropoff_date=2026-06-03&dropoff_time=12:00")
        assert resp.status_code == 200
        assert resp.json()["dropoff_blocked"] is False
