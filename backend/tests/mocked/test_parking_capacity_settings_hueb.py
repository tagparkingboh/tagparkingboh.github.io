"""
HUEB tests for date-effective parking capacity settings.

The production behaviour is:
  - online checkout/reporting uses online_spaces
  - admin/manual bookings use total_spaces
  - manual reserve is derived as total_spaces - online_spaces
  - effective_from is a UK timestamp, not a date-only value
"""
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import db_service
from database import get_db
from db_models import Booking, BookingStatus, ParkingCapacitySetting
from main import app, require_admin


def _booking(day, *, id=1):
    return SimpleNamespace(
        id=id,
        status=BookingStatus.CONFIRMED,
        dropoff_date=day,
        pickup_date=day,
    )


def _setting(effective_from, total, online, id=1):
    return SimpleNamespace(
        id=id,
        effective_from=effective_from,
        total_spaces=total,
        online_spaces=online,
        updated_at=None,
        updated_by="test",
    )


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_, **__):
        return self

    def order_by(self, *_, **__):
        self.rows.sort(key=lambda row: getattr(row, "effective_from", datetime.min))
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, *, bookings=None, settings=None):
        self.tables = {
            Booking: list(bookings or []),
            ParkingCapacitySetting: list(settings or []),
        }

    def query(self, model):
        return FakeQuery(self.tables.get(model, []))

    def add(self, row):
        if isinstance(row, ParkingCapacitySetting):
            row.id = len(self.tables[ParkingCapacitySetting]) + 1
            row.updated_at = None
            self.tables[ParkingCapacitySetting].append(row)

    def commit(self):
        pass

    def refresh(self, _row):
        pass


def _client(db):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        id=1,
        email="admin@tag.test",
        is_admin=True,
    )
    return TestClient(app)


class TestCapacityScheduleUnit:
    def test_H_default_schedule_preserves_legacy_then_current_capacity(self):
        schedule = db_service._fallback_capacity_schedule()

        legacy = db_service.capacity_for_date_from_schedule(schedule, date(2026, 6, 10))
        current = db_service.capacity_for_date_from_schedule(schedule, date(2026, 6, 11))

        assert legacy["total_spaces"] == 70
        assert legacy["online_spaces"] == 64
        assert current["total_spaces"] == 75
        assert current["online_spaces"] == 73
        assert current["manual_spaces"] == 2

    def test_B_future_timestamp_changes_later_operational_dates(self):
        schedule = db_service._fallback_capacity_schedule() + [
            {
                "id": 3,
                "effective_from": db_service.normalize_capacity_effective_from("2026-06-12T09:30:00"),
                "total_spaces": 90,
                "online_spaces": 88,
                "manual_spaces": 2,
                "updated_at": None,
                "updated_by": "test",
            }
        ]

        before = db_service.capacity_for_date_from_schedule(schedule, date(2026, 6, 11))
        after = db_service.capacity_for_date_from_schedule(schedule, date(2026, 6, 12))

        assert before["online_spaces"] == 73
        assert after["total_spaces"] == 90
        assert after["online_spaces"] == 88

    def test_U_online_spaces_cannot_exceed_total_spaces(self):
        try:
            db_service.validate_capacity_values(total_spaces=75, online_spaces=76)
        except ValueError as exc:
            assert "cannot exceed" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    def test_B_dynamic_gate_blocks_against_per_day_online_capacity(self):
        day = date(2026, 6, 11)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _booking(day, id=i) for i in range(73)
        ]
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            _booking(day, id=i) for i in range(73)
        ]
        capacity_by_date = {
            day.isoformat(): {
                "online_spaces": 73,
                "total_spaces": 75,
                "manual_spaces": 2,
            }
        }

        offending = db_service.find_overcapacity_day_in_stay(
            db,
            dropoff_date=day,
            pickup_date=day,
            cap_by_date=capacity_by_date,
            cap_field="online_spaces",
        )

        assert offending == (day, 73, 73)


class TestCapacitySettingsApi:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_H_admin_get_returns_uk_timestamp_display_and_manual_reserve(self):
        db = FakeDb(settings=[])

        response = _client(db).get("/api/admin/capacity-settings")

        assert response.status_code == 200
        body = response.json()
        assert body["current"]["total_spaces"] == 75
        assert body["current"]["online_spaces"] == 73
        assert body["current"]["manual_spaces"] == 2
        assert body["current"]["effective_from_display"] == "11/06/2026 00:00"

    def test_H_admin_put_creates_future_capacity_row(self):
        db = FakeDb(settings=[])

        response = _client(db).put("/api/admin/capacity-settings", json={
            "effective_from": "2026-06-12T09:30:00",
            "total_spaces": 90,
            "online_spaces": 88,
        })

        assert response.status_code == 200
        body = response.json()
        assert body["setting"]["effective_from_display"] == "12/06/2026 09:30"
        assert body["setting"]["total_spaces"] == 90
        assert body["setting"]["manual_spaces"] == 2

    def test_U_admin_put_rejects_online_above_total(self):
        response = _client(FakeDb()).put("/api/admin/capacity-settings", json={
            "effective_from": "2026-06-12T09:30:00",
            "total_spaces": 75,
            "online_spaces": 76,
        })

        assert response.status_code == 400
        assert "cannot exceed" in response.json()["detail"]

    def test_B_public_daily_capacity_returns_date_effective_online_caps(self):
        db = FakeDb(
            bookings=[_booking(date(2026, 6, 12), id=1)],
            settings=[
                _setting(datetime(2026, 6, 11, 0, 0), 75, 73, id=1),
                _setting(datetime(2026, 6, 12, 9, 30), 90, 88, id=2),
            ],
        )

        response = _client(db).get(
            "/api/capacity/daily?date_from=2026-06-11&date_to=2026-06-12"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["daily_capacity"]["2026-06-11"]["online_spaces"] == 73
        assert body["daily_capacity"]["2026-06-12"]["online_spaces"] == 88
        assert body["daily_occupancy"]["2026-06-12"] == 1
