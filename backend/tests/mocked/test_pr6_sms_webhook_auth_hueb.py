"""
HUEB tests for PR 6 of the 2026-05-29 security review: SMS webhook
authentication via URL-path shared secret.

Closes:
  - POST /api/webhooks/sms/incoming         DELETED (one-way SMS only;
                                            every outbound message says
                                            "please do not reply", so no
                                            legitimate inbound traffic
                                            exists. Removing the route
                                            eliminates the IDOR surface
                                            entirely instead of just
                                            gating it.)
  - POST /api/webhooks/sms/delivery-report/{secret}  GATED

Pre-PR-6 both were unauthenticated. The delivery-report endpoint let
an attacker flip outbound SMS delivery state to DELIVERED or FAILED by
guessing a messageid.

Why URL-path token on delivery-report, not header: SMS Works' dashboard
exposes only a URL input on its webhook config screen (verified
2026-05-29 against thesmsworks.co.uk/account). No custom-header field,
no auth dropdown. So the secret rides in the URL.

PR 6 adds _verify_sms_webhook_secret(secret) called inside the
delivery-report handler that:
  - 503 if SMS_WEBHOOK_SECRET env var is unset (fail closed)
  - 401 if path-param secret is missing or mismatched
  - uses secrets.compare_digest for constant-time comparison
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

import main
from main import app
from database import get_db


SECRET = "49e86ef95f96304e2c1505e82dcd992e50bd2262ac86b1b436c0d71124eb00fa"


@pytest.fixture
def stub_db():
    """Empty mock db; the gated handlers don't touch it on auth-fail
    paths, and success paths have sms_service helpers stubbed."""
    db = MagicMock()
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def set_secret(monkeypatch):
    monkeypatch.setenv("SMS_WEBHOOK_SECRET", SECRET)


@pytest.fixture
def unset_secret(monkeypatch):
    monkeypatch.delenv("SMS_WEBHOOK_SECRET", raising=False)


@pytest.fixture
def stub_sms_handlers(monkeypatch):
    monkeypatch.setattr(
        main.sms_service, "handle_incoming_sms",
        lambda payload, db: True,
    )
    monkeypatch.setattr(
        main.sms_service, "handle_delivery_report",
        lambda payload, db: True,
    )


# ============================================================================
# /api/webhooks/sms/incoming — DELETED (regression pin)
# ============================================================================


class TestIncomingRouteIsGone:
    """The inbound webhook route was removed entirely in PR 6 because
    TAG sends one-way SMS only — every outbound message includes
    "please do not reply", so there is no legitimate inbound traffic.
    Pin that the route stays gone so a future commit that re-registers
    POST /api/webhooks/sms/incoming (with or without a {secret} suffix)
    fails this test loudly. If two-way SMS ever becomes a feature, the
    re-add MUST come with the {secret} gate from day one — and that
    re-add is the right time to update this file."""

    def test_H_legacy_unauth_url_404_or_405(self):
        # H: The pre-PR-6 unauth URL must not be routable.
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/sms/incoming",
            json={"from": "+447700900000", "content": "spoofed",
                  "messageid": "msg_x"},
        )
        assert resp.status_code in (404, 405), (
            f"Expected 404/405 (route gone); got {resp.status_code}. "
            f"If 200 — the inbound IDOR surface was re-introduced."
        )

    def test_U_gated_url_with_any_secret_404(self, monkeypatch):
        # U: Even the secret-bearing URL form is not registered. The
        # delivery-report sibling exists at /delivery-report/{secret};
        # this one does not exist at all.
        monkeypatch.setenv("SMS_WEBHOOK_SECRET", SECRET)
        client = TestClient(app)
        resp = client.post(
            f"/api/webhooks/sms/incoming/{SECRET}",
            json={"from": "+447700900000", "content": "spoofed"},
        )
        assert resp.status_code in (404, 405)


# ============================================================================
# /api/webhooks/sms/delivery-report/{secret}
# ============================================================================


class TestDeliveryReportWebhookAuth:
    """Delivery-report webhook now demands the URL-path secret. Pre-fix
    an attacker could flip any outbound SMSMessage row to DELIVERED or
    FAILED by guessing its messageid."""

    def test_H_valid_secret_returns_200(
        self, stub_db, set_secret, stub_sms_handlers,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/webhooks/sms/delivery-report/{SECRET}",
            json={"messageid": "msg_1", "status": "DELIVERED"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

    def test_U_legacy_no_token_path_404_or_405(
        self, stub_db, set_secret, stub_sms_handlers,
    ):
        # U: Legacy unauth URL must be closed.
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/sms/delivery-report",
            json={"messageid": "msg_1", "status": "DELIVERED"},
        )
        assert resp.status_code in (404, 405)

    def test_U_wrong_secret_returns_401(
        self, stub_db, set_secret, stub_sms_handlers,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/sms/delivery-report/wrong",
            json={"messageid": "msg_1", "status": "FAILED"},
        )
        assert resp.status_code == 401

    def test_E_env_unset_returns_503(
        self, stub_db, unset_secret, stub_sms_handlers,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/webhooks/sms/delivery-report/{SECRET}",
            json={"messageid": "msg_1", "status": "DELIVERED"},
        )
        assert resp.status_code == 503

    def test_B_trailing_slash_returns_200_not_307(
        self, stub_db, set_secret, stub_sms_handlers,
    ):
        # B: 2026-05-29 review fix regression. PR 6 initially registered
        # only the no-trailing-slash form, which made FastAPI 307-redirect
        # the trailing-slash variant to the canonical form. SMS Works (and
        # webhook providers in general) often DON'T follow 307 on POST,
        # or treat the redirect as failed and never retry — silently
        # dropping delivery reports. Fix: register BOTH forms directly.
        # follow_redirects=False is essential — TestClient defaults to
        # following redirects, which would mask a 307 as a 200.
        client = TestClient(app)
        resp = client.post(
            f"/api/webhooks/sms/delivery-report/{SECRET}/",
            json={"messageid": "msg_1", "status": "DELIVERED"},
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"Expected 200 on trailing-slash POST; got {resp.status_code}. "
            f"If 307 — the dual @app.post decorator was dropped and "
            f"SMS Works deliveries will silently fail."
        )
        assert resp.json() == {"success": True}


# ============================================================================
# Constant-time compare invariant
# ============================================================================


class TestConstantTimeCompare:
    """The reviewer asked for hmac.compare_digest (or
    secrets.compare_digest — same algorithm) so an attacker can't
    time the comparison to discover prefix matches one byte at a
    time. Pin that the verifier uses one of those, not the == operator.
    """

    def test_H_verifier_uses_constant_time_compare(self):
        import inspect
        src = inspect.getsource(main._verify_sms_webhook_secret)
        assert (
            "secrets.compare_digest" in src
            or "hmac.compare_digest" in src
        ), (
            "_verify_sms_webhook_secret must use constant-time compare "
            "(secrets.compare_digest or hmac.compare_digest). Found "
            "neither in the source — a switch to == would leak the "
            "secret one byte at a time via timing attack."
        )


# ============================================================================
# URL is not logged
# ============================================================================


class TestUrlNotLogged:
    """The handler MUST NOT print the request URL (which contains the
    secret). Pin that the only log line written by the handler body
    is the body-only [SMS WEBHOOK] line, not a full-URL line."""

    def test_H_handler_does_not_print_url(self):
        import inspect
        src = inspect.getsource(main.webhook_sms_delivery)
        assert "request.url" not in src, (
            "webhook_sms_delivery prints request.url, which would "
            "leak the URL-path secret into logs. Strip it."
        )
        assert "request.path" not in src, (
            "webhook_sms_delivery prints request.path; same leak."
        )
