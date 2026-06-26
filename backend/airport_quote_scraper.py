"""Python Playwright adapter for Bournemouth Airport live parking quotes."""

from __future__ import annotations

import os
from datetime import date

from airport_quote_service import (
    AirportQuoteInput,
    AirportQuoteScrapeResult,
    BOH_REQUIRED_PRODUCT_NAMES,
    parse_boh_products,
    normalise_boh_time_slot,
)

BOH_COLLECT_URL = "https://book.bournemouthairport.com/book/BOH/Parking?parkingCmd=collectParkingDetails"


def _airport_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _debug_html_enabled() -> bool:
    return os.environ.get("AIRPORT_QUOTE_DEBUG_HTML", "").strip().lower() in {"1", "true", "yes", "on"}


def _has_required_named_products(products) -> bool:
    names = {product.name for product in products}
    return BOH_REQUIRED_PRODUCT_NAMES.issubset(names)


def _bounded_debug_snippet(page_html: str) -> str:
    needles = ("item__price__val", "item__options-price", "Car Park", "Premium")
    indexes = [page_html.find(needle) for needle in needles if page_html.find(needle) >= 0]
    if not indexes:
        return page_html[:6_000]
    anchor = min(indexes)
    start = max(anchor - 2_000, 0)
    end = min(start + 6_000, len(page_html))
    return page_html[start:end]


def _log_debug_html_if_needed(page_html: str, products) -> None:
    if not _debug_html_enabled() or _has_required_named_products(products):
        return
    snippet = _bounded_debug_snippet(page_html)
    print(
        "[AIRPORT_QUOTE_DEBUG_HTML] BOH product parse did not yield all required named products; "
        f"parsed={[product.to_api() for product in products]}; snippet={snippet!r}",
        flush=True,
    )


def fetch_bournemouth_airport_quote(
    quote_input: AirportQuoteInput,
    *,
    timeout_ms: int = 30_000,
) -> AirportQuoteScrapeResult:
    """Fetch a live BOH quote.

    This function owns the browser lifecycle and does not touch the database.
    Callers should perform DB reads/writes before/after this function, not
    during it, so Chromium work does not hold a request DB connection.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

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

            # BOH runs the search via a JS handler on the "Book now" submit button.
            # A raw form.submit() bypasses that handler, so results never load and we
            # time out on the price locator. Click the button so the site's own submit
            # handler fires (works for both navigation and AJAX-injected results).
            page.locator("input.btn--submit.btn-desktop").first.click()
            page.wait_for_load_state("domcontentloaded")
            try:
                page.locator(".item__price__val, .item__options-price").first.wait_for(
                    state="attached",
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:
                # Capture what BOH actually served so a future flow change is diagnosable
                # from logs instead of a blind timeout.
                print(
                    "[AIRPORT_QUOTE_SCRAPE_TIMEOUT] BOH price element never appeared; "
                    f"url={page.url}; snippet={_bounded_debug_snippet(page.content())!r}",
                    flush=True,
                )
                raise
            try:
                page.wait_for_function(
                    "() => /Car Park|Premium/i.test(document.body?.innerText || '')",
                    timeout=5_000,
                )
            except PlaywrightTimeoutError:
                pass

            page_html = page.content()
            products = parse_boh_products(page_html)
            _log_debug_html_if_needed(page_html, products)
            return AirportQuoteScrapeResult(products=products, source_url=page.url)
        finally:
            browser.close()
