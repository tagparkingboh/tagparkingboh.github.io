from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from airport_quote_service import (
    AirportProduct,
    AirportQuoteInput,
    AirportQuoteScrapeResult,
    calculate_billing_days,
    calculate_tag_price_pence,
    get_airport_quote_discount_percent,
    normalise_boh_time_slot,
    parse_boh_products,
    fallback_quote_from_snapshots,
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


def test_quote_endpoint_live_success_records_snapshot(monkeypatch):
    db = _mock_db()
    events = []
    _override_quote_db(monkeypatch, db)

    def scraper(quote_input: AirportQuoteInput, destination_id: str):
        events.append(("scrape", db.query.called))
        assert quote_input.entry_date == date(2026, 7, 6)
        assert destination_id != "2182"
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
    assert snapshot.cheapest_pence == 14805
    assert snapshot.tag_price_pence == 11103


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

    def scraper(_quote_input: AirportQuoteInput, _destination_id: str):
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

    def scraper(_quote_input: AirportQuoteInput, _destination_id: str):
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
        "2182",
    )

    assert calls[0] == (
        "https://worker.example/internal/airport-parking/scrape",
        {
            "entryDate": "2026-07-06",
            "entryTime": "06:00",
            "exitDate": "2026-07-13",
            "exitTime": "06:00",
            "destinationId": "2182",
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
    )
    db = _mock_db(snapshot)

    assert resolve_airport_quote_amount_pence(
        db,
        12,
        dropoff_date=date(2026, 7, 6),
    ) == 11103

    with pytest.raises(Exception):
        resolve_airport_quote_amount_pence(
            db,
            12,
            dropoff_date=date(2026, 7, 7),
        )
