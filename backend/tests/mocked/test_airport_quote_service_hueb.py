from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from airport_quote_service import (
    AirportProduct,
    AirportQuoteInput,
    AirportQuoteScrapeResult,
    calculate_billing_days,
    calculate_tag_price_pence,
    get_airport_quote_discount_decision,
    get_airport_quote_discount_percent,
    get_airport_quote_week1_price_pence,
    mark_airport_quote_converted,
    normalise_boh_time_slot,
    parse_boh_products,
    fallback_quote_from_snapshots,
    validate_products,
)
from airport_quote_worker_client import build_worker_scraper
from main import app
from main import resolve_airport_quote_amount_pence


class _Query:
    def __init__(self, row=None):
        self.row = row
        self.filter_args = []

    def filter(self, *args, **kwargs):
        self.filter_args.extend(args)
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if getattr(self.row, "source", None) == "model":
            filter_text = " ".join(str(arg) for arg in self.filter_args)
            if "airport_quote_snapshots.source IN" in filter_text:
                return None
        return self.row


def _mock_db(fallback_snapshot=None):
    db = MagicMock()
    db.query.return_value = _Query(fallback_snapshot)

    def _refresh(row):
        if getattr(row, "id", None) is None:
            row.id = len(db.add.call_args_list)

    db.refresh.side_effect = _refresh
    return db


def _override_quote_db(monkeypatch, db):
    monkeypatch.setattr("main.get_airport_quote_session_factory", lambda: lambda: db)


def test_billing_days_ceil_whole_day_boundaries():
    assert calculate_billing_days(
        datetime(2026, 7, 1, 6, 0),
        datetime(2026, 7, 2, 6, 0),
    ) == 1
    assert calculate_billing_days(
        datetime(2026, 7, 1, 6, 0),
        datetime(2026, 7, 2, 6, 1),
    ) == 2
    assert calculate_billing_days(
        datetime(2026, 7, 1, 6, 0),
        datetime(2026, 7, 1, 12, 0),
    ) == 1
    with pytest.raises(ValueError):
        calculate_billing_days(
            datetime(2026, 7, 1, 6, 0),
            datetime(2026, 7, 1, 6, 0),
        )


def test_boh_time_slot_rounds_to_nearest_with_ties_up():
    assert normalise_boh_time_slot("00:00") == "00:01"
    assert normalise_boh_time_slot("04:20") == "04:30"
    assert normalise_boh_time_slot("04:15") == "04:30"
    assert normalise_boh_time_slot("23:50") == "23:59"
    assert normalise_boh_time_slot(time(14, 44)) == "14:30"


def test_discount_env_valid_and_invalid(monkeypatch, caplog):
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "22.5")
    assert get_airport_quote_discount_percent() == pytest.approx(22.5)
    assert calculate_tag_price_pence(10000, get_airport_quote_discount_percent()) == 7750

    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "bad")
    assert get_airport_quote_discount_percent() == 25
    assert "AIRPORT_QUOTE_DISCOUNT_PERCENT" in caplog.text

    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "99")
    assert get_airport_quote_discount_percent() == 25


def test_matrix_discount_boundaries_at_lead_7_8_and_duration_7_8(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    monkeypatch.setenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", "7")
    monkeypatch.setenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", "7")
    shown_at = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

    cases = [
        (7, 7, "near-short", 25),
        (7, 8, "near-long", 20),
        (8, 7, "far-short", 12),
        (8, 8, "far-long", 10),
    ]

    for lead_days, billing_days, band, pct in cases:
        decision = get_airport_quote_discount_decision(
            shown_at.date() + timedelta(days=lead_days),
            billing_days,
            shown_at=shown_at,
        )
        assert decision.lead_days == lead_days
        assert decision.discount_band == band
        assert decision.discount_pct == pct


def test_matrix_discount_accepts_decimal_percent(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12.5,10")
    monkeypatch.setenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", "7")
    monkeypatch.setenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", "7")
    shown_at = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

    decision = get_airport_quote_discount_decision(
        shown_at.date() + timedelta(days=8),
        7,
        shown_at=shown_at,
    )

    assert decision.discount_band == "far-short"
    assert decision.discount_pct == Decimal("12.5")
    assert calculate_tag_price_pence(10000, decision.discount_pct) == 8750


def test_matrix_parse_failure_falls_back_to_flat_percent_with_log(monkeypatch, caplog):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,bad,10")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "22")

    decision = get_airport_quote_discount_decision(
        date(2026, 7, 1),
        7,
        shown_at=datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
    )

    assert decision.discount_pct == 22
    assert decision.discount_band == "flat-fallback"
    assert "AIRPORT_QUOTE_DISCOUNT_MATRIX" in caplog.text


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", "bad"),
        ("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", "0"),
    ],
)
def test_matrix_boundary_parse_failure_falls_back_to_flat_percent_with_log(
    monkeypatch,
    caplog,
    env_name,
    env_value,
):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "22")
    monkeypatch.setenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", "7")
    monkeypatch.setenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", "7")
    monkeypatch.setenv(env_name, env_value)

    decision = get_airport_quote_discount_decision(
        date(2026, 7, 2),
        7,
        shown_at=datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
    )

    assert decision.discount_pct == 22
    assert decision.discount_band == "flat-fallback"
    assert env_name in caplog.text
    assert "AIRPORT_QUOTE_DISCOUNT_PERCENT" in caplog.text


def test_min_price_floor_applies_after_discount():
    assert calculate_tag_price_pence(5313, 25, 6500) == 6500


def test_conversion_update_logs_when_no_row_matches(caplog):
    db = MagicMock()
    db.execute.return_value.rowcount = 0

    mark_airport_quote_converted(db, 555)

    assert "matched 0 rows" in caplog.text
    db.commit.assert_called_once()


def test_week1_env_unset_uses_default_with_warning(monkeypatch, caplog):
    monkeypatch.delenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", raising=False)

    assert get_airport_quote_week1_price_pence() == 10500
    assert "AIRPORT_QUOTE_WEEK1_PRICE_PENCE is unset" in caplog.text


def test_parse_boh_product_groups_excludes_flex_prices():
    html = """
      <div class="product-group__item-container">
        <div class="item__options">
          Back Options Car Park 3 <span class="item__options-price 7">£148.05</span>
          Car Park 3 Flex <span class="item__options-price 8">£153.05</span>
        </div>
      </div>
      <div class="product-group__item-container">
        <div class="item__options">
          Back Options Car Park 2 <span class="item__options-price 5">£149.94</span>
          Car Park 2 Flex <span class="item__options-price 6">£154.94</span>
        </div>
      </div>
      <div class="product-group__item-container">
        <div class="item__options">
          Back Options Car Park 1 <span class="item__options-price 1">£169.20</span>
          Car Park 1 Flex <span class="item__options-price 2">£174.20</span>
        </div>
      </div>
      <div class="product-group__item-container">
        <div class="item__options">
          Back Options Car Park 1 Premium <span class="item__options-price 3">£255.00</span>
          Car Park 1 Premium Flex <span class="item__options-price 4">£260.00</span>
        </div>
      </div>
    """
    products = parse_boh_products(html)

    assert [(p.name, p.price_pence) for p in products] == [
        ("Car Park 3", 14805),
        ("Car Park 2", 14994),
        ("Car Park 1", 16920),
        ("Car Park 1 Premium", 25500),
    ]


def test_parse_boh_flat_price_classes_maps_names_and_excludes_flex_prices():
    html = """
      <section class="parking-products">
        <span class="item__price__val 7">£148.05</span>
        <span class="item__price__val 8">£153.05</span>
        <span class="item__price__val 5">£149.94</span>
        <span class="item__price__val 6">£154.94</span>
        <span class="item__price__val 1">£169.20</span>
        <span class="item__price__val 2">£174.20</span>
        <span class="item__price__val 3">£255.00</span>
        <span class="item__price__val 4">£260.00</span>
      </section>
    """
    products = parse_boh_products(html)

    assert [(p.name, p.price_pence) for p in products] == [
        ("Car Park 3", 14805),
        ("Car Park 2", 14994),
        ("Car Park 1", 16920),
        ("Car Park 1 Premium", 25500),
    ]


def test_parse_boh_products_uses_flat_class_names_when_grouped_parse_is_incomplete():
    html = """
      <div class="product-group__item-container">
        <div class="item__options">
          <span class="item__options-price">£168.13</span>
        </div>
      </div>
      <section class="parking-products">
        <span class="item__price__val 7">£168.13</span>
        <span class="item__price__val 5">£171.36</span>
        <span class="item__price__val 1">£195.60</span>
        <span class="item__price__val 3">£300.00</span>
      </section>
    """
    products = parse_boh_products(html)

    assert [(p.name, p.price_pence) for p in products] == [
        ("Car Park 3", 16813),
        ("Car Park 2", 17136),
        ("Car Park 1", 19560),
        ("Car Park 1 Premium", 30000),
    ]


def test_parse_boh_flat_products_drops_generic_duplicate_price_nodes():
    html = """
      <section class="parking-products">
        <span class="item__price__val">£175.00</span>
        <span class="item__price__val 5">£175.00</span>
        <span class="item__price__val">£177.66</span>
        <span class="item__price__val 7">£177.66</span>
        <span class="item__price__val">£205.20</span>
        <span class="item__price__val 1">£205.20</span>
        <span class="item__price__val 3">£312.50</span>
      </section>
    """
    products = parse_boh_products(html)

    assert [(p.name, p.price_pence) for p in products] == [
        ("Car Park 2", 17500),
        ("Car Park 3", 17766),
        ("Car Park 1", 20520),
        ("Car Park 1 Premium", 31250),
    ]


def test_parse_boh_flat_products_accepts_three_standard_products_without_premium():
    html = """
      <section class="parking-products">
        <span class="item__price__val 7">£168.13</span>
        <span class="item__price__val 5">£171.36</span>
        <span class="item__price__val 1">£195.60</span>
      </section>
    """
    products = parse_boh_products(html)

    assert [(p.name, p.price_pence) for p in products] == [
        ("Car Park 3", 16813),
        ("Car Park 2", 17136),
        ("Car Park 1", 19560),
    ]


def test_validate_products_accepts_four_named_products():
    ok, reason = validate_products(
        [
            AirportProduct("Car Park 3", 14805, "£148.05"),
            AirportProduct("Car Park 2", 14994, "£149.94"),
            AirportProduct("Car Park 1", 16920, "£169.20"),
            AirportProduct("Car Park 1 Premium", 25500, "£255.00"),
        ],
        billing_days=8,
    )

    assert ok is True
    assert reason is None


def test_validate_products_accepts_three_standard_products_without_premium():
    ok, reason = validate_products(
        [
            AirportProduct("Car Park 3", 14805, "£148.05"),
            AirportProduct("Car Park 2", 14994, "£149.94"),
            AirportProduct("Car Park 1", 16920, "£169.20"),
        ],
        billing_days=8,
    )

    assert ok is True
    assert reason is None


def test_validate_products_rejects_two_products_as_missing():
    ok, reason = validate_products(
        [
            AirportProduct("Car Park 3", 14805, "£148.05"),
            AirportProduct("Car Park 2", 14994, "£149.94"),
        ],
        billing_days=8,
    )

    assert ok is False
    assert reason == "products_missing"


def test_validate_products_rejects_missing_standard_even_with_premium():
    ok, reason = validate_products(
        [
            AirportProduct("Car Park 2", 14994, "£149.94"),
            AirportProduct("Car Park 1", 16920, "£169.20"),
            AirportProduct("Car Park 1 Premium", 25500, "£255.00"),
        ],
        billing_days=8,
    )

    assert ok is False
    assert reason == "products_misnamed"


def test_validate_products_rejects_generic_product_names():
    ok, reason = validate_products(
        [
            AirportProduct("Bournemouth Airport product 1", 14805, "£148.05"),
            AirportProduct("Bournemouth Airport product 2", 14994, "£149.94"),
            AirportProduct("Bournemouth Airport product 3", 16920, "£169.20"),
        ],
        billing_days=8,
    )

    assert ok is False
    assert reason == "products_misnamed"


def test_quote_endpoint_live_success_records_snapshot(monkeypatch):
    db = _mock_db()
    events = []
    _override_quote_db(monkeypatch, db)

    def scraper(quote_input: AirportQuoteInput):
        events.append(("scrape", db.query.called))
        assert quote_input.entry_date == date(2026, 7, 6)
        return AirportQuoteScrapeResult(
            products=[
                AirportProduct("Car Park 3", 14805, "£148.05"),
                AirportProduct("Car Park 2", 14994, "£149.94"),
                AirportProduct("Car Park 1", 16920, "£169.20"),
                AirportProduct("Car Park 1 Premium", 25500, "£255.00"),
            ]
        )

    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: scraper)
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")

    try:
        response = TestClient(app).post(
            "/api/airport-parking/quote",
            json={
                "entryDate": "2026-07-06",
                "entryTime": "06:00",
                "exitDate": "2026-07-13",
                "exitTime": "22:00",
                "destination": "Zakynthos International Airport TUI",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert events == [("scrape", False)]
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "live"
    assert body["quoteId"] == 1
    assert body["pricingInfo"]["airport_quote_snapshot_id"] == 1
    assert body["tagPricePence"] == 11103
    assert body["pricingInfo"]["price"] == 111.03
    assert body["pricingInfo"]["discount_pct_used"] == 25.0
    assert body["billing_days"] == 8
    assert [p["name"] for p in body["airportPrices"]] == [
        "Car Park 3",
        "Car Park 2",
        "Car Park 1",
        "Car Park 1 Premium",
    ]
    assert db.add.called
    snapshot = db.add.call_args.args[0]
    assert snapshot.status == "ok"
    assert snapshot.destination_id == "2182"
    assert snapshot.cheapest_pence == 14805
    assert snapshot.tag_price_pence == 11103


def test_quote_endpoint_matrix_records_conversion_log_with_snapshot_id(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)

    def scraper(_quote_input: AirportQuoteInput):
        return AirportQuoteScrapeResult(
            products=[
                AirportProduct("Car Park 3", 10000, "£100.00"),
                AirportProduct("Car Park 2", 12000, "£120.00"),
                AirportProduct("Car Park 1", 14000, "£140.00"),
                AirportProduct("Car Park 1 Premium", 18000, "£180.00"),
            ]
        )

    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: scraper)
    monkeypatch.setattr("main.get_uk_now", lambda: datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    monkeypatch.setenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", "7")
    monkeypatch.setenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", "7")

    try:
        response = TestClient(app).post(
            "/api/airport-parking/quote",
            json={
                "entryDate": "2026-07-01",
                "entryTime": "06:00",
                "exitDate": "2026-07-09",
                "exitTime": "06:00",
                "destination": "Other",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["quoteId"] == 1
    assert body["billing_days"] == 8
    assert body["pricingInfo"]["discount_pct_used"] == 20.0
    assert body["tagPricePence"] == 8000

    assert db.execute.called
    assert "DO NOTHING" in str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert params["airport_quote_snapshot_id"] == 1
    assert params["lead_days"] == 7
    assert params["billing_days"] == 8
    assert params["discount_band"] == "near-long"
    assert params["tag_pence"] == 8000
    assert params["cheapest_boh_pence"] == 10000
    assert params["shown_at"].tzinfo is not None


def test_quote_endpoint_scraper_failure_uses_snapshot_model(monkeypatch):
    fallback = SimpleNamespace(
        products_json=[
            {"name": "Car Park 3", "pricePence": 12000, "priceText": "£120.00"},
            {"name": "Car Park 2", "pricePence": 12100, "priceText": "£121.00"},
        ],
        cheapest_pence=12000,
    )
    db = _mock_db(fallback)
    _override_quote_db(monkeypatch, db)

    def scraper(_quote_input: AirportQuoteInput):
        raise RuntimeError("blocked")

    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: scraper)

    try:
        response = TestClient(app).post(
            "/api/airport-parking/quote",
            json={
                "entryDate": "2026-07-06",
                "entryTime": "06:00",
                "exitDate": "2026-07-13",
                "exitTime": "06:00",
                "destination": "Other",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "model"
    assert body["quoteId"] == 2
    assert body["tagPricePence"] == 9000
    assert body["airportPrices"][0]["pricePence"] == 12000
    statuses = [call.args[0].status for call in db.add.call_args_list]
    assert "error" in statuses
    assert statuses[-1] == "ok"
    assert db.add.call_args_list[-1].args[0].source == "model"


def test_quote_endpoint_rejects_bad_live_structure_and_falls_back(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)

    def scraper(_quote_input: AirportQuoteInput):
        return AirportQuoteScrapeResult(
            products=[AirportProduct("Unknown", 100, "£1.00")]
        )

    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: scraper)

    try:
        response = TestClient(app).post(
            "/api/airport-parking/quote",
            json={
                "entryDate": "2026-07-06",
                "entryTime": "06:00",
                "exitDate": "2026-07-13",
                "exitTime": "06:00",
                "destination": "Other",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "model"
    assert body["quoteId"] == 2
    assert body["tagPricePence"] > 0
    snapshot = db.add.call_args_list[0].args[0]
    assert snapshot.status == "rejected"
    assert snapshot.reject_reason == "products_missing"
    assert db.add.call_args_list[-1].args[0].source == "model"


def test_quote_endpoint_without_worker_returns_model_price(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: None)

    response = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-07-06",
            "entryTime": "06:00",
            "exitDate": "2026-07-13",
            "exitTime": "06:00",
            "destination": "Other",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "model"
    assert body["tagPricePence"] > 0
    assert db.add.call_args.args[0].source == "model"


def test_model_rows_do_not_feed_future_model_derivation():
    model_echo = SimpleNamespace(
        products_json=[
            {"name": "Echoed model", "pricePence": 99999, "priceText": "£999.99"},
        ],
        cheapest_pence=99999,
        source="model",
    )
    db = _mock_db(model_echo)

    products, tag_price_pence, source = fallback_quote_from_snapshots(
        db,
        billing_days=7,
        discount_pct=25,
    )

    assert source == "model"
    assert products[0].name == "Bournemouth Airport model"
    assert products[0].price_pence == 14805
    assert tag_price_pence == 11103


def test_worker_client_maps_worker_payload(monkeypatch):
    calls = []

    class _Response:
        def raise_for_status(self):
            calls.append("raise_for_status")

        def json(self):
            return {
                "products": [
                    {"name": "Car Park 3", "pricePence": 14805, "priceText": "£148.05"},
                    {"name": "Car Park 2", "pricePence": 14994, "priceText": "£149.94"},
                ],
                "sourceUrl": "https://book.bournemouthairport.com/result",
            }

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return _Response()

    monkeypatch.setattr("airport_quote_worker_client.httpx.post", fake_post)
    monkeypatch.setenv("AIRPORT_QUOTE_WORKER_TIMEOUT_SECONDS", "3.5")

    scraper = build_worker_scraper("https://worker.example")
    result = scraper(
        AirportQuoteInput(
            entry_date=date(2026, 7, 6),
            entry_time=time(6, 0),
            exit_date=date(2026, 7, 13),
            exit_time=time(6, 0),
        ),
    )

    assert calls[0] == (
        "https://worker.example/internal/airport-parking/scrape",
        {
            "entryDate": "2026-07-06",
            "entryTime": "06:00",
            "exitDate": "2026-07-13",
            "exitTime": "06:00",
        },
        3.5,
    )
    assert calls[1] == "raise_for_status"
    assert [product.name for product in result.products] == ["Car Park 3", "Car Park 2"]
    assert result.source_url == "https://book.bournemouthairport.com/result"


def test_payment_amount_resolver_uses_persisted_quote_and_rejects_mismatch():
    snapshot = SimpleNamespace(
        id=12,
        status="ok",
        tag_price_pence=11103,
        entry_date=date(2026, 7, 6),
        entry_time=time(6, 0),
        exit_date=date(2026, 7, 13),
        exit_time=time(6, 30),
    )
    db = _mock_db(snapshot)

    assert resolve_airport_quote_amount_pence(
        db,
        12,
        dropoff_date=date(2026, 7, 6),
        entry_time=time(6, 0),
        exit_date=date(2026, 7, 13),
        exit_time=time(6, 30),
    ) == 11103

    with pytest.raises(Exception):
        resolve_airport_quote_amount_pence(
            db,
            12,
            dropoff_date=date(2026, 7, 6),
            entry_time=time(6, 15),
            exit_date=date(2026, 7, 13),
            exit_time=time(6, 30),
        )


# ---------------------------------------------------------------------------
# §18 QA brief — HTTP-boundary-mocked integration (mock ONLY the worker's
# httpx response via AIRPORT_QUOTE_WORKER_URL, never the service internals).
# ---------------------------------------------------------------------------

_STANDARD_BOH_PRODUCTS = [
    {"name": "Car Park 3", "pricePence": 14805, "priceText": "£148.05"},
    {"name": "Car Park 2", "pricePence": 14994, "priceText": "£149.94"},
    {"name": "Car Park 1", "pricePence": 16920, "priceText": "£169.20"},
    {"name": "Car Park 1 Premium", "pricePence": 25500, "priceText": "£255.00"},
]


def _mock_worker_http(monkeypatch, *, products=None, raise_exc=None, http_status=None):
    """Mock the worker HTTP boundary only: set the worker URL and patch httpx.post
    so the real worker-client -> service path runs (§18)."""
    monkeypatch.setenv("AIRPORT_QUOTE_WORKER_URL", "https://worker.test")

    class _Resp:
        def raise_for_status(self):
            if http_status and http_status >= 400:
                req = httpx.Request("POST", "https://worker.test")
                raise httpx.HTTPStatusError(
                    str(http_status), request=req, response=httpx.Response(http_status, request=req)
                )

        def json(self):
            return {
                "products": _STANDARD_BOH_PRODUCTS if products is None else products,
                "sourceUrl": "https://book.bournemouthairport.com/result",
            }

    def fake_post(url, json, timeout):
        if raise_exc is not None:
            raise raise_exc
        return _Resp()

    monkeypatch.setattr("airport_quote_worker_client.httpx.post", fake_post)


def _post_quote(overrides=None):
    body = {
        "entryDate": "2026-07-06", "entryTime": "06:00",
        "exitDate": "2026-07-13", "exitTime": "06:00",
        "destination": "Other",
    }
    if overrides:
        body.update(overrides)
    return TestClient(app).post("/api/airport-parking/quote", json=body)


def test_http_boundary_live_success_exercises_worker_client(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    _mock_worker_http(monkeypatch)
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")

    body = _post_quote().json()

    assert body["source"] == "live"
    assert body["tagPricePence"] == 11103  # floor(14805 * 0.75)
    assert [p["name"] for p in body["airportPrices"]] == [
        "Car Park 3", "Car Park 2", "Car Park 1", "Car Park 1 Premium",
    ]
    last = db.add.call_args_list[-1].args[0]
    assert (last.source, last.status) == ("live", "ok")
    assert last.cheapest_pence == 14805


def test_http_boundary_worker_timeout_serves_model(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    _mock_worker_http(monkeypatch, raise_exc=httpx.TimeoutException("slow"))

    body = _post_quote().json()

    assert body["source"] == "model"
    assert body["tagPricePence"] > 0
    statuses = [c.args[0].status for c in db.add.call_args_list]
    error_row = next(c.args[0] for c in db.add.call_args_list if c.args[0].status == "error")
    assert error_row.source == "live"          # the error row is tagged source='live'
    assert "error" in statuses
    assert db.add.call_args_list[-1].args[0].source == "model"  # final served row


def test_http_boundary_worker_5xx_serves_model(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    _mock_worker_http(monkeypatch, http_status=503)

    body = _post_quote().json()

    assert body["source"] == "model"
    assert body["tagPricePence"] > 0
    assert db.add.call_args_list[-1].args[0].source == "model"


def test_anomaly_zero_price_rejected_then_model(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    zero_priced = [
        {"name": "Car Park 3", "pricePence": 0, "priceText": "£0.00"},
        {"name": "Car Park 2", "pricePence": 14994, "priceText": "£149.94"},
        {"name": "Car Park 1", "pricePence": 16920, "priceText": "£169.20"},
        {"name": "Car Park 1 Premium", "pricePence": 25500, "priceText": "£255.00"},
    ]
    _mock_worker_http(monkeypatch, products=zero_priced)

    body = _post_quote().json()

    assert body["source"] == "model"
    rejected = db.add.call_args_list[0].args[0]
    assert rejected.status == "rejected"
    assert rejected.reject_reason in ("price_zero", "price_below_floor")
    assert rejected.source == "live"
    assert rejected.tag_price_pence is None
    assert db.add.call_args_list[-1].args[0].source == "model"


def test_discount_pct_range_edges(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "0")   # lower inclusive bound
    assert get_airport_quote_discount_percent() == 0
    assert calculate_tag_price_pence(14805, get_airport_quote_discount_percent()) == 14804

    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "60")  # upper inclusive bound
    assert get_airport_quote_discount_percent() == 60
    assert calculate_tag_price_pence(10000, get_airport_quote_discount_percent()) == 4000

    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "60.01")  # just over -> default
    assert get_airport_quote_discount_percent() == 25

    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "-1")     # negative -> default
    assert get_airport_quote_discount_percent() == 25


def test_endpoint_billing_days_rounds_up_on_boundary_crossing(monkeypatch):
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    monkeypatch.delenv("AIRPORT_QUOTE_WORKER_URL", raising=False)  # no worker -> model path

    exactly_7 = _post_quote({"exitDate": "2026-07-13", "exitTime": "06:00"}).json()
    assert exactly_7["billing_days"] == 7

    one_min_over = _post_quote({"exitDate": "2026-07-13", "exitTime": "06:01"}).json()
    assert one_min_over["billing_days"] == 8  # crossing the 24h block by a minute adds a day


def test_endpoint_sub_24h_returns_one_day_price_not_no_price(monkeypatch):
    """§4/§6 (intended): sub-24h is NOT no-price; max(1, ceil) floors to 1 day."""
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    monkeypatch.delenv("AIRPORT_QUOTE_WORKER_URL", raising=False)

    body = _post_quote({"exitDate": "2026-07-06", "exitTime": "20:00"}).json()

    assert body["billing_days"] == 1
    assert body["tagPricePence"] > 0
    assert body["source"] == "model"


def test_sustained_outage_price_does_not_drift(monkeypatch):
    """§6 adversarial: with the worker failing repeatedly, repeated quotes for the
    same trip return a STABLE modeled price — modeled rows never feed the model."""
    fallback = SimpleNamespace(
        products_json=[{"name": "Car Park 1", "pricePence": 13500, "priceText": "£135.00"}],
        cheapest_pence=13500,
        source="live",
    )
    db = _mock_db(fallback)
    _override_quote_db(monkeypatch, db)
    _mock_worker_http(monkeypatch, raise_exc=httpx.ConnectError("down"))

    prices = []
    for _ in range(5):
        body = _post_quote().json()
        assert body["source"] == "model"
        prices.append(body["tagPricePence"])

    assert len(set(prices)) == 1  # no drift across repeated outage quotes


def test_deferred_day_over_day_jump_is_not_yet_a_gate(monkeypatch):
    """DEFERRED (§7/§18): the day-over-day-jump / rolling-norm checks are NOT built
    in this slice. A structurally-valid but anomalously high live price currently
    PASSES the gate (known, owner-flagged residual risk). This documents today's
    behaviour so the future slice that adds the jump gate flips this to 'model'."""
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    inflated = [
        {"name": "Car Park 3", "pricePence": 1480500, "priceText": "£14805.00"},  # 100x
        {"name": "Car Park 2", "pricePence": 1499400, "priceText": "£14994.00"},
        {"name": "Car Park 1", "pricePence": 1692000, "priceText": "£16920.00"},
        {"name": "Car Park 1 Premium", "pricePence": 2550000, "priceText": "£25500.00"},
    ]
    _mock_worker_http(monkeypatch, products=inflated)

    body = _post_quote().json()

    assert body["source"] == "live"  # accepted today; would be "model" once the jump gate lands
    assert db.add.call_args_list[-1].args[0].status == "ok"


# ===========================================================================
# QA brief §3 — matrix additivity + boundary discipline.
#
# Two layers:
#  * Endpoint layer (TestClient + real service over the model path) — proves
#    additivity and the floor end-to-end. The conversion-log INSERT params
#    (db.execute.call_args.args[1]) expose the band + lead_days the service
#    actually decided, so we read the decision back through the real flow.
#  * Decision layer (get_airport_quote_discount_decision) — pure function,
#    used as a SUPPLEMENT for t-ε/t/t+ε precision on each boundary and DST.
#
# UK-now is pinned everywhere a lead day is asserted so dates don't drift
# with the wall clock.
# ===========================================================================

_PINNED_UK_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _pin_model_path(monkeypatch, *, uk_now=_PINNED_UK_NOW):
    """Deterministic model path: no worker, pinned UK now, fresh mock db."""
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: None)
    monkeypatch.setattr("main.get_uk_now", lambda: uk_now)
    return db


def _conversion_params(db):
    """The params dict the service passed to the conversion-log INSERT."""
    assert db.execute.called, "expected a conversion-log write"
    return db.execute.call_args.args[1]


# --- additivity: flag off / unset / invalid == flat-percent baseline --------


def test_matrix_off_unset_invalid_all_equal_flat_baseline_zero_diff(monkeypatch):
    """Golden additive proof: with the matrix DISABLED, UNSET, or ENABLED-but-
    unparseable, the served price and band are byte-identical to the captured
    flat-percent baseline. The flag adds nothing in the off state."""
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")
    quote = {
        "entryDate": "2026-07-06", "entryTime": "06:00",
        "exitDate": "2026-07-13", "exitTime": "06:00",  # billing 7 -> model 14805
        "destination": "Other",
    }

    # Baseline: matrix flag entirely unset.
    monkeypatch.delenv("AIRPORT_QUOTE_MATRIX_ENABLED", raising=False)
    monkeypatch.delenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", raising=False)
    db = _pin_model_path(monkeypatch)
    baseline = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    baseline_band = _conversion_params(db)["discount_band"]
    assert baseline["tagPricePence"] == 11103  # floor(14805 * 0.75)
    assert baseline["pricingInfo"]["discount_pct_used"] == 25.0
    assert baseline_band == "flat"

    # Flag explicitly OFF.
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "false")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    db_off = _pin_model_path(monkeypatch)
    off = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    assert off["tagPricePence"] == baseline["tagPricePence"]
    assert _conversion_params(db_off)["discount_band"] == "flat"

    # Flag ON but matrix unparseable -> flat fallback, same number.
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12")  # 3 values
    db_bad = _pin_model_path(monkeypatch)
    bad = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    assert bad["tagPricePence"] == baseline["tagPricePence"]
    assert _conversion_params(db_bad)["discount_band"] == "flat-fallback"


def test_matrix_on_diverges_only_when_enabled(monkeypatch):
    """Counterpart to the additive proof: the SAME trip prices differently once
    the flag flips on and the band differs from flat — proving the matrix is
    wired and is the only thing the flag changes."""
    quote = {
        "entryDate": "2026-07-06", "entryTime": "06:00",
        "exitDate": "2026-07-14", "exitTime": "06:00",  # billing 8 -> model 15040
        "destination": "Other",
    }
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")

    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "false")
    db_off = _pin_model_path(monkeypatch)
    off = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    assert off["tagPricePence"] == 11280  # floor(15040 * 0.75), flat 25%
    assert _conversion_params(db_off)["discount_band"] == "flat"

    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    db_on = _pin_model_path(monkeypatch)
    on = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    # lead 12 (<=70) near, billing 8 (>7) long -> near-long = 20%
    assert on["tagPricePence"] == 12032  # floor(15040 * 0.80)
    assert _conversion_params(db_on)["discount_band"] == "near-long"
    assert on["tagPricePence"] != off["tagPricePence"]


# --- lead boundary 69 / 70 / 71 at the real default (70) --------------------


def test_lead_boundary_69_70_71_flips_once_at_default(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    monkeypatch.delenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", raising=False)  # default 70
    monkeypatch.delenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", raising=False)  # default 7

    bands = []
    for lead in (69, 70, 71):
        decision = get_airport_quote_discount_decision(
            _PINNED_UK_NOW.date() + timedelta(days=lead),
            7,  # short
            shown_at=_PINNED_UK_NOW,
        )
        assert decision.lead_days == lead
        bands.append(decision.discount_band)

    # near up to and including 70; far from 71. Exactly one flip, on the far side.
    assert bands == ["near-short", "near-short", "far-short"]


# --- duration boundary 6 / 7 / 8 at the real default (7) --------------------


def test_duration_boundary_6_7_8_flips_once_at_default(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    monkeypatch.delenv("AIRPORT_QUOTE_DURATION_BOUNDARY_DAYS", raising=False)  # default 7
    monkeypatch.delenv("AIRPORT_QUOTE_LEAD_BOUNDARY_DAYS", raising=False)  # default 70

    bands = []
    for billing in (6, 7, 8):
        decision = get_airport_quote_discount_decision(
            _PINNED_UK_NOW.date() + timedelta(days=10),  # near
            billing,
            shown_at=_PINNED_UK_NOW,
        )
        bands.append(decision.discount_band)

    # short up to and including 7; long from 8. Exactly one flip.
    assert bands == ["near-short", "near-short", "near-long"]


# --- floor t-ε / t / t+ε at £65 (calc precision) ----------------------------


def test_floor_just_above_at_below_65_pounds():
    floor = 6500  # £65.00
    # Price caps at cheapest-1 before the floor is applied.
    assert calculate_tag_price_pence(6501, 0, floor) == 6500  # cap to 6500, then floor
    assert calculate_tag_price_pence(6500, 0, floor) == 6500  # cap to 6499, then floor
    assert calculate_tag_price_pence(6499, 0, floor) == 6500  # cap to 6498, then floor


# --- floor clamps in BOTH modes (flag off and flag on) ----------------------


def test_floor_clamps_in_both_modes(monkeypatch):
    quote = {
        "entryDate": "2026-07-06", "entryTime": "06:00",
        "exitDate": "2026-07-13", "exitTime": "06:00",  # billing 7 -> model 14805 -> 11103 @25%
        "destination": "Other",
    }
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")  # near-short=25 == flat

    # Floor ABOVE the discounted price -> clamps in both modes.
    monkeypatch.setenv("AIRPORT_QUOTE_MIN_PRICE_PENCE", "13000")
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "false")
    _pin_model_path(monkeypatch)
    off = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    _pin_model_path(monkeypatch)
    on = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    assert off["tagPricePence"] == 13000
    assert on["tagPricePence"] == 13000

    # Floor BELOW the discounted price -> no clamp in either mode.
    monkeypatch.setenv("AIRPORT_QUOTE_MIN_PRICE_PENCE", "10000")
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "false")
    _pin_model_path(monkeypatch)
    off2 = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    _pin_model_path(monkeypatch)
    on2 = TestClient(app).post("/api/airport-parking/quote", json=quote).json()
    assert off2["tagPricePence"] == 11103
    assert on2["tagPricePence"] == 11103


# --- malformed matrix set -> flat fallback + log ----------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",                 # empty
        "25,20,12",         # too few (3)
        "a,b,c,d",          # non-numeric
        "25,20,12,10,9",    # too many (5)
        "-5,20,12,10",      # negative value
        "25,20,12,61",      # value over the 0-60 cap
    ],
)
def test_malformed_matrix_falls_back_to_flat_with_log(monkeypatch, caplog, raw):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "22")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", raw)

    decision = get_airport_quote_discount_decision(
        _PINNED_UK_NOW.date() + timedelta(days=10),
        7,
        shown_at=_PINNED_UK_NOW,
    )

    assert decision.discount_pct == 22          # flat percent, not a matrix band
    assert decision.discount_band == "flat-fallback"
    assert "AIRPORT_QUOTE_DISCOUNT_MATRIX" in caplog.text


# --- DST-sensitive lead_days computes in Europe/London ----------------------


def test_lead_days_uses_london_date_not_utc_across_midnight(monkeypatch):
    """A quote shown at 23:30 UTC during BST is already the next calendar day in
    London. lead_days must count from the London date, not the UTC date."""
    monkeypatch.delenv("AIRPORT_QUOTE_MATRIX_ENABLED", raising=False)
    shown_at = datetime(2026, 6, 24, 23, 30, tzinfo=timezone.utc)  # London BST -> 2026-06-25 00:30
    decision = get_airport_quote_discount_decision(
        date(2026, 7, 5),
        7,
        shown_at=shown_at,
    )
    # London date 2026-06-25 -> 10 days to 07-05 (UTC date 06-24 would give 11).
    assert decision.lead_days == 10


def test_lead_days_spanning_autumn_clock_change_counts_calendar_days(monkeypatch):
    """Lead window straddling the BST->GMT switch (2026-10-25) counts whole
    calendar days with no DST double-count."""
    monkeypatch.delenv("AIRPORT_QUOTE_MATRIX_ENABLED", raising=False)
    shown_at = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)  # London 13:00 BST, 10-20
    decision = get_airport_quote_discount_decision(
        date(2026, 11, 5),  # after the GMT switch
        7,
        shown_at=shown_at,
    )
    assert decision.lead_days == 16


# --- out-of-grid inputs: duration <3, >15; lead negative / 0 ----------------


def test_out_of_grid_short_duration_under_3_prices_and_bands(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    db = _pin_model_path(monkeypatch)
    body = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-07-06", "entryTime": "06:00",
            "exitDate": "2026-07-08", "exitTime": "06:00",  # billing 2 (<3)
            "destination": "Other",
        },
    ).json()
    assert body["billing_days"] == 2
    assert body["tagPricePence"] == 6000  # floor(8000 * 0.75) near-short
    params = _conversion_params(db)
    assert params["billing_days"] == 2
    assert params["discount_band"] == "near-short"


def test_out_of_grid_long_duration_over_15_prices_and_bands(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")
    db = _pin_model_path(monkeypatch)
    body = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-07-06", "entryTime": "06:00",
            "exitDate": "2026-07-22", "exitTime": "06:00",  # billing 16 (>15)
            "destination": "Other",
        },
    ).json()
    assert body["billing_days"] == 16
    # bootstrap day14=21888 + (16-14)*1250 = 24388; near-long 20% -> floor(24388*0.8)
    assert body["tagPricePence"] == 19510
    params = _conversion_params(db)
    assert params["billing_days"] == 16
    assert params["discount_band"] == "near-long"


def test_out_of_grid_lead_zero_and_negative_still_price(monkeypatch):
    monkeypatch.setenv("AIRPORT_QUOTE_MATRIX_ENABLED", "true")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_MATRIX", "25,20,12,10")

    # lead 0: entry == pinned UK today.
    db0 = _pin_model_path(monkeypatch)
    zero = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-06-24", "entryTime": "06:00",
            "exitDate": "2026-07-01", "exitTime": "06:00",  # billing 7
            "destination": "Other",
        },
    ).json()
    assert zero["tagPricePence"] > 0
    p0 = _conversion_params(db0)
    assert p0["lead_days"] == 0
    assert p0["discount_band"] == "near-short"

    # lead negative: entry already in the past.
    dbn = _pin_model_path(monkeypatch)
    neg = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-06-20", "entryTime": "06:00",
            "exitDate": "2026-06-27", "exitTime": "06:00",  # billing 7
            "destination": "Other",
        },
    ).json()
    assert neg["tagPricePence"] > 0
    pn = _conversion_params(dbn)
    assert pn["lead_days"] == -4
    assert pn["discount_band"] == "near-short"


# ===========================================================================
# QA brief — conversion-logging lifecycle (#1 show-state, #2 re-show, #3 batch).
#
# Lifecycle of one conversion-log row:
#   quote shown   -> INSERT ... converted=false   (customer endpoint only)
#   payment OK    -> UPDATE ... SET converted=true (webhook / free-booking)
#   re-shown      -> ON CONFLICT DO NOTHING        (no clobber, no re-stamp)
#   batch refresh -> NO write at all
#
# The DB is mocked, so the ON CONFLICT / converted=true SEMANTICS are a
# Postgres guarantee we assert via the emitted SQL shape; the false->true
# TIMING is proven by the paired create-intent (no flip) and webhook (flip)
# handler tests — see test_create_intent_hueb.py::
# test_H_airport_quote_paid_intent_does_not_mark_conversion_yet and
# test_stripe_webhook_hueb_integration.py::
# test_H_payment_succeeded_issues_real_converted_update_sql.
# ===========================================================================


def _execute_sql_calls(db):
    """(sql_text_lower, params) for every db.execute call."""
    return [
        (str(call.args[0]).lower(), call.args[1] if len(call.args) > 1 else None)
        for call in db.execute.call_args_list
    ]


def _conversion_log_calls(db):
    return [(sql, params) for sql, params in _execute_sql_calls(db)
            if "airport_quote_conversion_log" in sql]


# --- #1: quote-shown writes converted=false and never flips at show time -----


def test_quote_shown_inserts_converted_false_and_does_not_flip(monkeypatch):
    db = _pin_model_path(monkeypatch)
    TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-07-06", "entryTime": "06:00",
            "exitDate": "2026-07-13", "exitTime": "06:00",
            "destination": "Other",
        },
    )

    log_calls = _conversion_log_calls(db)
    assert len(log_calls) == 1, "exactly one conversion-log write at show time"
    sql, _ = log_calls[0]
    assert "insert into airport_quote_conversion_log" in sql
    assert "false" in sql                       # row is seeded NOT-converted
    assert "set converted = true" not in sql    # nothing flips at show time
    # No UPDATE-to-converted issued anywhere in the show lifecycle.
    assert all("set converted = true" not in sql for sql, _ in _execute_sql_calls(db))


# --- #2: re-showing the same quote is ON CONFLICT DO NOTHING -----------------


def test_record_conversion_log_emits_do_nothing_not_do_update():
    """Unit-pin the SQL shape: the writer must NOT clobber an existing row.
    DO NOTHING (not DO UPDATE) is what preserves converted=true and shown_at
    when the same snapshot id is shown again."""
    from airport_quote_service import record_quote_conversion_log

    db = MagicMock()
    shown = datetime(2026, 6, 24, 9, 0, tzinfo=timezone.utc)
    record_quote_conversion_log(
        db,
        airport_quote_snapshot_id=555,
        lead_days=12, billing_days=7, discount_band="flat",
        tag_pence=11103, cheapest_boh_pence=14805, shown_at=shown,
    )
    sql = str(db.execute.call_args.args[0]).lower()
    assert "on conflict" in sql
    assert "do nothing" in sql
    assert "do update" not in sql               # must not re-stamp / overwrite


def test_reshow_same_quote_only_emits_idempotent_inserts(monkeypatch):
    """Drive the endpoint twice; every conversion-log write is the same
    DO-NOTHING INSERT and no UPDATE/re-stamp is ever issued."""
    db = _mock_db()
    _override_quote_db(monkeypatch, db)
    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: None)
    monkeypatch.setattr("main.get_uk_now", lambda: _PINNED_UK_NOW)

    body = {
        "entryDate": "2026-07-06", "entryTime": "06:00",
        "exitDate": "2026-07-13", "exitTime": "06:00",
        "destination": "Other",
    }
    TestClient(app).post("/api/airport-parking/quote", json=body)
    TestClient(app).post("/api/airport-parking/quote", json=body)

    log_calls = _conversion_log_calls(db)
    assert len(log_calls) == 2
    for sql, _ in log_calls:
        assert "insert into airport_quote_conversion_log" in sql
        assert "do nothing" in sql
        assert "set converted = true" not in sql  # re-show never flips/clobbers


# --- #3: batch / homepage refresh writes NOTHING to the conversion log ------


def test_batch_refresh_writes_snapshots_but_no_conversion_log(monkeypatch):
    import email_scheduler

    db = _mock_db()
    monkeypatch.setattr("email_scheduler.get_db", lambda: db)

    def scraper(_quote_input):
        return AirportQuoteScrapeResult(
            products=[
                AirportProduct(p["name"], p["pricePence"], p["priceText"])
                for p in _STANDARD_BOH_PRODUCTS
            ]
        )

    monkeypatch.setattr(
        "airport_quote_worker_client.get_worker_scraper_from_env", lambda: scraper
    )

    result = email_scheduler.refresh_homepage_airport_quote_snapshots()

    # The batch path DID run and wrote snapshots (discount math allowed)...
    assert db.add.called
    assert {call.args[0].source for call in db.add.call_args_list} == {"batch"}
    assert not result.get("skipped")
    # ...but it wrote ZERO conversion-log rows.
    assert _conversion_log_calls(db) == []


def test_homepage_comparison_endpoint_writes_no_conversion_log(monkeypatch):
    from database import get_db

    db = _mock_db()  # snapshot lookups return None -> empty comparison

    def _gen():
        yield db

    app.dependency_overrides[get_db] = _gen
    try:
        resp = TestClient(app).get("/api/airport-parking/homepage-comparison")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert _conversion_log_calls(db) == []


def test_boh_79_cell_floors_pre_promo_tag_to_65(monkeypatch):
    """BOH cheapest £79: 25% off = £59.25, below the £65 floor -> the PRE-promo
    TAG clamps UP to £65 at quote time (the floor is applied before any promo)."""
    db = _mock_db()
    _override_quote_db(monkeypatch, db)

    def scraper(_quote_input):
        return AirportQuoteScrapeResult(products=[
            AirportProduct("Car Park 3", 7900, "£79.00"),   # cheapest BOH cell
            AirportProduct("Car Park 2", 8500, "£85.00"),
            AirportProduct("Car Park 1", 9500, "£95.00"),
            AirportProduct("Car Park 1 Premium", 12000, "£120.00"),
        ])

    monkeypatch.setattr("main.get_airport_quote_scraper", lambda: scraper)
    monkeypatch.setattr("main.get_uk_now", lambda: _PINNED_UK_NOW)
    monkeypatch.delenv("AIRPORT_QUOTE_MATRIX_ENABLED", raising=False)  # flat path
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")
    monkeypatch.setenv("AIRPORT_QUOTE_MIN_PRICE_PENCE", "6500")  # £65 floor

    body = TestClient(app).post(
        "/api/airport-parking/quote",
        json={
            "entryDate": "2026-07-06", "entryTime": "06:00",
            "exitDate": "2026-07-13", "exitTime": "06:00",  # billing 7
            "destination": "Other",
        },
    ).json()

    assert body["source"] == "live"
    assert min(p["pricePence"] for p in body["airportPrices"]) == 7900  # £79 BOH
    assert body["tagPricePence"] == 6500  # pre-promo TAG floored to £65
