"""
HUEB tests for stripe_service.py — Happy / Unhappy / Edge / Boundary.

All Stripe SDK calls are mocked. Targets the create/get/refund/cancel/
webhook paths plus calculate_price_in_pence variants. No network access.
"""
from datetime import date as date_type
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import stripe_service
from stripe_service import PaymentIntentRequest


def _req(**overrides):
    base = dict(
        amount=9900,
        currency="gbp",
        customer_email="jo@x.test",
        customer_name="Jo K",
        booking_reference="TAG-1",
        flight_number="TOM1",
        flight_date="2026-06-01",
        drop_off_date="2026-06-01",
        pickup_date="2026-06-08",
    )
    base.update(overrides)
    return PaymentIntentRequest(**base)


def _fake_intent(**kw):
    base = dict(
        id="pi_123",
        client_secret="cs_456",
        amount=9900,
        amount_received=0,
        currency="gbp",
        status="requires_payment_method",
        receipt_email="jo@x.test",
        metadata=SimpleNamespace(booking_reference="TAG-1"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# init_stripe + create_payment_intent
# ============================================================================

class TestCreatePaymentIntent:
    def test_H_creates_and_returns_response(self, monkeypatch):
        monkeypatch.setattr(stripe_service, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "create",
                            lambda **kw: _fake_intent())
        resp = stripe_service.create_payment_intent(_req())
        assert resp.payment_intent_id == "pi_123"
        assert resp.client_secret == "cs_456"
        assert resp.amount == 9900

    def test_U_not_configured_raises(self, monkeypatch):
        monkeypatch.setattr(stripe_service, "is_stripe_configured", lambda: False)
        with pytest.raises(ValueError, match="not configured"):
            stripe_service.create_payment_intent(_req())

    def test_E_with_promo_code_metadata(self, monkeypatch):
        captured = {}
        def fake_create(**kw):
            captured.update(kw)
            return _fake_intent()
        monkeypatch.setattr(stripe_service, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "create", fake_create)
        stripe_service.create_payment_intent(_req(
            promo_code="TAG10", original_amount=11000, discount_amount=1100
        ))
        meta = captured["metadata"]
        assert meta["promo_code"] == "TAG10"
        assert meta["original_amount"] == "11000"
        assert meta["discount_amount"] == "1100"

    def test_E_optional_fields_blank_when_missing(self, monkeypatch):
        captured = {}
        def fake_create(**kw):
            captured.update(kw)
            return _fake_intent()
        monkeypatch.setattr(stripe_service, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "create", fake_create)
        stripe_service.create_payment_intent(_req())
        meta = captured["metadata"]
        assert meta["departure_id"] == ""
        assert meta["drop_off_slot"] == ""
        assert meta["promo_code"] == ""


# ============================================================================
# get_payment_status
# ============================================================================

class TestGetPaymentStatus:
    def test_H_retrieves_status(self, monkeypatch):
        intent = _fake_intent(status="succeeded", amount_received=9900)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "retrieve",
                            lambda pid: intent)
        st = stripe_service.get_payment_status("pi_123")
        assert st.status == "succeeded"
        assert st.amount_received == 9900
        assert st.booking_reference == "TAG-1"

    def test_E_no_metadata_returns_none_ref(self, monkeypatch):
        intent = _fake_intent(metadata=None)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "retrieve",
                            lambda pid: intent)
        st = stripe_service.get_payment_status("pi_123")
        assert st.booking_reference is None

    def test_E_zero_amount_received(self, monkeypatch):
        intent = _fake_intent(amount_received=None)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "retrieve",
                            lambda pid: intent)
        st = stripe_service.get_payment_status("pi_123")
        assert st.amount_received == 0


# ============================================================================
# verify_webhook_signature
# ============================================================================

class TestVerifyWebhookSignature:
    def test_H_returns_event(self, monkeypatch):
        monkeypatch.setattr(stripe_service.stripe.Webhook, "construct_event",
                            lambda payload, sig, secret: {"type": "payment_intent.succeeded"})
        evt = stripe_service.verify_webhook_signature(b"{}", "t=abc,v1=def")
        assert evt["type"] == "payment_intent.succeeded"

    def test_U_invalid_signature_raises(self, monkeypatch):
        import stripe
        def boom(payload, sig, secret):
            raise stripe.error.SignatureVerificationError("bad sig", sig)
        monkeypatch.setattr(stripe_service.stripe.Webhook, "construct_event", boom)
        with pytest.raises(stripe.error.SignatureVerificationError):
            stripe_service.verify_webhook_signature(b"{}", "bad")


# ============================================================================
# refund_payment
# ============================================================================

class TestRefundPayment:
    def test_H_returns_refund_details(self, monkeypatch):
        refund = SimpleNamespace(id="re_1", status="succeeded", amount=9900)
        monkeypatch.setattr(stripe_service.stripe.Refund, "create", lambda **kw: refund)
        out = stripe_service.refund_payment("pi_123")
        assert out["refund_id"] == "re_1"
        assert out["status"] == "succeeded"
        assert out["amount"] == 9900

    def test_E_custom_reason_passed_through(self, monkeypatch):
        captured = {}
        def fake_create(**kw):
            captured.update(kw)
            return SimpleNamespace(id="re_2", status="succeeded", amount=100)
        monkeypatch.setattr(stripe_service.stripe.Refund, "create", fake_create)
        stripe_service.refund_payment("pi_123", reason="duplicate")
        assert captured["reason"] == "duplicate"
        assert captured["payment_intent"] == "pi_123"


# ============================================================================
# cancel_payment_intent
# ============================================================================

class TestCancelPaymentIntent:
    def test_H_cancels_successfully(self, monkeypatch):
        cancelled = SimpleNamespace(id="pi_123", status="canceled")
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "cancel", lambda pid: cancelled)
        out = stripe_service.cancel_payment_intent("pi_123")
        assert out["success"] is True
        assert out["status"] == "canceled"

    def test_U_invalid_request_returns_error_dict(self, monkeypatch):
        import stripe
        def boom(pid):
            raise stripe.error.InvalidRequestError("already succeeded", pid)
        monkeypatch.setattr(stripe_service.stripe.PaymentIntent, "cancel", boom)
        out = stripe_service.cancel_payment_intent("pi_123")
        assert out["success"] is False
        assert "already succeeded" in out["error"]


# ============================================================================
# calculate_price_in_pence — all branches
# ============================================================================

class TestCalculatePriceInPence:
    def test_H_custom_price_overrides_everything(self):
        assert stripe_service.calculate_price_in_pence(custom_price=42.5) == 4250

    def test_H_duration_with_dropoff_date(self, monkeypatch):
        from booking_service import BookingService
        monkeypatch.setattr(BookingService, "calculate_price_for_duration",
                            classmethod(lambda cls, days, dd, pd: 99.0))
        pence = stripe_service.calculate_price_in_pence(
            duration_days=7, drop_off_date=date_type(2026, 6, 1)
        )
        assert pence == 9900

    def test_H_package_with_dropoff_date(self, monkeypatch):
        from booking_service import BookingService
        monkeypatch.setattr(BookingService, "calculate_price",
                            classmethod(lambda cls, pkg, dd: 109.0))
        pence = stripe_service.calculate_price_in_pence(
            package="quick", drop_off_date=date_type(2026, 6, 1)
        )
        assert pence == 10900

    def test_E_package_without_date_uses_late_fallback(self, monkeypatch):
        from booking_service import BookingService
        monkeypatch.setattr(BookingService, "get_package_prices",
                            classmethod(lambda cls: {"quick": {"late": 110.0}}))
        pence = stripe_service.calculate_price_in_pence(package="quick")
        assert pence == 11000

    def test_E_unknown_package_falls_back_to_109(self, monkeypatch):
        from booking_service import BookingService
        monkeypatch.setattr(BookingService, "get_package_prices",
                            classmethod(lambda cls: {}))  # no quick / longer key
        pence = stripe_service.calculate_price_in_pence(package="bogus")
        assert pence == 10900  # 109.0 default

    def test_E_no_args_uses_99_default(self):
        pence = stripe_service.calculate_price_in_pence()
        assert pence == 9900

    def test_B_zero_custom_price(self):
        assert stripe_service.calculate_price_in_pence(custom_price=0.0) == 0

    def test_B_fractional_pence_rounded(self):
        # 12.999 * 100 = 1299.9, int() truncates to 1299
        assert stripe_service.calculate_price_in_pence(custom_price=12.999) == 1299
