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
    Event,
    PlannerSettings,
    UK_TZ,
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
      airport before the plane lands so the car is ready); end_anchor =
      pickup_time (the customer-handoff moment, when the jockey is actually
      released). These differ by ~30 min (the standard
      arrival→collection gap). When flight_arrival_time isn't recorded, the
      engine derives start_anchor as `pickup_time - 30 min` (existing
      behaviour). When pickup_time isn't recorded, end_anchor falls back to
      `start_anchor + 30 min` (the same standard gap).

    Returned datetimes are naive (no tz) — the DB columns are naive too;
    we attach UK_TZ when handing off to the clusterer.
    """
    out: list[tuple[str, datetime, datetime]] = []
    if booking.dropoff_date and booking.dropoff_time:
        dropoff_dt = datetime.combine(booking.dropoff_date, booking.dropoff_time)
        out.append(("drop_off", dropoff_dt, dropoff_dt))
    if booking.pickup_date:
        if getattr(booking, "flight_arrival_time", None):
            # flight_arrival_time has no date column; it's normally on
            # pickup_date, but for early-AM pickups the flight lands the
            # previous calendar day (e.g. flight 23:55, pickup 00:25 next
            # day). Detect that by comparing against pickup_time.
            flight_date = booking.pickup_date
            if booking.pickup_time and booking.flight_arrival_time > booking.pickup_time:
                flight_date = booking.pickup_date - timedelta(days=1)
            start_anchor = datetime.combine(flight_date, booking.flight_arrival_time)
        elif booking.pickup_time:
            start_anchor = datetime.combine(booking.pickup_date, booking.pickup_time) - timedelta(minutes=30)
        else:
            start_anchor = None
        if start_anchor is not None:
            if booking.pickup_time:
                end_anchor = datetime.combine(booking.pickup_date, booking.pickup_time)
            else:
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


def _is_auto_shift_eligible_for_rebuild(shift: RosterShift) -> bool:
    """Untouched auto-shift = created_source='auto', staff_id NULL, SCHEDULED.
    Anything else is admin territory — preserve it."""
    return (
        getattr(shift, "created_source", None) == "auto"
        and shift.staff_id is None
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

    Returns a counts dict so callers can log / surface a banner.
    """
    summary = {"deleted": 0, "created": 0, "bookings_in_scope": 0, "events": 0}
    target_set = set(target_dates)
    if not target_set:
        return summary

    # 1. Delete untouched auto-shifts in scope.
    existing = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.staff_id.is_(None),
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

    # 4. Materialise shifts for clusters whose start lands on a target date.
    start_buffer = timedelta(minutes=settings.start_buffer_minutes)
    end_buffer = timedelta(minutes=settings.end_buffer_minutes)
    min_duration = timedelta(minutes=settings.min_shift_minutes)

    for cluster in clusters:
        cluster_start = cluster.events[0].event_time
        # cluster_end pivots on the latest *end* anchor — for pickups that's
        # pickup_time (handoff), for drop-offs that's dropoff_time. The
        # events list is sorted by event_time (start anchor) which doesn't
        # necessarily put the latest end anchor last; max() handles that.
        cluster_end = max(
            (e.end_anchor_time or e.event_time) for e in cluster.events
        )
        if cluster_start.date() not in target_set:
            # Adjacent-day rebuilds will own this cluster — don't double-write.
            continue

        # Strip tz for naive DB storage.
        c_start = cluster_start.replace(tzinfo=None)
        c_end = cluster_end.replace(tzinfo=None)
        shift_start = c_start - start_buffer
        shift_end = c_end + end_buffer
        if shift_end - shift_start < min_duration:
            shift_end = shift_start + min_duration

        shift_type, _ = round_to_shift_type(shift_start, shift_end)
        new_shift = RosterShift(
            staff_id=None,
            date=shift_start.date(),
            end_date=shift_end.date() if shift_end.date() != shift_start.date() else None,
            start_time=shift_start.time(),
            end_time=shift_end.time(),
            shift_type=shift_type,
            status=ShiftStatus.SCHEDULED,
            created_source="auto",
        )
        db.add(new_shift)
        db.flush()  # need shift.id for link rows

        booking_ids = sorted({e.booking_id for e in cluster.events})
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

    result = rebuild_auto_for_dates(db, dates, settings)
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

    dates = _affected_dates_for_booking(booking)
    if not dates:
        return summary

    # Need settings here too — pull from DB.
    from routers.roster import _load_planner_settings_rows

    settings = PlannerSettings.from_kv(_load_planner_settings_rows(db))
    result = rebuild_auto_for_dates(db, dates, settings)
    summary.update(result)
    return summary


def delete_all_auto_shifts(db: Session) -> int:
    """Admin override: wipe every untouched auto-shift across all dates.
    Touched / claimed shifts are preserved. Returns the number deleted."""
    candidates = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.staff_id.is_(None),
            RosterShift.status == ShiftStatus.SCHEDULED,
        )
        .all()
    )
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
