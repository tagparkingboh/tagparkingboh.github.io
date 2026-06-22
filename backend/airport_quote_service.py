"""Bournemouth Airport quote pricing, parsing, fallback, and persistence."""

from __future__ import annotations

import html
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_FLOOR
from typing import Callable, Iterable, Optional

from sqlalchemy.orm import Session

from db_models import AirportQuoteSnapshot

logger = logging.getLogger(__name__)

AIRPORT_CODE = "BOH"
DEFAULT_DISCOUNT_PERCENT = Decimal("25")
DEFAULT_WEEK1_PRICE_PENCE = 10500
DEFAULT_AIRPORT_PRICE_FLOOR_PER_DAY_PENCE = 1000

BOH_TIME_OPTIONS = (
    ["00:01"]
    + [f"{minutes // 60:02d}:{minutes % 60:02d}" for minutes in range(30, 24 * 60, 30)]
    + ["23:59"]
)

BOH_DESTINATION_OTHER_ID = "2182"
BOH_DESTINATION_IDS = {
    ("agadir", "ryanair"): "2116",
    ("agadir", "jet2"): "2117",
    ("alicante", "jet2"): "2118",
    ("alicante", "ryanair"): "2119",
    ("antalya", "jet2"): "2120",
    ("antalya", "tui"): "2121",
    ("bergerac", None): "2122",
    ("carcassonne", None): "2123",
    ("corfu", "jet2"): "2125",
    ("corfu", "tui"): "2126",
    ("crete", "jet2"): "2127",
    ("heraklion", "jet2"): "2127",
    ("crete", "ryanair"): "2128",
    ("heraklion", "ryanair"): "2128",
    ("crete", "tui"): "2129",
    ("heraklion", "tui"): "2129",
    ("dalaman", "jet2"): "2130",
    ("dalaman", "tui"): "2131",
    ("dubrovnik", None): "2132",
    ("edinburgh", None): "2133",
    ("faro", "jet2"): "2134",
    ("faro", "ryanair"): "2135",
    ("fuerteventura", "jet2"): "2136",
    ("fuerteventura", "ryanair"): "2137",
    ("geneva", None): "2138",
    ("girona", None): "2139",
    ("gran canaria", "jet2"): "2140",
    ("gran canaria", "ryanair"): "2141",
    ("gran canaria", "tui"): "2142",
    ("ibiza", "jet2"): "2143",
    ("ibiza", "tui"): "2144",
    ("iceland", None): "2145",
    ("kefalonia", None): "2146",
    ("kefolonia", None): "2146",
    ("kos", None): "2147",
    ("krakow", None): "2148",
    ("lanzarote", "jet2"): "2149",
    ("lanzarote", "tui"): "2150",
    ("lanzarote", "ryanair"): "2151",
    ("lyon", None): "2153",
    ("madeira", None): "2154",
    ("majorca", "jet2"): "2155",
    ("mallorca", "jet2"): "2155",
    ("palma", "jet2"): "2155",
    ("majorca", "tui"): "2156",
    ("mallorca", "tui"): "2156",
    ("palma", "tui"): "2156",
    ("majorca", "ryanair"): "2157",
    ("mallorca", "ryanair"): "2157",
    ("palma", "ryanair"): "2157",
    ("malaga", "jet2"): "2158",
    ("málaga", "jet2"): "2158",
    ("malaga", "ryanair"): "2159",
    ("málaga", "ryanair"): "2159",
    ("malta", None): "2160",
    ("menorca", "jet2"): "2161",
    ("menorca", "tui"): "2162",
    ("murcia", None): "2163",
    ("nantes", None): "2164",
    ("paphos", None): "2166",
    ("prague", None): "2167",
    ("reus", None): "2168",
    ("rhodes", "jet2"): "2169",
    ("rhodes", "ryanair"): "2170",
    ("rhodes", "tui"): "2171",
    ("tenerife", "jet2"): "2172",
    ("tenerife", "ryanair"): "2173",
    ("tenerife", "tui"): "2174",
    ("venice", None): "2175",
    ("verona", None): "2176",
    ("vienna", None): "2177",
    ("wroclaw", None): "2178",
    ("zadar", None): "2179",
    ("zante", "jet2"): "2180",
    ("zakynthos", "jet2"): "2180",
    ("zante", "tui"): "2181",
    ("zakynthos", "tui"): "2181",
    ("larnaca", None): "2183",
    ("trapani", None): "2184",
    ("sicily", None): "2184",
}

# Conservative bootstrapping model used only when no snapshot exists yet.
# Live snapshots replace this through the fallback lookup path.
BOOTSTRAP_AIRPORT_LOWEST_BY_BILLING_DAY = {
    1: 5313,
    2: 8000,
    3: 9125,
    4: 10624,
    5: 11970,
    6: 13608,
    7: 14805,
    8: 15040,
    9: 16320,
    10: 17216,
    11: 18625,
    12: 20375,
    13: 21888,
    14: 21888,
}


@dataclass(frozen=True)
class AirportProduct:
    name: str
    price_pence: int
    price_text: str

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "pricePence": self.price_pence,
            "priceText": self.price_text,
        }


@dataclass(frozen=True)
class AirportQuoteInput:
    entry_date: date
    entry_time: time
    exit_date: date
    exit_time: time
    destination: Optional[str] = None


@dataclass(frozen=True)
class AirportQuoteScrapeResult:
    products: list[AirportProduct]
    source_url: Optional[str] = None


@dataclass(frozen=True)
class AirportQuoteLiveResult:
    products: list[AirportProduct]
    destination_id: str


def _parse_decimal_env(name: str, default: Decimal, min_value: Decimal, max_value: Decimal) -> Decimal:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default

    try:
        value = Decimal(raw)
    except Exception:
        logger.warning("%s=%r is invalid; using default %s", name, raw, default)
        return default

    if value < min_value or value > max_value:
        logger.warning("%s=%r outside %s-%s; using default %s", name, raw, min_value, max_value, default)
        return default

    return value


def get_airport_quote_discount_percent() -> Decimal:
    return _parse_decimal_env(
        "AIRPORT_QUOTE_DISCOUNT_PERCENT",
        DEFAULT_DISCOUNT_PERCENT,
        Decimal("0"),
        Decimal("60"),
    )


def get_airport_quote_week1_price_pence() -> int:
    raw = os.environ.get("AIRPORT_QUOTE_WEEK1_PRICE_PENCE")
    if not raw:
        logger.warning(
            "AIRPORT_QUOTE_WEEK1_PRICE_PENCE is unset; using default %s",
            DEFAULT_WEEK1_PRICE_PENCE,
        )
        return DEFAULT_WEEK1_PRICE_PENCE
    try:
        value = int(raw)
    except ValueError:
        logger.warning("AIRPORT_QUOTE_WEEK1_PRICE_PENCE=%r is invalid; using default %s", raw, DEFAULT_WEEK1_PRICE_PENCE)
        return DEFAULT_WEEK1_PRICE_PENCE
    return max(0, value)


def get_airport_price_floor_per_day_pence() -> int:
    raw = os.environ.get("AIRPORT_QUOTE_MIN_AIRPORT_PRICE_PER_DAY_PENCE")
    if not raw:
        return DEFAULT_AIRPORT_PRICE_FLOOR_PER_DAY_PENCE
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AIRPORT_QUOTE_MIN_AIRPORT_PRICE_PER_DAY_PENCE=%r is invalid; using default %s",
            raw,
            DEFAULT_AIRPORT_PRICE_FLOOR_PER_DAY_PENCE,
        )
        return DEFAULT_AIRPORT_PRICE_FLOOR_PER_DAY_PENCE
    return max(0, value)


def calculate_billing_days(entry_dt: datetime, exit_dt: datetime) -> int:
    elapsed_seconds = (exit_dt - entry_dt).total_seconds()
    if elapsed_seconds <= 0:
        raise ValueError("exit must be after entry")
    return max(1, math.ceil(elapsed_seconds / (24 * 60 * 60)))


def _time_to_minutes(value: str) -> int:
    hour, minute = [int(part) for part in value.split(":")[:2]]
    return hour * 60 + minute


def normalise_boh_time_slot(value: time | str) -> str:
    if isinstance(value, time):
        requested = value.hour * 60 + value.minute
    else:
        requested = _time_to_minutes(value)

    best = BOH_TIME_OPTIONS[0]
    best_delta = abs(requested - _time_to_minutes(best))
    for option in BOH_TIME_OPTIONS[1:]:
        option_minutes = _time_to_minutes(option)
        delta = abs(requested - option_minutes)
        if delta < best_delta or (delta == best_delta and option_minutes > _time_to_minutes(best)):
            best = option
            best_delta = delta
    return best


def calculate_tag_price_pence(cheapest_pence: int, discount_pct: Decimal) -> int:
    multiplier = Decimal("1") - (discount_pct / Decimal("100"))
    return int((Decimal(cheapest_pence) * multiplier).to_integral_value(rounding=ROUND_FLOOR))


def format_price_text(price_pence: int) -> str:
    return f"£{price_pence / 100:.2f}"


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_money_to_pence(value: str) -> Optional[int]:
    match = re.search(r"£?\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", value)
    if not match:
        return None
    return int((Decimal(match.group(1).replace(",", "")) * 100).to_integral_value(rounding=ROUND_FLOOR))


def _parse_product_groups(page_html: str) -> list[AirportProduct]:
    chunks = re.split(r'<[^>]*class="[^"]*product-group__item-container[^"]*"[^>]*>', page_html)
    products: list[AirportProduct] = []
    for index, chunk in enumerate(chunks[1:]):
        chunk = chunk.split('class="product-group__item-container"', 1)[0]
        price_match = re.search(r'<[^>]*class="[^"]*item__options-price[^"]*"[^>]*>(.*?)</[^>]+>', chunk, re.S)
        if not price_match:
            continue
        price_text = _strip_tags(price_match.group(1))
        price_pence = parse_money_to_pence(price_text)
        if price_pence is None:
            continue

        options_text_match = re.search(r'<[^>]*class="[^"]*item__options[^"]*"[^>]*>(.*?)</div>', chunk, re.S)
        options_text = _strip_tags(options_text_match.group(1)) if options_text_match else _strip_tags(chunk)
        name_match = re.search(r"Options\s+(.+?)\s+£", options_text)
        name = name_match.group(1).strip() if name_match else f"Bournemouth Airport product {index + 1}"
        name = re.sub(r"\s+Flex$", "", name).strip()
        products.append(AirportProduct(name=name, price_pence=price_pence, price_text=format_price_text(price_pence)))
    return products


def parse_boh_products(page_html: str) -> list[AirportProduct]:
    grouped = _parse_product_groups(page_html)
    if grouped:
        return grouped

    products: list[AirportProduct] = []
    for index, match in enumerate(
        re.finditer(r'<[^>]*class="[^"]*item__price__val[^"]*"[^>]*>(.*?)</[^>]+>', page_html, re.S)
    ):
        price_text = _strip_tags(match.group(1))
        price_pence = parse_money_to_pence(price_text)
        if price_pence is None:
            continue
        products.append(
            AirportProduct(
                name=f"Bournemouth Airport product {index + 1}",
                price_pence=price_pence,
                price_text=format_price_text(price_pence),
            )
        )
    return products


def detect_airline(value: Optional[str]) -> Optional[str]:
    raw = (value or "").lower()
    if "tui" in raw or "tom" in raw or re.search(r"\bby\b", raw):
        return "tui"
    if "jet2" in raw or re.search(r"\bls\b", raw):
        return "jet2"
    if "ryanair" in raw or re.search(r"\bfr\b", raw):
        return "ryanair"
    if "easyjet" in raw or re.search(r"\bu2\b", raw):
        return "easyjet"
    return None


def map_destination_to_boh_id(destination: Optional[str], airline_hint: Optional[str] = None) -> str:
    raw_destination = (destination or "").lower()
    airline = detect_airline(f"{destination or ''} {airline_hint or ''}")
    for (needle, required_airline), destination_id in BOH_DESTINATION_IDS.items():
        if needle in raw_destination and (required_airline is None or required_airline == airline):
            return destination_id
    for (needle, required_airline), destination_id in BOH_DESTINATION_IDS.items():
        if needle in raw_destination and required_airline is None:
            return destination_id
    return BOH_DESTINATION_OTHER_ID


def validate_products(products: Iterable[AirportProduct], billing_days: int) -> tuple[bool, Optional[str]]:
    products = list(products)
    if len(products) < 3:
        return False, "products_missing"
    known = {"Car Park 1", "Car Park 2", "Car Park 3", "Car Park 1 Premium"}
    names = {product.name for product in products}
    if not {"Car Park 1", "Car Park 2", "Car Park 3"}.issubset(names):
        return False, "products_misnamed"
    cheapest = min(product.price_pence for product in products)
    if cheapest <= 0:
        return False, "price_zero"
    if cheapest < billing_days * get_airport_price_floor_per_day_pence():
        return False, "price_below_floor"
    if not names.issubset(known):
        return False, "unexpected_product_name"
    return True, None


def bootstrap_model_airport_price_pence(billing_days: int) -> int:
    if billing_days in BOOTSTRAP_AIRPORT_LOWEST_BY_BILLING_DAY:
        return BOOTSTRAP_AIRPORT_LOWEST_BY_BILLING_DAY[billing_days]
    if billing_days < 1:
        return BOOTSTRAP_AIRPORT_LOWEST_BY_BILLING_DAY[1]
    day_14 = BOOTSTRAP_AIRPORT_LOWEST_BY_BILLING_DAY[14]
    return day_14 + ((billing_days - 14) * 1250)


def fallback_quote_from_snapshots(
    db: Session,
    billing_days: int,
    discount_pct: Decimal,
) -> tuple[list[AirportProduct], int, str]:
    snapshot = (
        db.query(AirportQuoteSnapshot)
        .filter(
            AirportQuoteSnapshot.airport == AIRPORT_CODE,
            AirportQuoteSnapshot.billing_days == billing_days,
            AirportQuoteSnapshot.status == "ok",
            AirportQuoteSnapshot.source.in_(("live", "batch")),
            AirportQuoteSnapshot.cheapest_pence.isnot(None),
        )
        .order_by(AirportQuoteSnapshot.created_at.desc())
        .first()
    )
    if snapshot and snapshot.cheapest_pence:
        raw_products = snapshot.products_json or []
        products = [
            AirportProduct(
                name=item.get("name", "Bournemouth Airport"),
                price_pence=int(item.get("pricePence") or item.get("price_pence") or 0),
                price_text=item.get("priceText") or format_price_text(int(item.get("pricePence") or item.get("price_pence") or 0)),
            )
            for item in raw_products
            if int(item.get("pricePence") or item.get("price_pence") or 0) > 0
        ]
        return products, calculate_tag_price_pence(snapshot.cheapest_pence, discount_pct), "model"

    airport_price = bootstrap_model_airport_price_pence(billing_days)
    products = [AirportProduct("Bournemouth Airport model", airport_price, format_price_text(airport_price))]
    return products, calculate_tag_price_pence(airport_price, discount_pct), "model"


def record_quote_snapshot(
    db: Session,
    quote_input: AirportQuoteInput,
    *,
    destination_id: str,
    billing_days: int,
    products: list[AirportProduct],
    cheapest_pence: Optional[int],
    tag_price_pence: Optional[int],
    discount_pct: Decimal,
    source: str,
    status: str,
    reject_reason: Optional[str] = None,
) -> AirportQuoteSnapshot:
    snapshot = AirportQuoteSnapshot(
        airport=AIRPORT_CODE,
        entry_date=quote_input.entry_date,
        entry_time=quote_input.entry_time,
        exit_date=quote_input.exit_date,
        exit_time=quote_input.exit_time,
        destination_id=destination_id,
        billing_days=billing_days,
        products_json=[product.to_api() for product in products],
        cheapest_pence=cheapest_pence,
        tag_price_pence=tag_price_pence,
        discount_pct_used=discount_pct,
        source=source,
        status=status,
        reject_reason=reject_reason,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


Scraper = Callable[[AirportQuoteInput, str], AirportQuoteScrapeResult]


def fetch_live_airport_quote_without_db(
    quote_input: AirportQuoteInput,
    scraper: Scraper,
) -> AirportQuoteLiveResult:
    destination_id = map_destination_to_boh_id(quote_input.destination)
    scrape = scraper(quote_input, destination_id)
    return AirportQuoteLiveResult(
        products=scrape.products,
        destination_id=destination_id,
    )


def build_airport_quote_response(
    *,
    products: list[AirportProduct],
    tag_price_pence: int,
    billing_days: int,
    source: str,
    quoted_at: datetime,
    quote_snapshot_id: Optional[int] = None,
) -> dict:
    week1_price_pence = get_airport_quote_week1_price_pence()
    return {
        "quoteId": quote_snapshot_id,
        "tagPrice": tag_price_pence / 100,
        "tagPricePence": tag_price_pence,
        "pricingInfo": {
            "airport_quote_snapshot_id": quote_snapshot_id,
            "price": tag_price_pence / 100,
            "price_pence": tag_price_pence,
            "duration_days": billing_days,
            "week1_price": week1_price_pence / 100,
            "week1_price_pence": week1_price_pence,
        },
        "airportPrices": [product.to_api() for product in products],
        "billing_days": billing_days,
        "source": source,
        "quotedAt": quoted_at.isoformat(),
    }


def build_airport_parking_quote_from_live_or_model(
    db: Session,
    quote_input: AirportQuoteInput,
    *,
    live_quote: Optional[AirportQuoteLiveResult],
    live_error: Optional[str] = None,
    quoted_at_factory: Callable[[], datetime],
) -> dict:
    entry_dt = datetime.combine(quote_input.entry_date, quote_input.entry_time)
    exit_dt = datetime.combine(quote_input.exit_date, quote_input.exit_time)
    billing_days = calculate_billing_days(entry_dt, exit_dt)
    discount_pct = get_airport_quote_discount_percent()
    destination_id = live_quote.destination_id if live_quote else map_destination_to_boh_id(quote_input.destination)

    if live_quote is None and not live_error:
        products, tag_price_pence, source = fallback_quote_from_snapshots(db, billing_days, discount_pct)
        snapshot = record_quote_snapshot(
            db,
            quote_input,
            destination_id=destination_id,
            billing_days=billing_days,
            products=products,
            cheapest_pence=min((product.price_pence for product in products), default=None),
            tag_price_pence=tag_price_pence,
            discount_pct=discount_pct,
            source="model",
            status="ok",
        )
        return build_airport_quote_response(
            products=products,
            tag_price_pence=tag_price_pence,
            billing_days=billing_days,
            source=source,
            quoted_at=quoted_at_factory(),
            quote_snapshot_id=snapshot.id,
        )

    snapshot: Optional[AirportQuoteSnapshot] = None
    if live_quote is not None:
        products = live_quote.products
        valid, reject_reason = validate_products(products, billing_days)
        if not valid:
            cheapest = min((product.price_pence for product in products), default=None)
            record_quote_snapshot(
                db,
                quote_input,
                destination_id=destination_id,
                billing_days=billing_days,
                products=products,
                cheapest_pence=cheapest,
                tag_price_pence=None,
                discount_pct=discount_pct,
                source="live",
                status="rejected",
                reject_reason=reject_reason,
            )
            products, tag_price_pence, source = fallback_quote_from_snapshots(db, billing_days, discount_pct)
            snapshot = record_quote_snapshot(
                db,
                quote_input,
                destination_id=destination_id,
                billing_days=billing_days,
                products=products,
                cheapest_pence=min((product.price_pence for product in products), default=None),
                tag_price_pence=tag_price_pence,
                discount_pct=discount_pct,
                source="model",
                status="ok",
            )
        else:
            cheapest = min(product.price_pence for product in products)
            tag_price_pence = calculate_tag_price_pence(cheapest, discount_pct)
            snapshot = record_quote_snapshot(
                db,
                quote_input,
                destination_id=destination_id,
                billing_days=billing_days,
                products=products,
                cheapest_pence=cheapest,
                tag_price_pence=tag_price_pence,
                discount_pct=discount_pct,
                source="live",
                status="ok",
            )
            source = "live"
    else:
        logger.warning("BOH live quote failed; using model fallback: %s", live_error)
        record_quote_snapshot(
            db,
            quote_input,
            destination_id=destination_id,
            billing_days=billing_days,
            products=[],
            cheapest_pence=None,
            tag_price_pence=None,
            discount_pct=discount_pct,
            source="live",
            status="error",
            reject_reason=(live_error or "live_quote_unavailable")[:500],
        )
        products, tag_price_pence, source = fallback_quote_from_snapshots(db, billing_days, discount_pct)
        snapshot = record_quote_snapshot(
            db,
            quote_input,
            destination_id=destination_id,
            billing_days=billing_days,
            products=products,
            cheapest_pence=min((product.price_pence for product in products), default=None),
            tag_price_pence=tag_price_pence,
            discount_pct=discount_pct,
            source="model",
            status="ok",
        )

    return build_airport_quote_response(
        products=products,
        tag_price_pence=tag_price_pence,
        billing_days=billing_days,
        source=source,
        quoted_at=quoted_at_factory(),
        quote_snapshot_id=snapshot.id if snapshot else None,
    )


def get_airport_parking_quote(
    db: Session,
    quote_input: AirportQuoteInput,
    *,
    scraper: Optional[Scraper],
    quoted_at_factory: Callable[[], datetime],
) -> dict:
    live_quote = None
    live_error = None
    if scraper is not None:
        try:
            live_quote = fetch_live_airport_quote_without_db(quote_input, scraper)
        except Exception as exc:
            live_error = str(exc)

    return build_airport_parking_quote_from_live_or_model(
        db,
        quote_input,
        live_quote=live_quote,
        live_error=live_error,
        quoted_at_factory=quoted_at_factory,
    )
