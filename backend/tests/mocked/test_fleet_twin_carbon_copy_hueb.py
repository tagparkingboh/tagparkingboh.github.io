"""
Fleet twin carbon-copy — propagation paths (hueb).

Owner spec (2026-07-22): the fleet twin mirrors its jockey shift's bookings
through EVERY update path. Creation and reconcile mirroring are covered in
the phase 2/3 suites; this file closes the remaining paths:
- admin booking edits on the jockey (PUT booking_ids) propagate to the twin
- auto-link of a fresh booking propagates to the twin
- (phase 4 gap) admin PUT staff assignment clears the needs-cover flag

Real in-memory ORM rows + TestClient with router-local auth overrides.
"""
from datetime import date as date_type, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import (
    Booking, BookingStatus, RosterShift, ShiftBookingLink, ShiftStatus, ShiftType,
)
from main import app
from routers.roster import require_admin as roster_require_admin

V4_DAY = date_type(2026, 8, 12)
DRIVER_ID = 21


@pytest.fixture
def admin_client(db_session):
    app.dependency_overrides[roster_require_admin] = lambda: SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True, is_active=True,
        first_name="Ad", last_name="Min", driver_type=None,
    )
    yield TestClient(app)
    app.dependency_overrides.pop(roster_require_admin, None)


def _add_user(db, uid=DRIVER_ID, driver_type="jockey"):
    db.execute(text(
        "INSERT INTO users (id, email, first_name, last_name, is_admin, is_active, "
        "driver_type, preferred_shift_types, excluded_shift_types, preferred_days_off) "
        "VALUES (:id, :e, 'Test', 'Driver', 0, 1, :dt, '{}', '{}', '{}')"
    ), {"id": uid, "e": f"u{uid}@tag.test", "dt": driver_type})
    db.commit()


def _pair(db, start=time(3, 30), end=time(10, 30)):
    jockey = RosterShift(
        date=V4_DAY, start_time=start, end_time=end,
        shift_type=ShiftType.EARLY_MORNING, status=ShiftStatus.SCHEDULED,
        created_source="auto", intended_driver_type="jockey",
    )
    db.add(jockey)
    db.commit()
    fleet = RosterShift(
        date=V4_DAY, start_time=start, end_time=end,
        shift_type=ShiftType.EARLY_MORNING, status=ShiftStatus.SCHEDULED,
        created_source="auto", intended_driver_type="fleet",
        parent_shift_id=jockey.id,
    )
    db.add(fleet)
    db.commit()
    return jockey, fleet


def _booking(db, dropoff_time_=time(5, 0)):
    b = Booking(
        reference=f"TAG-CCP{db.query(Booking).count():05d}",
        customer_id=1, vehicle_id=1, package="full",
        status=BookingStatus.CONFIRMED,
        dropoff_date=V4_DAY, dropoff_time=dropoff_time_,
        pickup_date=V4_DAY + timedelta(days=7), pickup_time=time(12, 0),
    )
    db.add(b)
    db.commit()
    return b


def _links(db, shift_id):
    return {l.booking_id for l in db.query(ShiftBookingLink).filter_by(shift_id=shift_id)}


class TestAdminEditPropagationHUEB:

    def test_H_admin_adding_bookings_mirrors_to_twin(self, admin_client, db_session):
        jockey, fleet = _pair(db_session)
        b1, b2 = _booking(db_session), _booking(db_session, time(6, 0))

        resp = admin_client.put(f"/api/roster/{jockey.id}", json={"booking_ids": [b1.id, b2.id]})

        assert resp.status_code == 200, resp.text
        assert _links(db_session, jockey.id) == {b1.id, b2.id}
        assert _links(db_session, fleet.id) == {b1.id, b2.id}

    def test_H_admin_removing_a_booking_mirrors_to_twin(self, admin_client, db_session):
        jockey, fleet = _pair(db_session)
        b1, b2 = _booking(db_session), _booking(db_session, time(6, 0))
        for sid in (jockey.id, fleet.id):
            for b in (b1, b2):
                db_session.add(ShiftBookingLink(shift_id=sid, booking_id=b.id))
        db_session.commit()

        resp = admin_client.put(f"/api/roster/{jockey.id}", json={"booking_ids": [b1.id]})

        assert resp.status_code == 200, resp.text
        assert _links(db_session, jockey.id) == {b1.id}
        assert _links(db_session, fleet.id) == {b1.id}


class TestAutoLinkPropagationHUEB:

    def test_H_auto_linked_booking_reaches_the_twin(self, db_session):
        from roster_planner_runner import auto_link_booking_to_shifts
        jockey, fleet = _pair(db_session)
        booking = _booking(db_session)

        linked = auto_link_booking_to_shifts(db_session, booking)
        db_session.commit()

        assert jockey.id in linked
        assert booking.id in _links(db_session, jockey.id)
        assert booking.id in _links(db_session, fleet.id)  # carbon copy


class TestAdminAssignClearsNeedsCoverHUEB:

    def test_H_admin_put_assignment_resolves_needs_cover(self, admin_client, db_session):
        _add_user(db_session)
        jockey, _fleet = _pair(db_session)
        jockey.needs_cover_at = datetime.utcnow()
        db_session.commit()

        resp = admin_client.put(f"/api/roster/{jockey.id}", json={"staff_id": DRIVER_ID})

        assert resp.status_code == 200, resp.text
        db_session.refresh(jockey)
        assert jockey.staff_id == DRIVER_ID
        assert jockey.assigned_source == "admin"
        assert jockey.needs_cover_at is None
