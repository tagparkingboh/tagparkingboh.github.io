"""
Roster v4 Phase 2 (2026-07-22) — hueb tests for date-versioned windows and
fleet twins.

Spec: from Aug 10 the day is three windows (03:30-10:30, 10:30-18:30,
18:30-01:30 next day) every day, each generated as a jockey shift (carries
booking links / coverage) plus an identical fleet twin (extra capacity, no
links). Days before Aug 10 keep the legacy 4-window layout and grow no twins.

Real in-memory ORM rows; the rebuild engine is exercised directly.
"""
from datetime import date as date_type, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_roster import _rebuild_window_auto_for_dates, _windows_for_day
from db_models import (
    Booking,
    BookingStatus,
    RosterShift,
    RosterWindowTemplate,
    ShiftBookingLink,
    ShiftStatus,
    ShiftType,
)
from roster_planner import PlannerSettings

V4_FROM = date_type(2026, 8, 10)
PRE_V4_DAY = date_type(2026, 8, 5)    # Wednesday, legacy windows
V4_DAY = date_type(2026, 8, 12)       # Wednesday, v4 windows

LEGACY_WINDOWS = [
    ("early", time(3, 0), time(9, 0)),
    ("day", time(9, 30), time(15, 30)),
    ("late", time(15, 45), time(20, 45)),
    ("overnight", time(21, 0), time(2, 0)),
]
V4_WINDOWS = [
    ("early", time(3, 30), time(10, 30)),
    ("day", time(10, 30), time(18, 30)),
    ("late", time(18, 30), time(1, 30)),
]


@pytest.fixture
def seeded(db_session):
    for profile in ("weekday", "weekend"):
        for sort, (label, start, end) in enumerate(LEGACY_WINDOWS):
            db_session.add(RosterWindowTemplate(
                profile=profile, label=label, start_time=start, end_time=end,
                sort_order=sort, is_active=True, effective_from=None,
            ))
        for sort, (label, start, end) in enumerate(V4_WINDOWS):
            db_session.add(RosterWindowTemplate(
                profile=profile, label=label, start_time=start, end_time=end,
                sort_order=sort, is_active=True, effective_from=V4_FROM,
            ))
    db_session.commit()
    return db_session


def _booking(db, *, dropoff, dropoff_time_, pickup=None, pickup_time_=None,
             arrival_date=None, arrival_time=None, ref=None):
    booking = Booking(
        reference=ref or f"TAG-TST{db.query(Booking).count():05d}",
        customer_id=1,
        vehicle_id=1,
        package="full",
        status=BookingStatus.CONFIRMED,
        dropoff_date=dropoff,
        dropoff_time=dropoff_time_,
        pickup_date=pickup or (dropoff + timedelta(days=7)),
        pickup_time=pickup_time_ or time(12, 0),
        flight_arrival_date=arrival_date,
        flight_arrival_time=arrival_time,
    )
    db.add(booking)
    db.commit()
    return booking


def _shifts(db):
    return db.query(RosterShift).order_by(RosterShift.start_time, RosterShift.intended_driver_type).all()


def _settings():
    return PlannerSettings.from_kv({})


class TestWindowGenerationsHUEB:

    def test_H_generation_selection_boundary(self, seeded):
        rows = seeded.query(RosterWindowTemplate).all()
        # t-1 day: legacy 4 windows
        before = _windows_for_day(rows, V4_FROM - timedelta(days=1))
        assert [w.start_time for w in before] == [w[1] for w in LEGACY_WINDOWS]
        # t: v4 3 windows exactly on the effective date
        at = _windows_for_day(rows, V4_FROM)
        assert [(w.start_time, w.end_time) for w in at] == [(w[1], w[2]) for w in V4_WINDOWS]
        # t+many: still v4
        after = _windows_for_day(rows, V4_FROM + timedelta(days=60))
        assert len(after) == 3

    def test_B_weekend_profile_same_windows(self, seeded):
        rows = seeded.query(RosterWindowTemplate).all()
        saturday = date_type(2026, 8, 15)
        assert [(w.start_time, w.end_time) for w in _windows_for_day(rows, saturday)] \
            == [(w[1], w[2]) for w in V4_WINDOWS]


class TestFleetTwinsHUEB:

    def test_H_v4_day_creates_jockey_and_fleet_pair(self, seeded):
        booking = _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(5, 0))

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        shifts = _shifts(seeded)
        assert summary["created"] == 1 and summary["created_fleet"] == 1
        assert len(shifts) == 2
        jockey = next(s for s in shifts if s.intended_driver_type == "jockey")
        fleet = next(s for s in shifts if s.intended_driver_type == "fleet")
        # identical windows — the early 03:30-10:30 block
        for s in (jockey, fleet):
            assert (s.start_time, s.end_time) == (time(3, 30), time(10, 30))
            assert s.date == V4_DAY
        # links on the jockey shift only
        links = seeded.query(ShiftBookingLink).all()
        assert {l.shift_id for l in links} == {jockey.id}
        assert {l.booking_id for l in links} == {booking.id}

    def test_H_late_window_overnight_end_date(self, seeded):
        _booking(seeded, dropoff=V4_DAY - timedelta(days=5), dropoff_time_=time(9, 0),
                 pickup=V4_DAY, pickup_time_=time(23, 30),
                 arrival_date=V4_DAY, arrival_time=time(23, 0))

        _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        late = [s for s in _shifts(seeded) if s.start_time == time(18, 30)]
        assert len(late) == 2  # jockey + fleet twin
        for s in late:
            assert s.end_time == time(1, 30)
            assert s.end_date == V4_DAY + timedelta(days=1)

    def test_B_pre_v4_day_uses_legacy_windows_and_no_twin(self, seeded):
        _booking(seeded, dropoff=PRE_V4_DAY, dropoff_time_=time(5, 0))

        summary = _rebuild_window_auto_for_dates(seeded, [PRE_V4_DAY], _settings())

        shifts = _shifts(seeded)
        assert summary["created"] == 1 and summary["created_fleet"] == 0
        assert len(shifts) == 1
        assert shifts[0].intended_driver_type == "jockey"
        assert (shifts[0].start_time, shifts[0].end_time) == (time(3, 0), time(9, 0))

    def test_U_surviving_assigned_fleet_twin_not_duplicated(self, seeded):
        _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(5, 0))
        seeded.add(RosterShift(
            staff_id=14, assigned_source="admin", date=V4_DAY,
            start_time=time(3, 30), end_time=time(10, 30),
            shift_type=ShiftType.EARLY_MORNING, status=ShiftStatus.SCHEDULED,
            created_source="auto", intended_driver_type="fleet",
        ))
        seeded.commit()

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        assert summary["created"] == 1        # jockey still needed
        assert summary["created_fleet"] == 0  # assigned twin already there
        fleet = [s for s in _shifts(seeded) if s.intended_driver_type == "fleet"]
        assert len(fleet) == 1 and fleet[0].staff_id == 14

    def test_U_covered_jockey_still_gets_fleet_twin(self, seeded):
        _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(5, 0))
        seeded.add(RosterShift(
            staff_id=21, assigned_source="claim", date=V4_DAY,
            start_time=time(3, 30), end_time=time(10, 30),
            shift_type=ShiftType.EARLY_MORNING, status=ShiftStatus.SCHEDULED,
            created_source="auto", intended_driver_type="jockey",
        ))
        seeded.commit()

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        assert summary["created"] == 0 and summary["skipped_covered"] == 1
        assert summary["created_fleet"] == 1

    def test_U_suppressed_fleet_twin_blocks_only_fleet(self, seeded):
        _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(5, 0))
        seeded.add(RosterShift(
            staff_id=None, date=V4_DAY,
            start_time=time(3, 30), end_time=time(10, 30),
            shift_type=ShiftType.EARLY_MORNING, status=ShiftStatus.CANCELLED,
            created_source="auto", intended_driver_type="fleet",
            suppressed_at=datetime.now(timezone.utc), suppression_reason="admin_delete",
        ))
        seeded.commit()

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        assert summary["created"] == 1        # jockey unaffected
        assert summary["created_fleet"] == 0  # fleet stays deleted
        assert all(s.intended_driver_type != "fleet" or s.status == ShiftStatus.CANCELLED
                   for s in seeded.query(RosterShift).all())


class TestBoundaryFallbackHUEB:

    def test_B_event_straddling_window_boundary_still_gets_shift(self, seeded):
        """10:20 drop-off: buffered coverage crosses the 10:30 line so no
        window contains it whole — raw-anchor fallback places it in the
        early window instead of orphaning the booking."""
        _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(10, 20))

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        assert summary["created"] == 1
        assert summary["orphans"] == 0
        jockey = next(s for s in _shifts(seeded) if s.intended_driver_type == "jockey")
        assert (jockey.start_time, jockey.end_time) == (time(3, 30), time(10, 30))

    def test_B_event_exactly_on_boundary_goes_to_later_window(self, seeded):
        _booking(seeded, dropoff=V4_DAY, dropoff_time_=time(10, 30))

        _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        jockey = next(s for s in _shifts(seeded) if s.intended_driver_type == "jockey")
        assert (jockey.start_time, jockey.end_time) == (time(10, 30), time(18, 30))
