"""Roster Planner — pure-function engine.

Deterministic roster proposal for the next N days based on confirmed bookings,
existing shifts, staff attributes, and operator-tunable settings.

Rules locked 2026-04-24. See backend/docs/SPEC.md § Roster Planner for the
full rationale, the test matrix, and the phased rollout plan.

Architectural contract:
- `propose_roster(...)` is a pure function: same inputs produce the same output.
- No DB calls, no datetime.now(), no randomness — all needed state is passed in.
- The caller (a FastAPI endpoint) performs the reads, hands in plain iterables,
  serialises the returned dict to JSON.
- Phase 1: return only. No writes to `roster_shifts` are possible from this module.
"""
from __future__ import annotations

import uuid
import zoneinfo
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from db_models import (
    Booking,
    BookingStatus,
    EmployeeHoliday,
    RosterShift,
    ShiftStatus,
    ShiftType,
    User,
)

UK_TZ = zoneinfo.ZoneInfo("Europe/London")


# =====================================================================================
# Settings dataclass — parsed from the roster_planner_settings key/value rows.
# =====================================================================================


@dataclass(frozen=True)
class PlannerSettings:
    window_days: int
    gap_max_minutes: int
    buffer_minutes: int
    staffing_thresholds: tuple[dict, ...]
    max_hours_per_week: int
    min_rest_hours: int
    untouchable_hours: int

    @staticmethod
    def from_kv(rows: dict[str, object]) -> "PlannerSettings":
        """Build a PlannerSettings from a {key: parsed_value} map.

        The DB stores JSON-encoded strings; callers decode before calling this.
        Missing keys fall back to locked-2026-04-24 defaults so the engine never
        crashes on a partial settings row set.
        """
        return PlannerSettings(
            window_days=int(rows.get("window_days", 28)),
            gap_max_minutes=int(rows.get("gap_max_minutes", 120)),
            buffer_minutes=int(rows.get("buffer_minutes", 30)),
            staffing_thresholds=tuple(
                rows.get(
                    "staffing_thresholds",
                    [{"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}],
                )
            ),
            max_hours_per_week=int(rows.get("max_hours_per_week", 40)),
            min_rest_hours=int(rows.get("min_rest_hours", 8)),
            untouchable_hours=int(rows.get("untouchable_hours", 24)),
        )


# =====================================================================================
# Event modelling — a booking produces up to 2 events (drop-off + pick-up).
# =====================================================================================


@dataclass(frozen=True)
class Event:
    booking_id: int
    booking_reference: str
    event_type: str  # "drop_off" | "pick_up"
    event_time: datetime  # tz-aware Europe/London


@dataclass
class EventCluster:
    events: list[Event] = field(default_factory=list)

    @property
    def start(self) -> datetime:
        return min(e.event_time for e in self.events)

    @property
    def end(self) -> datetime:
        return max(e.event_time for e in self.events)


# =====================================================================================
# ShiftType canonical windows — read from enum comments in db_models.py.
# =====================================================================================

# (start_hour, start_minute, end_hour, end_minute) → ShiftType
# End-time for overnight types uses the raw wall-clock end (e.g. 01:20 next day).
_CANONICAL_SHIFT_TYPE_WINDOWS: dict[tuple[int, int, int, int], ShiftType] = {
    (3, 50, 7, 0): ShiftType.EARLY_MORNING,
    (7, 0, 11, 0): ShiftType.MORNING,
    (11, 0, 14, 0): ShiftType.MIDDAY,
    (14, 0, 17, 30): ShiftType.AFTERNOON,
    (17, 30, 21, 0): ShiftType.LATE_AFTERNOON,
    (21, 0, 1, 20): ShiftType.EVENING,
    (3, 50, 14, 0): ShiftType.FULL_MORNING,
    (11, 0, 21, 0): ShiftType.FULL_AFTERNOON,
    (17, 30, 1, 20): ShiftType.FULL_EVENING,
}


def round_to_shift_type(start: datetime, end: datetime) -> tuple[ShiftType, bool]:
    """Return `(shift_type, is_custom_range)`.

    When (start, end) exactly matches a canonical enum window, return that enum
    with `is_custom_range=False`. Otherwise pick a best-match enum (by start hour)
    with `is_custom_range=True` so the UI can show the actual custom times while
    still tagging the shift with a valid enum value.
    """
    key = (start.hour, start.minute, end.hour, end.minute)
    if key in _CANONICAL_SHIFT_TYPE_WINDOWS:
        return _CANONICAL_SHIFT_TYPE_WINDOWS[key], False

    hour = start.hour
    if 3 <= hour < 7:
        return ShiftType.EARLY_MORNING, True
    if 7 <= hour < 11:
        return ShiftType.MORNING, True
    if 11 <= hour < 14:
        return ShiftType.MIDDAY, True
    if 14 <= hour < 17 or (hour == 17 and start.minute < 30):
        return ShiftType.AFTERNOON, True
    if (hour == 17 and start.minute >= 30) or 18 <= hour < 21:
        return ShiftType.LATE_AFTERNOON, True
    return ShiftType.EVENING, True


# =====================================================================================
# Helper functions — each is independently testable.
# =====================================================================================


def group_events_by_gap(
    events: Iterable[Event], gap_max_minutes: int
) -> list[EventCluster]:
    """Group events into clusters where consecutive events are ≤ `gap_max_minutes` apart.

    The 2-hour rule is inclusive: a gap of exactly `gap_max_minutes` keeps events in
    the same cluster. Greater than that splits.
    """
    ordered = sorted(events, key=lambda e: e.event_time)
    if not ordered:
        return []

    clusters: list[EventCluster] = []
    current = [ordered[0]]
    for ev in ordered[1:]:
        gap_minutes = (ev.event_time - current[-1].event_time).total_seconds() / 60
        if gap_minutes <= gap_max_minutes:
            current.append(ev)
        else:
            clusters.append(EventCluster(events=current))
            current = [ev]
    clusters.append(EventCluster(events=current))
    return clusters


def peak_concurrent_count(events: Iterable[Event], window_minutes: int = 15) -> int:
    """Max number of events falling within any `window_minutes` rolling window.

    Uses the two-pointer technique over sorted event times. An event at the same
    timestamp as another counts — the bottleneck is concurrent physical presence.
    """
    times = sorted(e.event_time for e in events)
    if not times:
        return 0
    peak = 1
    left = 0
    for right in range(len(times)):
        while (times[right] - times[left]).total_seconds() / 60 > window_minutes:
            left += 1
        peak = max(peak, right - left + 1)
    return peak


def required_staff_count(peak: int, thresholds: Iterable[dict]) -> int:
    """Pick the first staffing bucket whose `max_peak` ≥ `peak`.

    Thresholds are sorted ascending by `max_peak` to keep the logic stable if the
    admin stores them out of order.
    """
    ordered = sorted(thresholds, key=lambda t: t["max_peak"])
    for t in ordered:
        if peak <= t["max_peak"]:
            return int(t["staff"])
    return int(ordered[-1]["staff"]) if ordered else 1


def iso_monday(d: date) -> date:
    """Monday (week start) of the week containing `d`. Python weekday: Mon=0, Sun=6."""
    return d - timedelta(days=d.weekday())


def is_staff_on_holiday(
    staff_id: int, day: date, holidays: Iterable[EmployeeHoliday]
) -> bool:
    return any(
        h.employee_id == staff_id and h.start_date <= day <= h.end_date for h in holidays
    )


def shift_hours(shift: RosterShift) -> float:
    """Total hours of an existing shift, handling overnight via end_date."""
    start_dt = datetime.combine(shift.date, shift.start_time)
    end_date = shift.end_date or shift.date
    end_dt = datetime.combine(end_date, shift.end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return (end_dt - start_dt).total_seconds() / 3600


def weekly_hours_for(
    staff_id: int,
    week_start: date,
    shifts: Iterable[RosterShift],
) -> float:
    """Hours already committed for `staff_id` in the Mon-Sun week starting `week_start`.

    Per SPEC.md: attribution is 100% to the week containing the shift's `start_time`
    (i.e. the shift's `date` column). A shift starting Sun 22:30 and ending Mon 02:00
    counts entirely against Sun's week.
    """
    week_end = week_start + timedelta(days=7)
    total = 0.0
    for s in shifts:
        if s.staff_id != staff_id:
            continue
        if s.date < week_start or s.date >= week_end:
            continue
        total += shift_hours(s)
    return total


def last_shift_end_for(
    staff_id: int,
    before_dt: datetime,
    shifts: Iterable[RosterShift],
) -> Optional[datetime]:
    """Latest end datetime of any shift for `staff_id` strictly before `before_dt`.

    Return value is tz-aware Europe/London.
    """
    latest: Optional[datetime] = None
    for s in shifts:
        if s.staff_id != staff_id:
            continue
        start_dt = _combine_uk(s.date, s.start_time)
        end_date = s.end_date or s.date
        end_dt = _combine_uk(end_date, s.end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if end_dt > before_dt:
            continue
        if latest is None or end_dt > latest:
            latest = end_dt
    return latest


def is_shift_untouchable(
    shift: RosterShift, now: datetime, untouchable_hours: int
) -> tuple[bool, Optional[str]]:
    """A shift is off-limits to the engine when confirmed OR imminent (< untouchable_hours)."""
    if shift.status == ShiftStatus.CONFIRMED:
        return True, "status=confirmed"
    start_dt = _combine_uk(shift.date, shift.start_time)
    hours_until = (start_dt - now).total_seconds() / 3600
    if hours_until < untouchable_hours:
        return True, f"starts in <{untouchable_hours}h"
    return False, None


def _combine_uk(d: date, t: time) -> datetime:
    """Combine date + time and tag as Europe/London. tz-aware throughout the engine."""
    return datetime.combine(d, t).replace(tzinfo=UK_TZ)


# =====================================================================================
# Staff picker — applies hard constraints, ranks by soft preferences.
# =====================================================================================


def pick_staff(
    *,
    shift_start_dt: datetime,
    shift_end_dt: datetime,
    shift_type: ShiftType,
    staff: Iterable[User],
    shifts: Iterable[RosterShift],
    holidays: Iterable[EmployeeHoliday],
    settings: PlannerSettings,
    already_chosen_ids: set[int],
    proposed_hours_by_staff_week: dict[tuple[int, date], float],
) -> Optional[User]:
    """Choose the best eligible staff member, or None if every one is blocked.

    Hard constraints (any one → exclude):
      - `is_active=False`
      - `auto_assign_excluded=True`
      - already picked for this exact shift (multi-staff shift)
      - on holiday that day
      - existing weekly hours + proposed weekly hours + this shift > `max_hours_per_week`
      - < `min_rest_hours` since last shift ended

    Soft preferences (tiebreaker ranking, lower is better):
      - 0 if shift_type is in `preferred_shift_types`, else 1
      - Then: total weekly hours (existing + proposed) — load-balances
      - Then: user id — final deterministic tiebreaker for test stability
    """
    shift_date = shift_start_dt.date()
    week_start = iso_monday(shift_date)
    this_shift_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600

    eligible: list[User] = []
    for s in staff:
        if not s.is_active:
            continue
        if s.auto_assign_excluded:
            continue
        if s.id in already_chosen_ids:
            continue
        if is_staff_on_holiday(s.id, shift_date, holidays):
            continue
        existing_hours = weekly_hours_for(s.id, week_start, shifts)
        proposed_hours = proposed_hours_by_staff_week.get((s.id, week_start), 0)
        if existing_hours + proposed_hours + this_shift_hours > settings.max_hours_per_week:
            continue
        last_end = last_shift_end_for(s.id, shift_start_dt, shifts)
        if last_end is not None:
            rest_hours = (shift_start_dt - last_end).total_seconds() / 3600
            if rest_hours < settings.min_rest_hours:
                continue
        eligible.append(s)

    if not eligible:
        return None

    def score(candidate: User) -> tuple[int, float, int]:
        pref_match = 0 if (shift_type in (candidate.preferred_shift_types or [])) else 1
        total_hours = weekly_hours_for(candidate.id, week_start, shifts) + (
            proposed_hours_by_staff_week.get((candidate.id, week_start), 0)
        )
        return (pref_match, total_hours, candidate.id)

    return sorted(eligible, key=score)[0]


# =====================================================================================
# Main entry point — propose_roster.
# =====================================================================================


def propose_roster(
    *,
    bookings: Iterable[Booking],
    shifts: Iterable[RosterShift],
    staff: Iterable[User],
    holidays: Iterable[EmployeeHoliday],
    settings: PlannerSettings,
    now: datetime,
) -> dict:
    """Deterministic roster proposal.

    Same inputs → identical output (aside from `run_id`, which is UUID-derived — callers
    pass a stable value via `run_id_override` kwarg if full determinism is required in tests;
    see `_make_run_id`).

    Returned dict matches the `RosterProposalResponse` Pydantic schema in `models.py`.
    """
    shifts = list(shifts)
    staff = list(staff)
    holidays = list(holidays)
    bookings = list(bookings)

    run_id = _make_run_id(now, settings)
    window_start = now.date()
    window_end = window_start + timedelta(days=settings.window_days)

    # 1. Extract events from CONFIRMED bookings whose drop-off and/or pick-up fall in window.
    events: list[Event] = []
    for b in bookings:
        if b.status != BookingStatus.CONFIRMED:
            continue
        if window_start <= b.dropoff_date < window_end:
            events.append(
                Event(
                    booking_id=b.id,
                    booking_reference=b.reference,
                    event_type="drop_off",
                    event_time=_combine_uk(b.dropoff_date, b.dropoff_time),
                )
            )
        if window_start <= b.pickup_date < window_end:
            events.append(
                Event(
                    booking_id=b.id,
                    booking_reference=b.reference,
                    event_type="pick_up",
                    event_time=_combine_uk(b.pickup_date, b.pickup_time),
                )
            )

    # 2. Drop events already covered by untouchable shifts — the engine reports those
    #    shifts separately but won't re-plan their events.
    untouchable_shift_ids: set[int] = set()
    covered_booking_ids: set[int] = set()
    for s in shifts:
        unt, _reason = is_shift_untouchable(s, now, settings.untouchable_hours)
        if unt:
            untouchable_shift_ids.add(s.id)
            for linked in getattr(s, "bookings", []) or []:
                covered_booking_ids.add(linked.id)
    events = [e for e in events if e.booking_id not in covered_booking_ids]

    # 3. Cluster events by the gap rule.
    clusters = group_events_by_gap(events, settings.gap_max_minutes)

    # 4. Walk clusters, compute shift bounds + staffing, assign staff.
    proposed_shifts_out: list[dict] = []
    warnings: list[dict] = []
    proposed_hours_by_staff_week: dict[tuple[int, date], float] = {}
    buffer = timedelta(minutes=settings.buffer_minutes)

    for cluster in clusters:
        shift_start_dt = cluster.start - buffer
        shift_end_dt = cluster.end + buffer
        shift_type, is_custom = round_to_shift_type(shift_start_dt, shift_end_dt)
        peak = peak_concurrent_count(cluster.events, window_minutes=15)
        required = required_staff_count(peak, settings.staffing_thresholds)

        shift_date = shift_start_dt.date()
        shift_end_date = (
            shift_end_dt.date() if shift_end_dt.date() > shift_date else None
        )
        cluster_events_dicts = [
            {
                "booking_id": e.booking_id,
                "booking_reference": e.booking_reference,
                "event_type": e.event_type,
                "event_time": e.event_time,
            }
            for e in cluster.events
        ]

        already_chosen: set[int] = set()
        for _ in range(required):
            chosen = pick_staff(
                shift_start_dt=shift_start_dt,
                shift_end_dt=shift_end_dt,
                shift_type=shift_type,
                staff=staff,
                shifts=shifts,
                holidays=holidays,
                settings=settings,
                already_chosen_ids=already_chosen,
                proposed_hours_by_staff_week=proposed_hours_by_staff_week,
            )

            proposed_shifts_out.append(
                {
                    "kind": "new",
                    "shift_id": None,
                    "date": shift_date,
                    "end_date": shift_end_date,
                    "start_time": shift_start_dt.time(),
                    "end_time": shift_end_dt.time(),
                    "shift_type": shift_type.value,
                    "is_custom_range": is_custom,
                    "staff_id": chosen.id if chosen else None,
                    "staff_initials": (
                        f"{chosen.first_name[0]}{chosen.last_name[0]}".upper()
                        if chosen
                        else None
                    ),
                    "events": cluster_events_dicts,
                    "peak_concurrent_count": peak,
                    "required_staff_count": required,
                    "reason": (
                        f"{len(cluster.events)} event(s) within "
                        f"{settings.gap_max_minutes}-min gap; peak {peak} concurrent"
                    ),
                    "untouched_reason": None,
                }
            )

            if chosen is None:
                warnings.append(
                    {
                        "rule": "unmanned",
                        "severity": "warning",
                        "message": (
                            f"No eligible staff for shift on {shift_date} "
                            f"{shift_start_dt.time().strftime('%H:%M')}-"
                            f"{shift_end_dt.time().strftime('%H:%M')}"
                        ),
                        "booking_references": [
                            e.booking_reference for e in cluster.events
                        ],
                        "staff_id": None,
                    }
                )
            else:
                already_chosen.add(chosen.id)
                week_start = iso_monday(shift_date)
                proposed_hours_by_staff_week[(chosen.id, week_start)] = (
                    proposed_hours_by_staff_week.get((chosen.id, week_start), 0)
                    + (shift_end_dt - shift_start_dt).total_seconds() / 3600
                )

    # 5. Append untouchable existing shifts so the UI renders the full picture.
    for s in shifts:
        unt, reason = is_shift_untouchable(s, now, settings.untouchable_hours)
        if not unt:
            continue
        proposed_shifts_out.append(
            {
                "kind": "untouched_for_reason",
                "shift_id": s.id,
                "date": s.date,
                "end_date": s.end_date,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "shift_type": s.shift_type.value,
                "is_custom_range": False,
                "staff_id": s.staff_id,
                "staff_initials": getattr(s, "staff_initials", None),
                "events": [],
                "peak_concurrent_count": 0,
                "required_staff_count": 1,
                "reason": "existing shift — not proposed for change",
                "untouched_reason": reason,
            }
        )

    summary = {
        "new_shifts": sum(1 for p in proposed_shifts_out if p["kind"] == "new"),
        "extended_shifts": sum(1 for p in proposed_shifts_out if p["kind"] == "extend"),
        "untouched_shifts": sum(
            1 for p in proposed_shifts_out if p["kind"] == "untouched_for_reason"
        ),
        "unmanned_events": sum(
            1 for p in proposed_shifts_out if p["kind"] == "new" and p["staff_id"] is None
        ),
        "staff_hit_max_hours": sum(
            1 for w in warnings if w["rule"] == "max_hours_per_week"
        ),
    }

    return {
        "run_id": run_id,
        "generated_at": now,
        "window_start": window_start,
        "window_end": window_end,
        "proposed_shifts": proposed_shifts_out,
        "warnings": warnings,
        "summary": summary,
    }


def _make_run_id(now: datetime, settings: PlannerSettings) -> str:
    """Deterministic UUID derived from `now` + settings hash.

    Same inputs → same run_id. Tests rely on this for purity assertions.
    Production callers pass `datetime.now(UK_TZ)` so each run gets a fresh id.
    """
    seed = f"{now.isoformat()}|{settings.window_days}|{settings.gap_max_minutes}"
    return uuid.uuid5(uuid.NAMESPACE_URL, seed).hex
