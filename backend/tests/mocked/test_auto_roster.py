"""
Unit tests for the auto-roster live-write path (`backend/auto_roster.py`).

The 2026-05-02 refactor swapped per-event extend logic for per-day rebuild
using the engine's `group_events_by_gap`. Tests focus on the rebuild
behaviour (clusters per the consecutive-event gap rule, refunded kept,
cancelled / P&R excluded, untouched-only deletion).

Per SPEC.md every subject covers Happy / Unhappy / Edge / Boundary.
"""
from __future__ import annotations

import logging
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
    _windows_overlap,
    _shift_linked_booking_ids,
    _is_auto_shift_eligible_for_rebuild,
    _affected_dates_for_booking,
    rebuild_auto_for_dates,
    auto_create_or_extend_for_booking,
    auto_create_or_extend_async,
    handle_booking_cancelled,
    handle_booking_cancelled_async,
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


def make_db(*, untouched_auto_shifts=None, assigned_shifts=None, suppressed_shifts=None,
            bookings=None, existing_links_by_shift=None):
    """A MagicMock db that:
      - returns `untouched_auto_shifts` for the rebuild's delete-candidate query
        (filtered by `staff_id IS NULL`)
      - returns `assigned_shifts` for the new extend-candidate query
        (filtered by `staff_id IS NOT NULL`)
      - returns `bookings` for the rebuild's source query
      - returns `existing_links_by_shift.get(sid, [])` for ShiftBookingLink
        queries filtered by `shift_id == sid`
      - records db.add / db.delete / db.commit for assertions
    """
    db = MagicMock()
    untouched_auto_shifts = list(untouched_auto_shifts or [])
    assigned_shifts = list(assigned_shifts or [])
    suppressed_shifts = list(suppressed_shifts or [])
    bookings = list(bookings or [])
    existing_links_by_shift = dict(existing_links_by_shift or {})
    added = []
    deleted = []

    from db_models import Booking, RosterShift, ShiftBookingLink

    state = {"shift_query_calls": 0, "booking_query_calls": 0}

    def _filter_str(args):
        # SQLAlchemy expressions stringify to roughly the SQL fragment; we
        # peek at this to decide whether the caller is asking for assigned
        # shifts (the new code path) or the legacy unassigned-auto bucket.
        return " ".join(str(a) for a in args)

    def query_side_effect(model):
        chain = MagicMock()
        captured_filters = []

        def capture_filter(*args, **kwargs):
            captured_filters.append(args)
            return chain
        chain.filter.side_effect = capture_filter

        def _status_allowed(shift_status, captured) -> bool:
            """Inspect captured filter args for a `status.in_([...])`
            clause and check whether `shift_status` is in the allowed
            list. Returns True (allowed) when no status filter is present
            OR when the inspector can't decode the args (defensive — the
            test should still see its rows). Mirrors the production
            query's status filter so a test that stuffs an IN_PROGRESS
            shift into the pool gets the same exclusion the real DB
            would apply."""
            try:
                from sqlalchemy.sql import operators as sqla_ops
            except Exception:
                return True
            for args in captured:
                for arg in args:
                    op = getattr(arg, "operator", None)
                    if op is not getattr(sqla_ops, "in_op", None):
                        continue
                    left = getattr(arg, "left", None)
                    if getattr(left, "key", None) != "status":
                        continue
                    # SQLAlchemy wraps the whole list into a single
                    # BindParameter whose .value is the python list.
                    right = getattr(arg, "right", None)
                    allowed = getattr(right, "value", None)
                    if isinstance(allowed, (list, tuple)):
                        return shift_status in allowed
                    # Unknown shape — defensive default.
                    return True
            return True

        def _is_null_required(col_name: str, captured) -> bool:
            """Returns True if any captured filter contains
            `Column.is_(None)` on this column. SQLAlchemy renders the
            right side as a `Null` instance (no `.value` attribute) for
            this case — so the operator + column-key match is sufficient
            to identify it."""
            try:
                from sqlalchemy.sql import operators as sqla_ops
                from sqlalchemy.sql.elements import Null
            except Exception:
                return False
            for args in captured:
                for arg in args:
                    op = getattr(arg, "operator", None)
                    if op is not getattr(sqla_ops, "is_", None):
                        continue
                    left = getattr(arg, "left", None)
                    if getattr(left, "key", None) != col_name:
                        continue
                    right = getattr(arg, "right", None)
                    if isinstance(right, Null):
                        return True
            return False

        def _status_equals(captured, expected_status) -> bool:
            try:
                from sqlalchemy.sql import operators as sqla_ops
            except Exception:
                return False
            for args in captured:
                for arg in args:
                    op = getattr(arg, "operator", None)
                    if op is not getattr(sqla_ops, "eq", None):
                        continue
                    left = getattr(arg, "left", None)
                    if getattr(left, "key", None) != "status":
                        continue
                    right = getattr(arg, "right", None)
                    if getattr(right, "value", None) == expected_status:
                        return True
            return False

        def shift_all():
            blob = " ".join(_filter_str(a) for a in captured_filters)
            if _status_equals(captured_filters, ShiftStatus.CANCELLED):
                return list(suppressed_shifts)
            if "IS NOT NULL" in blob:
                # Driver-trust pivot 2026-05-28: the rebuild's "frozen
                # shifts" query (skip-if-covered) intentionally includes
                # manual shifts AND admin-shaped auto shifts AND assigned
                # auto shifts. Honour the production status filter so
                # IN_PROGRESS rows are excluded from the frozen pool just
                # like the real DB would do them.
                return [
                    s for s in assigned_shifts
                    if _status_allowed(getattr(s, "status", None), captured_filters)
                ]
            pool = list(untouched_auto_shifts)
            # Honour `admin_shaped_at IS NULL` on the wipe / delete-all
            # paths so a test that drops an admin-shaped row in here
            # still gets the production-equivalent preservation.
            if _is_null_required("admin_shaped_at", captured_filters):
                pool = [
                    s for s in pool
                    if getattr(s, "admin_shaped_at", None) is None
                ]
            return pool

        def link_all():
            sid = None
            for args in captured_filters:
                for a in args:
                    right = getattr(a, "right", None)
                    val = getattr(right, "value", None)
                    if isinstance(val, int):
                        sid = val
            if sid is None:
                return []
            return list(existing_links_by_shift.get(sid, []))

        if model is RosterShift:
            state["shift_query_calls"] += 1
            chain.all.side_effect = shift_all
            chain.first.return_value = (
                untouched_auto_shifts[0] if untouched_auto_shifts else None
            )
        elif model is Booking:
            state["booking_query_calls"] += 1
            chain.all.return_value = list(bookings)
            chain.first.return_value = bookings[0] if bookings else None
        elif model is ShiftBookingLink:
            chain.all.side_effect = link_all
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
        # 3-tuple shape: (event_type, start_anchor, end_anchor).
        # Drop-off: both anchors == dropoff_time (handoff at customer arrival).
        # Pickup (no flight_arrival): start = pickup_time-30 (jockey readiness),
        #   end = pickup_time (customer handoff).
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        events = _events_for_booking(b)
        assert events[0] == (
            "drop_off",
            datetime(2026, 6, 10, 8, 30),
            datetime(2026, 6, 10, 8, 30),
        )
        assert events[1] == (
            "pick_up",
            datetime(2026, 6, 17, 13, 30),
            datetime(2026, 6, 17, 14, 0),
        )

    def test_edge_pickup_uses_flight_arrival_when_set(self):
        # Pickup with flight_arrival explicit: start = arrival, end = pickup_time.
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
            flight_arrival_time=time(13, 30),
        )
        events = _events_for_booking(b)
        pickup = next(e for e in events if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 13, 30)
        assert pickup[2] == datetime(2026, 6, 17, 14, 0)

    def test_edge_pickup_flight_arrival_crosses_midnight_backwards(self):
        # Flight lands 23:55 on day D-1, customer picks up car at 00:25 on
        # day D. flight_arrival_time has no date column, so START anchor
        # back-dates; END anchor stays on pickup_date.
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 18, 0, 25),
            flight_arrival_time=time(23, 55),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 23, 55)  # start = night before
        assert pickup[2] == datetime(2026, 6, 18, 0, 25)   # end = customer handoff next day

    def test_boundary_flight_arrival_equal_to_pickup_time_stays_same_day(self):
        # Equal times — no overnight crossing. start = arrival; end = arrival
        # + 30 (the standard handoff offset, derived from arrival, not read
        # from stored pickup_time).
        b = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 14, 0),
            flight_arrival_time=time(14, 0),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 14, 0)
        assert pickup[2] == datetime(2026, 6, 17, 14, 30)

    def test_boundary_flight_arrival_one_minute_after_pickup_back_dates(self):
        # 1-minute over the boundary triggers back-dating of the start anchor;
        # end_anchor follows as start + 30, so it lands the same day as start.
        b = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 0, 25),
            flight_arrival_time=time(0, 26),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 16, 0, 26)
        assert pickup[2] == datetime(2026, 6, 16, 0, 56)

    def test_boundary_flight_arrival_one_minute_before_pickup_stays_same_day(self):
        # Normal "land just before pickup" case must not back-date.
        b = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 14, 0),
            flight_arrival_time=time(13, 59),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 13, 59)
        assert pickup[2] == datetime(2026, 6, 17, 14, 29)

    def test_edge_pickup_at_midnight_with_late_evening_flight(self):
        # Pickup exactly at 00:00 on day D, flight at 23:59 on D-1.
        b = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 0, 0),
            flight_arrival_time=time(23, 59),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 16, 23, 59)
        # end = start + 30 → crosses midnight onto pickup_date
        assert pickup[2] == datetime(2026, 6, 17, 0, 29)

    def test_pickup_end_anchor_is_arrival_plus_handoff_offset(self):
        """2026-05-20 amendment: the END anchor for a pickup is derived as
        `start_anchor + 30 min` (the canonical handoff offset), NOT read from
        `booking.pickup_time`. Goal: engine pivots on a single canonical event
        (the flight landing), so the car is at the airport as close to
        arrival time as possible. The 30-min offset plus the configured
        end_buffer give the jockey time for the actual handover."""
        # Arrival 15:40, stored pickup_time 16:10 (typical: arrival + 30).
        # End anchor = 15:40 + 30 = 16:10 — happens to match stored pickup_time
        # in the common case, but the derivation no longer depends on it.
        b = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 16, 10),
            flight_arrival_time=time(15, 40),
        )
        pickup = next(e for e in _events_for_booking(b) if e[0] == "pick_up")
        assert pickup[1] == datetime(2026, 6, 17, 15, 40)
        assert pickup[2] == datetime(2026, 6, 17, 16, 10)

        # Stored pickup_time mismatch (e.g. admin manually changed it) does NOT
        # influence end_anchor anymore — the engine ignores it. Regression
        # against the pre-2026-05-20 behaviour where pickup_time drove shift_end.
        b_mismatch = mk_booking(
            pickup_dt=datetime(2026, 6, 17, 17, 30),  # admin set this 80 min late
            flight_arrival_time=time(15, 40),
        )
        pickup_m = next(e for e in _events_for_booking(b_mismatch) if e[0] == "pick_up")
        assert pickup_m[2] == datetime(2026, 6, 17, 16, 10), (
            "end_anchor must derive from flight_arrival_time, not stored pickup_time"
        )

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

    def test_rebuild_respects_suppressed_auto_shift_window(self):
        """A soft-deleted auto shift is a durable admin suppression: even
        explicit regenerate should not recreate the same generated coverage."""
        b = mk_booking(
            booking_id=77,
            reference="TAG-SUPPRESS",
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        suppressed = SimpleNamespace(
            id=7700,
            created_source="auto",
            staff_id=None,
            status=ShiftStatus.CANCELLED,
            suppressed_at=datetime(2026, 6, 9, 12, 0),
            admin_shaped_at=None,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(8, 0),
            end_time=time(9, 30),
            booking_id=None,
            bookings=[b],
        )
        db = make_db(bookings=[b], suppressed_shifts=[suppressed])

        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == []
        assert result["created"] == 0
        assert result["skipped_suppressed"] == 1

    def test_boundary_rebuild_expands_to_existing_cross_midnight_shift(self):
        """Regression: a booking whose pickup lands D 02:00 (no rollover since
        arrival_time 01:30 < pickup_time 02:00) should join the existing
        cluster anchored on D-1 23:30 via the gap rule. Real failure
        observed on staging 2026-05-20: target_set was {drop_off_day, D}
        based on the new booking's own affected dates, but the existing
        cross-midnight shift sits on D-1 → not deleted → cluster never
        rebuilt → new booking has no pickup shift.

        Fix: target_set is expanded to include the date of any untouched
        auto-shift whose window touches a neighbour of target_set, so the
        delete + rebuild covers the existing cross-midnight cluster."""
        # Two earlier bookings already in the cluster (their pickup-event
        # back-dates to D-1 23:30 because flight_arrival_time > pickup_time).
        b1 = mk_booking(
            booking_id=1, reference="TAG-NIGHT001",
            dropoff_dt=datetime(2026, 7, 1, 11, 45),
            pickup_dt=datetime(2026, 7, 9, 0, 0),
            flight_arrival_time=time(23, 30),
        )
        b2 = mk_booking(
            booking_id=2, reference="TAG-NIGHT002",
            dropoff_dt=datetime(2026, 7, 1, 11, 45),
            pickup_dt=datetime(2026, 7, 9, 0, 29),
            flight_arrival_time=time(23, 59),
        )
        # New booking landing 01:30 on D with pickup 02:00 (no rollover).
        b_new = mk_booking(
            booking_id=3, reference="TAG-LATEAM01",
            dropoff_dt=datetime(2026, 7, 1, 11, 45),
            pickup_dt=datetime(2026, 7, 9, 2, 0),
            flight_arrival_time=time(1, 30),
        )
        # Existing untouched auto-shift from b1+b2's earlier rebuild: spans
        # 8 Jul 23:00 → 9 Jul 00:30. Its `date` is 8 Jul — NOT in target_set
        # for the new booking's rebuild ({1 Jul, 9 Jul}).
        existing = SimpleNamespace(
            id=999,
            created_source="auto",
            staff_id=None,
            status=ShiftStatus.SCHEDULED,
            date=date(2026, 7, 8),
            end_date=date(2026, 7, 9),
            start_time=time(23, 0),
            end_time=time(0, 30),
        )
        db = make_db(
            bookings=[b1, b2, b_new],
            untouched_auto_shifts=[existing],
        )
        # Trigger the rebuild for b_new's own affected dates only.
        rebuild_auto_for_dates(
            db,
            {date(2026, 7, 1), date(2026, 7, 9)},
            mk_settings(),
        )

        from db_models import RosterShift
        # `existing` is a SimpleNamespace, not a RosterShift instance — filter
        # by attribute presence rather than isinstance so it still matches.
        deleted = [d for d in db._deleted if hasattr(d, "date")]
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]

        # The cross-midnight shift (date=8 Jul) must have been picked up
        # by the expanded delete scope, NOT left intact.
        assert any(s.date == date(2026, 7, 8) for s in deleted), (
            "expanded target_set must catch the existing 8 Jul shift; "
            f"deleted dates: {[s.date for s in deleted]}"
        )
        # A replacement cross-midnight shift must have been created that
        # extends past 02:00 (so it covers b_new's pickup).
        cross = [s for s in new_shifts if s.date == date(2026, 7, 8) and s.end_date == date(2026, 7, 9)]
        assert len(cross) == 1, (
            f"exactly one cross-midnight shift expected, got {len(cross)}: "
            f"{[(s.date, s.end_date, s.start_time, s.end_time) for s in new_shifts]}"
        )
        assert cross[0].end_time >= time(2, 0), (
            f"rebuilt shift must extend to cover the 02:00 pickup; ends at {cross[0].end_time}"
        )

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

    # ----------------------------------------------------------------------
    # ARRIVAL_OVERNIGHT_CUTOFF (02:00 UK) re-bucket — auto-roster path
    # ----------------------------------------------------------------------
    # Mirrors the rule in roster_planner.propose_roster and the Admin
    # Calendar display. A pickup-led cluster whose earliest arrival sits
    # before 02:00 must materialise with date=D-1 and end_date=D, instead
    # of a standalone early-AM shift on D. Caught on TAG-GTW73712 (Ria
    # Dudding, Antalya → BOH 00:35 Sat 27 Jun 2026 — see [[project_ria_real_flight]]
    # equivalent project memory): the planner side was fixed first, but
    # auto_roster was creating the same standalone Sat shift via this
    # second code path.

    def test_arrival_before_0200_rebuckets_to_previous_day(self):
        """TAG-GTW73712 regression: pickup 01:05 Sat 6/27, arrival 00:35
        Sat 6/27 → shift covers Fri 6/26 → Sat 6/27 (not standalone Sat)."""
        b = mk_booking(
            booking_id=685, reference="TAG-GTW73712",
            dropoff_dt=datetime(2026, 6, 19, 12, 15),
            pickup_dt=datetime(2026, 6, 27, 1, 5),
            flight_arrival_time=time(0, 35),
        )
        # flight_arrival_date populated on every booking from 2026-05-20+
        b.flight_arrival_date = date(2026, 6, 27)
        db = make_db(bookings=[b])
        # 6/27 is in target_set — the rebuild on this day should produce
        # the re-bucketed shift on 6/26.
        rebuild_auto_for_dates(db, {date(2026, 6, 27)}, mk_settings())
        from db_models import RosterShift
        # Filter to the pickup-driven shift (drop-off on 6/19 is outside target).
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date == date(2026, 6, 26)
        ]
        assert len(pickup_shifts) == 1
        s = pickup_shifts[0]
        assert s.date == date(2026, 6, 26)
        assert s.end_date == date(2026, 6, 27)
        # Wall-clock start = 00:35 - 15m pickup-led buffer = 00:20.
        assert s.start_time == time(0, 20)

    def test_arrival_before_0200_recreates_when_previous_day_is_rebuilt(self):
        """Happy: if a later booking rebuilds Fri 6/26, TAG-GTW73712's Sat
        00:35 pickup is still owned by the Fri operational day and must be
        recreated. This is the live failure where an old booking lost its
        pickup shift after a different booking regenerated 6/26."""
        b = mk_booking(
            booking_id=685, reference="TAG-GTW73712",
            dropoff_dt=datetime(2026, 6, 19, 12, 15),
            pickup_dt=datetime(2026, 6, 27, 1, 5),
            flight_arrival_time=time(0, 35),
        )
        b.flight_arrival_date = date(2026, 6, 27)
        db = make_db(bookings=[b])
        rebuild_auto_for_dates(db, {date(2026, 6, 26)}, mk_settings())
        from db_models import RosterShift
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date == date(2026, 6, 26)
        ]
        assert len(pickup_shifts) == 1
        s = pickup_shifts[0]
        assert s.end_date == date(2026, 6, 27)
        assert s.start_time == time(0, 20)
        assert s.end_time == time(1, 35)

    def test_arrival_before_0200_buffer_crossing_midnight_is_not_two_days_back(self):
        """Boundary: a 00:10 arrival with the pickup-led 15m buffer starts
        at 23:55 the previous calendar day. The operational date is still
        D-1, not D-2."""
        b = mk_booking(
            booking_id=686, reference="TAG-EARLY001",
            dropoff_dt=datetime(2026, 6, 19, 12, 15),
            pickup_dt=datetime(2026, 6, 27, 0, 40),
            flight_arrival_time=time(0, 10),
        )
        b.flight_arrival_date = date(2026, 6, 27)
        db = make_db(bookings=[b])
        rebuild_auto_for_dates(db, {date(2026, 6, 26)}, mk_settings())
        from db_models import RosterShift
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date == date(2026, 6, 26)
        ]
        assert len(pickup_shifts) == 1
        s = pickup_shifts[0]
        assert s.end_date == date(2026, 6, 27)
        assert s.start_time == time(23, 55)
        assert s.end_time == time(1, 10)

    @pytest.mark.parametrize(
        "arrival_time, expected_shift_date",
        [
            (time(0, 0), date(2026, 6, 24)),
            (time(0, 1), date(2026, 6, 24)),
            (time(1, 59), date(2026, 6, 24)),
            (time(2, 0), date(2026, 6, 25)),
            (time(2, 1), date(2026, 6, 25)),
        ],
    )
    def test_arrival_0200_cutoff_boundaries_for_standalone_pickups(
        self, arrival_time, expected_shift_date
    ):
        """Standalone after-midnight arrivals before 02:00 belong to the
        previous operational day; 02:00 exactly and later belong to the
        arrival calendar day."""
        arrival_dt = datetime.combine(date(2026, 6, 25), arrival_time)
        b = mk_booking(
            booking_id=700 + arrival_time.hour * 60 + arrival_time.minute,
            reference=f"TAG-CUT{arrival_time.strftime('%H%M')}",
            dropoff_dt=datetime(2026, 6, 19, 12, 15),
            pickup_dt=arrival_dt + timedelta(minutes=30),
            flight_arrival_time=arrival_time,
        )
        b.flight_arrival_date = arrival_dt.date()

        db = make_db(bookings=[b])
        rebuild_auto_for_dates(db, {expected_shift_date}, mk_settings())

        from db_models import RosterShift
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date in {
                date(2026, 6, 24), date(2026, 6, 25)
            }
        ]
        assert len(pickup_shifts) == 1
        assert pickup_shifts[0].date == expected_shift_date

    def test_late_night_and_following_day_arrivals_stay_in_one_shift(self):
        """Boundary sweep: arrivals at 23:29, 23:30, 23:31, 23:59 and then
        00:00, 00:01, 01:59, 02:00, 02:01 are all within the live 190-minute
        pickup gap and should materialise as one cross-midnight shift."""
        arrival_dts = [
            datetime(2026, 6, 24, 23, 29),
            datetime(2026, 6, 24, 23, 30),
            datetime(2026, 6, 24, 23, 31),
            datetime(2026, 6, 24, 23, 59),
            datetime(2026, 6, 25, 0, 0),
            datetime(2026, 6, 25, 0, 1),
            datetime(2026, 6, 25, 1, 59),
            datetime(2026, 6, 25, 2, 0),
            datetime(2026, 6, 25, 2, 1),
        ]
        bookings = []
        for i, arrival_dt in enumerate(arrival_dts, start=1):
            b = mk_booking(
                booking_id=800 + i,
                reference=f"TAG-OVN{i:03d}",
                dropoff_dt=datetime(2026, 6, 19, 12, 15),
                pickup_dt=arrival_dt + timedelta(minutes=30),
                flight_arrival_time=arrival_dt.time(),
            )
            b.flight_arrival_date = arrival_dt.date()
            bookings.append(b)

        db = make_db(bookings=bookings)
        result = rebuild_auto_for_dates(
            db, {date(2026, 6, 24), date(2026, 6, 25)}, mk_settings()
        )

        from db_models import RosterShift, ShiftBookingLink
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date == date(2026, 6, 24)
        ]
        pickup_links = [
            a for a in db._added
            if isinstance(a, ShiftBookingLink)
            and a.booking_id in {b.id for b in bookings}
        ]

        assert result["created"] == 1
        assert len(pickup_shifts) == 1
        shift = pickup_shifts[0]
        assert shift.end_date == date(2026, 6, 25)
        # Seven tight pickup pairs (<30 min apart) add 7 * 30 minutes to
        # the pickup-led 15-minute start buffer: 23:29 - 225m = 19:44.
        assert shift.start_time == time(19, 44)
        assert shift.end_time == time(3, 1)
        assert {l.booking_id for l in pickup_links} == {b.id for b in bookings}

    @pytest.mark.parametrize(
        (
            "arrival_time",
            "target_date",
            "expected_date",
            "expected_end_date",
            "expected_start",
            "expected_end",
        ),
        [
            pytest.param(
                time(0, 14),
                date(2026, 6, 26),
                date(2026, 6, 26),
                date(2026, 6, 27),
                time(23, 59),
                time(1, 14),
                id="H-0014-buffer-crosses-midnight-but-owner-is-D-minus-1",
            ),
            pytest.param(
                time(0, 15),
                date(2026, 6, 26),
                date(2026, 6, 26),
                date(2026, 6, 27),
                time(0, 0),
                time(1, 15),
                id="U-0015-buffer-starts-at-midnight-and-still-owner-is-D-minus-1",
            ),
            pytest.param(
                time(0, 16),
                date(2026, 6, 26),
                date(2026, 6, 26),
                date(2026, 6, 27),
                time(0, 1),
                time(1, 16),
                id="E-0016-buffer-after-midnight-and-still-owner-is-D-minus-1",
            ),
            pytest.param(
                time(1, 59),
                date(2026, 6, 26),
                date(2026, 6, 26),
                date(2026, 6, 27),
                time(1, 44),
                time(2, 59),
                id="B-0159-last-minute-before-cutoff-rebuckets-to-D-minus-1",
            ),
            pytest.param(
                time(2, 0),
                date(2026, 6, 27),
                date(2026, 6, 27),
                None,
                time(1, 45),
                time(3, 0),
                id="B-0200-cutoff-is-exclusive-stays-on-D",
            ),
            pytest.param(
                time(2, 1),
                date(2026, 6, 27),
                date(2026, 6, 27),
                None,
                time(1, 46),
                time(3, 1),
                id="B-0201-after-cutoff-stays-on-D",
            ),
        ],
    )
    def test_HUEB_arrival_cutoff_and_pickup_buffer_boundaries(
        self,
        arrival_time,
        target_date,
        expected_date,
        expected_end_date,
        expected_start,
        expected_end,
    ):
        """HUEB: lock the pickup-led 15m buffer and 02:00 cutoff boundaries."""
        pickup_dt = datetime.combine(date(2026, 6, 27), arrival_time) + timedelta(minutes=30)
        b = mk_booking(
            booking_id=700 + arrival_time.hour * 60 + arrival_time.minute,
            reference=f"TAG-CUT{arrival_time.hour:02d}{arrival_time.minute:02d}",
            dropoff_dt=datetime(2026, 6, 19, 12, 15),
            pickup_dt=pickup_dt,
            flight_arrival_time=arrival_time,
        )
        b.flight_arrival_date = date(2026, 6, 27)
        db = make_db(bookings=[b])
        rebuild_auto_for_dates(db, {target_date}, mk_settings())

        from db_models import RosterShift
        pickup_shifts = [
            a for a in db._added
            if isinstance(a, RosterShift) and a.date == expected_date
        ]
        assert len(pickup_shifts) == 1
        s = pickup_shifts[0]
        assert s.end_date == expected_end_date
        assert s.start_time == expected_start
        assert s.end_time == expected_end

    def test_arrival_at_0200_stays_on_day(self):
        """Cutoff is exclusive — arrival 02:00 stays on its own calendar day."""
        b = mk_booking(
            booking_id=900, reference="TAG-CUT0200",
            dropoff_dt=datetime(2026, 4, 1, 9, 0),  # outside window
            pickup_dt=datetime(2026, 6, 27, 2, 30),
            flight_arrival_time=time(2, 0),
        )
        b.flight_arrival_date = date(2026, 6, 27)
        db = make_db(bookings=[b])
        rebuild_auto_for_dates(db, {date(2026, 6, 27)}, mk_settings())
        from db_models import RosterShift
        shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(shifts) == 1
        assert shifts[0].date == date(2026, 6, 27)
        assert shifts[0].end_date is None


# ===========================================================================
# Driver-trust contract (locked 2026-05-28, supersedes the 60-min extend
# rule from 2026-05-25). The auto-roster's only window-mutating action is
# wipe-and-recreate of UNOWNED auto shifts. The moment a shift becomes
# owned — assigned, claimed, split, merged, duplicated, or directly
# time-edited — its window is FROZEN. Auto-link still writes booking
# links to such shifts when the booking's event falls inside the existing
# window (separate background task), but the auto-roster itself never
# stretches or shrinks them.
#
# The rebuild's per-cluster guard (`_cluster_fully_covered`): when EVERY
# event in a cluster sits inside the wall-clock window of some existing
# frozen shift, skip materialising a new auto-shift. That's what stops
# Kris's "duplicate ghost shift" loop without the auto-side ever mutating
# an owned row. Partial overlap (some events in-window, some not) still
# materialises the whole cluster — accepted as the simpler tradeoff vs
# splitting clusters.
#
# An auto shift is "frozen" iff ANY of:
#   - created_source != 'auto'           (manual, planner)
#   - staff_id IS NOT NULL                (assigned / claimed)
#   - admin_shaped_at IS NOT NULL         (split / merged / duplicated /
#                                          PATCH'd window field)
# ===========================================================================


def mk_assigned_shift(
    *,
    id=99,
    shift_date=None,
    end_date=None,
    start_time=time(12, 0),
    end_time=time(15, 0),
    staff_id=10,
    created_source="auto",
    admin_shaped_at=None,
):
    """A frozen shift fixture. Defaults to assigned auto (`staff_id` set,
    `created_source='auto'`, `admin_shaped_at=None`) — the most common
    shape Kris hits. Override `created_source='manual'` for manual shifts,
    or pass `admin_shaped_at=datetime.now()` for admin-shaped auto rows."""
    return SimpleNamespace(
        id=id,
        staff_id=staff_id,
        date=shift_date or date(2026, 6, 10),
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        shift_type=ShiftType.MORNING,
        status=ShiftStatus.SCHEDULED,
        created_source=created_source,
        admin_shaped_at=admin_shaped_at,
    )


def mk_existing_link(shift_id, booking_id):
    return SimpleNamespace(shift_id=shift_id, booking_id=booking_id)


class TestRebuildSkipsCoveredClusters:
    """Driver-trust contract (2026-05-28). The rebuild MUST NOT spawn a
    duplicate auto-shift over hours that an existing frozen shift already
    covers — that loop is what Kris was hitting before the contract
    pivot. Equally important, the rebuild MUST still spawn a fresh
    auto-shift for genuinely uncovered hours, and for partial-overlap
    clusters it materialises the WHOLE cluster (per the all-or-nothing
    rule) — auto-link will sort the inside-events out via its in-window
    coverage check.

    These tests sit on top of the rule, not the implementation: they
    don't probe whether the manual shift was "skipped" or "ignored" or
    "passed through" — they verify that the manual / assigned / admin-
    shaped row's *window stays as the admin left it*, AND no duplicate
    auto-shift is materialised over its hours. That keeps a future
    reader from "simplifying" the predicate into something narrower than
    the contract."""

    def test_H_cluster_fully_inside_frozen_window_skips_materialise(self):
        """Happy: cluster of 3 events at 13:00/13:30/14:00 on 6/10
        sits entirely inside Kristian's frozen 12:00-15:00 shift.
        Rebuild must skip — no new RosterShift, no window mutation on
        the frozen row, summary['skipped_covered']=1, ['created']=0."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,  # assigned auto = frozen
        )
        original = (frozen.date, frozen.end_date, frozen.start_time, frozen.end_time)
        b1 = mk_booking(
            booking_id=500, reference="TAG-SKIP00001",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        b2 = mk_booking(
            booking_id=501, reference="TAG-SKIP00002",
            dropoff_dt=datetime(2026, 6, 10, 13, 30),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        b3 = mk_booking(
            booking_id=502, reference="TAG-SKIP00003",
            dropoff_dt=datetime(2026, 6, 10, 14, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b1, b2, b3], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift, ShiftBookingLink
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == [], (
            f"no new auto-shift expected — cluster covered by frozen 12-15:00; "
            f"got {len(new_shifts)}"
        )
        # Frozen row's window untouched.
        assert (frozen.date, frozen.end_date, frozen.start_time, frozen.end_time) == original
        # Rebuild does NOT write link rows itself in this branch — that's
        # auto_link_booking_to_shifts' job (separate background task).
        new_links = [a for a in db._added if isinstance(a, ShiftBookingLink)]
        assert new_links == [], (
            "rebuild must not double-write links — auto_link owns that"
        )
        assert result["skipped_covered"] == 1
        assert result["created"] == 0

    def test_U_no_frozen_shift_still_materialises_normally(self):
        """Unhappy (for the contract): no frozen shift on the date at
        all. Rebuild creates a fresh unassigned auto-shift for the
        cluster, summary['created']=1, ['skipped_covered']=0. Regression
        guard — confirms the new guard isn't accidentally suppressing
        all materialisation."""
        b = mk_booking(
            booking_id=510, reference="TAG-SKIP00010",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        # No assigned_shifts → no frozen rows → skip can't fire.
        db = make_db(bookings=[b])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert new_shifts[0].staff_id is None
        assert result["created"] == 1
        assert result["skipped_covered"] == 0

    def test_E_partial_overlap_materialises_whole_cluster(self):
        """Edge: cluster of 3 events at 13:00/14:00/16:30 on 6/10 with
        Kristian's frozen 12:00-15:00. Two events inside (13:00, 14:00),
        one outside (16:30). Per the all-or-nothing rule, rebuild must
        materialise the WHOLE cluster as a new auto-shift — accepts
        some duplicate linking for the inside events in exchange for
        coverage of the outside one. (Splitting the cluster would be
        cleaner, but not yet implemented.)"""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        original_end = frozen.end_time
        b1 = mk_booking(
            booking_id=520, reference="TAG-PARTIAL01",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        b2 = mk_booking(
            booking_id=521, reference="TAG-PARTIAL02",
            dropoff_dt=datetime(2026, 6, 10, 14, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        b3 = mk_booking(
            booking_id=522, reference="TAG-PARTIAL03",
            dropoff_dt=datetime(2026, 6, 10, 16, 30),  # outside frozen window
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b1, b2, b3], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        # At least one new shift to cover the 16:30 event.
        assert len(new_shifts) >= 1
        # Frozen window NEVER changes regardless of cluster overlap.
        assert frozen.end_time == original_end
        assert result["created"] >= 1
        assert result["skipped_covered"] == 0

    def test_B_event_at_window_boundary_needs_end_buffer(self):
        """Boundary: a 15:00 drop-off in a frozen 12:00-15:00 shift leaves
        no 30m end buffer, so the cluster is NOT covered and rebuild must
        materialise a new unassigned shift."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        original_end = frozen.end_time
        b = mk_booking(
            booking_id=530, reference="TAG-BOUNDARY1",
            dropoff_dt=datetime(2026, 6, 10, 15, 0),  # event AT boundary
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert frozen.end_time == original_end
        assert result["skipped_covered"] == 0
        assert result["created"] == 1

    def test_B_event_at_generated_window_boundary_counts_as_covered(self):
        """Boundary: a 14:20 drop-off in a frozen 12:00-15:00 shift generates
        a 14:00-15:00 required window, so it is covered inclusively."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        b = mk_booking(
            booking_id=531, reference="TAG-BOUNDARY2",
            dropoff_dt=datetime(2026, 6, 10, 14, 20),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == []
        assert result["skipped_covered"] == 1
        assert result["created"] == 0

    def test_HUEB_dropoff_0645_not_covered_by_fixed_shift_ending_0700(self):
        """HUEB regression: TAG-SHS00925-style 06:45 drop-off needs coverage
        through 07:15. A fixed 03:50-07:00 assigned shift must not cause
        rebuild to skip materialising fresh coverage."""
        frozen = mk_assigned_shift(
            id=3663,
            shift_date=date(2026, 6, 8),
            start_time=time(3, 50),
            end_time=time(7, 0),
            staff_id=15,
        )
        b = mk_booking(
            booking_id=807,
            reference="TAG-SHS00925",
            dropoff_dt=datetime(2026, 6, 8, 6, 45),
            pickup_dt=datetime(2026, 6, 11, 23, 25),
            flight_arrival_time=time(22, 55),
        )
        b.flight_arrival_date = date(2026, 6, 11)
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 8)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert new_shifts[0].date == date(2026, 6, 8)
        # Start buffer makes this 06:25; min_shift_minutes=60 extends it
        # beyond the bare 07:15 buffered requirement to 07:25.
        assert new_shifts[0].end_time == time(7, 25)
        assert result["skipped_covered"] == 0
        assert result["created"] == 1

    def test_E_mixed_partial_frozen_coverage_materialises_cluster(self):
        """Edge: two events in the same generated cluster sit in different
        fixed shifts, but neither fixed shift covers the generated cluster
        window. Rebuild must materialise fresh coverage rather than treating
        partial coverage as enough."""
        frozen1 = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(9, 0), end_time=time(12, 0),  # covers 10:00 dropoff
            staff_id=10,
        )
        frozen2 = mk_assigned_shift(
            id=100, shift_date=date(2026, 6, 10),
            start_time=time(11, 0), end_time=time(14, 0),  # covers 13:00 dropoff
            staff_id=11,  # different staff
        )
        b1 = mk_booking(
            booking_id=600, reference="TAG-MIXED0001",
            dropoff_dt=datetime(2026, 6, 10, 10, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        b2 = mk_booking(
            booking_id=601, reference="TAG-MIXED0002",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b1, b2], assigned_shifts=[frozen1, frozen2])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        assert result["skipped_covered"] == 0
        assert result["created"] == 1

    def test_HUEB_pickup_cluster_requires_tight_pair_start_extension(self):
        """HUEB regression: SHS 22:55 + LDH 23:00 are a tight pickup pair,
        so the generated cluster starts 45m before 22:55 at 22:10. A fixed
        22:45-00:00 shift must not suppress new coverage."""
        frozen = mk_assigned_shift(
            id=4527,
            shift_date=date(2026, 6, 11),
            end_date=date(2026, 6, 12),
            start_time=time(22, 45),
            end_time=time(0, 0),
            staff_id=15,
        )
        shs = mk_booking(
            booking_id=807,
            reference="TAG-SHS00925",
            dropoff_dt=datetime(2026, 6, 8, 6, 45),
            pickup_dt=datetime(2026, 6, 11, 23, 25),
            flight_arrival_time=time(22, 55),
        )
        shs.flight_arrival_date = date(2026, 6, 11)
        ldh = mk_booking(
            booking_id=755,
            reference="TAG-LDH79714",
            dropoff_dt=datetime(2026, 6, 6, 6, 5),
            pickup_dt=datetime(2026, 6, 11, 23, 30),
            flight_arrival_time=time(23, 0),
        )
        ldh.flight_arrival_date = date(2026, 6, 11)
        db = make_db(bookings=[shs, ldh], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 11)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        pickup_shifts = [s for s in new_shifts if s.date == date(2026, 6, 11)]
        assert len(pickup_shifts) == 1
        s = pickup_shifts[0]
        assert s.start_time == time(22, 10)
        assert s.end_date == date(2026, 6, 12)
        assert s.end_time == time(0, 0)
        assert result["skipped_covered"] == 0
        assert result["created"] == 1

    def test_B_overnight_frozen_shift_covers_event_across_midnight(self):
        """Boundary: a frozen overnight shift (22:00 6/10 → 02:00 6/11)
        covers a pickup whose canonical event span straddles midnight.
        Flight lands 23:30 6/10 (start anchor), handoff 00:00 6/11 (end
        anchor). BOTH endpoints sit inside the overnight window —
        skip-if-covered must fire. Equally important — neither endpoint
        falling on the wrong side of midnight should confuse the check."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            end_date=date(2026, 6, 11),
            start_time=time(22, 0), end_time=time(2, 0),
            staff_id=10,
        )
        # Flight arrival 23:30 6/10 → derived handoff 00:00 6/11
        b = mk_booking(
            booking_id=610, reference="TAG-OVERNIGHT1",
            dropoff_dt=datetime(2026, 5, 1, 9, 0),  # outside target
            pickup_dt=datetime(2026, 6, 11, 0, 0),
            flight_arrival_time=time(23, 30),
        )
        b.flight_arrival_date = date(2026, 6, 10)
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(
            db, {date(2026, 6, 10), date(2026, 6, 11)}, mk_settings(),
        )

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == [], (
            "overnight frozen shift covers the cross-midnight pickup event "
            "→ no new auto-shift"
        )
        assert result["skipped_covered"] == 1
        # Window untouched.
        assert frozen.start_time == time(22, 0)
        assert frozen.end_time == time(2, 0)


class TestRebuildIgnoresAdminShapedAutoShifts:
    """Companion to the wipe filter — confirms that an auto shift with
    admin_shaped_at set is treated identically to an assigned auto shift
    (no window mutation; covers cluster events the same way for the skip
    rule). Tests the contract that "admin-shaped means no window
    mutation," NOT "admin-shaped means invisible to automation." If a
    future refactor narrows the predicate it should fail here."""

    def test_H_admin_shaped_unassigned_still_blocks_duplicate(self):
        """Admin split an empty auto shift earlier; both halves have
        admin_shaped_at != None and staff_id = None. A new booking
        whose pickup lands inside one half must NOT cause a duplicate
        auto-shift over the same hours."""
        shaped = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=None,  # unassigned
            admin_shaped_at=datetime(2026, 5, 28, 10, 0),  # but admin-shaped
        )
        original = (shaped.start_time, shaped.end_time)
        b = mk_booking(
            booking_id=600, reference="TAG-SHAPED001",
            dropoff_dt=datetime(2026, 6, 10, 13, 30),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b], assigned_shifts=[shaped])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == [], (
            "admin-shaped unassigned auto shift must still block "
            "duplicate materialisation"
        )
        assert (shaped.start_time, shaped.end_time) == original
        assert result["skipped_covered"] == 1


class TestSkipIfCoveredUsesBothEventAnchors:
    """Code-review regression 2026-05-28: skip-if-covered must use BOTH
    the start anchor (flight_arrival_time for pickups) AND the end
    anchor (pickup-handoff time = arrival + 30 min for pickups) when
    deciding whether a cluster fits inside a frozen shift. Otherwise the
    rebuild and auto_link can disagree on coverage and leave a booking
    with no shift at all."""

    def test_E_pickup_handoff_outside_frozen_window_does_NOT_skip(self):
        """Edge: frozen 12:00-15:00 shift. Flight arrival 14:45 IS inside,
        but pickup handoff 15:15 (arrival + 30 min) is OUTSIDE. Skip-if-
        covered must return False — auto_link would otherwise refuse to
        link (handoff at 15:15 > end_time 15:00). Forcing both endpoints
        to fit means rebuild creates a new auto-shift spanning ~14:30 to
        ~15:45 so the booking has somewhere to land."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        # Pickup booking: arrival 14:45, handoff 15:15. Per
        # _events_for_booking, start_anchor = flight_arrival 14:45,
        # end_anchor = start + 30 min = 15:15.
        b = mk_booking(
            booking_id=800, reference="TAG-HANDOFF01",
            dropoff_dt=datetime(2026, 5, 1, 9, 0),  # outside target
            pickup_dt=datetime(2026, 6, 10, 15, 15),  # handoff time
            flight_arrival_time=time(14, 45),
        )
        b.flight_arrival_date = date(2026, 6, 10)
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1, (
            "must materialise a new shift — handoff 15:15 is outside the "
            "frozen 12:00-15:00 window, even though arrival 14:45 sits inside"
        )
        # Original frozen window unchanged.
        assert frozen.end_time == time(15, 0)
        assert result["created"] == 1
        assert result["skipped_covered"] == 0

    def test_H_handoff_inside_window_skips(self):
        """Mirror: same flight arrival 14:00 / handoff 14:30, but frozen
        shift now 12:00-15:00 — BOTH endpoints fit, skip fires."""
        frozen = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        b = mk_booking(
            booking_id=801, reference="TAG-HANDOFF02",
            dropoff_dt=datetime(2026, 5, 1, 9, 0),
            pickup_dt=datetime(2026, 6, 10, 14, 30),
            flight_arrival_time=time(14, 0),
        )
        b.flight_arrival_date = date(2026, 6, 10)
        db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == []
        assert result["skipped_covered"] == 1


class TestFrozenPoolMatchesAutoLinkStatus:
    """Code-review regression 2026-05-28: the frozen-shift query must
    only include statuses that auto_link will also link to (SCHEDULED +
    CONFIRMED). Otherwise an IN_PROGRESS shift inside the frozen pool
    can cause skip-if-covered to fire when auto_link won't compensate."""

    def test_U_in_progress_shift_is_NOT_in_the_frozen_pool(self):
        """Unhappy: an IN_PROGRESS frozen shift exists on the date. A
        cluster's events fall inside its window. The rebuild must STILL
        materialise a new auto-shift (because auto_link can't reach the
        in-progress one). Result: created=1, skipped_covered=0."""
        in_progress = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
        )
        in_progress.status = ShiftStatus.IN_PROGRESS
        b = mk_booking(
            booking_id=810, reference="TAG-INPROG001",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b], assigned_shifts=[in_progress])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1, (
            "IN_PROGRESS shift must not block materialisation — auto_link "
            "only links to SCHEDULED/CONFIRMED, so blocking here would "
            "orphan the booking"
        )
        assert result["skipped_covered"] == 0
        assert result["created"] == 1


class TestRebuildSkipsManualShifts:
    """Manual shifts (created_source='manual') are the original frozen
    case — the auto-roster has always preserved them. With the driver-
    trust pivot they participate in the skip-if-covered guard too: a
    cluster fully inside a manual shift's window doesn't spawn a
    duplicate."""

    def test_H_cluster_inside_manual_window_skips(self):
        manual = mk_assigned_shift(
            id=99, shift_date=date(2026, 6, 10),
            start_time=time(12, 0), end_time=time(15, 0),
            staff_id=10,
            created_source="manual",  # manually created
        )
        original = (manual.start_time, manual.end_time)
        b = mk_booking(
            booking_id=700, reference="TAG-MANUAL001",
            dropoff_dt=datetime(2026, 6, 10, 13, 0),
            pickup_dt=datetime(2026, 7, 10, 14, 0),
        )
        db = make_db(bookings=[b], assigned_shifts=[manual])
        result = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert new_shifts == []
        assert (manual.start_time, manual.end_time) == original
        assert result["skipped_covered"] == 1


class TestSkipAndLinkAgreeForFlightArrivalBooking:
    """Cross-path contract: for the SAME flight-arrival booking against
    the SAME frozen shift, auto_link_booking_to_shifts must create a
    link AND rebuild_auto_for_dates must skip the materialise. Proves
    both paths use the same canonical event semantics
    (`_events_for_booking` + window coverage). If a future change drifts
    one path's anchor back to literal pickup_time, or shrinks the
    coverage definition, this test catches the disagreement immediately.

    The two passes use different mock shapes (auto_link queries don't
    have IS NOT NULL / staff_id filters; rebuild does), so the test
    constructs each mock inline. The point isn't shared in-memory state
    — it's identical *inputs* + identical *contract conclusions*."""

    def test_H_link_writes_and_rebuild_skips_for_same_inputs(self):
        # Reviewer's mismatch example, shaped for both paths:
        #   shift           15:25 – 16:40 on 6/14, assigned, staff_id=10
        #   flight_arrival  15:40 on 6/14
        #   derived handoff 16:10 on 6/14
        #   buffered end    16:40 on 6/14
        #   stored pickup   17:30 on 6/14
        # Full buffered event window (15:25, 16:40) sits inside the shift;
        # literal pickup (17:30) outside — must be irrelevant to both paths.
        frozen = mk_assigned_shift(
            id=999, shift_date=date(2026, 6, 14),
            start_time=time(15, 25), end_time=time(16, 40),
            staff_id=10,
        )
        original_window = (
            frozen.date, frozen.end_date, frozen.start_time, frozen.end_time,
        )
        b = mk_booking(
            booking_id=1000, reference="TAG-CROSS001",
            dropoff_dt=datetime(2026, 6, 1, 9, 0),  # outside target_set
            pickup_dt=datetime(2026, 6, 14, 17, 30),
            flight_arrival_time=time(15, 40),
        )
        b.flight_arrival_date = date(2026, 6, 14)

        # ----- Pass 1: auto_link must write a link to the frozen shift.
        # Minimal mock: just enough to satisfy the candidate query, the
        # idempotency lookup, and the db.add/commit hooks.
        from unittest.mock import MagicMock as _MM
        link_added: list = []
        link_db = _MM()
        link_db._committed = False

        def _link_query(model):
            from db_models import RosterShift as _RS, ShiftBookingLink as _SBL
            chain = _MM()
            chain.filter.return_value = chain
            if model is _RS:
                chain.all.return_value = [frozen]
            elif model is _SBL:
                chain.first.return_value = None  # no existing link
            return chain
        link_db.query.side_effect = _link_query
        link_db.add.side_effect = lambda obj: link_added.append(obj)

        def _link_commit():
            link_db._committed = True
        link_db.commit.side_effect = _link_commit
        link_db.rollback = _MM()

        from roster_planner_runner import auto_link_booking_to_shifts
        from db_models import ShiftBookingLink
        linked_ids = auto_link_booking_to_shifts(link_db, b)
        assert linked_ids == [999], (
            "auto_link must attach the booking to the frozen 15:25-16:40 "
            "shift — the buffered event fits; literal pickup at 17:30 must NOT "
            "block the link"
        )
        link_rows = [a for a in link_added if isinstance(a, ShiftBookingLink)]
        assert len(link_rows) == 1
        assert link_rows[0].shift_id == 999 and link_rows[0].booking_id == 1000

        # ----- Pass 2: rebuild must skip materialising for same inputs.
        rebuild_db = make_db(bookings=[b], assigned_shifts=[frozen])
        result = rebuild_auto_for_dates(
            rebuild_db, {date(2026, 6, 14)}, mk_settings(),
        )
        from db_models import RosterShift
        new_shifts = [a for a in rebuild_db._added if isinstance(a, RosterShift)]
        assert new_shifts == [], (
            "rebuild must skip — cluster fully covered by the frozen shift"
        )
        assert result["skipped_covered"] == 1
        assert result["created"] == 0

        # ----- Final assertion: frozen window is byte-identical to the start.
        # No path should ever mutate a frozen shift.
        assert (
            frozen.date, frozen.end_date, frozen.start_time, frozen.end_time,
        ) == original_window


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

    def test_late_booking_does_not_recreate_unrelated_deleted_auto_cluster(self):
        """Booking-triggered auto-roster is focused on the new booking's
        clusters. If an unrelated auto shift on the same date was manually
        deleted earlier, a late booking must not recreate that old cluster."""
        old = mk_booking(
            booking_id=20, reference="TAG-OLD0800",
            dropoff_dt=datetime(2026, 6, 15, 8, 0),
            pickup_dt=datetime(2026, 6, 25, 8, 0),
        )
        late = mk_booking(
            booking_id=21, reference="TAG-LATE1600",
            dropoff_dt=datetime(2026, 6, 15, 16, 0),
            pickup_dt=datetime(2026, 6, 25, 17, 30),
            flight_arrival_time=time(17, 0),
        )
        db = make_db(bookings=[old, late])

        result = auto_create_or_extend_for_booking(db, late, mk_settings())

        from db_models import RosterShift, ShiftBookingLink
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        new_links = [a for a in db._added if isinstance(a, ShiftBookingLink)]

        assert result["created"] == 2
        assert len(new_shifts) == 2
        assert {(s.date, s.start_time) for s in new_shifts} == {
            (date(2026, 6, 15), time(15, 40)),
            (date(2026, 6, 25), time(16, 45)),
        }
        assert {l.booking_id for l in new_links} == {late.id}


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

    def test_happy_no_range_passes_no_extra_filters(self):
        """Boundary: omitting both date_from and date_to should not narrow
        the candidate query — legacy behaviour preserved (locked 2026-05-05)."""
        s1 = SimpleNamespace(id=1, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        db = make_db(untouched_auto_shifts=[s1])
        assert delete_all_auto_shifts(db, date_from=None, date_to=None) == 1

    def test_edge_only_date_from_filters_lower_bound(self):
        """Edge: passing only date_from leaves the upper edge open."""
        s1 = SimpleNamespace(id=1, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        db = make_db(untouched_auto_shifts=[s1])
        # Mock returns the same list regardless of filters — what we're
        # asserting is that the function accepts the kwarg and doesn't
        # crash. The SQL filter is exercised live by integration tests.
        assert delete_all_auto_shifts(db, date_from=date(2026, 6, 1)) == 1

    def test_edge_only_date_to_filters_upper_bound(self):
        s1 = SimpleNamespace(id=1, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        db = make_db(untouched_auto_shifts=[s1])
        assert delete_all_auto_shifts(db, date_to=date(2026, 6, 30)) == 1

    def test_boundary_both_dates_set_filters_inclusive_range(self):
        s1 = SimpleNamespace(id=1, created_source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        db = make_db(untouched_auto_shifts=[s1])
        assert delete_all_auto_shifts(
            db, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
        ) == 1

    def test_edge_admin_shaped_unassigned_auto_is_preserved(self):
        """Driver-trust pivot 2026-05-28: an unassigned auto-shift that
        an admin has shaped (split/merge/duplicate/PATCH stamped
        `admin_shaped_at`) is OFF-LIMITS to the bulk delete, same as it
        is to the rebuild wipe. The contract is consistent across both
        wipe paths. Without the filter, a single misclick on the admin
        "Clear all auto-shifts" button would wipe deliberate split halves.

        Sets two rows: one untouched (deleted), one admin-shaped
        (preserved). Asserts only the untouched one moves."""
        untouched = SimpleNamespace(
            id=1, created_source="auto", staff_id=None,
            admin_shaped_at=None,
            status=ShiftStatus.SCHEDULED,
        )
        shaped = SimpleNamespace(
            id=2, created_source="auto", staff_id=None,
            admin_shaped_at=datetime(2026, 5, 28, 10, 0),
            status=ShiftStatus.SCHEDULED,
        )
        db = make_db(untouched_auto_shifts=[untouched, shaped])
        n = delete_all_auto_shifts(db)
        assert n == 1, (
            "only the untouched row should be deleted; admin-shaped row "
            "is off-limits"
        )
        assert untouched in db._deleted
        assert shaped not in db._deleted


# ===========================================================================
# focused coverage helpers / isolation paths
# ===========================================================================

class TestAutoRosterCoverageEdges:
    def test_helper_collects_shift_booking_ids_from_legacy_and_relationships(self):
        shift = SimpleNamespace(
            booking_id=10,
            bookings=[
                SimpleNamespace(id=20),
                SimpleNamespace(id=None),
                SimpleNamespace(id=30),
            ],
        )

        assert _shift_linked_booking_ids(shift) == {10, 20, 30}
        assert _shift_linked_booking_ids(SimpleNamespace(booking_id=None, bookings=None)) == set()

    def test_helper_windows_overlap_false_for_disjoint_windows(self):
        morning = (datetime(2026, 6, 10, 8, 0), datetime(2026, 6, 10, 9, 0))
        afternoon = (datetime(2026, 6, 10, 13, 0), datetime(2026, 6, 10, 14, 0))

        assert _windows_overlap(morning, afternoon) is False

    def test_helper_auto_shift_eligibility_rejects_admin_owned_rows(self):
        eligible = SimpleNamespace(
            created_source="auto",
            staff_id=None,
            admin_shaped_at=None,
            status=ShiftStatus.SCHEDULED,
        )
        assigned = SimpleNamespace(
            created_source="auto",
            staff_id=12,
            admin_shaped_at=None,
            status=ShiftStatus.SCHEDULED,
        )
        shaped = SimpleNamespace(
            created_source="auto",
            staff_id=None,
            admin_shaped_at=datetime(2026, 6, 10, 9, 0),
            status=ShiftStatus.SCHEDULED,
        )
        manual = SimpleNamespace(
            created_source="manual",
            staff_id=None,
            admin_shaped_at=None,
            status=ShiftStatus.SCHEDULED,
        )

        assert _is_auto_shift_eligible_for_rebuild(eligible) is True
        assert _is_auto_shift_eligible_for_rebuild(assigned) is False
        assert _is_auto_shift_eligible_for_rebuild(shaped) is False
        assert _is_auto_shift_eligible_for_rebuild(manual) is False

    def test_rebuild_with_empty_target_dates_returns_zero_summary(self):
        db = make_db()

        assert rebuild_auto_for_dates(db, set(), mk_settings()) == {
            "deleted": 0,
            "created": 0,
            "skipped_covered": 0,
            "skipped_suppressed": 0,
            "bookings_in_scope": 0,
            "events": 0,
        }
        db.query.assert_not_called()

    def test_rebuild_skips_adjacent_day_cluster_owned_elsewhere(self):
        booking = SimpleNamespace(
            id=91,
            reference="TAG-ADJ0001",
            status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=date(2026, 6, 10),
            dropoff_time=time(8, 0),
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )
        db = make_db(bookings=[booking])

        summary = rebuild_auto_for_dates(db, {date(2026, 6, 11)}, mk_settings())

        assert summary["created"] == 0
        assert not db._added

    def test_rebuild_suppresses_cluster_when_cancelled_shift_kept_booking_link(self):
        booking = SimpleNamespace(
            id=92,
            reference="TAG-SUPP001",
            status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=date(2026, 6, 10),
            dropoff_time=time(8, 0),
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )
        suppressed = SimpleNamespace(
            id=50,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(1, 0),
            end_time=time(2, 0),
            booking_id=booking.id,
            bookings=[],
            created_source="auto",
            status=ShiftStatus.CANCELLED,
            suppressed_at=datetime(2026, 6, 9, 18, 0),
        )
        db = make_db(bookings=[booking], suppressed_shifts=[suppressed])

        summary = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        assert summary["skipped_suppressed"] == 1
        assert summary["created"] == 0

    def test_rebuild_does_not_suppress_when_cancelled_shift_is_unrelated(self):
        booking = SimpleNamespace(
            id=93,
            reference="TAG-SUPP002",
            status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=date(2026, 6, 10),
            dropoff_time=time(8, 0),
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )
        suppressed = SimpleNamespace(
            id=51,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(1, 0),
            end_time=time(2, 0),
            booking_id=999,
            bookings=[],
            created_source="auto",
            status=ShiftStatus.CANCELLED,
            suppressed_at=datetime(2026, 6, 9, 18, 0),
        )
        db = make_db(bookings=[booking], suppressed_shifts=[suppressed])

        summary = rebuild_auto_for_dates(db, {date(2026, 6, 10)}, mk_settings())

        assert summary["skipped_suppressed"] == 0
        assert summary["created"] == 1

    def test_focused_rebuild_deletes_overlapping_untouched_auto_shift_once(self):
        booking = SimpleNamespace(
            id=94,
            reference="TAG-FOCUS01",
            status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=date(2026, 6, 10),
            dropoff_time=time(8, 0),
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )
        existing = SimpleNamespace(
            id=60,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(7, 30),
            end_time=time(8, 45),
            booking_id=None,
            bookings=[],
            created_source="auto",
            staff_id=None,
            admin_shaped_at=None,
            status=ShiftStatus.SCHEDULED,
        )
        db = make_db(untouched_auto_shifts=[existing], bookings=[booking])

        summary = rebuild_auto_for_dates(
            db,
            {date(2026, 6, 10)},
            mk_settings(),
            focus_booking_id=booking.id,
        )

        assert summary["deleted"] == 1
        assert existing in db._deleted
        assert summary["created"] == 1

    def test_auto_create_or_extend_skips_when_booking_has_no_events(self):
        booking = SimpleNamespace(
            id=95,
            reference="TAG-EMPTY01",
            status=BookingStatus.CONFIRMED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=None,
            dropoff_time=None,
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )

        assert auto_create_or_extend_for_booking(make_db(), booking, mk_settings()) == {
            "created": 0,
            "deleted": 0,
            "bookings_in_scope": 0,
            "skipped": 1,
        }

    def test_handle_booking_cancelled_skips_rebuild_when_booking_has_no_events(self):
        booking = SimpleNamespace(
            id=96,
            reference="TAG-EMPTY02",
            status=BookingStatus.CANCELLED,
            service_type=ServiceType.MEET_GREET,
            dropoff_date=None,
            dropoff_time=None,
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
        )

        assert handle_booking_cancelled(make_db(), booking) == {
            "created": 0,
            "deleted": 0,
            "bookings_in_scope": 0,
            "skipped": 0,
        }

    def test_auto_create_async_logs_start_loaded_and_success(self, monkeypatch, caplog):
        booking = mk_booking(
            booking_id=123,
            reference="TAG-LOG0123",
            dropoff_dt=datetime(2026, 7, 5, 10, 40),
            pickup_dt=datetime(2026, 7, 12, 14, 15),
        )
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        monkeypatch.setattr("database.SessionLocal", lambda: db)
        monkeypatch.setattr("routers.roster._load_planner_settings_rows", lambda db: {})
        monkeypatch.setattr(
            "auto_roster.auto_create_or_extend_for_booking",
            lambda db, booking, settings: {"created": 2, "deleted": 1, "skipped": 0},
        )
        caplog.set_level(logging.INFO, logger="auto_roster")

        auto_create_or_extend_async(123)

        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "auto_create_or_extend_async outcome=start booking_id=123" in messages
        assert "outcome=loaded booking_id=123 ref=TAG-LOG0123" in messages
        assert "affected_dates=['2026-07-05', '2026-07-12']" in messages
        assert "outcome=success booking_id=123 ref=TAG-LOG0123" in messages
        assert "'created': 2" in messages
        db.close.assert_called_once()

    def test_auto_create_async_logs_not_found(self, monkeypatch, caplog):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        monkeypatch.setattr("database.SessionLocal", lambda: db)
        caplog.set_level(logging.INFO, logger="auto_roster")

        auto_create_or_extend_async(404)

        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "auto_create_or_extend_async outcome=start booking_id=404" in messages
        assert "auto_create_or_extend_async outcome=not_found booking_id=404" in messages
        db.rollback.assert_not_called()
        db.close.assert_called_once()

    def test_auto_create_async_logs_session_creation_failure(self, monkeypatch, caplog):
        def fail_session():
            raise RuntimeError("session unavailable")

        monkeypatch.setattr("database.SessionLocal", fail_session)
        caplog.set_level(logging.INFO, logger="auto_roster")

        auto_create_or_extend_async(123)

        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "auto_create_or_extend_async outcome=start booking_id=123" in messages
        assert "auto_create_or_extend_async outcome=failure booking_id=123" in messages
        assert "session unavailable" in messages

    def test_auto_create_async_swallows_query_and_rollback_failures(self, monkeypatch, caplog):
        db = MagicMock()
        db.query.side_effect = RuntimeError("query exploded")
        db.rollback.side_effect = RuntimeError("rollback exploded")
        monkeypatch.setattr("database.SessionLocal", lambda: db)
        caplog.set_level(logging.INFO, logger="auto_roster")

        auto_create_or_extend_async(123)

        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert "auto_create_or_extend_async outcome=start booking_id=123" in messages
        assert "auto_create_or_extend_async outcome=failure booking_id=123" in messages
        assert "query exploded" in messages
        db.rollback.assert_called_once()
        db.close.assert_called_once()

    def test_handle_cancelled_async_swallows_query_and_rollback_failures(self, monkeypatch):
        db = MagicMock()
        db.query.side_effect = RuntimeError("query exploded")
        db.rollback.side_effect = RuntimeError("rollback exploded")
        monkeypatch.setattr("database.SessionLocal", lambda: db)

        handle_booking_cancelled_async(123)

        db.rollback.assert_called_once()
        db.close.assert_called_once()
