"""Python Playwright adapter for Bournemouth Airport live parking quotes."""

from __future__ import annotations

import os
from datetime import date

from airport_quote_service import (
    AirportQuoteInput,
    AirportQuoteScrapeResult,
    parse_boh_products,
    normalise_boh_time_slot,
)

BOH_COLLECT_URL = "https://book.bournemouthairport.com/book/BOH/Parking?parkingCmd=collectParkingDetails"


def _airport_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def fetch_bournemouth_airport_quote(
    quote_input: AirportQuoteInput,
    destination_id: str,
    *,
    timeout_ms: int = 30_000,
) -> AirportQuoteScrapeResult:
    """Fetch a live BOH quote.

    This function owns the browser lifecycle and does not touch the database.
    Callers should perform DB reads/writes before/after this function, not
    during it, so Chromium work does not hold a request DB connection.
    """
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
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)

            page.goto(BOH_COLLECT_URL, wait_until="domcontentloaded")

            page.locator("#changeEntryDate").evaluate(
                """(input, value) => {
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                _airport_date(quote_input.entry_date),
            )
            page.locator("#changeEntryTime").select_option(normalise_boh_time_slot(quote_input.entry_time))

            page.locator("#changeExitDate").evaluate(
                """(input, value) => {
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                _airport_date(quote_input.exit_date),
            )
            page.locator("#changeExitTime").select_option(normalise_boh_time_slot(quote_input.exit_time))
            page.locator("#selectDestination").select_option(destination_id)

            page.locator("form").first.evaluate(
                """(form) => {
                    if (!(form instanceof HTMLFormElement)) {
                        throw new Error('Parking search form not found');
                    }
                    form.submit();
                }"""
            )
            page.wait_for_load_state("domcontentloaded")
            page.locator(".item__price__val, .item__options-price").first.wait_for(
                state="attached",
                timeout=15_000,
            )

            products = parse_boh_products(page.content())
            return AirportQuoteScrapeResult(products=products, source_url=page.url)
        finally:
            browser.close()
