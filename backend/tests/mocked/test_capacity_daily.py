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

    def test_happy_only_confirmed_and_completed_seed_returns_count(self, mock_db):
        """PENDING is excluded by the handler's status filter (post-2026-05-21);
        seed only the rows the real query would return after that filter and
        assert the count loop produces the right occupancy."""
        d = date(2026, 6, 15)
        mock_db._tables[Booking] = [
            mk_booking(dropoff=d, pickup=d, status=BookingStatus.CONFIRMED),
            mk_booking(dropoff=d, pickup=d, status=BookingStatus.COMPLETED),
        ]
        r = _client(mock_db).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.status_code == 200
        assert r.json()["daily_occupancy"]["2026-06-15"] == 2

    def test_happy_status_filter_excludes_pending(self):
        """Regression for the 2026-05-21 incident (27 May prod: 57 confirmed
        + 3 pending → ops calendar showed "Full (60)" but real occupancy was
        57). Asserts the handler's SQLAlchemy filter passes a status list
        that does NOT include PENDING. Stronger than FakeQuery-based tests
        which can't observe the filter clause."""
        captured = {"in_args": None}

        class _SpyChain:
            def __init__(self):
                self.calls = 0

            def filter(self, *args, **_kw):
                self.calls += 1
                # First .filter() is the status filter — capture its first
                # argument's in_() values for inspection.
                for arg in args:
                    if captured["in_args"] is None and hasattr(arg, "right"):
                        try:
                            # SQLAlchemy In-expression: arg.right is a
                            # BindParameter or a tuple of values.
                            value = arg.right.value if hasattr(arg.right, "value") else None
                            if value is not None:
                                captured["in_args"] = value
                        except Exception:
                            pass
                return self

            def all(self):
                return []

        db = MagicMock()
        db.query.return_value = _SpyChain()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            r = TestClient(app).get("/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
            assert r.status_code == 200
            assert captured["in_args"] is not None, "status filter clause not observed"
            assert BookingStatus.CONFIRMED in captured["in_args"]
            assert BookingStatus.COMPLETED in captured["in_args"]
            assert BookingStatus.PENDING not in captured["in_args"], (
                "PENDING must not count toward customer-facing daily occupancy"
            )
        finally:
            app.dependency_overrides.clear()


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
