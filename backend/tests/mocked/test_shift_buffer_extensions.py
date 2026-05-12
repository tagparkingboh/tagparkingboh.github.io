"""
TDD spec for the per-cluster shift-buffer extension rule.

Locked rules (2026-05-07 conversation):
  - Default shift wraps the cluster with `base_start_minutes` / `base_end_minutes`.
  - Pickup tight pair = two consecutive **pickup** events (same type) with
    arrival-time gap STRICTLY less than 30 minutes. Each tight pair adds
    30 minutes to the START buffer.
  - Drop-off tight pair = same idea, but on **drop_off** events. Each tight
    pair adds 30 minutes to the END buffer.
  - Same-type only — a drop_off→pick_up transition (or vice versa) does NOT
    count as a tight pair on either side.
  - Pairs are scanned across the whole shift, independent of the 190-min
    cluster-formation threshold.
  - A single event of either type gets just the base buffer; no extension.

Formulas:
    start_buffer = base_start + 30 × pickup_missed_pairs
    end_buffer   = base_end   + 30 × dropoff_missed_pairs

Coverage matrix:
    A. Pure unit tests on `compute_shift_buffers` (does not exist yet — RED).
    B. Integration tests through `rebuild_auto_for_dates` to confirm the rule
       reaches the materialised shift's start_time / end_time (RED).

The implementation follows in a separate change (GREEN).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db_models import (  # noqa: E402
    BookingStatus,
    ServiceType,
    ShiftStatus,
    ShiftType,
)
from roster_planner import Event, EventCluster, PlannerSettings, UK_TZ  # noqa: E402
from auto_roster import rebuild_auto_for_dates  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dropoff_event(dt: datetime, booking_id: int = 1) -> Event:
    """Build a drop-off Event. event_time == end_anchor_time == dropoff_time."""
    aware = dt.replace(tzinfo=UK_TZ)
    return Event(
        booking_id=booking_id,
        booking_reference=f"TAG-DO{booking_id:05d}",
        event_type="drop_off",
        event_time=aware,
        end_anchor_time=aware,
    )


def _pickup_event(arrival: datetime, end: datetime | None = None, booking_id: int = 1) -> Event:
    """Build a pick-up Event keyed off arrival time.

    event_time = arrival (start anchor — driver must be at airport before plane lands).
    end_anchor_time = pickup_time = arrival + 30 min unless overridden.
    """
    if end is None:
        end = arrival + timedelta(minutes=30)
    return Event(
        booking_id=booking_id,
        booking_reference=f"TAG-PU{booking_id:05d}",
        event_type="pick_up",
        event_time=arrival.replace(tzinfo=UK_TZ),
        end_anchor_time=end.replace(tzinfo=UK_TZ),
    )


def _cluster(*events: Event) -> EventCluster:
    return EventCluster(events=list(events))


def mk_booking(
    *,
    booking_id: int = 1,
    reference: str = "TAG-BUF00001",
    status: BookingStatus = BookingStatus.CONFIRMED,
    service_type: ServiceType = ServiceType.MEET_GREET,
    dropoff_dt: datetime = datetime(2026, 6, 10, 8, 0),
    pickup_dt: datetime = datetime(2026, 6, 17, 14, 0),
    flight_arrival_time=None,
):
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
    start_buffer_minutes: int = 30,
    end_buffer_minutes: int = 30,
    gap_max_minutes: int = 190,
    mixed_gap_max_minutes: int = 190,
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
    db = MagicMock()
    untouched_auto_shifts = list(untouched_auto_shifts or [])
    bookings = list(bookings or [])
    added: list = []
    deleted: list = []

    from db_models import Booking, RosterShift, ShiftBookingLink

    def query_side_effect(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        if model is RosterShift:
            chain.all.return_value = list(untouched_auto_shifts)
            chain.first.return_value = untouched_auto_shifts[0] if untouched_auto_shifts else None
        elif model is Booking:
            chain.all.return_value = list(bookings)
            chain.first.return_value = bookings[0] if bookings else None
        else:
            chain.all.return_value = []
            chain.first.return_value = None
        return chain

    db.query.side_effect = query_side_effect
    db.add.side_effect = lambda obj: added.append(obj)
    db.delete.side_effect = lambda obj: deleted.append(obj)
    db._added = added
    db._deleted = deleted
    return db


# ===========================================================================
# A. Pure unit tests — compute_shift_buffers
# ===========================================================================
#
# Function under test (does not yet exist — fails at import = RED phase):
#
#     from roster_planner import compute_shift_buffers
#     compute_shift_buffers(
#         cluster: EventCluster,
#         base_start_minutes: int,
#         base_end_minutes: int,
#         tight_gap_minutes: int = 30,
#         extension_minutes: int = 30,
#     ) -> tuple[int, int]
#
# Returns (start_buffer_minutes, end_buffer_minutes).


def _import_target():
    """Try-import the target so the rest of the suite can skip cleanly with a
    descriptive failure rather than a collection-time crash. The import error
    IS the red-phase signal."""
    from roster_planner import compute_shift_buffers  # type: ignore[attr-defined]
    return compute_shift_buffers


class TestComputeShiftBuffersBaseline:
    """Without any same-type tight pair, the cluster gets just the base."""

    def test_happy_single_dropoff_uses_base_buffers(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(_dropoff_event(datetime(2026, 6, 10, 8, 0)))
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_happy_single_pickup_uses_base_buffers(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(_pickup_event(datetime(2026, 6, 10, 14, 0)))
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_happy_empty_cluster_returns_base(self):
        compute_shift_buffers = _import_target()
        assert compute_shift_buffers(_cluster(), 30, 30) == (30, 30)

    def test_happy_base_buffers_are_respected_when_non_default(self):
        """Don't hard-code 30 — the base values come from settings."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(_dropoff_event(datetime(2026, 6, 10, 8, 0)))
        assert compute_shift_buffers(cluster, 20, 45) == (20, 45)


class TestComputeShiftBuffersGapBoundary:
    """Gap of exactly 30 min = OK (≥30 doesn't count as missed). 29 min = missed."""

    def test_boundary_dropoff_pair_gap_30_no_extension(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 30)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_boundary_dropoff_pair_gap_29_extends(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 29)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 60)

    def test_boundary_pickup_pair_gap_30_no_extension(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _pickup_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 30)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_boundary_pickup_pair_gap_29_extends_start(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _pickup_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 29)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (60, 30)


class TestComputeShiftBuffersDropoffExtension:
    """Drop-off → drop-off tight pairs add 30 to the END buffer per pair."""

    def test_happy_two_dropoffs_one_missed_pair(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 15)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 60)

    def test_happy_user_4_dropoff_example(self):
        """User example: 04:50, 05:00, 05:15, 05:20 → 3 missed pairs → end +90 → end_buffer 120."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 4, 50)),
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 15)),
            _dropoff_event(datetime(2026, 6, 10, 5, 20)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 120)

    def test_edge_three_dropoffs_one_missed_one_loose(self):
        """Gaps 10, 60 → 1 missed pair → end_buffer = 30 + 30 = 60."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 10)),
            _dropoff_event(datetime(2026, 6, 10, 6, 10)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 60)

    def test_edge_three_dropoffs_loose_then_missed(self):
        """Order doesn't matter — same count, same answer."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 6, 0)),
            _dropoff_event(datetime(2026, 6, 10, 6, 10)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 60)

    def test_edge_four_dropoffs_two_missed_pairs_split_by_loose(self):
        """Gaps 10, 100, 10 → 2 missed pairs → end_buffer = 30 + 60 = 90."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 5, 0)),
            _dropoff_event(datetime(2026, 6, 10, 5, 10)),
            _dropoff_event(datetime(2026, 6, 10, 6, 50)),
            _dropoff_event(datetime(2026, 6, 10, 7, 0)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 90)


class TestComputeShiftBuffersPickupExtension:
    """Pickup → pickup tight pairs add 30 to the START buffer per pair.

    Pickup events are keyed by arrival time (event_time on the engine Event)."""

    def test_happy_two_pickups_one_missed_pair(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _pickup_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 15)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (60, 30)

    def test_happy_user_3_pickup_example(self):
        """User example: arrivals 23:20 / 23:30 / 23:40 → 2 missed pairs → start_buffer = 30 + 60 = 90."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _pickup_event(datetime(2026, 6, 10, 23, 20)),
            _pickup_event(datetime(2026, 6, 10, 23, 30)),
            _pickup_event(datetime(2026, 6, 10, 23, 40)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (90, 30)

    def test_edge_pickup_pair_loose_no_extension(self):
        """Gap 60 min — no missed pair → no extension."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _pickup_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 15, 0)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)


class TestComputeShiftBuffersSameTypeOnly:
    """Mixed pairs (drop_off → pick_up or vice versa) do NOT count as missed."""

    def test_edge_mixed_pair_close_no_extension_either_side(self):
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 10)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_edge_dropoff_then_pickup_then_dropoff_pickup_not_bridged(self):
        """A pickup between two drop-offs doesn't 'bridge' a drop-off→drop-off pair.
        Drop-offs at 14:00 and 14:50 — even with a pickup at 14:25 between them,
        their direct gap is 50 min so they're NOT a missed pair."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 25)),
            _dropoff_event(datetime(2026, 6, 10, 14, 50)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 30)

    def test_edge_dropoff_pair_close_with_pickup_between(self):
        """Drop-offs at 14:00 and 14:20 (gap 20, missed) — pickup at 14:10
        between them shouldn't suppress the missed pair."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            _dropoff_event(datetime(2026, 6, 10, 14, 0)),
            _pickup_event(datetime(2026, 6, 10, 14, 10)),
            _dropoff_event(datetime(2026, 6, 10, 14, 20)),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (30, 60)


class TestComputeShiftBuffersBothExtensionsStack:
    """A shift can hold both a pickup cluster and a drop-off cluster — both
    extensions apply independently."""

    def test_happy_pickups_extend_start_dropoffs_extend_end(self):
        """3 pickups (2 missed pairs → +60 start) + 4 drop-offs (3 missed → +90 end)."""
        compute_shift_buffers = _import_target()
        cluster = _cluster(
            # 3 pickups, gaps 10/10
            _pickup_event(datetime(2026, 6, 10, 6, 0), booking_id=1),
            _pickup_event(datetime(2026, 6, 10, 6, 10), booking_id=2),
            _pickup_event(datetime(2026, 6, 10, 6, 20), booking_id=3),
            # 4 drop-offs, gaps 10/15/5
            _dropoff_event(datetime(2026, 6, 10, 8, 0), booking_id=4),
            _dropoff_event(datetime(2026, 6, 10, 8, 10), booking_id=5),
            _dropoff_event(datetime(2026, 6, 10, 8, 25), booking_id=6),
            _dropoff_event(datetime(2026, 6, 10, 8, 30), booking_id=7),
        )
        assert compute_shift_buffers(cluster, 30, 30) == (90, 120)


# ===========================================================================
# B. Integration tests — through rebuild_auto_for_dates
# Confirms the extension reaches the materialised RosterShift.start_time/end_time.
# ===========================================================================


class TestRebuildAppliesPickupExtension:
    def test_happy_three_pickups_within_30min_extends_start_by_60(self):
        """User example: arrivals 23:20 / 23:30 / 23:40 on June 17.
        Pickup_times wrap to June 18 (+30 min). Cluster is pickup-led so the
        base start_buffer is 15 (locked 2026-05-12) regardless of settings.
        2 missed pairs → start_buffer = 15 + 60 = 75 → 23:20 - 75 = 22:05."""
        bookings = []
        for i, (arr_h, arr_m) in enumerate([(23, 20), (23, 30), (23, 40)]):
            pt_total = arr_h * 60 + arr_m + 30
            pt_h, pt_m = (pt_total // 60) % 24, pt_total % 60
            pt_date = date(2026, 6, 17)
            if pt_total >= 24 * 60:
                pt_date = date(2026, 6, 18)
            bookings.append(mk_booking(
                booking_id=100 + i,
                reference=f"TAG-PUX{i:05d}",
                dropoff_dt=datetime(2026, 6, 10, 8, 0),  # earlier, out of target
                pickup_dt=datetime(pt_date.year, pt_date.month, pt_date.day, pt_h, pt_m),
                flight_arrival_time=time(arr_h, arr_m),
            ))
        db = make_db(bookings=bookings)
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 17)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 17)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(22, 5), (
            f"Expected 22:05 (= 23:20 − 15 pickup-led base − 60 for 2 missed pairs), got {s.start_time}"
        )
        # Last pickup arrival = 23:40, end_anchor = pickup_time = 00:10 next day.
        # End buffer = base 30 (no drop-off pairs) → 00:40 next day.
        assert s.end_date == date(2026, 6, 18)
        assert s.end_time == time(0, 40)


class TestRebuildAppliesDropoffExtension:
    def test_happy_four_dropoffs_within_30min_extends_end_by_90(self):
        """User example: drop-offs at 04:50 / 05:00 / 05:15 / 05:20 on June 10.
        3 missed pairs → end_buffer = 30 + 90 = 120 → shift ends 07:20."""
        bookings = []
        for i, (h, m) in enumerate([(4, 50), (5, 0), (5, 15), (5, 20)]):
            bookings.append(mk_booking(
                booking_id=200 + i,
                reference=f"TAG-DOX{i:05d}",
                dropoff_dt=datetime(2026, 6, 10, h, m),
                pickup_dt=datetime(2026, 7, 1, 14, 0),  # far future, out of target
            ))
        db = make_db(bookings=bookings)
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 10)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 10)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(4, 20), (
            f"Expected 04:20 (= 04:50 − 30 base, no pickup pair), got {s.start_time}"
        )
        assert s.end_time == time(7, 20), (
            f"Expected 07:20 (= 05:20 + 30 base + 90 for 3 missed pairs), got {s.end_time}"
        )


class TestRebuildSingleEventNoExtension:
    def test_happy_single_dropoff_uses_base_buffers_only(self):
        """Sanity: a single drop-off shift gets base buffers, no extension."""
        b = mk_booking(
            booking_id=1, reference="TAG-SINGLE001",
            dropoff_dt=datetime(2026, 6, 10, 8, 30),
            pickup_dt=datetime(2026, 7, 1, 14, 0),
        )
        db = make_db(bookings=[b])
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 10)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 10)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(8, 0)   # 8:30 - 30
        # 8:30 + 30 = 9:00 → 60 min duration, exactly at min_shift floor, no adjustment
        assert s.end_time == time(9, 0)


class TestRebuildPickupExtensionBoundaries:
    """The pickup start-shift formula is `arrival − 15 − 30·N` (locked 2026-05-12,
    where 15 is the pickup-led base — see PICKUP_LED_START_BUFFER_MINUTES).
    The two equivalent clock-time formulations agree; the DATE assignment is
    what these tests pin down.
    """

    def test_boundary_midday_no_wrap_either_side(self):
        """Mid-day arrivals 14:00/14:10/14:20 — no midnight crossing on either edge.
        2 missed pairs → start = 14:00 − 15 pickup-led base − 60 ext = 12:45;
        end = pickup_time(14:50) + 30 = 15:20. Shift wholly within target date."""
        bookings = []
        for i, (arr_h, arr_m) in enumerate([(14, 0), (14, 10), (14, 20)]):
            pt_total = arr_h * 60 + arr_m + 30
            pt_h, pt_m = (pt_total // 60) % 24, pt_total % 60
            bookings.append(mk_booking(
                booking_id=300 + i,
                reference=f"TAG-MID{i:05d}",
                dropoff_dt=datetime(2026, 6, 5, 8, 0),  # earlier, out of target
                pickup_dt=datetime(2026, 6, 17, pt_h, pt_m),
                flight_arrival_time=time(arr_h, arr_m),
            ))
        db = make_db(bookings=bookings)
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 17)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 17)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(12, 45)
        assert s.end_time == time(15, 20)
        assert s.end_date is None  # same-day shift

    def test_boundary_morning_wrap_start_lands_previous_day(self):
        """Morning arrivals 00:30/00:40/00:50 on June 17.
        2 missed pairs → start = 00:30 − 15 pickup-led base − 60 ext = 23:15
        on June 16 (previous day). End = pickup_time(01:20) + 30 = 01:50 on
        June 17. Shift spans midnight: starts on the day BEFORE the target."""
        bookings = []
        for i, (arr_h, arr_m) in enumerate([(0, 30), (0, 40), (0, 50)]):
            pt_total = arr_h * 60 + arr_m + 30  # no wrap, all stay on pickup_date
            pt_h, pt_m = pt_total // 60, pt_total % 60
            bookings.append(mk_booking(
                booking_id=400 + i,
                reference=f"TAG-MOR{i:05d}",
                dropoff_dt=datetime(2026, 6, 5, 8, 0),
                pickup_dt=datetime(2026, 6, 17, pt_h, pt_m),
                flight_arrival_time=time(arr_h, arr_m),
            ))
        db = make_db(bookings=bookings)
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 17)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        # Shift's start date is the previous day (16th) because the start
        # buffer pushed it across midnight. Cluster_start.date() is still 17th
        # (first event_time = arrival 00:30 on the 17th), so the rebuild for
        # target {17th} owns this cluster — but the materialised shift sits
        # on the 16th. Locking that semantic here.
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.date == date(2026, 6, 16)
        assert s.start_time == time(23, 15)
        assert s.end_date == date(2026, 6, 17)
        assert s.end_time == time(1, 50)

    def test_boundary_evening_wrap_end_lands_next_day(self):
        """Evening arrivals 23:20/23:30/23:40 — start same day, end wraps to next.
        Pickup-led base 15 + 60 ext for 2 missed pairs → 23:20 − 75 = 22:05.
        Locks the date semantics explicitly alongside the parallel test in
        TestRebuildAppliesPickupExtension."""
        bookings = []
        for i, (arr_h, arr_m) in enumerate([(23, 20), (23, 30), (23, 40)]):
            pt_total = arr_h * 60 + arr_m + 30
            pt_h, pt_m = (pt_total // 60) % 24, pt_total % 60
            pt_date = date(2026, 6, 17) if pt_total < 24 * 60 else date(2026, 6, 18)
            bookings.append(mk_booking(
                booking_id=500 + i,
                reference=f"TAG-EVE{i:05d}",
                dropoff_dt=datetime(2026, 6, 5, 8, 0),
                pickup_dt=datetime(pt_date.year, pt_date.month, pt_date.day, pt_h, pt_m),
                flight_arrival_time=time(arr_h, arr_m),
            ))
        db = make_db(bookings=bookings)
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 17)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.date == date(2026, 6, 17)
        assert s.start_time == time(22, 5)
        assert s.end_date == date(2026, 6, 18)
        assert s.end_time == time(0, 40)


class TestRebuildLooseDropoffsNoExtension:
    def test_happy_two_dropoffs_60min_apart_no_extension(self):
        """Drop-offs 60 min apart — within 190-min cluster threshold so they
        share a shift, but >30 min so no end extension."""
        b1 = mk_booking(
            booking_id=1, reference="TAG-LOOSE01",
            dropoff_dt=datetime(2026, 6, 10, 8, 0),
            pickup_dt=datetime(2026, 7, 1, 14, 0),
        )
        b2 = mk_booking(
            booking_id=2, reference="TAG-LOOSE02",
            dropoff_dt=datetime(2026, 6, 10, 9, 0),
            pickup_dt=datetime(2026, 7, 1, 14, 0),
        )
        db = make_db(bookings=[b1, b2])
        rebuild_auto_for_dates(
            db,
            {date(2026, 6, 10)},
            mk_settings(start_buffer_minutes=30, end_buffer_minutes=30),
        )
        from db_models import RosterShift
        new_shifts = [a for a in db._added if isinstance(a, RosterShift) and a.date == date(2026, 6, 10)]
        assert len(new_shifts) == 1
        s = new_shifts[0]
        assert s.start_time == time(7, 30)   # 8:00 - 30
        assert s.end_time == time(9, 30)     # 9:00 + 30, no extension
