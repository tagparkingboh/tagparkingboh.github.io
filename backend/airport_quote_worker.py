"""Dedicated FastAPI worker for BOH parking quote scrapes.

This app intentionally has no database dependency. The request-serving API calls
it to run Chromium work in a separate process/service, then persists the quote
snapshot with a short-lived DB session after the worker returns.
"""

from __future__ import annotations

import os
from threading import BoundedSemaphore
from datetime import date, time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from airport_quote_scraper import fetch_bournemouth_airport_quote
from airport_quote_service import AirportQuoteInput

app = FastAPI(title="TAG Airport Quote Worker")


def _max_concurrency() -> int:
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_MAX_CONCURRENCY", "2")
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


SCRAPE_SEMAPHORE = BoundedSemaphore(_max_concurrency())


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
    return {"ok": True, "service": "airport_quote_worker"}


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
        scrape = fetch_bournemouth_airport_quote(quote_input)
    finally:
        SCRAPE_SEMAPHORE.release()
    return {
        "products": [product.to_api() for product in scrape.products],
        "sourceUrl": scrape.source_url,
    }
