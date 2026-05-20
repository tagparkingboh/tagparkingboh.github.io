"""
HUEB tests for booking-flow helper endpoints in main.py.

  POST /api/booking/validate-flight-time
  GET  /api/booking/airlines
  GET  /api/booking/destinations
  POST /api/booking/audit-event
  POST /api/customers
  PATCH /api/customers/{id}
  GET  /api/customers/heard-about-us-status
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import main
from main import app
from database import get_db


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/booking/validate-flight-time
# ============================================================================

class TestValidateFlightTime:
    def teardown_method(self):
        _clear()

    def test_H_valid_departure_time(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/validate-flight-time",
                                     json={"time": "10:30", "flight_type": "departure"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_H_valid_arrival_time(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/validate-flight-time",
                                     json={"time": "15:45", "flight_type": "arrival"})
        assert resp.status_code == 200

    def test_U_invalid_format(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/validate-flight-time",
                                     json={"time": "bogus", "flight_type": "departure"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_U_invalid_flight_type(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/validate-flight-time",
                                     json={"time": "10:30", "flight_type": "bogus"})
        assert resp.status_code == 200
        # validate_flight_time probably returns False for unknown type


# ============================================================================
# GET /api/booking/airlines
# ============================================================================

class TestAirlines:
    def teardown_method(self):
        _clear()

    def test_H_returns_airline_list(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/booking/airlines")
        assert resp.status_code == 200
        airlines = resp.json()["airlines"]
        assert len(airlines) > 0
        # Ryanair, easyJet, etc.
        codes = [a["code"] for a in airlines]
        assert "FR" in codes
        assert "U2" in codes


# ============================================================================
# GET /api/booking/destinations
# ============================================================================

class TestDestinations:
    def teardown_method(self):
        _clear()

    def test_H_returns_destinations(self):
        db = MagicMock()
        chain = MagicMock()
        chain.distinct.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = [("TFS", "Tenerife"), ("AGP", "Malaga"), (None, None)]
        db.query.return_value = chain
        _override(db)
        resp = TestClient(app).get("/api/booking/destinations")
        assert resp.status_code == 200
        body = resp.json()
        # (None, None) filtered out
        assert len(body["destinations"]) == 2


# ============================================================================
# POST /api/booking/audit-event
# ============================================================================

class TestAuditEvent:
    def teardown_method(self):
        _clear()

    def test_H_logs_event(self, monkeypatch):
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/audit-event", json={
            "session_id": "sess-123", "event": "tnc_accepted",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_H_with_booking_reference_and_data(self, monkeypatch):
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/audit-event", json={
            "session_id": "sess-123", "event": "promo_code_added",
            "booking_reference": "TAG-1", "event_data": {"code": "TAG10"},
        })
        assert resp.status_code == 200

    def test_U_unknown_event(self):
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/audit-event", json={
            "session_id": "sess-123", "event": "bogus_event",
        })
        assert resp.status_code == 400
        assert "unknown event" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("event", [
        "dates_selected", "flight_selected", "tnc_accepted", "tnc_unchecked",
        "promo_code_added", "promo_code_removed", "checkout_loaded",
        "stripe_form_ready", "stripe_form_error", "payment_processing",
        "payment_initiated", "payment_succeeded", "payment_failed",
        "payment_requires_action",
    ])
    def test_H_each_event_type_accepted(self, monkeypatch, event):
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/booking/audit-event", json={
            "session_id": "sess-1", "event": event,
        })
        assert resp.status_code == 200


# ============================================================================
# POST /api/customers + PATCH /api/customers/{id}
# ============================================================================

class TestCreateOrUpdateCustomer:
    def teardown_method(self):
        _clear()

    def test_H_creates_new_customer(self, monkeypatch):
        new_customer = SimpleNamespace(id=42)
        monkeypatch.setattr("db_service.create_customer",
                            lambda **kw: (new_customer, True))
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/customers", json={
            "first_name": "Jo", "last_name": "K",
            "email": "jo@x.test", "phone": "07123",
        })
        assert resp.status_code == 200
        assert resp.json()["customer_id"] == 42
        assert resp.json()["is_new_customer"] is True

    def test_H_updates_existing(self, monkeypatch):
        existing = SimpleNamespace(id=42)
        monkeypatch.setattr("db_service.create_customer",
                            lambda **kw: (existing, False))
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/customers", json={
            "first_name": "Jo", "last_name": "K",
            "email": "jo@x.test", "phone": "07123",
        })
        assert resp.json()["is_new_customer"] is False

    def test_U_exception_returns_400(self, monkeypatch):
        def boom(**kw):
            raise RuntimeError("DB integrity")
        monkeypatch.setattr("db_service.create_customer", boom)
        _override(MagicMock())
        resp = TestClient(app).post("/api/customers", json={
            "first_name": "Jo", "last_name": "K",
            "email": "jo@x.test", "phone": "07123",
        })
        assert resp.status_code == 400


class TestPatchCustomer:
    def teardown_method(self):
        _clear()

    def test_H_updates_customer(self, monkeypatch):
        customer = SimpleNamespace(id=42, first_name="Jo", last_name="K",
                                    email="jo@x.test", phone="07123")
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: customer)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).patch("/api/customers/42", json={
            "first_name": "Jane", "last_name": "Doe",
            "email": "jane@x.test", "phone": "07999",
        })
        assert resp.status_code == 200
        assert customer.first_name == "Jane"

    def test_U_not_found(self, monkeypatch):
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: None)
        _override(MagicMock())
        resp = TestClient(app).patch("/api/customers/9999", json={
            "first_name": "Jo", "last_name": "K",
            "email": "jo@x.test", "phone": "07123",
        })
        assert resp.status_code == 404


# ============================================================================
# GET /api/customers/heard-about-us-status
# ============================================================================

class TestHeardAboutUsStatus:
    def teardown_method(self):
        _clear()

    def test_H_existing_customer_already_answered(self):
        c = SimpleNamespace(id=42, has_answered_heard_about_us=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = c
        _override(db)
        resp = TestClient(app).get("/api/customers/heard-about-us-status?email=jo@x.test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["customer_id"] == 42
        assert body["has_answered_heard_about_us"] is True
        assert body["show_heard_about_us"] is False

    def test_H_existing_customer_not_answered(self):
        c = SimpleNamespace(id=42, has_answered_heard_about_us=False)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = c
        _override(db)
        resp = TestClient(app).get("/api/customers/heard-about-us-status?email=jo@x.test")
        assert resp.json()["show_heard_about_us"] is True

    def test_E_new_customer(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        _override(db)
        resp = TestClient(app).get("/api/customers/heard-about-us-status?email=new@x.test")
        assert resp.json()["customer_id"] is None
        assert resp.json()["show_heard_about_us"] is True

    def test_U_missing_email(self):
        _override(MagicMock())
        resp = TestClient(app).get("/api/customers/heard-about-us-status")
        assert resp.status_code == 422
