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


# 2026-05-29 PR 6: SMS webhooks now require the secret as a URL-path
# token. SMS Works' dashboard exposes only a URL field on its webhook
# config screen — no header auth — so the secret rides in the URL.
# Tests that exercise the handler body must set SMS_WEBHOOK_SECRET in
# env AND post to the new URL pattern. Auth-fail paths (wrong secret,
# env unset, legacy URL closed) are covered in
# test_pr6_sms_webhook_auth_hueb.py.
SMS_TEST_SECRET = "test-sms-webhook-secret"
SMS_DELIVERY_URL = f"/api/webhooks/sms/delivery-report/{SMS_TEST_SECRET}"
# SMS_INCOMING_URL removed 2026-05-29 PR 6 — inbound webhook route
# deleted (one-way SMS only; "please do not reply" on every outbound).


@pytest.fixture(autouse=True)
def _set_sms_webhook_secret(monkeypatch):
    """Make every test in this file run with the secret configured so
    the focus stays on handler behaviour, not gate behaviour."""
    monkeypatch.setenv("SMS_WEBHOOK_SECRET", SMS_TEST_SECRET)


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


# TestSmsIncomingWebhook removed 2026-05-29 PR 6: POST /api/webhooks/sms/incoming
# route was deleted entirely. TAG sends one-way SMS only ("please do not
# reply" on every outbound), so there's no legitimate inbound traffic and
# no SMS Works dashboard config that would post here. Regression that
# the route stays gone lives in
# test_pr6_sms_webhook_auth_hueb.py::TestIncomingRouteIsGone.
# sms_service.handle_incoming_sms (the parsing helper) stays — it's
# exercised directly without HTTP by test_sms_integration.py.


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
        resp = TestClient(app).post(
            SMS_DELIVERY_URL,
            json={"messageid": "m1", "status": "delivered"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    # test_E_trailing_slash removed 2026-05-29 PR 6: the legacy
    # trailing-slash variant route is gone (was unauth).

    def test_E_handler_returns_false(self, monkeypatch):
        monkeypatch.setattr("sms_service.handle_delivery_report",
                            lambda payload, db: False)
        _override_public(MagicMock())
        resp = TestClient(app).post(
            SMS_DELIVERY_URL,
            json={},
        )
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
