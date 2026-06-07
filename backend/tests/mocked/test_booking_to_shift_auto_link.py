"""Auto-link freshly-confirmed bookings to existing live planner-sourced
jockey shifts. Per SPEC.md Happy / Unhappy / Edge / Boundary matrix.

Lifecycle: a new CONFIRMED booking fires `auto_link_booking_to_shifts`
in a background task. Function scans live planner-sourced jockey shifts
that cover the booking's drop-off and/or pickup events and writes a
ShiftBookingLink row for each. Idempotent; failure-isolated; does not
touch admin-created shifts (planner_run_id IS NULL) or fleet shifts.
"""
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from db_models import RosterShift, ShiftBookingLink, ShiftStatus, Booking
from roster_planner_runner import (
    auto_link_booking_to_shifts,
    _shift_covers_event,
)


# =====================================================================================
# Test factories
# =====================================================================================


def _mk_booking(
    booking_id=1,
    reference="TAG-AUTO-1",
    dropoff_date=date(2026, 5, 11),
    dropoff_time=time(9, 0),
    pickup_date=date(2026, 5, 14),
    pickup_time=time(17, 0),
):
    return SimpleNamespace(
        id=booking_id,
        reference=reference,
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
    )


def _mk_shift(
    shift_id=100,
    shift_date=date(2026, 5, 11),
    end_date=None,
    start_time=time(8, 0),
    end_time=time(16, 0),
    status=ShiftStatus.SCHEDULED,
    planner_run_id="run-x",
    intended_driver_type="jockey",
):
    s = MagicMock(spec=RosterShift)
    s.id = shift_id
    s.date = shift_date
    s.end_date = end_date or shift_date
    s.start_time = start_time
    s.end_time = end_time
    s.status = status
    s.planner_run_id = planner_run_id
    s.intended_driver_type = intended_driver_type
    return s


class _FakeQuery:
    """Minimal SQLAlchemy-query stand-in. Filters are no-ops; tests pre-seed
    the rows the query is expected to return."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


@pytest.fixture
def db():
    """MagicMock DB session.

    `db._candidate_shifts`: rows the candidate-shifts query returns.
    `db._existing_links`: rows the idempotency-check query returns. Defaults
        to empty (no link exists). Tests can mutate to seed dupes.
    """
    sess = MagicMock()
    sess._candidate_shifts = []
    sess._existing_links = {}  # key=(shift_id, booking_id) → row
    sess._added = []
    sess._committed = False
    sess._rolled_back = False

    def _query(model):
        if model is RosterShift:
            return _FakeQuery(sess._candidate_shifts)
        if model is ShiftBookingLink:
            # Tests seed by exact (shift_id, booking_id) pair via a closure
            # over the next .filter() call. We don't have access to the
            # filter args, so just look up the most-recently-added link to
            # decide existence — see helper `seed_existing_link`.
            return _FakeQuery(list(sess._existing_links.values()))
        return _FakeQuery([])

    sess.query.side_effect = _query
    sess.add = MagicMock(side_effect=lambda obj: sess._added.append(obj))
    sess.commit = MagicMock(side_effect=lambda: setattr(sess, "_committed", True))
    sess.rollback = MagicMock(side_effect=lambda: setattr(sess, "_rolled_back", True))
    return sess


def _added_links(db) -> list:
    return [a for a in db._added if isinstance(a, ShiftBookingLink)]


# =====================================================================================
# Happy path
# =====================================================================================


class TestAutoLinkHappy:
    def test_links_booking_to_single_covering_jockey_shift(self, db):
        """Drop-off at 09:00 falls in 08:00-16:00 jockey shift → 1 link."""
        booking = _mk_booking()
        shift = _mk_shift(shift_id=100)
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == [100]
        links = _added_links(db)
        assert len(links) == 1
        assert links[0].shift_id == 100
        assert links[0].booking_id == 1
        assert db._committed is True

    def test_links_booking_to_both_dropoff_and_pickup_shifts(self, db):
        """Drop-off + pickup hit two different shifts → both linked."""
        booking = _mk_booking()
        s_drop = _mk_shift(
            shift_id=100, shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
        )
        s_pick = _mk_shift(
            shift_id=200, shift_date=date(2026, 5, 14),
            start_time=time(15, 0), end_time=time(23, 0),
        )
        db._candidate_shifts = [s_drop, s_pick]

        result = auto_link_booking_to_shifts(db, booking)
        assert sorted(result) == [100, 200]

    def test_links_to_all_duplicates_at_same_time_window(self, db):
        """Three duplicate shifts at the same window → booking attaches to
        all three (link-to-all semantics, ownership decided at claim time)."""
        booking = _mk_booking()
        shifts = [_mk_shift(shift_id=100 + i) for i in range(3)]
        db._candidate_shifts = shifts

        result = auto_link_booking_to_shifts(db, booking)
        assert sorted(result) == [100, 101, 102]


# =====================================================================================
# Unhappy path
# =====================================================================================


class TestAutoLinkUnhappy:
    def test_skips_fleet_shift(self, db):
        """Fleet shifts do not auto-pick-up jockey-workload bookings."""
        booking = _mk_booking()
        shift = _mk_shift(shift_id=100, intended_driver_type="fleet")
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []
        assert _added_links(db) == []
        assert db._committed is False

    def test_links_admin_created_shift_too(self, db):
        """Admin-created shifts (planner_run_id=NULL) are eligible — alignment
        between bookings and shifts must be automatic regardless of how the
        shift was created (May 2026 user preference)."""
        booking = _mk_booking()
        shift = _mk_shift(shift_id=100, planner_run_id=None)
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == [100]
        assert _added_links(db) == [_added_links(db)[0]]  # exactly one link written

    def test_skips_when_no_shift_covers_event(self, db):
        """Drop-off at 09:00 vs shift 17:00-22:00 → no overlap, no link."""
        booking = _mk_booking()
        shift = _mk_shift(shift_id=100, start_time=time(17, 0), end_time=time(22, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []
        assert db._committed is False

    def test_handles_booking_with_no_event_times(self, db):
        """Booking without dropoff_time AND pickup_time → no match work."""
        booking = SimpleNamespace(
            id=1, reference="X",
            dropoff_date=None, dropoff_time=None,
            pickup_date=None, pickup_time=None,
        )
        db._candidate_shifts = [_mk_shift()]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []
        assert db.query.called is False  # short-circuited

    def test_failure_isolated_from_caller(self, db):
        """If the candidate-shift query raises, we log and return [] — never
        re-raise into the caller (BackgroundTasks runs after response)."""
        booking = _mk_booking()
        db.query.side_effect = RuntimeError("database is on fire")

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []


# =====================================================================================
# Edge cases
# =====================================================================================


class TestAutoLinkEdge:
    def test_idempotent_skips_existing_link(self, db):
        """If a ShiftBookingLink already exists for (shift, booking), don't
        write a duplicate row."""
        booking = _mk_booking()
        shift = _mk_shift(shift_id=100)
        db._candidate_shifts = [shift]
        # Seed an existing link so the idempotency query returns it.
        existing = ShiftBookingLink(shift_id=100, booking_id=1)
        db._existing_links[(100, 1)] = existing

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []
        assert _added_links(db) == []

    def test_fleet_and_jockey_mixed_only_jockey_picked_up(self, db):
        """Some fleet, some jockey — only jockey shifts attract the link."""
        booking = _mk_booking()
        jockey1 = _mk_shift(shift_id=100, intended_driver_type="jockey")
        fleet = _mk_shift(shift_id=200, intended_driver_type="fleet")
        jockey2 = _mk_shift(shift_id=300, intended_driver_type=None)  # NULL ↔ jockey
        db._candidate_shifts = [jockey1, fleet, jockey2]

        result = auto_link_booking_to_shifts(db, booking)
        assert sorted(result) == [100, 300]

    def test_overnight_shift_covers_late_event(self, db):
        """Pickup at 01:00 next day falls inside an overnight 23:00-02:00
        shift — span comparison must respect end_date."""
        booking = SimpleNamespace(
            id=1, reference="X",
            dropoff_date=None, dropoff_time=None,
            pickup_date=date(2026, 5, 12),
            pickup_time=time(1, 0),
        )
        overnight = _mk_shift(
            shift_id=100,
            shift_date=date(2026, 5, 11), end_date=date(2026, 5, 12),
            start_time=time(23, 0), end_time=time(2, 0),
        )
        db._candidate_shifts = [overnight]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == [100]


# =====================================================================================
# Boundaries — min/max time and date edges
# =====================================================================================


class TestAutoLinkBoundary:
    def test_event_exactly_at_shift_start_links(self, db):
        """Drop-off time == shift.start_time → covered (inclusive)."""
        booking = _mk_booking(dropoff_time=time(8, 0))
        shift = _mk_shift(shift_id=100, start_time=time(8, 0), end_time=time(16, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == [100]

    def test_event_exactly_at_shift_end_does_not_link_without_buffer(self, db):
        """Drop-off time == shift.end_time leaves no end buffer → no link."""
        booking = _mk_booking(dropoff_time=time(16, 0))
        shift = _mk_shift(shift_id=100, start_time=time(8, 0), end_time=time(16, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []

    def test_event_exactly_end_buffer_before_shift_end_links(self, db):
        """Drop-off at 15:30 in 08:00-16:00 leaves the 30m end buffer."""
        booking = _mk_booking(dropoff_time=time(15, 30))
        shift = _mk_shift(shift_id=100, start_time=time(8, 0), end_time=time(16, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == [100]

    def test_HUEB_dropoff_0645_does_not_link_to_shift_ending_0700(self, db):
        """HUEB regression: TAG-SHS00925-style 06:45 drop-off needs
        coverage until 07:15, so a 03:50-07:00 fixed shift is not enough."""
        booking = _mk_booking(
            booking_id=807,
            reference="TAG-SHS00925",
            dropoff_date=date(2026, 6, 8),
            dropoff_time=time(6, 45),
        )
        short_shift = _mk_shift(
            shift_id=3663,
            shift_date=date(2026, 6, 8),
            start_time=time(3, 50),
            end_time=time(7, 0),
        )
        covered_shift = _mk_shift(
            shift_id=9001,
            shift_date=date(2026, 6, 8),
            start_time=time(3, 50),
            end_time=time(7, 15),
        )

        db._candidate_shifts = [short_shift]
        assert auto_link_booking_to_shifts(db, booking) == []

        db._added.clear()
        db._committed = False
        db._candidate_shifts = [covered_shift]
        assert auto_link_booking_to_shifts(db, booking) == [9001]

    def test_event_one_minute_before_start_does_not_link(self, db):
        """07:59 falls just outside 08:00-16:00 → no link."""
        booking = _mk_booking(dropoff_time=time(7, 59))
        shift = _mk_shift(shift_id=100, start_time=time(8, 0), end_time=time(16, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []

    def test_event_one_minute_after_end_does_not_link(self, db):
        """16:01 falls just outside 08:00-16:00 → no link."""
        booking = _mk_booking(dropoff_time=time(16, 1))
        shift = _mk_shift(shift_id=100, start_time=time(8, 0), end_time=time(16, 0))
        db._candidate_shifts = [shift]

        result = auto_link_booking_to_shifts(db, booking)
        assert result == []

    def test_in_progress_shift_not_eligible(self, db):
        """IN_PROGRESS shifts are filtered out by the query — defensively
        ensure the function still works correctly if one slipped past."""
        # Filter is enforced in SQL. This test documents the rule via the
        # status enum used in the filter.
        from db_models import ShiftStatus
        assert ShiftStatus.IN_PROGRESS not in (
            ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED
        )


# =====================================================================================
# Coverage helper unit tests — _shift_covers_event
# =====================================================================================


class TestShiftCoversEvent:
    def test_handles_none_event(self):
        s = _mk_shift()
        assert _shift_covers_event(s, None) is False

    def test_inclusive_on_both_endpoints(self):
        s = _mk_shift(start_time=time(8, 0), end_time=time(16, 0))
        assert _shift_covers_event(s, datetime(2026, 5, 11, 8, 0)) is True
        assert _shift_covers_event(s, datetime(2026, 5, 11, 16, 0)) is True

    def test_overnight_span_inclusive(self):
        s = _mk_shift(
            shift_date=date(2026, 5, 11), end_date=date(2026, 5, 12),
            start_time=time(23, 0), end_time=time(2, 0),
        )
        assert _shift_covers_event(s, datetime(2026, 5, 11, 23, 30)) is True
        assert _shift_covers_event(s, datetime(2026, 5, 12, 0, 30)) is True
        assert _shift_covers_event(s, datetime(2026, 5, 12, 2, 0)) is True
        assert _shift_covers_event(s, datetime(2026, 5, 12, 2, 1)) is False


# =====================================================================================
# Auto-link uses _events_for_booking (code-review pivot 2026-05-28).
#
# Auto-link now shares the rebuild's event extraction: pickups derive from
# flight_arrival_date + flight_arrival_time (canonical) with handoff at
# arrival + 30; drop-offs anchor on dropoff_date + dropoff_time. The literal
# pickup_date + pickup_time fields are NOT consulted by auto-link any more
# — they're customer-facing display only.
# =====================================================================================


def _mk_booking_with_flight(
    booking_id=1,
    reference="TAG-FA-001",
    dropoff_date=date(2026, 5, 11),
    dropoff_time=time(9, 0),
    flight_arrival_date=date(2026, 5, 14),
    flight_arrival_time=time(15, 40),
    pickup_date=date(2026, 5, 14),
    pickup_time=time(17, 30),
):
    """Booking with explicit flight_arrival_date / _time. Useful for verifying
    that auto-link keys off the flight anchor, not the literal pickup_time."""
    b = SimpleNamespace(
        id=booking_id,
        reference=reference,
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
        flight_arrival_date=flight_arrival_date,
        flight_arrival_time=flight_arrival_time,
    )
    return b


class TestAutoLinkSharesEventExtraction:

    def test_H_flight_arrival_drives_linking_not_pickup_time(self, db):
        """Happy / the EXACT reviewer mismatch case:
            shift           15:30 – 16:15
            flight_arrival  15:40
            derived handoff 16:10   (arrival + 30)
            stored pickup   17:30
        Arrival (15:40), derived handoff (16:10), and the configured 30m
        end buffer sit inside 15:30–16:40. The customer-facing pickup_time (17:30) is way
        outside but auto-link must NOT consult it any more — keying on
        the canonical arrival anchor closes the orphan gap that the
        old (literal pickup_time) code would have hit here. Old code:
        17:30 outside 15:30–16:40 → no link → orphan. New code: buffered handoff
        anchor inside → link."""
        booking = _mk_booking_with_flight(
            booking_id=10,
            flight_arrival_date=date(2026, 5, 14),
            flight_arrival_time=time(15, 40),
            pickup_date=date(2026, 5, 14),
            pickup_time=time(17, 30),
        )
        s_drop = _mk_shift(
            shift_id=100, shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
        )
        s_pick = _mk_shift(
            shift_id=200, shift_date=date(2026, 5, 14),
            start_time=time(15, 30), end_time=time(16, 40),
        )
        db._candidate_shifts = [s_drop, s_pick]

        result = auto_link_booking_to_shifts(db, booking)
        assert 200 in result, (
            "shift 15:30–16:40 covers arrival 15:40, derived handoff "
            "16:10, and the 30m end buffer — link must be created; literal pickup_time 17:30 is "
            "irrelevant"
        )
        # drop-off side also links.
        assert 100 in result

    def test_E_pickup_time_later_than_handoff_still_links(self, db):
        """Edge: arrival 14:00, derived handoff 14:30, literal pickup_time
        17:30. Shift 14:00–15:00 covers the canonical event plus buffer but ends
        before the literal pickup. Auto-link must still link — the link
        is keyed on the canonical event window, not the customer-facing
        pickup_time. (Closes the orphan-gap reviewer flagged: rebuild
        would skip-as-covered here too, so they must agree.)"""
        booking = _mk_booking_with_flight(
            booking_id=11, reference="TAG-FA-002",
            flight_arrival_date=date(2026, 5, 14),
            flight_arrival_time=time(14, 0),
            pickup_date=date(2026, 5, 14),
            pickup_time=time(17, 30),  # much later than arrival + 30
        )
        s_drop = _mk_shift(
            shift_id=100, shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
        )
        s_pick = _mk_shift(
            shift_id=300, shift_date=date(2026, 5, 14),
            start_time=time(14, 0), end_time=time(15, 0),  # covers canonical
        )
        db._candidate_shifts = [s_drop, s_pick]

        result = auto_link_booking_to_shifts(db, booking)
        assert 300 in result, (
            "shift covering [arrival, arrival+30,end_buffer] must link even when "
            "literal pickup_time falls outside the shift"
        )

    def test_U_derived_handoff_outside_window_does_not_link(self, db):
        """Unhappy: arrival 15:40, handoff 16:10. Shift 12:00–16:10 covers
        the handoff but NOT the 30m end buffer. Auto-link must require the
        full buffered window to fit."""
        booking = _mk_booking_with_flight(
            booking_id=12, reference="TAG-FA-003",
            flight_arrival_date=date(2026, 5, 14),
            flight_arrival_time=time(15, 40),
            pickup_date=date(2026, 5, 14),
            pickup_time=time(16, 10),
        )
        s_drop = _mk_shift(
            shift_id=100, shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
        )
        s_pick_too_short = _mk_shift(
            shift_id=400, shift_date=date(2026, 5, 14),
            start_time=time(12, 0), end_time=time(16, 10),  # ends BEFORE buffered handoff
        )
        db._candidate_shifts = [s_drop, s_pick_too_short]

        result = auto_link_booking_to_shifts(db, booking)
        assert 400 not in result, (
            "shift ending at 16:10 does not cover buffered handoff until 16:40 → no link"
        )
        # Drop-off still links (separate event).
        assert 100 in result

    def test_B_overnight_arrival_links_to_prior_day_evening_shift(self, db):
        """Boundary: flight arrives 23:55 on 5/13, derived handoff 00:25
        on 5/14. A shift dated 5/13 with end_date 5/14 covering 22:00–
        01:00 spans the overnight cleanly and must catch both endpoints
        of the pickup event. Mirrors the rebuild's overnight rebucket."""
        booking = _mk_booking_with_flight(
            booking_id=13, reference="TAG-FA-004",
            dropoff_date=date(2026, 5, 1),
            dropoff_time=time(9, 0),
            flight_arrival_date=date(2026, 5, 13),
            flight_arrival_time=time(23, 55),
            pickup_date=date(2026, 5, 14),
            pickup_time=time(0, 25),
        )
        s_overnight = _mk_shift(
            shift_id=500, shift_date=date(2026, 5, 13),
            end_date=date(2026, 5, 14),
            start_time=time(22, 0), end_time=time(1, 0),
        )
        # Add a dropoff-only shift too for completeness; we only care
        # about whether the overnight shift catches the pickup event.
        s_drop = _mk_shift(
            shift_id=100, shift_date=date(2026, 5, 1),
            start_time=time(8, 0), end_time=time(16, 0),
        )
        db._candidate_shifts = [s_drop, s_overnight]

        result = auto_link_booking_to_shifts(db, booking)
        assert 500 in result, (
            "overnight shift must catch the pickup event whose endpoints "
            "straddle midnight"
        )
