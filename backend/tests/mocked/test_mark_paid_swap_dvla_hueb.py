"""
HUEB tests for: /api/admin/bookings/{id}/mark-paid, swap-vehicle, and
/api/vehicles/dvla-lookup.
"""
from datetime import date as date_type, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
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


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/admin/bookings/{id}/mark-paid
# ============================================================================

def _booking(**kw):
    from db_models import BookingStatus, PaymentStatus
    base = dict(
        id=99, reference="TAG-1",
        status=BookingStatus.PENDING,
        customer=SimpleNamespace(id=1, email="jo@x.test",
                                  first_name="Jo", last_name="K"),
        customer_first_name="Jo", customer_last_name="K",
        vehicle=SimpleNamespace(registration="AB12CDE", make="Ford",
                                 model="Focus", colour="Blue"),
        payment=SimpleNamespace(amount_pence=9900, status=PaymentStatus.PENDING,
                                 paid_at=None, stripe_payment_intent_id="pi_1"),
        departure_id=None, dropoff_slot=None,
        dropoff_date=date_type(2026, 6, 1),
        pickup_date=date_type(2026, 6, 8),
        dropoff_time=time(10, 0), pickup_time=time(11, 30),
        flight_arrival_time=time(15, 0), flight_departure_time=time(12, 0),
        dropoff_destination="Tenerife",
        dropoff_airline_name="TUI Airways", dropoff_flight_number="TOM1234",
        pickup_origin="Tenerife", pickup_airline_name="TUI Airways",
        pickup_flight_number="TOM1235",
        package="longer", created_at=datetime(2026, 5, 1),
        confirmation_email_sent=False, confirmation_email_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestMarkBookingPaid:
    def teardown_method(self):
        _clear()

    def _wire(self, booking, payment=None, departure=None, subscriber=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "Payment":
                chain.first.return_value = payment
            elif name == "FlightDeparture":
                chain.first.return_value = departure
            elif name == "MarketingSubscriber":
                chain.first.return_value = subscriber
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        return db

    def test_H_marks_paid(self, monkeypatch):
        b = _booking()
        p = b.payment
        monkeypatch.setattr(main, "send_booking_confirmation_email", lambda **kw: True)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            lambda *a, **kw: None)
        _override(self._wire(b, payment=p))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 200
        from db_models import BookingStatus
        assert b.status == BookingStatus.CONFIRMED

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/mark-paid")
        assert resp.status_code == 404

    def test_U_already_confirmed(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CONFIRMED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 400

    def test_U_cancelled_cannot_confirm(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 400

    def test_U_refunded_cannot_confirm(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.REFUNDED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 400

    def test_U_slot_full_blocks(self, monkeypatch):
        b = _booking(departure_id=5, dropoff_slot="150")
        dep = SimpleNamespace(id=5, capacity_tier=4,
                              slots_booked_early=2, slots_booked_late=0)
        monkeypatch.setattr(main, "send_booking_confirmation_email", lambda **kw: True)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        monkeypatch.setattr("roster_planner_runner.auto_link_booking_async",
                            lambda *a, **kw: None)
        _override(self._wire(b, departure=dep))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/mark-paid")
        assert resp.status_code == 400
        assert "fully booked" in resp.json()["detail"].lower()


# ============================================================================
# PUT /api/admin/bookings/{id}/swap-vehicle
# ============================================================================

class TestSwapVehicle:
    def teardown_method(self):
        _clear()

    def _wire(self, booking, new_vehicle, old_vehicle=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "Vehicle":
                # First call returns new_vehicle, second call returns old_vehicle
                if calls["n"] == 2:
                    chain.first.return_value = new_vehicle
                else:
                    chain.first.return_value = old_vehicle
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_swaps(self):
        b = _booking()
        b.customer_id = 1
        b.vehicle_id = 21
        new_v = SimpleNamespace(id=22, customer_id=1, registration="XY12ZAB",
                                 make="Honda", model="Civic", colour="Red")
        old_v = SimpleNamespace(id=21, registration="AB12CDE")
        _override(self._wire(b, new_v, old_v))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}/swap-vehicle",
                                    json={"vehicle_id": 22})
        assert resp.status_code == 200
        body = resp.json()
        assert body["new_vehicle"]["id"] == 22
        assert body["old_vehicle"]["registration"] == "AB12CDE"

    def test_U_booking_not_found(self):
        _override(self._wire(None, None))
        resp = TestClient(app).put("/api/admin/bookings/9999/swap-vehicle",
                                    json={"vehicle_id": 22})
        assert resp.status_code == 404

    def test_U_vehicle_not_found(self):
        b = _booking()
        b.customer_id = 1
        _override(self._wire(b, None))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}/swap-vehicle",
                                    json={"vehicle_id": 22})
        assert resp.status_code == 404

    def test_U_vehicle_other_customer(self):
        b = _booking()
        b.customer_id = 1
        new_v = SimpleNamespace(id=22, customer_id=99, registration="XY12ZAB",
                                 make="Honda", model="Civic", colour="Red")
        _override(self._wire(b, new_v))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}/swap-vehicle",
                                    json={"vehicle_id": 22})
        assert resp.status_code == 400
        assert "this customer" in resp.json()["detail"].lower()

    def test_U_same_vehicle(self):
        b = _booking()
        b.customer_id = 1
        b.vehicle_id = 22
        new_v = SimpleNamespace(id=22, customer_id=1, registration="XY12ZAB",
                                 make="Honda", model="Civic", colour="Red")
        _override(self._wire(b, new_v))
        resp = TestClient(app).put(f"/api/admin/bookings/{b.id}/swap-vehicle",
                                    json={"vehicle_id": 22})
        assert resp.status_code == 400
        assert "already has" in resp.json()["detail"].lower()


# ============================================================================
# POST /api/vehicles/dvla-lookup
# ============================================================================

def _patch_dvla(monkeypatch, json_body=None, status=200, raise_exc=None):
    client = MagicMock()
    if raise_exc:
        client.post = AsyncMock(side_effect=raise_exc)
    else:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = json_body or {}
        client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", MagicMock(return_value=cm))


class TestDvlaLookup:
    def teardown_method(self):
        _clear()

    def _settings(self, env="staging", test_key="key", prod_key=""):
        return SimpleNamespace(
            environment=env, dvla_api_key_test=test_key, dvla_api_key_prod=prod_key,
        )

    def test_H_returns_data(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _patch_dvla(monkeypatch, json_body={
            "make": "FORD", "colour": "BLUE",
            "taxStatus": "Taxed", "motStatus": "Valid",
            "taxDueDate": "2026-12-01", "motExpiryDate": "2026-11-15",
        })
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "ab 12 cde"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["registration"] == "AB12CDE"
        assert body["make"] == "FORD"

    def test_U_invalid_registration(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "!@#$%"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_U_no_api_key(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings",
                            lambda: self._settings(test_key=""))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 503

    def test_U_dvla_404(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _patch_dvla(monkeypatch, status=404)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error"] == "Vehicle not found"

    def test_U_dvla_400(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _patch_dvla(monkeypatch, status=400)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        assert resp.json()["error"] == "Invalid registration format"

    def test_U_dvla_403_access_denied(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_dvla(monkeypatch, status=403)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        assert "denied" in resp.json()["error"].lower()

    def test_U_dvla_500_logs_error(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_dvla(monkeypatch, status=500)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        assert "500" in resp.json()["error"]

    def test_U_timeout(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_dvla(monkeypatch, raise_exc=httpx.TimeoutException("timed out"))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        assert "timeout" in resp.json()["error"].lower()

    def test_U_generic_exception(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_dvla(monkeypatch, raise_exc=RuntimeError("boom"))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        assert "unable to lookup" in resp.json()["error"].lower()

    def test_E_production_uses_prod_url_and_key(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(main, "get_settings",
                            lambda: self._settings(env="production", prod_key="prod-key"))
        client = MagicMock()
        async def fake_post(url, **kw):
            captured["url"] = url
            captured["headers"] = kw.get("headers", {})
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"make": "F", "colour": "B",
                                       "taxStatus": "Taxed", "motStatus": "Valid",
                                       "taxDueDate": None, "motExpiryDate": None}
            return resp
        client.post = fake_post
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("main.httpx.AsyncClient", MagicMock(return_value=cm))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/vehicles/dvla-lookup",
                                     json={"registration": "AB12CDE"})
        assert resp.status_code == 200
        # Production URL hits the live driver-vehicle-licensing endpoint
        assert "driver-vehicle-licensing.api.gov.uk" in captured["url"]
        # UAT path NOT used
        assert "uat" not in captured["url"]
        assert captured["headers"].get("x-api-key") == "prod-key"
