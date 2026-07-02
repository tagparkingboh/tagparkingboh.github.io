"""Persistence + scheduling helpers for the BOH arrivals/departures board.

The 30-minute scheduler job (registered in email_scheduler.start_scheduler,
gated by FLIGHT_BOARD_SCRAPE_ENABLED) calls the quote worker, then:
  1. stores a FlightBoardSnapshot — the live board /employee displays;
  2. upserts FlightScheduleHistory — SCHEDULED times only, one row per
     (direction, flight_date, flight_number), the long-term demand signal;
  3. prunes snapshots older than 30 days (history is never pruned).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone

import pytz

from flight_board_scraper import parse_board_hhmm, resolve_board_date

logger = logging.getLogger(__name__)

FLIGHT_BOARD_SCRAPE_ENABLED_ENV = "FLIGHT_BOARD_SCRAPE_ENABLED"
FLIGHT_BOARD_SCRAPE_INTERVAL_MINUTES = 30
# Up to ±4 minutes of drift per firing so the hits never land on an exact
# half-hour clock pattern.
FLIGHT_BOARD_SCRAPE_JITTER_SECONDS = 240
FLIGHT_BOARD_SNAPSHOT_RETENTION_DAYS = 30

UK_TZ = pytz.timezone("Europe/London")


def is_flight_board_scrape_enabled() -> bool:
    raw = os.environ.get(FLIGHT_BOARD_SCRAPE_ENABLED_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def uk_today() -> date:
    return datetime.now(UK_TZ).date()


def build_history_rows(board: dict, *, today: date, now: datetime) -> list[dict]:
    """Turn a scraped board into upsertable history rows.

    Pure so the filtering/dedup/date-resolution rules are unit-testable:
    rows missing a parseable date, scheduled time, or flight number are
    dropped; duplicates of the same (direction, date, flight) within one
    board keep the last occurrence (Postgres ON CONFLICT cannot touch the
    same row twice in one statement).
    """
    by_key: dict[tuple, dict] = {}
    for direction, board_key in (("arrival", "arrivals"), ("departure", "departures")):
        for row in board.get(board_key) or []:
            flight_date = resolve_board_date(row.get("date"), today)
            scheduled_time = parse_board_hhmm(row.get("scheduled"))
            flight_number = (row.get("flight") or "").strip()
            if not (flight_date and scheduled_time and flight_number):
                continue
            key = (direction, flight_date, flight_number)
            by_key[key] = {
                "direction": direction,
                "flight_date": flight_date,
                "scheduled_time": scheduled_time,
                "flight_number": flight_number,
                "airline": (row.get("airline") or "").strip() or None,
                "place": (row.get("place") or "").strip() or None,
                "first_seen_at": now,
                "last_seen_at": now,
            }
    return list(by_key.values())


def upsert_flight_schedule_history(db, board: dict) -> int:
    """Upsert history rows; a re-timed flight updates scheduled_time and
    last_seen_at while first_seen_at keeps the original sighting."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db_models import FlightScheduleHistory

    rows = build_history_rows(
        board, today=uk_today(), now=datetime.now(timezone.utc)
    )
    if not rows:
        return 0
    stmt = pg_insert(FlightScheduleHistory.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_flight_schedule_direction_date_flight",
        set_={
            "scheduled_time": stmt.excluded.scheduled_time,
            "airline": stmt.excluded.airline,
            "place": stmt.excluded.place,
            "last_seen_at": stmt.excluded.last_seen_at,
        },
    )
    db.execute(stmt)
    return len(rows)


def prune_old_flight_snapshots(db) -> int:
    from db_models import FlightBoardSnapshot

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=FLIGHT_BOARD_SNAPSHOT_RETENTION_DAYS
    )
    return (
        db.query(FlightBoardSnapshot)
        .filter(FlightBoardSnapshot.created_at < cutoff)
        .delete(synchronize_session=False)
    )


def process_flight_board_scrape(session_factory) -> None:
    """Scheduler entry point: scrape via the worker and persist results.

    Failures store an `error` snapshot for observability but never touch
    history and never remove the last good board — /employee keeps serving
    the most recent `ok` snapshot with its age displayed.
    """
    from airport_quote_worker_client import (
        fetch_flight_board_via_worker,
        get_airport_quote_worker_url,
    )
    from db_models import FlightBoardSnapshot

    worker_url = get_airport_quote_worker_url()
    if not worker_url:
        logger.warning("flight_board_scrape skipped: AIRPORT_QUOTE_WORKER_URL not set")
        return

    board = None
    error = None
    try:
        board = fetch_flight_board_via_worker(worker_url)
    except Exception as exc:  # noqa: BLE001 — background job must not raise
        logger.exception("flight_board_scrape worker call failed")
        error = str(exc)[:2000]

    db = session_factory()
    try:
        if board is None:
            db.add(FlightBoardSnapshot(status="error", error=error))
        else:
            db.add(
                FlightBoardSnapshot(
                    status="ok",
                    arrivals_json=board["arrivals"],
                    departures_json=board["departures"],
                    source_url=board.get("source_url"),
                )
            )
            upserted = upsert_flight_schedule_history(db, board)
            pruned = prune_old_flight_snapshots(db)
            logger.info(
                "flight_board_scrape ok: arrivals=%s departures=%s history_upserts=%s pruned=%s",
                len(board["arrivals"]), len(board["departures"]), upserted, pruned,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("flight_board_scrape persistence failed")
    finally:
        db.close()
