"""Client for the dedicated Bournemouth Airport quote worker."""

from __future__ import annotations

import os
from typing import Optional

import httpx

from airport_quote_service import (
    AirportProduct,
    AirportQuoteInput,
    AirportQuoteScrapeResult,
    Scraper,
)


def _timeout_seconds() -> float:
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_TIMEOUT_SECONDS", "12")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 12.0


def get_airport_quote_worker_url() -> Optional[str]:
    raw = os.environ.get("AIRPORT_QUOTE_WORKER_URL")
    if not raw:
        return None
    return raw.rstrip("/")


def build_worker_scraper(worker_url: str) -> Scraper:
    endpoint = f"{worker_url.rstrip('/')}/internal/airport-parking/scrape"

    def _scrape(quote_input: AirportQuoteInput) -> AirportQuoteScrapeResult:
        response = httpx.post(
            endpoint,
            json={
                "entryDate": quote_input.entry_date.isoformat(),
                "entryTime": quote_input.entry_time.strftime("%H:%M"),
                "exitDate": quote_input.exit_date.isoformat(),
                "exitTime": quote_input.exit_time.strftime("%H:%M"),
            },
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
        products = [
            AirportProduct(
                name=item["name"],
                price_pence=int(item["pricePence"]),
                price_text=item.get("priceText") or f"£{int(item['pricePence']) / 100:.2f}",
            )
            for item in payload.get("products", [])
        ]
        return AirportQuoteScrapeResult(
            products=products,
            source_url=payload.get("sourceUrl"),
        )

    return _scrape


def get_worker_scraper_from_env() -> Optional[Scraper]:
    worker_url = get_airport_quote_worker_url()
    if not worker_url:
        return None
    return build_worker_scraper(worker_url)


def _flight_board_timeout_seconds() -> float:
    # Longer than the quote timeout: this is a background job, not a customer
    # request, so waiting out a slow page load beats a spurious failure.
    raw = os.environ.get("FLIGHT_BOARD_WORKER_TIMEOUT_SECONDS", "45")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 45.0


def fetch_flight_board_via_worker(worker_url: str) -> dict:
    """Call the worker's flight-board scrape and normalise the payload."""
    response = httpx.post(
        f"{worker_url.rstrip('/')}/internal/flight-board/scrape",
        timeout=_flight_board_timeout_seconds(),
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "arrivals": payload.get("arrivals") or [],
        "departures": payload.get("departures") or [],
        "source_url": payload.get("sourceUrl"),
    }
