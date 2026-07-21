"""
Cancelled shifts must never count as payable hours (hueb).

Admin-deleting an AUTO shift soft-suppresses it (status='cancelled' +
suppressed_at) so auto-roster remembers the intent and doesn't recreate the
coverage — the row survives on purpose. Until 2026-07-21 all three hours
surfaces summed those markers as worked hours (July: +28.5 real-staff hours
in the payroll report before pay was run). Policy: cancelled = not worked =
not paid. Every other status still counts.

Endpoints under test (real in-memory ORM rows + TestClient, auth overridden
on the router-local dependencies):
- GET /api/employee/monthly-hours
- GET /api/employee/payroll/monthly
- GET /api/payroll/monthly (admin)
"""
from datetime import date, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import RosterShift, ShiftStatus, ShiftType
from routers.roster import (
    get_current_user as roster_get_current_user,
    require_admin as roster_require_admin,
)

STAFF_ID = 14


def _employee():
    return SimpleNamespace(
        id=STAFF_ID, email="steve@tag.test", is_admin=False,
        first_name="Steve", last_name="Cooper", driver_type="fleet", is_active=True,
    )


def _admin():
    return SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True,
        first_name="Ad", last_name="Min", driver_type=None, is_active=True,
    )


@pytest.fixture
def client(db_session):
    app.dependency_overrides[roster_get_current_user] = _employee
    app.dependency_overrides[roster_require_admin] = _admin
    yield TestClient(app)
    app.dependency_overrides.pop(roster_get_current_user, None)
    app.dependency_overrides.pop(roster_require_admin, None)


def _add_shift(db, *, staff_id=STAFF_ID, date_, start, end, status, end_date=None,
               shift_type=ShiftType.MORNING, created_source="auto"):
    shift = RosterShift(
        staff_id=staff_id,
        date=date_,
        end_date=end_date,
        start_time=start,
        end_time=end,
        shift_type=shift_type,
        status=status,
        created_source=created_source,
    )
    db.add(shift)
    db.commit()
    return shift


def _add_staff_user(db, user_id, first_name, last_name):
    # List columns get '{}' (PG array literal) — the ORM's ARRAY type parses
    # them even on the SQLite test table, unlike the schema default '[]'.
    db.execute(text(
        "INSERT INTO users (id, email, first_name, last_name, is_admin, is_active, "
        "preferred_shift_types, excluded_shift_types, preferred_days_off) "
        "VALUES (:id, :email, :fn, :ln, 0, 1, '{}', '{}', '{}')"
    ), {"id": user_id, "email": f"{first_name.lower()}@tag.test", "fn": first_name, "ln": last_name})
    db.commit()


# =============================================================================
# /api/employee/monthly-hours
# =============================================================================

class TestEmployeeMonthlyHoursHUEB:

    def test_H_cancelled_shift_excluded_from_monthly_hours(self, client, db_session):
        _add_shift(db_session, date_=date(2026, 7, 6), start=time(9, 0), end=time(13, 0),
                   status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, date_=date(2026, 7, 7), start=time(9, 0), end=time(15, 0),
                   status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/monthly-hours?year=2026&month=7").json()

        assert body["total_hours"] == 4.0
        assert body["shift_count"] == 1

    def test_B_all_non_cancelled_statuses_still_count(self, client, db_session):
        """Only CANCELLED is a suppression marker — every other status is real work."""
        d = date(2026, 7, 6)
        for offset, status in enumerate([
            ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED,
            ShiftStatus.IN_PROGRESS, ShiftStatus.COMPLETED,
        ]):
            _add_shift(db_session, date_=date(2026, 7, 6 + offset),
                       start=time(9, 0), end=time(10, 0), status=status)
        _add_shift(db_session, date_=date(2026, 7, 10), start=time(9, 0), end=time(10, 0),
                   status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/monthly-hours?year=2026&month=7").json()

        assert body["shift_count"] == 4
        assert body["total_hours"] == 4.0

    def test_B_cancelled_overnight_shift_excluded(self, client, db_session):
        """Overnight cancelled shifts (the biggest hour blocks) must not count."""
        _add_shift(db_session, date_=date(2026, 7, 20), end_date=date(2026, 7, 21),
                   start=time(20, 0), end=time(2, 0), status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/monthly-hours?year=2026&month=7").json()

        assert body["total_hours"] == 0.0
        assert body["shift_count"] == 0

    def test_B_weekly_breakdown_excludes_cancelled(self, client, db_session):
        _add_shift(db_session, date_=date(2026, 7, 6), start=time(9, 0), end=time(12, 0),
                   status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, date_=date(2026, 7, 7), start=time(9, 0), end=time(12, 0),
                   status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/monthly-hours?year=2026&month=7").json()

        week = next(w for w in body["weeks"] if w["week_start"] <= "2026-07-06" <= w["week_end"])
        assert week["total_hours"] == 3.0
        assert week["shift_count"] == 1


# =============================================================================
# /api/employee/payroll/monthly
# =============================================================================

class TestEmployeePayrollHUEB:

    def test_H_cancelled_shift_excluded_from_employee_payroll(self, client, db_session):
        _add_shift(db_session, date_=date(2026, 7, 6), start=time(9, 0), end=time(14, 0),
                   status=ShiftStatus.COMPLETED)
        _add_shift(db_session, date_=date(2026, 7, 8), start=time(9, 0), end=time(18, 0),
                   status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/payroll/monthly?year=2026&month=7").json()

        assert body["total_hours"] == 5.0
        assert body["total_shifts"] == 1

    def test_U_only_cancelled_shifts_gives_zero_hours(self, client, db_session):
        _add_shift(db_session, date_=date(2026, 7, 6), start=time(9, 0), end=time(14, 0),
                   status=ShiftStatus.CANCELLED)

        body = client.get("/api/employee/payroll/monthly?year=2026&month=7").json()

        assert body["total_hours"] == 0.0
        assert body["total_shifts"] == 0


# =============================================================================
# /api/payroll/monthly (admin)
# =============================================================================

class TestAdminPayrollHUEB:

    def test_H_admin_payroll_excludes_cancelled_per_staff(self, client, db_session):
        _add_staff_user(db_session, STAFF_ID, "Steve", "Cooper")
        _add_staff_user(db_session, 7, "Marek", "Smolarek")
        # Steve: one real 4h shift + one cancelled 6h shift.
        _add_shift(db_session, staff_id=STAFF_ID, date_=date(2026, 7, 6),
                   start=time(9, 0), end=time(13, 0), status=ShiftStatus.SCHEDULED)
        _add_shift(db_session, staff_id=STAFF_ID, date_=date(2026, 7, 7),
                   start=time(9, 0), end=time(15, 0), status=ShiftStatus.CANCELLED)
        # Marek: cancelled only — must show zero hours, not vanish from the list.
        _add_shift(db_session, staff_id=7, date_=date(2026, 7, 8),
                   start=time(9, 0), end=time(20, 0), status=ShiftStatus.CANCELLED)

        body = client.get("/api/payroll/monthly?year=2026&month=7").json()

        by_id = {s["staff_id"]: s for s in body["staff"]}
        assert by_id[STAFF_ID]["total_hours"] == 4.0
        assert by_id[STAFF_ID]["total_shifts"] == 1
        assert by_id[7]["total_hours"] == 0.0
        assert by_id[7]["total_shifts"] == 0

    def test_B_month_totals_exclude_cancelled(self, client, db_session):
        _add_staff_user(db_session, STAFF_ID, "Steve", "Cooper")
        _add_shift(db_session, staff_id=STAFF_ID, date_=date(2026, 7, 1),
                   start=time(9, 0), end=time(11, 0), status=ShiftStatus.COMPLETED)
        _add_shift(db_session, staff_id=STAFF_ID, date_=date(2026, 7, 31),
                   start=time(9, 0), end=time(11, 0), status=ShiftStatus.CANCELLED)

        body = client.get("/api/payroll/monthly?year=2026&month=7").json()

        assert body["totals"]["total_hours"] == 2.0
        assert body["totals"]["total_shifts"] == 1
