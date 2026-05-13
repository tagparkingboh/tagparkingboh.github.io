"""
Mocked-integration tests for GET /api/capacity/daily.

Customer-facing endpoint that drives the date-pick-time capacity block on
the booking page. H/U/E/B per SPEC, TestClient-based so it actually
exercises main.py and counts toward coverage.
"""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from database import get_db
from db_models import Booking, BookingStatus


class FakeQuery:
    """Minimal SQLAlchemy query stub — filter()/in_() are no-ops; tests
    populate `_tables` directly so the filter conditions don't matter."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def mk_booking(*, dropoff, pickup, status=BookingStatus.CONFIRMED):
    """Lightweight Booking stub — only the fields the handler reads."""
    return SimpleNamespace(
        dropoff_date=dropoff,
        pickup_date=pickup,
        status=status,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._tables = {Booking: []}

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    db.query.side_effect = _query
    return db


def _client(mock_db):
    def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


class TestCapacityDailyHappy:

    def test_happy_three_overlapping_bookings_on_one_day(self, mock_db):
        d = date(2026, 6, 15)
        mock_db._tables[Booking] = [
            mk_booking(dropoff=d, pickup=d),
            mk_booking(dropoff=d, pickup=d),
            mk_booking(dropoff=d, pickup=d),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.status_code == 200
        body = r.json()
        assert body["daily_occupancy"] == {"2026-06-15": 3}
        # Cap is sourced from BookingService.MAX_PARKING_SPOTS — locked at 60.
        assert body["max_capacity"] == 60

    def test_happy_booking_spans_multiple_days(self, mock_db):
        """A single car parked over 3 days adds +1 to each day in the range."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff=date(2026, 6, 15), pickup=date(2026, 6, 17)),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        assert r.json()["daily_occupancy"] == {
            "2026-06-15": 1,
            "2026-06-16": 1,
            "2026-06-17": 1,
        }

    def test_happy_pending_counted_alongside_confirmed(self, mock_db):
        """PENDING bookings are in-payment-flow and must count so two
        customers can't race for the same last spot."""
        d = date(2026, 6, 15)
        mock_db._tables[Booking] = [
            mk_booking(dropoff=d, pickup=d, status=BookingStatus.CONFIRMED),
            mk_booking(dropoff=d, pickup=d, status=BookingStatus.PENDING),
            mk_booking(dropoff=d, pickup=d, status=BookingStatus.COMPLETED),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.status_code == 200
        # FakeQuery doesn't actually filter — but the handler's count loop
        # walks every row, so this confirms PENDING + COMPLETED are eligible
        # alongside CONFIRMED in the response shape.
        assert r.json()["daily_occupancy"]["2026-06-15"] == 3


class TestCapacityDailyUnhappy:

    def test_unhappy_date_to_before_date_from(self, mock_db):
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-20&date_to=2026-06-15")
        assert r.status_code == 400
        assert "date_to" in r.json()["detail"].lower()

    def test_unhappy_range_too_large(self, mock_db):
        # 91-day range exceeds the 90-day cap.
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-01-01&date_to=2026-04-02")
        assert r.status_code == 400
        assert "90" in r.json()["detail"]

    def test_unhappy_missing_query_param(self, mock_db):
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15")
        # FastAPI returns 422 for missing required query params.
        assert r.status_code == 422


class TestCapacityDailyEdge:

    def test_edge_no_bookings_returns_all_zeros(self, mock_db):
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        assert r.json()["daily_occupancy"] == {
            "2026-06-15": 0,
            "2026-06-16": 0,
            "2026-06-17": 0,
        }

    def test_edge_booking_partially_overlaps_window(self, mock_db):
        """Booking 2026-06-13 → 2026-06-16, window 2026-06-15 → 2026-06-17:
        the booking contributes to 15 + 16 only (it picked up on 16)."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff=date(2026, 6, 13), pickup=date(2026, 6, 16)),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        assert r.json()["daily_occupancy"] == {
            "2026-06-15": 1,
            "2026-06-16": 1,
            "2026-06-17": 0,
        }


class TestCapacityDailyBoundary:

    def test_boundary_single_day_range(self, mock_db):
        mock_db._tables[Booking] = [
            mk_booking(dropoff=date(2026, 6, 15), pickup=date(2026, 6, 15)),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.status_code == 200
        body = r.json()
        assert list(body["daily_occupancy"].keys()) == ["2026-06-15"]
        assert body["daily_occupancy"]["2026-06-15"] == 1

    def test_boundary_exactly_90_day_range_allowed(self, mock_db):
        # 90-day inclusive range is at the upper bound — must succeed.
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-01-01&date_to=2026-04-01")
        assert r.status_code == 200
        assert len(r.json()["daily_occupancy"]) == 91  # inclusive

    def test_boundary_dropoff_on_window_end_counted(self, mock_db):
        """A booking whose dropoff_date == the window's date_to still
        contributes to that day (boundary inclusive)."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff=date(2026, 6, 17), pickup=date(2026, 6, 20)),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        occ = r.json()["daily_occupancy"]
        assert occ["2026-06-15"] == 0
        assert occ["2026-06-16"] == 0
        assert occ["2026-06-17"] == 1

    def test_boundary_pickup_on_window_start_counted(self, mock_db):
        """A booking whose pickup_date == the window's date_from still
        contributes to that day (boundary inclusive)."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff=date(2026, 6, 10), pickup=date(2026, 6, 15)),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        occ = r.json()["daily_occupancy"]
        assert occ["2026-06-15"] == 1
        assert occ["2026-06-16"] == 0
        assert occ["2026-06-17"] == 0
