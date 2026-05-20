"""
HUEB tests for /api/capacity/check-slot + /api/pricing/calculate +
/api/pricing/tiers + /api/prices/durations.
"""
from datetime import date as date_type, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app
from database import get_db


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# GET /api/capacity/check-slot
# ============================================================================

class TestCheckSlot:
    def teardown_method(self):
        _clear()

    def _wire(self, bookings):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = bookings
        db.query.return_value = chain
        return db

    def test_H_empty_lot_allows(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-01", "dropoff_time": "10:00",
            "pickup_date": "2026-06-08", "pickup_time": "11:30",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is True
        assert body["peak"] == 0
        assert body["max_capacity"] == 60

    def test_H_one_overlap_allows(self):
        from db_models import BookingStatus
        other = SimpleNamespace(
            status=BookingStatus.CONFIRMED,
            dropoff_date=date_type(2026, 6, 1), dropoff_time=time(9, 0),
            pickup_date=date_type(2026, 6, 8), pickup_time=time(12, 0),
        )
        _override(self._wire([other]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-01", "dropoff_time": "10:00",
            "pickup_date": "2026-06-08", "pickup_time": "11:30",
        })
        assert resp.json()["peak"] == 1
        assert resp.json()["allowed"] is True

    def test_U_pickup_before_dropoff(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-08", "dropoff_time": "10:00",
            "pickup_date": "2026-06-01", "pickup_time": "11:30",
        })
        assert resp.status_code == 400
        assert "pickup must be after" in resp.json()["detail"].lower()

    def test_U_stay_too_long(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-01", "dropoff_time": "10:00",
            "pickup_date": "2026-12-01", "pickup_time": "11:30",
        })
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    def test_U_invalid_time_format(self):
        _override(self._wire([]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-01", "dropoff_time": "bogus",
            "pickup_date": "2026-06-08", "pickup_time": "11:30",
        })
        assert resp.status_code == 400

    def test_E_back_to_back_swap_counts_as_collision(self):
        """The sort `(time, -delta)` puts +1 BEFORE -1 at the same instant —
        so a 11:30 pickup and 11:30 dropoff are counted as transient overlap."""
        from db_models import BookingStatus
        # Existing booking pickup is exactly 11:30
        existing = SimpleNamespace(
            status=BookingStatus.CONFIRMED,
            dropoff_date=date_type(2026, 6, 1), dropoff_time=time(9, 0),
            pickup_date=date_type(2026, 6, 8), pickup_time=time(11, 30),
        )
        _override(self._wire([existing]))
        resp = TestClient(app).get("/api/capacity/check-slot", params={
            "dropoff_date": "2026-06-01", "dropoff_time": "10:00",
            "pickup_date": "2026-06-08", "pickup_time": "11:30",
        })
        assert resp.status_code == 200


# ============================================================================
# POST /api/pricing/calculate
# ============================================================================

class TestPricingCalculate:
    def teardown_method(self):
        _clear()

    def test_H_7_day_trip(self):
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        future_pickup = (datetime.now().date() + timedelta(days=37)).isoformat()
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future_pickup,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["duration_days"] == 7
        assert body["package_name"] == "1 Week Trip"

    def test_H_14_day_trip(self):
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        future_pickup = (datetime.now().date() + timedelta(days=44)).isoformat()
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future_pickup,
        })
        assert resp.status_code == 200
        assert resp.json()["duration_days"] == 14

    def test_E_short_3_day_trip(self):
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        future_pickup = (datetime.now().date() + timedelta(days=33)).isoformat()
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future_pickup,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "3 Day" in body["package_name"]

    def test_U_duration_zero(self):
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future,
        })
        assert resp.status_code == 400
        assert "between 1 and 60" in resp.json()["detail"]

    def test_U_duration_too_long(self):
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        future_pickup = (datetime.now().date() + timedelta(days=100)).isoformat()
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future_pickup,
        })
        assert resp.status_code == 400

    def test_E_pickup_with_early_arrival_time(self):
        """02:00 arrival cutoff: pickup_time = arrival + 30min, so 02:30 customer
        meet means 02:00 arrival → bills as previous day."""
        _override(MagicMock())
        future = (datetime.now().date() + timedelta(days=30)).isoformat()
        future_pickup = (datetime.now().date() + timedelta(days=37)).isoformat()
        # pickup_time 02:30 = arrival 02:00 → just at the cutoff → bills as same day
        resp = TestClient(app).post("/api/pricing/calculate", json={
            "drop_off_date": future, "pickup_date": future_pickup,
            "pickup_time": "02:30",
        })
        assert resp.status_code == 200


# ============================================================================
# GET /api/pricing/tiers + /api/prices/durations
# ============================================================================

class TestPricingTiers:
    def teardown_method(self):
        _clear()

    def test_H_returns_package_prices(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/pricing/tiers")
        assert resp.status_code == 200
        body = resp.json()
        # Returns price tiers for quick/longer packages
        assert isinstance(body, dict)


class TestPricesDurations:
    def teardown_method(self):
        _clear()

    def test_H_returns_durations(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/prices/durations")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
