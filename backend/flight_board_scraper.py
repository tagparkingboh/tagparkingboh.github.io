"""Playwright adapter + parser for the Bournemouth Airport arrivals/departures board.

The public page (https://www.bournemouthairport.com/arrivals-departures/) renders
BOTH boards in the DOM at once — the Arrivals/Departures buttons only toggle an
`is-active` class — so a single page load captures everything. The site 403s
plain HTTP clients, so fetching runs through real Chromium in the quote worker,
reusing the same launch profile as the parking-price scraper.

Parsing and date resolution are pure functions so they can be unit-tested
against captured fixtures without a browser.
"""

from __future__ import annotations

import html as html_lib
import random
import re
from datetime import date, time
from typing import Optional

BOH_FLIGHT_BOARD_URL = "https://www.bournemouthairport.com/arrivals-departures/"

ARRIVALS_CONTAINER_ID = "widget-arrivals-content"
DEPARTURES_CONTAINER_ID = "widget-departures-content"

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD_RE = re.compile(r'<td[^>]*class="([a-zA-Z\- ]+)"[^>]*>(.*?)</td>', re.S | re.I)
# Mobile-only duplicate of the whole row nested inside the place cell — drop it.
_DETAILS_SPAN_RE = re.compile(
    r'<span[^>]*class="[^"]*details-for-small[^"]*"[^>]*>.*?</span>', re.S | re.I
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_cell(cell_html: str) -> str:
    cell_html = _DETAILS_SPAN_RE.sub("", cell_html)
    text = _TAG_RE.sub(" ", cell_html)
    return html_lib.unescape(" ".join(text.split()))


def _extract_section(page_html: str, container_id: str) -> str:
    start = page_html.find(f'id="{container_id}"')
    if start < 0:
        return ""
    other_id = (
        DEPARTURES_CONTAINER_ID
        if container_id == ARRIVALS_CONTAINER_ID
        else ARRIVALS_CONTAINER_ID
    )
    end = page_html.find(f'id="{other_id}"', start)
    if end < 0:
        return page_html[start:]
    return page_html[start:end]


def _parse_rows(section_html: str) -> list[dict]:
    rows = []
    for tr_html in _TR_RE.findall(section_html):
        cells = _TD_RE.findall(tr_html)
        if not cells:
            continue  # thead rows use <th>
        row = {
            "place": None,
            "airline": None,
            "flight": None,
            "date": None,
            "scheduled": None,
            "status": None,
        }
        # Two cells share class "time": the first is the date (DD/MM), the
        # second the scheduled time (HH:MM).
        times: list[str] = []
        for css_class, content in cells:
            value = _clean_cell(content)
            if "place" in css_class:
                row["place"] = value
            elif "airline" in css_class:
                row["airline"] = value
            elif "flight" in css_class:
                row["flight"] = value
            elif "time" in css_class:
                times.append(value)
            elif "status" in css_class:
                row["status"] = value
        if times:
            row["date"] = times[0]
        if len(times) > 1:
            row["scheduled"] = times[1]
        if row["flight"] or row["place"]:
            rows.append(row)
    return rows


def parse_boh_flight_board(page_html: str) -> dict:
    """Parse both boards out of the arrivals/departures page HTML."""
    return {
        "arrivals": _parse_rows(_extract_section(page_html, ARRIVALS_CONTAINER_ID)),
        "departures": _parse_rows(_extract_section(page_html, DEPARTURES_CONTAINER_ID)),
    }


def resolve_board_date(day_month: str, today: date) -> Optional[date]:
    """Resolve the board's year-less DD/MM into a full date.

    The board only shows flights near "now", so of the candidate years
    (last/this/next) the correct one is whichever lands closest to today —
    this handles both directions of the year boundary (a 31/12 row seen on
    01/01, and a 01/01 row seen on 31/12).
    """
    if not day_month:
        return None
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})\s*", day_month)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue  # e.g. 29/02 in a non-leap year
        candidates.append(candidate)
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs((candidate - today).days))


def parse_board_hhmm(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return time(hour, minute)


def fetch_bournemouth_flight_board(*, timeout_ms: int = 30_000) -> dict:
    """Load the live board with Chromium and parse both tables.

    Owns the browser lifecycle and never touches the database — same contract
    as fetch_bournemouth_airport_quote. Raises if the page loads but neither
    board yields rows (site layout change), so callers keep their last good
    snapshot instead of storing an empty board.
    """
    import os

    from playwright.sync_api import sync_playwright

    proxy_url = os.environ.get("SCRAPE_PROXY_URL")
    launch_kwargs = {"headless": True}
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1365, "height": 900},
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)

            page.goto(BOH_FLIGHT_BOARD_URL, wait_until="domcontentloaded")
            page.locator(f"#{ARRIVALS_CONTAINER_ID} table tbody tr").first.wait_for(
                state="attached", timeout=15_000
            )
            # Linger like a person reading the board rather than grabbing the
            # DOM the instant it exists.
            page.wait_for_timeout(random.uniform(800, 2_200))

            page_html = page.content()
            board = parse_boh_flight_board(page_html)
            if not board["arrivals"] and not board["departures"]:
                print(
                    "[FLIGHT_BOARD_SCRAPE_EMPTY] parsed no rows from either board; "
                    f"url={page.url}; snippet={page_html[:4_000]!r}",
                    flush=True,
                )
                raise RuntimeError("flight board parsed empty")
            board["source_url"] = page.url
            return board
        finally:
            browser.close()
