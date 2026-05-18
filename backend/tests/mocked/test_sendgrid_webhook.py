"""
Tests for POST /api/webhooks/sendgrid — the SendGrid Event Webhook endpoint
added 2026-05-19 to turn silent email failures (bounce / dropped / blocked /
spamreport) into actionable founder alerts.

Covers:
  - Hard-failure events trigger send_bounce_alert_email
  - Non-hard events (delivered, open, click, processed) are ignored
  - Mixed batches alert only on the hard ones
  - HTTP Basic auth (allow when both env vars set + correct creds;
    reject 401 on wrong creds; allow when env vars unset with a warning)
  - Malformed payloads don't crash the endpoint
  - Booking-reference lookup attaches when a matching customer exists
"""
import os
import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _basic_header(user: str, password: str) -> dict:
    raw = f"{user}:{password}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}


def _empty_db():
    """Fake DB that always finds no booking (booking_ref will be None)."""
    db = MagicMock()
    # Whatever query chain runs, .first() returns None and .all() returns [].
    chain = MagicMock()
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.first.return_value = None
    chain.all.return_value = []
    db.query.return_value = chain
    return db


# ----------------------------------------------------------------------
# Event filtering
# ----------------------------------------------------------------------

class TestEventFiltering:
    """Only the four hard-failure event types should trigger alerts."""

    @pytest.fixture(autouse=True)
    def _no_auth(self, monkeypatch):
        monkeypatch.delenv("SENDGRID_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("SENDGRID_WEBHOOK_PASS", raising=False)
        # Wire a no-op DB to silence the booking lookup.
        app.dependency_overrides[get_db] = lambda: iter([_empty_db()])
        yield
        app.dependency_overrides.clear()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_bounce_event_triggers_alert(self, mock_alert):
        payload = [
            {"email": "x@example.com", "event": "bounce",
             "reason": "550 No such user", "sg_event_id": "evt-1"}
        ]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"received": 1, "alerted": 1}
        assert mock_alert.call_count == 1
        kwargs = mock_alert.call_args.kwargs
        assert kwargs["customer_email"] == "x@example.com"
        assert kwargs["event_type"] == "bounce"
        assert "550" in kwargs["reason"]

    @patch("email_service.send_bounce_alert_email", return_value=True)
    @pytest.mark.parametrize("event_type", ["bounce", "dropped", "blocked", "spamreport"])
    def test_each_hard_failure_alerts(self, mock_alert, event_type):
        payload = [{"email": "x@y.com", "event": event_type, "reason": "test"}]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.status_code == 200
        assert resp.json()["alerted"] == 1

    @patch("email_service.send_bounce_alert_email", return_value=True)
    @pytest.mark.parametrize(
        "event_type",
        ["delivered", "open", "click", "processed", "deferred", "group_unsubscribe", "unsubscribe"],
    )
    def test_non_hard_events_ignored(self, mock_alert, event_type):
        payload = [{"email": "x@y.com", "event": event_type}]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"received": 1, "alerted": 0}
        mock_alert.assert_not_called()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_event_type_is_case_insensitive(self, mock_alert):
        """SendGrid event names are lowercase, but defend against UPPER."""
        payload = [{"email": "x@y.com", "event": "BOUNCE", "reason": "x"}]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.json()["alerted"] == 1


class TestMixedBatch:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        monkeypatch.delenv("SENDGRID_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("SENDGRID_WEBHOOK_PASS", raising=False)
        app.dependency_overrides[get_db] = lambda: iter([_empty_db()])
        yield
        app.dependency_overrides.clear()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_batch_alerts_only_on_hard_failures(self, mock_alert):
        payload = [
            {"email": "a@y.com", "event": "delivered"},
            {"email": "b@y.com", "event": "bounce", "reason": "x"},
            {"email": "c@y.com", "event": "open"},
            {"email": "d@y.com", "event": "blocked", "reason": "y"},
            {"email": "e@y.com", "event": "deferred"},
        ]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        body = resp.json()
        assert body == {"received": 5, "alerted": 2}
        assert mock_alert.call_count == 2
        called_emails = [c.kwargs["customer_email"] for c in mock_alert.call_args_list]
        assert "b@y.com" in called_emails
        assert "d@y.com" in called_emails


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------

class TestAuth:
    """Endpoint enforces Basic auth ONLY when both env vars are set."""

    def setup_method(self):
        app.dependency_overrides[get_db] = lambda: iter([_empty_db()])

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_accepts_when_creds_unset(self, mock_alert, monkeypatch):
        monkeypatch.delenv("SENDGRID_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("SENDGRID_WEBHOOK_PASS", raising=False)
        payload = [{"email": "x@y.com", "event": "bounce", "reason": "x"}]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.status_code == 200

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_rejects_missing_auth_header_when_creds_set(self, mock_alert, monkeypatch):
        monkeypatch.setenv("SENDGRID_WEBHOOK_USER", "sguser")
        monkeypatch.setenv("SENDGRID_WEBHOOK_PASS", "sgpass")
        payload = [{"email": "x@y.com", "event": "bounce", "reason": "x"}]
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=payload)
        assert resp.status_code == 401

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_rejects_wrong_creds(self, mock_alert, monkeypatch):
        monkeypatch.setenv("SENDGRID_WEBHOOK_USER", "sguser")
        monkeypatch.setenv("SENDGRID_WEBHOOK_PASS", "sgpass")
        payload = [{"email": "x@y.com", "event": "bounce", "reason": "x"}]
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=payload,
            headers=_basic_header("sguser", "wrongpass"),
        )
        assert resp.status_code == 401

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_accepts_correct_creds(self, mock_alert, monkeypatch):
        monkeypatch.setenv("SENDGRID_WEBHOOK_USER", "sguser")
        monkeypatch.setenv("SENDGRID_WEBHOOK_PASS", "sgpass")
        payload = [{"email": "x@y.com", "event": "bounce", "reason": "x"}]
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=payload,
            headers=_basic_header("sguser", "sgpass"),
        )
        assert resp.status_code == 200
        assert resp.json()["alerted"] == 1

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_rejects_malformed_auth_header(self, mock_alert, monkeypatch):
        monkeypatch.setenv("SENDGRID_WEBHOOK_USER", "sguser")
        monkeypatch.setenv("SENDGRID_WEBHOOK_PASS", "sgpass")
        payload = [{"email": "x@y.com", "event": "bounce", "reason": "x"}]
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=payload,
            headers={"Authorization": "Bearer not-basic"},
        )
        assert resp.status_code == 401


# ----------------------------------------------------------------------
# Defensive payloads
# ----------------------------------------------------------------------

class TestDefensive:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        monkeypatch.delenv("SENDGRID_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("SENDGRID_WEBHOOK_PASS", raising=False)
        app.dependency_overrides[get_db] = lambda: iter([_empty_db()])
        yield
        app.dependency_overrides.clear()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_empty_array_no_crash_no_alert(self, mock_alert):
        resp = TestClient(app).post("/api/webhooks/sendgrid", json=[])
        assert resp.status_code == 200
        assert resp.json() == {"received": 0, "alerted": 0}
        mock_alert.assert_not_called()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_object_payload_treated_as_empty(self, mock_alert):
        """SendGrid always posts an array; an object is malformed → treat as nothing."""
        resp = TestClient(app).post("/api/webhooks/sendgrid", json={"event": "bounce"})
        assert resp.status_code == 200
        assert resp.json() == {"received": 0, "alerted": 0}
        mock_alert.assert_not_called()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_non_dict_items_in_array_skipped(self, mock_alert):
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=["not-a-dict", {"email": "x@y.com", "event": "bounce", "reason": "x"}],
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": 2, "alerted": 1}

    @patch("email_service.send_bounce_alert_email", side_effect=Exception("kaboom"))
    def test_alert_send_failure_does_not_break_endpoint(self, mock_alert):
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=[{"email": "x@y.com", "event": "bounce", "reason": "x"}],
        )
        assert resp.status_code == 200
        # We received it but couldn't alert — the counter reflects that.
        assert resp.json() == {"received": 1, "alerted": 0}


# ----------------------------------------------------------------------
# Booking-reference lookup
# ----------------------------------------------------------------------

class TestBookingLookup:
    """When a matching customer/booking exists, the alert should be passed
    the booking reference. When not, booking_ref should be None."""

    @pytest.fixture(autouse=True)
    def _noauth(self, monkeypatch):
        monkeypatch.delenv("SENDGRID_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("SENDGRID_WEBHOOK_PASS", raising=False)
        yield
        app.dependency_overrides.clear()

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_attaches_booking_reference_when_customer_found(self, mock_alert):
        # Build a chain that returns a booking with .reference
        booking = MagicMock()
        booking.reference = "TAG-LOOKUP01"
        db = MagicMock()
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain

        # FastAPI expects a generator from get_db; yield the db.
        def _override():
            yield db
        app.dependency_overrides[get_db] = _override

        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=[{"email": "found@example.com", "event": "bounce", "reason": "x"}],
        )
        assert resp.status_code == 200
        kwargs = mock_alert.call_args.kwargs
        assert kwargs["booking_reference"] == "TAG-LOOKUP01"

    @patch("email_service.send_bounce_alert_email", return_value=True)
    def test_booking_reference_none_when_no_match(self, mock_alert):
        app.dependency_overrides[get_db] = lambda: iter([_empty_db()])
        resp = TestClient(app).post(
            "/api/webhooks/sendgrid",
            json=[{"email": "stranger@example.com", "event": "bounce", "reason": "x"}],
        )
        assert resp.status_code == 200
        kwargs = mock_alert.call_args.kwargs
        assert kwargs["booking_reference"] is None
