from datetime import datetime, time, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from airport_quote_service import AirportProduct, AirportQuoteScrapeResult
from email_scheduler import refresh_homepage_airport_quote_snapshots
from main import app


class _QueuedQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows.pop(0) if self.rows else None


class _EndpointDb:
    def __init__(self, rows):
        self.rows = list(rows)

    def query(self, model):
        return _QueuedQuery(self.rows)


class _RefreshDb:
    def __init__(self):
        self.added = []
        self.closed = False

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass

    def refresh(self, row):
        row.id = len(self.added)

    def close(self):
        self.closed = True


def _snapshot(*, billing_days, cheapest, premium, tag, created_at):
    return SimpleNamespace(
        airport="BOH",
        billing_days=billing_days,
        products_json=[
            {"name": "Car Park 3", "pricePence": cheapest, "priceText": f"£{cheapest / 100:.2f}"},
            {"name": "Car Park 2", "pricePence": cheapest + 100, "priceText": f"£{(cheapest + 100) / 100:.2f}"},
            {"name": "Car Park 1", "pricePence": cheapest + 3000, "priceText": f"£{(cheapest + 3000) / 100:.2f}"},
            {"name": "Car Park 1 Premium", "pricePence": premium, "priceText": f"£{premium / 100:.2f}"},
        ],
        cheapest_pence=cheapest,
        tag_price_pence=tag,
        source="live",
        status="ok",
        created_at=created_at,
    )


def test_homepage_airport_comparison_reads_cached_live_snapshots(monkeypatch):
    db = _EndpointDb([
        _snapshot(
            billing_days=4,
            cheapest=16800,
            premium=30000,
            tag=13020,
            created_at=datetime(2026, 6, 23, 8, 30, tzinfo=timezone.utc),
        ),
        _snapshot(
            billing_days=7,
            cheapest=18000,
            premium=32000,
            tag=13950,
            created_at=datetime(2026, 6, 23, 9, 30, tzinfo=timezone.utc),
        ),
    ])
    app.dependency_overrides[main.get_db] = lambda: db
    monkeypatch.setenv("HOMEPAGE_AIRPORT_COMPARISON_PRICE_MODE", "live")
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "30")

    try:
        response = TestClient(app).get("/api/airport-parking/homepage-comparison")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["checkedAt"] == "2026-06-23T09:30:00+00:00"
    assert body["maxCheapestSavingPct"] == 30
    assert body["maxPremiumSavingPct"] == 61
    assert [item["billingDays"] for item in body["items"]] == [4, 7]
    assert body["items"][0]["cheapestPence"] == 16800
    assert body["items"][0]["premiumPence"] == 30000
    assert body["items"][0]["tagPricePence"] == 11760
    assert body["items"][0]["savingPct"] == 30
    assert body["items"][0]["source"] == "live"


def test_homepage_airport_comparison_recomputes_tag_price_when_discount_changes(monkeypatch):
    def get_response(discount):
        db = _EndpointDb([
            _snapshot(
                billing_days=4,
                cheapest=16800,
                premium=30000,
                tag=13020,
                created_at=datetime(2026, 6, 23, 8, 30, tzinfo=timezone.utc),
            ),
            _snapshot(
                billing_days=7,
                cheapest=18000,
                premium=32000,
                tag=13950,
                created_at=datetime(2026, 6, 23, 9, 30, tzinfo=timezone.utc),
            ),
        ])
        app.dependency_overrides[main.get_db] = lambda: db
        monkeypatch.setenv("HOMEPAGE_AIRPORT_COMPARISON_PRICE_MODE", "live")
        monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", str(discount))
        try:
            return TestClient(app).get("/api/airport-parking/homepage-comparison")
        finally:
            app.dependency_overrides.clear()

    thirty_pct = get_response(30).json()
    twenty_five_pct = get_response(25).json()

    assert thirty_pct["items"][1]["tagPricePence"] == 12600
    assert thirty_pct["items"][1]["savingPct"] == 30
    assert thirty_pct["items"][1]["premiumSavingPct"] == 61
    assert twenty_five_pct["items"][1]["tagPricePence"] == 13500
    assert twenty_five_pct["items"][1]["savingPct"] == 25
    assert twenty_five_pct["items"][1]["premiumSavingPct"] == 58


def test_homepage_airport_comparison_empty_when_no_live_cache(monkeypatch):
    app.dependency_overrides[main.get_db] = lambda: _EndpointDb([None, None])

    try:
        response = TestClient(app).get("/api/airport-parking/homepage-comparison")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_refresh_homepage_airport_quote_snapshots_writes_batch_rows(monkeypatch):
    db = _RefreshDb()

    def scraper(quote_input):
        assert quote_input.entry_time == time(6, 0)
        return AirportQuoteScrapeResult(
            products=[
                AirportProduct("Car Park 3", 16800, "£168.00"),
                AirportProduct("Car Park 2", 17100, "£171.00"),
                AirportProduct("Car Park 1", 19500, "£195.00"),
                AirportProduct("Car Park 1 Premium", 30000, "£300.00"),
            ]
        )

    monkeypatch.setattr("email_scheduler.get_db", lambda: db)
    monkeypatch.setattr("airport_quote_worker_client.get_worker_scraper_from_env", lambda: scraper)
    monkeypatch.setenv("AIRPORT_QUOTE_DISCOUNT_PERCENT", "25")

    result = refresh_homepage_airport_quote_snapshots()

    assert result["skipped"] is False
    assert [item["billing_days"] for item in result["refreshed"]] == [4, 7]
    assert [row.source for row in db.added] == ["batch", "batch"]
    assert [row.status for row in db.added] == ["ok", "ok"]
    assert [row.billing_days for row in db.added] == [4, 7]
    assert all(row.tag_price_pence == 12600 for row in db.added)
    assert db.closed is True
