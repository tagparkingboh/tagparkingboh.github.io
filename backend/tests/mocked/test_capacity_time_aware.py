"""
HUEB tests for the time-aware capacity helpers (CAPACITY_GATE_TIME_AWARE):

  db_service.peak_concurrent_occupancy
  db_service.find_overcapacity_moment_in_stay
  db_service.find_overcapacity_moment_in_stay_locked
  db_service.is_capacity_gate_time_aware

Background (2026-07-02): the per-day gate counts any booking TOUCHING a
date as +1, which overcounts on turnover days — prod 2026-07-04 had 80
bookings touching the day (= cap → "we're full") but only 68 cars
concurrently present. These helpers gate on peak CONCURRENT cars instead.

Boundary dimensions pinned here (per SPEC testing standards):
  - same-instant tie rule: a pickup at T frees the space BEFORE a dropoff
    at T claims one (departures sort before arrivals) — the REVERSE of the
    old check-slot sweep;
  - cap boundaries at cap-1 / cap / cap+1 pre-existing concurrent cars;
  - midnight zero-delta probes: date-effective cap changes are enforced
    at day boundaries even with no booking event on them;
  - status set: CONFIRMED+COMPLETED+REFUNDED (car still on site), PENDING
    and CANCELLED excluded — asserted on the real SQLAlchemy filter clause;
  - missing times worst-cased to 00:00 (drop) / 23:59 (pick);
  - DST (Europe/London, 2026-10-25 clock change): naive wall-clock sweep
    counts each car exactly once across the 01:00-02:00 repeated hour.

Helper-level tests use MagicMock sessions (HUEB completeness); endpoint
wiring is covered in test_capacity_check_slot_time_aware.py /
test_create_intent_time_aware.py / webhook tests, which are
TestClient-based and count toward coverage per project convention.
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import db_service
from db_service import (
    TIME_AWARE_OCCUPYING_STATUSES,
    find_overcapacity_moment_in_stay,
    find_overcapacity_moment_in_stay_locked,
    is_capacity_gate_time_aware,
    peak_concurrent_occupancy,
)
from db_models import BookingStatus


# =============================================================================
# Helpers
# =============================================================================

def _b(dd, dt, pd, pt, id=1, status=BookingStatus.CONFIRMED):
    """Booking-shaped namespace with the fields the sweep reads."""
    return SimpleNamespace(
        id=id,
        dropoff_date=dd,
        dropoff_time=dt,
        pickup_date=pd,
        pickup_time=pt,
        status=status,
    )


def _mock_db(rows):
    """MagicMock session: query().filter(...).all() → rows. The helper may
    chain .filter() once (status+dates) or twice (exclude_booking_id), and
    exclude_staging_e2e_capacity_bookings may add another — make the chain
    self-returning so any depth lands on the same row list."""
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.all.return_value = list(rows)
    db.query.return_value = chain
    return db


D = date(2026, 7, 4)  # prod incident day: 80 touching / 68 concurrent


# =============================================================================
# Flag parse
# =============================================================================

class TestFlagParse:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", " yes ", "on"])
    def test_H_truthy_values(self, monkeypatch, raw):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", raw)
        assert is_capacity_gate_time_aware() is True

    @pytest.mark.parametrize("raw", ["", "0", "false", "off", "no", "banana"])
    def test_U_falsy_values(self, monkeypatch, raw):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", raw)
        assert is_capacity_gate_time_aware() is False

    def test_B_unset_is_off(self, monkeypatch):
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        assert is_capacity_gate_time_aware() is False


# =============================================================================
# Same-instant tie rule (matrix #1): departures free space before arrivals
# =============================================================================

class TestSameInstantTieRule:
    """Existing car picked up at 16:00; another existing car dropped off
    around 16:00. Window covers the whole day. t-ε / t / t+ε on the
    arrival side of the boundary."""

    def _peak_with_arrival_at(self, arrival):
        rows = [
            _b(D, time(9, 0), D, time(16, 0), id=1),           # leaves 16:00
            _b(D, arrival, D + timedelta(days=1), time(10, 0), id=2),
        ]
        return peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(D, time(0, 0)),
            window_end=datetime.combine(D + timedelta(days=1), time(23, 59)),
        )

    def test_B_arrival_one_minute_before_pickup_overlaps(self):
        # 15:59 arrival overlaps the 16:00 departure → both present at once.
        assert self._peak_with_arrival_at(time(15, 59)) == 2

    def test_B_arrival_at_exact_pickup_instant_swaps(self):
        # 16:00 arrival: departure (-1) sorts before arrival (+1) at the
        # same instant → back-to-back swap, never concurrent.
        assert self._peak_with_arrival_at(time(16, 0)) == 1

    def test_B_arrival_one_minute_after_pickup_no_overlap(self):
        assert self._peak_with_arrival_at(time(16, 1)) == 1

    def test_H_full_lot_swap_at_cap_is_permitted_by_moment_gate(self):
        """cap cars all leave at 12:00; cap fresh cars arrive at 12:00 —
        departures-first means concurrency never exceeds cap, so a gate
        with cap+? … here we assert peak == cap, not 2×cap."""
        cap = 5
        rows = (
            [_b(D, time(8, 0), D, time(12, 0), id=i) for i in range(cap)]
            + [_b(D, time(12, 0), D, time(20, 0), id=100 + i) for i in range(cap)]
        )
        peak = peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(D, time(0, 0)),
            window_end=datetime.combine(D, time(23, 59)),
        )
        assert peak == cap


# =============================================================================
# Cap boundaries (matrix #3): peak+1 vs cap at cap-1 / cap / cap+1
# =============================================================================

class TestCapBoundaries:
    def _gate(self, n_existing, cap):
        rows = [
            _b(D, time(9, 0), D + timedelta(days=1), time(12, 0), id=i)
            for i in range(n_existing)
        ]
        return find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(10, 0),
            pickup_time=time(10, 0),
            cap=cap,
        )

    def test_B_cap_minus_one_existing_allowed(self):
        # 79 concurrent + this customer = 80 = cap → allowed.
        assert self._gate(79, 80) is None

    def test_B_cap_existing_rejected(self):
        # 80 concurrent + this customer = 81 > 80 → rejected on day one.
        offending = self._gate(80, 80)
        assert offending == (D, 80)

    def test_B_cap_plus_one_existing_rejected(self):
        # Early-exit semantics: the sweep returns at the FIRST moment the
        # check trips (current=80, 80+1>80), so the reported count is 80
        # even though 81 cars would eventually be concurrent. The per-day
        # gate reports the day's full count instead — callers only rely on
        # the day + "is not None", which unpack_capacity_offending preserves.
        offending = self._gate(81, 80)
        assert offending == (D, 80)

    def test_H_zero_bookings_allowed(self):
        assert self._gate(0, 80) is None


# =============================================================================
# The 2026-07-04 prod shape (matrix #7b): turnover day passes
# =============================================================================

class TestJulyFourthTurnoverShape:
    """cap 80; 68 cars parked straight through + 10 leaving in the morning.
    Touch-count = 78+customer's overlap patterns pushed the per-day gate to
    reject; the moment gate must pass an afternoon arrival."""

    def _rows(self):
        overnight = [
            _b(D - timedelta(days=2), time(9, 0), D + timedelta(days=3), time(12, 0), id=i)
            for i in range(68)
        ]
        leavers = [
            _b(D - timedelta(days=1), time(9, 0), D, time(9, 30 // 10 + 8), id=200 + i)
            for i in range(10)
        ]
        # give the leavers explicit morning pickup times 08:00-09:30
        for idx, row in enumerate(leavers):
            row.pickup_time = time(8 + (idx % 2), (idx * 7) % 60)
        return overnight + leavers

    def test_H_afternoon_arrival_passes_moment_gate(self):
        offending = find_overcapacity_moment_in_stay(
            _mock_db(self._rows()),
            dropoff_date=D,
            pickup_date=D + timedelta(days=2),
            dropoff_time=time(15, 0),   # after the 10 morning departures
            pickup_time=time(11, 0),
            cap=80,
        )
        assert offending is None

    def test_U_same_shape_rejects_per_day_gate(self):
        """Control: the old per-day gate rejects this exact shape (78
        touching + customer = 79 ≤ 80 actually passes at 78 — push to 80
        touching with 12 leavers to mirror prod's 80)."""
        rows = self._rows() + [
            _b(D - timedelta(days=1), time(9, 0), D, time(9, 0), id=300 + i)
            for i in range(2)
        ]
        offending = db_service.find_overcapacity_day_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=2),
            cap=80,
        )
        assert offending is not None
        assert offending[0] == D

    def test_U_morning_arrival_before_departures_rejected_at_cap(self):
        """Same lot, but the customer arrives 07:00 BEFORE the 10 morning
        departures: 78 concurrent + 1 = 79 ≤ 80 passes; tighten the lot to
        79 pre-departure cars to hit the boundary."""
        rows = self._rows() + [
            _b(D - timedelta(days=1), time(9, 0), D, time(10, 0), id=400),
            _b(D - timedelta(days=1), time(9, 0), D, time(10, 0), id=401),
        ]  # 70 + 10 + 2 = 80 present pre-departure... but only until 08:00
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(7, 0),
            pickup_time=time(11, 0),
            cap=80,
        )
        assert offending == (D, 80)


# =============================================================================
# Mid-stay full day still rejects (matrix #7a — TAG-MSH89023 shape)
# =============================================================================

class TestMidStayFullStillRejects:
    def test_U_middle_day_saturated_by_through_cars_rejects(self):
        """Endpoints clear, but every space is occupied by cars parked
        straight through day 2 of a 3-day stay → time-aware gate must
        still reject, pointing at day 2 (the 2026-05-18 leak must not
        reopen under the new gate)."""
        d1, d2, d3 = D, D + timedelta(days=1), D + timedelta(days=2)
        rows = [
            _b(d2 - timedelta(days=1), time(9, 0), d2 + timedelta(days=1), time(12, 0), id=i)
            for i in range(80)
        ]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=d1,
            pickup_date=d3,
            dropoff_time=time(14, 0),
            pickup_time=time(10, 0),
            cap=80,
        )
        assert offending is not None
        # The 80 through-cars enter the customer's window at their real
        # arrival (day before d2) truncated to window start (d1 14:00) —
        # concurrency saturates from the moment they're all in.
        assert offending[0] in (d1, d2)


# =============================================================================
# Midnight zero-delta probes (matrix #4): date-effective cap changes
# =============================================================================

class TestMidnightCapChangeProbes:
    """One car parked across the whole stay; cap drops from 80 to 1 on day
    two. No booking event lands between the events — only the midnight
    probe can catch the cap change."""

    def _cap_by_date(self, d1_cap, d2_cap):
        return {
            D.isoformat(): {"online_spaces": d1_cap},
            (D + timedelta(days=1)).isoformat(): {"online_spaces": d2_cap},
        }

    def test_U_cap_drop_at_midnight_rejects_with_no_events(self):
        rows = [_b(D - timedelta(days=1), time(9, 0), D + timedelta(days=5), time(12, 0), id=1)]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(14, 0),
            pickup_time=time(10, 0),
            cap_by_date=self._cap_by_date(80, 1),
        )
        # current=1 (the through car) + this customer = 2 > 1 → rejected on
        # day two, discovered by the midnight probe.
        assert offending == (D + timedelta(days=1), 1, 1)

    def test_H_cap_rise_at_midnight_passes(self):
        rows = [_b(D - timedelta(days=1), time(9, 0), D + timedelta(days=5), time(12, 0), id=1)]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(14, 0),
            pickup_time=time(10, 0),
            cap_by_date=self._cap_by_date(2, 80),
        )
        assert offending is None

    def test_B_cap_drop_on_dropoff_day_checked_at_window_start(self):
        """The window-start probe (not just midnights) enforces day one's
        cap before any event."""
        rows = [_b(D - timedelta(days=1), time(9, 0), D + timedelta(days=5), time(12, 0), id=1)]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(14, 0),
            pickup_time=time(10, 0),
            cap_by_date=self._cap_by_date(1, 80),
        )
        assert offending == (D, 1, 1)


# =============================================================================
# Status set (matrix #2): filter clause carries CONFIRMED+COMPLETED+REFUNDED
# =============================================================================

class TestStatusSet:
    def test_H_refunded_in_default_status_tuple(self):
        assert BookingStatus.REFUNDED in TIME_AWARE_OCCUPYING_STATUSES
        assert BookingStatus.CONFIRMED in TIME_AWARE_OCCUPYING_STATUSES
        assert BookingStatus.COMPLETED in TIME_AWARE_OCCUPYING_STATUSES
        assert BookingStatus.PENDING not in TIME_AWARE_OCCUPYING_STATUSES
        assert BookingStatus.CANCELLED not in TIME_AWARE_OCCUPYING_STATUSES

    def test_H_sweep_filter_clause_uses_default_statuses(self):
        """Capture the real SQLAlchemy in_() values the sweep filters on —
        stronger than row-seeding, which can't observe the clause (the
        FakeQuery convention ignores filters)."""
        captured = {}

        class _Spy:
            def filter(self, *args, **_kw):
                for a in args:
                    # BinaryExpression for Booking.status.in_([...]) exposes
                    # the literal list on .right.value.
                    try:
                        vals = a.right.value
                    except AttributeError:
                        continue
                    if isinstance(vals, (list, tuple)) and vals and hasattr(vals[0], "name"):
                        captured["statuses"] = list(vals)
                return self

            def all(self):
                return []

        db = MagicMock()
        db.query.return_value = _Spy()
        peak_concurrent_occupancy(
            db,
            window_start=datetime.combine(D, time(0, 0)),
            window_end=datetime.combine(D, time(23, 59)),
        )
        assert set(captured["statuses"]) == {
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.REFUNDED,
        }

    def test_E_refunded_car_still_counts_toward_peak(self):
        """A REFUNDED row that survives the status filter occupies a space
        exactly like a CONFIRMED one."""
        rows = [
            _b(D, time(9, 0), D + timedelta(days=1), time(12, 0), id=1,
               status=BookingStatus.REFUNDED),
        ]
        peak = peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(D, time(10, 0)),
            window_end=datetime.combine(D, time(20, 0)),
        )
        assert peak == 1


# =============================================================================
# Missing times worst-cased (dates-only degrade, matrix #1/#8 support)
# =============================================================================

class TestMissingTimesWorstCase:
    def test_E_null_times_degrade_to_full_day_occupancy(self):
        """No times on the existing booking → treated as 00:00→23:59, so it
        overlaps any window on its dates."""
        rows = [_b(D, None, D, None, id=1)]
        peak = peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(D, time(0, 5)),
            window_end=datetime.combine(D, time(23, 50)),
        )
        assert peak == 1

    def test_E_gate_without_times_matches_per_day_conservatism(self):
        """Dates-only call: 80 cars touching the day (no times) must still
        reject at cap 80 — the moment gate can't be LOOSER than per-day
        when it has no time information."""
        rows = [_b(D, None, D + timedelta(days=1), None, id=i) for i in range(80)]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            cap=80,
        )
        assert offending is not None


# =============================================================================
# Overnight rollover (matrix #8): exit past midnight extends the window
# =============================================================================

class TestOvernightRollover:
    def test_B_post_midnight_exit_checks_the_extra_day(self):
        """Customer exit rolls to 00:20 next day (arrival 23:50 + 30).
        A cap-saturating fleet parked only on that extra day must reject."""
        extra_day = D + timedelta(days=2)
        rows = [
            _b(extra_day, time(0, 0), extra_day, time(6, 0), id=i)
            for i in range(80)
        ]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=extra_day,          # exit date already rolled
            dropoff_time=time(14, 0),
            pickup_time=time(0, 20),
            cap=80,
        )
        assert offending == (extra_day, 80)

    def test_H_exit_just_before_midnight_ignores_next_day(self):
        next_day = D + timedelta(days=2)
        rows = [
            _b(next_day, time(0, 0), next_day, time(6, 0), id=i)
            for i in range(80)
        ]
        offending = find_overcapacity_moment_in_stay(
            _mock_db(rows),
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(14, 0),
            pickup_time=time(23, 59),
            cap=80,
        )
        assert offending is None


# =============================================================================
# DST (matrix #9): Europe/London 2026-10-25 clock change, naive wall-clock
# =============================================================================

class TestDstOctoberClockChange:
    DST_DAY = date(2026, 10, 25)  # clocks fall back 02:00→01:00 UK

    def test_E_stay_spanning_clock_change_counts_each_car_once(self):
        """The sweep is naive wall-clock: a car parked across the 01:00-
        02:00 repeated hour contributes exactly one +1/-1 pair — no
        double-count, no gap."""
        rows = [
            _b(self.DST_DAY - timedelta(days=1), time(9, 0),
               self.DST_DAY, time(12, 0), id=1),
        ]
        peak = peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(self.DST_DAY - timedelta(days=1), time(22, 0)),
            window_end=datetime.combine(self.DST_DAY, time(3, 0)),
        )
        assert peak == 1

    def test_B_pickup_inside_repeated_hour_frees_space_once(self):
        rows = [
            _b(self.DST_DAY - timedelta(days=1), time(9, 0),
               self.DST_DAY, time(1, 30), id=1),          # leaves 01:30
            _b(self.DST_DAY, time(1, 30), self.DST_DAY, time(9, 0), id=2),
        ]
        peak = peak_concurrent_occupancy(
            _mock_db(rows),
            window_start=datetime.combine(self.DST_DAY - timedelta(days=1), time(22, 0)),
            window_end=datetime.combine(self.DST_DAY, time(10, 0)),
        )
        assert peak == 1  # same-instant swap inside the DST hour


# =============================================================================
# Locked variant (matrix #6 helper level)
# =============================================================================

class TestMomentGateLocked:
    def test_H_acquires_same_ascending_lock_keys_as_per_day_variant(self):
        d1 = date(2026, 7, 10)
        d3 = date(2026, 7, 12)
        db = _mock_db([])
        result = find_overcapacity_moment_in_stay_locked(
            db,
            dropoff_date=d1,
            pickup_date=d3,
            dropoff_time=time(14, 0),
            pickup_time=time(10, 0),
            cap=10,
        )
        assert result is None
        keys = [c.args[1]["k"] for c in db.execute.call_args_list]
        assert keys == [
            "booking_capacity:2026-07-10",
            "booking_capacity:2026-07-11",
            "booking_capacity:2026-07-12",
        ]
        for c in db.execute.call_args_list:
            assert "pg_advisory_xact_lock" in str(c.args[0])

    def test_U_over_cap_under_lock_returns_offending(self):
        d1 = date(2026, 7, 10)
        rows = [_b(d1, time(9, 0), d1 + timedelta(days=1), time(12, 0), id=i) for i in range(10)]
        db = _mock_db(rows)
        offending = find_overcapacity_moment_in_stay_locked(
            db,
            dropoff_date=d1,
            pickup_date=d1 + timedelta(days=1),
            dropoff_time=time(10, 0),
            pickup_time=time(10, 0),
            cap=10,
        )
        assert offending == (d1, 10)
        assert db.execute.call_count == 2  # one lock per stay date

    def test_B_inverted_dates_acquire_no_locks_and_reject(self):
        """Inverted windows fail CLOSED (reviewer fix 2026-07-02): a
        zero/negative-length stay can never fit — it must return an
        offending tuple for the dropoff date, still without taking locks."""
        db = _mock_db([])
        result = find_overcapacity_moment_in_stay_locked(
            db,
            dropoff_date=date(2026, 7, 12),
            pickup_date=date(2026, 7, 10),
            cap=10,
        )
        assert result == (date(2026, 7, 12), 0)
        assert db.execute.call_count == 0


# =============================================================================
# exclude_booking_id pass-through
# =============================================================================

class TestExcludeBookingId:
    def test_H_exclude_id_reaches_the_query_filter(self):
        """The pending-booking exclusion must survive into the sweep's
        query — capture the != clause value."""
        captured = {}

        class _Spy:
            def filter(self, *args, **_kw):
                for a in args:
                    try:
                        if a.left.key == "id":
                            captured["excluded"] = a.right.value
                    except AttributeError:
                        continue
                return self

            def all(self):
                return []

        db = MagicMock()
        db.query.return_value = _Spy()
        find_overcapacity_moment_in_stay(
            db,
            dropoff_date=D,
            pickup_date=D + timedelta(days=1),
            dropoff_time=time(10, 0),
            pickup_time=time(10, 0),
            cap=80,
            exclude_booking_id=4242,
        )
        assert captured.get("excluded") == 4242
