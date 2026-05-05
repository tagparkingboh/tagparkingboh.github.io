"""
Mocked-integration tests for the v3 per-shift action endpoints.

Phase 2 endpoints (locked 2026-05-04, see backend/docs/SPEC.md):
  POST   /api/roster/{id}/duplicate
  POST   /api/roster/{id}/merge
  POST   /api/roster/{id}/split
  PATCH  /api/roster/{id}/unassign

Per the SPEC test rule (2026-04-21 lesson), every test uses TestClient(app)
and imports from main so coverage actually moves on routers/roster.py.

Boundary coverage (per the user's standing 'test boundaries — times, days,
dates' rule): every time/date rule has t-ε / t / t+ε cases including
wrap-around (cross-midnight, month, year, DST).
"""
import sys
from pathlib import Path
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app
from database import get_db
from routers.roster import require_admin
from db_models import RosterShift, Booking, ShiftBookingLink, ShiftType, ShiftStatus, User


# =============================================================================
# Test rig — DB mock + dependency overrides
# =============================================================================

ADMIN_USER = MagicMock(id=1, is_admin=True, is_active=True, first_name="Admin", last_name="User")


def make_user(*, id, first_name="Karl", last_name="Walden", driver_type="jockey", active=True):
    u = MagicMock()
    u.id = id
    u.first_name = first_name
    u.last_name = last_name
    u.driver_type = driver_type
    u.is_active = active
    u.is_admin = False
    return u


def make_shift(
    *,
    id=1,
    staff_id=10,
    shift_date=None,
    end_date=None,
    start_time=time(9, 0),
    end_time=time(17, 0),
    bookings=None,
    created_source="manual",
    intended_driver_type="jockey",
    notes=None,
):
    s = MagicMock(spec=RosterShift)
    s.id = id
    s.staff_id = staff_id
    s.staff = make_user(id=staff_id) if staff_id else None
    s.booking_id = None
    s.date = shift_date or date(2026, 5, 10)
    s.end_date = end_date
    s.start_time = start_time
    s.end_time = end_time
    s.shift_type = ShiftType.MORNING
    s.status = ShiftStatus.SCHEDULED
    s.notes = notes
    s.intended_driver_type = intended_driver_type
    s.created_source = created_source
    s.bookings = bookings or []
    s.created_at = datetime(2026, 5, 1)
    s.updated_at = None
    return s


def make_booking(*, id, ref, dropoff_dt=None, pickup_dt=None, flight_arrival_time=None):
    b = MagicMock(spec=Booking)
    b.id = id
    b.reference = ref
    b.status = MagicMock(value="confirmed")
    b.dropoff_date = dropoff_dt.date() if dropoff_dt else None
    b.dropoff_time = dropoff_dt.time() if dropoff_dt else None
    b.pickup_date = pickup_dt.date() if pickup_dt else None
    b.pickup_time = pickup_dt.time() if pickup_dt else None
    b.flight_arrival_time = flight_arrival_time
    b.customer_first_name = "Test"
    b.customer_last_name = "Customer"
    b.dropoff_flight_number = None
    b.dropoff_destination = None
    b.dropoff_airline_name = None
    b.flight_departure_time = None
    b.pickup_flight_number = None
    b.pickup_origin = None
    b.pickup_airline_name = None
    return b


@pytest.fixture
def rig():
    """A reusable rig: configurable shift / booking lookup tables, captures
    db.add / db.delete / db.commit for assertions."""
    state = {
        "shifts_by_id": {},
        "bookings_by_id": {},
        "users_by_id": {},
        "shift_links_by_shift": {},   # shift_id -> list of MagicMock links
        "added": [],
        "deleted": [],
        "committed": False,
        "overlap_returns": None,      # set per-test to force check_shift_overlap result
    }

    def make_chain_for(model):
        # chain-local filter args list — scoped to a single .query() call so
        # one query's filter doesn't leak into the next query's .first().
        local_args: list[tuple] = []
        chain = MagicMock()
        chain.order_by.return_value = chain

        def filter_wrap(*args, **kwargs):
            local_args.append(args)
            return chain
        chain.filter.side_effect = filter_wrap

        def lookup_id():
            for args in reversed(local_args):
                for arg in args:
                    target_id = getattr(getattr(arg, "right", None), "value", None)
                    if target_id is not None:
                        return target_id
            return None

        if model is RosterShift:
            def first_shift():
                tid = lookup_id()
                return state["shifts_by_id"].get(tid) if tid is not None else None
            chain.first.side_effect = first_shift

            def all_shifts():
                # When a filter is keyed off staff_id, narrow to that staff.
                # Otherwise return everything (used by overlap-detection in tests
                # that explicitly want to exercise the conflict path).
                staff_id_targets = []
                for args in local_args:
                    for arg in args:
                        col = getattr(getattr(arg, "left", None), "key", None)
                        val = getattr(getattr(arg, "right", None), "value", None)
                        if col == "staff_id":
                            staff_id_targets.append(val)
                if staff_id_targets:
                    target = staff_id_targets[-1]
                    return [s for s in state["shifts_by_id"].values()
                            if getattr(s, "staff_id", None) == target]
                return list(state["shifts_by_id"].values())
            chain.all.side_effect = all_shifts
        elif model is Booking:
            def first_booking():
                tid = lookup_id()
                return state["bookings_by_id"].get(tid) if tid is not None else None
            chain.first.side_effect = first_booking
            chain.all.side_effect = lambda: list(state["bookings_by_id"].values())
        elif model is User:
            def first_user():
                tid = lookup_id()
                return state["users_by_id"].get(tid) if tid is not None else None
            chain.first.side_effect = first_user
        elif model is ShiftBookingLink:
            chain.first.return_value = None

            def links_for():
                # Return links for the most recently filtered shift_id, if any.
                shift_id_targets = []
                for args in local_args:
                    for arg in args:
                        col = getattr(getattr(arg, "left", None), "key", None)
                        val = getattr(getattr(arg, "right", None), "value", None)
                        if col == "shift_id":
                            shift_id_targets.append(val)
                if shift_id_targets:
                    return list(state["shift_links_by_shift"].get(shift_id_targets[-1], []))
                return _all_links(state)
            chain.all.side_effect = links_for
            chain.delete.side_effect = lambda: 0
        else:
            chain.first.return_value = None
            chain.all.return_value = []
        return chain

    def query_side_effect(model):
        return make_chain_for(model)

    db = MagicMock()
    db.query.side_effect = query_side_effect

    def add(obj):
        state["added"].append(obj)
        # New RosterShift rows: synthesise the DB-side fields the response
        # model requires (id, created_at) so RosterShiftResponse validates.
        if isinstance(obj, RosterShift):
            if not getattr(obj, "id", None):
                obj.id = 9000 + len(state["added"])
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime(2026, 5, 4, 12, 0)
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = None
            # Hydrate the staff relationship so shift_to_response() can read
            # staff.first_name / last_name without hitting the DB.
            staff_id = getattr(obj, "staff_id", None)
            if staff_id is not None and staff_id in state["users_by_id"]:
                obj.staff = state["users_by_id"][staff_id]
            elif staff_id is None:
                obj.staff = None
            else:
                obj.staff = make_user(id=staff_id)
            if not hasattr(obj, "bookings") or obj.bookings is None:
                obj.bookings = []
            state["shifts_by_id"][obj.id] = obj

    db.add.side_effect = add
    db.delete.side_effect = lambda obj: state["deleted"].append(obj)
    db.flush.return_value = None

    def commit():
        state["committed"] = True
    db.commit.side_effect = commit
    db.refresh.return_value = None

    def _mock_get_db():
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    try:
        client = TestClient(app)
        yield client, db, state
    finally:
        app.dependency_overrides.clear()


def _next_shift_match(state):
    """Look at the latest filter args and try to find an id match."""
    for model, args in reversed(state["last_filter_args"]):
        if model is not RosterShift:
            continue
        for arg in args:
            # SQLAlchemy filter args are BinaryExpression — try to read .right.value
            target_id = getattr(getattr(arg, "right", None), "value", None)
            if target_id and target_id in state["shifts_by_id"]:
                return state["shifts_by_id"][target_id]
    return None


def _next_booking_match(state):
    for model, args in reversed(state["last_filter_args"]):
        if model is not Booking:
            continue
        for arg in args:
            target_id = getattr(getattr(arg, "right", None), "value", None)
            if target_id and target_id in state["bookings_by_id"]:
                return state["bookings_by_id"][target_id]
    return None


def _next_user_match(state):
    for model, args in reversed(state["last_filter_args"]):
        if model is not User:
            continue
        for arg in args:
            target_id = getattr(getattr(arg, "right", None), "value", None)
            if target_id and target_id in state["users_by_id"]:
                return state["users_by_id"][target_id]
    return None


def _all_links(state):
    out = []
    for links in state["shift_links_by_shift"].values():
        out.extend(links)
    return out


# =============================================================================
# Duplicate — Happy
# =============================================================================

class TestDuplicateDateCopyHappy:

    def test_target_date_copy_creates_one_row_with_same_staff(self, rig):
        client, db, state = rig
        src = make_shift(id=42, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][42] = src

        r = client.post("/api/roster/42/duplicate", json={"target_date": "2026-05-17"})

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        copy = body[0]
        assert copy["date"] == "2026-05-17"
        assert copy["staff_id"] == 10
        assert copy["start_time"] == "09:00"
        assert copy["end_time"] == "17:00"

    def test_overnight_source_copy_shifts_end_date(self, rig):
        client, db, state = rig
        # Source 22:00 on 9th → 02:00 on 10th
        src = make_shift(
            id=50, staff_id=10,
            shift_date=date(2026, 5, 9), end_date=date(2026, 5, 10),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        state["shifts_by_id"][50] = src

        r = client.post("/api/roster/50/duplicate", json={"target_date": "2026-05-11"})

        assert r.status_code == 200, r.text
        copy = r.json()[0]
        assert copy["date"] == "2026-05-11"
        # end_date shifted by the same delta — 9th→10th becomes 11th→12th.
        assert copy["end_date"] == "2026-05-12"

    def test_target_equal_source_creates_literal_copy(self, rig):
        """Boundary: target_date == source.date → still creates a copy."""
        client, db, state = rig
        src = make_shift(id=60, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][60] = src

        r = client.post("/api/roster/60/duplicate", json={"target_date": "2026-05-10"})
        assert r.status_code == 200, r.text
        assert r.json()[0]["date"] == "2026-05-10"


class TestDuplicateDateCopyDateBoundaries:
    """t-ε / t / t+ε across month / year / DST transitions."""

    @pytest.mark.parametrize("source_date,target_date,expected_date", [
        # Month rollover
        (date(2026, 5, 31), date(2026, 6, 1), "2026-06-01"),
        # Year rollover
        (date(2026, 12, 31), date(2027, 1, 1), "2027-01-01"),
        # DST forward — 2026-03-29 BST starts; copy across the transition
        (date(2026, 3, 28), date(2026, 3, 29), "2026-03-29"),
        # DST back — 2026-10-25 BST ends; copy across the transition
        (date(2026, 10, 24), date(2026, 10, 25), "2026-10-25"),
    ])
    def test_target_date_across_calendar_boundaries(self, rig, source_date, target_date, expected_date):
        client, db, state = rig
        src = make_shift(id=70, staff_id=10, shift_date=source_date)
        state["shifts_by_id"][70] = src

        r = client.post("/api/roster/70/duplicate", json={"target_date": target_date.isoformat()})
        assert r.status_code == 200, r.text
        assert r.json()[0]["date"] == expected_date


class TestDuplicateStaffFanoutHappy:

    def test_two_staff_ids_produces_two_copies(self, rig):
        client, db, state = rig
        src = make_shift(id=80, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][80] = src
        state["users_by_id"][20] = make_user(id=20, first_name="Marek", last_name="Smolarek", driver_type="jockey")
        state["users_by_id"][30] = make_user(id=30, first_name="Karl", last_name="Walden", driver_type="jockey")

        r = client.post("/api/roster/80/duplicate", json={"staff_ids": [20, 30]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 2
        assert {b["staff_id"] for b in body} == {20, 30}
        assert all(b["date"] == "2026-05-10" for b in body)

    def test_unassigned_jockey_flag_creates_one_unassigned_copy(self, rig):
        client, db, state = rig
        src = make_shift(id=90, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][90] = src
        r = client.post("/api/roster/90/duplicate", json={"add_unassigned_jockey": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["staff_id"] is None
        assert body[0]["intended_driver_type"] == "jockey"

    def test_unassigned_fleet_flag_tags_intended_fleet(self, rig):
        client, db, state = rig
        src = make_shift(id=91, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][91] = src
        r = client.post("/api/roster/91/duplicate", json={"add_unassigned_fleet": True})
        assert r.status_code == 200, r.text
        assert r.json()[0]["intended_driver_type"] == "fleet"


# =============================================================================
# Duplicate — Unhappy / Edge
# =============================================================================

class TestDuplicateUnhappy:

    def test_source_not_found_returns_404(self, rig):
        client, db, state = rig
        r = client.post("/api/roster/9999/duplicate", json={"target_date": "2026-05-17"})
        assert r.status_code == 404

    def test_both_modes_set_returns_422(self, rig):
        client, db, state = rig
        src = make_shift(id=100, staff_id=10)
        state["shifts_by_id"][100] = src
        state["users_by_id"][20] = make_user(id=20)
        r = client.post(
            "/api/roster/100/duplicate",
            json={"target_date": "2026-05-17", "staff_ids": [20]},
        )
        assert r.status_code == 422

    def test_neither_mode_set_returns_422(self, rig):
        client, db, state = rig
        src = make_shift(id=101, staff_id=10)
        state["shifts_by_id"][101] = src
        r = client.post("/api/roster/101/duplicate", json={})
        assert r.status_code == 422


class TestDuplicateStaffFanoutEdge:

    def test_source_staff_in_target_list_is_skipped(self, rig):
        """Edge: tick source's own staff_id → de-duped, not double-written."""
        client, db, state = rig
        src = make_shift(id=110, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][110] = src
        state["users_by_id"][20] = make_user(id=20, driver_type="jockey")

        r = client.post("/api/roster/110/duplicate", json={"staff_ids": [10, 20]})
        assert r.status_code == 200, r.text
        body = r.json()
        # Only staff 20 was a fresh target — 10 == source, skipped.
        assert {b["staff_id"] for b in body} == {20}

    def test_only_source_staff_in_targets_raises_422(self, rig):
        """Edge: only the source's own staff_id → no effective targets → 422."""
        client, db, state = rig
        src = make_shift(id=111, staff_id=10)
        state["shifts_by_id"][111] = src
        r = client.post("/api/roster/111/duplicate", json={"staff_ids": [10]})
        assert r.status_code == 422


# =============================================================================
# Merge — Happy
# =============================================================================

class TestMergeHappy:

    def test_adjacent_same_staff_merges(self, rig):
        client, db, state = rig
        a = make_shift(
            id=200, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=201, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(12, 0), end_time=time(14, 0),
        )
        state["shifts_by_id"][200] = a
        state["shifts_by_id"][201] = b
        state["users_by_id"][10] = make_user(id=10, driver_type="jockey")

        r = client.post("/api/roster/200/merge", json={"other_shift_id": 201})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["start_time"] == "09:00"
        assert body["end_time"] == "14:00"

    def test_overnight_pair_merges_across_midnight(self, rig):
        """A 22:00–00:00 (9th→10th) + B 00:00–02:00 (10th) → 22:00–02:00 (9th→10th)."""
        client, db, state = rig
        a = make_shift(
            id=210, staff_id=10,
            shift_date=date(2026, 5, 9), end_date=date(2026, 5, 10),
            start_time=time(22, 0), end_time=time(0, 0),
        )
        b = make_shift(
            id=211, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(0, 0), end_time=time(2, 0),
        )
        state["shifts_by_id"][210] = a
        state["shifts_by_id"][211] = b
        state["users_by_id"][10] = make_user(id=10)

        r = client.post("/api/roster/210/merge", json={"other_shift_id": 211})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["start_time"] == "22:00"
        assert body["end_time"] == "02:00"
        assert body["end_date"] == "2026-05-10"


class TestMergeUnhappy:

    def test_one_shift_missing_returns_404(self, rig):
        client, db, state = rig
        a = make_shift(id=220, staff_id=10)
        state["shifts_by_id"][220] = a
        r = client.post("/api/roster/220/merge", json={"other_shift_id": 9999})
        assert r.status_code == 404

    def test_self_merge_returns_422(self, rig):
        client, db, state = rig
        a = make_shift(id=221, staff_id=10)
        state["shifts_by_id"][221] = a
        r = client.post("/api/roster/221/merge", json={"other_shift_id": 221})
        assert r.status_code == 422

    def test_different_staff_returns_422(self, rig):
        client, db, state = rig
        a = make_shift(
            id=222, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=223, staff_id=99, shift_date=date(2026, 5, 10),
            start_time=time(12, 0), end_time=time(14, 0),
        )
        state["shifts_by_id"][222] = a
        state["shifts_by_id"][223] = b
        r = client.post("/api/roster/222/merge", json={"other_shift_id": 223})
        assert r.status_code == 422


class TestMergeAdjacencyBoundary:
    """t-ε / t / t+ε at the 0-minute gap rule."""

    def test_gap_zero_minutes_merges(self, rig):
        client, db, state = rig
        a = make_shift(
            id=230, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=231, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(12, 0), end_time=time(14, 0),
        )
        state["shifts_by_id"][230] = a
        state["shifts_by_id"][231] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/230/merge", json={"other_shift_id": 231})
        assert r.status_code == 200, r.text

    def test_gap_one_minute_returns_422(self, rig):
        client, db, state = rig
        a = make_shift(
            id=232, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=233, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(12, 1), end_time=time(14, 0),
        )
        state["shifts_by_id"][232] = a
        state["shifts_by_id"][233] = b
        r = client.post("/api/roster/232/merge", json={"other_shift_id": 233})
        assert r.status_code == 422

    def test_overlap_returns_422(self, rig):
        client, db, state = rig
        a = make_shift(
            id=234, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(13, 0),
        )
        b = make_shift(
            id=235, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(12, 0), end_time=time(14, 0),
        )
        state["shifts_by_id"][234] = a
        state["shifts_by_id"][235] = b
        r = client.post("/api/roster/234/merge", json={"other_shift_id": 235})
        assert r.status_code == 422


# =============================================================================
# Split — Happy + Boundaries
# =============================================================================

class TestSplitHappy:

    def test_midpoint_split_creates_two_halves(self, rig):
        client, db, state = rig
        s = make_shift(
            id=300, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][300] = s
        r = client.post("/api/roster/300/split", json={"split_at_time": "13:00"})
        assert r.status_code == 200, r.text
        halves = r.json()
        assert len(halves) == 2
        assert halves[0]["start_time"] == "09:00"
        assert halves[0]["end_time"] == "13:00"
        assert halves[1]["start_time"] == "13:00"
        assert halves[1]["end_time"] == "17:00"

    def test_overnight_split_at_midnight(self, rig):
        """22:00 on D → 02:00 on D+1, split at 00:00 → halves cross the day boundary."""
        client, db, state = rig
        s = make_shift(
            id=310, staff_id=10,
            shift_date=date(2026, 5, 9), end_date=date(2026, 5, 10),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        state["shifts_by_id"][310] = s
        r = client.post("/api/roster/310/split", json={"split_at_time": "00:00"})
        assert r.status_code == 200, r.text
        halves = r.json()
        # First half: 22:00 on 9th → 00:00 on 10th
        assert halves[0]["date"] == "2026-05-09"
        assert halves[0]["end_date"] == "2026-05-10"
        assert halves[0]["start_time"] == "22:00"
        assert halves[0]["end_time"] == "00:00"
        # Second half: 00:00 on 10th → 02:00 on 10th
        assert halves[1]["date"] == "2026-05-10"
        assert halves[1]["start_time"] == "00:00"
        assert halves[1]["end_time"] == "02:00"


class TestSplitUnhappy:

    def test_shift_not_found_returns_404(self, rig):
        client, db, state = rig
        r = client.post("/api/roster/9999/split", json={"split_at_time": "13:00"})
        assert r.status_code == 404

    def test_split_at_start_time_returns_422(self, rig):
        client, db, state = rig
        s = make_shift(id=320, staff_id=10, start_time=time(9, 0), end_time=time(17, 0))
        state["shifts_by_id"][320] = s
        r = client.post("/api/roster/320/split", json={"split_at_time": "09:00"})
        assert r.status_code == 422

    def test_split_at_end_time_returns_422(self, rig):
        client, db, state = rig
        s = make_shift(id=321, staff_id=10, start_time=time(9, 0), end_time=time(17, 0))
        state["shifts_by_id"][321] = s
        r = client.post("/api/roster/321/split", json={"split_at_time": "17:00"})
        assert r.status_code == 422

    def test_split_outside_window_returns_422(self, rig):
        client, db, state = rig
        s = make_shift(id=322, staff_id=10, start_time=time(9, 0), end_time=time(17, 0))
        state["shifts_by_id"][322] = s
        r = client.post("/api/roster/322/split", json={"split_at_time": "20:00"})
        assert r.status_code == 422


class TestSplitTimeBoundary:
    """t-ε / t / t+ε at the start and end of the shift window."""

    def test_split_at_start_plus_one_minute_allowed(self, rig):
        client, db, state = rig
        s = make_shift(id=330, staff_id=10, start_time=time(9, 0), end_time=time(17, 0))
        state["shifts_by_id"][330] = s
        r = client.post("/api/roster/330/split", json={"split_at_time": "09:01"})
        assert r.status_code == 200, r.text

    def test_split_at_end_minus_one_minute_allowed(self, rig):
        client, db, state = rig
        s = make_shift(id=331, staff_id=10, start_time=time(9, 0), end_time=time(17, 0))
        state["shifts_by_id"][331] = s
        r = client.post("/api/roster/331/split", json={"split_at_time": "16:59"})
        assert r.status_code == 200, r.text


# =============================================================================
# Unassign
# =============================================================================

class TestUnassign:

    def test_assigned_shift_unassigns(self, rig):
        client, db, state = rig
        s = make_shift(id=400, staff_id=10)
        state["shifts_by_id"][400] = s
        r = client.patch("/api/roster/400/unassign")
        assert r.status_code == 200, r.text
        assert r.json()["staff_id"] is None

    def test_already_unassigned_is_idempotent(self, rig):
        client, db, state = rig
        s = make_shift(id=401, staff_id=None)
        state["shifts_by_id"][401] = s
        r = client.patch("/api/roster/401/unassign")
        assert r.status_code == 200, r.text
        assert r.json()["staff_id"] is None

    def test_not_found_returns_404(self, rig):
        client, db, state = rig
        r = client.patch("/api/roster/9999/unassign")
        assert r.status_code == 404
