"""
HUEB tests for the financials refund-sync edit.

Covers:
  - PUT /api/admin/bookings/{id}/refund-sync — manual amount mode (validation,
    full/partial boundaries, Stripe-synced 409) and Stripe id mode (back-fill,
    conflicts, warnings)
  - stripe_service.lookup_refund — re_/pi_ resolution against a mocked Stripe
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import main
import stripe_service
from main import app, require_admin
from database import get_db
from db_models import Booking, Payment, PaymentStatus

from fastapi.testclient import TestClient


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: _admin()


def _payment(**kw):
    base = dict(
        id=5,
        booking_id=42,
        amount_pence=8100,
        refund_amount_pence=None,
        refund_id=None,
        refund_reason=None,
        refunded_at=None,
        status=PaymentStatus.SUCCEEDED,
        stripe_payment_intent_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _booking(payment=None, **kw):
    base = dict(
        id=42,
        reference="TAG-2NSWW130",
        payment=payment if payment is not None else _payment(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _model_db(handlers=None):
    handlers = handlers or {}
    db = MagicMock()

    def _query(model, *args):
        spec = handlers.get(model, {})
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = spec.get("first")
        chain.all.return_value = spec.get("all", [])
        return chain

    db.query.side_effect = _query
    return db


def _lookup_result(**kw):
    base = dict(
        refund_id="re_123",
        payment_intent_id="pi_456",
        refund_amount_pence=8100,
        latest_refund_amount_pence=8100,
        charge_amount_pence=8100,
        reason="requested_by_customer",
        refunded_at_ts=1780000000,
        fully_refunded=True,
    )
    base.update(kw)
    return base


class TestRefundSyncManualMode:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _put(self, db, booking_id=42, **params):
        _override(db)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return TestClient(app).put(f"/api/admin/bookings/{booking_id}/refund-sync?{qs}")

    # --- HAPPY ---------------------------------------------------------------

    def test_H_full_manual_refund_marks_refunded(self):
        payment = _payment()
        db = _model_db({Booking: {"first": _booking(payment)}})

        resp = self._put(db, refund_pence=8100)

        assert resp.status_code == 200
        assert payment.refund_amount_pence == 8100
        assert payment.status == PaymentStatus.REFUNDED
        assert payment.refunded_at is not None
        assert resp.json()["payment_status"] == "refunded"

    def test_H_partial_manual_refund_marks_partially_refunded(self):
        payment = _payment()
        db = _model_db({Booking: {"first": _booking(payment)}})

        resp = self._put(db, refund_pence=2000)

        assert resp.status_code == 200
        assert payment.refund_amount_pence == 2000
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED

    def test_H_reason_recorded(self):
        payment = _payment()
        db = _model_db({Booking: {"first": _booking(payment)}})

        resp = self._put(db, refund_pence=2000, refund_reason=
                         "goodwill")

        assert resp.status_code == 200
        assert payment.refund_reason == "goodwill"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_neither_mode_rejected(self):
        resp = self._put(_model_db())
        assert resp.status_code == 400
        assert "exactly one" in resp.json()["detail"].lower()

    def test_U_both_modes_rejected(self):
        resp = self._put(_model_db(), refund_pence=100, stripe_id="re_1")
        assert resp.status_code == 400

    def test_U_booking_not_found(self):
        resp = self._put(_model_db({Booking: {"first": None}}), refund_pence=100)
        assert resp.status_code == 404

    def test_U_booking_without_payment(self):
        db = _model_db({Booking: {"first": _booking(payment=False)}})
        # payment=False is falsy → "no payment record"
        resp = self._put(db, refund_pence=100)
        assert resp.status_code == 404
        assert "payment" in resp.json()["detail"].lower()

    def test_U_manual_blocked_when_stripe_refund_on_record(self):
        payment = _payment(refund_id="re_existing")
        db = _model_db({Booking: {"first": _booking(payment)}})
        resp = self._put(db, refund_pence=2000)
        assert resp.status_code == 409
        assert "Stripe" in resp.json()["detail"]

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_refund_one_below_paid_is_partial(self):
        payment = _payment()
        db = _model_db({Booking: {"first": _booking(payment)}})
        resp = self._put(db, refund_pence=8099)
        assert resp.status_code == 200
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED

    def test_B_refund_above_paid_rejected(self):
        payment = _payment()
        db = _model_db({Booking: {"first": _booking(payment)}})
        resp = self._put(db, refund_pence=8101)
        assert resp.status_code == 400
        assert "exceed" in resp.json()["detail"].lower()

    def test_B_zero_refund_rejected(self):
        db = _model_db({Booking: {"first": _booking()}})
        resp = self._put(db, refund_pence=0)
        assert resp.status_code == 400

    def test_B_negative_refund_rejected(self):
        db = _model_db({Booking: {"first": _booking()}})
        resp = self._put(db, refund_pence=-100)
        assert resp.status_code == 400


class TestRefundSyncStripeMode:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _put(self, db, monkeypatch, lookup=None, stripe_id="re_123", configured=True):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: configured)
        if lookup is not None:
            monkeypatch.setattr(stripe_service, "lookup_refund",
                                lookup if callable(lookup) else lambda _id: lookup)
        _override(db)
        return TestClient(app).put(
            f"/api/admin/bookings/42/refund-sync?stripe_id={stripe_id}"
        )

    # --- HAPPY ---------------------------------------------------------------

    def test_H_syncs_and_backfills_payment_intent(self, monkeypatch):
        payment = _payment()
        db = _model_db({
            Booking: {"first": _booking(payment)},
            Payment: {"first": None},
        })

        resp = self._put(db, monkeypatch, lookup=_lookup_result())

        assert resp.status_code == 200
        assert payment.stripe_payment_intent_id == "pi_456"
        assert payment.refund_id == "re_123"
        assert payment.refund_amount_pence == 8100
        assert payment.status == PaymentStatus.REFUNDED
        assert payment.refunded_at == datetime.utcfromtimestamp(1780000000)
        assert resp.json()["warning"] is None

    def test_H_partial_stripe_refund(self, monkeypatch):
        payment = _payment()
        db = _model_db({
            Booking: {"first": _booking(payment)},
            Payment: {"first": None},
        })
        lookup = _lookup_result(
            refund_amount_pence=3000, latest_refund_amount_pence=3000,
            fully_refunded=False,
        )

        resp = self._put(db, monkeypatch, lookup=lookup)

        assert resp.status_code == 200
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_stripe_not_configured(self, monkeypatch):
        db = _model_db({Booking: {"first": _booking()}})
        resp = self._put(db, monkeypatch, configured=False)
        assert resp.status_code == 503

    def test_U_lookup_value_error_becomes_400(self, monkeypatch):
        db = _model_db({Booking: {"first": _booking()}})

        def boom(_id):
            raise ValueError("No refunds found on payment intent pi_x")

        resp = self._put(db, monkeypatch, lookup=boom, stripe_id="pi_x")
        assert resp.status_code == 400
        assert "No refunds" in resp.json()["detail"]

    def test_U_payment_intent_mismatch_conflicts(self, monkeypatch):
        payment = _payment(stripe_payment_intent_id="pi_OTHER")
        db = _model_db({Booking: {"first": _booking(payment)}})

        resp = self._put(db, monkeypatch, lookup=_lookup_result())

        assert resp.status_code == 409
        assert "different payment intent" in resp.json()["detail"]

    def test_U_payment_intent_owned_by_other_booking_conflicts(self, monkeypatch):
        payment = _payment()
        other_payment = _payment(booking_id=99)
        db = _model_db({
            Booking: {"first": _booking(payment)},
            Payment: {"first": other_payment},
        })

        resp = self._put(db, monkeypatch, lookup=_lookup_result())

        assert resp.status_code == 409
        assert "already belongs" in resp.json()["detail"]

    # --- EDGE ----------------------------------------------------------------

    def test_E_amount_mismatch_returns_warning_but_saves(self, monkeypatch):
        payment = _payment(amount_pence=9000)
        db = _model_db({
            Booking: {"first": _booking(payment)},
            Payment: {"first": None},
        })
        lookup = _lookup_result(charge_amount_pence=8100, refund_amount_pence=8100)

        resp = self._put(db, monkeypatch, lookup=lookup)

        assert resp.status_code == 200
        assert "differs" in resp.json()["warning"]
        assert payment.refund_amount_pence == 8100


class TestLookupRefund:
    def _stripe(self, monkeypatch, refund=None, refunds_list=None, charge=None):
        monkeypatch.setattr(stripe_service, "init_stripe", lambda: None)
        fake = SimpleNamespace(
            Refund=SimpleNamespace(
                retrieve=lambda _id: refund,
                list=lambda **kw: SimpleNamespace(data=refunds_list or []),
            ),
            Charge=SimpleNamespace(retrieve=lambda _id: charge),
        )
        monkeypatch.setattr(stripe_service, "stripe", fake)

    def test_H_refund_id_resolves_with_cumulative_amount(self, monkeypatch):
        refund = SimpleNamespace(
            id="re_123", status="succeeded", amount=3000,
            payment_intent="pi_456", charge="ch_1",
            reason="requested_by_customer", created=1780000000,
        )
        charge = SimpleNamespace(amount=8100, amount_refunded=5000)
        self._stripe(monkeypatch, refund=refund, charge=charge)

        result = stripe_service.lookup_refund("re_123")

        assert result["refund_id"] == "re_123"
        assert result["payment_intent_id"] == "pi_456"
        assert result["refund_amount_pence"] == 5000  # cumulative, not 3000
        assert result["latest_refund_amount_pence"] == 3000
        assert result["fully_refunded"] is False

    def test_H_payment_intent_id_resolves_latest_refund(self, monkeypatch):
        refund = SimpleNamespace(
            id="re_999", status="succeeded", amount=8100,
            payment_intent="pi_456", charge="ch_1",
            reason=None, created=1780000000,
        )
        charge = SimpleNamespace(amount=8100, amount_refunded=8100)
        self._stripe(monkeypatch, refunds_list=[refund], charge=charge)

        result = stripe_service.lookup_refund("pi_456")

        assert result["refund_id"] == "re_999"
        assert result["fully_refunded"] is True

    def test_U_payment_intent_without_refunds(self, monkeypatch):
        self._stripe(monkeypatch, refunds_list=[])
        with pytest.raises(ValueError, match="No refunds found"):
            stripe_service.lookup_refund("pi_456")

    def test_U_unsupported_id_prefix(self, monkeypatch):
        self._stripe(monkeypatch)
        with pytest.raises(ValueError, match="re_.*pi_"):
            stripe_service.lookup_refund("ch_123")

    def test_U_non_succeeded_refund(self, monkeypatch):
        refund = SimpleNamespace(
            id="re_123", status="pending", amount=3000,
            payment_intent="pi_456", charge="ch_1",
        )
        self._stripe(monkeypatch, refund=refund)
        with pytest.raises(ValueError, match="not succeeded"):
            stripe_service.lookup_refund("re_123")

    def test_E_no_charge_falls_back_to_refund_amount(self, monkeypatch):
        refund = SimpleNamespace(
            id="re_123", status="succeeded", amount=3000,
            payment_intent="pi_456", charge=None,
            reason=None, created=1780000000,
        )
        self._stripe(monkeypatch, refund=refund)

        result = stripe_service.lookup_refund("re_123")

        assert result["refund_amount_pence"] == 3000
        assert result["charge_amount_pence"] is None
        assert result["fully_refunded"] is False
