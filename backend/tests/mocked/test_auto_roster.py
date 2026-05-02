"""
Unit tests for the auto-roster live-write path (`backend/auto_roster.py`).

The 2026-05-02 refactor swapped per-event extend logic for per-day rebuild
using the engine's `group_events_by_gap`. Tests focus on the rebuild
behaviour (clusters per the consecutive-event gap rule, refunded kept,
cancelled / P&R excluded, untouched-only deletion).

Per SPEC.md every subject covers Happy / Unhappy / Edge / Boundary.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auto_roster import (  # noqa: E402
    _events_for_booking,
    _shift_window,
    _affected_dates_for_booking,
    rebuild_auto_for_dates,
    auto_create_or_extend_for_booking,
    handle_booking_cancelled,
    delete_all_auto_shifts,
)
from db_models import (  # noqa: E402
    BookingStatus,
    ServiceType,
    ShiftStatus,
    ShiftType,
)
from roster_planner import PlannerSettings  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def mk_booking(
    *,
    booking_id: int = 1,
    reference: str = "TAG-AUTO0001",
    status: BookingStatus = BookingStatus.CONFIRMED,
    service_type: ServiceType = ServiceType.MEET_GREET,
    dropoff_dt: datetime = datetime(2026, 6, 10, 8, 0),
    pickup_dt: datetime = datetime(2026, 6, 17, 14, 0),
    flight_arrival_time=None,
):
    """SimpleNamespace booking — auto_roster only reads attributes."""
    return SimpleNamespace(
        id=booking_id,
        reference=reference,
        status=status,
        service_type=service_type,
        dropoff_date=dropoff_dt.date(),
        dropoff_time=dropoff_dt.time(),
        pickup_date=pickup_dt.date(),
        pickup_time=pickup_dt.time(),
        flight_arrival_time=flight_arrival_time,
    )


def mk_settings(
    *,
    gap_max_minutes: int = 190,        # match live setting
    mixed_gap_max_minutes: int = 190,
    start_buffer_minutes: int = 20,
    end_buffer_minutes: int = 30,
    min_shift_minutes: int = 60,
    window_days: int = 28,
):
    return PlannerSettings(
        window_days=window_days,
        gap_max_minutes=gap_max_minutes,
        mixed_gap_max_minutes=mixed_gap_max_minutes,
        start_buffer_minutes=start_buffer_minutes,
        end_buffer_minutes=end_buffer_minutes,
        staffing_thresholds=[(3, 1), (999, 2)],
        max_hours_per_week=40,
        min_rest_hours=8,
        untouchable_hours=24,
        min_shift_minutes=min_shift_minutes,
    )


def make_db(*, untouched_auto_shifts=None, bookings=None):
    """A MagicMock db that:
      - returns `untouched_auto_shifts` for the rebuild's delete-candidate query
      - returns `bookings` for the rebuild's source query
      - records db.add / db.delete / db.commit for assertions
    """
    db = MagicMock()
    untouched_auto_shifts = list(untouched_auto_shifts or [])
    bookings = list(bookings or [])
    added = []
    deleted = []

    from db_models import Booking, RosterShift, ShiftBookingLink

    # Track which queries we've answered so the test can introspect
    state = {"shift_query_calls": 0, "booking_query_calls": 0}

    def query_side_effect(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        if model is RosterShift:
            state["shift_query_calls"] += 1
            chain.all.return_value = list(untouched_auto_shifts)
            chain.first.return_value = untouched_auto_shifts[0] if untouched_auto_shifts else None
        elif model is Booking:
            state["booking_query_calls"] += 1
            chain.all.return_value = list(bookings)
            chain.first.return_value = bookings[0] if bookings else None
        elif model is ShiftBookingLink:
            chain.all.return_value = []
            chain.first.return_value = None
        else:
            chain.all.return_value = []
            chain.first.return_value = None
        return chain

    db.query.side_effect = query_side_effect
    db.add.side_effect = lambda obj: added.append(obj)
    db.delete.side_effect = lambda obj: deleted.append(obj)
    db._added = added
    db._deleted = deleted
    db._state = state
    return db


# ===========================================================================
# _events_for_booking (pure)
# ===========================================================================

class TestEventsForBooking:
    def test_happy_dropoff_and_pickup_extracted(self):
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        events = _events_for_booking(b)
        assert events[0] == ("drop_off", datetime(2026, 6, 10, 8, 30))
        assert events[1] == ("pick_up", datetime(2026, 6, 17, 14, 0) - timedelta(minutes=30))

    def test_edge_pickup_uses_flight_arrival_when_set(self):
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
            flight_arrival_time=time(13, 30),
        )
        events = _events_for_booking(b)
        pickup = next(e for e in events if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 13, 30)

    def test_unhappy_missing_dropoff_time_skipped(self):
        b = SimpleNamespace(
            id=1, reference="X", status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=date(2026, 6, 10), dropoff_time=None,
            pickup_date=date(2026, 6, 17), pickup_time=time(14, 0),
            flight_arrival_time=None,
        )
        assert [e[0] for e in _events_for_booking(b)] == ["pick_up"]

    def test_boundary_no_dates_at_all_returns_empty(self):
        b = SimpleNamespace(
            id=1, reference="X", status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=None, dropoff_time=None,
            pickup_date=None, pickup_time=None,
            flight_arrival_time=None,
        )
        assert _events_for_booking(b) == []


# ===========================================================================
# _shift_window (pure)
# ===========================================================================

class TestShiftWindow:
    def test_happy_single_day_shift(self):
        s = SimpleNamespace(
            date=date(2026, 6, 10), end_date=None,
            start_time=time(7, 30), end_time=time(14, 30),
        )
        start, end = _shift_window(s)
        assert start == datetime(2026, 6, 10, 7, 30)
        assert end == datetime(2026, 6, 10, 14, 30)

    def test_edge_overnight_shift_uses_end_date(self):
        s = SimpleNamespace(
            date=date(2026, 6, 10), end_date=date(2026, 6, 11),
            start_time=time(22, 0), end_time=time(2, 0),
        )
        start, end = _shift_window(s)
        assert start == datetime(2026, 6, 10, 22, 0)
        assert end == datetime(2026, 6, 11, 2, 0)


# ===========================================================================
# _affected_dates_for_booking (pure)
# ===========================================================================

class TestAffectedDates:
    def test_happy_two_distinct_dates(self):
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 0),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        assert _affected_dates_for_booking(b) == {date(2026, 6, 10), date(2026, 6, 17)}


# ===========================================================================
# rebuild_auto_for_dates — the new core
# ===========================================================================

class TestRebuildAutoForDates:
    def test_happy_single_event_creates_one_shift(self):
        b = mk_booking(
            booking_id=10,
            reference="TAG-SINGLE01",
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        db = make_db(bookings=[b])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())
        # Shift on 2026-06-10 created (from 8:30 dropoff). Pickup on 6/17
        # is out of target_set; that day's rebuild would own it.
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.date == date(2026, 6, 10)
        assert s.start_time == time(8, 10)   # 8:30 - 20m start_buffer
        assert s.end_time == time(9, 10)     # 8:30 + 30m end_buffer = 9:00, but min_shift = 60m → 9:10
        assert s.staff_id is None
        assert s.created_source == "auto"
        assert result["created"] == 1

    def test_happy_three_events_within_gap_cluster_into_one_shift(self):
        """gap_max=190 means events at 12:45 / 13:15 / 15:45 should cluster
        (gaps 30 / 150 — both ≤ 190). Single shift covers 11:55-16:15."""
        b1 = mk_booking(
            booking_id=1, reference="TAG-CLU0001",
            dropoff_dt=datetime(2026, 6, 11, 12, 45),
            pickup_dt=datetime(2026, 7, 11, 14, 0),  # far out — won't matter
        )
        b2 = mk_booking(
            booking_id=2, reference="TAG-CLU0002",
            dropoff_dt=datetime(2026, 6, 11, 13, 15),
            pickup_dt=datetime(2026, 7, 11, 14, 0),
        )
        b3 = mk_booking(
            booking_id=3, reference="TAG-CLU0003",
            dropoff_dt=datetime(2026, 6, 11, 15, 45),
            pickup_dt=datetime(2026, 7, 11, 14, 0),
        )
        db = make_db(bookings=[b1, b2, b3])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 11)}, mk_settings(gap_max_minutes=190))
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        # Only 1 shift on the target date — pickups on 7/11 are filtered out
        # because their date isn't in target_set.
        new_shifts = [s for s in new_shifts if s.date == date(2026, 6, 11)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(12, 25)   # 12:45 - 20m
        assert s.end_time == time(16, 15)     # 15:45 + 30m

    def test_unhappy_split_when_consecutive_gap_exceeds_threshold(self):
        """Same three events, but the middle one removed → 12:45 and 15:45,
        gap=180min ≤ 190 → still ONE shift. Bump gap_max to 120 (the wrong
        old default) and the same set splits. Confirms cluster threshold
        is honoured."""
        b1 = mk_booking(
            booking_id=1, reference="TAG-GAP0001",
            dropoff_dt=datetime(2026, 6, 11, 12, 45),
            pickup_dt=datetime(2026, 7, 11, 14, 0),
        )
        b2 = mk_booking(
            booking_id=3, reference="TAG-GAP0003",
            dropoff_dt=datetime(2026, 6, 11, 15, 45),
            pickup_dt=datetime(2026, 7, 11, 14, 0),
        )
        # gap_max=120: 180min gap > 120 → split
        db = make_db(bookings=[b1, b2])
        rebuild_auto_for_dates(db, {date(2026, 6, 11)}, mk_settings(gap_max_minutes=120, mixed_gap_max_minutes=120))
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 11)]
        assert len(new_shifts) == 2

    def test_edge_refunded_booking_still_included(self):
        b = mk_booking(
            booking_id=99, reference="TAG-REF00001",
            status=BookingStatus.REFUNDED,
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 7, 1, 10, 0),
        )
        db = make_db(bookings=[b])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        # And the refunded booking IS linked to it.
        from db_models import ShiftBookingLink
        links = [a for a in db._added if isinstance(a, ShiftBookingLink)]
        assert any(l.booking_id == 99 for l in links)

    def test_edge_park_and_ride_booking_excluded(self):
        b = mk_booking(
            booking_id=2, reference="TAG-PR000001",
            service_type=ServiceType.PARK_RIDE,
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 7, 1, 10, 0),
        )
        db = make_db(bookings=[b])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == []
        assert result["created"] == 0

    def test_edge_rebuild_deletes_untouched_auto_shifts_on_target_date(self):
        """Force-rebuild semantics: every untouched auto-shift on the day
        is wiped before recreation."""
        existing = SimpleNamespace(
            id=42, created_source="auto", staff_id=None,
            status=ShiftStatus.SCHEDULED,
            date=date(2026, 6, 10), end_date=None,
            start_time=time(7, 0), end_time=time(8, 0),
            shift_type=ShiftType.MORNING,
        )
        db = make_db(untouched_auto_shifts=[existing], bookings=[])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())
        assert existing in db._deleted
        assert result["deleted"] == 1
        assert result["created"] == 0

    def test_boundary_overnight_cluster_attributed_to_first_event_date(self):
        """A booking with pickup 00:25 (anchor 23:55 prev day) and dropoff
        on prev day's 22:30 → cluster spans midnight, but is anchored to
        the prev day. Rebuilding only the prev day creates the shift; the
        next day's rebuild does NOT duplicate it."""
        b1 = mk_booking(
            booking_id=1, reference="TAG-NIGHT001",
            dropoff_dt=datetime(2026, 6, 10, 22, 30),
            pickup_dt=datetime(2026, 7, 1, 10, 0),
        )
        b2 = mk_booking(
            booking_id=2, reference="TAG-NIGHT002",
            dropoff_dt=datetime(2026, 7, 1, 8, 0),  # not the cluster
            pickup_dt=datetime(2026, 6, 11, 0, 25),  # anchor: 11/06 00:25 - 30 = 10/06 23:55
        )
        # Build 10/06 first
        db = make_db(bookings=[b1, b2])
        rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())
        from db_models import RosterShift
        first_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        # One cross-midnight shift created (start date = 10/06).
        assert len(first_shifts) >= 1
        cross = [s for s in first_shifts if s.date == date(2026, 6, 10)]
        assert len(cross) == 1

        # Now rebuild 11/06 only — cluster starts on 10/06 so should be
        # skipped to avoid double-creation.
        db2 = make_db(bookings=[b1, b2])
        rebuild_auto_for_dates(db2, {date(2026, 6, 11)}, mk_settings())
        new_shifts = [a for a in db2._added if isinstance(a, RosterShift)]
        # 11/06 has b2's dropoff at 08:00 → that's its own cluster.
        # The cross-midnight cluster should NOT also be recreated.
        assert all(s.date != date(2026, 6, 10) for s in new_shifts)


# ===========================================================================
# auto_create_or_extend_for_booking — top-level entry point
# ===========================================================================

class TestAutoCreateOrExtendForBooking:
    def test_unhappy_refunded_booking_is_no_op(self):
        db = make_db()
        b = mk_booking(status=BookingStatus.REFUNDED)
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result["skipped"] == 1
        db.add.assert_not_called()

    def test_unhappy_cancelled_booking_is_no_op(self):
        db = make_db()
        b = mk_booking(status=BookingStatus.CANCELLED)
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result["skipped"] == 1

    def test_unhappy_park_and_ride_booking_is_no_op(self):
        db = make_db()
        b = mk_booking(service_type=ServiceType.PARK_RIDE)
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result["skipped"] == 1

    def test_happy_confirmed_booking_triggers_rebuild(self):
        b = mk_booking(
            booking_id=10, reference="TAG-OK000001",
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        db = make_db(bookings=[b])
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        # Two events → two affected dates → rebuild creates two shifts.
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 2


# ===========================================================================
# delete_all_auto_shifts
# ===========================================================================

class TestDeleteAllAutoShifts:
    def test_happy_deletes_only_untouched(self):
        s1 = SimpleNamespace(id=1, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        s2 = SimpleNamespace(id=2, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        db = make_db(untouched_auto_shifts=[s1, s2])
        n = delete_all_auto_shifts(db)
        assert n == 2
        assert s1 in db._deleted
        assert s2 in db._deleted

    def test_unhappy_no_auto_shifts_returns_zero(self):
        db = make_db()
        assert delete_all_auto_shifts(db) == 0
        db.commit.assert_not_called()
