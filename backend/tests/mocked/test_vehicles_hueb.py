"""
HUEB tests for public-facing vehicle endpoints in main.py.

  POST  /api/vehicles            (create_or_update_vehicle)
  PATCH /api/vehicles/{id}       (update_vehicle)
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
from main import app
from database import get_db


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/vehicles — create or update
# ============================================================================

class TestCreateOrUpdateVehicle:
    def teardown_method(self):
        _clear()

    _payload = dict(
        customer_id=42, registration="ab 12 cde",
        make="Ford", colour="Blue",
    )

    def test_H_creates_new_vehicle(self, monkeypatch):
        customer = SimpleNamespace(id=42)
        vehicle = SimpleNamespace(id=99)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: customer)
        monkeypatch.setattr("db_service.create_vehicle",
                            lambda **kw: (vehicle, True))
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/vehicles", json=self._payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["vehicle_id"] == 99
        assert body["is_new_vehicle"] is True

    def test_H_updates_existing(self, monkeypatch):
        customer = SimpleNamespace(id=42)
        vehicle = SimpleNamespace(id=99)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: customer)
        monkeypatch.setattr("db_service.create_vehicle",
                            lambda **kw: (vehicle, False))
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/vehicles", json=self._payload)
        assert resp.status_code == 200
        assert resp.json()["is_new_vehicle"] is False

    def test_U_customer_not_found(self, monkeypatch):
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: None)
        _override(MagicMock())
        resp = TestClient(app).post("/api/vehicles", json=self._payload)
        assert resp.status_code == 404

    def test_U_db_exception_returns_400(self, monkeypatch):
        customer = SimpleNamespace(id=42)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: customer)
        def boom(**kw):
            raise RuntimeError("DB integrity error")
        monkeypatch.setattr("db_service.create_vehicle", boom)
        _override(MagicMock())
        resp = TestClient(app).post("/api/vehicles", json=self._payload)
        assert resp.status_code == 400


# ============================================================================
# PATCH /api/vehicles/{id} — update_vehicle
# ============================================================================

class TestUpdateVehicle:
    def teardown_method(self):
        _clear()

    _payload = dict(
        customer_id=42, registration="ab 12 cde",
        make="Ford", colour="Blue",
    )

    def _wire(self, vehicle):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = vehicle
        db.query.return_value = chain
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_updates(self, monkeypatch):
        v = SimpleNamespace(id=99, registration="OLD", make="Ford",
                            model=None, colour="Blue",
                            tax_status=None, mot_status=None,
                            tax_due_date=None, mot_expiry_date=None,
                            dvla_checked_at=None, dvla_retry_count=0)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(self._wire(v))
        resp = TestClient(app).patch("/api/vehicles/99", json=self._payload)
        assert resp.status_code == 200
        assert v.registration == "AB 12 CDE"  # uppercased (handler doesn't strip spaces)
        assert v.make == "Ford"

    def test_H_with_dvla_data_sets_checked_at(self, monkeypatch):
        v = SimpleNamespace(id=99, registration="OLD", make="Ford",
                            model=None, colour="Blue",
                            tax_status=None, mot_status=None,
                            tax_due_date=None, mot_expiry_date=None,
                            dvla_checked_at=None, dvla_retry_count=5)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(self._wire(v))
        payload = dict(self._payload, tax_status="Taxed", mot_status="Valid")
        resp = TestClient(app).patch("/api/vehicles/99", json=payload)
        assert resp.status_code == 200
        assert v.dvla_checked_at is not None
        assert v.dvla_retry_count == 0

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).patch("/api/vehicles/9999", json=self._payload)
        assert resp.status_code == 404

    def test_U_db_exception_returns_400(self, monkeypatch):
        v = SimpleNamespace(id=99, registration="OLD", make="Ford",
                            model=None, colour="Blue",
                            tax_status=None, mot_status=None,
                            tax_due_date=None, mot_expiry_date=None,
                            dvla_checked_at=None, dvla_retry_count=0)
        db = self._wire(v)
        db.commit.side_effect = RuntimeError("constraint fail")
        _override(db)
        resp = TestClient(app).patch("/api/vehicles/99", json=self._payload)
        assert resp.status_code == 400
