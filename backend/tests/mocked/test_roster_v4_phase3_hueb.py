"""
Roster v4 Phase 3 (2026-07-22) — reconcile-in-place + batch-aware trim.

Spec: assigned shifts are sticky, not frozen — new bookings link into them
and reshape the window in place (within template window bounds) instead of
duplicating or destroying. Locked = fully frozen. The 20:00 T-1 trim sizes
shifts with the cluster engine's rules (tight pairs, pickup-led buffers) and
fleet twins sync in lockstep with their window's jockey shift.

Real in-memory ORM rows; engine functions exercised directly.
"""
from datetime import date as date_type, datetime, time, timedelta, timezone

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_roster import (
    _rebuild_window_auto_for_dates,
    trim_window_auto_shifts_for_date,
)
from db_models import (
    Booking,
    BookingStatus,
    RosterShift,
    RosterWindowTemplate,
    ShiftBookingLink,
    ShiftStatus,
    ShiftType,
)
from roster_planner import (
    Event,
    PlannerSettings,
    UK_TZ,
    compute_cluster_shift_window,
    group_events_by_gap,
)

V4_FROM = date_type(2026, 8, 10)
V4_DAY = date_type(2026, 8, 12)

V4_WINDOWS = [
    ("early", time(3, 30), time(10, 30)),
    ("day", time(10, 30), time(18, 30)),
    ("late", time(18, 30), time(1, 30)),
]


@pytest.fixture
def seeded(db_session):
    for profile in ("weekday", "weekend"):
        for sort, (label, start, end) in enumerate(V4_WINDOWS):
            db_session.add(RosterWindowTemplate(
                profile=profile, label=label, start_time=start, end_time=end,
                sort_order=sort, is_active=True, effective_from=V4_FROM,
            ))
    db_session.commit()
    return db_session


def _settings():
    return PlannerSettings.from_kv({})


def _booking(db, *, dropoff_time_, dropoff=V4_DAY, ref=None):
    booking = Booking(
        reference=ref or f"TAG-TP3{db.query(Booking).count():05d}",
        customer_id=1,
        vehicle_id=1,
        package="full",
        status=BookingStatus.CONFIRMED,
        dropoff_date=dropoff,
        dropoff_time=dropoff_time_,
        pickup_date=dropoff + timedelta(days=7),
        pickup_time=time(12, 0),
    )
    db.add(booking)
    db.commit()
    return booking


def _shift(db, *, start, end, staff_id=None, driver_type="jockey", locked=False,
           date_=V4_DAY, admin_shaped_at=None, bookings=()):
    shift = RosterShift(
        staff_id=staff_id,
        assigned_source="admin" if staff_id else None,
        date=date_,
        start_time=start,
        end_time=end,
        shift_type=ShiftType.MORNING,
        status=ShiftStatus.SCHEDULED,
        created_source="auto",
        intended_driver_type=driver_type,
        locked=locked,
        admin_shaped_at=admin_shaped_at,
    )
    db.add(shift)
    db.commit()
    for b in bookings:
        db.add(ShiftBookingLink(shift_id=shift.id, booking_id=b.id))
    db.commit()
    return shift


class TestReconcileInPlaceHUEB:

    def test_H_new_booking_extends_assigned_trimmed_shift(self, seeded):
        """The core sticky behaviour: an assigned shift trimmed to 05:00-07:00
        gains a 09:00 booking — same row extends, staffing intact, no new
        jockey shift, link lands on it."""
        assigned = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=16)
        booking = _booking(seeded, dropoff_time_=time(9, 0))

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        seeded.refresh(assigned)
        assert summary["reconciled"] >= 1
        assert summary["created"] == 0
        assert assigned.staff_id == 16
        assert assigned.start_time == time(5, 0)          # start untouched
        assert assigned.end_time == time(9, 30)           # 09:00 + 30min coverage
        links = seeded.query(ShiftBookingLink).filter_by(shift_id=assigned.id).all()
        assert {l.booking_id for l in links} == {booking.id}
        jockeys = seeded.query(RosterShift).filter_by(intended_driver_type="jockey").count()
        assert jockeys == 1

    def test_B_extension_clamped_to_window_bound(self, seeded):
        """A 10:20 booking's coverage tail (10:50) exceeds the early window —
        the extension stops exactly at 10:30."""
        assigned = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=16)
        _booking(seeded, dropoff_time_=time(10, 20))

        _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        seeded.refresh(assigned)
        assert assigned.end_time == time(10, 30)

    def test_H_booking_inside_span_links_without_reshape(self, seeded):
        assigned = _shift(seeded, start=time(4, 0), end=time(10, 0), staff_id=16)
        booking = _booking(seeded, dropoff_time_=time(6, 0))

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        seeded.refresh(assigned)
        assert summary["reconciled"] == 0                 # nothing to reshape
        assert summary["links_added"] == 1
        assert (assigned.start_time, assigned.end_time) == (time(4, 0), time(10, 0))
        links = seeded.query(ShiftBookingLink).filter_by(shift_id=assigned.id).all()
        assert {l.booking_id for l in links} == {booking.id}

    def test_H_idempotent_second_rebuild_changes_nothing(self, seeded):
        assigned = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=16)
        _booking(seeded, dropoff_time_=time(9, 0))

        _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())
        second = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        assert second["reconciled"] == 0
        assert second["links_added"] == 0
        assert second["created"] == 0

    def test_U_locked_shift_never_reshaped(self, seeded):
        """Locked = frozen: demand outside its span spawns parallel coverage
        instead of touching it."""
        locked = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=16, locked=True)
        _booking(seeded, dropoff_time_=time(9, 0))

        summary = _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        seeded.refresh(locked)
        assert (locked.start_time, locked.end_time) == (time(5, 0), time(7, 0))
        assert summary["reconciled"] == 0
        assert summary["created"] == 1                    # parallel unassigned cover

    def test_H_assigned_fleet_twin_reconciles_too(self, seeded):
        jockey = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=16)
        fleet = _shift(seeded, start=time(5, 0), end=time(7, 0), staff_id=14, driver_type="fleet")
        _booking(seeded, dropoff_time_=time(9, 0))

        _rebuild_window_auto_for_dates(seeded, [V4_DAY], _settings())

        seeded.refresh(jockey)
        seeded.refresh(fleet)
        assert jockey.end_time == time(9, 30)
        assert fleet.end_time == time(9, 30)              # twins stay identical
        # Carbon-copy: the reconciled twin mirrors the jockey's new booking.
        jockey_links = {l.booking_id for l in seeded.query(ShiftBookingLink).filter_by(shift_id=jockey.id)}
        fleet_links = {l.booking_id for l in seeded.query(ShiftBookingLink).filter_by(shift_id=fleet.id)}
        assert fleet_links == jockey_links and jockey_links


class TestBatchAwareTrimHUEB:

    def _expected_span(self, events_spec, settings):
        """Ground truth straight from the cluster engine."""
        events = [
            Event(
                booking_id=i, booking_reference=f"REF{i}", event_type=et,
                event_time=datetime.combine(V4_DAY, t).replace(tzinfo=UK_TZ),
                end_anchor_time=datetime.combine(V4_DAY, t2).replace(tzinfo=UK_TZ),
            )
            for i, (et, t, t2) in enumerate(events_spec)
        ]
        clusters = group_events_by_gap(
            events,
            gap_max_minutes=settings.gap_max_minutes,
            mixed_gap_max_minutes=settings.mixed_gap_max_minutes,
        )
        starts, ends = [], []
        for c in clusters:
            s, e = compute_cluster_shift_window(
                c,
                start_buffer_minutes=settings.start_buffer_minutes,
                end_buffer_minutes=settings.end_buffer_minutes,
                min_shift_minutes=settings.min_shift_minutes,
            )
            starts.append(s.replace(tzinfo=None))
            ends.append(e.replace(tzinfo=None))
        return min(starts), max(ends)

    def test_H_tight_dropoff_batch_gets_cluster_sizing(self, seeded):
        """Three drop-offs 10 minutes apart: the trim must match the cluster
        engine's window (incl. tight-pair extension) — not flat last+30."""
        settings = _settings()
        bookings = [
            _booking(seeded, dropoff_time_=t)
            for t in (time(5, 50), time(6, 0), time(6, 10))
        ]
        shift = _shift(seeded, start=time(3, 30), end=time(10, 30), bookings=bookings)

        result = trim_window_auto_shifts_for_date(seeded, V4_DAY, settings)

        seeded.refresh(shift)
        exp_start, exp_end = self._expected_span(
            [("drop_off", t, t) for t in (time(5, 50), time(6, 0), time(6, 10))],
            settings,
        )
        assert result["trimmed"] == 1
        assert shift.start_time == max(time(3, 30), exp_start.time())
        assert shift.end_time == exp_end.time()
        # the whole point: batch sizing holds the driver past flat last+30
        assert exp_end.time() > time(6, 40)

    def test_H_fleet_twin_trims_in_lockstep(self, seeded):
        settings = _settings()
        bookings = [_booking(seeded, dropoff_time_=time(6, 0))]
        jockey = _shift(seeded, start=time(3, 30), end=time(10, 30), bookings=bookings)
        fleet = _shift(seeded, start=time(3, 30), end=time(10, 30), driver_type="fleet")

        result = trim_window_auto_shifts_for_date(seeded, V4_DAY, settings)

        seeded.refresh(jockey)
        seeded.refresh(fleet)
        assert result["trimmed"] == 1
        assert result["twins_synced"] == 1
        assert (fleet.start_time, fleet.end_time) == (jockey.start_time, jockey.end_time)

    def test_U_locked_twin_not_synced(self, seeded):
        settings = _settings()
        bookings = [_booking(seeded, dropoff_time_=time(6, 0))]
        _shift(seeded, start=time(3, 30), end=time(10, 30), bookings=bookings)
        locked_fleet = _shift(seeded, start=time(3, 30), end=time(10, 30),
                              driver_type="fleet", locked=True)

        result = trim_window_auto_shifts_for_date(seeded, V4_DAY, settings)

        seeded.refresh(locked_fleet)
        assert result["twins_synced"] == 0
        assert (locked_fleet.start_time, locked_fleet.end_time) == (time(3, 30), time(10, 30))

    def test_B_trim_never_expands(self, seeded):
        """A shift already tighter than the cluster window stays put."""
        settings = _settings()
        bookings = [_booking(seeded, dropoff_time_=time(6, 0))]
        shift = _shift(seeded, start=time(5, 55), end=time(6, 20), bookings=bookings)

        result = trim_window_auto_shifts_for_date(seeded, V4_DAY, settings)

        seeded.refresh(shift)
        assert result["trimmed"] == 0
        assert (shift.start_time, shift.end_time) == (time(5, 55), time(6, 20))
