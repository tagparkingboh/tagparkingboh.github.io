"""
HUEB tests for /api/address/postcode-lookup + /api/employee/* endpoints.

  POST /api/address/postcode-lookup
  GET  /api/employee/bookings
  POST /api/employee/inspections
  GET  /api/employee/inspections/{booking_id}
  POST /api/employee/inspections/status
  PUT  /api/employee/inspections/{id}
  POST /api/employee/bookings/{id}/complete
  POST /api/employee/bookings/{id}/decline-inspection
  POST /api/employee/bookings/{id}/undecline-inspection
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
from main import app, get_current_user
from database import get_db


def _employee():
    return SimpleNamespace(id=1, email="emp@tag.test", is_admin=False)


def _override_employee(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[get_current_user] = lambda: user or _employee()


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/address/postcode-lookup
# ============================================================================

def _patch_ideal(monkeypatch, json_body=None, status=200, raise_exc=None):
    client = MagicMock()
    if raise_exc:
        client.get = AsyncMock(side_effect=raise_exc)
    else:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = json_body or {"result": []}
        client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", MagicMock(return_value=cm))


class TestPostcodeLookup:
    def teardown_method(self):
        _clear()

    def _settings(self, key="ideal-key"):
        return SimpleNamespace(os_places_api_key=key)

    def test_H_returns_addresses(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _patch_ideal(monkeypatch, json_body={"result": [{
            "udprn": 12345,
            "line_1": "1 High St", "line_2": "", "line_3": "",
            "post_town": "Bournemouth", "postcode": "BH1 1AA",
            "building_number": "1", "thoroughfare": "High St",
        }]})
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["addresses"]) == 1
        assert body["addresses"][0]["county"] == "Dorset"

    def test_U_empty_postcode(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": ""})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "enter a postcode" in resp.json()["error"].lower()

    def test_U_invalid_format(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "AB"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "invalid postcode" in resp.json()["error"].lower()

    def test_U_no_api_key(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings(key=""))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 503

    def test_U_404_postcode_not_found(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        _patch_ideal(monkeypatch, status=404)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH99 9XX"})
        assert resp.status_code == 200
        assert "not found" in resp.json()["error"].lower()

    def test_U_402_payment_required(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_ideal(monkeypatch, status=402)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        assert "temporarily unavailable" in resp.json()["error"].lower()

    def test_U_401_auth_failed(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_ideal(monkeypatch, status=401)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        assert "authentication failed" in resp.json()["error"].lower()

    def test_U_500_logs_error(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_ideal(monkeypatch, status=500)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        assert "500" in resp.json()["error"]

    def test_U_timeout(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_ideal(monkeypatch, raise_exc=httpx.TimeoutException("timed out"))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        assert "timeout" in resp.json()["error"].lower()

    def test_U_generic_exception(self, monkeypatch):
        monkeypatch.setattr(main, "get_settings", lambda: self._settings())
        monkeypatch.setattr(main, "log_error", lambda **kw: None)
        _patch_ideal(monkeypatch, raise_exc=RuntimeError("boom"))
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/address/postcode-lookup",
                                     json={"postcode": "BH1 1AA"})
        assert resp.status_code == 200
        assert "unable to lookup" in resp.json()["error"].lower()


# ============================================================================
# GET /api/employee/bookings
# ============================================================================

class TestEmployeeBookings:
    def teardown_method(self):
        _clear()

    def _wire(self, bookings):
        db = MagicMock()
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = bookings
        db.query.return_value = chain
        return db

    def _booking(self, **kw):
        from db_models import BookingStatus
        cust = SimpleNamespace(first_name="Jo", last_name="K", phone="07111")
        veh = SimpleNamespace(registration="AB12CDE", make="Ford",
                              model="Focus", colour="Blue")
        base = dict(
            id=1, reference="TAG-1",
            status=BookingStatus.CONFIRMED,
            customer=cust,
            customer_first_name="Jo", customer_last_name="K",
            vehicle=veh,
            dropoff_date=date_type(2026, 6, 1),
            dropoff_time=time(10, 0),
            pickup_date=date_type(2026, 6, 8),
            pickup_time=time(11, 30),
            flight_arrival_time=time(15, 0),
            flight_departure_time=time(12, 0),
            dropoff_flight_number="TOM1",
            dropoff_airline_name="TUI",
            dropoff_destination="Tenerife",
            pickup_flight_number="TOM2",
            pickup_airline_name="TUI",
            pickup_origin="Tenerife",
            notes="",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_H_returns_bookings(self):
        _override_employee(self._wire([self._booking()]))
        resp = TestClient(app).get("/api/employee/bookings")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_H_include_cancelled(self):
        _override_employee(self._wire([self._booking()]))
        resp = TestClient(app).get("/api/employee/bookings?include_cancelled=true")
        assert resp.status_code == 200

    def test_E_empty(self):
        _override_employee(self._wire([]))
        resp = TestClient(app).get("/api/employee/bookings")
        assert resp.json()["count"] == 0


# ============================================================================
# POST + GET /api/employee/inspections
# ============================================================================

class TestEmployeeInspections:
    def teardown_method(self):
        _clear()

    def _wire(self, booking=None, existing=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "VehicleInspection":
                chain.first.return_value = existing
                chain.all.return_value = []
            return chain
        db.query.side_effect = _query
        added = []
        def _add(obj):
            obj.id = 1
            obj.created_at = datetime(2026, 5, 1)
            obj.updated_at = None
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_create_dropoff_inspection(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        _override_employee(self._wire(booking=b))
        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1, "inspection_type": "dropoff",
            "notes": "All good", "mileage": 50000,
        })
        assert resp.status_code == 200

    def test_U_invalid_type(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        _override_employee(self._wire(booking=b))
        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1, "inspection_type": "bogus",
        })
        assert resp.status_code == 400

    def test_U_booking_not_found(self):
        _override_employee(self._wire(booking=None))
        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 9999, "inspection_type": "dropoff",
        })
        assert resp.status_code == 404

    def test_U_already_exists(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        existing = SimpleNamespace(id=99)
        _override_employee(self._wire(booking=b, existing=existing))
        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1, "inspection_type": "dropoff",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_U_invalid_signed_date(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        _override_employee(self._wire(booking=b))
        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1, "inspection_type": "dropoff",
            "signed_date": "bogus",
        })
        assert resp.status_code == 400


class TestEmployeeGetInspections:
    def teardown_method(self):
        _clear()

    def test_H_returns_list(self):
        from db_models import InspectionType
        insp = SimpleNamespace(
            id=1, booking_id=1, inspection_type=InspectionType.DROPOFF,
            notes="x", photos=None, customer_name="Jo",
            signed_date=None, signature=None,
            vehicle_inspection_read=True, acknowledgement_confirmed=False,
            declined=False, accepted=None, mileage=50000,
            inspector_id=1,
            created_at=datetime(2026, 5, 1), updated_at=None,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [insp]
        _override_employee(db)
        resp = TestClient(app).get("/api/employee/inspections/1")
        assert resp.status_code == 200
        assert len(resp.json()["inspections"]) == 1


class TestEmployeeInspectionsStatus:
    def teardown_method(self):
        _clear()

    def test_H_returns_status_for_bookings(self):
        from db_models import InspectionType
        insp = SimpleNamespace(
            id=1, booking_id=5,
            inspection_type=InspectionType.DROPOFF,
            declined=False, mileage=50000,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [insp]
        _override_employee(db)
        resp = TestClient(app).post("/api/employee/inspections/status",
                                     json={"booking_ids": [5, 6, 7]})
        assert resp.status_code == 200
        body = resp.json()
        # 5 gets one inspection, 6 + 7 get []
        assert body["inspections"]["5"] == [{
            "id": 1, "booking_id": 5, "inspection_type": "dropoff",
            "declined": False, "mileage": 50000,
        }]
        assert body["inspections"]["6"] == []

    def test_E_empty_booking_ids(self):
        _override_employee(MagicMock())
        resp = TestClient(app).post("/api/employee/inspections/status",
                                     json={"booking_ids": []})
        assert resp.status_code == 200
        assert resp.json()["inspections"] == {}


class TestUpdateInspection:
    def teardown_method(self):
        _clear()

    def _wire(self, insp):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = insp
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_updates_notes(self):
        from db_models import InspectionType
        insp = SimpleNamespace(
            id=1, booking_id=1, inspection_type=InspectionType.DROPOFF,
            notes=None, photos=None, customer_name=None,
            signed_date=None, signature=None,
            vehicle_inspection_read=False, acknowledgement_confirmed=False,
            declined=False, accepted=None, mileage=None,
            inspector_id=1, created_at=datetime(2026, 5, 1), updated_at=None,
        )
        _override_employee(self._wire(insp))
        resp = TestClient(app).put("/api/employee/inspections/1",
                                    json={"notes": "Updated"})
        assert resp.status_code == 200
        assert insp.notes == "Updated"

    def test_U_not_found(self):
        _override_employee(self._wire(None))
        resp = TestClient(app).put("/api/employee/inspections/9999",
                                    json={"notes": "x"})
        assert resp.status_code == 404

    def test_U_invalid_signed_date(self):
        from db_models import InspectionType
        insp = SimpleNamespace(
            id=1, booking_id=1, inspection_type=InspectionType.DROPOFF,
            notes=None, photos=None, customer_name=None,
            signed_date=None, signature=None,
            vehicle_inspection_read=False, acknowledgement_confirmed=False,
            declined=False, accepted=None, mileage=None,
            inspector_id=1, created_at=datetime(2026, 5, 1), updated_at=None,
        )
        _override_employee(self._wire(insp))
        resp = TestClient(app).put("/api/employee/inspections/1",
                                    json={"signed_date": "bogus"})
        assert resp.status_code == 400


# ============================================================================
# POST /api/employee/bookings/{id}/complete + decline/undecline
# ============================================================================

class TestEmployeeBookingComplete:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = booking
        db.commit = MagicMock()
        return db

    def test_H_completes_confirmed(self):
        from db_models import BookingStatus
        b = SimpleNamespace(id=1, reference="TAG-1",
                            status=BookingStatus.CONFIRMED,
                            completed_at=None)
        _override_employee(self._wire(b))
        resp = TestClient(app).post("/api/employee/bookings/1/complete")
        assert resp.status_code == 200
        assert b.status == BookingStatus.COMPLETED
        assert b.completed_at is not None

    def test_H_completes_refunded(self):
        from db_models import BookingStatus
        b = SimpleNamespace(id=1, reference="TAG-1",
                            status=BookingStatus.REFUNDED,
                            completed_at=None)
        _override_employee(self._wire(b))
        resp = TestClient(app).post("/api/employee/bookings/1/complete")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override_employee(self._wire(None))
        resp = TestClient(app).post("/api/employee/bookings/9999/complete")
        assert resp.status_code == 404

    def test_U_pending_cannot_complete(self):
        from db_models import BookingStatus
        b = SimpleNamespace(id=1, reference="TAG-1",
                            status=BookingStatus.PENDING)
        _override_employee(self._wire(b))
        resp = TestClient(app).post("/api/employee/bookings/1/complete")
        assert resp.status_code == 400


class TestDeclineInspection:
    def teardown_method(self):
        _clear()

    def _wire(self, booking, existing=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "VehicleInspection":
                chain.first.return_value = existing
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_decline_creates_new_inspection(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        _override_employee(self._wire(b))
        resp = TestClient(app).post("/api/employee/bookings/1/decline-inspection")
        assert resp.status_code == 200

    def test_H_decline_updates_existing(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        existing = SimpleNamespace(declined=False)
        _override_employee(self._wire(b, existing=existing))
        resp = TestClient(app).post("/api/employee/bookings/1/decline-inspection")
        assert resp.status_code == 200
        assert existing.declined is True

    def test_U_not_found(self):
        _override_employee(self._wire(None))
        resp = TestClient(app).post("/api/employee/bookings/9999/decline-inspection")
        assert resp.status_code == 404

    def test_H_undecline_deletes_empty(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        existing = SimpleNamespace(declined=True, notes=None, photos=None,
                                    signature=None)
        db = self._wire(b, existing=existing)
        _override_employee(db)
        resp = TestClient(app).post("/api/employee/bookings/1/undecline-inspection")
        assert resp.status_code == 200
        assert db.delete.called

    def test_H_undecline_keeps_if_has_data(self):
        b = SimpleNamespace(id=1, reference="TAG-1")
        existing = SimpleNamespace(declined=True, notes="customer comments",
                                    photos=None, signature=None)
        db = self._wire(b, existing=existing)
        _override_employee(db)
        resp = TestClient(app).post("/api/employee/bookings/1/undecline-inspection")
        assert resp.status_code == 200
        assert existing.declined is False
        assert not db.delete.called

    def test_U_undecline_not_found(self):
        _override_employee(self._wire(None))
        resp = TestClient(app).post("/api/employee/bookings/9999/undecline-inspection")
        assert resp.status_code == 404
