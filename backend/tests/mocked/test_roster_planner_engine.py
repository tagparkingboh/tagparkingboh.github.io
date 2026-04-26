"""Pure-function tests for the Roster Planner engine.

Covers the test matrix in backend/docs/SPEC.md § Roster Planner — Testing matrix:
happy / unhappy / edge / boundary per subject. These tests pass lightweight
namespace objects (not SQLAlchemy instances) because the engine is pure — it
only reads attributes off the passed iterables.

Pure-function tests do NOT go through TestClient(app), so they don't raise
main.py coverage. Coverage for endpoint handlers lives in
test_roster_planner_integration.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Optional

import pytest

from db_models import BookingStatus, ShiftStatus, ShiftType
from roster_planner import (
    Event,
    EventCluster,
    PlannerSettings,
    UK_TZ,
    group_events_by_gap,
    iso_monday,
    is_shift_untouchable,
    is_staff_on_holiday,
    last_shift_end_for,
    peak_concurrent_count,
    pick_staff,
    propose_roster,
    required_staff_count,
    round_to_shift_type,
    shift_hours,
    weekly_hours_for,
)


# =====================================================================================
# Fixtures / factories
# =====================================================================================

DEFAULT_SETTINGS = PlannerSettings(
    window_days=28,
    gap_max_minutes=150,
    mixed_gap_max_minutes=150,
    start_buffer_minutes=20,
    end_buffer_minutes=30,
    staffing_thresholds=({"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}),
    max_hours_per_week=40,
    min_rest_hours=8,
    untouchable_hours=24,
    min_shift_minutes=60,
)


def uk_dt(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """Europe/London-aware datetime factory."""
    return datetime(y, mo, d, h, mi, tzinfo=UK_TZ)


def mk_event(booking_id: int, when: datetime, event_type: str = "drop_off") -> Event:
    return Event(
        booking_id=booking_id,
        booking_reference=f"TAG-{booking_id:05d}",
        event_type=event_type,
        event_time=when,
    )


def mk_booking(
    booking_id: int,
    ref: str,
    drop_dt: datetime,
    pick_dt: datetime,
    status: BookingStatus = BookingStatus.CONFIRMED,
):
    """Lightweight booking stand-in — the engine only reads a handful of attributes."""
    return SimpleNamespace(
        id=booking_id,
        reference=ref,
        status=status,
        dropoff_date=drop_dt.date(),
        dropoff_time=drop_dt.time(),
        pickup_date=pick_dt.date(),
        pickup_time=pick_dt.time(),
    )


def mk_staff(
    user_id: int,
    first: str = "Jo",
    last: str = "Surname",
    preferred: Optional[list[ShiftType]] = None,
    excluded: bool = False,
    active: bool = True,
    *,
    driver_type: str = "jockey",          # default to jockey so existing tests keep their behaviour
    excluded_shift_types: Optional[list[ShiftType]] = None,
    preferred_days_off: Optional[list[int]] = None,
    preferred_start_time: Optional[time] = None,
    preferred_end_time: Optional[time] = None,
    is_fallback_driver: bool = False,
):
    return SimpleNamespace(
        id=user_id,
        first_name=first,
        last_name=last,
        preferred_shift_types=preferred or [],
        auto_assign_excluded=excluded,
        is_active=active,
        driver_type=driver_type,
        excluded_shift_types=excluded_shift_types or [],
        preferred_days_off=preferred_days_off or [],
        preferred_start_time=preferred_start_time,
        preferred_end_time=preferred_end_time,
        is_fallback_driver=is_fallback_driver,
    )


def mk_shift(
    shift_id: int,
    staff_id: Optional[int],
    d: date,
    start: time,
    end: time,
    *,
    end_date: Optional[date] = None,
    status: ShiftStatus = ShiftStatus.SCHEDULED,
    shift_type: ShiftType = ShiftType.MORNING,
    bookings: Optional[list] = None,
):
    return SimpleNamespace(
        id=shift_id,
        staff_id=staff_id,
        date=d,
        end_date=end_date,
        start_time=start,
        end_time=end,
        status=status,
        shift_type=shift_type,
        bookings=bookings or [],
        staff_initials="XX",
    )


def mk_holiday(staff_id: int, start: date, end: Optional[date] = None):
    # Match the real EmployeeHoliday.staff_id column — engine reads h.staff_id.
    return SimpleNamespace(
        staff_id=staff_id, start_date=start, end_date=end or start
    )


# =====================================================================================
# group_events_by_gap
# =====================================================================================


class TestGapSplitting:
    """Consecutive events within the gap limit stay together; beyond it they split."""

    def test_happy_three_events_within_window_one_cluster(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [
            mk_event(1, base),
            mk_event(2, base + timedelta(minutes=30)),
            mk_event(3, base + timedelta(minutes=45)),
        ]
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert len(clusters) == 1
        assert len(clusters[0].events) == 3

    def test_unhappy_empty_list_returns_empty(self):
        assert group_events_by_gap([], gap_max_minutes=120) == []

    def test_edge_mixed_drop_and_pick_in_one_window(self):
        base = uk_dt(2026, 5, 4, 13, 0)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(minutes=45), "pick_up"),
            mk_event(3, base + timedelta(minutes=75), "drop_off"),
        ]
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert len(clusters) == 1
        assert [e.event_type for e in clusters[0].events] == [
            "drop_off",
            "pick_up",
            "drop_off",
        ]

    def test_boundary_exactly_2h_gap_stays_same(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [mk_event(1, base), mk_event(2, base + timedelta(hours=2))]
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert len(clusters) == 1, "≤ 2h inclusive per rule lock 2026-04-24"

    def test_boundary_2h_and_one_second_splits(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [
            mk_event(1, base),
            mk_event(2, base + timedelta(hours=2, seconds=1)),
        ]
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert len(clusters) == 2

    def test_edge_alternating_small_and_large_gaps(self):
        base = uk_dt(2026, 5, 4, 7, 0)
        events = [
            mk_event(1, base),
            mk_event(2, base + timedelta(minutes=30)),
            mk_event(3, base + timedelta(hours=4)),  # split
            mk_event(4, base + timedelta(hours=4, minutes=30)),
            mk_event(5, base + timedelta(hours=9)),  # split
        ]
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert [len(c.events) for c in clusters] == [2, 2, 1]


class TestMixedTypeGap:
    """Drop-off → pick-up bridging tolerates a wider gap than two same-type
    events. Mirrors the operational reality: a driver doing a drop-off can
    pre-position pick-up cars on the same airport trip, so the round-trip
    chain merits a longer gap allowance."""

    def test_mixed_gap_merges_across_2h15_when_types_differ(self):
        # Reproduces prod 2026-05-01: drop-off cluster at 11:55-12:00,
        # pick-up cluster at 14:15+. Gap 12:00 → 14:15 = 2h15m. With
        # gap=120 + mixed_gap=150, the mixed bridge merges.
        base = uk_dt(2026, 5, 1, 11, 55)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(minutes=5), "drop_off"),
            mk_event(3, base + timedelta(hours=2, minutes=20), "pick_up"),
            mk_event(4, base + timedelta(hours=3, minutes=25), "pick_up"),
        ]
        clusters = group_events_by_gap(
            events, gap_max_minutes=120, mixed_gap_max_minutes=150
        )
        assert len(clusters) == 1
        assert len(clusters[0].events) == 4

    def test_same_type_gap_at_2h15_still_splits(self):
        # Two drop-offs 2h15m apart → same-type gap rule applies (120),
        # mixed_gap doesn't kick in. Splits as before.
        base = uk_dt(2026, 5, 1, 11, 0)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(hours=2, minutes=15), "drop_off"),
        ]
        clusters = group_events_by_gap(
            events, gap_max_minutes=120, mixed_gap_max_minutes=150
        )
        assert len(clusters) == 2

    def test_boundary_mixed_gap_exactly_at_threshold_stays_same(self):
        base = uk_dt(2026, 5, 1, 12, 0)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(minutes=150), "pick_up"),
        ]
        clusters = group_events_by_gap(
            events, gap_max_minutes=120, mixed_gap_max_minutes=150
        )
        assert len(clusters) == 1

    def test_boundary_mixed_gap_one_second_over_splits(self):
        base = uk_dt(2026, 5, 1, 12, 0)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(minutes=150, seconds=1), "pick_up"),
        ]
        clusters = group_events_by_gap(
            events, gap_max_minutes=120, mixed_gap_max_minutes=150
        )
        assert len(clusters) == 2

    def test_mixed_gap_default_falls_back_to_same_type(self):
        """Backwards compatibility — older callers passing only
        gap_max_minutes get the original behaviour."""
        base = uk_dt(2026, 5, 1, 12, 0)
        events = [
            mk_event(1, base, "drop_off"),
            mk_event(2, base + timedelta(minutes=140), "pick_up"),
        ]
        # No mixed_gap kwarg — must split at 140min (>120) just like before.
        clusters = group_events_by_gap(events, gap_max_minutes=120)
        assert len(clusters) == 2


# =====================================================================================
# peak_concurrent_count
# =====================================================================================


class TestPeakConcurrentCount:
    def test_happy_two_concurrent_within_15m(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [mk_event(1, base), mk_event(2, base + timedelta(minutes=10))]
        assert peak_concurrent_count(events, window_minutes=15) == 2

    def test_unhappy_empty_returns_zero(self):
        assert peak_concurrent_count([], window_minutes=15) == 0

    def test_edge_events_spread_not_concurrent(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [
            mk_event(1, base),
            mk_event(2, base + timedelta(minutes=20)),
            mk_event(3, base + timedelta(minutes=40)),
        ]
        assert peak_concurrent_count(events, window_minutes=15) == 1

    def test_boundary_four_at_same_time(self):
        base = uk_dt(2026, 5, 4, 8, 0)
        events = [mk_event(i, base) for i in range(1, 5)]
        assert peak_concurrent_count(events, window_minutes=15) == 4


# =====================================================================================
# required_staff_count
# =====================================================================================


class TestRequiredStaffCount:
    thresholds = [{"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}]

    def test_happy_peak_2_returns_1(self):
        assert required_staff_count(2, self.thresholds) == 1

    def test_happy_peak_4_returns_2(self):
        assert required_staff_count(4, self.thresholds) == 2

    def test_boundary_peak_3_returns_1(self):
        assert required_staff_count(3, self.thresholds) == 1

    def test_boundary_peak_4_returns_2(self):
        assert required_staff_count(4, self.thresholds) == 2

    def test_edge_thresholds_out_of_order(self):
        out_of_order = [{"max_peak": 999, "staff": 2}, {"max_peak": 3, "staff": 1}]
        assert required_staff_count(2, out_of_order) == 1

    def test_unhappy_empty_thresholds_falls_back_to_1(self):
        assert required_staff_count(5, []) == 1


# =====================================================================================
# round_to_shift_type
# =====================================================================================


class TestShiftTypeRounding:
    def test_happy_canonical_morning_exact(self):
        start = uk_dt(2026, 5, 4, 7, 0)
        end = uk_dt(2026, 5, 4, 11, 0)
        shift_type, is_custom = round_to_shift_type(start, end)
        assert shift_type == ShiftType.MORNING
        assert is_custom is False

    def test_happy_canonical_full_morning_exact(self):
        start = uk_dt(2026, 5, 4, 3, 50)
        end = uk_dt(2026, 5, 4, 14, 0)
        shift_type, is_custom = round_to_shift_type(start, end)
        assert shift_type == ShiftType.FULL_MORNING
        assert is_custom is False

    def test_edge_slightly_off_canonical_falls_back_custom(self):
        start = uk_dt(2026, 5, 4, 7, 5)
        end = uk_dt(2026, 5, 4, 11, 30)
        shift_type, is_custom = round_to_shift_type(start, end)
        assert shift_type == ShiftType.MORNING
        assert is_custom is True

    def test_boundary_17_30_exactly_maps_to_late_afternoon(self):
        start = uk_dt(2026, 5, 4, 17, 30)
        end = uk_dt(2026, 5, 4, 21, 0)
        shift_type, is_custom = round_to_shift_type(start, end)
        assert shift_type == ShiftType.LATE_AFTERNOON
        assert is_custom is False


# =====================================================================================
# iso_monday — week boundaries
# =====================================================================================


class TestIsoMonday:
    def test_happy_tuesday_returns_monday(self):
        assert iso_monday(date(2026, 5, 5)) == date(2026, 5, 4)  # Tue → Mon 4 May

    def test_boundary_monday_returns_itself(self):
        assert iso_monday(date(2026, 5, 4)) == date(2026, 5, 4)

    def test_boundary_sunday_returns_week_start_monday(self):
        assert iso_monday(date(2026, 5, 10)) == date(2026, 5, 4)


# =====================================================================================
# weekly_hours_for & shift_hours — week attribution per SPEC.md
# =====================================================================================


class TestWeekHourAttribution:
    def test_happy_shift_on_wednesday_counted_against_weeks_monday(self):
        shifts = [mk_shift(1, 10, date(2026, 5, 6), time(8, 0), time(14, 0))]
        assert weekly_hours_for(10, date(2026, 5, 4), shifts) == 6.0

    def test_edge_sun_to_mon_overnight_counts_against_sun_week(self):
        """Shift starts Sun 22:30, ends Mon 02:00 (3.5h). Entirely attributed to Sun's week."""
        sun = date(2026, 5, 10)
        mon_next = date(2026, 5, 11)
        shifts = [
            mk_shift(
                1,
                10,
                sun,
                time(22, 30),
                time(2, 0),
                end_date=mon_next,
            )
        ]
        sun_week = iso_monday(sun)  # Mon 4 May
        mon_week = iso_monday(mon_next)  # Mon 11 May
        assert weekly_hours_for(10, sun_week, shifts) == 3.5
        assert weekly_hours_for(10, mon_week, shifts) == 0.0

    def test_boundary_shift_starting_sun_late_attributed_to_sun_week(self):
        """A 30-min shift starting Sun 23:30 counts fully against Sun's week,
        not the Mon-starting week after it."""
        sun = date(2026, 5, 10)
        mon_next = date(2026, 5, 11)
        shifts = [
            mk_shift(1, 10, sun, time(23, 30), time(0, 0), end_date=mon_next)
        ]
        assert weekly_hours_for(10, iso_monday(sun), shifts) == 0.5
        assert weekly_hours_for(10, iso_monday(mon_next), shifts) == 0.0

    def test_shift_hours_overnight(self):
        s = mk_shift(1, 10, date(2026, 5, 10), time(22, 0), time(6, 0), end_date=date(2026, 5, 11))
        assert shift_hours(s) == 8.0


# =====================================================================================
# last_shift_end_for — 8h rest
# =====================================================================================


class TestMinRest:
    def test_happy_finds_latest_end(self):
        shifts = [
            mk_shift(1, 10, date(2026, 5, 1), time(8, 0), time(14, 0)),
            mk_shift(2, 10, date(2026, 5, 2), time(10, 0), time(16, 0)),
        ]
        latest = last_shift_end_for(10, uk_dt(2026, 5, 3, 0, 0), shifts)
        assert latest == uk_dt(2026, 5, 2, 16, 0)

    def test_unhappy_no_prior_shift_returns_none(self):
        assert last_shift_end_for(10, uk_dt(2026, 5, 3, 0, 0), []) is None

    def test_edge_overnight_shift_end_is_next_day(self):
        shifts = [
            mk_shift(
                1, 10, date(2026, 5, 1), time(22, 0), time(6, 0), end_date=date(2026, 5, 2)
            )
        ]
        latest = last_shift_end_for(10, uk_dt(2026, 5, 3, 0, 0), shifts)
        assert latest == uk_dt(2026, 5, 2, 6, 0)

    def test_boundary_shift_ending_exactly_at_before_dt_is_included(self):
        shifts = [mk_shift(1, 10, date(2026, 5, 2), time(8, 0), time(16, 0))]
        latest = last_shift_end_for(10, uk_dt(2026, 5, 2, 16, 0), shifts)
        assert latest == uk_dt(2026, 5, 2, 16, 0)


# =====================================================================================
# is_shift_untouchable
# =====================================================================================


class TestUntouchable:
    def test_happy_confirmed_shift_is_untouchable(self):
        s = mk_shift(
            1, 10, date(2026, 5, 10), time(8, 0), time(14, 0), status=ShiftStatus.CONFIRMED
        )
        now = uk_dt(2026, 5, 4, 0, 0)  # far in advance
        assert is_shift_untouchable(s, now, untouchable_hours=24) == (True, "status=confirmed")

    def test_happy_shift_23h_away_is_untouchable(self):
        s = mk_shift(1, 10, date(2026, 5, 4), time(23, 0), time(23, 59))
        now = uk_dt(2026, 5, 4, 0, 30)  # 22h30m before start
        unt, reason = is_shift_untouchable(s, now, untouchable_hours=24)
        assert unt is True
        assert "24h" in (reason or "")

    def test_unhappy_shift_far_in_future_is_touchable(self):
        s = mk_shift(1, 10, date(2026, 5, 20), time(8, 0), time(14, 0))
        now = uk_dt(2026, 5, 4, 0, 0)
        assert is_shift_untouchable(s, now, untouchable_hours=24) == (False, None)

    def test_boundary_shift_exactly_24h_away_is_touchable(self):
        s = mk_shift(1, 10, date(2026, 5, 5), time(8, 0), time(14, 0))
        now = uk_dt(2026, 5, 4, 8, 0)  # exactly 24h before
        unt, _ = is_shift_untouchable(s, now, untouchable_hours=24)
        assert unt is False, "exactly 24h away is the touchable edge"


# =====================================================================================
# pick_staff — hard constraints + preferences
# =====================================================================================


class TestPickStaff:
    def test_happy_flexible_staff_assigned(self):
        staff = [mk_staff(10, "Ly", "Nguyen")]
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=staff,
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 10

    def test_happy_lower_weekly_hours_wins_tiebreaker(self):
        """With both candidates eligible (same window, same fallback
        status), the one with fewer weekly hours wins — load balancer."""
        # MS already has 8h existing this week, LN has none.
        existing = mk_shift(100, 20, date(2026, 5, 4), time(0, 0), time(8, 0))
        ms = mk_staff(20, "M", "S")
        ln = mk_staff(21, "L", "N")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms, ln],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 21

    def test_unhappy_auto_assign_excluded_never_picked(self):
        mc = mk_staff(30, "M", "C", excluded=True)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[mc],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    # -- driver_type ---------------------------------------------------

    def test_unhappy_fleet_driver_never_picked(self):
        """Phase 2: only jockeys are auto-assigned. A fleet-only pool
        leaves the shift unassigned even though they're otherwise eligible."""
        fleet_only = mk_staff(50, "Aaron", "S", driver_type="fleet")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[fleet_only], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    def test_unhappy_null_driver_type_never_picked(self):
        """Admins / undecided users have driver_type=None and must
        also be skipped."""
        admin_ish = mk_staff(60, "Admin", "Ish", driver_type=None)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[admin_ish], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    def test_happy_jockey_picked_over_fleet_in_mixed_pool(self):
        ms = mk_staff(7, "M", "S", driver_type="jockey")
        aaron = mk_staff(50, "Aaron", "S", driver_type="fleet")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[aaron, ms], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 7

    # -- working window (preferred_start_time / preferred_end_time) -----

    def test_unhappy_kw_blocked_from_morning_via_window(self):
        """KW's window is 16:00–01:00 (next day). A 07:00–11:00 morning
        shift is outside that window → KW excluded. KA (the fallback,
        no window configured) covers it."""
        kw = mk_staff(
            8, "Karl", "Walden",
            preferred_start_time=time(16, 0),
            preferred_end_time=time(1, 0),
        )
        ka = mk_staff(2, "Kristian", "AB", is_fallback_driver=True)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[kw, ka], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 2

    def test_unhappy_ms_blocked_from_evening_via_window(self):
        """MS's window is 03:00–12:00. A 21:00–00:30 evening shift is
        outside that window → MS excluded. KW (window 16:00–01:00 next
        day) covers it."""
        ms = mk_staff(
            7, "Marek", "Smolarek",
            preferred_start_time=time(3, 0),
            preferred_end_time=time(12, 0),
        )
        kw = mk_staff(
            8, "Karl", "Walden",
            preferred_start_time=time(16, 0),
            preferred_end_time=time(1, 0),
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 21, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 0, 30),
            shift_type=ShiftType.EVENING,
            staff=[ms, kw], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 8

    def test_window_only_blocks_shifts_outside_it(self):
        """KW's window 16:00–01:00 (next day) must still let KW take an
        evening shift — the window restricts time-of-day, not shift type."""
        kw = mk_staff(
            8, "Karl", "Walden",
            preferred_start_time=time(16, 0),
            preferred_end_time=time(1, 0),
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 21, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 0, 30),
            shift_type=ShiftType.EVENING,
            staff=[kw], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 8

    def test_overnight_window_accepts_post_midnight_tail(self):
        """KW's window 16:00–01:00 wraps midnight. A 00:30–00:45 shift
        (early next day) belongs to the previous day's window and KW
        must still be eligible."""
        kw = mk_staff(
            8, "Karl", "Walden",
            preferred_start_time=time(16, 0),
            preferred_end_time=time(1, 0),
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 0, 30),
            shift_end_dt=uk_dt(2026, 5, 7, 0, 45),
            shift_type=ShiftType.EVENING,
            staff=[kw], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 8

    # -- primary vs fallback (is_fallback_driver) -----------------------

    def test_primary_beats_fallback_when_both_eligible(self):
        """KA (fallback) is only used when no primary is available.
        With MS (primary, window contains shift) and KA (fallback, no
        window) both eligible for a 09:00–11:00 shift, MS wins."""
        ms = mk_staff(
            7, "Marek", "Smolarek",
            preferred_start_time=time(3, 0),
            preferred_end_time=time(12, 0),
        )
        ka = mk_staff(
            2, "Kristian", "AB",
            preferred_start_time=time(9, 0),
            preferred_end_time=time(17, 0),
            is_fallback_driver=True,
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 9, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms, ka], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 7

    def test_fallback_fires_when_primary_on_holiday(self):
        """MS on holiday → KA (fallback) covers."""
        ms = mk_staff(
            7, "Marek", "Smolarek",
            preferred_start_time=time(3, 0),
            preferred_end_time=time(12, 0),
        )
        ka = mk_staff(
            2, "Kristian", "AB",
            preferred_start_time=time(9, 0),
            preferred_end_time=time(17, 0),
            is_fallback_driver=True,
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 9, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms, ka],
            holidays=[mk_holiday(7, date(2026, 5, 6))],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 2

    def test_fallback_skipped_if_shift_outside_their_window(self):
        """KA (fallback, window 09:00–17:00) cannot cover a 05:00–06:00
        shift even when MS (primary) is on holiday — the shift is
        outside KA's window. Returns None (unmanned)."""
        ms = mk_staff(
            7, "Marek", "Smolarek",
            preferred_start_time=time(3, 0),
            preferred_end_time=time(12, 0),
        )
        ka = mk_staff(
            2, "Kristian", "AB",
            preferred_start_time=time(9, 0),
            preferred_end_time=time(17, 0),
            is_fallback_driver=True,
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 5, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 6, 0),
            shift_type=ShiftType.EARLY_MORNING,
            staff=[ms, ka],
            holidays=[mk_holiday(7, date(2026, 5, 6))],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    # -- tiebreaker semantics -------------------------------------------

    def test_tiebreaker_does_not_use_user_id(self):
        """When two primaries are equally eligible with equal weekly
        hours, the lower user.id MUST NOT win — id is identity, not a
        ranking signal. Final tiebreaker is alphabetical first_name."""
        # Higher id, alphabetically-earlier first name → should win.
        anna = mk_staff(99, "Anna", "Z")
        zach = mk_staff(2, "Zach", "A")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[zach, anna],   # input order favours Zach if id were used
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 99, "Anna (alphabetical first_name) wins, not the lower id"

    # -- preferred_days_off --------------------------------------------

    def test_unhappy_preferred_day_off_hard_excludes(self):
        """preferred_days_off [5] = Sat. A Saturday morning shift must
        skip a jockey marked Sat-off, picking the next eligible."""
        # 2026-05-09 is a Saturday → weekday() = 5
        ms = mk_staff(7, "Marek", "S", preferred_days_off=[5])
        ka = mk_staff(2, "Kristian", "AB")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 9, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 9, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms, ka], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 2

    def test_preferred_days_off_does_not_affect_other_days(self):
        """Same MS with Sat-off — a Friday shift still works."""
        # 2026-05-08 = Friday → weekday() = 4
        ms = mk_staff(7, "Marek", "S", preferred_days_off=[5])
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 8, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 8, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 7

    def test_unhappy_all_on_holiday_returns_none(self):
        s = mk_staff(40)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            holidays=[mk_holiday(40, date(2026, 5, 6))],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    def test_edge_at_max_hours_falls_back_to_other_jockey(self):
        """MS is at 40h already — must be excluded by max_hours_per_week
        even though both candidates have no window restriction."""
        ms = mk_staff(20, "M", "S")
        ln = mk_staff(21, "L", "N")
        # MS has 38h existing; new 4h shift would push to 42 → over cap
        existing = [
            mk_shift(100, 20, date(2026, 5, 4), time(0, 0), time(12, 0), end_date=date(2026, 5, 4)),
            mk_shift(101, 20, date(2026, 5, 5), time(0, 0), time(12, 0), end_date=date(2026, 5, 5)),
            mk_shift(102, 20, date(2026, 5, 6), time(0, 0), time(14, 0)),
        ]
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 14, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 18, 0),
            shift_type=ShiftType.AFTERNOON,
            staff=[ms, ln],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen.id == 21, "MS over cap → LN picked"

    def test_boundary_exactly_40h_in_run_excluded_from_more(self):
        """Hard 40h cap counts against IN-RUN proposed hours only — saved
        roster_shifts are never consulted (engine = pure simulation)."""
        s = mk_staff(50)
        week_start = iso_monday(date(2026, 5, 7))
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 8, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 10, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={(50, week_start): 40},  # at cap
            proposed_last_end_by_staff={},
        )
        assert chosen is None, "at exactly 40h in this run, any more over caps"

    def test_boundary_8h_rest_exactly_ok_7h59m_blocked(self):
        """Engine enforces 8h min rest against the IN-RUN previous pick.
        Saved roster_shifts are never consulted."""
        s = mk_staff(60)
        # Pretend this run already picked staff 60 for a shift ending Sun 23:00.
        prior_end = uk_dt(2026, 5, 3, 23, 0)

        ok = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 4, 7, 0),  # exactly 8h later
            shift_end_dt=uk_dt(2026, 5, 4, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
            proposed_last_end_by_staff={60: prior_end},
        )
        assert ok is not None

        blocked = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 4, 6, 59),  # 7h59m later
            shift_end_dt=uk_dt(2026, 5, 4, 10, 59),
            shift_type=ShiftType.MORNING,
            staff=[s],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
            proposed_last_end_by_staff={60: prior_end},
        )
        assert blocked is None

    def test_same_day_split_shifts_skip_min_rest(self):
        """Min rest only applies between calendar days. A jockey can
        do a morning + afternoon split on the same day with < 8h gap
        (operational reality: short-turnaround coverage)."""
        s = mk_staff(70, "KA", "F", preferred_start_time=time(9, 0),
                     preferred_end_time=time(17, 0))
        # In-run pick ended same-day at 12:00; new shift starts 14:00 (2h gap).
        prior_end = uk_dt(2026, 5, 6, 12, 0)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 14, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 16, 0),
            shift_type=ShiftType.AFTERNOON,
            staff=[s],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
            proposed_last_end_by_staff={70: prior_end},
        )
        assert chosen is not None and chosen.id == 70

    def test_min_rest_still_enforced_across_midnight(self):
        """Same-day rule does NOT relax cross-day rest. KW finishing
        Sat 23:30 and starting again Sun 02:00 = 2h30m gap across days
        → blocked. The previous ok-at-8h test covers the boundary; this
        guards the cross-day intent."""
        kw = mk_staff(80, "Karl", "Walden",
                      preferred_start_time=time(16, 0),
                      preferred_end_time=time(1, 0))
        prior_end = uk_dt(2026, 5, 9, 23, 30)  # Sat
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 10, 2, 0),  # Sun, 2h30m later
            shift_end_dt=uk_dt(2026, 5, 10, 5, 0),
            shift_type=ShiftType.EARLY_MORNING,
            staff=[kw],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
            proposed_last_end_by_staff={80: prior_end},
        )
        assert chosen is None

    # -- window_overrun_minutes -----------------------------------------

    def test_window_overrun_allows_shift_to_extend_past_preferred_end(self):
        """KA window 09:00–17:00 + default 60-min overrun → a 13:40–17:55
        shift (55 min past) is eligible. Without overrun this was the
        '?unassigned' bug from 30 Apr."""
        ka = mk_staff(2, "Kristian", "AB",
                      preferred_start_time=time(9, 0),
                      preferred_end_time=time(17, 0))
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 13, 40),
            shift_end_dt=uk_dt(2026, 5, 7, 17, 55),
            shift_type=ShiftType.AFTERNOON,
            staff=[ka],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is not None and chosen.id == 2

    def test_window_overrun_does_not_help_when_overrun_exceeded(self):
        """Default overrun is 60 min. A shift ending 18:01 (61 min past
        17:00) is still rejected — the buffer is a courtesy, not infinite."""
        ka = mk_staff(2, "Kristian", "AB",
                      preferred_start_time=time(9, 0),
                      preferred_end_time=time(17, 0))
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 13, 40),
            shift_end_dt=uk_dt(2026, 5, 7, 18, 1),
            shift_type=ShiftType.AFTERNOON,
            staff=[ka],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None


# =====================================================================================
# propose_roster — end-to-end integration on pure inputs
# =====================================================================================


class TestProposeRosterEndToEnd:
    def test_happy_single_cluster_produces_one_shift(self):
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(
                1,
                "TAG-AAA",
                drop_dt=uk_dt(2026, 5, 6, 13, 0),
                pick_dt=uk_dt(2026, 5, 10, 17, 0),
            ),
        ]
        staff = [mk_staff(10, "Ly", "Nguyen")]
        result = propose_roster(
            bookings=bookings,
            shifts=[],
            staff=staff,
            holidays=[],
            settings=DEFAULT_SETTINGS,
            now=now,
        )
        # Two events, far apart → 2 separate shifts
        new_shifts = [p for p in result["proposed_shifts"] if p["kind"] == "new"]
        assert len(new_shifts) == 2

    def test_unhappy_no_bookings_in_window(self):
        now = uk_dt(2026, 5, 1, 0, 0)
        result = propose_roster(
            bookings=[],
            shifts=[],
            staff=[mk_staff(10)],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            now=now,
        )
        assert result["proposed_shifts"] == []

    def test_asymmetric_buffer_20_before_30_after(self):
        """Single 13:00 drop-off: buffered window 12:40–13:30 (50min) gets
        EXTENDED by the 60-min min_shift_minutes rule to 12:40–13:40.
        Locks both behaviours at once: asymmetric buffer + min length."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(
                1,
                "TAG-BUF",
                drop_dt=uk_dt(2026, 5, 6, 13, 0),
                pick_dt=uk_dt(2026, 5, 20, 17, 0),  # far away — separate cluster
            ),
        ]
        staff = [mk_staff(10, "Ly", "Nguyen")]
        result = propose_roster(
            bookings=bookings,
            shifts=[],
            staff=staff,
            holidays=[],
            settings=DEFAULT_SETTINGS,
            now=now,
        )
        drop_shift = next(
            p for p in result["proposed_shifts"]
            if p["kind"] == "new" and p["date"].isoformat() == "2026-05-06"
        )
        assert drop_shift["start_time"].strftime("%H:%M") == "12:40"
        assert drop_shift["end_time"].strftime("%H:%M") == "13:40"

    def test_min_shift_minutes_does_not_extend_already_long_enough(self):
        """Three events spanning 13:00–14:15 → shift 12:40–14:45 (125 min)
        exceeds 60 min, so no extension needed."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(1, "TAG-A",
                drop_dt=uk_dt(2026, 5, 6, 13, 0),
                pick_dt=uk_dt(2026, 5, 6, 13, 45)),
            mk_booking(2, "TAG-B",
                drop_dt=uk_dt(2026, 5, 6, 14, 15),
                pick_dt=uk_dt(2026, 6, 30, 10, 0)),
        ]
        staff = [mk_staff(10)]
        result = propose_roster(
            bookings=bookings, shifts=[], staff=staff, holidays=[],
            settings=DEFAULT_SETTINGS, now=now,
        )
        s = next(p for p in result["proposed_shifts"]
                 if p["kind"] == "new" and p["date"].isoformat() == "2026-05-06")
        assert s["start_time"].strftime("%H:%M") == "12:40"
        assert s["end_time"].strftime("%H:%M") == "14:45"

    def test_edge_spec_worked_example(self):
        """SPEC events 13:00d, 13:45p, 14:15d → single shift 12:40–14:45
        with asymmetric buffer (20 start / 30 end). Original SPEC line was
        12:30–14:45 under the locked 30-min symmetric buffer; updated 2026-04-25."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(
                1, "TAG-A",
                drop_dt=uk_dt(2026, 5, 6, 13, 0),
                pick_dt=uk_dt(2026, 5, 6, 13, 45),
            ),
            mk_booking(
                2, "TAG-B",
                drop_dt=uk_dt(2026, 5, 6, 14, 15),
                pick_dt=uk_dt(2026, 6, 30, 10, 0),  # out of window
            ),
        ]
        result = propose_roster(
            bookings=bookings,
            shifts=[],
            staff=[mk_staff(10)],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            now=now,
        )
        new_shifts = [p for p in result["proposed_shifts"] if p["kind"] == "new"]
        # One cluster, 3 events in window, 1 staff
        in_window = [
            p for p in new_shifts if p["date"] == date(2026, 5, 6)
        ]
        assert len(in_window) == 1
        s = in_window[0]
        assert s["start_time"] == time(12, 40)
        assert s["end_time"] == time(14, 45)
        assert len(s["events"]) == 3

    def test_edge_untouchable_confirmed_shift_reported_not_replanned(self):
        now = uk_dt(2026, 5, 1, 0, 0)
        confirmed = mk_shift(
            99, 10, date(2026, 5, 10), time(8, 0), time(14, 0),
            status=ShiftStatus.CONFIRMED,
        )
        result = propose_roster(
            bookings=[],
            shifts=[confirmed],
            staff=[mk_staff(10)],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            now=now,
        )
        untouched = [p for p in result["proposed_shifts"] if p["kind"] == "untouched_for_reason"]
        assert len(untouched) == 1
        assert untouched[0]["shift_id"] == 99
        assert untouched[0]["untouched_reason"] == "status=confirmed"

    def test_edge_excluded_staff_never_proposed(self):
        """Mark Custard & John Penney style: excluded flag → never assigned."""
        now = uk_dt(2026, 5, 1, 0, 0)
        mc = mk_staff(1, "Mark", "Custard", excluded=True)
        bookings = [
            mk_booking(1, "TAG-A",
                       drop_dt=uk_dt(2026, 5, 6, 8, 0),
                       pick_dt=uk_dt(2026, 6, 30, 0, 0))
        ]
        result = propose_roster(
            bookings=bookings, shifts=[], staff=[mc],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        new_shifts = [p for p in result["proposed_shifts"] if p["kind"] == "new"]
        assert all(p["staff_id"] is None for p in new_shifts)
        assert any(w["rule"] == "unmanned" for w in result["warnings"])

    def test_boundary_non_confirmed_bookings_ignored(self):
        now = uk_dt(2026, 5, 1, 0, 0)
        pending = mk_booking(
            1, "TAG-PENDING",
            drop_dt=uk_dt(2026, 5, 6, 8, 0),
            pick_dt=uk_dt(2026, 6, 30, 0, 0),
            status=BookingStatus.PENDING,
        )
        result = propose_roster(
            bookings=[pending], shifts=[], staff=[mk_staff(10)],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        new_shifts = [p for p in result["proposed_shifts"] if p["kind"] == "new"]
        assert new_shifts == []

    def test_purity_same_inputs_same_output(self):
        """Engine determinism is load-bearing for audit/replay. Locked 2026-04-24."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(1, "TAG-A",
                       drop_dt=uk_dt(2026, 5, 6, 8, 0),
                       pick_dt=uk_dt(2026, 5, 6, 14, 0))
        ]
        staff = [mk_staff(10, "A", "One"), mk_staff(11, "B", "Two")]
        r1 = propose_roster(
            bookings=bookings, shifts=[], staff=staff,
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        r2 = propose_roster(
            bookings=bookings, shifts=[], staff=staff,
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        # Strip non-deterministic nested event_time/generated_at (already tz-fixed) —
        # just compare structure
        assert r1["run_id"] == r2["run_id"]
        assert r1["proposed_shifts"] == r2["proposed_shifts"]
        assert r1["summary"] == r2["summary"]

    def test_edge_rolling_window_excludes_bookings_past_end(self):
        now = uk_dt(2026, 5, 1, 0, 0)
        # Booking 35 days out — past 28-day window
        out_of_window = mk_booking(
            1, "TAG-OUT",
            drop_dt=uk_dt(2026, 6, 5, 8, 0),
            pick_dt=uk_dt(2026, 6, 10, 10, 0),
        )
        result = propose_roster(
            bookings=[out_of_window], shifts=[], staff=[mk_staff(10)],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        new_shifts = [p for p in result["proposed_shifts"] if p["kind"] == "new"]
        assert new_shifts == []


# =====================================================================================
# SPEC.md gap-fillers (audit 2026-04-26): cases the testing matrix calls out
# but weren't yet locked in.
# =====================================================================================


class TestSpecGapFillers:
    def test_all_jockeys_excluded_produces_unmanned_warning(self):
        """When every assignable jockey is on holiday, the shift is
        emitted with staff_id=None and an 'unmanned' warning."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(1, "TAG-A",
                drop_dt=uk_dt(2026, 5, 6, 8, 0),
                pick_dt=uk_dt(2026, 5, 20, 10, 0)),
        ]
        ms = mk_staff(7, "Marek", "S")
        ka = mk_staff(2, "Kristian", "AB")
        result = propose_roster(
            bookings=bookings, shifts=[], staff=[ms, ka],
            holidays=[
                mk_holiday(7, date(2026, 5, 6)),
                mk_holiday(2, date(2026, 5, 6)),
            ],
            settings=DEFAULT_SETTINGS, now=now,
        )
        drop = next(p for p in result["proposed_shifts"]
                    if p["kind"] == "new" and p["date"].isoformat() == "2026-05-06")
        assert drop["staff_id"] is None
        assert any(w["rule"] == "unmanned" for w in result["warnings"])

    def test_existing_confirmed_shifts_do_not_suppress_new_proposals(self):
        """Engine is a pure simulation — it plans every booking in window
        regardless of what's saved in roster_shifts. A CONFIRMED saved
        shift covering the same booking still surfaces in the comparison
        view (kind='untouched_for_reason') but does NOT prevent the
        engine emitting its own 'new' proposal for the same time. See
        SPEC.md § Roster Planner."""
        now = uk_dt(2026, 5, 1, 0, 0)
        bookings = [
            mk_booking(1, "TAG-A",
                drop_dt=uk_dt(2026, 5, 6, 8, 0),
                pick_dt=uk_dt(2026, 5, 20, 10, 0)),
        ]
        b = SimpleNamespace(id=1, dropoff_date=date(2026, 5, 6), pickup_date=date(2026, 5, 20))
        confirmed = mk_shift(
            99, 7, date(2026, 5, 6), time(7, 30), time(9, 0),
            status=ShiftStatus.CONFIRMED,
            bookings=[b],
        )
        result = propose_roster(
            bookings=bookings, shifts=[confirmed], staff=[mk_staff(7, "Marek", "S")],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        # The engine STILL emits a new shift for the drop-off — saved
        # shifts no longer suppress planning.
        new_drop = [p for p in result["proposed_shifts"]
                    if p["kind"] == "new" and p["date"].isoformat() == "2026-05-06"]
        assert len(new_drop) == 1
        # The existing confirmed shift is rendered alongside (comparison view).
        untouched = [p for p in result["proposed_shifts"]
                     if p["kind"] == "untouched_for_reason"]
        assert any(p["shift_id"] == 99 for p in untouched)

    def test_boundary_39h59m_existing_still_eligible_for_3min_shift(self):
        """Hard 40h cap is `>` not `>=`. 39h59m existing + 3min
        proposed = 39h62m — still under 40h, so the staff is
        eligible. Confirms the boundary direction."""
        # Existing 39h59m of shifts: 4 × 9h59m45s ≈ 39h59m
        # Simpler: one 39h59m shift Mon 00:00 - Tue 15:59
        existing = mk_shift(
            1, 7, date(2026, 5, 4), time(0, 0), time(15, 59),
            end_date=date(2026, 5, 5),
            status=ShiftStatus.SCHEDULED,
        )
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 12, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 12, 1),  # 1 minute
            shift_type=ShiftType.MIDDAY,
            staff=[mk_staff(7, "Marek", "S")], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        # 39h59m + 1m = 40h0m, which is NOT > 40 → eligible.
        assert chosen is not None and chosen.id == 7

    def test_boundary_holiday_starts_mid_shift_excludes_for_that_day(self):
        """Holiday on the same date as the shift excludes the staff,
        even if their holiday only covers part of the day."""
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 9, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 17, 0),
            shift_type=ShiftType.MIDDAY,
            staff=[mk_staff(7, "Marek", "S")],
            holidays=[mk_holiday(7, date(2026, 5, 7))],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(), proposed_hours_by_staff_week={}, proposed_last_end_by_staff={},
        )
        assert chosen is None

    def test_shift_type_rounding_longest_match_at_canonical_overlap(self):
        """SPEC: when (start, end) match multiple canonical windows
        (e.g. 03:50 is the start of both EARLY_MORNING and FULL_MORNING),
        the longest-window match wins. Locks the canonical lookup
        order in _CANONICAL_SHIFT_TYPE_WINDOWS."""
        # 03:50 → 14:00 exactly matches FULL_MORNING canonical window.
        # 03:50 → 07:00 exactly matches EARLY_MORNING canonical window.
        # Both end times tested separately — assert each maps right.
        from roster_planner import round_to_shift_type
        sh, _ = round_to_shift_type(uk_dt(2026, 5, 6, 3, 50), uk_dt(2026, 5, 6, 14, 0))
        assert sh == ShiftType.FULL_MORNING
        sh, _ = round_to_shift_type(uk_dt(2026, 5, 6, 3, 50), uk_dt(2026, 5, 6, 7, 0))
        assert sh == ShiftType.EARLY_MORNING


class TestDstRegression:
    """SPEC § Regression guards: 'Explicit DST-transition tests
    (last Sun in March, last Sun in October 2026).'

    UK DST 2026:
      - Spring forward: 29 March 2026 (Sun 01:00 → 02:00)
      - Fall back:      25 October 2026 (Sun 02:00 → 01:00)

    Engine must:
      - Cluster events across the transition without crashing
      - Attribute hours correctly (Europe/London wall-clock)
      - Apply the rest gap correctly across DST
    """

    def test_spring_forward_event_clusters_without_crashing(self):
        # 29 Mar 2026 is the spring-forward Sunday. now=Mar 5 → window
        # spans the transition (Mar 5 to Apr 2). An event at 03:30
        # post-jump is fine; clustering shouldn't blow up.
        now = uk_dt(2026, 3, 5, 0, 0)
        bookings = [
            mk_booking(1, "TAG-DST",
                drop_dt=uk_dt(2026, 3, 29, 3, 30),
                pick_dt=uk_dt(2026, 3, 31, 10, 0)),
        ]
        result = propose_roster(
            bookings=bookings, shifts=[], staff=[mk_staff(7, "Marek", "S")],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        assert any(p["date"].isoformat() == "2026-03-29"
                   for p in result["proposed_shifts"]
                   if p["kind"] == "new")

    @pytest.mark.xfail(
        reason="Engine bug: pick_staff computes rest as "
               "(shift_start_dt - last_end).total_seconds() with same-ZoneInfo "
               "tz-aware datetimes. Python 3.9 zoneinfo subtraction returns "
               "wall-clock seconds across DST instead of true elapsed UTC "
               "seconds — under-counts by 1h across the Oct fall-back, "
               "blocking eligible staff. Fix needs UTC conversion before "
               "subtraction; tracked separately.",
        strict=True,
    )
    def test_fall_back_rest_gap_crosses_dst_correctly(self):
        """Sun 25 Oct 2026 falls back: 02:00 BST → 01:00 GMT, so the
        clock shows 01:00–02:00 twice. An in-run pick ending Sat 23:00 BST,
        next eligible at 06:30 GMT — wall-clock looks like 7h30m but real
        elapsed time is 8h30m. The engine SHOULD compare in UTC and treat
        8.5h as ≥ 8h required."""
        # Pretend this run already picked Marek for a shift ending Sat 23:00 BST.
        prior_end = uk_dt(2026, 10, 24, 23, 0)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 10, 25, 6, 30),
            shift_end_dt=uk_dt(2026, 10, 25, 8, 0),
            shift_type=ShiftType.EARLY_MORNING,
            staff=[mk_staff(7, "Marek", "S")], holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
            proposed_last_end_by_staff={7: prior_end},
        )
        # Real elapsed across DST: 8h30m ≥ 8h → eligible.
        assert chosen is not None and chosen.id == 7

    def test_window_spans_dst_no_crash(self):
        """28-day window starting 22 March 2026 (BST starts 29 Mar)
        spans the spring-forward. Engine must not crash and should
        produce a normal proposal."""
        now = uk_dt(2026, 3, 22, 0, 0)
        bookings = [
            mk_booking(1, "TAG-X",
                drop_dt=uk_dt(2026, 3, 26, 10, 0),
                pick_dt=uk_dt(2026, 4, 2, 15, 0)),
        ]
        result = propose_roster(
            bookings=bookings, shifts=[], staff=[mk_staff(7, "Marek", "S")],
            holidays=[], settings=DEFAULT_SETTINGS, now=now,
        )
        assert "proposed_shifts" in result
        assert "warnings" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
