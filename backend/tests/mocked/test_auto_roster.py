"""
Unit tests for the auto-roster live-write path (`backend/auto_roster.py`).

Covers the per-event create / extend / skip decisions made when a booking
flips to CONFIRMED. Pure-function tests where possible; MagicMock-based
DB stubs where the function has to query / write.

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
    auto_create_or_extend_for_booking,
    handle_booking_cancelled,
)
from db_models import BookingStatus, ShiftStatus, ShiftType  # noqa: E402
from roster_planner import PlannerSettings  # noqa: E402


def mk_booking(
    *,
    booking_id: int = 1,
    reference: str = "TAG-AUTO0001",
    status: BookingStatus = BookingStatus.CONFIRMED,
    dropoff_dt: datetime = datetime(2026, 6, 10, 8, 0),
    pickup_dt: datetime = datetime(2026, 6, 17, 14, 0),
    flight_arrival_time=None,
):
    """SimpleNamespace booking — auto_roster only reads attributes."""
    return SimpleNamespace(
        id=booking_id,
        reference=reference,
        status=status,
        dropoff_date=dropoff_dt.date(),
        dropoff_time=dropoff_dt.time(),
        pickup_date=pickup_dt.date(),
        pickup_time=pickup_dt.time(),
        flight_arrival_time=flight_arrival_time,
    )


def mk_settings(
    *,
    gap_max_minutes: int = 120,
    start_buffer_minutes: int = 30,
    end_buffer_minutes: int = 30,
    min_shift_minutes: int = 60,
):
    """Minimal PlannerSettings stub — only the fields auto_roster reads."""
    return PlannerSettings(
        window_days=28,
        gap_max_minutes=gap_max_minutes,
        mixed_gap_max_minutes=gap_max_minutes,
        start_buffer_minutes=start_buffer_minutes,
        end_buffer_minutes=end_buffer_minutes,
        staffing_thresholds=[(3, 1), (999, 2)],
        max_hours_per_week=40,
        min_rest_hours=8,
        untouchable_hours=24,
        min_shift_minutes=min_shift_minutes,
    )


def make_query_chain_mock(
    *,
    auto_shifts: list = None,
    existing_links: list = None,
):
    """Build a MagicMock db with .query() chainable to .filter().all()/.first().

    `auto_shifts` is the list returned for the auto-shift candidate query.
    `existing_links` is the list returned for the booking-link existence
    query (returned by .all()).
    """
    db = MagicMock()
    auto_shifts = auto_shifts or []
    existing_links = existing_links or []

    def query_side_effect(model):
        from db_models import RosterShift, ShiftBookingLink
        chain = MagicMock()
        chain.filter.return_value = chain
        if model is RosterShift:
            chain.all.return_value = auto_shifts
            chain.first.return_value = auto_shifts[0] if auto_shifts else None
        elif model is ShiftBookingLink:
            chain.all.return_value = existing_links
            chain.first.return_value = existing_links[0] if existing_links else None
        else:
            chain.all.return_value = []
            chain.first.return_value = None
        return chain

    db.query.side_effect = query_side_effect
    return db


# =====================================================================================
# _events_for_booking (pure)
# =====================================================================================

class TestEventsForBooking:
    def test_happy_dropoff_and_pickup_extracted(self):
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        events = _events_for_booking(b)
        assert len(events) == 2
        assert events[0] == ("drop_off", datetime(2026, 6, 10, 8, 30))
        assert events[1] == ("pick_up", datetime(2026, 6, 17, 14, 0) - timedelta(minutes=30))

    def test_edge_pickup_uses_flight_arrival_when_set(self):
        """flight_arrival_time wins over pickup_time minus 30 (matches engine)."""
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
            dropoff_date=date(2026, 6, 10), dropoff_time=None,
            pickup_date=date(2026, 6, 17), pickup_time=time(14, 0),
            flight_arrival_time=None,
        )
        events = _events_for_booking(b)
        assert [e[0] for e in events] == ["pick_up"]

    def test_boundary_no_dates_at_all_returns_empty(self):
        b = SimpleNamespace(
            id=1, reference="X", status=BookingStatus.CONFIRMED,
            dropoff_date=None, dropoff_time=None,
            pickup_date=None, pickup_time=None,
            flight_arrival_time=None,
        )
        assert _events_for_booking(b) == []


# =====================================================================================
# _shift_window (pure)
# =====================================================================================

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


# =====================================================================================
# auto_create_or_extend_for_booking (top-level — uses mocked DB)
# =====================================================================================

class TestAutoCreateOrExtendForBooking:
    def test_happy_creates_two_shifts_for_isolated_dropoff_and_pickup(self):
        """Dropoff on 10/06, pickup on 17/06 — 7 days apart, no overlap.
        Expect 2 separate auto-shifts created."""
        db = make_query_chain_mock(auto_shifts=[], existing_links=[])
        b = mk_booking(
            dropoff_dt=datetime(2026, 6, 10, 8, 0),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result == {"created": 2, "extended": 0, "skipped": 0}
        # Two RosterShift adds + two ShiftBookingLink adds = 4 db.add calls
        assert db.add.call_count == 4
        db.commit.assert_called_once()

    def test_unhappy_refunded_booking_is_no_op(self):
        """Refunded bookings don't trigger auto-create — only CONFIRMED do."""
        db = make_query_chain_mock()
        b = mk_booking(status=BookingStatus.REFUNDED)
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result["skipped"] == 1
        assert result["created"] == 0
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_unhappy_cancelled_booking_is_no_op(self):
        db = make_query_chain_mock()
        b = mk_booking(status=BookingStatus.CANCELLED)
        result = auto_create_or_extend_for_booking(db, b, mk_settings())
        assert result["skipped"] == 1
        assert result["created"] == 0
        db.add.assert_not_called()

    def test_edge_extends_existing_auto_shift_within_gap_rule(self):
        """A new event 90 min after the edge of an existing auto-shift gets
        merged in — no new shift, the existing one extends."""
        existing = SimpleNamespace(
            id=42,
            staff_id=None,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(7, 30),  # buffer-back of an 08:00 dropoff
            end_time=time(8, 30),    # buffer-forward of an 08:00 dropoff
            shift_type=ShiftType.MORNING,
            status=ShiftStatus.SCHEDULED,
            created_source="auto",
        )
        db = make_query_chain_mock(auto_shifts=[existing], existing_links=[])
        b = mk_booking(
            booking_id=2,
            reference="TAG-NEAR0001",
            # New event at 10:00 — 90 min after the 08:30 shift edge.
            dropoff_dt=datetime(2026, 6, 10, 10, 0),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        result = auto_create_or_extend_for_booking(db, b, mk_settings(gap_max_minutes=120))
        # First event (10:00 dropoff) extends the 07:30-08:30 shift.
        # Second event (pickup on 17/06) is far away → new shift.
        assert result["extended"] >= 1
        assert result["created"] >= 1
        # The existing shift's end_time should have moved out to cover 10:30
        # (10:00 event + 30min end buffer).
        assert existing.end_time == time(10, 30)

    def test_boundary_event_just_outside_gap_creates_new_shift(self):
        """An event 121 min after the shift edge is BEYOND gap_max=120, so
        a new shift should be created (not extend)."""
        existing = SimpleNamespace(
            id=42,
            staff_id=None,
            date=date(2026, 6, 10),
            end_date=None,
            start_time=time(7, 30),
            end_time=time(8, 30),
            shift_type=ShiftType.MORNING,
            status=ShiftStatus.SCHEDULED,
            created_source="auto",
        )
        db = make_query_chain_mock(auto_shifts=[existing], existing_links=[])
        b = mk_booking(
            # 08:30 + 2h01m = 10:31 — just past the gap_max threshold.
            dropoff_dt=datetime(2026, 6, 10, 10, 31),
            pickup_dt=datetime(2026, 6, 17, 14, 0),
        )
        result = auto_create_or_extend_for_booking(db, b, mk_settings(gap_max_minutes=120))
        # Both events need new shifts — neither matches the existing 08:30 edge.
        assert result["created"] == 2
        assert result["extended"] == 0


# =====================================================================================
# handle_booking_cancelled
# =====================================================================================

class TestHandleBookingCancelled:
    def _link(self, link_id, shift_id, booking_id):
        return SimpleNamespace(id=link_id, shift_id=shift_id, booking_id=booking_id)

    def _shift(self, sid, source="auto", staff_id=None, status=ShiftStatus.SCHEDULED):
        return SimpleNamespace(
            id=sid, created_source=source, staff_id=staff_id,
            status=status, bookings=[],
        )

    def _make_db(self, *, links, shifts_by_id, remaining_by_shift):
        """A mock db that returns:
        - .query(ShiftBookingLink).filter(...).all() → `links` initially
        - .query(RosterShift).filter(id == X).first() → shifts_by_id[X] or None
        - .query(ShiftBookingLink).filter(shift_id == X).first() → remaining_by_shift[X]
        """
        db = MagicMock()
        deleted = {"links": [], "shifts": []}

        from db_models import RosterShift, ShiftBookingLink

        def query_side_effect(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            if model is ShiftBookingLink:
                chain.all.return_value = list(links)

                def first_side_effect():
                    # Used for the post-delete "any remaining link?" check.
                    return remaining_by_shift.get(getattr(first_side_effect, "_last_shift_id", None))

                # Capture the most recent shift_id passed to filter so the
                # post-delete check returns the right "remaining link" answer.
                # Simpler: just sequentially pop from a queue.
                chain.first.side_effect = list(remaining_by_shift.values())
            elif model is RosterShift:
                def first_side_effect_shift():
                    # No clean way to capture id; use a queue keyed on shifts requested.
                    # The function calls .first() once per ShiftBookingLink (to find
                    # the linked shift), then once per auto_shift_id (to refetch).
                    # Just iterate through shifts_by_id values in order.
                    return next(first_side_effect_shift._iter, None)
                first_side_effect_shift._iter = iter([
                    *(shifts_by_id.get(l.shift_id) for l in links),
                    *(shifts_by_id.get(sid) for sid in {l.shift_id for l in links} if shifts_by_id.get(sid) and shifts_by_id.get(sid).created_source == "auto"),
                ])
                chain.first.side_effect = first_side_effect_shift
            else:
                chain.all.return_value = []
                chain.first.return_value = None
            return chain

        db.query.side_effect = query_side_effect

        def delete_side_effect(obj):
            if isinstance(obj, MagicMock) or hasattr(obj, "shift_id"):
                # link
                deleted["links"].append(obj)
            else:
                deleted["shifts"].append(obj)
        db.delete.side_effect = delete_side_effect
        db._deleted = deleted
        return db

    def test_happy_unlinks_and_deletes_empty_auto_shift(self):
        """Cancelled booking → unlink from auto-shift → shift now empty +
        unassigned + scheduled → delete the auto-shift."""
        shift = self._shift(99, source="auto", staff_id=None, status=ShiftStatus.SCHEDULED)
        link = self._link(1, shift.id, 7)
        db = self._make_db(
            links=[link],
            shifts_by_id={99: shift},
            remaining_by_shift={99: None},  # no other links left after delete
        )
        booking = SimpleNamespace(id=7, reference="TAG-CANC0001", status=BookingStatus.CANCELLED)
        result = handle_booking_cancelled(db, booking)
        assert result == {"links_removed": 1, "auto_shifts_deleted": 1}

    def test_unhappy_non_cancelled_booking_is_no_op(self):
        db = MagicMock()
        booking = SimpleNamespace(id=7, status=BookingStatus.CONFIRMED)
        result = handle_booking_cancelled(db, booking)
        assert result == {"links_removed": 0, "auto_shifts_deleted": 0}
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    def test_edge_admin_shift_link_left_intact(self):
        """If the cancelled booking is linked to a manual/planner shift, the
        link is NOT removed — admin/planner shifts are admin territory."""
        shift = self._shift(99, source="manual")
        link = self._link(1, shift.id, 7)
        db = self._make_db(
            links=[link],
            shifts_by_id={99: shift},
            remaining_by_shift={},
        )
        booking = SimpleNamespace(id=7, reference="TAG-CANC0002", status=BookingStatus.CANCELLED)
        result = handle_booking_cancelled(db, booking)
        assert result["links_removed"] == 0
        assert result["auto_shifts_deleted"] == 0

    def test_boundary_assigned_auto_shift_is_unlinked_but_not_deleted(self):
        """If the auto-shift is unassigned still, it gets deleted on empty —
        but if a jockey claimed it (staff_id set), the shift is left in place
        even after the link is removed (admin's call from there)."""
        shift = self._shift(99, source="auto", staff_id=42)
        link = self._link(1, shift.id, 7)
        db = self._make_db(
            links=[link],
            shifts_by_id={99: shift},
            remaining_by_shift={99: None},
        )
        booking = SimpleNamespace(id=7, reference="TAG-CANC0003", status=BookingStatus.CANCELLED)
        result = handle_booking_cancelled(db, booking)
        assert result["links_removed"] == 1
        assert result["auto_shifts_deleted"] == 0
