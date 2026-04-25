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
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from db_models import PlannerRun

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
