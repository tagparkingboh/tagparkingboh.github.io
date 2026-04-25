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
        window_end = window_start + timedelta(days=engine_settings.window_days)

        bookings = (
            db.query(Booking)
            .filter(
                Booking.status == BookingStatus.CONFIRMED,
                or_(
                    and_(
                        Booking.dropoff_date >= window_start,
                        Booking.dropoff_date < window_end,
                    ),
                    and_(
                        Booking.pickup_date >= window_start,
                        Booking.pickup_date < window_end,
                    ),
                ),
            )
            .all()
        )
        shifts = (
            db.query(RosterShift)
            .filter(
                RosterShift.date >= window_start,
                RosterShift.date < window_end,
            )
            .all()
        )
        staff = (
            db.query(User)
            .filter(User.is_active == True, User.is_admin == False)
            .all()
        )
        holidays = (
            db.query(EmployeeHoliday)
            .filter(
                EmployeeHoliday.start_date < window_end,
                EmployeeHoliday.end_date >= window_start,
            )
            .all()
        )

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
