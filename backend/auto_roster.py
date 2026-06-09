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
from datetime import date as date_type, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db_models import (
    Booking,
    BookingStatus,
    RosterShift,
    ServiceType,
    ShiftBookingLink,
    ShiftStatus,
)
from roster_planner import (
    ARRIVAL_OVERNIGHT_CUTOFF,
    Event,
    PlannerSettings,
    UK_TZ,
    compute_cluster_shift_window,
    group_events_by_gap,
    round_to_shift_type,
)

logger = logging.getLogger(__name__)


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


def _booking_in_scope(booking: Booking) -> bool:
    """Bookings the auto-roster covers: jockey work (not P&R) with status
    in CONFIRMED or REFUNDED. CANCELLED / PENDING are excluded."""
    if getattr(booking, "service_type", None) == ServiceType.PARK_RIDE:
        return False
    return booking.status in (BookingStatus.CONFIRMED, BookingStatus.REFUNDED)


# ---------------------------------------------------------------------------
# Rebuild — core
# ---------------------------------------------------------------------------

def rebuild_auto_for_dates(
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

    def _cluster_fully_covered(cluster_events, required_start: datetime, required_end: datetime) -> bool:
        """All-or-nothing skip rule (partial-overlap pivot 2026-05-28):
        return True only when EVERY event in the cluster has BOTH its
        start anchor (flight_arrival_time for pickups, dropoff_time for
        drop-offs) AND its end anchor (pickup handoff = arrival + 30 min
        for pickups; same as start for drop-offs) inside the wall-clock
        window of at least one frozen shift. Partial overlap still
        materialises the whole cluster.

        The full generated shift window matters: start anchor minus start
        buffer through end anchor plus end buffer, including tight-pair
        extensions. If pickups at 22:55 and 23:00 sit in a fixed 22:45-23:45
        shift, they are NOT covered: the tight pickup pair requires an
        earlier 22:10 start. Regression caught on TAG-SHS00925 / TAG-LDH79714."""
        if not frozen_shifts:
            return False
        for ev in cluster_events:
            inside_any = False
            for fs in frozen_shifts:
                fs_start = datetime.combine(fs.date, fs.start_time)
                fs_end = datetime.combine(fs.end_date or fs.date, fs.end_time)
                if fs_start <= required_start and required_end <= fs_end:
                    inside_any = True
                    break
            if not inside_any:
                return False
        return True

    def _cluster_suppressed(booking_ids: set[int], required_start: datetime, required_end: datetime) -> bool:
        """A cancelled/suppressed auto shift means "do not recreate this
        generated coverage". Match by fully covered window or by retained
        linked bookings."""
        if not suppressed_shifts:
            return False
        required_window = (required_start, required_end)
        for s in suppressed_shifts:
            suppressed_start, suppressed_end = _shift_window(s)
            if suppressed_start <= required_window[0] and required_window[1] <= suppressed_end:
                return True
            if _shift_linked_booking_ids(s) & booking_ids:
                return True
        return False

    # 4. Materialise shifts for clusters whose owner lands in target_set.
    # Usually that owner is the event anchor date. For arrivals before the
    # 02:00 operational cutoff, the owner is the prior operational day, so a
    # 26 Jun rebuild must recreate a 27 Jun 00:35 pickup shift dated 26 Jun.
    for cluster in clusters:
        if (
            focus_booking_id is not None
            and all(e.booking_id != focus_booking_id for e in cluster.events)
        ):
            continue

        cluster_start = cluster.events[0].event_time
        # Compute each event type's requirement independently, then use the
        # outer bounds. Tight pickups can pull the start earlier from the
        # pickup arrival anchor; tight drop-offs can push the end later from
        # the drop-off anchor. A mixed event in the middle must not magnify
        # the opposite side of the shift.
        shift_start, shift_end = compute_cluster_shift_window(
            cluster,
            start_buffer_minutes=settings.start_buffer_minutes,
            end_buffer_minutes=settings.end_buffer_minutes,
            min_shift_minutes=settings.min_shift_minutes,
        )
        # Strip tz for naive DB storage.
        shift_start = shift_start.replace(tzinfo=None)
        shift_end = shift_end.replace(tzinfo=None)

        shift_type, _ = round_to_shift_type(shift_start, shift_end)

        # Arrivals strictly before ARRIVAL_OVERNIGHT_CUTOFF (02:00 UK) belong
        # to the prior day's evening shift — mirrors the rule in
        # roster_planner.propose_roster and the Admin Calendar display
        # (RosterCalendar.jsx claimPickupDate). cluster_start is the arrival
        # anchor for pickup-led clusters.
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

        if (
            focus_booking_id is None
            and cluster_start.date() not in target_set
            and shift_date_val not in target_set
        ):
            # Adjacent-day rebuilds will own this cluster — don't double-write.
            continue

        booking_ids = sorted({e.booking_id for e in cluster.events})
        booking_id_set = set(booking_ids)

        if _cluster_suppressed(booking_id_set, shift_start, shift_end):
            summary["skipped_suppressed"] += 1
            continue

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
                    db.delete(s)
                    if sid is not None:
                        deleted_shift_ids.add(sid)
                    summary["deleted"] += 1
            if summary["deleted"]:
                db.flush()

        # Skip-if-covered: when every event in this cluster falls inside
        # an existing frozen shift's window, do NOT materialise a new
        # auto-shift over the same hours. `auto_link_booking_to_shifts`
        # is the bridge that writes the ShiftBookingLink rows — it runs
        # on confirmation and only links bookings whose event time the
        # shift window actually covers. (Driver-trust pivot 2026-05-28.)
        if _cluster_fully_covered(cluster.events, shift_start, shift_end):
            summary["skipped_covered"] += 1
            continue

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

    db.commit()
    return summary


def _affected_dates_for_booking(booking: Booking) -> set[date_type]:
    """Days touched by a booking's events — covers both the start anchor
    (e.g. flight_arrival on D) and the end anchor (e.g. pickup_time on D+1
    if the flight crosses midnight) so the rebuild scope catches both
    sides of an asymmetric pickup window."""
    dates: set[date_type] = set()
    for _et, start_dt, end_dt in _events_for_booking(booking):
        dates.add(start_dt.date())
        dates.add(end_dt.date())
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
    from database import SessionLocal
    from routers.roster import _load_planner_settings_rows

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking is None:
            logger.warning("auto_create_or_extend_async: booking %s not found", booking_id)
            return
        settings = PlannerSettings.from_kv(_load_planner_settings_rows(db))
        result = auto_create_or_extend_for_booking(db, booking, settings)
        logger.info(
            "auto_create_or_extend_async booking=%s ref=%s result=%s",
            booking.id, booking.reference, result,
        )
    except Exception as e:
        logger.exception(
            "auto_create_or_extend_async failed booking_id=%s: %s", booking_id, e
        )
        try:
            db.rollback()
        except Exception:
            pass
    finally:
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
