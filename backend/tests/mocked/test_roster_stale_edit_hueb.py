"""
HUEB integration tests — the PUT /api/roster/{shift_id} partial-update
contract the stale-tab fix (2026-07-23) relies on. Real FastAPI routes via
TestClient against real in-memory ORM rows.

Incident: the admin runs the roster page on a phone; mobile browsers freeze
background tabs and restore them hours later without reloading, and saves
used to send EVERY form field — reverting concurrent changes (engine
re-cuts, edits from another device) and falsely stamping admin_shaped_at.
The frontend now populates the edit dialog from GET /api/roster/{id} and
sends diff-only payloads (RosterCalendar.buildShiftUpdateDiff). These tests
pin the backend behaviours that contract depends on:

  * omitted fields are left untouched (window, staff, links, stamp)
  * provided-but-equal window fields do NOT re-stamp admin_shaped_at
  * provided-and-different window fields DO re-stamp
  * staff_id / end_date null-vs-absent provided-marker semantics
  * validation failures (overlap 409) leave the row untouched
  * GET /api/roster/{shift_id} serves the fresh row the dialog needs

Fixture mirrors the real Mon 27 Jul 2026 shift (times are UK wall-clock,
as stored): engine-cut to 03:50-07:30 around the 04:20 first job
(TAG-DKG92004 minus the 30-min start buffer), staffed, admin-shaped days
earlier.
"""
from datetime import date as date_type, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from routers.roster import (
    get_current_user as roster_get_current_user,
    require_admin as roster_require_admin,
)
from db_models import (
    AuditLog,
    AuditLogEvent,
    Booking,
    BookingStatus,
    RosterShift,
    ShiftBookingLink,
    ShiftStatus,
    ShiftType,
)
import json

SHIFT_DAY = date_type(2026, 7, 27)
# Stamped 19:45 UK on 19 Jul (18:45 UTC) — the admin's original shaping.
SHAPED_AT = datetime(2026, 7, 19, 18, 45, tzinfo=timezone.utc)


def _admin():
    u = MagicMock()
    u.id = 1
    u.email = "admin@tag.test"
    u.is_admin = True
    u.driver_type = None
    return u


def _naive(dt):
    """sqlite hands tz-aware seeds back naive — normalise for comparison."""
    return dt.replace(tzinfo=None) if dt is not None else None


@pytest.fixture
def client(db_session):
    app.dependency_overrides[roster_get_current_user] = lambda: _admin()
    app.dependency_overrides[roster_require_admin] = lambda: _admin()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(roster_get_current_user, None)
        app.dependency_overrides.pop(roster_require_admin, None)


@pytest.fixture
def seeded(db_session):
    # Raw SQL: the User model's Postgres ARRAY columns don't round-trip
    # through the sqlite fixture — same pattern as the other hueb suites.
    for uid, first in ((15, "Rota"), (14, "Cover")):
        db_session.execute(text(
            "INSERT INTO users (id, email, first_name, last_name, is_admin, is_active, "
            "driver_type, preferred_shift_types, excluded_shift_types, preferred_days_off) "
            "VALUES (:id, :e, :f, 'Driver', 0, 1, 'jockey', '{}', '{}', '{}')"
        ), {"id": uid, "e": f"driver{uid}@tag.test", "f": first})
    bookings = [
        Booking(
            id=1021, reference="TAG-DKG92004", customer_id=1, vehicle_id=1,
            package="full", status=BookingStatus.CONFIRMED,
            dropoff_date=SHIFT_DAY, dropoff_time=time(4, 20),
            pickup_date=SHIFT_DAY + timedelta(days=14), pickup_time=time(14, 45),
        ),
        Booking(
            id=912, reference="TAG-PSQ44974", customer_id=1, vehicle_id=1,
            package="full", status=BookingStatus.CONFIRMED,
            dropoff_date=SHIFT_DAY, dropoff_time=time(5, 25),
            pickup_date=SHIFT_DAY + timedelta(days=4), pickup_time=time(12, 20),
        ),
    ]
    for b in bookings:
        db_session.add(b)
    shift = RosterShift(
        staff_id=15,
        assigned_source="admin",
        date=SHIFT_DAY,
        start_time=time(3, 50),
        end_time=time(7, 30),
        shift_type=ShiftType.MORNING,
        status=ShiftStatus.SCHEDULED,
        created_source="auto",
        intended_driver_type="jockey",
        admin_shaped_at=SHAPED_AT,
    )
    db_session.add(shift)
    db_session.commit()
    for b in bookings:
        db_session.add(ShiftBookingLink(shift_id=shift.id, booking_id=b.id))
    db_session.commit()
    return db_session, shift


def _linked_ids(db, shift_id):
    return {
        l.booking_id
        for l in db.query(ShiftBookingLink).filter_by(shift_id=shift_id).all()
    }


class TestPartialUpdateStaleTabHUEB:

    def test_H_staff_only_update_leaves_window_links_and_stamp(self, client, seeded):
        """The Kris regression: reassigning the driver from a (possibly
        stale) dialog must move ONLY the driver — window, links and the
        admin_shaped_at audit stamp stay exactly as they were."""
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": 14})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.staff_id == 14
        assert shift.assigned_source == "admin"
        assert (shift.date, shift.start_time, shift.end_time) == (
            SHIFT_DAY, time(3, 50), time(7, 30),
        )
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)
        assert _linked_ids(db, shift.id) == {1021, 912}

    def test_H_time_change_restamps_admin_shaped_at(self, client, seeded):
        """A deliberate window edit (03:50 → 04:30 UK) applies and re-stamps
        the shaping audit — the stamp's meaning is 'an admin last shaped the
        window at this moment'."""
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"start_time": "04:30"})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.start_time == time(4, 30)
        assert shift.end_time == time(7, 30)          # untouched side intact
        stamp = _naive(shift.admin_shaped_at)
        assert stamp != _naive(SHAPED_AT)
        assert abs((stamp - datetime.utcnow()).total_seconds()) < 60

    def test_U_empty_payload_is_a_full_noop(self, client, seeded):
        """The diff-only frontend never sends an empty body (it skips the
        request), but the backend must still treat one as change-nothing."""
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.staff_id == 15
        assert (shift.start_time, shift.end_time) == (time(3, 50), time(7, 30))
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)
        assert _linked_ids(db, shift.id) == {1021, 912}

    def test_U_explicit_null_staff_unassigns_without_touching_window(self, client, seeded):
        """null-vs-absent marker: {"staff_id": null} means unassign — and
        still must not move the window or the stamp."""
        db, shift = seeded
        shift.needs_cover_at = datetime.now(timezone.utc)
        db.commit()

        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": None})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.staff_id is None
        assert shift.assigned_source is None
        assert shift.needs_cover_at is None           # admin decision resolves the alert
        assert (shift.start_time, shift.end_time) == (time(3, 50), time(7, 30))
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)

    def test_E_non_window_field_keeps_assignment_and_stamp(self, client, seeded):
        """Notes are a non-window field: applied, but no re-stamp and no
        side effects on assignment."""
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"notes": "cover for holiday"})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.notes == "cover for holiday"
        assert shift.staff_id == 15
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)

    def test_E_clearing_end_date_restamps_via_provided_marker(self, client, seeded):
        """{"end_date": null} is a window change (clears the overnight
        cross-day) — the provided-marker must catch it and re-stamp."""
        db, shift = seeded
        shift.end_date = SHIFT_DAY + timedelta(days=1)
        db.commit()

        r = client.put(f"/api/roster/{shift.id}", json={"end_date": None})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert shift.end_date is None
        assert _naive(shift.admin_shaped_at) != _naive(SHAPED_AT)

    def test_B_provided_but_equal_window_does_not_restamp(self, client, seeded):
        """Boundary between 'provided' and 'changed': echoing the current
        window back (what a non-diffing client does) must not re-stamp —
        window_changed compares values, not presence."""
        db, shift = seeded
        r = client.put(
            f"/api/roster/{shift.id}",
            json={"start_time": "03:50", "end_time": "07:30", "date": "2026-07-27"},
        )
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert (shift.start_time, shift.end_time) == (time(3, 50), time(7, 30))
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)

    def test_E_booking_ids_only_rewrites_links_not_window(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"booking_ids": [1021]})
        assert r.status_code == 200, r.text

        db.refresh(shift)
        assert _linked_ids(db, shift.id) == {1021}
        assert shift.staff_id == 15
        assert (shift.start_time, shift.end_time) == (time(3, 50), time(7, 30))
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)

    def test_U_overlap_409_leaves_row_untouched(self, client, seeded):
        """Validation failures must reject BEFORE mutating: reassigning to a
        driver who already has an overlapping shift 409s and changes
        nothing on the target row."""
        db, shift = seeded
        db.add(RosterShift(
            staff_id=14,
            date=SHIFT_DAY,
            start_time=time(3, 0),
            end_time=time(8, 0),
            shift_type=ShiftType.MORNING,
            status=ShiftStatus.SCHEDULED,
            created_source="manual",
            intended_driver_type="jockey",
        ))
        db.commit()

        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": 14})
        assert r.status_code == 409, r.text

        db.refresh(shift)
        assert shift.staff_id == 15
        assert (shift.start_time, shift.end_time) == (time(3, 50), time(7, 30))
        assert _naive(shift.admin_shaped_at) == _naive(SHAPED_AT)


class TestGetSingleShiftHUEB:

    def test_H_get_returns_fresh_row_for_edit_dialog(self, client, seeded):
        """The dialog populates from this response — it must carry the
        window (UK wall-clock), assignment and linked bookings."""
        db, shift = seeded
        r = client.get(f"/api/roster/{shift.id}")
        assert r.status_code == 200, r.text

        data = r.json()
        assert data["id"] == shift.id
        assert data["date"] == "2026-07-27"
        assert data["start_time"][:5] == "03:50"
        assert data["end_time"][:5] == "07:30"
        assert data["staff_id"] == 15
        assert {b["id"] for b in data["bookings"]} == {1021, 912}

    def test_U_get_unknown_shift_404s(self, client, seeded):
        r = client.get("/api/roster/999999")
        assert r.status_code == 404


def _update_audits(db):
    return (
        db.query(AuditLog)
        .filter(AuditLog.event == AuditLogEvent.ROSTER_SHIFT_UPDATED)
        .all()
    )


class TestUpdateAuditHUEB:
    """roster_shift_updated audit rows (2026-07-23): every PUT that actually
    changes something records old→new per field, so "what changed my shift"
    is a one-query answer instead of an evening of forensics."""

    def test_H_time_change_audits_old_and_new_window(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"start_time": "04:30"})
        assert r.status_code == 200, r.text

        audits = _update_audits(db)
        assert len(audits) == 1
        data = json.loads(audits[0].event_data)
        assert data["shift_id"] == shift.id
        assert data["window_changed"] is True
        assert data["changes"] == {
            "start_time": {"from": "03:50", "to": "04:30"},
        }
        assert data["updated_by_user_id"] == 1
        assert audits[0].session_id == f"roster-shift-{shift.id}"
        assert audits[0].booking_reference in ("TAG-DKG92004", "TAG-PSQ44974")

    def test_H_staff_change_audits_without_window_flag(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": 14})
        assert r.status_code == 200, r.text

        audits = _update_audits(db)
        assert len(audits) == 1
        data = json.loads(audits[0].event_data)
        assert data["window_changed"] is False
        assert data["changes"] == {"staff_id": {"from": 15, "to": 14}}

    def test_U_noop_put_writes_no_audit(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={})
        assert r.status_code == 200, r.text
        assert _update_audits(db) == []

    def test_B_provided_but_equal_values_write_no_audit(self, client, seeded):
        """Boundary between provided and changed, audit-side: a non-diffing
        client echoing the current values back must not spam the trail."""
        db, shift = seeded
        r = client.put(
            f"/api/roster/{shift.id}",
            json={"start_time": "03:50", "end_time": "07:30", "staff_id": 15},
        )
        assert r.status_code == 200, r.text
        assert _update_audits(db) == []

    def test_E_unassign_audits_explicit_null(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": None})
        assert r.status_code == 200, r.text

        data = json.loads(_update_audits(db)[0].event_data)
        assert data["changes"] == {"staff_id": {"from": 15, "to": None}}

    def test_E_booking_ids_change_audits_old_and_new_sets(self, client, seeded):
        db, shift = seeded
        r = client.put(f"/api/roster/{shift.id}", json={"booking_ids": [1021]})
        assert r.status_code == 200, r.text

        data = json.loads(_update_audits(db)[0].event_data)
        assert data["changes"] == {
            "booking_ids": {"from": [912, 1021], "to": [1021]},
        }

    def test_E_rejected_put_writes_no_audit(self, client, seeded):
        """A 409 (overlap) mutates nothing and must audit nothing."""
        db, shift = seeded
        db.add(RosterShift(
            staff_id=14,
            date=SHIFT_DAY,
            start_time=time(3, 0),
            end_time=time(8, 0),
            shift_type=ShiftType.MORNING,
            status=ShiftStatus.SCHEDULED,
            created_source="manual",
            intended_driver_type="jockey",
        ))
        db.commit()

        r = client.put(f"/api/roster/{shift.id}", json={"staff_id": 14})
        assert r.status_code == 409, r.text
        assert _update_audits(db) == []
