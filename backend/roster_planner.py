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
    mixed_gap_max_minutes: int
    start_buffer_minutes: int
    end_buffer_minutes: int
    staffing_thresholds: tuple[dict, ...]
    max_hours_per_week: int
    min_rest_hours: int
    untouchable_hours: int
    min_shift_minutes: int

    @staticmethod
    def from_kv(rows: dict[str, object]) -> "PlannerSettings":
        """Build a PlannerSettings from a {key: parsed_value} map.

        The DB stores JSON-encoded strings; callers decode before calling this.
        Missing keys fall back to locked-2026-04-24 defaults so the engine never
        crashes on a partial settings row set.

        Buffer compat: the legacy single `buffer_minutes` key (symmetric)
        falls back to start_buffer_minutes / end_buffer_minutes when the
        new keys aren't present. Lets old DB rows keep working until they
        get rewritten by an admin PATCH or a data migration.
        """
        legacy_buffer = int(rows.get("buffer_minutes", 30))
        return PlannerSettings(
            window_days=int(rows.get("window_days", 28)),
            gap_max_minutes=int(rows.get("gap_max_minutes", 150)),
            mixed_gap_max_minutes=int(rows.get("mixed_gap_max_minutes", 150)),
            start_buffer_minutes=int(rows.get("start_buffer_minutes", 20 if "buffer_minutes" not in rows else legacy_buffer)),
            end_buffer_minutes=int(rows.get("end_buffer_minutes", 30 if "buffer_minutes" not in rows else legacy_buffer)),
            staffing_thresholds=tuple(
                rows.get(
                    "staffing_thresholds",
                    [{"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}],
                )
            ),
            max_hours_per_week=int(rows.get("max_hours_per_week", 40)),
            min_rest_hours=int(rows.get("min_rest_hours", 8)),
            untouchable_hours=int(rows.get("untouchable_hours", 24)),
            min_shift_minutes=int(rows.get("min_shift_minutes", 60)),
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
    # Enriched fields so the QA modal can drill into a shift and see the
    # job the engine assigned, matching the admin calendar's render.
    # All optional — engine logic doesn't depend on them.
    customer_name: Optional[str] = None
    flight_number: Optional[str] = None
    destination: Optional[str] = None  # destination for drop_off, origin for pick_up
    # Booking status at the time of proposal — 'confirmed' for engine-emitted
    # events (engine only plans for confirmed), or whatever's actually on the
    # saved shift's linked bookings for untouched_for_reason cards.
    status: Optional[str] = None


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
    events: Iterable[Event],
    gap_max_minutes: int,
    mixed_gap_max_minutes: Optional[int] = None,
) -> list[EventCluster]:
    """Group events into clusters by adjacent-event gap.

    Two thresholds — pick the one matching the event-type pair:
      - same-type gap (drop_off→drop_off, pick_up→pick_up): use `gap_max_minutes`
      - mixed-type gap (drop_off→pick_up, pick_up→drop_off): use `mixed_gap_max_minutes`

    The mixed threshold captures the round-trip efficiency: a driver doing a
    drop-off can pre-position pick-up cars on the same airport trip, so events
    that bridge the two types tolerate a wider gap than two same-type events.

    Both thresholds are inclusive — a gap of exactly the threshold keeps events
    in the same cluster, anything greater splits.

    `mixed_gap_max_minutes=None` falls back to `gap_max_minutes` for backwards
    compatibility (older callers that don't pass the new threshold).
    """
    if mixed_gap_max_minutes is None:
        mixed_gap_max_minutes = gap_max_minutes

    ordered = sorted(events, key=lambda e: e.event_time)
    if not ordered:
        return []

    clusters: list[EventCluster] = []
    current = [ordered[0]]
    for ev in ordered[1:]:
        gap_minutes = (ev.event_time - current[-1].event_time).total_seconds() / 60
        threshold = (
            mixed_gap_max_minutes
            if ev.event_type != current[-1].event_type
            else gap_max_minutes
        )
        if gap_minutes <= threshold:
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
        h.staff_id == staff_id and h.start_date <= day <= h.end_date for h in holidays
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


def shift_in_window(
    staff_member: User,
    shift_start_dt: datetime,
    shift_end_dt: datetime,
    end_overrun_minutes: int = 0,
) -> bool:
    """True if the shift fits inside the staff member's working window.

    NULL window (either bound unset) → always-open, returns True.

    A window with `preferred_end_time < preferred_start_time` wraps midnight
    (e.g. KW 16:00–01:00 next day). For overnight windows we accept a shift
    that fits in either today's window OR the previous day's window — the
    post-midnight tail.

    `end_overrun_minutes` extends the effective window end so a shift may
    run that many minutes past the jockey's preferred_end_time. Lets a
    17:00-window driver pick up a 13:40–17:55 shift (55 min over) without
    being filtered out — matches operational reality where the end_buffer
    on each shift naturally lands ~30 min past the last event.
    """
    pst = getattr(staff_member, "preferred_start_time", None)
    pet = getattr(staff_member, "preferred_end_time", None)
    if pst is None or pet is None:
        return True

    tz = shift_start_dt.tzinfo
    shift_date = shift_start_dt.date()
    overrun = timedelta(minutes=end_overrun_minutes)

    window_start = datetime.combine(shift_date, pst, tzinfo=tz)
    if pet > pst:
        window_end = datetime.combine(shift_date, pet, tzinfo=tz) + overrun
    else:
        window_end = datetime.combine(shift_date + timedelta(days=1), pet, tzinfo=tz) + overrun
    if window_start <= shift_start_dt and shift_end_dt <= window_end:
        return True

    # Overnight windows also cover shifts in the post-midnight tail.
    if pet < pst:
        prev_date = shift_date - timedelta(days=1)
        ws = datetime.combine(prev_date, pst, tzinfo=tz)
        we = datetime.combine(shift_date, pet, tzinfo=tz) + overrun
        if ws <= shift_start_dt and shift_end_dt <= we:
            return True

    return False


_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _initials(s: User) -> str:
    if s.first_name and s.last_name:
        return f"{s.first_name[0]}{s.last_name[0]}".upper()
    return f"#{s.id}"


def explain_unmanned(
    *,
    shift_start_dt: datetime,
    shift_end_dt: datetime,
    staff: Iterable[User],
    holidays: Iterable[EmployeeHoliday],
    settings: PlannerSettings,
    already_chosen_ids: set[int],
    proposed_hours_by_staff_week: dict[tuple[int, date], float],
    proposed_last_end_by_staff: dict[int, datetime],
) -> list[dict]:
    """Per-jockey reason for being excluded from this shift.

    Mirrors the hard-constraint order in `pick_staff()`. Inactive users,
    fleet drivers, and admins (driver_type=None) are silently skipped —
    they're not auto-assignable in any scenario, so listing them as
    "excluded" is noise. The output is intended for a debugging panel
    next to an `unmanned` warning.

    Like `pick_staff()`, this never reads saved `roster_shifts` — only
    the in-run state matters. See SPEC.md § Roster Planner.
    """
    shift_date = shift_start_dt.date()
    week_start = iso_monday(shift_date)
    this_shift_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600
    shift_weekday = shift_date.weekday()

    out: list[dict] = []
    for s in staff:
        if not s.is_active:
            continue
        if getattr(s, "driver_type", None) != "jockey":
            continue

        initials = _initials(s)

        if s.auto_assign_excluded:
            out.append({"initials": initials, "reason": "auto-assign disabled"})
            continue
        if shift_weekday in (getattr(s, "preferred_days_off", None) or []):
            out.append({
                "initials": initials,
                "reason": f"preferred day off ({_WEEKDAY_SHORT[shift_weekday]})",
            })
            continue
        if s.id in already_chosen_ids:
            out.append({"initials": initials, "reason": "already on this shift"})
            continue
        if is_staff_on_holiday(s.id, shift_date, holidays):
            out.append({"initials": initials, "reason": "on holiday"})
            continue
        proposed_hours = proposed_hours_by_staff_week.get((s.id, week_start), 0)
        if proposed_hours + this_shift_hours > settings.max_hours_per_week:
            out.append({
                "initials": initials,
                "reason": (
                    f"would exceed weekly cap "
                    f"({proposed_hours:.1f}h + {this_shift_hours:.1f}h > "
                    f"{settings.max_hours_per_week}h)"
                ),
            })
            continue
        last_end = proposed_last_end_by_staff.get(s.id)
        # Min rest only applies between calendar days — split shifts on
        # the same day are fine (no 8h gap required).
        if last_end is not None and last_end.date() != shift_start_dt.date():
            rest_hours = (shift_start_dt - last_end).total_seconds() / 3600
            if rest_hours < settings.min_rest_hours:
                out.append({
                    "initials": initials,
                    "reason": (
                        f"insufficient overnight rest "
                        f"({rest_hours:.1f}h < {settings.min_rest_hours}h required)"
                    ),
                })
                continue
        if not shift_in_window(s, shift_start_dt, shift_end_dt, getattr(s, "window_overrun_minutes", 60) or 60):
            pst = getattr(s, "preferred_start_time", None)
            pet = getattr(s, "preferred_end_time", None)
            window_str = (
                f"{pst.strftime('%H:%M')}–{pet.strftime('%H:%M')}"
                if pst and pet else "no window set"
            )
            out.append({
                "initials": initials,
                "reason": f"outside working window ({window_str})",
            })
            continue
        # Reaching here means hard constraints all pass — the only
        # remaining filter is the primary/fallback split. If a primary
        # was eligible we wouldn't be unmanned, so this must be a
        # fallback whose primary partner failed.
        if getattr(s, "is_fallback_driver", False):
            out.append({
                "initials": initials,
                "reason": "fallback only — no primary needed coverage in this window",
            })

    return out


def jockey_summary(
    staff: Iterable[User],
    holidays: Iterable[EmployeeHoliday],
    window_start: date,
    window_end: date,
    proposed_hours_by_staff_week: Optional[dict[tuple[int, date], float]] = None,
) -> list[dict]:
    """Snapshot of every active jockey's preferences, in-window holidays,
    and predicted hours per ISO week (Mon-anchored). Rendered in the QA
    panel below the run summary so admins can sanity-check assignments
    at a glance.

    `proposed_hours_by_staff_week` is the engine's in-run accumulator
    keyed by (staff_id, iso_monday). When passed, each jockey row gets
    a `predicted_hours_by_week` map (week_start_iso → hours) and a
    `predicted_hours_total` rolled up across the window.
    """
    holidays_by_staff: dict[int, list[EmployeeHoliday]] = {}
    for h in holidays:
        if h.start_date > window_end or h.end_date < window_start:
            continue
        holidays_by_staff.setdefault(h.staff_id, []).append(h)

    proposed_hours_by_staff_week = proposed_hours_by_staff_week or {}

    out: list[dict] = []
    for s in staff:
        if not s.is_active:
            continue
        if getattr(s, "driver_type", None) != "jockey":
            continue
        pst = getattr(s, "preferred_start_time", None)
        pet = getattr(s, "preferred_end_time", None)
        # Pull predicted hours for this jockey across every week we've
        # seen in this run. Sorted by week start so the UI can render
        # in chronological order without re-sorting.
        per_week = sorted(
            (
                (week_start, hours)
                for (sid, week_start), hours in proposed_hours_by_staff_week.items()
                if sid == s.id
            ),
            key=lambda kv: kv[0],
        )
        predicted_total = sum(h for _, h in per_week)
        out.append({
            "id": s.id,
            "initials": _initials(s),
            "first_name": s.first_name,
            "last_name": s.last_name,
            "preferred_start_time": pst,
            "preferred_end_time": pet,
            "is_fallback_driver": bool(getattr(s, "is_fallback_driver", False)),
            "window_overrun_minutes": int(getattr(s, "window_overrun_minutes", 60) or 60),
            "auto_assign_excluded": bool(s.auto_assign_excluded),
            "preferred_days_off": [
                _WEEKDAY_SHORT[d]
                for d in (getattr(s, "preferred_days_off", None) or [])
                if 0 <= d <= 6
            ],
            "holidays_in_window": [
                {"start_date": h.start_date, "end_date": h.end_date}
                for h in holidays_by_staff.get(s.id, [])
            ],
            "predicted_hours_by_week": [
                {"week_start": ws, "hours": round(h, 2)}
                for ws, h in per_week
            ],
            "predicted_hours_total": round(predicted_total, 2),
        })
    # Primaries first (alphabetical), fallbacks last.
    out.sort(key=lambda j: (j["is_fallback_driver"], j["first_name"] or ""))
    return out


def pick_staff(
    *,
    shift_start_dt: datetime,
    shift_end_dt: datetime,
    shift_type: ShiftType,
    staff: Iterable[User],
    holidays: Iterable[EmployeeHoliday],
    settings: PlannerSettings,
    already_chosen_ids: set[int],
    proposed_hours_by_staff_week: dict[tuple[int, date], float],
    proposed_last_end_by_staff: dict[int, datetime],
) -> Optional[User]:
    """Choose the best eligible staff member, or None if every one is blocked.

    Pure simulation: this function never consults saved `roster_shifts`.
    Weekly-hour and rest-gap checks use only in-run state — `proposed_*_by_*`
    dicts the caller threads through across `pick_staff` calls. See SPEC.md
    § Roster Planner for why (admins manually-edit the saved roster outside
    the engine; mixing that into availability decisions produces opaque
    warnings whose causes aren't visible in the preview UI).

    Hard constraints (any one → exclude):
      - `is_active=False`
      - `auto_assign_excluded=True`
      - `driver_type != 'jockey'` — only jockeys are auto-assigned. Fleet
        drivers handle taxi runs (future feature). NULL driver_type also
        excluded (admins, undecided).
      - `weekday(shift_date) ∈ preferred_days_off` — hard day-off rule.
      - already picked for this exact shift (multi-staff shift)
      - on holiday that day
      - in-run proposed weekly hours + this shift > `max_hours_per_week`
      - < `min_rest_hours` since this run's last assigned shift ended,
        BUT only when the prior shift ended on a different calendar day —
        same-day split shifts are allowed without an 8h gap.
      - shift not contained in driver's working window (`preferred_start_time`
        / `preferred_end_time`), allowing up to
        `users.window_overrun_minutes` past the preferred end time
        (per-driver, default 60) so the natural end-of-shift buffer
        doesn't disqualify a driver. Replaces the old shift-type bucket
        model.

    Selection (primary vs fallback):
      Eligible candidates split into `primaries` (`is_fallback_driver=False`)
      and `fallbacks` (`is_fallback_driver=True`). Fallbacks are only
      considered if no primary is eligible — e.g. KA (fallback) only fills
      in for MS / KW (primaries) when neither is available.

    Tiebreaker (lower is better):
      - total in-run weekly hours — load-balances within the run
      - first_name alphabetical — deterministic without using `id` as a
        ranking signal (true ties carry no semantic meaning, but tests need
        a stable choice).
    """
    shift_date = shift_start_dt.date()
    week_start = iso_monday(shift_date)
    this_shift_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600
    shift_weekday = shift_date.weekday()  # 0=Mon..6=Sun

    primaries: list[User] = []
    fallbacks: list[User] = []
    for s in staff:
        if not s.is_active:
            continue
        if s.auto_assign_excluded:
            continue
        if getattr(s, "driver_type", None) != "jockey":
            continue
        if shift_weekday in (getattr(s, "preferred_days_off", None) or []):
            continue
        if s.id in already_chosen_ids:
            continue
        if is_staff_on_holiday(s.id, shift_date, holidays):
            continue
        proposed_hours = proposed_hours_by_staff_week.get((s.id, week_start), 0)
        if proposed_hours + this_shift_hours > settings.max_hours_per_week:
            continue
        last_end = proposed_last_end_by_staff.get(s.id)
        # Min rest only applies between calendar days — split shifts on
        # the same day are fine (no 8h gap required).
        if last_end is not None and last_end.date() != shift_start_dt.date():
            rest_hours = (shift_start_dt - last_end).total_seconds() / 3600
            if rest_hours < settings.min_rest_hours:
                continue
        if not shift_in_window(s, shift_start_dt, shift_end_dt, getattr(s, "window_overrun_minutes", 60) or 60):
            continue

        if getattr(s, "is_fallback_driver", False):
            fallbacks.append(s)
        else:
            primaries.append(s)

    pool = primaries if primaries else fallbacks
    if not pool:
        return None

    def score(candidate: User) -> tuple[float, str]:
        total_hours = proposed_hours_by_staff_week.get((candidate.id, week_start), 0)
        return (total_hours, candidate.first_name or "")

    return sorted(pool, key=score)[0]


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
        customer_name = (
            f"{getattr(b, 'customer_first_name', '') or ''} "
            f"{getattr(b, 'customer_last_name', '') or ''}".strip() or None
        )
        if window_start <= b.dropoff_date < window_end:
            events.append(
                Event(
                    booking_id=b.id,
                    booking_reference=b.reference,
                    event_type="drop_off",
                    event_time=_combine_uk(b.dropoff_date, b.dropoff_time),
                    customer_name=customer_name,
                    flight_number=getattr(b, "dropoff_flight_number", None),
                    destination=getattr(b, "dropoff_destination", None),
                    status="confirmed",
                )
            )
        if window_start <= b.pickup_date < window_end:
            # Pick-up shift anchors to the *flight arrival time*, not the
            # customer-meet time (= arrival + 30). The jockey needs to be
            # at the airport before the plane lands so the car is ready
            # when the customer comes through.
            #   event_time = arrival_time (preferred) | pickup_time - 30 (fallback)
            # Downstream: shift_start = event_time - start_buffer
            # so a 20-min start_buffer puts the jockey on duty 20 min
            # before the plane lands.
            arrival_t = getattr(b, "flight_arrival_time", None)
            if arrival_t is not None:
                anchor_time = _combine_uk(b.pickup_date, arrival_t)
            else:
                anchor_time = _combine_uk(b.pickup_date, b.pickup_time) - timedelta(minutes=30)
            events.append(
                Event(
                    booking_id=b.id,
                    booking_reference=b.reference,
                    event_type="pick_up",
                    event_time=anchor_time,
                    customer_name=customer_name,
                    flight_number=getattr(b, "pickup_flight_number", None),
                    destination=getattr(b, "pickup_origin", None),
                    status="confirmed",
                )
            )

    # 2. Cluster events by the gap rule. The engine plans every booking
    #    in window from a clean slate — saved roster_shifts are NOT used
    #    to skip events. (Pre-rebuild the engine could mute clusters
    #    "covered" by untouchable shifts; that conflated availability
    #    with reality and produced opaque proposals. See SPEC.md.)
    clusters = group_events_by_gap(
        events,
        settings.gap_max_minutes,
        mixed_gap_max_minutes=settings.mixed_gap_max_minutes,
    )

    # 3. Walk clusters, compute shift bounds + staffing, assign staff.
    proposed_shifts_out: list[dict] = []
    warnings: list[dict] = []
    proposed_hours_by_staff_week: dict[tuple[int, date], float] = {}
    proposed_last_end_by_staff: dict[int, datetime] = {}
    start_buffer = timedelta(minutes=settings.start_buffer_minutes)
    end_buffer = timedelta(minutes=settings.end_buffer_minutes)

    for cluster in clusters:
        shift_start_dt = cluster.start - start_buffer
        shift_end_dt = cluster.end + end_buffer
        # Min shift length — extend the END (not the start) when the
        # buffered window is shorter than the floor. A single drop-off
        # at 13:00 with 20/30 buffer would otherwise give 12:40-13:30
        # (50 min); we extend to 12:40-13:40.
        min_duration = timedelta(minutes=settings.min_shift_minutes)
        if shift_end_dt - shift_start_dt < min_duration:
            shift_end_dt = shift_start_dt + min_duration
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
                "customer_name": e.customer_name,
                "flight_number": e.flight_number,
                "destination": e.destination,
                "status": e.status,
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
                holidays=holidays,
                settings=settings,
                already_chosen_ids=already_chosen,
                proposed_hours_by_staff_week=proposed_hours_by_staff_week,
                proposed_last_end_by_staff=proposed_last_end_by_staff,
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
                exclusions = explain_unmanned(
                    shift_start_dt=shift_start_dt,
                    shift_end_dt=shift_end_dt,
                    staff=staff,
                    holidays=holidays,
                    settings=settings,
                    already_chosen_ids=already_chosen,
                    proposed_hours_by_staff_week=proposed_hours_by_staff_week,
                    proposed_last_end_by_staff=proposed_last_end_by_staff,
                )
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
                        "exclusions": exclusions,
                    }
                )
            else:
                already_chosen.add(chosen.id)
                week_start = iso_monday(shift_date)
                proposed_hours_by_staff_week[(chosen.id, week_start)] = (
                    proposed_hours_by_staff_week.get((chosen.id, week_start), 0)
                    + (shift_end_dt - shift_start_dt).total_seconds() / 3600
                )
                # Track this run's last end per jockey so the next pick
                # respects min_rest_hours against in-run picks (not against
                # saved roster_shifts).
                prior_end = proposed_last_end_by_staff.get(chosen.id)
                if prior_end is None or shift_end_dt > prior_end:
                    proposed_last_end_by_staff[chosen.id] = shift_end_dt

    # 5. Append untouchable existing shifts so the UI renders the full picture.
    for s in shifts:
        unt, reason = is_shift_untouchable(s, now, settings.untouchable_hours)
        if not unt:
            continue
        # Surface the linked bookings on the saved shift so the planner UI
        # can render them on the card (matches the admin Calendar's render).
        # Each booking produces an event for whichever side (drop-off / pick-up)
        # falls within the shift's date range. Status is included verbatim so
        # the UI can distinguish e.g. refunded bookings with the REFUNDED pill.
        shift_dates = {s.date}
        if s.end_date and s.end_date != s.date:
            shift_dates.add(s.end_date)
        untouched_events: list[dict] = []
        for b in getattr(s, "bookings", None) or []:
            b_status = (
                b.status.value if getattr(b, "status", None) is not None
                and hasattr(b.status, "value") else getattr(b, "status", None)
            )
            customer_name = (
                f"{getattr(b, 'customer_first_name', '') or ''} "
                f"{getattr(b, 'customer_last_name', '') or ''}".strip() or None
            )
            d_date = getattr(b, "dropoff_date", None)
            d_time = getattr(b, "dropoff_time", None)
            p_date = getattr(b, "pickup_date", None)
            p_time = getattr(b, "pickup_time", None)
            if d_date in shift_dates and d_time:
                untouched_events.append({
                    "booking_id": b.id,
                    "booking_reference": getattr(b, "reference", "") or "",
                    "event_type": "drop_off",
                    "event_time": _combine_uk(d_date, d_time),
                    "customer_name": customer_name,
                    "flight_number": getattr(b, "dropoff_flight_number", None),
                    "destination": getattr(b, "dropoff_destination", None),
                    "status": b_status,
                })
            elif p_date in shift_dates and p_time:
                untouched_events.append({
                    "booking_id": b.id,
                    "booking_reference": getattr(b, "reference", "") or "",
                    "event_type": "pick_up",
                    "event_time": _combine_uk(p_date, p_time),
                    "customer_name": customer_name,
                    "flight_number": getattr(b, "pickup_flight_number", None),
                    "destination": getattr(b, "pickup_origin", None),
                    "status": b_status,
                })
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
                "events": untouched_events,
                "peak_concurrent_count": 0,
                "required_staff_count": 1,
                "reason": "existing shift — not proposed for change",
                "untouched_reason": reason,
                "created_source": getattr(s, "created_source", "manual") or "manual",
                "planner_run_id": getattr(s, "planner_run_id", None),
            }
        )

    # Dedupe: when a `new` proposal has the same (date, start, end, staff_id)
    # as an `untouched_for_reason` row, the existing live shift already
    # covers it — drop the new one to avoid showing two cards for the same
    # actual shift. Keeps clean-slate planning logic intact; just cleans up
    # the output presentation. Without this, the FE shows e.g. two LN cards
    # at 04:30-06:45 when LN already has a committed shift there. See
    # 2026-05-01 user report.
    untouched_keys = {
        (p["date"], p["start_time"], p["end_time"], p["staff_id"])
        for p in proposed_shifts_out
        if p["kind"] == "untouched_for_reason"
    }
    proposed_shifts_out = [
        p for p in proposed_shifts_out
        if not (
            p["kind"] == "new"
            and (p["date"], p["start_time"], p["end_time"], p["staff_id"]) in untouched_keys
        )
    ]

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
        "jockeys": jockey_summary(
            staff, holidays, window_start, window_end,
            proposed_hours_by_staff_week=proposed_hours_by_staff_week,
        ),
        "max_hours_per_week": settings.max_hours_per_week,
    }


def _make_run_id(now: datetime, settings: PlannerSettings) -> str:
    """Deterministic UUID derived from `now` + settings hash.

    Same inputs → same run_id. Tests rely on this for purity assertions.
    Production callers pass `datetime.now(UK_TZ)` so each run gets a fresh id.
    """
    seed = f"{now.isoformat()}|{settings.window_days}|{settings.gap_max_minutes}"
    return uuid.uuid5(uuid.NAMESPACE_URL, seed).hex
