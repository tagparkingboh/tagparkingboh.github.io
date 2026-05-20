"""
HUEB tests for SMS webhook endpoints + admin/sms/stats.

  POST /api/webhooks/sms/incoming (+ /)
  POST /api/webhooks/sms/delivery-report (+ /)
  GET  /api/admin/sms/stats
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
from main import app, require_admin
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _override_admin(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/webhooks/sms/incoming
# ============================================================================

class TestSmsIncomingWebhook:
    def teardown_method(self):
        _clear()

    def test_H_handles_incoming(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_incoming_sms",
                            lambda payload, db: True)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/incoming", json={
            "from": "07111", "content": "Hello", "messageid": "in-1",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_E_handler_returns_false(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_incoming_sms",
                            lambda payload, db: False)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/incoming", json={
            "content": "no sender",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_E_trailing_slash(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_incoming_sms",
                            lambda payload, db: True)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/incoming/", json={
            "from": "07111", "content": "Hi",
        })
        assert resp.status_code == 200


# ============================================================================
# POST /api/webhooks/sms/delivery-report
# ============================================================================

class TestSmsDeliveryWebhook:
    def teardown_method(self):
        _clear()

    def test_H_handles_delivery(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_delivery_report",
                            lambda payload, db: True)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/delivery-report", json={
            "messageid": "m1", "status": "delivered",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_E_trailing_slash(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_delivery_report",
                            lambda payload, db: True)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/delivery-report/", json={
            "messageid": "m1", "status": "failed",
        })
        assert resp.status_code == 200

    def test_E_handler_returns_false(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_delivery_report",
                            lambda payload, db: False)
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/webhooks/sms/delivery-report", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ============================================================================
# GET /api/admin/sms/stats
# ============================================================================

class TestSmsStats:
    def teardown_method(self):
        _clear()

    def test_H_returns_counts(self):
        """Each db.query(...).filter(...).count() returns a counter — we just
        verify it returns 200 with the expected shape."""
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.distinct.return_value = chain
        chain.count.return_value = 42  # all counts return 42
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/sms/stats")
        assert resp.status_code == 200
        body = resp.json()
        # All counts were 42
        assert body["total_sent"] == 42
        assert body["total_received"] == 42
        assert body["delivered"] == 42

    def test_E_empty_counts(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.distinct.return_value = chain
        chain.count.return_value = 0
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/sms/stats")
        assert resp.status_code == 200
        assert resp.json()["total_sent"] == 0
