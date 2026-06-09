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

    Kept for callers that pass a single timestamp; new code should prefer
    `_shift_covers_event_window` so the rule matches `_events_for_booking`'s
    (start_anchor, end_anchor) shape.
    """
    if event_dt is None:
        return False
    ev_date = event_dt.date()
    ev_time = event_dt.time()
    end_date = getattr(shift, "end_date", None) or shift.date
    if end_date == shift.date and shift.end_time < shift.start_time:
        end_date = shift.date + timedelta(days=1)
    if shift.date == end_date:
        if ev_date != shift.date:
            return False
        return shift.start_time <= ev_time <= shift.end_time
    # Overnight: build naive datetimes for the full span and compare.
    span_start = datetime.combine(shift.date, shift.start_time)
    span_end = datetime.combine(end_date, shift.end_time)
    return span_start <= event_dt <= span_end


def _shift_covers_event_window(
    shift: RosterShift, start_dt: datetime, end_dt: datetime,
    *, end_buffer_minutes: int = 0,
) -> bool:
    """Does `shift` cover the entire [start_dt, end_dt] event window?

    Both endpoints, plus the configured end buffer, must fall inside the
    shift's wall-clock span. This is the rule the rebuild's skip-if-covered
    uses, exposed here so auto-link can apply the same definition of
    "covered" — otherwise a frozen shift can be considered covering by the
    rebuild but non-covering by auto-link, leaving the booking orphaned
    (no new shift, no link).
    """
    if start_dt is None or end_dt is None:
        return False
    end_date = getattr(shift, "end_date", None) or shift.date
    if end_date == shift.date and shift.end_time < shift.start_time:
        end_date = shift.date + timedelta(days=1)
    span_start = datetime.combine(shift.date, shift.start_time)
    span_end = datetime.combine(end_date, shift.end_time)
    required_end = end_dt + timedelta(minutes=end_buffer_minutes)
    if required_end < end_dt:
        return False
    return span_start <= start_dt and required_end <= span_end


def _planner_settings(db: Session):
    """Best-effort read of live planner settings for auto-link."""
    try:
        from roster_planner import PlannerSettings
        from routers.roster import _load_planner_settings_rows

        return PlannerSettings.from_kv(_load_planner_settings_rows(db))
    except Exception:
        from roster_planner import PlannerSettings

        return PlannerSettings.from_kv({})


def _shift_linked_bookings(shift: RosterShift) -> list[Booking]:
    """Return real linked bookings when the relationship is loaded/iterable."""
    linked = getattr(shift, "bookings", None)
    if isinstance(linked, (list, tuple, set)):
        return [
            booking
            for booking in linked
            if getattr(booking, "status", None) != BookingStatus.CANCELLED
        ]
    return []


def _required_windows_for_shift_candidate(
    shift: RosterShift,
    booking: Booking,
    settings,
) -> list[tuple[datetime, datetime]]:
    """Buffered windows the candidate shift must cover for this booking.

    The window is calculated from the booking plus the candidate shift's
    existing linked bookings, using the same clustering and tight-pair buffer
    rules as auto-roster. This catches cases like 22:55 + 23:00 pickups:
    the pair is under 30 minutes apart, so the required start moves another
    30 minutes earlier.
    """
    from auto_roster import _events_for_booking
    from roster_planner import (
        Event,
        UK_TZ,
        compute_cluster_shift_window,
        group_events_by_gap,
    )

    source_bookings = [booking]
    seen_booking_ids = {getattr(booking, "id", None)}
    for linked_booking in _shift_linked_bookings(shift):
        linked_id = getattr(linked_booking, "id", None)
        if linked_id in seen_booking_ids:
            continue
        seen_booking_ids.add(linked_id)
        source_bookings.append(linked_booking)

    events: list[Event] = []
    for source in source_bookings:
        for event_type, start_dt, end_dt in _events_for_booking(source):
            events.append(
                Event(
                    booking_id=getattr(source, "id", None),
                    booking_reference=getattr(source, "reference", "") or "",
                    event_type=event_type,
                    event_time=start_dt.replace(tzinfo=UK_TZ),
                    end_anchor_time=end_dt.replace(tzinfo=UK_TZ),
                )
            )
    if not events:
        return []

    windows: list[tuple[datetime, datetime]] = []
    for cluster in group_events_by_gap(
        events,
        gap_max_minutes=settings.gap_max_minutes,
        mixed_gap_max_minutes=settings.mixed_gap_max_minutes,
    ):
        if not any(e.booking_id == getattr(booking, "id", None) for e in cluster.events):
            continue

        required_start, required_end = compute_cluster_shift_window(
            cluster,
            start_buffer_minutes=settings.start_buffer_minutes,
            end_buffer_minutes=settings.end_buffer_minutes,
            min_shift_minutes=settings.min_shift_minutes,
        )
        windows.append((
            required_start.replace(tzinfo=None),
            required_end.replace(tzinfo=None),
        ))

    return windows


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
      * Window covers the booking's buffered cluster window. A booking can
        hit two shifts (one for drop-off, another for pickup); both get linked.
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
    if getattr(booking, "status", None) not in (
        BookingStatus.CONFIRMED,
        BookingStatus.REFUNDED,
    ):
        return []
    try:
        # Use the same event extraction as the rebuild — one helper, one
        # definition of where a booking's work happens. For a pickup
        # that's [flight_arrival, flight_arrival + 30] (canonical handoff);
        # for a drop-off both anchors are the dropoff time. Aligning here
        # eliminates the skip-vs-link disagreement that left bookings
        # orphaned when the literal pickup_time differed from the derived
        # handoff. Code-review fix 2026-05-28.
        from auto_roster import _events_for_booking
        events = _events_for_booking(booking)
        if not events:
            return []
        settings = _planner_settings(db)

        # Pull candidate shifts in a date window that could plausibly
        # cover any event endpoint. -1/+1 catches overnight wraps.
        all_dts = [dt for _et, s, e in events for dt in (s, e)]
        min_d = min(dt.date() for dt in all_dts) - timedelta(days=1)
        max_d = max(dt.date() for dt in all_dts) + timedelta(days=1)
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
            if not any(
                _shift_covers_event_window(shift, s, e)
                for s, e in _required_windows_for_shift_candidate(
                    shift,
                    booking,
                    settings,
                )
            ):
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
