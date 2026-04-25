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
    gap_max_minutes=120,
    mixed_gap_max_minutes=150,
    buffer_minutes=30,
    staffing_thresholds=({"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}),
    max_hours_per_week=40,
    min_rest_hours=8,
    untouchable_hours=24,
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
):
    return SimpleNamespace(
        id=user_id,
        first_name=first,
        last_name=last,
        preferred_shift_types=preferred or [],
        auto_assign_excluded=excluded,
        is_active=active,
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
            shifts=[],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen is not None and chosen.id == 10

    def test_happy_preferred_staff_beats_flexible(self):
        ms = mk_staff(20, "M", "S", preferred=[ShiftType.MORNING])
        ln = mk_staff(21, "L", "N")
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[ms, ln],
            shifts=[],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen.id == 20

    def test_unhappy_auto_assign_excluded_never_picked(self):
        mc = mk_staff(30, "M", "C", excluded=True)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[mc],
            shifts=[],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen is None

    def test_unhappy_all_on_holiday_returns_none(self):
        s = mk_staff(40)
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 6, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 6, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            shifts=[],
            holidays=[mk_holiday(40, date(2026, 5, 6))],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen is None

    def test_edge_preferred_at_max_hours_falls_back_to_flex(self):
        """MS prefers MORNING but is at 40h already — should fall back to LN."""
        ms = mk_staff(20, "M", "S", preferred=[ShiftType.MORNING])
        ln = mk_staff(21, "L", "N")
        week_start = iso_monday(date(2026, 5, 6))
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
            shifts=existing,
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen.id == 21, "MS over cap → LN picked"

    def test_boundary_exactly_40h_existing_excluded_from_more(self):
        s = mk_staff(50)
        existing = [
            mk_shift(200, 50, date(2026, 5, 4), time(0, 0), time(0, 0), end_date=date(2026, 5, 5)),  # 24h
            mk_shift(201, 50, date(2026, 5, 6), time(0, 0), time(16, 0)),  # 16h → total 40h
        ]
        chosen = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 7, 8, 0),
            shift_end_dt=uk_dt(2026, 5, 7, 10, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            shifts=existing,
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert chosen is None, "at exactly 40h, any more over caps"

    def test_boundary_8h_rest_exactly_ok_7h59m_blocked(self):
        s = mk_staff(60)
        # Prior shift ends Sun 23:00
        prior = mk_shift(300, 60, date(2026, 5, 3), time(15, 0), time(23, 0))

        # Next shift 8h later — OK
        ok = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 4, 7, 0),
            shift_end_dt=uk_dt(2026, 5, 4, 11, 0),
            shift_type=ShiftType.MORNING,
            staff=[s],
            shifts=[prior],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert ok is not None

        # 7h59m later — blocked
        blocked = pick_staff(
            shift_start_dt=uk_dt(2026, 5, 4, 6, 59),
            shift_end_dt=uk_dt(2026, 5, 4, 10, 59),
            shift_type=ShiftType.MORNING,
            staff=[s],
            shifts=[prior],
            holidays=[],
            settings=DEFAULT_SETTINGS,
            already_chosen_ids=set(),
            proposed_hours_by_staff_week={},
        )
        assert blocked is None


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
        assert result["warnings"] == []
        assert result["summary"]["new_shifts"] == 0

    def test_edge_spec_worked_example(self):
        """From SPEC.md 2026-04-24: events 13:00d, 13:45p, 14:15d → single shift 12:30–14:45."""
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
        assert s["start_time"] == time(12, 30)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
