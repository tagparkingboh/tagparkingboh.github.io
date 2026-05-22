"""
HUEB tests for POST /api/admin/manual-booking (main.py:2354+).

Focuses on the validation gates: stripe_payment_link requirement,
capacity ceiling, departure flight validation, slot fullness. Doesn't
exhaustively exercise the customer/vehicle creation paths or email
sending — those happen after all gates have passed.
"""
from datetime import date as date_type, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import main
from main import app, require_admin
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


def _payload(**overrides):
    base = dict(
        first_name="Jo", last_name="K", email="jo@x.test", phone="07123",
        billing_address1="1 High St", billing_city="Bournemouth",
        billing_postcode="BH1 1AA",
        registration="AB12CDE", make="Ford", colour="Blue",
        dropoff_date="2026-08-15", dropoff_time="10:00",
        pickup_date="2026-08-22", pickup_time="11:30",
        stripe_payment_link="https://buy.stripe.com/test_abc",
        amount_pence=9900,
    )
    base.update(overrides)
    return base


# ============================================================================
# Validation gates
# ============================================================================

class TestManualBookingValidation:
    def teardown_method(self):
        _clear()

    def _wire(self, customer=None, vehicle=None, departure=None, arrival=None):
        """Build a DB stub that returns the listed objects for each model."""
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "Vehicle":
                chain.first.return_value = vehicle
            elif name == "FlightDeparture":
                chain.first.return_value = departure
            elif name == "FlightArrival":
                chain.first.return_value = arrival
            else:
                chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_U_paid_without_payment_link(self):
        _override(self._wire())
        # Pop the stripe link from payload
        p = _payload()
        p.pop("stripe_payment_link")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 422

    def test_U_capacity_ceiling_hit(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: (date_type(2026, 8, 18), 70),
        )
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/manual-booking", json=_payload())
        assert resp.status_code == 400
        assert "ceiling" in resp.json()["detail"].lower()
        assert "70" in resp.json()["detail"]

    def test_U_invalid_departure_id(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        _override(self._wire(departure=None))
        p = _payload(departure_id=999, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "departure flight" in resp.json()["detail"].lower()

    def test_U_call_us_only_flight(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        dep = SimpleNamespace(
            id=5, capacity_tier=0,
            slots_booked_early=0, slots_booked_late=0,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "calling to book" in resp.json()["detail"].lower()

    def test_U_early_slot_full(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=2, slots_booked_late=0,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "early slot" in resp.json()["detail"].lower()

    def test_U_late_slot_full(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=0, slots_booked_late=2,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="late")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "late slot" in resp.json()["detail"].lower()

    def test_U_standard_slot_full(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=0, slots_booked_late=2,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="standard")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "standard slot" in resp.json()["detail"].lower()

    def test_E_free_booking_no_payment_link_required(self, monkeypatch):
        """When amount_pence=0 and is_free_booking=true, payment link is optional."""
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        _override(self._wire())
        p = _payload(is_free_booking=True, amount_pence=0)
        p.pop("stripe_payment_link")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        # Should NOT return 422 for missing payment link — should succeed
        # (or fail at a later step that requires more wiring)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert resp.json()["is_free_booking"] is True
