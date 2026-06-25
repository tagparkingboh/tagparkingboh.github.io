"""
HUEB (Happy / Unhappy / Edge / Boundary) integration tests for the
Stripe webhook endpoint, hitting the live FastAPI route through TestClient
so coverage on main.py is genuinely lifted (per backend/docs/SPEC.md).

Endpoint: POST /api/webhooks/stripe

Event types handled by main.py:
  payment_intent.succeeded       (H) — flips Payment to SUCCEEDED, fires
                                       planner / auto-roster / DVLA hooks
  payment_intent.payment_failed  (U) — flips Payment to FAILED, audit log
  charge.refunded                (E) — applies full or partial refund
  refund.updated / refund.created (E) — alternative refund path

Auth notes:
  - The endpoint is unauthenticated (Stripe verifies via signature header).
  - We monkeypatch `verify_webhook_signature` and `is_stripe_configured` so
    we can drive every branch without real Stripe keys.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app
from database import get_db
from db_models import PaymentStatus


# ============================================================================
# Helpers
# ============================================================================

def _stripe_obj(**fields):
    """Stripe API responses are StripeObject (not dicts); the webhook uses
    a mix of getattr() and bracket access. MagicMock covers both."""
    obj = MagicMock()
    for k, v in fields.items():
        setattr(obj, k, v)
        # Also support bracket access for the few keys the endpoint reads
        # with data["id"], data["amount_refunded"], etc.
    # Make subscript ([] access) return matching attribute when asked.
    obj.__getitem__.side_effect = lambda k: fields.get(k)
    obj.__contains__.side_effect = lambda k: k in fields
    return obj


def _event(event_type, data_object):
    """Build a Stripe-shaped event dict our endpoint expects."""
    return {
        "type": event_type,
        "data": {"object": data_object},
    }


def _override_db(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


def _mock_payment(intent_id="pi_test_HUEB", booking_id=1):
    p = MagicMock()
    p.id = 1
    p.booking_id = booking_id
    p.stripe_payment_intent_id = intent_id
    p.status = PaymentStatus.PENDING
    p.refund_amount_pence = None
    p.refunded_at = None
    p.refund_id = None
    return p


def _wire_payment_lookup(payment):
    """Stub DB so Payment lookups return our row."""
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value.first.return_value = payment
    db.query.return_value = chain
    db.commit = MagicMock()
    return db


def _post(payload, signature="t=1,v1=fake"):
    """POST with a body that's a valid JSON serialisation."""
    return TestClient(app).post(
        "/api/webhooks/stripe",
        content=json.dumps({"_meta": "see-fixture"}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": signature,
        },
    )


# ============================================================================
# payment_intent.succeeded — Happy
# ============================================================================

class TestPaymentIntentSucceeded:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_payment_succeeded_updates_status(self, mock_update, mock_verify, mock_cfg):
        payment = _mock_payment(intent_id="pi_succ_001", booking_id=42)
        payment.status = PaymentStatus.SUCCEEDED
        mock_update.return_value = (payment, False)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_succ_001",
                metadata={"booking_reference": "TAG-HUEB001"},
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        resp = _post({})
        assert resp.status_code == 200
        # Payment update call was made with the correct intent id + status
        mock_update.assert_called_once()
        kwargs = mock_update.call_args.kwargs
        assert kwargs["stripe_payment_intent_id"] == "pi_succ_001"
        assert kwargs["status"] == PaymentStatus.SUCCEEDED

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_payment_succeeded_with_promo_metadata(self, mock_update, mock_verify, mock_cfg):
        payment = _mock_payment()
        payment.status = PaymentStatus.SUCCEEDED
        mock_update.return_value = (payment, False)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_succ_002",
                metadata={
                    "booking_reference": "TAG-HUEB002",
                    "promo_code": "TEST10OFF",
                    "original_amount": "10000",
                    "discount_amount": "1000",
                },
            ),
        )
        _override_db(_wire_payment_lookup(payment))
        resp = _post({})
        assert resp.status_code == 200

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_payment_succeeded_marks_airport_quote_converted(self, mock_update, mock_verify, mock_cfg):
        payment = _mock_payment(intent_id="pi_aq_conv", booking_id=42)
        payment.status = PaymentStatus.SUCCEEDED
        mock_update.return_value = (payment, False)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_aq_conv",
                metadata={
                    "booking_reference": "TAG-AQCONV",
                    "airport_quote_snapshot_id": "555",
                },
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        with patch("main.mark_airport_quote_converted") as mock_mark:
            resp = _post({})

        assert resp.status_code == 200
        mock_mark.assert_called_once_with(ANY, 555)

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_U_duplicate_payment_webhook_does_not_mark_airport_quote_converted(self, mock_update, mock_verify, mock_cfg):
        payment = _mock_payment(intent_id="pi_aq_dup", booking_id=42)
        mock_update.return_value = (payment, True)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_aq_dup",
                metadata={
                    "booking_reference": "TAG-AQDUP",
                    "airport_quote_snapshot_id": "555",
                },
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        with patch("main.mark_airport_quote_converted") as mock_mark:
            resp = _post({})

        assert resp.status_code == 200
        mock_mark.assert_not_called()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_payment_succeeded_issues_real_converted_update_sql(self, mock_update, mock_verify, mock_cfg):
        """#1 success lifecycle point, proven through the REAL writer (mark is
        NOT patched): the succeeded webhook issues an UPDATE ... SET converted =
        true for the snapshot id. The sibling test above proves the call site is
        reached; this one proves the SQL that actually flips the row."""
        payment = _mock_payment(intent_id="pi_aq_real", booking_id=42)
        payment.status = PaymentStatus.SUCCEEDED
        mock_update.return_value = (payment, False)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_aq_real",
                metadata={
                    "booking_reference": "TAG-AQREAL",
                    "airport_quote_snapshot_id": "555",
                },
            ),
        )
        db = _wire_payment_lookup(payment)
        _override_db(db)

        resp = _post({})

        assert resp.status_code == 200
        updates = [
            call for call in db.execute.call_args_list
            if "airport_quote_conversion_log" in str(call.args[0]).lower()
        ]
        assert updates, "succeeded webhook must issue the conversion UPDATE"
        sql = str(updates[0].args[0]).lower()
        assert "update airport_quote_conversion_log" in sql
        assert "set converted = true" in sql
        assert updates[0].args[1] == {"airport_quote_snapshot_id": 555}


# ============================================================================
# payment_intent.succeeded — auto-roster + auto-link wiring
#
# Driver-trust pivot (2026-05-28) split shift coverage into two background
# tasks: `auto_create_or_extend_async` rebuilds unowned auto-shifts, and
# `auto_link_booking_async` writes the ShiftBookingLink to any existing
# (incl. frozen) shift whose window covers the booking. When rebuild's
# skip-if-covered fires (booking lands inside a claimed/frozen shift),
# auto_link is the ONLY path that writes the link row.
#
# Real incident (TAG-EAW63114, 2026-05-29): online booking confirmed via
# Stripe webhook fell inside Marek's already-claimed 03:50-09:10 shift on
# 13 Jun. Rebuild correctly skipped (booking covered by frozen window),
# but the webhook was never scheduling auto_link — booking ended up
# orphaned from the driver's card. Admin mark-paid path scheduled both;
# webhook + free-booking paths only scheduled the rebuild.
#
# Tests below pin both background tasks to the webhook entry so a future
# refactor can't silently drop one again.
# ============================================================================


class TestPaymentSucceededSchedulesAutoLink:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_schedules_both_auto_create_and_auto_link(
        self, mock_update, mock_verify, mock_cfg
    ):
        """Real new confirmation → BOTH auto_create_or_extend_async AND
        auto_link_booking_async must be scheduled with the booking id.

        Regression fence for TAG-EAW63114: rebuild alone is not enough
        when the booking lands inside a frozen shift's window — only
        auto_link writes the ShiftBookingLink in that case."""
        payment = _mock_payment(intent_id="pi_wire_001", booking_id=746)
        payment.status = PaymentStatus.SUCCEEDED
        mock_update.return_value = (payment, False)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_wire_001",
                metadata={"booking_reference": "TAG-EAW63114"},
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        with patch("auto_roster.auto_create_or_extend_async") as mock_rebuild, \
             patch("roster_planner_runner.auto_link_booking_async") as mock_link, \
             patch("roster_planner_runner.fire_engine_async"), \
             patch("dvla_compliance.check_and_alert_for_booking_async"):
            resp = _post({})
            assert resp.status_code == 200
            mock_rebuild.assert_called_once_with(746)
            mock_link.assert_called_once_with(746)

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_U_duplicate_webhook_skips_auto_link_too(
        self, mock_update, mock_verify, mock_cfg
    ):
        """Duplicate webhook (was_already_processed=True) must not
        schedule EITHER background task — pairs with the existing
        rebuild-skip assertion so a future change can't drift one path's
        duplicate-handling without the other."""
        payment = _mock_payment(intent_id="pi_dup_002", booking_id=748)
        mock_update.return_value = (payment, True)

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_dup_002",
                metadata={"booking_reference": "TAG-EAW63116"},
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        with patch("auto_roster.auto_create_or_extend_async") as mock_rebuild, \
             patch("roster_planner_runner.auto_link_booking_async") as mock_link:
            resp = _post({})
            assert resp.status_code == 200
            mock_rebuild.assert_not_called()
            mock_link.assert_not_called()


# ============================================================================
# Signature + config — Unhappy
# ============================================================================

class TestSignatureAndConfig:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.is_stripe_configured", return_value=False)
    def test_U_stripe_not_configured_returns_503(self, mock_cfg):
        _override_db(MagicMock())
        resp = TestClient(app).post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "t=1,v1=x"},
        )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    @patch("main.is_stripe_configured", return_value=True)
    def test_U_missing_signature_header_returns_400(self, mock_cfg):
        _override_db(MagicMock())
        resp = TestClient(app).post(
            "/api/webhooks/stripe",
            content=b"{}",
            # No Stripe-Signature header
        )
        assert resp.status_code == 400
        assert "missing" in resp.json()["detail"].lower()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature", side_effect=Exception("bad sig"))
    def test_U_invalid_signature_returns_400(self, mock_verify, mock_cfg):
        _override_db(MagicMock())
        resp = TestClient(app).post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "t=1,v1=tampered"},
        )
        assert resp.status_code == 400
        assert "invalid signature" in resp.json()["detail"].lower()


# ============================================================================
# payment_intent.payment_failed — Unhappy
# ============================================================================

class TestPaymentIntentFailed:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_U_payment_failed_returns_status_failed(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log
    ):
        last_err = MagicMock()
        last_err.message = "card_declined"
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_fail_001",
                metadata={"booking_reference": "TAG-HUEB003"},
                last_payment_error=last_err,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert "card_declined" in body["error"]

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_U_payment_failed_without_last_error_uses_generic_message(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log
    ):
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_fail_002",
                metadata={"booking_reference": "TAG-HUEB004"},
                last_payment_error=None,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200
        assert resp.json()["error"] == "Unknown error"


# ============================================================================
# payment_intent.payment_failed — decline_code capture (2026-05-27)
#
# Before: only `last_payment_error.message` was logged. "Your card was
# declined" by itself doesn't distinguish a fraud-flag from insufficient
# funds from "try_again_later" — admins had to open the Stripe dashboard.
# After: also capture `last_payment_error.code` (e.g. "card_declined")
# and `last_payment_error.decline_code` (e.g. "do_not_honor",
# "insufficient_funds", "try_again_later"), include them in the error_log
# message suffix `[code=..., decline_code=...]` AND in the audit event's
# `event_data` dict. Triggered by triage of TAG-TSZ61426 — Santander
# returned `do_not_honor`, invisible in our logs.
# ============================================================================


class TestPaymentFailedDeclineCodeCapture:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_H_code_and_decline_code_both_captured(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log,
    ):
        """Happy: Stripe returns full error shape — message + code +
        decline_code. All three appear in the audit `event_data` AND the
        error_log message suffix. (TAG-TSZ61426's actual data shape:
        card_declined / do_not_honor from Santander.)"""
        last_err = MagicMock()
        last_err.message = "Your card was declined."
        last_err.code = "card_declined"
        last_err.decline_code = "do_not_honor"
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_decline_001",
                metadata={"booking_reference": "TAG-DECLINE01"},
                last_payment_error=last_err,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200

        # Audit event carries both structured fields.
        audit_kwargs = mock_audit.call_args.kwargs
        ed = audit_kwargs["event_data"]
        assert ed["error_code"] == "card_declined"
        assert ed["decline_code"] == "do_not_honor"
        assert ed["error_message"] == "Your card was declined."

        # Error log message includes the suffix so it's grep-able.
        log_kwargs = mock_log.call_args.kwargs
        assert "code=card_declined" in log_kwargs["message"]
        assert "decline_code=do_not_honor" in log_kwargs["message"]
        assert "Your card was declined." in log_kwargs["message"]

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_U_no_last_payment_error_object_no_suffix_no_code_fields(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log,
    ):
        """Unhappy: webhook arrives with `last_payment_error=None` (rare —
        Stripe usually always populates it on payment_failed events, but
        the handler must be defensive). Generic "Unknown error" message,
        no `[code=...]` suffix, audit dict's structured fields are None."""
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_decline_002",
                metadata={"booking_reference": "TAG-DECLINE02"},
                last_payment_error=None,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200

        audit_kwargs = mock_audit.call_args.kwargs
        ed = audit_kwargs["event_data"]
        assert ed["error_code"] is None
        assert ed["decline_code"] is None
        assert ed["error_message"] == "Unknown error"

        log_kwargs = mock_log.call_args.kwargs
        # No structured suffix when both fields are absent.
        assert "[code=" not in log_kwargs["message"]
        assert log_kwargs["message"] == "Payment failed: Unknown error"

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_E_code_present_decline_code_missing_renders_dash(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log,
    ):
        """Edge: some Stripe error shapes (non-card errors like
        `authentication_required`, `payment_method_provider_decline`)
        carry `code` but not `decline_code`. The suffix must still render
        — `decline_code=-` is more useful than a missing field, because
        it tells the admin "we asked Stripe, decline_code wasn't set."
        Audit dict carries `None` faithfully (not the dash) so a future
        consumer can distinguish absent from literal "-"."""
        last_err = MagicMock()
        last_err.message = "Authentication required for this card."
        last_err.code = "authentication_required"
        last_err.decline_code = None  # Stripe didn't return one
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_decline_003",
                metadata={"booking_reference": "TAG-DECLINE03"},
                last_payment_error=last_err,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200

        audit_kwargs = mock_audit.call_args.kwargs
        ed = audit_kwargs["event_data"]
        assert ed["error_code"] == "authentication_required"
        assert ed["decline_code"] is None  # raw None preserved

        log_kwargs = mock_log.call_args.kwargs
        assert "code=authentication_required" in log_kwargs["message"]
        # Dash placeholder so the suffix structure is consistent.
        assert "decline_code=-" in log_kwargs["message"]

    @patch("main.log_error")
    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_B_try_again_later_decline_code_surfaced_in_log(
        self, mock_update, mock_verify, mock_cfg, mock_audit, mock_log,
    ):
        """Boundary: the user's literal question was 'what does try_again_
        later mean.' Specifically verify that decline_code, when its value
        is the string 'try_again_later', flows through to the log message
        verbatim so admins can grep for it (rather than every decline
        flattening to the same generic 'Your card was declined.')."""
        last_err = MagicMock()
        last_err.message = "Your card was declined."
        last_err.code = "card_declined"
        last_err.decline_code = "try_again_later"
        mock_verify.return_value = _event(
            "payment_intent.payment_failed",
            _stripe_obj(
                id="pi_decline_004",
                metadata={"booking_reference": "TAG-DECLINE04"},
                last_payment_error=last_err,
            ),
        )
        mock_update.return_value = (None, False)
        _override_db(MagicMock())

        resp = _post({})
        assert resp.status_code == 200

        log_kwargs = mock_log.call_args.kwargs
        assert "decline_code=try_again_later" in log_kwargs["message"]
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["event_data"]["decline_code"] == "try_again_later"


# ============================================================================
# charge.refunded — Edge (full / partial / no payment found)
# ============================================================================

class TestChargeRefunded:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    def test_E_full_refund_marks_payment_refunded(self, mock_verify, mock_cfg, mock_audit):
        payment = _mock_payment(intent_id="pi_refund_001")
        payment.status = PaymentStatus.SUCCEEDED
        db = _wire_payment_lookup(payment)

        refund_obj = MagicMock()
        refund_obj.data = [{"id": "re_001"}]
        mock_verify.return_value = _event(
            "charge.refunded",
            _stripe_obj(
                id="ch_001",
                amount=8500,
                amount_refunded=8500,
                payment_intent="pi_refund_001",
                metadata={"booking_reference": "TAG-HUEB005"},
                refunds=refund_obj,
            ),
        )
        _override_db(db)

        resp = _post({})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "refunded"
        assert body["payment_intent_id"] == "pi_refund_001"
        assert payment.status == PaymentStatus.REFUNDED
        assert payment.refund_amount_pence == 8500
        assert payment.refund_id == "re_001"

    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    def test_E_partial_refund_marks_payment_partially_refunded(
        self, mock_verify, mock_cfg, mock_audit
    ):
        payment = _mock_payment(intent_id="pi_refund_002")
        payment.status = PaymentStatus.SUCCEEDED
        db = _wire_payment_lookup(payment)

        refund_obj = MagicMock()
        refund_obj.data = [{"id": "re_002"}]
        mock_verify.return_value = _event(
            "charge.refunded",
            _stripe_obj(
                id="ch_002",
                amount=10000,
                amount_refunded=2500,  # 25% partial
                payment_intent="pi_refund_002",
                metadata={"booking_reference": "TAG-HUEB006"},
                refunds=refund_obj,
            ),
        )
        _override_db(db)

        resp = _post({})
        assert resp.status_code == 200
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
        assert payment.refund_amount_pence == 2500

    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    def test_E_refund_when_payment_not_in_db(self, mock_verify, mock_cfg, mock_audit):
        """No matching Payment row — endpoint should still respond 200
        (the refund-related audit log still fires; no DB write happens)."""
        db = _wire_payment_lookup(None)
        refund_obj = MagicMock()
        refund_obj.data = []
        mock_verify.return_value = _event(
            "charge.refunded",
            _stripe_obj(
                id="ch_unknown",
                amount=8500,
                amount_refunded=8500,
                payment_intent="pi_unknown",
                metadata={"booking_reference": "TAG-HUEB007"},
                refunds=refund_obj,
            ),
        )
        _override_db(db)
        resp = _post({})
        assert resp.status_code == 200
        assert resp.json()["status"] == "refunded"

    @patch("main.log_audit_event")
    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    def test_E_refund_without_payment_intent_id_does_not_crash(
        self, mock_verify, mock_cfg, mock_audit
    ):
        """Stripe's charge.refunded always carries payment_intent — but
        defend against absent value (the endpoint guards with `if
        payment_intent_id`)."""
        refund_obj = MagicMock()
        refund_obj.data = []
        mock_verify.return_value = _event(
            "charge.refunded",
            _stripe_obj(
                id="ch_no_pi",
                amount=8500,
                amount_refunded=8500,
                payment_intent=None,
                metadata={"booking_reference": "TAG-HUEB008"},
                refunds=refund_obj,
            ),
        )
        _override_db(MagicMock())
        resp = _post({})
        assert resp.status_code == 200


# ============================================================================
# Idempotency + unknown events — Boundary
# ============================================================================

class TestIdempotencyAndUnknownEvents:
    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    def test_B_unknown_event_type_returns_200_silently(self, mock_verify, mock_cfg):
        """Stripe sends ~150 event types — we only act on ~5. The rest must
        be ack'd 200 OK so Stripe doesn't keep retrying them."""
        mock_verify.return_value = _event(
            "customer.subscription.updated",  # we don't handle subscriptions
            _stripe_obj(id="sub_001"),
        )
        _override_db(MagicMock())
        resp = _post({})
        assert resp.status_code == 200

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_B_duplicate_webhook_already_processed_no_side_effects(
        self, mock_update, mock_verify, mock_cfg
    ):
        """update_payment_status returns (payment, was_already_processed=True)
        on duplicate. Endpoint must skip the planner/auto-roster background
        tasks and still respond 200."""
        payment = _mock_payment()
        mock_update.return_value = (payment, True)  # already-processed flag set

        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_dup_001",
                metadata={"booking_reference": "TAG-HUEB009"},
            ),
        )
        _override_db(_wire_payment_lookup(payment))

        with patch("roster_planner_runner.fire_engine_async") as mock_planner:
            with patch("auto_roster.auto_create_or_extend_async") as mock_roster:
                resp = _post({})
                assert resp.status_code == 200
                # Duplicate → no background tasks should be queued.
                mock_planner.assert_not_called()
                mock_roster.assert_not_called()

    @patch("main.is_stripe_configured", return_value=True)
    @patch("main.verify_webhook_signature")
    @patch("db_service.update_payment_status")
    def test_B_succeeded_without_db_payment_row_handled_gracefully(
        self, mock_update, mock_verify, mock_cfg
    ):
        """Manual booking payment links — Stripe sends webhook but our DB
        has no Payment row yet. Endpoint should not 5xx; admin confirms
        manually via separate flow."""
        mock_update.return_value = (None, False)  # payment lookup miss
        mock_verify.return_value = _event(
            "payment_intent.succeeded",
            _stripe_obj(
                id="pi_manual_001",
                metadata={"booking_reference": "TAG-HUEB010"},
            ),
        )
        _override_db(MagicMock())
        resp = _post({})
        assert resp.status_code == 200
