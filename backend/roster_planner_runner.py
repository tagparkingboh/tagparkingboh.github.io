"""Shadow-mode runner for the Roster Planner.

The engine itself (`roster_planner.py`) is a pure function. This module is
the side-effect bridge: every engine invocation flows through here so we can
persist a `planner_runs` audit row without coupling the engine to the DB.

Shadow mode invariant — *no writes to roster_shifts go through this module.*
Even if the engine produces "what to write," we only record the proposal.
The audit table is the kill-switch boundary: ship code that writes runs,
flip the live-write flag in a follow-up once we trust the proposals.

Failure isolation — every public function here swallows its own exceptions
and writes them to error_logs (when available). The booking flow that
triggers a planner run must never fail because the planner crashed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from db_models import (
    Booking,
    BookingStatus,
    EmployeeHoliday,
    PlannerRun,
    RosterShift,
    ServiceType,
    ShiftBookingLink,
    ShiftStatus,
    User,
)

logger = logging.getLogger(__name__)


# Closed set of trigger event tags. Stored as String(50) on PlannerRun.
TRIGGER_MANUAL = "manual"
TRIGGER_BOOKING_CONFIRMED = "booking_confirmed"
TRIGGER_BOOKING_CANCELLED = "booking_cancelled"
TRIGGER_BOOKING_RESCHEDULED = "booking_rescheduled"
TRIGGER_HOLIDAY_CHANGED = "holiday_changed"
TRIGGER_SETTINGS_CHANGED = "settings_changed"


def _safe_json(payload) -> Optional[str]:
    """Serialise to JSON; return None on failure rather than raising.
    The audit row is best-effort — we'd rather record a partial run than
    drop the row entirely because one field didn't serialise."""
    if payload is None:
        return None
    try:
        return json.dumps(payload, default=str)
    except (TypeError, ValueError) as e:
        logger.warning("planner_runs serialise failed (%s); writing null", e)
        return None


def fire_engine(
    db: Session,
    *,
    trigger_event: str,
    trigger_ref: Optional[str] = None,
) -> Optional[str]:
    """Run the engine end-to-end and audit the result. Returns run_id or None.

    Owns the full read path: settings → bookings/shifts/staff/holidays →
    propose_roster() → record_run(). Same query shape as the /propose
    endpoint, kept inline here so the BackgroundTask-safe call site has
    no external dependency on the FastAPI request lifecycle.

    Failure isolation: any exception (DB, engine, serialise) is caught and
    logged. Caller never sees a raise. This is what makes it safe to fire
    from booking-confirmation handlers — a planner bug must not break
    payment processing.
    """
    # Imports here (not module-level) to avoid an import cycle:
    # roster_planner_runner is imported from routers.roster, and
    # roster_planner imports from db_models which is fine, but settings
    # loading lives in routers.roster which would close the cycle.
    from roster_planner import propose_roster, PlannerSettings, UK_TZ
    from routers.roster import _load_planner_settings_rows

    try:
        started_at = datetime.utcnow()
        parsed = _load_planner_settings_rows(db)
        engine_settings = PlannerSettings.from_kv(parsed)
        now = datetime.now(UK_TZ)
        window_start = now.date()
        # window_days = None / 0 → no upper bound (locked 2026-05-05). DB
        # prefetch drops the `< window_end` filter when unbounded so the
        # engine sees every confirmed booking from today onwards, no matter
        # how far ahead the trip date is.
        bounded = engine_settings.window_days is not None and engine_settings.window_days > 0
        window_end = window_start + timedelta(days=engine_settings.window_days) if bounded else None

        booking_filters = [Booking.status == BookingStatus.CONFIRMED]
        if bounded:
            booking_filters.append(
                or_(
                    and_(
                        Booking.dropoff_date >= window_start,
                        Booking.dropoff_date < window_end,
                    ),
                    and_(
                        Booking.pickup_date >= window_start,
                        Booking.pickup_date < window_end,
                    ),
                )
            )
        else:
            # Unbounded: only need the lower bound on either side.
            booking_filters.append(
                or_(
                    Booking.dropoff_date >= window_start,
                    Booking.pickup_date >= window_start,
                )
            )
        bookings = db.query(Booking).filter(*booking_filters).all()

        shift_filters = [RosterShift.date >= window_start]
        if bounded:
            shift_filters.append(RosterShift.date < window_end)
        shifts = db.query(RosterShift).filter(*shift_filters).all()

        staff = (
            db.query(User)
            .filter(User.is_active == True)
            .all()
        )
        holiday_filters = [EmployeeHoliday.end_date >= window_start]
        if bounded:
            holiday_filters.append(EmployeeHoliday.start_date < window_end)
        holidays = db.query(EmployeeHoliday).filter(*holiday_filters).all()

        proposal = propose_roster(
            bookings=bookings,
            shifts=shifts,
            staff=staff,
            holidays=holidays,
            settings=engine_settings,
            now=now,
        )
        return record_run(
            db,
            trigger_event=trigger_event,
            trigger_ref=trigger_ref,
            proposal=proposal,
            started_at=started_at,
        )
    except Exception as e:
        logger.exception("fire_engine failed (trigger=%s ref=%s): %s",
                         trigger_event, trigger_ref, e)
        return None


def fire_engine_async(
    trigger_event: str,
    trigger_ref: Optional[str] = None,
) -> None:
    """BackgroundTasks-safe entry — owns its own DB session.

    The caller's request session ends as soon as the response is sent;
    BackgroundTasks runs after that, so we can't reuse the request session.
    Open a fresh one, fire the engine, close.
    """
    from database import SessionLocal
    if SessionLocal is None:
        # No DB configured (test/import context). Silently no-op.
        return
    db = SessionLocal()
    try:
        fire_engine(db, trigger_event=trigger_event, trigger_ref=trigger_ref)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _shift_covers_event(shift: RosterShift, event_dt: datetime) -> bool:
    """Does `shift` cover the given event timestamp?

    Single-day shift: event date matches shift.date AND event time falls
    inside [shift.start_time, shift.end_time].

    Overnight shift (end_date > date): event must fall inside the contiguous
    span starting at shift.date+start_time and ending at shift.end_date+
    end_time. We compare naive timestamps because both shift columns and
    booking dropoff_/pickup_time are stored without tz info.
    """
    if event_dt is None:
        return False
    ev_date = event_dt.date()
    ev_time = event_dt.time()
    end_date = getattr(shift, "end_date", None) or shift.date
    if shift.date == end_date:
        if ev_date != shift.date:
            return False
        return shift.start_time <= ev_time <= shift.end_time
    # Overnight: build naive datetimes for the full span and compare.
    span_start = datetime.combine(shift.date, shift.start_time)
    span_end = datetime.combine(end_date, shift.end_time)
    return span_start <= event_dt <= span_end


def auto_link_booking_to_shifts(db: Session, booking: Booking) -> list[int]:
    """Attach a freshly-confirmed booking to every live planner-sourced
    jockey shift whose window covers either of the booking's events.

    Match rules:
      * Status SCHEDULED or CONFIRMED — IN_PROGRESS / COMPLETED / CANCELLED
        are skipped (current shift already running, or the row's done).
      * Includes both planner-sourced AND admin-created shifts — alignment
        between bookings and shifts must be automatic regardless of how
        the shift was created (per user preference May 2026).
      * intended_driver_type 'jockey' or NULL — fleet shifts ignored
        (bookings are jockey workload in the current model). NULL coerces
        to jockey to match the shift_to_response convention.
      * Window covers booking's drop-off OR pickup event time. A booking
        can hit two shifts (one for drop-off, another for pickup); both
        get linked.
      * Idempotent: skip pairs that already have a ShiftBookingLink row.

    Returns the list of shift IDs that received a new link this call.

    Failure isolation: any DB exception is logged and swallowed so the
    booking-confirmed flow that calls this never breaks because of a
    planner side-effect.
    """
    if booking is None or booking.id is None:
        return []
    if getattr(booking, "service_type", None) == ServiceType.PARK_RIDE:
        return []
    try:
        # Build the up-to-2 event timestamps we need to match against.
        events: list[datetime] = []
        if booking.dropoff_date and booking.dropoff_time:
            events.append(datetime.combine(booking.dropoff_date, booking.dropoff_time))
        if booking.pickup_date and booking.pickup_time:
            events.append(datetime.combine(booking.pickup_date, booking.pickup_time))
        if not events:
            return []

        # Pull candidate shifts: planner-sourced, jockey-eligible, scheduled
        # or confirmed, in a date window that could plausibly cover any of
        # the booking's events. Date filter trims the candidate set in the
        # DB so coverage check stays cheap in Python.
        min_d = min(ev.date() for ev in events) - timedelta(days=1)  # -1 catches overnight
        max_d = max(ev.date() for ev in events)
        candidates = (
            db.query(RosterShift)
            .filter(
                RosterShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED]),
                RosterShift.date >= min_d,
                RosterShift.date <= max_d,
            )
            .all()
        )

        linked: list[int] = []
        for shift in candidates:
            intended = getattr(shift, "intended_driver_type", None)
            if intended not in (None, "jockey"):
                continue  # fleet (or other) — not jockey workload
            if not any(_shift_covers_event(shift, ev) for ev in events):
                continue
            # Idempotency: don't write a duplicate link.
            existing = (
                db.query(ShiftBookingLink)
                .filter(
                    ShiftBookingLink.shift_id == shift.id,
                    ShiftBookingLink.booking_id == booking.id,
                )
                .first()
            )
            if existing:
                continue
            db.add(ShiftBookingLink(shift_id=shift.id, booking_id=booking.id))
            linked.append(shift.id)

        if linked:
            db.commit()
        return linked
    except Exception as e:
        logger.exception(
            "auto_link_booking_to_shifts failed booking_id=%s: %s",
            getattr(booking, "id", None), e,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return []


def auto_link_booking_async(booking_id: int) -> None:
    """BackgroundTasks-safe entry — owns its own DB session.

    Mirrors fire_engine_async: the request session ends with the response,
    so we open a fresh one for the deferred work.
    """
    from database import SessionLocal
    if SessionLocal is None:
        return
    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking is not None:
            auto_link_booking_to_shifts(db, booking)
    finally:
        try:
            db.close()
        except Exception:
            pass


def record_run(
    db: Session,
    *,
    trigger_event: str,
    trigger_ref: Optional[str],
    proposal: dict,
    started_at: datetime,
) -> Optional[str]:
    """Persist one engine result to `planner_runs`. Returns the run_id on
    success, None on failure (failure already logged).

    `proposal` is the dict produced by `propose_roster()` — it already
    contains run_id, window_start, window_end, proposed_shifts, warnings,
    summary. We pluck the audit-relevant slices and store the rest as
    proposal_json so the QA UI can render historical runs faithfully.
    """
    try:
        run_id = proposal.get("run_id")
        if not run_id:
            logger.warning("planner_runs: proposal missing run_id; skip")
            return None

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

        row = PlannerRun(
            run_id=run_id,
            trigger_event=trigger_event,
            trigger_ref=trigger_ref,
            window_start=proposal["window_start"],
            window_end=proposal["window_end"],
            proposal_json=_safe_json(proposal),
            warnings_json=_safe_json(proposal.get("warnings", [])),
            duration_ms=duration_ms,
        )
        db.add(row)
        db.commit()
        return run_id
    except Exception as e:
        # Booking flow must never fail because the planner audit failed.
        logger.exception("planner_runs record_run failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return None
