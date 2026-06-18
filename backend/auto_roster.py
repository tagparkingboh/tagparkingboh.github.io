"""
Auto-roster: live shift coverage for inbound bookings.

Replaces the old Phase-3 commit pipeline (see SPEC.md "Roster Planner v2").
The pure-simulation engine in `roster_planner.py` is reused for *clustering*;
this module owns the live-write path.

Design (refactor 2026-05-02 — supersedes the per-event extend approach):

  We rebuild the affected day(s) from scratch using the engine's
  `group_events_by_gap` clusterer, instead of extending shifts edge-to-edge
  per booking event. The earlier extend logic produced violations of the
  consecutive-event gap rule (an event 2h from the shift edge is actually
  2h+end_buffer from the nearest event) and didn't handle cross-midnight
  end-date updates correctly. Per-day rebuild eliminates both.

Rules in effect:
  - Auto-shifts are tagged `created_source='auto'`. Only auto-shifts that
    are still SCHEDULED + unassigned are rebuilt — anything an admin has
    claimed or confirmed is preserved untouched.
  - Refunded bookings are INCLUDED in the rebuild source (per the user's
    2026-05 distinction: refund = "we offered poor service", customer may
    still park, shift coverage stays).
  - Cancelled bookings are EXCLUDED — those customers are gone.
  - Park & Ride bookings are excluded — no jockey work.
  - Pick-up event time anchors to `flight_arrival_time` when set; falls
    back to `pickup_time - 30min` (matches the engine).
  - Buffers and gap thresholds come from `roster_planner_settings`
    (the live values, not hardcoded defaults).

Failure isolation: callers wrap in BackgroundTasks and the function
swallows DB errors so a planner side-effect can never break the
confirmation/cancellation flow that triggered it.
"""

from __future__ import annotations

import logging
from datetime import date as date_type, datetime, time as time_type, timedelta
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db_models import (
    Booking,
    BookingStatus,
    RosterShift,
    RosterWindowTemplate,
    ServiceType,
    ShiftBookingLink,
    ShiftStatus,
)
from roster_planner import (
    ARRIVAL_OVERNIGHT_CUTOFF,
    Event,
    EventCluster,
    PlannerSettings,
    UK_TZ,
    compute_cluster_shift_window,
    group_events_by_gap,
    round_to_shift_type,
)
from roster_effective_date import get_roster_effective_date

logger = logging.getLogger(__name__)


def _scalar_value(value):
    return value.value if hasattr(value, "value") else value


# ---------------------------------------------------------------------------
# Event extraction (pure)
# ---------------------------------------------------------------------------

def _events_for_booking(booking: Booking) -> list[tuple[str, datetime, datetime]]:
    """Return (event_type, start_anchor, end_anchor) tuples.

    - **Drop-off**: start_anchor == end_anchor == dropoff_time. The handoff
      happens at the moment the customer arrives, so both ends of the shift
      window pivot off the same time.
    - **Pickup**: start_anchor = flight_arrival_time (jockey must be at the
      airport before the plane lands so the car is ready). end_anchor =
      start_anchor + 30 min — the standard arrival→handoff offset, derived
      rather than read from `pickup_time`. The engine pivots on a single
      canonical event (the flight landing); the +30 buffer plus the
      configured end_buffer give the jockey time to actually hand the car
      over. Decision locked 2026-05-20: customer-facing time is the flight
      landing, not a separately-stored handoff timestamp.

    Calendar day for the flight:
      * Prefer `flight_arrival_date` when set (canonical, populated on every
        booking from 2026-05-20 onward).
      * Legacy fallback for nullable rows: `flight_arrival_time > pickup_time`
        means the flight landed the previous calendar day (overnight landing
        with rolled-forward pickup_date).

    Returned datetimes are naive (no tz) — the DB columns are naive too;
    we attach UK_TZ when handing off to the clusterer.
    """
    out: list[tuple[str, datetime, datetime]] = []
    if booking.dropoff_date and booking.dropoff_time:
        dropoff_dt = datetime.combine(booking.dropoff_date, booking.dropoff_time)
        out.append(("drop_off", dropoff_dt, dropoff_dt))
    if booking.pickup_date:
        flight_arrival_time = getattr(booking, "flight_arrival_time", None)
        start_anchor: Optional[datetime] = None
        if flight_arrival_time:
            flight_date = getattr(booking, "flight_arrival_date", None)
            if flight_date is None:
                # Legacy row (pre-flight_arrival_date column). Re-derive the
                # calendar day from the overnight-rollover heuristic.
                flight_date = booking.pickup_date
                if booking.pickup_time and flight_arrival_time > booking.pickup_time:
                    flight_date = booking.pickup_date - timedelta(days=1)
            start_anchor = datetime.combine(flight_date, flight_arrival_time)
        elif booking.pickup_time:
            # Very old rows with no flight_arrival_time at all — derive the
            # landing time as pickup_time minus the standard 30-min handoff.
            start_anchor = datetime.combine(booking.pickup_date, booking.pickup_time) - timedelta(minutes=30)
        if start_anchor is not None:
            end_anchor = start_anchor + timedelta(minutes=30)
            out.append(("pick_up", start_anchor, end_anchor))
    return out


def _shift_window(shift: RosterShift) -> tuple[datetime, datetime]:
    """Naive [start, end] datetimes for an existing shift (handles overnight)."""
    end_date = shift.end_date or shift.date
    if not shift.end_date and shift.end_time <= shift.start_time:
        end_date = shift.date + timedelta(days=1)
    return (
        datetime.combine(shift.date, shift.start_time),
        datetime.combine(end_date, shift.end_time),
    )


def _windows_overlap(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    """True when two wall-clock windows overlap or touch."""
    return a[0] <= b[1] and b[0] <= a[1]


def _shift_linked_booking_ids(shift: RosterShift) -> set[int]:
    """Best-effort booking ids already attached to a shift."""
    ids: set[int] = set()
    booking_id = getattr(shift, "booking_id", None)
    if booking_id is not None:
        ids.add(booking_id)
    for booking in getattr(shift, "bookings", []) or []:
        bid = getattr(booking, "id", None)
        if bid is not None:
            ids.add(bid)
    return ids


def _is_auto_shift_eligible_for_rebuild(shift: RosterShift) -> bool:
    """Untouched auto-shift = created_source='auto', staff_id NULL,
    admin_shaped_at NULL, SCHEDULED. Anything else is admin territory —
    preserve it. (Driver-trust pivot 2026-05-28 added the
    `admin_shaped_at IS NULL` clause: split/merge/duplicate/direct time
    edits stamp this column, freezing the row.)"""
    return (
        getattr(shift, "created_source", None) == "auto"
        and shift.staff_id is None
        and getattr(shift, "admin_shaped_at", None) is None
        and shift.status == ShiftStatus.SCHEDULED
    )


def _shift_can_cover_jockey_work(shift: RosterShift) -> bool:
    """Auto-roster events are jockey work. Fleet shifts must not be treated
    as coverage for jockey bookings; legacy NULL rows are treated as jockey."""
    driver_type = getattr(shift, "intended_driver_type", None)
    return driver_type in (None, "", "jockey")


def _booking_in_scope(booking: Booking) -> bool:
    """Bookings the auto-roster covers: jockey work (not P&R) with status
    in CONFIRMED or REFUNDED. CANCELLED / PENDING are excluded."""
    if _scalar_value(getattr(booking, "service_type", None)) == ServiceType.PARK_RIDE.value:
        return False
    return _scalar_value(getattr(booking, "status", None)) in (
        BookingStatus.CONFIRMED.value,
        BookingStatus.REFUNDED.value,
    )


def _review_event_key(booking_id: int, event_type: str) -> str:
    return f"{booking_id}:{event_type}"


def _pickup_event_date(booking: Booking) -> Optional[date_type]:
    if getattr(booking, "flight_arrival_date", None):
        return booking.flight_arrival_date
    if not getattr(booking, "pickup_date", None):
        return None
    if (
        getattr(booking, "flight_arrival_time", None)
        and getattr(booking, "pickup_time", None)
        and booking.flight_arrival_time > booking.pickup_time
    ):
        return booking.pickup_date - timedelta(days=1)
    return booking.pickup_date


def _shift_linked_event_keys(shift: RosterShift) -> set[str]:
    shift_dates = {getattr(shift, "date", None), getattr(shift, "end_date", None)}
    shift_dates.discard(None)
    keys: set[str] = set()

    for booking in getattr(shift, "bookings", []) or []:
        if _scalar_value(getattr(booking, "status", None)) == BookingStatus.CANCELLED.value:
            continue
        bid = getattr(booking, "id", None)
        if bid is None:
            continue
        if getattr(booking, "dropoff_date", None) in shift_dates:
            keys.add(_review_event_key(bid, "drop_off"))
        elif _pickup_event_date(booking) in shift_dates:
            keys.add(_review_event_key(bid, "pick_up"))

    booking_id = getattr(shift, "booking_id", None)
    booking = getattr(shift, "booking", None)
    if booking_id is not None and booking is not None:
        if _scalar_value(getattr(booking, "status", None)) != BookingStatus.CANCELLED.value:
            if getattr(booking, "dropoff_date", None) in shift_dates:
                keys.add(_review_event_key(booking_id, "drop_off"))
            elif _pickup_event_date(booking) in shift_dates:
                keys.add(_review_event_key(booking_id, "pick_up"))

    return keys


def _review_operational_date(event_type: str, event_time: datetime) -> date_type:
    if event_type == "pick_up" and event_time.time() < ARRIVAL_OVERNIGHT_CUTOFF:
        return event_time.date() - timedelta(days=1)
    return event_time.date()


def _cluster_shift_plan(cluster, settings: PlannerSettings) -> dict:
    """Shared generated-shift window/date calculation for rebuild and sweep."""
    cluster_start = cluster.events[0].event_time
    shift_start, shift_end = compute_cluster_shift_window(
        cluster,
        start_buffer_minutes=settings.start_buffer_minutes,
        end_buffer_minutes=settings.end_buffer_minutes,
        min_shift_minutes=settings.min_shift_minutes,
    )
    shift_start = shift_start.replace(tzinfo=None)
    shift_end = shift_end.replace(tzinfo=None)
    shift_type, _ = round_to_shift_type(shift_start, shift_end)

    earliest_event = min(cluster.events, key=lambda e: e.event_time)
    if (
        earliest_event.event_type == "pick_up"
        and cluster_start.time() < ARRIVAL_OVERNIGHT_CUTOFF
    ):
        shift_date_val = cluster_start.date() - timedelta(days=1)
        shift_end_date_val = (
            shift_end.date() if shift_end.date() != shift_date_val else None
        )
    else:
        shift_date_val = shift_start.date()
        shift_end_date_val = (
            shift_end.date() if shift_end.date() != shift_start.date() else None
        )

    return {
        "cluster_start": cluster_start,
        "shift_start": shift_start,
        "shift_end": shift_end,
        "shift_date": shift_date_val,
        "shift_end_date": shift_end_date_val,
        "shift_type": shift_type,
    }


def _cluster_fully_covered_by_shifts(
    cluster_events,
    frozen_shifts: list[RosterShift],
    settings: PlannerSettings,
) -> list[RosterShift]:
    """Return the frozen shifts that jointly cover every event in the cluster.

    Combined coverage counts: events may be split across several owned,
    jockey-capable shifts (2026-06-12 incident: a day hand-staffed with three
    admin-shaped shifts grew a redundant 10-booking auto shift because the
    old check demanded ONE shift spanning the entire cluster window —
    shift 5505 / TAG-XTD95525).

    The buffer rules are preserved by re-running the engine's own window
    math per covering shift: each event is assigned to the first owned shift
    (by start time) whose window contains its anchors, then every shift must
    span `compute_cluster_shift_window` of its OWN subset of events — so
    start/end buffers, tight-pair extensions, and the min-shift floor apply
    exactly as they would if that subset were generated. A single shift
    covering the whole cluster therefore behaves identically to the old
    whole-window check. Returns [] when any event is uncovered or any
    covering shift fails its subset's buffered window.
    """
    if not frozen_shifts:
        return []
    eligible = [
        (fs, _shift_window(fs))
        for fs in frozen_shifts
        if _shift_can_cover_jockey_work(fs)
    ]
    if not eligible:
        return []
    eligible.sort(key=lambda pair: pair[1][0])

    assigned: dict = {}
    for event in sorted(cluster_events, key=lambda e: e.event_time):
        event_start = event.event_time.replace(tzinfo=None)
        event_end = (event.end_anchor_time or event.event_time).replace(tzinfo=None)
        for fs, (fs_start, fs_end) in eligible:
            if fs_start <= event_start and event_end <= fs_end:
                key = getattr(fs, "id", None) or id(fs)
                bucket = assigned.setdefault(key, (fs, (fs_start, fs_end), []))
                bucket[2].append(event)
                break
        else:
            # This event has no owned shift containing it — cluster must be
            # materialised.
            return []

    covering: list[RosterShift] = []
    for fs, (fs_start, fs_end), subset_events in assigned.values():
        sub_start, sub_end = compute_cluster_shift_window(
            EventCluster(events=subset_events),
            start_buffer_minutes=settings.start_buffer_minutes,
            end_buffer_minutes=settings.end_buffer_minutes,
            min_shift_minutes=settings.min_shift_minutes,
        )
        sub_start = sub_start.replace(tzinfo=None)
        sub_end = sub_end.replace(tzinfo=None)
        if not (fs_start <= sub_start and sub_end <= fs_end):
            return []
        covering.append(fs)
    return covering


def _cluster_suppression_blockers(
    booking_ids: set[int],
    required_start: datetime,
    required_end: datetime,
    suppressed_shifts: list[RosterShift],
) -> list[RosterShift]:
    """Cancelled/suppressed auto shift = do not recreate this coverage."""
    if not suppressed_shifts:
        return []
    blockers = []
    required_window = (required_start, required_end)
    for s in suppressed_shifts:
        suppressed_start, suppressed_end = _shift_window(s)
        if suppressed_start <= required_window[0] and required_window[1] <= suppressed_end:
            blockers.append(s)
            continue
        if _shift_linked_booking_ids(s) & booking_ids:
            blockers.append(s)
    return blockers


def _format_dt(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def _booking_confirmation_marker(booking: Booking) -> dict:
    payment = getattr(booking, "payment", None)
    paid_at = getattr(payment, "paid_at", None) if payment is not None else None
    if isinstance(paid_at, datetime):
        return {"source": "payment.paid_at", "timestamp": _format_dt(paid_at)}
    confirmation_email_sent_at = getattr(booking, "confirmation_email_sent_at", None)
    if isinstance(confirmation_email_sent_at, datetime):
        return {
            "source": "booking.confirmation_email_sent_at",
            "timestamp": _format_dt(confirmation_email_sent_at),
        }
    created_at = getattr(booking, "created_at", None)
    return {
        "source": "booking.created_at" if isinstance(created_at, datetime) else None,
        "timestamp": _format_dt(created_at),
    }


# ---------------------------------------------------------------------------
# Rebuild — core
# ---------------------------------------------------------------------------

def _rebuild_cluster_auto_for_dates(
    db: Session,
    target_dates: Iterable[date_type],
    settings: PlannerSettings,
    focus_booking_id: Optional[int] = None,
) -> dict:
    """Wipe + recreate every auto-shift whose start date is in `target_dates`.

    Steps:
      1. Delete every untouched auto-shift on target dates (cascades the
         shift_booking_links rows).
      2. Pull every CONFIRMED + REFUNDED booking with at least one event
         in the expanded window (target ± 1 day so cross-midnight clusters
         are caught).
      3. Cluster the events using the engine's `group_events_by_gap`
         (consecutive-event semantics — the rule the user actually wants).
      4. For each cluster whose first event sits on a target date, create
         a new auto-shift sized [first_event - start_buffer, last_event +
         end_buffer], floored to `min_shift_minutes`. Link every booking
         in the cluster to it.

    When `focus_booking_id` is supplied (the booking-confirmation/edit path),
    only clusters containing that booking are materialised, and only existing
    untouched auto-shifts overlapping/linked to those clusters are deleted.
    This keeps a late booking from resurrecting unrelated auto-shifts that an
    admin already deleted on the same date. Operator-triggered regenerate
    leaves `focus_booking_id=None` and keeps full force-rebuild semantics.

    Returns a counts dict so callers can log / surface a banner.
    """
    summary = {
        "deleted": 0, "created": 0, "skipped_covered": 0,
        "skipped_suppressed": 0, "bookings_in_scope": 0, "events": 0,
        "rescued": 0,
    }
    target_set = set(target_dates)
    if not target_set:
        return summary

    # 1a. Expand target_set to include any neighbour day hosting an existing
    # untouched auto-shift whose window touches our scope. Without this, a
    # cross-midnight cluster anchored on D-1 stays intact when a new booking
    # whose pickup lands on D (and within gap_max_minutes of D-1's events) is
    # confirmed — the existing shift never gets rebuilt to include the new
    # booking. Real example caught on staging 2026-05-20: TAG-HBD80857 with
    # pickup 9 Jul 02:00 should have joined the existing 8→9 Jul shift via
    # the 190-min gap rule, but didn't because 8 Jul wasn't in target_set.
    neighbour_dates: set[date_type] = set()
    for d in target_set:
        neighbour_dates.add(d - timedelta(days=1))
        neighbour_dates.add(d + timedelta(days=1))
    if neighbour_dates:
        adjacent = (
            db.query(RosterShift)
            .filter(
                RosterShift.created_source == "auto",
                RosterShift.staff_id.is_(None),
                RosterShift.admin_shaped_at.is_(None),
                RosterShift.status == ShiftStatus.SCHEDULED,
                or_(
                    RosterShift.date.in_(neighbour_dates),
                    RosterShift.end_date.in_(neighbour_dates),
                ),
            )
            .all()
        )
        for s in adjacent:
            target_set.add(s.date)
            if s.end_date:
                target_set.add(s.end_date)

    # 1b. Delete untouched auto-shifts in scope.
    # Driver-trust rule (2026-05-28): a row is "owned" (and therefore
    # immune to wipe) when ANY of these are true:
    #   - staff_id IS NOT NULL              (assigned / claimed)
    #   - admin_shaped_at IS NOT NULL       (split / merged / duplicated / time-edited)
    #   - created_source != 'auto'          (manual / planner)
    # The filter below is the only-eligible-for-wipe predicate.
    focus_delete_candidates: list[RosterShift] = []
    deleted_shift_ids: set[int] = set()
    if focus_booking_id is None:
        existing = (
            db.query(RosterShift)
            .filter(
                RosterShift.created_source == "auto",
                RosterShift.staff_id.is_(None),
                RosterShift.admin_shaped_at.is_(None),
                RosterShift.status == ShiftStatus.SCHEDULED,
                RosterShift.date.in_(target_set),
            )
            .all()
        )
        for s in existing:
            db.delete(s)
            summary["deleted"] += 1
        if summary["deleted"]:
            db.flush()
    else:
        focus_delete_scope_dates = set(target_set)
        for d in target_set:
            focus_delete_scope_dates.add(d - timedelta(days=1))
            focus_delete_scope_dates.add(d + timedelta(days=1))
        focus_delete_candidates = (
            db.query(RosterShift)
            .filter(
                RosterShift.created_source == "auto",
                RosterShift.staff_id.is_(None),
                RosterShift.admin_shaped_at.is_(None),
                RosterShift.status == ShiftStatus.SCHEDULED,
                or_(
                    RosterShift.date.in_(focus_delete_scope_dates),
                    RosterShift.end_date.in_(focus_delete_scope_dates),
                ),
            )
            .all()
        )

    # 2. Pull bookings whose events MAY land in scope (±1 day for overnight).
    expanded = set()
    for d in target_set:
        expanded.add(d)
        expanded.add(d - timedelta(days=1))
        expanded.add(d + timedelta(days=1))

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.REFUNDED]),
            or_(
                Booking.dropoff_date.in_(expanded),
                Booking.pickup_date.in_(expanded),
            ),
        )
        .all()
    )
    bookings = [b for b in bookings if _booking_in_scope(b)]
    summary["bookings_in_scope"] = len(bookings)

    # 3. Build engine Event objects (UK-tz-aware so group_events_by_gap
    # behaves identically to the shadow-mode engine). Each event carries
    # both a start anchor (clustering + shift_start) and an end anchor
    # (shift_end). Drop-offs share the same anchor on both sides; pickups
    # have asymmetric anchors so shift_end = pickup_time + end_buffer.
    all_events: list[Event] = []
    for b in bookings:
        for et, start_dt, end_dt in _events_for_booking(b):
            all_events.append(
                Event(
                    booking_id=b.id,
                    booking_reference=b.reference or "",
                    event_type=et,
                    event_time=start_dt.replace(tzinfo=UK_TZ),
                    end_anchor_time=end_dt.replace(tzinfo=UK_TZ),
                )
            )
    summary["events"] = len(all_events)
    if not all_events:
        db.commit()
        return summary

    clusters = group_events_by_gap(
        all_events,
        gap_max_minutes=settings.gap_max_minutes,
        mixed_gap_max_minutes=settings.mixed_gap_max_minutes,
    )

    # 3b. Pull existing FROZEN shifts in scope so the cluster loop can skip
    # materialising a duplicate auto-shift over a window that's already
    # covered by something owned. "Frozen" here = any shift the auto path
    # is not allowed to reshape:
    #   - any manual shift (created_source != 'auto')
    #   - any auto shift that's owned (staff_id IS NOT NULL)
    #   - any auto shift that's been admin-shaped (admin_shaped_at IS NOT NULL)
    # Auto-link writes its own ShiftBookingLink rows for bookings that fall
    # inside these windows in a separate background task; the rebuild just
    # needs to know they're there so it doesn't spawn ghost duplicates over
    # the same coverage. (Driver-trust pivot 2026-05-28.)
    frozen_scope_dates = set(target_set)
    for d in target_set:
        frozen_scope_dates.add(d - timedelta(days=1))
        frozen_scope_dates.add(d + timedelta(days=1))
    # Match auto_link's status filter (SCHEDULED + CONFIRMED only) so the
    # rebuild's freeze pool and the link pool agree. If we included
    # IN_PROGRESS here, an in-progress frozen shift could cause the
    # rebuild to skip materialising a cluster, but auto_link would refuse
    # to link to it (status filter mismatch) — leaving the booking with
    # no shift coverage at all. Code-review finding 2026-05-28.
    frozen_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.status.in_([
                ShiftStatus.SCHEDULED,
                ShiftStatus.CONFIRMED,
            ]),
            or_(
                RosterShift.created_source != "auto",
                RosterShift.staff_id.isnot(None),
                RosterShift.admin_shaped_at.isnot(None),
            ),
            or_(
                RosterShift.date.in_(frozen_scope_dates),
                RosterShift.end_date.in_(frozen_scope_dates),
            ),
        )
        .all()
    )
    suppressed_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.status == ShiftStatus.CANCELLED,
            RosterShift.suppressed_at.isnot(None),
            or_(
                RosterShift.date.in_(frozen_scope_dates),
                RosterShift.end_date.in_(frozen_scope_dates),
            ),
        )
        .all()
    )

    # 4. Materialise shifts for clusters whose owner lands in target_set.
    # Usually that owner is the event anchor date. For arrivals before the
    # 02:00 operational cutoff, the owner is the prior operational day, so a
    # 26 Jun rebuild must recreate a 27 Jun 00:35 pickup shift dated 26 Jun.
    #
    # Orphan rescue (2026-06-12 incident, TAG-GIR11546 → shift 5263): the
    # focus-delete pass may remove a shift via a SHARED booking whose other
    # event lives on it alongside other bookings. Those bookings' clusters
    # don't contain the focus booking, so they were never re-materialised —
    # leaving covered events orphaned. Every booking that loses a shift in a
    # delete goes into `rescue_pool`; after the focus clusters are built, any
    # unprocessed cluster containing a rescued booking is materialised too,
    # cascading until nothing new is orphaned. Suppression is still honoured.
    materialised_keys: set = set()
    rescue_pool: set[int] = set()
    deleted_windows: list = []

    def _cluster_key(cluster):
        return tuple(sorted((e.booking_id, e.event_type) for e in cluster.events))

    def _cluster_lost_coverage(cluster) -> bool:
        """A cluster qualifies for rescue when it shares a booking with a
        deleted shift AND one of its events sits inside a deleted shift's
        window — i.e. the delete actually removed coverage this cluster's
        events were relying on. Without the window condition, a rescued
        booking's UNRELATED clusters (its other event days away, already
        covered by shifts outside the delete scope) would be re-materialised
        as duplicates."""
        if not ({e.booking_id for e in cluster.events} & rescue_pool):
            return False
        for event in cluster.events:
            event_naive = event.event_time.replace(tzinfo=None)
            for w_start, w_end in deleted_windows:
                if w_start <= event_naive <= w_end:
                    return True
        return False

    def _materialise_cluster(cluster):
        materialised_keys.add(_cluster_key(cluster))

        plan = _cluster_shift_plan(cluster, settings)
        cluster_start = plan["cluster_start"]
        shift_start = plan["shift_start"]
        shift_end = plan["shift_end"]
        shift_type = plan["shift_type"]
        shift_date_val = plan["shift_date"]
        shift_end_date_val = plan["shift_end_date"]

        if (
            focus_booking_id is None
            and cluster_start.date() not in target_set
            and shift_date_val not in target_set
        ):
            # Adjacent-day rebuilds will own this cluster — don't double-write.
            return

        booking_ids = sorted({e.booking_id for e in cluster.events})
        booking_id_set = set(booking_ids)

        if _cluster_suppression_blockers(
            booking_id_set,
            shift_start,
            shift_end,
            suppressed_shifts,
        ):
            summary["skipped_suppressed"] += 1
            return

        if focus_booking_id is not None:
            cluster_window = (shift_start, shift_end)
            for s in focus_delete_candidates:
                sid = getattr(s, "id", None)
                if sid is not None and sid in deleted_shift_ids:
                    continue
                if (
                    _windows_overlap(_shift_window(s), cluster_window)
                    or bool(_shift_linked_booking_ids(s) & booking_id_set)
                ):
                    # Anyone on this shift loses coverage for the event it
                    # served — queue them for the rescue pass.
                    rescue_pool.update(_shift_linked_booking_ids(s))
                    deleted_windows.append(_shift_window(s))
                    db.delete(s)
                    if sid is not None:
                        deleted_shift_ids.add(sid)
                    summary["deleted"] += 1
            if summary["deleted"]:
                db.flush()

        # Skip-if-covered: when every event in this cluster falls inside
        # an existing frozen shift's window (combined coverage across
        # multiple owned shifts counts), do NOT materialise a new
        # auto-shift over the same hours. `auto_link_booking_to_shifts`
        # is the bridge that writes the ShiftBookingLink rows — it runs
        # on confirmation and only links bookings whose event time the
        # shift window actually covers. (Driver-trust pivot 2026-05-28.)
        if _cluster_fully_covered_by_shifts(
            cluster.events,
            frozen_shifts,
            settings,
        ):
            summary["skipped_covered"] += 1
            return

        new_shift = RosterShift(
            staff_id=None,
            date=shift_date_val,
            end_date=shift_end_date_val,
            start_time=shift_start.time(),
            end_time=shift_end.time(),
            shift_type=shift_type,
            status=ShiftStatus.SCHEDULED,
            created_source="auto",
        )
        db.add(new_shift)
        db.flush()  # need shift.id for link rows

        for bid in booking_ids:
            db.add(ShiftBookingLink(shift_id=new_shift.id, booking_id=bid))
        summary["created"] += 1

    for cluster in clusters:
        if (
            focus_booking_id is not None
            and all(e.booking_id != focus_booking_id for e in cluster.events)
        ):
            continue
        _materialise_cluster(cluster)

    if focus_booking_id is not None and rescue_pool:
        progressed = True
        while progressed:
            progressed = False
            for cluster in clusters:
                if _cluster_key(cluster) in materialised_keys:
                    continue
                if _cluster_lost_coverage(cluster):
                    _materialise_cluster(cluster)
                    summary["rescued"] += 1
                    progressed = True

    db.commit()
    return summary


def _summary() -> dict:
    return {
        "deleted": 0, "created": 0, "skipped_covered": 0,
        "skipped_suppressed": 0, "bookings_in_scope": 0, "events": 0,
        "rescued": 0,
    }


def _merge_summary(target: dict, source: dict) -> dict:
    for key, value in (source or {}).items():
        if isinstance(value, int):
            target[key] = target.get(key, 0) + value
    return target


def _default_window_template_specs() -> list[dict]:
    windows = [
        ("early", time_type(3, 0), time_type(9, 0)),
        ("day", time_type(9, 30), time_type(15, 30)),
        ("late", time_type(15, 45), time_type(20, 45)),
        ("overnight", time_type(21, 0), time_type(2, 0)),
    ]
    specs = []
    for profile in ("weekday", "weekend"):
        for idx, (label, start_time, end_time) in enumerate(windows):
            specs.append({
                "profile": profile,
                "label": label,
                "start_time": start_time,
                "end_time": end_time,
                "sort_order": idx,
                "is_active": True,
            })
    return specs


def _load_window_templates(db: Session) -> dict[str, list[RosterWindowTemplate]]:
    rows = (
        db.query(RosterWindowTemplate)
        .filter(RosterWindowTemplate.is_active == True)
        .order_by(RosterWindowTemplate.profile, RosterWindowTemplate.sort_order, RosterWindowTemplate.start_time)
        .all()
    )
    if not rows:
        rows = [RosterWindowTemplate(**spec) for spec in _default_window_template_specs()]
        for row in rows:
            db.add(row)
        try:
            db.flush()
        except Exception:
            # Unit-test fakes may not implement flush fully; the rows are still
            # usable as in-memory config for this call.
            pass

    grouped: dict[str, list[RosterWindowTemplate]] = {"weekday": [], "weekend": []}
    for row in rows:
        profile = getattr(row, "profile", None)
        if profile in grouped:
            grouped[profile].append(row)
    for profile in grouped:
        grouped[profile].sort(key=lambda row: (
            getattr(row, "sort_order", 0),
            getattr(row, "start_time", time_type(0, 0)),
        ))
    return grouped


def _window_profile_for_day(day: date_type) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


def _window_bounds(day: date_type, window: RosterWindowTemplate) -> tuple[datetime, datetime]:
    start = datetime.combine(day, window.start_time)
    end_day = day + timedelta(days=1) if window.end_time <= window.start_time else day
    return start, datetime.combine(end_day, window.end_time)


def _window_contains_event(
    day: date_type,
    window: RosterWindowTemplate,
    start_dt: datetime,
    end_dt: datetime,
) -> bool:
    win_start, win_end = _window_bounds(day, window)
    return win_start <= start_dt and end_dt <= win_end


def _distance_to_window(
    day: date_type,
    window: RosterWindowTemplate,
    start_dt: datetime,
    end_dt: datetime,
) -> timedelta:
    win_start, win_end = _window_bounds(day, window)
    if end_dt < win_start:
        return win_start - end_dt
    if start_dt > win_end:
        return start_dt - win_end
    return timedelta(0)


def _template_for_event(
    templates: dict[str, list[RosterWindowTemplate]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[date_type, RosterWindowTemplate]:
    candidate_days = [start_dt.date(), start_dt.date() - timedelta(days=1)]
    matches: list[tuple[int, date_type, RosterWindowTemplate]] = []
    for day_index, day in enumerate(candidate_days):
        for window in templates.get(_window_profile_for_day(day), []):
            if _window_contains_event(day, window, start_dt, end_dt):
                matches.append((day_index, day, window))
    if matches:
        matches.sort(key=lambda item: (
            item[0],
            getattr(item[2], "sort_order", 0),
            getattr(item[2], "start_time", time_type(0, 0)),
        ))
        return matches[0][1], matches[0][2]

    nearest: list[tuple[timedelta, int, date_type, RosterWindowTemplate]] = []
    for day_index, day in enumerate(candidate_days):
        for window in templates.get(_window_profile_for_day(day), []):
            nearest.append((
                _distance_to_window(day, window, start_dt, end_dt),
                day_index,
                day,
                window,
            ))
    if not nearest:
        raise ValueError("No active roster window templates configured")
    nearest.sort(key=lambda item: (
        item[0],
        item[1],
        getattr(item[3], "sort_order", 0),
        getattr(item[3], "start_time", time_type(0, 0)),
    ))
    return nearest[0][2], nearest[0][3]


def _window_shift_type(start_dt: datetime, end_dt: datetime):
    shift_type, _ = round_to_shift_type(start_dt, end_dt)
    return shift_type


def _rebuild_window_auto_for_dates(
    db: Session,
    target_dates: Iterable[date_type],
    settings: PlannerSettings,
    focus_booking_id: Optional[int] = None,
) -> dict:
    summary = _summary()
    effective_date = get_roster_effective_date()
    target_set = {d for d in set(target_dates) if d >= effective_date}
    if not target_set:
        return summary

    templates = _load_window_templates(db)

    existing = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.staff_id.is_(None),
            RosterShift.admin_shaped_at.is_(None),
            RosterShift.status == ShiftStatus.SCHEDULED,
            RosterShift.date.in_(target_set),
        )
        .all()
    )
    for shift in existing:
        db.delete(shift)
        summary["deleted"] += 1
    if summary["deleted"]:
        db.flush()

    expanded = set()
    for d in target_set:
        expanded.update({d - timedelta(days=1), d, d + timedelta(days=1)})

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.REFUNDED]),
            or_(
                Booking.dropoff_date.in_(expanded),
                Booking.pickup_date.in_(expanded),
                Booking.flight_arrival_date.in_(expanded),
            ),
        )
        .all()
    )
    bookings = [booking for booking in bookings if _booking_in_scope(booking)]
    summary["bookings_in_scope"] = len(bookings)

    frozen_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.status.in_([
                ShiftStatus.SCHEDULED,
                ShiftStatus.CONFIRMED,
            ]),
            or_(
                RosterShift.created_source != "auto",
                RosterShift.staff_id.isnot(None),
                RosterShift.admin_shaped_at.isnot(None),
            ),
            or_(
                RosterShift.date.in_(expanded),
                RosterShift.end_date.in_(expanded),
            ),
        )
        .all()
    )
    suppressed_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.status == ShiftStatus.CANCELLED,
            RosterShift.suppressed_at.isnot(None),
            or_(
                RosterShift.date.in_(expanded),
                RosterShift.end_date.in_(expanded),
            ),
        )
        .all()
    )

    groups: dict[tuple[date_type, str, str], dict] = {}
    for booking in bookings:
        for event_type, start_dt, end_dt in _events_for_booking(booking):
            op_date, window = _template_for_event(templates, start_dt, end_dt)
            if op_date not in target_set:
                continue
            summary["events"] += 1
            window_start, window_end = _window_bounds(op_date, window)
            group = groups.setdefault(
                (op_date, window.profile, window.label),
                {
                    "op_date": op_date,
                    "window": window,
                    "start": window_start,
                    "end": window_end,
                    "booking_ids": set(),
                },
            )
            if start_dt < group["start"]:
                group["start"] = start_dt
            if end_dt > group["end"]:
                group["end"] = end_dt
            group["booking_ids"].add(booking.id)

    for group in sorted(groups.values(), key=lambda item: (item["op_date"], item["start"])):
        group_window = (group["start"], group["end"])
        booking_ids = sorted(group["booking_ids"])
        if _cluster_suppression_blockers(
            set(booking_ids),
            group["start"],
            group["end"],
            suppressed_shifts,
        ):
            summary["skipped_suppressed"] += 1
            continue

        if any(
            _shift_can_cover_jockey_work(shift)
            and _shift_window(shift)[0] <= group_window[0]
            and group_window[1] <= _shift_window(shift)[1]
            for shift in frozen_shifts
        ):
            summary["skipped_covered"] += 1
            continue

        end_date = group["end"].date() if group["end"].date() != group["op_date"] else None
        new_shift = RosterShift(
            staff_id=None,
            date=group["op_date"],
            end_date=end_date,
            start_time=group["start"].time(),
            end_time=group["end"].time(),
            shift_type=_window_shift_type(group["start"], group["end"]),
            status=ShiftStatus.SCHEDULED,
            created_source="auto",
            intended_driver_type="jockey",
        )
        db.add(new_shift)
        db.flush()
        for booking_id in booking_ids:
            db.add(ShiftBookingLink(shift_id=new_shift.id, booking_id=booking_id))
        summary["created"] += 1

    db.commit()
    return summary


def rebuild_auto_for_dates(
    db: Session,
    target_dates: Iterable[date_type],
    settings: PlannerSettings,
    focus_booking_id: Optional[int] = None,
) -> dict:
    target_set = set(target_dates)
    if not target_set:
        return _summary()

    effective_date = get_roster_effective_date()
    pre_effective = {d for d in target_set if d < effective_date}
    window_effective = {d for d in target_set if d >= effective_date}
    result = _summary()
    if pre_effective:
        _merge_summary(
            result,
            _rebuild_cluster_auto_for_dates(
                db,
                pre_effective,
                settings,
                focus_booking_id=focus_booking_id,
            ),
        )
    if window_effective:
        _merge_summary(
            result,
            _rebuild_window_auto_for_dates(
                db,
                window_effective,
                settings,
                focus_booking_id=focus_booking_id,
            ),
        )
    return result


def trim_window_auto_shifts_for_date(
    db: Session,
    target_date: date_type,
    settings: PlannerSettings,
) -> dict:
    """Shrink untouched template-window shifts to actual event span + buffers.

    Intended for the T-1 20:00 booking cutoff job. The function is deliberately
    narrow: only July+ untouched auto shifts are eligible, and the new window is
    clamped inside the existing shift so this job never expands or reshapes
    claimed/admin-owned rows.
    """
    result = {"trimmed": 0, "skipped": 0}
    if target_date < get_roster_effective_date():
        return result

    shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.staff_id.is_(None),
            RosterShift.admin_shaped_at.is_(None),
            RosterShift.status == ShiftStatus.SCHEDULED,
            RosterShift.date == target_date,
        )
        .all()
    )
    if not shifts:
        return result

    for shift in shifts:
        if not _is_auto_shift_eligible_for_rebuild(shift):
            result["skipped"] += 1
            continue
        shift_start, shift_end = _shift_window(shift)
        event_starts: list[datetime] = []
        event_ends: list[datetime] = []
        for booking in getattr(shift, "bookings", []) or []:
            if not _booking_in_scope(booking):
                continue
            for _event_type, start_dt, end_dt in _events_for_booking(booking):
                if shift_start <= start_dt and end_dt <= shift_end:
                    event_starts.append(start_dt)
                    event_ends.append(end_dt)
        if not event_starts:
            result["skipped"] += 1
            continue

        desired_start = min(event_starts) - timedelta(minutes=settings.start_buffer_minutes)
        desired_end = max(event_ends) + timedelta(minutes=settings.end_buffer_minutes)
        new_start = max(shift_start, desired_start)
        new_end = min(shift_end, desired_end)
        if new_end <= new_start:
            result["skipped"] += 1
            continue
        if new_start == shift_start and new_end == shift_end:
            result["skipped"] += 1
            continue

        shift.date = new_start.date()
        shift.end_date = new_end.date() if new_end.date() != new_start.date() else None
        shift.start_time = new_start.time()
        shift.end_time = new_end.time()
        shift.shift_type = _window_shift_type(new_start, new_end)
        result["trimmed"] += 1

    if result["trimmed"]:
        db.commit()
    return result


def build_auto_roster_sweep_plan(
    target_dates: Iterable[date_type],
    bookings: list[Booking],
    live_shifts: list[RosterShift],
    suppressed_shifts: list[RosterShift],
    settings: PlannerSettings,
) -> dict:
    """Read-only per-cluster sweep plan.

    This is Step 2 of the sweep work: the future write-mode sweep should use
    this same cluster decision path, then execute the `focus_booking_id`
    actions it reports.
    """
    target_set = set(target_dates)
    dates_payload = {
        d: {
            "date": d.isoformat(),
            "missing_review_count": 0,
            "cluster_count": 0,
            "would_generate_count": 0,
            "skipped_suppressed_count": 0,
            "skipped_owned_coverage_count": 0,
            "clusters": [],
        }
        for d in sorted(target_set)
    }

    if not target_set:
        return {
            "write": False,
            "date_from": None,
            "date_to": None,
            "dates_scanned": 0,
            "clusters_missing_coverage": 0,
            "clusters_would_generate": 0,
            "clusters_skipped_suppressed": 0,
            "clusters_skipped_owned_coverage": 0,
            "focus_rebuild_count": 0,
            "dates": [],
        }

    events = []
    cluster_events = []
    for booking in bookings or []:
        if not _booking_in_scope(booking):
            continue
        for event_type, start_dt, end_dt in _events_for_booking(booking):
            event = {
                "booking": booking,
                "booking_id": booking.id,
                "booking_reference": booking.reference or "",
                "event_type": event_type,
                "event_time": start_dt,
                "end_anchor_time": end_dt,
                "operational_date": _review_operational_date(event_type, start_dt),
            }
            events.append(event)
            cluster_events.append(Event(
                booking_id=booking.id,
                booking_reference=booking.reference or "",
                event_type=event_type,
                event_time=start_dt.replace(tzinfo=UK_TZ),
                end_anchor_time=end_dt.replace(tzinfo=UK_TZ),
            ))

    live_event_keys: set[str] = set()
    for shift in live_shifts or []:
        if _scalar_value(getattr(shift, "status", None)) == ShiftStatus.CANCELLED.value:
            continue
        live_event_keys.update(_shift_linked_event_keys(shift))

    missing_events = [
        event for event in events
        if event["operational_date"] in target_set
        and _review_event_key(event["booking_id"], event["event_type"]) not in live_event_keys
    ]
    for event in missing_events:
        dates_payload[event["operational_date"]]["missing_review_count"] += 1

    clusters = group_events_by_gap(
        cluster_events,
        gap_max_minutes=settings.gap_max_minutes,
        mixed_gap_max_minutes=settings.mixed_gap_max_minutes,
    )
    cluster_by_event_key: dict[str, object] = {}
    for cluster in clusters:
        for event in cluster.events:
            cluster_by_event_key[_review_event_key(event.booking_id, event.event_type)] = cluster

    missing_by_cluster: dict[tuple[str, ...], list[dict]] = {}
    cluster_by_key: dict[tuple[str, ...], object] = {}
    for missing in missing_events:
        key = _review_event_key(missing["booking_id"], missing["event_type"])
        cluster = cluster_by_event_key.get(key)
        if cluster is None:
            continue
        cluster_key = tuple(sorted(
            _review_event_key(event.booking_id, event.event_type)
            for event in cluster.events
        ))
        cluster_by_key[cluster_key] = cluster
        missing_by_cluster.setdefault(cluster_key, []).append(missing)

    frozen_shifts = [
        shift for shift in (live_shifts or [])
        if _scalar_value(getattr(shift, "status", None)) in (
            ShiftStatus.SCHEDULED.value,
            ShiftStatus.CONFIRMED.value,
        )
        and (
            getattr(shift, "created_source", None) != "auto"
            or getattr(shift, "staff_id", None) is not None
            or getattr(shift, "admin_shaped_at", None) is not None
        )
    ]
    active_suppressed = [
        shift for shift in (suppressed_shifts or [])
        if getattr(shift, "created_source", None) == "auto"
        and _scalar_value(getattr(shift, "status", None)) == ShiftStatus.CANCELLED.value
        and getattr(shift, "suppressed_at", None) is not None
    ]

    totals = {
        "clusters_missing_coverage": 0,
        "clusters_would_generate": 0,
        "clusters_skipped_suppressed": 0,
        "clusters_skipped_owned_coverage": 0,
    }
    def _event_sort_key(event):
        return (
            event["event_time"],
            event["event_type"],
            event["booking_reference"],
            event["booking_id"],
        )

    for cluster_key in sorted(missing_by_cluster):
        cluster = cluster_by_key[cluster_key]
        missing_for_cluster = sorted(missing_by_cluster[cluster_key], key=_event_sort_key)
        owner_date = min(event["operational_date"] for event in missing_for_cluster)
        if owner_date not in dates_payload:
            continue

        plan = _cluster_shift_plan(cluster, settings)
        shift_start = plan["shift_start"]
        shift_end = plan["shift_end"]
        booking_ids = {event.booking_id for event in cluster.events}
        suppression_blockers = _cluster_suppression_blockers(
            booking_ids,
            shift_start,
            shift_end,
            active_suppressed,
        )
        covering_shifts = _cluster_fully_covered_by_shifts(
            cluster.events,
            frozen_shifts,
            settings,
        )

        if suppression_blockers:
            action = "skip_suppressed"
            totals["clusters_skipped_suppressed"] += 1
            dates_payload[owner_date]["skipped_suppressed_count"] += 1
        elif covering_shifts:
            action = "skip_owned_coverage"
            totals["clusters_skipped_owned_coverage"] += 1
            dates_payload[owner_date]["skipped_owned_coverage_count"] += 1
        else:
            action = "would_generate"
            totals["clusters_would_generate"] += 1
            dates_payload[owner_date]["would_generate_count"] += 1

        focus_booking_id = missing_for_cluster[0]["booking_id"]

        missing_payload = []
        for event in missing_for_cluster:
            booking = event["booking"]
            marker = _booking_confirmation_marker(booking)
            missing_payload.append({
                "booking_id": event["booking_id"],
                "booking_reference": event["booking_reference"],
                "event_type": event["event_type"],
                "event_time": event["event_time"].strftime("%H:%M"),
                "event_datetime": event["event_time"].isoformat(),
                "operational_date": event["operational_date"].isoformat(),
                "confirmation_source": marker["source"],
                "confirmation_timestamp": marker["timestamp"],
            })

        cluster_payload = {
            "operational_date": owner_date.isoformat(),
            "operational_dates": sorted({
                event["operational_date"].isoformat()
                for event in missing_for_cluster
            }),
            "action": action,
            "focus_booking_id": focus_booking_id,
            "would_call": (
                "rebuild_auto_for_dates"
                if action == "would_generate"
                else None
            ),
            "would_call_kwargs": (
                {
                    "target_dates": [owner_date.isoformat()],
                    "focus_booking_id": focus_booking_id,
                }
                if action == "would_generate"
                else None
            ),
            "would_shift": {
                "date": plan["shift_date"].isoformat(),
                "end_date": (
                    plan["shift_end_date"].isoformat()
                    if plan["shift_end_date"] else None
                ),
                "start_time": shift_start.strftime("%H:%M"),
                "end_time": shift_end.strftime("%H:%M"),
                "start_datetime": shift_start.isoformat(),
                "end_datetime": shift_end.isoformat(),
                "shift_type": _scalar_value(plan["shift_type"]),
            },
            "missing_events": missing_payload,
            "all_cluster_events": [
                {
                    "booking_id": event.booking_id,
                    "booking_reference": event.booking_reference,
                    "event_type": event.event_type,
                    "event_datetime": event.event_time.replace(tzinfo=None).isoformat(),
                }
                for event in sorted(
                    cluster.events,
                    key=lambda e: (
                        e.event_time,
                        e.event_type,
                        e.booking_reference,
                        e.booking_id,
                    ),
                )
            ],
            "suppressed": {
                "blocked": bool(suppression_blockers),
                "shift_ids": sorted(
                    sid for sid in (
                        getattr(shift, "id", None) for shift in suppression_blockers
                    )
                    if sid is not None
                ),
            },
            "owned_coverage": {
                "covered": bool(covering_shifts),
                "shift_ids": sorted(
                    sid for sid in (
                        getattr(shift, "id", None) for shift in covering_shifts
                    )
                    if sid is not None
                ),
            },
        }
        dates_payload[owner_date]["clusters"].append(cluster_payload)
        dates_payload[owner_date]["cluster_count"] += 1
        totals["clusters_missing_coverage"] += 1

    return {
        "write": False,
        "date_from": min(target_set).isoformat(),
        "date_to": max(target_set).isoformat(),
        "dates_scanned": len(target_set),
        "clusters_missing_coverage": totals["clusters_missing_coverage"],
        "clusters_would_generate": totals["clusters_would_generate"],
        "clusters_skipped_suppressed": totals["clusters_skipped_suppressed"],
        "clusters_skipped_owned_coverage": totals["clusters_skipped_owned_coverage"],
        "focus_rebuild_count": totals["clusters_would_generate"],
        "dates": list(dates_payload.values()),
    }


def dry_run_auto_roster_sweep(
    db: Session,
    date_from: Optional[date_type],
    date_to: Optional[date_type],
    settings: PlannerSettings,
) -> dict:
    if date_from is None:
        date_from = datetime.now(UK_TZ).date() + timedelta(days=1)
    if date_to is None:
        window_days = settings.window_days if settings.window_days and settings.window_days > 0 else 28
        date_to = date_from + timedelta(days=window_days - 1)
    if date_to < date_from:
        raise ValueError("date_to must be >= date_from")
    if (date_to - date_from).days > 62:
        raise ValueError("Date range must be 63 days or fewer")

    target_dates = {
        date_from + timedelta(days=i)
        for i in range((date_to - date_from).days + 1)
    }
    expanded = set(target_dates)
    for d in target_dates:
        expanded.add(d - timedelta(days=1))
        expanded.add(d + timedelta(days=1))

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.REFUNDED]),
            or_(Booking.service_type.is_(None), Booking.service_type != ServiceType.PARK_RIDE),
            or_(
                Booking.dropoff_date.in_(expanded),
                Booking.pickup_date.in_(expanded),
                Booking.flight_arrival_date.in_(expanded),
            ),
        )
        .all()
    )
    live_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.status != ShiftStatus.CANCELLED,
            or_(
                RosterShift.date.in_(expanded),
                RosterShift.end_date.in_(expanded),
            ),
        )
        .all()
    )
    suppressed_shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.status == ShiftStatus.CANCELLED,
            RosterShift.suppressed_at.isnot(None),
            or_(
                RosterShift.date.in_(expanded),
                RosterShift.end_date.in_(expanded),
            ),
        )
        .all()
    )
    return build_auto_roster_sweep_plan(
        target_dates,
        bookings,
        live_shifts,
        suppressed_shifts,
        settings,
    )


def run_auto_roster_sweep(
    db: Session,
    settings: PlannerSettings,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    *,
    write: bool = False,
    run_id: Optional[str] = None,
    trigger: str = "manual",
) -> dict:
    """Run the shared sweep decision path, optionally executing it.

    Step 3 contract: write mode executes only the `would_generate` clusters
    reported by dry-run, using the exact date/focus kwargs in the report.
    """
    report = dry_run_auto_roster_sweep(db, date_from, date_to, settings)
    report["write"] = bool(write)
    report["trigger"] = trigger
    report["run_id"] = run_id
    report["executions"] = []
    report["clusters_attempted"] = 0
    report["clusters_repaired"] = 0
    report["clusters_noop"] = 0
    report["failures"] = 0

    if not write:
        logger.info(
            "auto_roster_sweep outcome=dry_run trigger=%s run_id=%s dates_scanned=%s clusters_missing=%s would_generate=%s skipped_suppressed=%s skipped_owned=%s",
            trigger,
            run_id,
            report.get("dates_scanned", 0),
            report.get("clusters_missing_coverage", 0),
            report.get("clusters_would_generate", 0),
            report.get("clusters_skipped_suppressed", 0),
            report.get("clusters_skipped_owned_coverage", 0),
        )
        return report

    logger.info(
        "auto_roster_sweep outcome=start trigger=%s run_id=%s dates_scanned=%s clusters_missing=%s would_generate=%s skipped_suppressed=%s skipped_owned=%s",
        trigger,
        run_id,
        report.get("dates_scanned", 0),
        report.get("clusters_missing_coverage", 0),
        report.get("clusters_would_generate", 0),
        report.get("clusters_skipped_suppressed", 0),
        report.get("clusters_skipped_owned_coverage", 0),
    )

    for date_payload in report.get("dates", []):
        for cluster in date_payload.get("clusters", []):
            if cluster.get("action") != "would_generate":
                continue
            kwargs = cluster.get("would_call_kwargs") or {}
            target_dates = {
                datetime.strptime(d, "%Y-%m-%d").date()
                for d in kwargs.get("target_dates", [])
            }
            focus_booking_id = kwargs.get("focus_booking_id")
            execution = {
                "operational_date": cluster.get("operational_date"),
                "focus_booking_id": focus_booking_id,
                "target_dates": sorted(d.isoformat() for d in target_dates),
                "status": "pending",
                "result": None,
                "error": None,
            }
            report["clusters_attempted"] += 1
            try:
                result = rebuild_auto_for_dates(
                    db,
                    target_dates,
                    settings,
                    focus_booking_id=focus_booking_id,
                )
                execution["status"] = "repaired" if result.get("created", 0) else "noop"
                execution["result"] = result
                if result.get("created", 0):
                    report["clusters_repaired"] += 1
                else:
                    report["clusters_noop"] += 1
                logger.info(
                    "auto_roster_sweep outcome=cluster trigger=%s run_id=%s operational_date=%s focus_booking_id=%s target_dates=%s status=%s result=%s",
                    trigger,
                    run_id,
                    execution["operational_date"],
                    focus_booking_id,
                    execution["target_dates"],
                    execution["status"],
                    result,
                )
            except Exception as e:
                execution["status"] = "failed"
                execution["error"] = str(e)
                report["failures"] += 1
                logger.exception(
                    "auto_roster_sweep outcome=cluster_failure trigger=%s run_id=%s operational_date=%s focus_booking_id=%s target_dates=%s error=%s",
                    trigger,
                    run_id,
                    execution["operational_date"],
                    focus_booking_id,
                    execution["target_dates"],
                    e,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
            report["executions"].append(execution)

    logger.info(
        "auto_roster_sweep outcome=complete trigger=%s run_id=%s attempted=%s repaired=%s noop=%s failures=%s",
        trigger,
        run_id,
        report["clusters_attempted"],
        report["clusters_repaired"],
        report["clusters_noop"],
        report["failures"],
    )
    return report


def _affected_dates_for_booking(booking: Booking) -> set[date_type]:
    """Days touched by a booking's events — covers both the start anchor
    (e.g. flight_arrival on D) and the end anchor (e.g. pickup_time on D+1
    if the flight crosses midnight) so the rebuild scope catches both
    sides of an asymmetric pickup window."""
    dates: set[date_type] = set()
    effective_date = get_roster_effective_date()
    for _et, start_dt, end_dt in _events_for_booking(booking):
        dates.add(start_dt.date())
        dates.add(end_dt.date())
        for dt in (start_dt, end_dt):
            if (
                dt.date() >= effective_date
                and dt.time() < time_type(2, 0)
            ):
                dates.add(dt.date() - timedelta(days=1))
    return dates


# ---------------------------------------------------------------------------
# Public entry points (kept signature-compatible with prior versions)
# ---------------------------------------------------------------------------

def auto_create_or_extend_for_booking(
    db: Session, booking: Booking, settings: PlannerSettings
) -> dict:
    """A booking just flipped to CONFIRMED — rebuild the days it touches.

    Skip rules:
      * Booking must be CONFIRMED (refunded / cancelled / pending no-op).
      * Park & Ride bookings — no jockey work, no shift to create.
    """
    summary = {"created": 0, "deleted": 0, "bookings_in_scope": 0, "skipped": 0}
    if booking is None or booking.status != BookingStatus.CONFIRMED:
        summary["skipped"] = 1
        return summary
    if getattr(booking, "service_type", None) == ServiceType.PARK_RIDE:
        summary["skipped"] = 1
        return summary

    dates = _affected_dates_for_booking(booking)
    if not dates:
        summary["skipped"] = 1
        return summary

    result = rebuild_auto_for_dates(db, dates, settings, focus_booking_id=booking.id)
    summary.update(result)
    return summary


def handle_booking_cancelled(db: Session, booking: Booking) -> dict:
    """A booking just flipped to CANCELLED — rebuild the days it touched.

    The booking is now excluded from the rebuild source, so the day's
    auto-shift will shrink (or disappear) accordingly. Touched / claimed
    auto-shifts on the same day are preserved.
    """
    summary = {"created": 0, "deleted": 0, "bookings_in_scope": 0, "skipped": 0}
    if booking is None or booking.status != BookingStatus.CANCELLED:
        return summary
    if getattr(booking, "service_type", None) == ServiceType.PARK_RIDE:
        return summary

    db.query(ShiftBookingLink).filter(
        ShiftBookingLink.booking_id == booking.id
    ).delete(synchronize_session=False)

    dates = _affected_dates_for_booking(booking)
    if not dates:
        return summary

    # Need settings here too — pull from DB.
    from routers.roster import _load_planner_settings_rows

    settings = PlannerSettings.from_kv(_load_planner_settings_rows(db))
    result = rebuild_auto_for_dates(db, dates, settings)
    summary.update(result)
    return summary


def delete_all_auto_shifts(
    db: Session,
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
) -> int:
    """Admin override: wipe untouched auto-shifts. Touched / claimed shifts
    are preserved. Returns the number deleted.

    Date scoping (locked 2026-05-05): when `date_from` and/or `date_to` are
    set, the wipe is constrained to that range (inclusive both ends). Both
    None → wipe across all dates (legacy behaviour). Only date_from set →
    open-ended right edge (`>= date_from`). Only date_to set → open-ended
    left edge (`<= date_to`).
    """
    # Driver-trust rule (2026-05-28): admin_shaped_at IS NULL keeps
    # split/merged/duplicated/time-edited rows out of the wipe set, even
    # if they're unassigned. They're admin-shaped, the admin owns the
    # window — preserve them.
    query = db.query(RosterShift).filter(
        RosterShift.created_source == "auto",
        RosterShift.staff_id.is_(None),
        RosterShift.admin_shaped_at.is_(None),
        RosterShift.status == ShiftStatus.SCHEDULED,
    )
    if date_from is not None:
        query = query.filter(RosterShift.date >= date_from)
    if date_to is not None:
        query = query.filter(RosterShift.date <= date_to)
    candidates = query.all()
    count = 0
    for s in candidates:
        db.delete(s)
        count += 1
    if count:
        db.commit()
    return count


# ---------------------------------------------------------------------------
# Async wrappers (FastAPI BackgroundTasks entry points)
# ---------------------------------------------------------------------------

def auto_create_or_extend_async(booking_id: int) -> None:
    """BackgroundTask entry — owns its own DB session, swallows errors."""
    db = None
    booking_ref = None
    affected_dates: list[str] = []
    logger.info("auto_create_or_extend_async outcome=start booking_id=%s", booking_id)
    try:
        from database import SessionLocal
        from routers.roster import _load_planner_settings_rows

        db = SessionLocal()
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking is None:
            logger.warning(
                "auto_create_or_extend_async outcome=not_found booking_id=%s",
                booking_id,
            )
            return
        booking_ref = booking.reference
        affected_dates = sorted(d.isoformat() for d in _affected_dates_for_booking(booking))
        logger.info(
            "auto_create_or_extend_async outcome=loaded booking_id=%s ref=%s status=%s service_type=%s affected_dates=%s",
            booking.id,
            booking_ref,
            _scalar_value(getattr(booking, "status", None)),
            _scalar_value(getattr(booking, "service_type", None)),
            affected_dates,
        )
        settings = PlannerSettings.from_kv(_load_planner_settings_rows(db))
        result = auto_create_or_extend_for_booking(db, booking, settings)
        logger.info(
            "auto_create_or_extend_async outcome=success booking_id=%s ref=%s affected_dates=%s result=%s",
            booking.id,
            booking_ref,
            affected_dates,
            result,
        )
    except Exception as e:
        logger.exception(
            "auto_create_or_extend_async outcome=failure booking_id=%s ref=%s affected_dates=%s error=%s",
            booking_id,
            booking_ref,
            affected_dates,
            e,
        )
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()


def handle_booking_cancelled_async(booking_id: int) -> None:
    """BackgroundTask entry — same isolation contract as auto_create_or_extend_async."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking is None:
            logger.warning("handle_booking_cancelled_async: booking %s not found", booking_id)
            return
        result = handle_booking_cancelled(db, booking)
        logger.info(
            "handle_booking_cancelled_async booking=%s ref=%s result=%s",
            booking.id, booking.reference, result,
        )
    except Exception as e:
        logger.exception(
            "handle_booking_cancelled_async failed booking_id=%s: %s", booking_id, e
        )
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
