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
from unittest.mock import MagicMock, patch

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
    s.suppressed_at = None
    s.suppressed_by_user_id = None
    s.suppression_reason = None
    s.parent_shift_id = None
    s.dependents_independent = False
    # Driver-trust pivot 2026-05-28: explicit NULL so admin_shaped_at
    # behaves like a fresh DB row (not a MagicMock auto-attribute) when
    # endpoints read it for stamp-or-not decisions.
    s.admin_shaped_at = None
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
                # Mirror the SQL filters the endpoint composes: when a filter
                # keys off staff_id, narrow to that staff; when a filter keys
                # off date (== exact match), narrow to that date too. Without
                # the date narrowing, check_shift_overlap sees ALL of a
                # staff's shifts at any date and false-409s tests that copy
                # to a different target_date.
                staff_id_targets = []
                date_targets = []
                for args in local_args:
                    for arg in args:
                        col = getattr(getattr(arg, "left", None), "key", None)
                        val = getattr(getattr(arg, "right", None), "value", None)
                        if col == "staff_id":
                            staff_id_targets.append(val)
                        elif col == "date":
                            date_targets.append(val)

                rows = list(state["shifts_by_id"].values())
                if staff_id_targets:
                    target = staff_id_targets[-1]
                    rows = [s for s in rows if getattr(s, "staff_id", None) == target]
                if date_targets:
                    target = date_targets[-1]
                    rows = [s for s in rows if getattr(s, "date", None) == target]
                return rows
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


class TestDuplicateDependencyPoolHUEB:

    def test_H_july_duplicate_stamps_parent_dependency_on_children(self, rig):
        client, db, state = rig
        booking = make_booking(id=700, ref="TAG-POOL700", dropoff_dt=datetime(2026, 7, 2, 9, 30))
        src = make_shift(id=7000, staff_id=10, shift_date=date(2026, 7, 2), bookings=[booking])
        state["shifts_by_id"][7000] = src
        state["bookings_by_id"][700] = booking
        state["users_by_id"][20] = make_user(id=20, first_name="Marek", last_name="Smolarek", driver_type="jockey")
        state["users_by_id"][30] = make_user(id=30, first_name="Fleet", last_name="Driver", driver_type="fleet")

        r = client.post("/api/roster/7000/duplicate", json={"staff_ids": [20, 30]})

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 2
        assert {row["parent_shift_id"] for row in body} == {7000}
        assert {row["dependents_independent"] for row in body} == {False}
        created_shifts = [obj for obj in state["added"] if isinstance(obj, RosterShift)]
        assert len(created_shifts) == 2
        assert all(s.parent_shift_id == 7000 for s in created_shifts)

    def test_H_june_shift_tailing_into_july_does_not_create_dependency(self, rig):
        client, db, state = rig
        src = make_shift(
            id=7001,
            staff_id=10,
            shift_date=date(2026, 6, 30),
            end_date=date(2026, 7, 1),
            start_time=time(22, 0),
            end_time=time(2, 0),
        )
        state["shifts_by_id"][7001] = src
        state["users_by_id"][20] = make_user(id=20)

        r = client.post("/api/roster/7001/duplicate", json={"staff_ids": [20]})

        assert r.status_code == 200, r.text
        assert r.json()[0]["parent_shift_id"] is None
        created_shift = next(obj for obj in state["added"] if isinstance(obj, RosterShift))
        assert created_shift.parent_shift_id is None

    def test_U_duplicate_rejects_self_parent_assignment(self, rig):
        client, db, state = rig
        src = make_shift(id=7010, staff_id=10, shift_date=date(2026, 7, 2))
        state["shifts_by_id"][7010] = src

        def add_with_source_id(obj):
            state["added"].append(obj)
            if isinstance(obj, RosterShift):
                obj.id = src.id
                obj.created_at = datetime(2026, 7, 1, 12, 0)
                obj.updated_at = None
                obj.staff = None
                obj.bookings = []
                state["shifts_by_id"][obj.id] = obj

        db.add.side_effect = add_with_source_id

        r = client.post("/api/roster/7010/duplicate", json={"add_unassigned_jockey": True})

        assert r.status_code == 409
        assert "own parent" in r.json()["detail"]
        db.rollback.assert_called()

    def test_U_duplicate_rejects_cycle_creating_assignment(self, rig):
        client, db, state = rig
        src = make_shift(id=7020, staff_id=10, shift_date=date(2026, 7, 2))
        state["shifts_by_id"][7020] = src

        def add_cycle_child(obj):
            state["added"].append(obj)
            if isinstance(obj, RosterShift):
                obj.id = 7021
                obj.created_at = datetime(2026, 7, 1, 12, 0)
                obj.updated_at = None
                obj.staff = None
                obj.bookings = []
                state["shifts_by_id"][obj.id] = obj
                src.parent_shift_id = obj.id

        db.add.side_effect = add_cycle_child

        r = client.post("/api/roster/7020/duplicate", json={"add_unassigned_jockey": True})

        assert r.status_code == 409
        assert "Cycle detected in roster shift dependency tree" in r.json()["detail"]
        db.rollback.assert_called()

    def test_H_toggle_false_resyncs_children(self, rig):
        client, db, state = rig
        parent = make_shift(id=7002, shift_date=date(2026, 7, 2))
        parent.dependents_independent = True
        state["shifts_by_id"][7002] = parent

        with patch("routers.roster.sync_shift_pool_from_parent", return_value=[7003]) as sync:
            r = client.patch(
                "/api/roster/7002/dependents-independent",
                json={"dependents_independent": False},
            )

        assert r.status_code == 200, r.text
        assert parent.dependents_independent is False
        sync.assert_called_once_with(db, 7002)

    def test_H_toggle_true_detaches_without_resync(self, rig):
        client, db, state = rig
        parent = make_shift(id=7004, shift_date=date(2026, 7, 2))
        state["shifts_by_id"][7004] = parent

        with patch("routers.roster.sync_shift_pool_from_parent", return_value=[]) as sync:
            r = client.patch(
                "/api/roster/7004/dependents-independent",
                json={"dependents_independent": True},
            )

        assert r.status_code == 200, r.text
        assert parent.dependents_independent is True
        sync.assert_not_called()

    def test_H_toggle_rejects_pre_july_parent(self, rig):
        client, db, state = rig
        parent = make_shift(id=7005, shift_date=date(2026, 6, 30), end_date=date(2026, 7, 1))
        state["shifts_by_id"][7005] = parent

        r = client.patch(
            "/api/roster/7005/dependents-independent",
            json={"dependents_independent": False},
        )

        assert r.status_code == 422


# =============================================================================
# Duplicate — Unhappy / Edge
# =============================================================================

class TestDuplicateUnhappy:

    def test_source_not_found_returns_404(self, rig):
        client, db, state = rig
        r = client.post("/api/roster/9999/duplicate", json={"target_date": "2026-05-17"})
        assert r.status_code == 404

    def test_neither_mode_set_returns_422(self, rig):
        client, db, state = rig
        src = make_shift(id=101, staff_id=10)
        state["shifts_by_id"][101] = src
        r = client.post("/api/roster/101/duplicate", json={})
        assert r.status_code == 422


class TestDuplicateBulkStaffAdd:
    """v3 Phase 4 unblocked 2026-05-05: target_date + staff_ids combine into
    'bulk staff-add' — copy to target date AND assign to picked staff in one
    call. Multi-shift bulk Duplicate UI calls this per shift."""

    def test_happy_target_date_plus_one_staff_creates_one_assigned_copy(self, rig):
        client, db, state = rig
        src = make_shift(id=500, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][500] = src
        state["users_by_id"][20] = make_user(
            id=20, first_name="Marek", last_name="Smolarek", driver_type="jockey"
        )

        r = client.post(
            "/api/roster/500/duplicate",
            json={"target_date": "2026-05-17", "staff_ids": [20]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["date"] == "2026-05-17"
        assert body[0]["staff_id"] == 20

    def test_happy_target_date_plus_multi_staff_fans_out_at_target(self, rig):
        """N×M expansion: 1 source × 2 staff + 1 unassigned flag = 3 copies,
        all on target_date."""
        client, db, state = rig
        src = make_shift(id=501, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][501] = src
        state["users_by_id"][20] = make_user(id=20, driver_type="jockey")
        state["users_by_id"][30] = make_user(id=30, driver_type="jockey")

        r = client.post(
            "/api/roster/501/duplicate",
            json={
                "target_date": "2026-05-17",
                "staff_ids": [20, 30],
                "add_unassigned_jockey": True,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 3
        assert all(b["date"] == "2026-05-17" for b in body)
        # Two assigned + one unassigned (flag).
        assigned = [b for b in body if b["staff_id"] is not None]
        unassigned = [b for b in body if b["staff_id"] is None]
        assert {b["staff_id"] for b in assigned} == {20, 30}
        assert len(unassigned) == 1

    def test_edge_source_staff_in_target_kept_when_target_date_differs(self, rig):
        """When the target date differs from source, source.staff_id IS a valid
        pick — it's a date-copy assigned to them, not a literal duplicate."""
        client, db, state = rig
        src = make_shift(id=502, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][502] = src
        state["users_by_id"][10] = make_user(id=10, driver_type="jockey")

        r = client.post(
            "/api/roster/502/duplicate",
            json={"target_date": "2026-05-17", "staff_ids": [10]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["date"] == "2026-05-17"
        assert body[0]["staff_id"] == 10  # NOT skipped — it's a date copy assigned to source's staff

    def test_boundary_overlap_at_target_returns_409(self, rig):
        """Overlap guard fires at the TARGET date (not source.date) for
        bulk-staff-add. Confirms the fix where overlap-check uses the right date."""
        client, db, state = rig
        src = make_shift(id=503, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][503] = src
        state["users_by_id"][20] = make_user(id=20, driver_type="jockey")
        # Pre-existing shift on the target date for staff 20 — should collide.
        existing = make_shift(
            id=504, staff_id=20, shift_date=date(2026, 5, 17),
            start_time=time(9, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][504] = existing

        r = client.post(
            "/api/roster/503/duplicate",
            json={"target_date": "2026-05-17", "staff_ids": [20]},
        )
        assert r.status_code == 409
        assert "17/05/2026" in r.json()["detail"]

    def test_boundary_pure_date_copy_skips_overlap_check(self, rig):
        """Regression guard for the SPEC v3 'create both copies; admin sorts
        manually' rule: pure date-copy (no staff_ids) does NOT 409 on overlap."""
        client, db, state = rig
        src = make_shift(id=505, staff_id=10, shift_date=date(2026, 5, 10))
        state["shifts_by_id"][505] = src
        # Pre-existing shift on the target date for source's staff (10).
        existing = make_shift(
            id=506, staff_id=10, shift_date=date(2026, 5, 17),
            start_time=time(9, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][506] = existing

        r = client.post(
            "/api/roster/505/duplicate",
            json={"target_date": "2026-05-17"},
        )
        assert r.status_code == 200, r.text  # admin sorts the overlap manually


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

    def test_overnight_shift_merges_with_same_day_evening_shift(self, rig):
        """Both shifts are anchored to 5/9 (the overnight one's date=5/9,
        the evening one's date=5/9 too) → merges into a single 18:00–02:00
        shift that wraps into 5/10."""
        client, db, state = rig
        evening = make_shift(
            id=210, staff_id=10, shift_date=date(2026, 5, 9),
            start_time=time(18, 0), end_time=time(22, 0),
        )
        overnight = make_shift(
            id=211, staff_id=10,
            shift_date=date(2026, 5, 9), end_date=date(2026, 5, 10),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        state["shifts_by_id"][210] = evening
        state["shifts_by_id"][211] = overnight
        state["users_by_id"][10] = make_user(id=10)

        r = client.post("/api/roster/210/merge", json={"other_shift_id": 211})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["start_time"] == "18:00"
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

    def test_different_staff_without_explicit_choice_returns_422(self, rig):
        """Post-2026-05 the staff-conflict rule changed: instead of a hard
        422 we ask the admin to pick. Without staff_choice_made we still
        422 — never silently throw away a driver assignment."""
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
        assert "different assigned staff" in r.json()["detail"].lower()


class TestMergeUnionWindows:
    """Post-2026-05: no adjacency requirement. Merged window = union of
    both shifts' time ranges. Gap and overlap both succeed; same-time
    pairs collapse to a single window."""

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
        assert r.json()["start_time"] == "09:00"
        assert r.json()["end_time"] == "14:00"

    def test_gap_one_minute_now_merges(self, rig):
        """Pre-2026-05 this returned 422 (adjacency required). Now the
        merged window swallows the 1-minute gap."""
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
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/232/merge", json={"other_shift_id": 233})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["start_time"] == "09:00"
        assert body["end_time"] == "14:00"

    def test_two_hour_gap_now_merges(self, rig):
        """Bigger gap — admin merging two shifts on the same driver to
        collapse a quiet midday break into a single shift."""
        client, db, state = rig
        a = make_shift(
            id=240, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=241, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][240] = a
        state["shifts_by_id"][241] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/240/merge", json={"other_shift_id": 241})
        assert r.status_code == 200, r.text
        assert r.json()["start_time"] == "09:00"
        assert r.json()["end_time"] == "17:00"

    def test_overlap_now_merges(self, rig):
        """Pre-2026-05 this returned 422. Now overlap is allowed —
        union swallows the overlapping region."""
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
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/234/merge", json={"other_shift_id": 235})
        assert r.status_code == 200, r.text
        assert r.json()["start_time"] == "09:00"
        assert r.json()["end_time"] == "14:00"

    def test_absorbed_fully_inside_survivor(self, rig):
        """Boundary: shift 10–11 entirely inside shift 9–13. Union = 9–13
        (the survivor's window already covers the absorbed)."""
        client, db, state = rig
        a = make_shift(
            id=242, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(10, 0), end_time=time(11, 0),
        )
        b = make_shift(
            id=243, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(13, 0),
        )
        state["shifts_by_id"][242] = a
        state["shifts_by_id"][243] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/242/merge", json={"other_shift_id": 243})
        assert r.status_code == 200, r.text
        assert r.json()["start_time"] == "09:00"
        assert r.json()["end_time"] == "13:00"


class TestMergeSurvivorIsExplicit:
    """Post-2026-05 the SURVIVOR is the one in body.other_shift_id (the
    one the admin clicks in the modal), not the earlier-starting shift."""

    def test_survivor_is_later_shift_when_picked(self, rig):
        """URL shift (200, 9–12) is absorbed INTO body.other_shift_id
        (201, 14–17). Survivor row = 201, with end_time stretched from
        17:00 down to start at 09:00."""
        client, db, state = rig
        a = make_shift(
            id=250, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=251, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][250] = a
        state["shifts_by_id"][251] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/250/merge", json={"other_shift_id": 251})
        assert r.status_code == 200, r.text
        body = r.json()
        # Survivor is the picked one (id=251), not the earlier (id=250).
        assert body["id"] == 251
        assert body["start_time"] == "09:00"
        assert body["end_time"] == "17:00"

    def test_survivor_is_earlier_shift_when_picked(self, rig):
        """Mirror: URL shift (252, 14–17) absorbed INTO body.other_shift_id
        (253, 9–12). Survivor row = 253, end stretched to 17:00."""
        client, db, state = rig
        a = make_shift(
            id=252, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        b = make_shift(
            id=253, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        state["shifts_by_id"][252] = a
        state["shifts_by_id"][253] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/252/merge", json={"other_shift_id": 253})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == 253
        assert body["start_time"] == "09:00"
        assert body["end_time"] == "17:00"


class TestMergeStaffChoice:
    """Post-2026-05: when both shifts have different assigned staff, the
    admin MUST pick the survivor's staff via survivor_staff_id +
    staff_choice_made=True. Without the choice → 422."""

    def test_explicit_choice_keeps_absorbed_staff(self, rig):
        client, db, state = rig
        a = make_shift(
            id=260, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=261, staff_id=99, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][260] = a
        state["shifts_by_id"][261] = b
        state["users_by_id"][10] = make_user(id=10, driver_type="jockey")
        state["users_by_id"][99] = make_user(id=99, driver_type="fleet")
        r = client.post(
            "/api/roster/260/merge",
            json={"other_shift_id": 261, "survivor_staff_id": 10, "staff_choice_made": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == 261  # survivor row
        assert body["staff_id"] == 10  # but with absorbed's staff
        assert body["intended_driver_type"] == "jockey"

    def test_explicit_choice_keeps_survivor_staff(self, rig):
        client, db, state = rig
        a = make_shift(
            id=262, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=263, staff_id=99, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][262] = a
        state["shifts_by_id"][263] = b
        state["users_by_id"][10] = make_user(id=10, driver_type="jockey")
        state["users_by_id"][99] = make_user(id=99, driver_type="fleet")
        r = client.post(
            "/api/roster/262/merge",
            json={"other_shift_id": 263, "survivor_staff_id": 99, "staff_choice_made": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["staff_id"] == 99
        assert r.json()["intended_driver_type"] == "fleet"

    def test_explicit_choice_unassign(self, rig):
        """survivor_staff_id=null + staff_choice_made=True → merged
        shift becomes unassigned."""
        client, db, state = rig
        a = make_shift(
            id=264, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=265, staff_id=99, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][264] = a
        state["shifts_by_id"][265] = b
        r = client.post(
            "/api/roster/264/merge",
            json={"other_shift_id": 265, "survivor_staff_id": None, "staff_choice_made": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["staff_id"] is None

    def test_invalid_survivor_staff_id_returns_422(self, rig):
        """survivor_staff_id must be one of the two existing staff_ids
        or null. Anything else (e.g. a third driver's id) → 422."""
        client, db, state = rig
        a = make_shift(
            id=266, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=267, staff_id=99, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][266] = a
        state["shifts_by_id"][267] = b
        r = client.post(
            "/api/roster/266/merge",
            json={"other_shift_id": 267, "survivor_staff_id": 42, "staff_choice_made": True},
        )
        assert r.status_code == 422
        assert "survivor_staff_id" in r.json()["detail"]

    def test_one_null_staff_no_choice_needed(self, rig):
        """When exactly one shift is unassigned (the existing case), no
        explicit choice required — survivor inherits the assigned one."""
        client, db, state = rig
        a = make_shift(
            id=268, staff_id=None, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=269, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][268] = a
        state["shifts_by_id"][269] = b
        state["users_by_id"][10] = make_user(id=10, driver_type="jockey")
        r = client.post("/api/roster/268/merge", json={"other_shift_id": 269})
        assert r.status_code == 200, r.text
        assert r.json()["staff_id"] == 10


class TestMergeSameDayRule:
    """Both shifts must share an anchor `date`. Overnight shifts stay
    anchored to their START date — the next morning is a separate day.
    Belt-and-braces against direct API callers; the UI already filters
    by date bucket."""

    def test_H_same_date_merges(self, rig):
        """Sanity: two same-date shifts merge fine. Already covered
        elsewhere; this is the explicit Happy case for the new rule."""
        client, db, state = rig
        a = make_shift(
            id=280, staff_id=10, shift_date=date(2026, 2, 3),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=281, staff_id=10, shift_date=date(2026, 2, 3),
            start_time=time(13, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][280] = a
        state["shifts_by_id"][281] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/280/merge", json={"other_shift_id": 281})
        assert r.status_code == 200, r.text

    def test_U_overnight_ending_on_next_day_cannot_merge_with_next_day_shift(self, rig):
        """User-described scenario: an overnight shift dated 2/3 that
        finishes 2/4 at 02:00 cannot be merged with a shift dated 2/4
        that starts at 03:00. Different anchor dates → 422 even though
        the real-time gap is only 1 hour."""
        client, db, state = rig
        overnight = make_shift(
            id=282, staff_id=10,
            shift_date=date(2026, 2, 3), end_date=date(2026, 2, 4),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        morning = make_shift(
            id=283, staff_id=10, shift_date=date(2026, 2, 4),
            start_time=time(3, 0), end_time=time(7, 0),
        )
        state["shifts_by_id"][282] = overnight
        state["shifts_by_id"][283] = morning
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/282/merge", json={"other_shift_id": 283})
        assert r.status_code == 422
        detail = r.json()["detail"].lower()
        assert "same calendar day" in detail
        assert "2026-02-03" in r.json()["detail"]
        assert "2026-02-04" in r.json()["detail"]

    def test_U_different_dates_rejected_regardless_of_real_time_gap(self, rig):
        """Same idea but with a multi-day gap (Mon shift + Fri shift).
        Without this guard the union would produce a 5-day mega-shift."""
        client, db, state = rig
        monday = make_shift(
            id=284, staff_id=10, shift_date=date(2026, 5, 4),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        friday = make_shift(
            id=285, staff_id=10, shift_date=date(2026, 5, 8),
            start_time=time(14, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][284] = monday
        state["shifts_by_id"][285] = friday
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/284/merge", json={"other_shift_id": 285})
        assert r.status_code == 422
        assert "same calendar day" in r.json()["detail"].lower()

    def test_B_overnight_can_merge_with_same_start_date_shift(self, rig):
        """t / t-ε / t+ε boundary on the date check: an overnight shift
        dated 2/3 (end_date=2/4) CAN still merge with another 2/3-dated
        shift, because the rule keys off `date` not `end_date`. This is
        the Boundary case proving the rule is start-date-based."""
        client, db, state = rig
        overnight = make_shift(
            id=286, staff_id=10,
            shift_date=date(2026, 2, 3), end_date=date(2026, 2, 4),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        evening = make_shift(
            id=287, staff_id=10, shift_date=date(2026, 2, 3),
            start_time=time(18, 0), end_time=time(21, 0),
        )
        state["shifts_by_id"][286] = overnight
        state["shifts_by_id"][287] = evening
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/286/merge", json={"other_shift_id": 287})
        assert r.status_code == 200, r.text
        body = r.json()
        # Survivor is body.other_shift_id (=287, the evening shift),
        # window = union = 18:00 → 02:00 next day.
        assert body["id"] == 287
        assert body["start_time"] == "18:00"
        assert body["end_time"] == "02:00"
        assert body["end_date"] == "2026-02-04"

    def test_E_one_day_apart_off_by_one(self, rig):
        """Edge: shifts exactly 1 day apart (2/3 and 2/4, no overnight).
        Real-time gap might be huge or tiny depending on times but
        the date rule rejects regardless."""
        client, db, state = rig
        a = make_shift(
            id=288, staff_id=10, shift_date=date(2026, 2, 3),
            start_time=time(23, 30), end_time=time(23, 45),
        )
        b = make_shift(
            id=289, staff_id=10, shift_date=date(2026, 2, 4),
            start_time=time(0, 0), end_time=time(0, 15),
        )
        state["shifts_by_id"][288] = a
        state["shifts_by_id"][289] = b
        state["users_by_id"][10] = make_user(id=10)
        r = client.post("/api/roster/288/merge", json={"other_shift_id": 289})
        assert r.status_code == 422
        assert "same calendar day" in r.json()["detail"].lower()


# =============================================================================
# Merge — absorbed-link cascade (M2M secondary cleanup race)
# =============================================================================


def _make_link(shift_id, booking_id):
    """Mocked ShiftBookingLink with mutable shift_id (endpoint mutates it)."""
    link = MagicMock(spec=ShiftBookingLink)
    link.shift_id = shift_id
    link.booking_id = booking_id
    return link


def _find_call_index(db_mock, name, predicate):
    """Index of the first db.method_calls entry matching name+predicate.
    Returns -1 if not found."""
    for i, call in enumerate(db_mock.method_calls):
        cname, cargs, ckwargs = call
        if cname == name and predicate(cargs, ckwargs):
            return i
    return -1


class TestMergeAbsorbedLinkCascade:
    """Regression: before the fix, `db.delete(absorbed)` triggered
    SQLAlchemy's M2M auto-cleanup on the `bookings` secondary, which raced
    ahead of the pending link UPDATEs and raised StaleDataError — surfaced
    as a 500 (text/plain 'Internal Server Error', 21 bytes) on /merge
    whenever the absorbed shift had any linked bookings. The fix flushes
    the link re-pointing and expires the cached collection BEFORE deleting
    absorbed. These tests assert both the behaviour and the call-order
    contract so the fix can't silently regress."""

    def test_H_absorbed_with_distinct_bookings_merges_and_repoints_links(self, rig):
        """Happy: absorbed has 3 linked bookings, survivor 2 (all distinct).
        Merge succeeds, all 3 absorbed links get repointed to survivor,
        nothing is deleted on the link path (no duplicates)."""
        client, db, state = rig
        absorbed = make_shift(
            id=400, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(10, 0), end_time=time(16, 10),
        )
        survivor = make_shift(
            id=401, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(6, 40), end_time=time(9, 30),
        )
        state["shifts_by_id"][400] = absorbed
        state["shifts_by_id"][401] = survivor
        absorbed_links = [_make_link(400, b) for b in (15, 16, 124)]
        survivor_links = [_make_link(401, b) for b in (460, 576)]
        state["shift_links_by_shift"][400] = absorbed_links
        state["shift_links_by_shift"][401] = survivor_links

        r = client.post("/api/roster/400/merge", json={"other_shift_id": 401})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == 401
        assert body["start_time"] == "06:40"
        assert body["end_time"] == "16:10"
        assert all(l.shift_id == 401 for l in absorbed_links)
        # No link rows were deleted (none were duplicates).
        assert not any(l in state["deleted"] for l in absorbed_links + survivor_links)

    def test_U_fix_contract_flush_and_expire_run_before_delete(self, rig):
        """Unhappy-path guard: in real SQLAlchemy, `db.delete(absorbed)`
        before `db.expire(absorbed, ['bookings'])` re-raises the bug as a
        StaleDataError 500. The MagicMock rig can't reproduce that race,
        but it CAN catch the fix being silently removed — assert flush()
        and expire(absorbed, ['bookings']) both run before delete(absorbed)."""
        client, db, state = rig
        absorbed = make_shift(
            id=410, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(10, 0), end_time=time(16, 10),
        )
        survivor = make_shift(
            id=411, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(6, 40), end_time=time(9, 30),
        )
        state["shifts_by_id"][410] = absorbed
        state["shifts_by_id"][411] = survivor
        # Absorbed must have ≥1 link; without one the M2M cleanup would
        # never have triggered in real SQLAlchemy either.
        state["shift_links_by_shift"][410] = [_make_link(410, 15)]
        state["shift_links_by_shift"][411] = []

        r = client.post("/api/roster/410/merge", json={"other_shift_id": 411})
        assert r.status_code == 200, r.text

        flush_idx = _find_call_index(db, "flush", lambda a, k: True)
        expire_idx = _find_call_index(
            db, "expire",
            lambda a, k: len(a) >= 2 and a[0] is absorbed and a[1] == ["bookings"],
        )
        delete_absorbed_idx = _find_call_index(
            db, "delete", lambda a, k: a and a[0] is absorbed,
        )
        assert flush_idx != -1, "endpoint must flush link UPDATEs before deleting absorbed"
        assert expire_idx != -1, "endpoint must expire absorbed.bookings before deleting absorbed"
        assert delete_absorbed_idx != -1
        assert flush_idx < delete_absorbed_idx
        assert expire_idx < delete_absorbed_idx

    def test_E_shared_booking_dedupes_link_and_repoints_others(self, rig):
        """Edge: absorbed and survivor both link to the SAME booking_id
        (e.g. a customer whose drop-off shift and pickup shift happen to
        land on the same day pair). The shared link gets db.delete'd
        rather than repointed — UniqueConstraint(shift_id, booking_id)
        would otherwise reject the UPDATE."""
        client, db, state = rig
        absorbed = make_shift(
            id=420, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(10, 0), end_time=time(16, 10),
        )
        survivor = make_shift(
            id=421, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(6, 40), end_time=time(9, 30),
        )
        state["shifts_by_id"][420] = absorbed
        state["shifts_by_id"][421] = survivor
        shared_link = _make_link(420, 999)
        distinct_link = _make_link(420, 124)
        state["shift_links_by_shift"][420] = [shared_link, distinct_link]
        state["shift_links_by_shift"][421] = [_make_link(421, 999)]

        r = client.post("/api/roster/420/merge", json={"other_shift_id": 421})
        assert r.status_code == 200, r.text
        assert distinct_link.shift_id == 421
        assert shared_link in state["deleted"]
        # Deleted link's shift_id wasn't moved — it's being dropped, not migrated.
        assert shared_link.shift_id == 420

    def test_B_absorbed_with_zero_bookings_still_runs_fix(self, rig):
        """Boundary: absorbed has no linked bookings (the case that did
        work pre-fix). The fix's flush+expire calls still run — they're
        cheap and unconditional — and the endpoint must not crash on
        the empty link list."""
        client, db, state = rig
        absorbed = make_shift(
            id=430, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(10, 0), end_time=time(16, 10),
        )
        survivor = make_shift(
            id=431, staff_id=None, shift_date=date(2026, 6, 11),
            start_time=time(6, 40), end_time=time(9, 30),
        )
        state["shifts_by_id"][430] = absorbed
        state["shifts_by_id"][431] = survivor
        state["shift_links_by_shift"][430] = []
        state["shift_links_by_shift"][431] = []

        r = client.post("/api/roster/430/merge", json={"other_shift_id": 431})
        assert r.status_code == 200, r.text
        expire_idx = _find_call_index(
            db, "expire",
            lambda a, k: len(a) >= 2 and a[0] is absorbed and a[1] == ["bookings"],
        )
        assert expire_idx != -1


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


# =============================================================================
# Driver-trust pivot 2026-05-28: admin_shaped_at stamp-or-not contract.
#
# Stamped by: split, merge, duplicate, PUT /roster/{id} when ANY of
# (start_time, end_time, date, end_date) actually changes.
# NOT stamped by: assignment / unassignment, notes, status,
# intended_driver_type. The point of the column is to record a
# deliberate window-shaping action so the auto-roster knows it must
# never reshape this row again — even after the admin unassigns it back
# to staff_id=NULL. Owning a shift (staff_id IS NOT NULL) already
# freezes its window via the auto_roster filter, so we deliberately
# DON'T pile assignment on top of admin_shaped_at; that keeps the
# column's audit meaning sharp.
# =============================================================================


class TestDuplicateStampsAdminShapedAt:

    def test_H_duplicate_to_other_date_stamps_new_copy(self, rig):
        """Duplicating a shift to another date stamps admin_shaped_at on
        the new copy so a subsequent auto-rebuild on that date treats it
        as frozen — admin made a deliberate planning call by duplicating."""
        client, db, state = rig
        source = make_shift(
            id=600, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(13, 0),
            created_source="auto",
        )
        state["shifts_by_id"][600] = source
        state["users_by_id"][10] = make_user(id=10)
        r = client.post(
            "/api/roster/600/duplicate",
            json={"target_date": "2026-05-12"},
        )
        assert r.status_code == 200, r.text

        from db_models import RosterShift
        new_shifts = [a for a in state["added"] if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert new_shifts[0].admin_shaped_at is not None


class TestMergeStampsAdminShapedAt:

    def test_H_merge_stamps_survivor(self, rig):
        """The union'd survivor row encodes a deliberate admin decision
        about which hours one driver should cover — stamp it so the
        auto-roster never stretches/shrinks the merged window."""
        client, db, state = rig
        a = make_shift(
            id=620, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(12, 0),
        )
        b = make_shift(
            id=621, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(13, 0), end_time=time(16, 0),
        )
        state["shifts_by_id"][620] = a
        state["shifts_by_id"][621] = b
        state["users_by_id"][10] = make_user(id=10)
        assert b.admin_shaped_at is None
        r = client.post("/api/roster/620/merge", json={"other_shift_id": 621})
        assert r.status_code == 200, r.text
        # Survivor is body.other_shift_id = 621.
        assert b.admin_shaped_at is not None


class TestSplitStampsAdminShapedAt:

    def test_H_split_stamps_both_halves(self, rig):
        """Both halves of a split are admin-shaped: the in-place first
        half (modified end_time) AND the freshly-created second half."""
        client, db, state = rig
        s = make_shift(
            id=640, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
        )
        state["shifts_by_id"][640] = s
        assert s.admin_shaped_at is None
        r = client.post("/api/roster/640/split", json={"split_at_time": "13:00"})
        assert r.status_code == 200, r.text
        # First half stamped in place.
        assert s.admin_shaped_at is not None
        # Second half stamped on construction.
        from db_models import RosterShift
        new_shifts = [a for a in state["added"] if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert new_shifts[0].admin_shaped_at is not None


class TestPatchStampingHUEB:
    """The PATCH stamp is the most-tested: it has to fire on ANY of
    {start_time, end_time, date, end_date} actually changing, AND it
    must NOT fire on assignment-only / notes-only / status-only edits."""

    def test_H_changing_end_time_stamps(self, rig):
        client, db, state = rig
        # Unassigned to skip the overlap-check branch — the rig mock
        # doesn't honor `exclude_shift_id`. Staff_id is irrelevant to
        # the stamp logic; we're testing the window-edit path.
        s = make_shift(
            id=660, staff_id=None, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
            created_source="auto",
        )
        state["shifts_by_id"][660] = s
        assert s.admin_shaped_at is None
        r = client.put(
            "/api/roster/660",
            json={"end_time": "18:00"},
        )
        assert r.status_code == 200, r.text
        assert s.admin_shaped_at is not None

    def test_U_reassignment_only_does_NOT_stamp(self, rig):
        """REGRESSION GUARD for the Kris-loop fix philosophy:
        re-assigning a shift (changing staff_id) is NOT a shape action.
        Owning the shift is already frozen-equivalent via the staff_id
        filter in the auto-roster — stamping admin_shaped_at here would
        muddy the audit meaning of the column."""
        client, db, state = rig
        s = make_shift(
            id=661, staff_id=10, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
            created_source="auto",
        )
        state["shifts_by_id"][661] = s
        state["users_by_id"][20] = make_user(id=20)
        r = client.put(
            "/api/roster/661",
            json={"staff_id": 20},
        )
        assert r.status_code == 200, r.text
        assert s.admin_shaped_at is None, (
            "assignment-only PATCH must NOT stamp admin_shaped_at; "
            "ownership already freezes the window"
        )

    def test_E_notes_status_intended_driver_type_do_NOT_stamp(self, rig):
        """Edge: non-window field edits — notes, status,
        intended_driver_type — are fill-in info, not shape changes.
        Confirms the stamp predicate is narrowly window-only."""
        client, db, state = rig
        s = make_shift(
            id=662, staff_id=None, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
            created_source="auto",
        )
        state["shifts_by_id"][662] = s
        r = client.put(
            "/api/roster/662",
            json={"notes": "ring driver at 09:30",
                  "intended_driver_type": "fleet"},
        )
        assert r.status_code == 200, r.text
        assert s.admin_shaped_at is None

    def test_B_noop_edit_setting_same_value_does_NOT_stamp(self, rig):
        """Boundary: PATCH sends `end_time: 17:00` when the shift's
        end_time is ALREADY 17:00. No actual window change — stamp
        must not fire. Cleanest protection against UI-form-saves that
        round-trip every field including unchanged ones."""
        client, db, state = rig
        s = make_shift(
            id=663, staff_id=None, shift_date=date(2026, 5, 10),
            start_time=time(9, 0), end_time=time(17, 0),
            created_source="auto",
        )
        state["shifts_by_id"][663] = s
        r = client.put(
            "/api/roster/663",
            json={"start_time": "09:00", "end_time": "17:00"},
        )
        assert r.status_code == 200, r.text
        assert s.admin_shaped_at is None

    def test_U_client_supplied_end_date_provided_marker_is_ignored(self, rig):
        """Unhappy (security): a request that sends
        `{"end_date_provided": true}` WITHOUT `end_date` must NOT clear
        end_date and must NOT stamp admin_shaped_at. The provided-markers
        are internal book-keeping derived in the validator from actual
        field presence; client-supplied values must be overwritten.
        Reviewer flagged this 2026-05-28 — same risk pattern would let a
        client forge staff_id_provided too."""
        client, db, state = rig
        s = make_shift(
            id=665, staff_id=None, shift_date=date(2026, 5, 10),
            end_date=date(2026, 5, 11),
            start_time=time(22, 0), end_time=time(2, 0),
            created_source="auto",
        )
        state["shifts_by_id"][665] = s
        original_end = s.end_date
        r = client.put(
            "/api/roster/665",
            json={"end_date_provided": True},  # marker alone, no end_date
        )
        assert r.status_code == 200, r.text
        assert s.end_date == original_end, (
            "end_date must NOT be cleared when only the marker is sent"
        )
        assert s.admin_shaped_at is None, (
            "no real window change → no stamp"
        )

    def test_E_clearing_overnight_end_date_applies_and_stamps(self, rig):
        """Code-review regression 2026-05-28: PATCH with
        `end_date: null` (clearing an overnight cross-day) must:
          (a) actually clear the field (was silently dropped before the
              `end_date_provided` marker was added — `is not None` guard
              treated null as "field not provided");
          (b) stamp admin_shaped_at because the window shape changed.
        Without (a) the PATCH was a silent no-op; without (b) auto could
        later reshape it back."""
        client, db, state = rig
        s = make_shift(
            id=664, staff_id=None, shift_date=date(2026, 5, 10),
            end_date=date(2026, 5, 11),  # overnight to start
            start_time=time(22, 0), end_time=time(2, 0),
            created_source="auto",
        )
        state["shifts_by_id"][664] = s
        r = client.put(
            "/api/roster/664",
            json={"end_date": None},
        )
        assert r.status_code == 200, r.text
        assert s.end_date is None, "end_date null must actually be applied"
        assert s.admin_shaped_at is not None, (
            "clearing overnight cross-day is a window-shape change — must stamp"
        )
