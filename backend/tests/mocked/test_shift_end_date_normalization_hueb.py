"""
end_date consistency (2026-07-22 Aug-10 missing-jockeys incident) — hueb.

Times are canonical: end <= start means overnight, otherwise same-day. A
spurious next-day end_date on a same-day evening shift made _shift_window
read a 26h phantom that swallowed the NEXT day's windows in the coverage
check (missing jockey shifts, unlinked bookings) and inflated payroll +24h.

Covers: _shift_window inference at the midnight boundary, write-path
normalization on admin create/update, and the rebuild regression — a
corrupt prior-day row must not block the next day's jockey generation.
"""
from datetime import date as date_type, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_roster import _rebuild_window_auto_for_dates, _shift_window
from db_models import (
    Booking, BookingStatus, RosterShift, RosterWindowTemplate,
    ShiftStatus, ShiftType,
)
from main import app
from roster_planner import PlannerSettings
from routers.roster import (
    _normalize_shift_end_date,
    get_current_user as roster_get_current_user,
    require_admin as roster_require_admin,
)

V4_FROM = date_type(2026, 8, 10)
DAY = date_type(2026, 8, 10)


def _ns_shift(date_, end_date, start, end):
    return SimpleNamespace(date=date_, end_date=end_date, start_time=start, end_time=end)


class TestShiftWindowInferenceHUEB:

    def test_B_midnight_boundary_triple(self):
        d = date_type(2026, 8, 9)
        # t-eps: 21:15 -> 23:45 same-day EVEN with corrupt end_date
        s, e = _shift_window(_ns_shift(d, d + timedelta(days=1), time(21, 15), time(23, 45)))
        assert (s, e) == (datetime(2026, 8, 9, 21, 15), datetime(2026, 8, 9, 23, 45))
        # t: end == start -> overnight (24h wrap semantics)
        s, e = _shift_window(_ns_shift(d, None, time(21, 15), time(21, 15)))
        assert e == datetime(2026, 8, 10, 21, 15)
        # t+eps: end 00:30 -> overnight regardless of missing end_date
        s, e = _shift_window(_ns_shift(d, None, time(21, 15), time(0, 30)))
        assert e == datetime(2026, 8, 10, 0, 30)


class TestWriteNormalizationHUEB:

    def test_H_same_day_times_clear_end_date(self):
        shift = _ns_shift(date_type(2026, 8, 9), date_type(2026, 8, 10), time(21, 15), time(23, 45))
        _normalize_shift_end_date(shift)
        assert shift.end_date is None

    def test_H_overnight_times_set_next_day(self):
        shift = _ns_shift(date_type(2026, 8, 9), None, time(21, 15), time(0, 30))
        _normalize_shift_end_date(shift)
        assert shift.end_date == date_type(2026, 8, 10)

    def test_H_admin_update_normalizes(self, db_session):
        app.dependency_overrides[roster_require_admin] = lambda: SimpleNamespace(
            id=1, email="a@t", is_admin=True, driver_type=None, is_active=True,
            first_name="A", last_name="D",
        )
        try:
            shift = RosterShift(
                date=date_type(2026, 8, 9), end_date=date_type(2026, 8, 10),
                start_time=time(21, 15), end_time=time(0, 30),
                shift_type=ShiftType.LATE_AFTERNOON, status=ShiftStatus.SCHEDULED,
                created_source="auto",
            )
            db_session.add(shift)
            db_session.commit()

            # Admin pulls the end back before midnight — stale end_date must clear.
            resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"end_time": "23:45"})
            assert resp.status_code == 200, resp.text
            db_session.refresh(shift)
            assert shift.end_time == time(23, 45)
            assert shift.end_date is None
        finally:
            app.dependency_overrides.pop(roster_require_admin, None)


class TestPhantomCoverageRegressionHUEB:

    def test_H_corrupt_prior_day_shift_does_not_swallow_next_day(self, db_session):
        """Reproduction of Aug 10: an assigned prior-evening shift with a
        spurious next-day end_date must NOT count as jockey coverage for the
        next day's windows — the pair must be generated."""
        for profile in ("weekday", "weekend"):
            for sort, (label, s, e) in enumerate([
                ("early", time(3, 30), time(10, 30)),
                ("day", time(10, 30), time(18, 30)),
                ("late", time(18, 30), time(1, 30)),
            ]):
                db_session.add(RosterWindowTemplate(
                    profile=profile, label=label, start_time=s, end_time=e,
                    sort_order=sort, is_active=True, effective_from=V4_FROM,
                ))
        # The corrupt row: Aug 9 21:15-23:45 assigned, end_date wrongly Aug 10.
        db_session.add(RosterShift(
            date=DAY - timedelta(days=1), end_date=DAY,
            start_time=time(21, 15), end_time=time(23, 45),
            shift_type=ShiftType.LATE_AFTERNOON, status=ShiftStatus.SCHEDULED,
            created_source="auto", intended_driver_type="jockey", staff_id=16,
            assigned_source="admin",
        ))
        db_session.add(Booking(
            reference="TAG-PHANTM01", customer_id=1, vehicle_id=1, package="full",
            status=BookingStatus.CONFIRMED,
            dropoff_date=DAY, dropoff_time=time(5, 0),
            pickup_date=DAY + timedelta(days=7), pickup_time=time(12, 0),
        ))
        db_session.commit()

        summary = _rebuild_window_auto_for_dates(db_session, [DAY], PlannerSettings.from_kv({}))

        early = [s for s in db_session.query(RosterShift).filter(RosterShift.date == DAY)
                 if s.start_time == time(3, 30)]
        assert summary["created"] == 1        # jockey generated despite the phantom
        assert summary["created_fleet"] == 1
        assert {s.intended_driver_type for s in early} == {"jockey", "fleet"}
