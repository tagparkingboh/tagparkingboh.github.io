"""Dedicated FastAPI worker for BOH parking quote scrapes.

This app intentionally has no database dependency. The request-serving API calls
it to run Chromium work in a separate process/service, then persists the quote
snapshot with a short-lived DB session after the worker returns.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore
from datetime import date, time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from airport_quote_scraper import fetch_bournemouth_airport_quote
from airport_quote_service import AirportQuoteInput
from flight_board_scraper import fetch_bournemouth_flight_board

logger = logging.getLogger(__name__)

app = FastAPI(title="TAG Airport Quote Worker")


def _max_concurrency() -> int:
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_MAX_CONCURRENCY", "2")
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def _scrape_timeout_seconds() -> float:
    """Hard deadline for a single Chromium scrape, watchdog-enforced.

    Well above a healthy scrape (~10-30s incl. launch) and above both client
    timeouts (12s quote / 45s board), so it only fires on genuine hangs.
    """
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_SCRAPE_TIMEOUT_SECONDS", "90")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 90.0


def _max_stuck_scrapes() -> int:
    """Stuck-scrape count at which the worker exits for a clean restart.

    0 disables the self-restart backstop.
    """
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_MAX_STUCK_SCRAPES", "")
    try:
        return max(0, int(raw))
    except ValueError:
        pass
    return _max_concurrency()


SCRAPE_SEMAPHORE = BoundedSemaphore(_max_concurrency())

# Scrapes run on watchdog-owned threads so a hung Chromium can be abandoned:
# the request thread stops waiting at the deadline and its semaphore slot is
# released in the endpoint's `finally`. Without this, a hung scrape held its
# slot forever — two hangs wedged the worker into permanent 429s for two days
# (2026-07-08 flight-board outage). Abandoned threads cannot be killed, so the
# pool is sized to keep serving with up to _max_stuck_scrapes() zombies
# outstanding before the self-restart backstop trips.
_SCRAPE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_max_concurrency() + max(1, _max_stuck_scrapes()),
    thread_name_prefix="scrape",
)

_stuck_lock = threading.Lock()
_stuck_scrapes = 0


def _terminate_process() -> None:
    """Exit hard for Railway's ON_FAILURE restart. Wrapped so tests can patch it."""
    os._exit(1)


def _run_scrape_with_deadline(label: str, fn):
    """Run fn on a watchdog thread; abandon it if it outlives the deadline.

    Each stuck scrape leaks its thread and a Chromium process. Once
    _max_stuck_scrapes() of them are outstanding at once, the container is
    better off dead: exit non-zero and let Railway restart it clean.
    """
    global _stuck_scrapes
    future = _SCRAPE_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=_scrape_timeout_seconds())
    except HTTPException:
        raise
    except FutureTimeoutError:
        with _stuck_lock:
            _stuck_scrapes += 1
            stuck_now = _stuck_scrapes

        def _finished_late(_future):
            global _stuck_scrapes
            with _stuck_lock:
                _stuck_scrapes -= 1

        # If the scrape ever does finish, it stops counting as stuck (fires
        # immediately when it completed in the timeout/bookkeeping window).
        future.add_done_callback(_finished_late)

        limit = _max_stuck_scrapes()
        if limit and stuck_now >= limit:
            logger.critical(
                "%s stuck scrape(s) outstanding (limit %s); exiting for a clean restart",
                stuck_now,
                limit,
            )
            _terminate_process()
        logger.error(
            "%s scrape exceeded %.0fs; abandoning its thread (%s now stuck)",
            label,
            _scrape_timeout_seconds(),
            stuck_now,
        )
        raise HTTPException(status_code=504, detail=f"{label} scrape timed out")
    except Exception as exc:
        # Scrape failed on its own (Playwright timeout, BOH flow bounce, …).
        # The thread finished cleanly — nothing is stuck — so answer with a
        # tidy 502 instead of letting the raw traceback 500 through ASGI.
        # The scraper's own debug capture already logged what BOH served.
        summary = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        logger.error(
            "%s scrape failed: %s%s",
            label,
            type(exc).__name__,
            f": {summary}" if summary else "",
        )
        raise HTTPException(status_code=502, detail=f"{label} scrape failed") from exc


class AirportQuoteWorkerRequest(BaseModel):
    entry_date: date = Field(alias="entryDate")
    entry_time: str = Field(alias="entryTime")
    exit_date: date = Field(alias="exitDate")
    exit_time: str = Field(alias="exitTime")

    model_config = {"populate_by_name": True}


def _parse_time(value: str, field_name: str) -> time:
    try:
        hour, minute = [int(part) for part in value.split(":")[:2]]
    except (AttributeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be HH:MM")
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise HTTPException(status_code=400, detail=f"{field_name} must be HH:MM")
    return time(hour, minute)


@app.get("/")
def worker_healthcheck():
    return {"ok": True, "service": "airport_quote_worker", "stuck_scrapes": _stuck_scrapes}


@app.post("/internal/airport-parking/scrape")
def scrape_airport_quote(request: AirportQuoteWorkerRequest):
    quote_input = AirportQuoteInput(
        entry_date=request.entry_date,
        entry_time=_parse_time(request.entry_time, "entryTime"),
        exit_date=request.exit_date,
        exit_time=_parse_time(request.exit_time, "exitTime"),
    )
    acquired = SCRAPE_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=429, detail="Airport quote worker is busy")
    try:
        scrape = _run_scrape_with_deadline(
            "airport-parking", lambda: fetch_bournemouth_airport_quote(quote_input)
        )
    finally:
        SCRAPE_SEMAPHORE.release()
    return {
        "products": [product.to_api() for product in scrape.products],
        "sourceUrl": scrape.source_url,
    }


@app.post("/internal/flight-board/scrape")
def scrape_flight_board():
    """Scrape the public BOH arrivals/departures board (both tables, one load)."""
    acquired = SCRAPE_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=429, detail="Airport quote worker is busy")
    try:
        board = _run_scrape_with_deadline("flight-board", fetch_bournemouth_flight_board)
    finally:
        SCRAPE_SEMAPHORE.release()
    return {
        "arrivals": board["arrivals"],
        "departures": board["departures"],
        "sourceUrl": board.get("source_url"),
    }
