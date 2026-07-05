"""
Cancelled shifts must not block overlap validation.

Regression for the 2026-07-07 prod incident (staff 19): an auto-roster shift
20:15-21:45 was "deleted" via the admin UI, which soft-deletes it as
status=cancelled (kept so the auto-roster won't recreate the window). The
roster UI hides cancelled shifts, but check_shift_overlap had no status
filter, so extending the adjacent 13:35-20:00 shift to 21:30 was rejected
with "Shift overlaps with existing shift (20:15-21:45)" against a shift the
admin could not see.

Fixture times below are the real incident triple (shift 5996 vs 5956).
"""
from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import text

from db_models import RosterShift, ShiftType, ShiftStatus
from main import app


INCIDENT_DATE = date(2026, 7, 7)
STAFF_ID = 19


def _insert_staff(db, staff_id=STAFF_ID):
    # Array columns need the postgres '{}' literal — the ORM's ARRAY result
    # parser chokes on the sqlite table's '[]' default.
    db.execute(text(
        "INSERT INTO users (id, email, first_name, last_name, is_admin, is_active, driver_type, "
        "preferred_shift_types, excluded_shift_types, preferred_days_off) "
        "VALUES (:id, :email, 'Fleet', 'Driver', 0, 1, 'fleet', '{}', '{}', '{}')"
    ), {"id": staff_id, "email": f"driver{staff_id}@tagparking.co.uk"})
    db.commit()


def _add_shift(db, *, start, end, status, shift_type=ShiftType.AFTERNOON, staff_id=STAFF_ID):
    shift = RosterShift(
        staff_id=staff_id,
        date=INCIDENT_DATE,
        end_date=INCIDENT_DATE,
        start_time=start,
        end_time=end,
        shift_type=shift_type,
        status=status,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def _admin_client(db):
    from routers.roster import require_admin

    class _Admin:
        id = 1
        is_admin = True
        is_active = True
        email = "admin@tagparking.co.uk"

    app.dependency_overrides[require_admin] = lambda: _Admin()
    return TestClient(app)


def _cleanup_admin_override():
    from routers.roster import require_admin
    app.dependency_overrides.pop(require_admin, None)


# ===========================================================================
# check_shift_overlap unit behaviour (real ORM rows, in-memory sqlite)
# ===========================================================================

class TestCheckShiftOverlapStatusFilter:

    def test_cancelled_shift_is_ignored(self, db_session):
        """The incident shape: extending 13:35-20:00 to 21:30 across a
        cancelled 20:15-21:45 shift must find no conflict."""
        from routers.roster import check_shift_overlap

        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.CANCELLED, shift_type=ShiftType.LATE_AFTERNOON)

        conflict = check_shift_overlap(
            db_session, STAFF_ID, INCIDENT_DATE, time(13, 35), time(21, 30),
            exclude_shift_id=live.id,
        )
        assert conflict is None

    def test_scheduled_shift_still_conflicts(self, db_session):
        """Control: the same window against a live (scheduled) shift must
        still be reported as a conflict."""
        from routers.roster import check_shift_overlap

        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        blocker = _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                             status=ShiftStatus.SCHEDULED, shift_type=ShiftType.LATE_AFTERNOON)

        conflict = check_shift_overlap(
            db_session, STAFF_ID, INCIDENT_DATE, time(13, 35), time(21, 30),
            exclude_shift_id=live.id,
        )
        assert conflict is not None
        assert conflict.id == blocker.id

    def test_boundary_end_exactly_at_scheduled_start_is_not_conflict(self, db_session):
        """t boundary: new end == existing start (20:15) is adjacency, not overlap."""
        from routers.roster import check_shift_overlap

        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.SCHEDULED, shift_type=ShiftType.LATE_AFTERNOON)

        conflict = check_shift_overlap(
            db_session, STAFF_ID, INCIDENT_DATE, time(13, 35), time(20, 15),
            exclude_shift_id=live.id,
        )
        assert conflict is None

    def test_boundary_one_minute_past_scheduled_start_conflicts(self, db_session):
        """t+1min boundary: new end 20:16 against a scheduled 20:15 start conflicts."""
        from routers.roster import check_shift_overlap

        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.SCHEDULED, shift_type=ShiftType.LATE_AFTERNOON)

        conflict = check_shift_overlap(
            db_session, STAFF_ID, INCIDENT_DATE, time(13, 35), time(20, 16),
            exclude_shift_id=live.id,
        )
        assert conflict is not None


# ===========================================================================
# Endpoint behaviour — PUT /api/roster/{id} and POST /api/roster
# ===========================================================================

class TestShiftEndpointsIgnoreCancelled:

    def test_update_extends_over_cancelled_shift(self, db_session):
        """The exact failed prod edit: PUT end_time=21:30 on the 13:35 shift
        with a cancelled 20:15-21:45 shift present must succeed."""
        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.CANCELLED, shift_type=ShiftType.LATE_AFTERNOON)

        client = _admin_client(db_session)
        try:
            response = client.put(f"/api/roster/{live.id}", json={"end_time": "21:30"})
        finally:
            _cleanup_admin_override()

        assert response.status_code == 200, response.text
        assert response.json()["end_time"] == "21:30"
        db_session.refresh(live)
        assert live.end_time == time(21, 30)

    def test_update_still_blocked_by_scheduled_shift(self, db_session):
        """Control: the same PUT against a live 20:15-21:45 shift stays 409."""
        _insert_staff(db_session)
        live = _add_shift(db_session, start=time(13, 35), end=time(20, 0),
                          status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.SCHEDULED, shift_type=ShiftType.LATE_AFTERNOON)

        client = _admin_client(db_session)
        try:
            response = client.put(f"/api/roster/{live.id}", json={"end_time": "21:30"})
        finally:
            _cleanup_admin_override()

        assert response.status_code == 409
        assert "20:15-21:45" in response.json()["detail"]

    def test_create_over_cancelled_shift_succeeds(self, db_session):
        """POST a new shift into a window occupied only by a cancelled shift."""
        _insert_staff(db_session)
        _add_shift(db_session, start=time(20, 15), end=time(21, 45),
                   status=ShiftStatus.CANCELLED, shift_type=ShiftType.LATE_AFTERNOON)

        client = _admin_client(db_session)
        try:
            response = client.post("/api/roster", json={
                "staff_id": STAFF_ID,
                "date": INCIDENT_DATE.isoformat(),
                "start_time": "20:15",
                "end_time": "21:45",
                "shift_type": "late_afternoon",
                "status": "scheduled",
            })
        finally:
            _cleanup_admin_override()

        assert response.status_code == 201, response.text
