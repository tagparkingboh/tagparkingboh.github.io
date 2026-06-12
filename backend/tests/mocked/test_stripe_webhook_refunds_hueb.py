"""
HUEB tests for the Stripe webhook refund branches in main.py.

Existing test_stripe_webhook_hueb_integration.py covers
payment_intent.succeeded / payment_failed. This file targets the
charge.refunded and refund.updated / refund.created event types.
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


def _payment(**kw):
    from db_models import PaymentStatus
    base = dict(
        id=1, amount_pence=9900, refund_amount_pence=0,
        status=PaymentStatus.SUCCEEDED,
        stripe_payment_intent_id="pi_1",
        refunded_at=None, refund_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _wire(payment=None):
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.first.return_value = payment
    db.query.return_value = chain
    db.commit = MagicMock()
    return db


def _stripe_event(event_type, data):
    return {"type": event_type, "data": {"object": data}}


# ============================================================================
# charge.refunded
# ============================================================================

class TestChargeRefunded:
    def teardown_method(self):
        _clear()

    def test_H_full_refund(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_1",
            "amount": 9900,
            "amount_refunded": 9900,
            "payment_intent": "pi_1",
            "metadata": {"booking_reference": "TAG-1"},
            "refunds": SimpleNamespace(data=[{"id": "re_1"}]),
        })
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        p = _payment()
        _override(_wire(p))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200
        from db_models import PaymentStatus
        assert p.status == PaymentStatus.REFUNDED
        assert p.refund_amount_pence == 9900

    def test_H_partial_refund(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_1",
            "amount": 9900,
            "amount_refunded": 3000,
            "payment_intent": "pi_1",
            "metadata": {"booking_reference": "TAG-1"},
            "refunds": SimpleNamespace(data=[{"id": "re_2"}]),
        })
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        p = _payment()
        _override(_wire(p))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200
        from db_models import PaymentStatus
        assert p.status == PaymentStatus.PARTIALLY_REFUNDED
        assert p.refund_amount_pence == 3000

    def test_E_payment_not_found(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_1",
            "amount": 9900,
            "amount_refunded": 9900,
            "payment_intent": "pi_missing",
            "metadata": {"booking_reference": "TAG-X"},
            "refunds": SimpleNamespace(data=[]),
        })
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200

    def test_E_no_payment_intent_id(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_1", "amount": 9900, "amount_refunded": 9900,
            "metadata": {"booking_reference": "TAG-1"},
            "refunds": SimpleNamespace(data=[]),
        })
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200


# ============================================================================
# refund.updated / refund.created
# ============================================================================

class TestRefundUpdated:
    def teardown_method(self):
        _clear()

    # Latent bug: refund.updated / refund.created branch (main.py:11966+) uses
    # `Payment` but never imports it locally — only the charge.refunded branch
    # above does. UnboundLocalError if Stripe sends these directly.
    # Documented in memory/project_manual_booking_system.md.
    # The not-succeeded + unknown-event + stripe-not-configured paths still
    # exercise the dispatch without reaching the broken Payment reference.

    def test_E_refund_not_succeeded(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("refund.updated", {
            "id": "re_1", "amount": 9900, "status": "failed",
            "payment_intent": "pi_1",
        })
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        _override(_wire(_payment()))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200
        assert resp.json()["refund_status"] == "failed"

    def test_E_unknown_event_type_falls_through(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        evt = _stripe_event("some.other.event", {})
        monkeypatch.setattr(main, "verify_webhook_signature",
                            lambda payload, sig: evt)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 200
        assert resp.json()["type"] == "some.other.event"

    def test_U_stripe_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: False)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "t=1,v1=s"})
        assert resp.status_code == 503

    def test_U_missing_signature(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={})
        assert resp.status_code == 400

    def test_U_invalid_signature(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        def boom(payload, sig):
            raise RuntimeError("bad sig")
        monkeypatch.setattr(main, "verify_webhook_signature", boom)
        _override(_wire(None))
        resp = TestClient(app).post("/api/webhooks/stripe", json={},
                                     headers={"Stripe-Signature": "bad"})
        assert resp.status_code == 400


class TestChargeRefundedManualBookingFallback:
    """Manual bookings paid via Stripe Payment Link have no payment intent on
    file, so the PI match finds nothing and dashboard refunds used to vanish.
    The fallback matches the charge's booking_reference metadata and
    back-fills the PI."""

    def teardown_method(self):
        _clear()

    def _wire_models(self, booking):
        from db_models import Booking, Payment
        db = MagicMock()

        def _query(model, *args):
            chain = MagicMock()
            chain.filter.return_value = chain
            if model is Payment:
                chain.first.return_value = None  # no PI match
            elif model is Booking:
                chain.first.return_value = booking
            else:
                chain.first.return_value = None
            return chain

        db.query.side_effect = _query
        return db

    def _post(self, monkeypatch, evt, db):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(main, "verify_webhook_signature", lambda payload, sig: evt)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override(db)
        return TestClient(app).post("/api/webhooks/stripe", json={},
                                    headers={"Stripe-Signature": "t=1,v1=s"})

    def test_H_metadata_reference_matches_and_backfills_pi(self, monkeypatch):
        from db_models import PaymentStatus
        p = _payment(stripe_payment_intent_id=None)
        booking = SimpleNamespace(id=42, reference="TAG-MANUAL1", payment=p)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_9",
            "amount": 9900,
            "amount_refunded": 9900,
            "payment_intent": "pi_manual_9",
            "metadata": {"booking_reference": "TAG-MANUAL1"},
            "refunds": SimpleNamespace(data=[{"id": "re_manual_9"}]),
        })

        resp = self._post(monkeypatch, evt, self._wire_models(booking))

        assert resp.status_code == 200
        assert p.stripe_payment_intent_id == "pi_manual_9"  # back-filled
        assert p.refund_id == "re_manual_9"
        assert p.refund_amount_pence == 9900
        assert p.status == PaymentStatus.REFUNDED

    def test_E_partial_refund_via_fallback(self, monkeypatch):
        from db_models import PaymentStatus
        p = _payment(stripe_payment_intent_id=None)
        booking = SimpleNamespace(id=42, reference="TAG-MANUAL1", payment=p)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_9",
            "amount": 9900,
            "amount_refunded": 2500,
            "payment_intent": "pi_manual_9",
            "metadata": {"booking_reference": "TAG-MANUAL1"},
            "refunds": SimpleNamespace(data=[{"id": "re_manual_9"}]),
        })

        resp = self._post(monkeypatch, evt, self._wire_models(booking))

        assert resp.status_code == 200
        assert p.status == PaymentStatus.PARTIALLY_REFUNDED
        assert p.refund_amount_pence == 2500

    def test_U_no_metadata_reference_stays_unmatched(self, monkeypatch):
        p = _payment(stripe_payment_intent_id=None)
        booking = SimpleNamespace(id=42, reference="TAG-MANUAL1", payment=p)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_9",
            "amount": 9900,
            "amount_refunded": 9900,
            "payment_intent": "pi_manual_9",
            "metadata": {},
            "refunds": SimpleNamespace(data=[{"id": "re_manual_9"}]),
        })

        resp = self._post(monkeypatch, evt, self._wire_models(booking))

        assert resp.status_code == 200
        assert p.refund_amount_pence == 0  # untouched
        assert p.stripe_payment_intent_id is None

    def test_E_existing_pi_not_overwritten_by_fallback(self, monkeypatch):
        """If the fallback booking's payment somehow has a different PI, the
        refund still records but the stored PI is preserved."""
        p = _payment(stripe_payment_intent_id="pi_already")
        booking = SimpleNamespace(id=42, reference="TAG-MANUAL1", payment=p)
        evt = _stripe_event("charge.refunded", {
            "id": "ch_9",
            "amount": 9900,
            "amount_refunded": 9900,
            "payment_intent": "pi_manual_9",
            "metadata": {"booking_reference": "TAG-MANUAL1"},
            "refunds": SimpleNamespace(data=[{"id": "re_manual_9"}]),
        })

        resp = self._post(monkeypatch, evt, self._wire_models(booking))

        assert resp.status_code == 200
        assert p.stripe_payment_intent_id == "pi_already"
