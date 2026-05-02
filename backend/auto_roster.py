"""
Auto-roster: create / extend roster shifts in real-time as bookings flow in.

Replaces the Phase-3 commit pipeline of the old planner (see SPEC.md). The
engine in `roster_planner.py` stays a pure simulation for QA / shadow-mode;
this module owns the live-write path.

Design notes (2026-05-02):
  - Auto-shifts are tagged `created_source='auto'` and live exclusively on
    the new self-contained Calendar embedded on the Roster Planner page —
    they don't appear on the regular admin Roster Calendar or the employee
    available-shifts pool until promoted (future work).
  - Always unassigned (`staff_id=NULL`); admin promotes / claims later.
  - Never touches `created_source` in {'manual','planner'} — those are
    admin / engine-commit territory.
  - For each booking event (drop-off, pick-up):
      1. If an admin/planner shift already covers it → existing
         `auto_link_booking_to_shifts` will link them; we skip.
      2. Else if a nearby auto-shift exists (within `gap_max_minutes` of
         either edge of its window, same date) → extend that shift's
         start / end and add a `ShiftBookingLink`.
      3. Else → create a new auto-shift with the SPEC's start/end buffers.
  - Idempotent: re-running for the same booking is a no-op once linked.
  - Failure-isolated: the caller wraps in `background_tasks.add_task` and
    the function swallows DB errors so a planner side-effect never breaks
    the confirmation flow that triggered it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from db_models import (
    Booking,
    BookingStatus,
    RosterShift,
    ShiftBookingLink,
    ShiftStatus,
)
from roster_planner import (
    PlannerSettings,
    UK_TZ,
    round_to_shift_type,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------

def _events_for_booking(booking: Booking) -> list[tuple[str, datetime]]:
    """Return (event_type, event_dt) tuples for the booking's drop-off and
    pick-up. Pick-up anchors to `flight_arrival_time` if available, else
    `pickup_time` minus 30 minutes (matches the engine in roster_planner.py).
    """
    out: list[tuple[str, datetime]] = []
    if booking.dropoff_date and booking.dropoff_time:
        out.append((
            "drop_off",
            datetime.combine(booking.dropoff_date, booking.dropoff_time),
        ))
    if booking.pickup_date:
        if booking.flight_arrival_time:
            anchor = datetime.combine(booking.pickup_date, booking.flight_arrival_time)
        elif booking.pickup_time:
            anchor = datetime.combine(booking.pickup_date, booking.pickup_time) - timedelta(minutes=30)
        else:
            anchor = None
        if anchor is not None:
            out.append(("pick_up", anchor))
    return out


# ---------------------------------------------------------------------------
# Shift window helpers (naive datetimes — DB columns store no tz)
# ---------------------------------------------------------------------------

def _shift_window(shift: RosterShift) -> tuple[datetime, datetime]:
    """Naive [start, end] datetimes for an existing shift (handles overnight)."""
    end_date = shift.end_date or shift.date
    return (
        datetime.combine(shift.date, shift.start_time),
        datetime.combine(end_date, shift.end_time),
    )


def _is_already_linked(db: Session, shift_id: int, booking_id: int) -> bool:
    return (
        db.query(ShiftBookingLink)
        .filter(
            ShiftBookingLink.shift_id == shift_id,
            ShiftBookingLink.booking_id == booking_id,
        )
        .first()
        is not None
    )


def _booking_has_any_link(db: Session, booking_id: int) -> bool:
    return (
        db.query(ShiftBookingLink)
        .filter(ShiftBookingLink.booking_id == booking_id)
        .first()
        is not None
    )


def _find_extendable_auto_shift(
    db: Session, event_dt: datetime, settings: PlannerSettings
) -> Optional[RosterShift]:
    """An existing auto-shift, still SCHEDULED + unassigned, whose window is
    within `gap_max_minutes` of the new event (covers it OR sits adjacent).
    Returns None if no candidate.
    """
    gap_max = timedelta(minutes=settings.gap_max_minutes)
    candidates = (
        db.query(RosterShift)
        .filter(
            RosterShift.created_source == "auto",
            RosterShift.staff_id.is_(None),
            RosterShift.status == ShiftStatus.SCHEDULED,
            # Date filter trims the candidate set — gap_max is at most 2h so
            # a candidate must touch the event date or the adjacent day.
            RosterShift.date >= (event_dt.date() - timedelta(days=1)),
            RosterShift.date <= (event_dt.date() + timedelta(days=1)),
        )
        .all()
    )
    for s in candidates:
        s_start, s_end = _shift_window(s)
        # Cover or near: event sits inside [start - gap, end + gap].
        if s_start - gap_max <= event_dt <= s_end + gap_max:
            return s
    return None


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------

def _extend_and_link(
    db: Session,
    shift: RosterShift,
    event_type: str,
    event_dt: datetime,
    booking: Booking,
    settings: PlannerSettings,
) -> None:
    """Extend `shift`'s [start, end] to include the new event (with buffers)
    and add a ShiftBookingLink. No-op if already linked."""
    start_buffer = timedelta(minutes=settings.start_buffer_minutes)
    end_buffer = timedelta(minutes=settings.end_buffer_minutes)
    s_start, s_end = _shift_window(shift)
    new_start = min(s_start, event_dt - start_buffer)
    new_end = max(s_end, event_dt + end_buffer)
    if new_start != s_start:
        shift.date = new_start.date()
        shift.start_time = new_start.time()
    if new_end != s_end:
        shift.end_date = new_end.date() if new_end.date() != shift.date else None
        shift.end_time = new_end.time()
    # Re-round shift_type to match the new window.
    new_type, _ = round_to_shift_type(new_start, new_end)
    shift.shift_type = new_type

    if not _is_already_linked(db, shift.id, booking.id):
        db.add(ShiftBookingLink(shift_id=shift.id, booking_id=booking.id))


def _create_auto_shift(
    db: Session,
    event_type: str,
    event_dt: datetime,
    booking: Booking,
    settings: PlannerSettings,
) -> RosterShift:
    start_buffer = timedelta(minutes=settings.start_buffer_minutes)
    end_buffer = timedelta(minutes=settings.end_buffer_minutes)
    new_start = event_dt - start_buffer
    new_end = event_dt + end_buffer
    # Min shift length — same rule as the engine.
    min_duration = timedelta(minutes=settings.min_shift_minutes)
    if new_end - new_start < min_duration:
        new_end = new_start + min_duration
    shift_type, _ = round_to_shift_type(new_start, new_end)
    shift = RosterShift(
        staff_id=None,
        date=new_start.date(),
        end_date=new_end.date() if new_end.date() != new_start.date() else None,
        start_time=new_start.time(),
        end_time=new_end.time(),
        shift_type=shift_type,
        status=ShiftStatus.SCHEDULED,
        created_source="auto",
    )
    db.add(shift)
    db.flush()  # need shift.id for the link row
    db.add(ShiftBookingLink(shift_id=shift.id, booking_id=booking.id))
    return shift


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def auto_create_or_extend_for_booking(
    db: Session, booking: Booking, settings: PlannerSettings
) -> dict:
    """Per-event, ensure an auto-shift covers it (extending one nearby or
    creating a new one). Returns a small summary for logging.

    Skip rules:
      * Booking must be CONFIRMED (refunded / cancelled / pending no-op).
      * If the booking is already linked to ANY shift (admin, planner, or
        prior auto-run), skip — `auto_link_booking_to_shifts` runs first
        and will have linked admin/planner coverage already.
    """
    summary = {"created": 0, "extended": 0, "skipped": 0}
    if booking is None or booking.status != BookingStatus.CONFIRMED:
        summary["skipped"] = 1
        return summary

    events = _events_for_booking(booking)
    if not events:
        return summary

    for event_type, event_dt in events:
        # Per-event skip: if this booking is already linked to a shift whose
        # window covers this event, no auto-shift needed for it.
        already_covered = False
        existing_links = (
            db.query(ShiftBookingLink)
            .filter(ShiftBookingLink.booking_id == booking.id)
            .all()
        )
        for link in existing_links:
            s = db.query(RosterShift).filter(RosterShift.id == link.shift_id).first()
            if s is None:
                continue
            s_start, s_end = _shift_window(s)
            if s_start <= event_dt <= s_end:
                already_covered = True
                break
        if already_covered:
            summary["skipped"] += 1
            continue

        candidate = _find_extendable_auto_shift(db, event_dt, settings)
        if candidate is not None:
            _extend_and_link(db, candidate, event_type, event_dt, booking, settings)
            summary["extended"] += 1
        else:
            _create_auto_shift(db, event_type, event_dt, booking, settings)
            summary["created"] += 1

    db.commit()
    return summary


def auto_create_or_extend_async(booking_id: int) -> None:
    """FastAPI BackgroundTasks entry point.

    Owns its own DB session and swallows exceptions so a failure here can
    never break the confirmation flow that scheduled it (per the same
    pattern as `auto_link_booking_async`).
    """
    from database import SessionLocal
    from routers.roster import _load_planner_settings_rows

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking is None:
            logger.warning("auto_create_or_extend_async: booking %s not found", booking_id)
            return
        settings_rows = _load_planner_settings_rows(db)
        settings = PlannerSettings.from_kv(settings_rows)
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
