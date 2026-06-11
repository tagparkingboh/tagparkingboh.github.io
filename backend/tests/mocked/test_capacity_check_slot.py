"""
Mocked-integration tests for GET /api/capacity/check-slot.

Time-aware capacity gate. Uses peak-concurrent-events within the customer's
[dropoff_dt, pickup_dt] window so a 16:30 drop-off is allowed even when the
day is "full" if another car is being picked up at 16:00.

H/U/E/B per SPEC. TestClient-based so it executes main.py and counts toward
coverage.
"""
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from database import get_db
from db_models import Booking, BookingStatus, ParkingCapacitySetting


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def mk_booking(*, dropoff_date, dropoff_time, pickup_date, pickup_time,
               status=BookingStatus.CONFIRMED):
    """Lightweight Booking stub — only the fields the handler reads."""
    return SimpleNamespace(
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
        status=status,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._tables = {Booking: [], ParkingCapacitySetting: []}

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


def _qs(*, dd, dt, pd, pt):
    """Build the query string with the four required params."""
    return f"dropoff_date={dd}&dropoff_time={dt}&pickup_date={pd}&pickup_time={pt}"


class TestCheckSlotHappy:

    def test_happy_empty_lot_is_allowed(self, mock_db):
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["peak"] == 0
        assert body["max_capacity"] == 73
        assert body["online_capacity"] == 73

    def test_happy_pickup_at_1600_releases_spot_for_1630_dropoff(self, mock_db):
        """User-described scenario: existing car picked up at 16:00 → spot is
        free for a 16:30 drop-off. Peak during the customer's stay is the
        single existing booking, capped only at the truncated overlap (none —
        the existing car leaves before the customer arrives)."""
        # 73 existing cars all leaving by 16:00 on June 15. Customer wants
        # 16:30 on June 15 → 10:00 on June 16. Peak during customer's window
        # should be 0 because every existing car's leave time is before
        # customer's drop-off, so they don't appear inside the window at all.
        d = date(2026, 6, 15)
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=d, dropoff_time=time(10, 0),
                pickup_date=d, pickup_time=time(16, 0),
            )
            for _ in range(73)
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="16:30", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["peak"] == 0  # no other car is in the lot during stay

    def test_happy_72_concurrent_during_stay_still_allows_73rd(self, mock_db):
        """Lot has 72 cars all parked overnight through the customer's window
        → customer is allowed as the 73rd (peak + 1 = 73 ≤ 73)."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 14), dropoff_time=time(9, 0),
                pickup_date=date(2026, 6, 16), pickup_time=time(12, 0),
            )
            for _ in range(72)
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is True
        assert body["peak"] == 72


class TestCheckSlotUnhappy:

    def test_unhappy_73_concurrent_blocks_74th(self, mock_db):
        """When 73 existing cars overlap the customer's stay, peak = 73,
        peak + 1 = 74 > cap → blocked."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 14), dropoff_time=time(9, 0),
                pickup_date=date(2026, 6, 16), pickup_time=time(12, 0),
            )
            for _ in range(73)
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        body = r.json()
        assert body["allowed"] is False
        assert body["peak"] == 73
        assert body["max_capacity"] == 73

    def test_unhappy_pickup_before_dropoff_rejected(self, mock_db):
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-15", pt="10:00",
            )
        )
        assert r.status_code == 400
        assert "pickup" in r.json()["detail"].lower()

    def test_unhappy_malformed_time_rejected(self, mock_db):
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14h00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 400
        assert "HH:MM" in r.json()["detail"]

    def test_unhappy_stay_too_long(self, mock_db):
        # 91 days > the 90-day max.
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-01", dt="14:00", pd="2026-08-31", pt="10:00",
            )
        )
        assert r.status_code == 400
        assert "90" in r.json()["detail"]


class TestCheckSlotEdge:

    def test_edge_existing_booking_partially_inside_window(self, mock_db):
        """Existing car arrives mid-stay → contributes +1 from its actual
        arrival inside the window, not from the customer's drop-off."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 15), dropoff_time=time(18, 0),
                pickup_date=date(2026, 6, 17), pickup_time=time(9, 0),
            )
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        assert r.json()["peak"] == 1  # one car overlaps from 18:00 onwards

    def test_edge_existing_booking_envelops_customer_stay(self, mock_db):
        """Existing car parked since yesterday and not leaving until next
        week → contributes +1 across the entire customer window."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 10), dropoff_time=time(8, 0),
                pickup_date=date(2026, 6, 20), pickup_time=time(20, 0),
            )
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        assert r.json()["peak"] == 1

    def test_edge_existing_booking_outside_window_ignored(self, mock_db):
        """An existing booking that starts AFTER customer's pickup must not
        count — it's not in the lot during customer's stay."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 16), dropoff_time=time(11, 0),
                pickup_date=date(2026, 6, 18), pickup_time=time(9, 0),
            )
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        assert r.json()["peak"] == 0


class TestCheckSlotBoundary:

    def test_boundary_existing_pickup_at_exact_customer_dropoff_ties_safely(self, mock_db):
        """Existing booking pickup at 16:00, customer drop at 16:00 →
        with +1-before-−1 tiebreak, the new arrival ticks up before the
        departure registers, so peak is 1. Block decision: 1+1=2 still well
        below cap; only matters at very high counts."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 15), dropoff_time=time(9, 0),
                pickup_date=date(2026, 6, 15), pickup_time=time(16, 0),
            )
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="16:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        body = r.json()
        # The existing car's enter is max(09:00, 16:00) = 16:00; leave is
        # min(16:00, customer's 16:00 next-day) = 16:00. enter < leave is
        # False → it doesn't contribute. Peak = 0.
        assert body["peak"] == 0
        assert body["allowed"] is True

    def test_boundary_existing_dropoff_at_customer_pickup_does_not_count(self, mock_db):
        """An existing booking that drops off exactly when the customer
        picks up shares only a zero-length instant — must not count."""
        mock_db._tables[Booking] = [
            mk_booking(
                dropoff_date=date(2026, 6, 16), dropoff_time=time(10, 0),
                pickup_date=date(2026, 6, 18), pickup_time=time(9, 0),
            )
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        assert r.json()["peak"] == 0

    def test_boundary_exactly_90_day_stay_allowed(self, mock_db):
        # Inclusive 90-day range is at the upper bound — must process.
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-01-01", dt="14:00", pd="2026-04-01", pt="10:00",
            )
        )
        assert r.status_code == 200

    def test_boundary_one_minute_stay_returns_peak_0_on_empty_lot(self, mock_db):
        """Edge of a valid stay: 1 minute long."""
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-15", pt="14:01",
            )
        )
        assert r.status_code == 200
        assert r.json()["allowed"] is True
        assert r.json()["peak"] == 0
