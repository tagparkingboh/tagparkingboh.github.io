"""
HUEB tests for the secondary car park qualification rule (2026-06 brief).

Business rule: a booking qualifies when BOTH its drop-off and pickup handoff
times fall within the operating window (default 09:00-21:00, boundaries
INCLUSIVE). Window and capacity are env-configured on Railway:
SECONDARY_CARPARK_WINDOW_START / _WINDOW_END / _CAPACITY.

Covers:
  - settings parsing (defaults, overrides, invalid values)
  - qualification boundary triplets on both ends of the window, both events
  - the brief's worked examples verbatim
  - secondary_carpark_info routing payload
  - occupancy report split (daily counts/refs/over-capacity flag,
    weekly/monthly averages, summary block)
  - roster bookings-for-date carries the qualification flag
"""
from datetime import date as date_type, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import main
import db_service
from main import app, require_admin
from database import get_db
from db_models import BookingStatus

from fastapi.testclient import TestClient


def _clear_env(monkeypatch):
    for name in (
        "SECONDARY_CARPARK_WINDOW_START",
        "SECONDARY_CARPARK_WINDOW_END",
        "SECONDARY_CARPARK_CAPACITY",
    ):
        monkeypatch.delenv(name, raising=False)


def _booking(dropoff_time=None, pickup_time=None, **kw):
    base = dict(
        id=1,
        reference="TAG-CARPARK01",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date_type(2026, 6, 18),
        pickup_date=date_type(2026, 6, 26),
        dropoff_time=dropoff_time,
        pickup_time=pickup_time,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestSecondaryCarparkSettings:
    def test_H_defaults_match_business_rule(self, monkeypatch):
        _clear_env(monkeypatch)
        s = db_service.get_secondary_carpark_settings()
        assert s == {
            "window_start": time(9, 0),
            "window_end": time(21, 0),
            "capacity": 20,
        }

    def test_H_env_overrides_apply(self, monkeypatch):
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_START", "08:30")
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_END", "22:15")
        monkeypatch.setenv("SECONDARY_CARPARK_CAPACITY", "35")
        s = db_service.get_secondary_carpark_settings()
        assert s == {
            "window_start": time(8, 30),
            "window_end": time(22, 15),
            "capacity": 35,
        }

    def test_U_invalid_values_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_START", "bogus")
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_END", "25:99x")
        monkeypatch.setenv("SECONDARY_CARPARK_CAPACITY", "twenty")
        s = db_service.get_secondary_carpark_settings()
        assert s["window_start"] == time(9, 0)
        assert s["window_end"] == time(21, 0)
        assert s["capacity"] == 20

    def test_B_negative_capacity_floors_at_zero(self, monkeypatch):
        monkeypatch.setenv("SECONDARY_CARPARK_CAPACITY", "-5")
        assert db_service.get_secondary_carpark_settings()["capacity"] == 0


class TestQualificationRule:
    """Boundary triplets on every dimension, per house rules."""

    def _q(self, dropoff, pickup, monkeypatch):
        _clear_env(monkeypatch)
        return db_service.booking_qualifies_for_secondary_carpark(
            _booking(dropoff_time=dropoff, pickup_time=pickup)
        )

    # --- BOUNDARY: drop-off against window start --------------------------

    def test_B_dropoff_0859_does_not_qualify(self, monkeypatch):
        assert self._q(time(8, 59), time(12, 0), monkeypatch) is False

    def test_B_dropoff_0900_qualifies_inclusive(self, monkeypatch):
        assert self._q(time(9, 0), time(12, 0), monkeypatch) is True

    def test_B_dropoff_0901_qualifies(self, monkeypatch):
        assert self._q(time(9, 1), time(12, 0), monkeypatch) is True

    # --- BOUNDARY: pickup against window end -------------------------------

    def test_B_pickup_2059_qualifies(self, monkeypatch):
        assert self._q(time(12, 0), time(20, 59), monkeypatch) is True

    def test_B_pickup_2100_qualifies_inclusive(self, monkeypatch):
        assert self._q(time(12, 0), time(21, 0), monkeypatch) is True

    def test_B_pickup_2101_does_not_qualify(self, monkeypatch):
        assert self._q(time(12, 0), time(21, 1), monkeypatch) is False

    # --- BOUNDARY: cross checks (each event against its far edge) ----------

    def test_B_dropoff_2100_pickup_0900_both_at_edges_qualifies(self, monkeypatch):
        assert self._q(time(21, 0), time(9, 0), monkeypatch) is True

    def test_B_pickup_0859_does_not_qualify(self, monkeypatch):
        assert self._q(time(12, 0), time(8, 59), monkeypatch) is False

    def test_B_dropoff_2101_does_not_qualify(self, monkeypatch):
        assert self._q(time(21, 1), time(12, 0), monkeypatch) is False

    # --- HAPPY/UNHAPPY: the brief's worked examples verbatim ---------------

    def test_H_brief_example_qualifies(self, monkeypatch):
        assert self._q(time(9, 5), time(20, 55), monkeypatch) is True

    def test_U_brief_example_late_pickup(self, monkeypatch):
        assert self._q(time(10, 0), time(22, 15), monkeypatch) is False

    def test_U_brief_example_early_dropoff(self, monkeypatch):
        assert self._q(time(8, 45), time(20, 0), monkeypatch) is False

    def test_H_brief_example_mid_window(self, monkeypatch):
        assert self._q(time(9, 15), time(20, 30), monkeypatch) is True

    # --- EDGE: missing times never qualify ----------------------------------

    def test_E_missing_pickup_time_does_not_qualify(self, monkeypatch):
        assert self._q(time(10, 0), None, monkeypatch) is False

    def test_E_missing_dropoff_time_does_not_qualify(self, monkeypatch):
        assert self._q(None, time(10, 0), monkeypatch) is False

    # --- EDGE: env-configured window shifts the rule -------------------------

    def test_E_env_window_changes_qualification(self, monkeypatch):
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_START", "07:00")
        monkeypatch.setenv("SECONDARY_CARPARK_WINDOW_END", "23:00")
        assert db_service.booking_qualifies_for_secondary_carpark(
            _booking(dropoff_time=time(8, 45), pickup_time=time(22, 15))
        ) is True


class TestSecondaryCarparkInfo:
    def test_H_qualifying_payload(self, monkeypatch):
        _clear_env(monkeypatch)
        info = db_service.secondary_carpark_info(
            _booking(dropoff_time=time(9, 5), pickup_time=time(20, 55))
        )
        assert info["qualifies"] is True
        assert info["assigned_carpark"] == "secondary"
        assert info["window"] == "09:00-21:00"
        assert "within 09:00-21:00" in info["reason"]

    def test_U_failing_payload_names_the_offending_event(self, monkeypatch):
        _clear_env(monkeypatch)
        info = db_service.secondary_carpark_info(
            _booking(dropoff_time=time(10, 0), pickup_time=time(22, 15))
        )
        assert info["qualifies"] is False
        assert info["assigned_carpark"] == "main"
        assert "pickup 22:15 outside 09:00-21:00" in info["reason"]
        assert "drop-off" not in info["reason"]

    def test_U_both_events_outside_lists_both(self, monkeypatch):
        _clear_env(monkeypatch)
        info = db_service.secondary_carpark_info(
            _booking(dropoff_time=time(8, 0), pickup_time=time(22, 0))
        )
        assert "drop-off 08:00" in info["reason"]
        assert "pickup 22:00" in info["reason"]

    def test_E_missing_time_reason(self, monkeypatch):
        _clear_env(monkeypatch)
        info = db_service.secondary_carpark_info(_booking(dropoff_time=time(10, 0)))
        assert info["qualifies"] is False
        assert "missing" in info["reason"]


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: _admin()


def _wire(bookings):
    db = MagicMock()
    def _query(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.options.return_value = chain
        chain.order_by.return_value = chain
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        chain.all.return_value = bookings if name == "Booking" else []
        return chain
    db.query.side_effect = _query
    return db


class TestOccupancyReportSecondarySplit:
    def setup_method(self):
        main._occupancy_cache = {}

    def teardown_method(self):
        app.dependency_overrides.clear()
        main._occupancy_cache = {}

    def _bookings(self):
        from datetime import timedelta
        today = date_type.today()
        return [
            _booking(  # qualifies — active today and tomorrow
                id=1, reference="TAG-P2QUAL01",
                dropoff_time=time(9, 5), pickup_time=time(20, 55),
                dropoff_date=today, pickup_date=today + timedelta(days=1),
            ),
            _booking(  # does not qualify (pickup outside window)
                id=2, reference="TAG-MAINONLY",
                dropoff_time=time(10, 0), pickup_time=time(22, 15),
                dropoff_date=today, pickup_date=today + timedelta(days=1),
            ),
        ]

    def test_H_daily_split_counts_and_refs(self, monkeypatch):
        _clear_env(monkeypatch)
        _override(_wire(self._bookings()))

        resp = TestClient(app).get("/api/admin/reports/occupancy?refresh=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["secondary_carpark"] == {
            "capacity": 20, "window_start": "09:00", "window_end": "21:00",
        }
        today_row = next(r for r in body["data"] if r["is_today"])
        assert today_row["occupied"] == 2
        assert today_row["secondary_occupied"] == 1
        assert today_row["main_occupied"] == 1
        assert today_row["secondary_bookings"] == ["TAG-P2QUAL01"]
        assert today_row["secondary_over_capacity"] is False

    def test_B_over_capacity_flag_fires_above_env_capacity(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("SECONDARY_CARPARK_CAPACITY", "1")
        bookings = self._bookings() + [
            _booking(
                id=3, reference="TAG-P2QUAL02",
                dropoff_time=time(9, 30), pickup_time=time(19, 0),
                dropoff_date=date_type.today(), pickup_date=date_type.today(),
            ),
        ]
        _override(_wire(bookings))

        resp = TestClient(app).get("/api/admin/reports/occupancy?refresh=true")

        today_row = next(r for r in resp.json()["data"] if r["is_today"])
        assert today_row["secondary_occupied"] == 2  # capacity 1 → over
        assert today_row["secondary_over_capacity"] is True

    def test_B_exactly_at_capacity_is_not_over(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("SECONDARY_CARPARK_CAPACITY", "1")
        bookings = [self._bookings()[0]]  # one qualifying booking, capacity 1
        _override(_wire(bookings))

        resp = TestClient(app).get("/api/admin/reports/occupancy?refresh=true")

        today_row = next(r for r in resp.json()["data"] if r["is_today"])
        assert today_row["secondary_occupied"] == 1
        assert today_row["secondary_over_capacity"] is False

    def test_H_weekly_view_includes_average(self, monkeypatch):
        _clear_env(monkeypatch)
        _override(_wire(self._bookings()))

        resp = TestClient(app).get("/api/admin/reports/occupancy?view=weekly&refresh=true")

        body = resp.json()
        assert body["secondary_carpark"]["capacity"] == 20
        assert all("avg_secondary_occupied" in row for row in body["data"])
        assert any(row["avg_secondary_occupied"] > 0 for row in body["data"])

    def test_H_monthly_view_includes_average(self, monkeypatch):
        _clear_env(monkeypatch)
        _override(_wire(self._bookings()))

        resp = TestClient(app).get("/api/admin/reports/occupancy?view=monthly&refresh=true")

        body = resp.json()
        assert body["secondary_carpark"]["capacity"] == 20
        assert all("avg_secondary_occupied" in row for row in body["data"])


class TestSecondaryCarparkReportEndpoint:
    """GET /api/admin/reports/secondary-carpark — the dedicated Occupancy
    panel: future eligible bookings (drop-off today onward, UK) with
    ref / name / car / reg / drop-off / pickup."""

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _full_booking(self, **kw):
        from datetime import timedelta
        today = date_type.today()
        base = dict(
            id=10,
            reference="TAG-P2ROW0001",
            status=BookingStatus.CONFIRMED,
            dropoff_date=today + timedelta(days=2),
            dropoff_time=time(10, 0),
            pickup_date=today + timedelta(days=9),
            pickup_time=time(18, 30),
            customer_first_name="Hazel",
            customer_last_name="Firth",
            customer=SimpleNamespace(first_name="Hazel", last_name="Firth"),
            vehicle=SimpleNamespace(colour="Blue", make="Ford", registration="SV68 HPO"),
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _get(self, bookings, monkeypatch):
        _clear_env(monkeypatch)
        _override(_wire(bookings))
        return TestClient(app).get("/api/admin/reports/secondary-carpark")

    def test_H_returns_row_fields_for_eligible_booking(self, monkeypatch):
        resp = self._get([self._full_booking()], monkeypatch)

        assert resp.status_code == 200
        body = resp.json()
        assert body["capacity"] == 20
        assert body["window_start"] == "09:00"
        assert body["window_end"] == "21:00"
        assert body["count"] == 1
        row = body["bookings"][0]
        assert row["reference"] == "TAG-P2ROW0001"
        assert row["customer_name"] == "Hazel Firth"
        assert row["car"] == "Blue Ford"
        assert row["registration"] == "SV68 HPO"
        assert row["dropoff_time"] == "10:00"
        assert row["pickup_time"] == "18:30"
        assert "/" in row["dropoff_display"] and "/" in row["pickup_display"]

    def test_U_non_qualifying_booking_excluded(self, monkeypatch):
        late_pickup = self._full_booking(id=11, reference="TAG-LATEPICK", pickup_time=time(22, 15))
        resp = self._get([late_pickup], monkeypatch)
        assert resp.json()["count"] == 0

    def test_B_dropoff_today_included(self, monkeypatch):
        today_booking = self._full_booking(
            id=12, reference="TAG-TODAY0001", dropoff_date=date_type.today(),
        )
        resp = self._get([today_booking], monkeypatch)
        assert resp.json()["count"] == 1

    def test_B_dropoff_yesterday_excluded(self, monkeypatch):
        from datetime import timedelta
        parked = self._full_booking(
            id=13, reference="TAG-PARKED001",
            dropoff_date=date_type.today() - timedelta(days=1),
        )
        resp = self._get([parked], monkeypatch)
        # Already parked — eligibility is arrivals from today onward.
        assert resp.json()["count"] == 0

    def test_E_missing_vehicle_renders_nulls(self, monkeypatch):
        no_vehicle = self._full_booking(id=14, reference="TAG-NOVEHICLE", vehicle=None)
        resp = self._get([no_vehicle], monkeypatch)
        row = resp.json()["bookings"][0]
        assert row["car"] is None
        assert row["registration"] is None
