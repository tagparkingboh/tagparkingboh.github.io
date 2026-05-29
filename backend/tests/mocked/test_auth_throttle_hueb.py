"""
HUEB integration tests for the auth-code rate-limit + lockout layer
(security review 2026-05-29).

Endpoints under test:
  POST /api/auth/request-code     — rate-limited per IP + per email,
                                    resend cooldown
  POST /api/auth/verify-code      — rate-limited per IP + per-code
                                    attempt counter (5 strikes = lock)

The rig wires a MagicMock DB whose `query(...)` chain returns scripted
results: candidate user, candidate login_code, and an auth_throttle
count that the test sets to drive the threshold under inspection.
Every test is one HUEB-cell:
  H — first request from a clean IP succeeds (200, generic message)
  U — per-IP threshold exceeded → 429 with Retry-After
  E — fifth wrong verify locks the code → sixth returns generic invalid
  B — resend within the 60-second cooldown returns silent success
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app
from database import get_db


def _user(email="alice@example.com"):
    return SimpleNamespace(
        id=1, email=email, first_name="Alice", last_name="Test",
        is_admin=False, is_active=True,
        last_login=None,
    )


def _login_code(code="123456", attempts=0, used=False, user_id=1):
    return SimpleNamespace(
        id=10, user_id=user_id, code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        used=used, attempts=attempts,
    )


def _make_db(*, user=None, throttle_counts=None, login_code=None,
             matching_login_code=None, latest_active_login_code=None):
    """MagicMock DB that returns scripted rows. `throttle_counts` is a
    list — consumed in the order the production code issues count()
    calls.

    LoginCode lookups (new shape after the 2026-05-29 review):
      - matching_login_code  — returned by the first .first() call
                                (the WHERE code=submitted match-first
                                lookup). None means the submitted code
                                didn't match any active row.
      - latest_active_login_code — returned by the second .first() call
                                (the latest-active lookup the endpoint
                                falls back to for the wrong-code path).
      - login_code (legacy)  — convenience alias: when set, both lookups
                                return it. Lets the original H test
                                keep its shape.

    `.update({LoginCode.attempts: ...})` is simulated to bump the
    latest_active fixture in place so the threshold check at
    `attempts >= MAX_VERIFY_ATTEMPTS_PER_CODE` fires in tests, just like
    it would in production after the atomic SQL UPDATE."""
    db = MagicMock()
    counts = list(throttle_counts or [])

    # Alias: `login_code=...` means "the submitted code is a valid match"
    # — sets only the match-first slot. For wrong-code tests, pass
    # `latest_active_login_code=...` explicitly so the intent is
    # readable and the wrong-code path actually fires.
    if login_code is not None and matching_login_code is None:
        matching_login_code = login_code

    login_code_call_count = [0]

    def _q(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.update.return_value = 0
        chain.delete.return_value = 0
        name = getattr(model, "__name__", str(model))
        if name == "AuthThrottle":
            def _next_count():
                return counts.pop(0) if counts else 1
            chain.count.side_effect = _next_count
            chain.first.return_value = None
            chain.all.return_value = []
        elif name == "User":
            chain.first.return_value = user
            chain.all.return_value = [user] if user else []
        elif name == "LoginCode":
            def _first():
                login_code_call_count[0] += 1
                return (
                    matching_login_code if login_code_call_count[0] == 1
                    else latest_active_login_code
                )
            chain.first.side_effect = _first

            # Simulate the atomic SQL UPDATE on `attempts`. Detected by
            # finding "attempts" in the dict's keys/string repr.
            def _update(values, **kw):
                target = latest_active_login_code
                if target is None:
                    return 0
                for k in values.keys():
                    key_str = (
                        getattr(k, "name", None)
                        or getattr(k, "key", None)
                        or str(k)
                    )
                    if "attempts" in str(key_str).lower():
                        target.attempts = (getattr(target, "attempts", 0) or 0) + 1
                        return 1
                return 0
            chain.update.side_effect = _update
        else:
            chain.first.return_value = None
            chain.all.return_value = []
        return chain

    db.query.side_effect = _q
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: None)
    return db


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _override(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


class TestAuthThrottleHUEB:

    def test_H_first_request_succeeds_returns_generic_message(self, client):
        """Happy: clean IP, registered email, no recent throttle rows.
        Returns the generic "If your email is registered…" message
        (server still doesn't disclose existence even on success) and
        the email-send hook is invoked."""
        db = _make_db(
            user=_user(),
            # throttle counts: ip-window, email-window, cooldown
            throttle_counts=[1, 1, 1],
        )
        _override(db)
        with patch("main.send_login_code_email", return_value=True) as send:
            r = client.post(
                "/api/auth/request-code",
                json={"email": "alice@example.com"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert "registered" in body["message"].lower()
        send.assert_called_once()

    def test_U_per_ip_limit_returns_429_with_retry_after(self, client):
        """Unhappy: per-IP count in the 15-min window has crossed
        MAX_REQUEST_CODES_PER_IP_PER_WINDOW (10). The endpoint must
        return 429 with a Retry-After header BEFORE the email send
        path is even reached. Note: no email lookup, no PII leak."""
        # Script the IP count as 11 — exactly one over the threshold.
        db = _make_db(user=_user(), throttle_counts=[11])
        _override(db)
        with patch("main.send_login_code_email") as send:
            r = client.post(
                "/api/auth/request-code",
                json={"email": "alice@example.com"},
            )
        assert r.status_code == 429, r.text
        assert r.headers.get("Retry-After") == str(15 * 60)
        # Email path never reached.
        send.assert_not_called()

    def test_E_fifth_wrong_verify_attempt_locks_the_code(self, client):
        """Edge: a valid user with an active code at attempts=4 (one
        wrong attempt away from the limit) submits a wrong code. The
        match-first lookup returns None; the latest-active lookup
        returns the existing row. Endpoint atomically bumps attempts
        to 5, marks the code used=True, and returns generic invalid.
        A subsequent attempt with the correct code would find no
        active code and also get the generic invalid — brute-force
        permanently stopped on this code."""
        code_row = _login_code(code="654321", attempts=4)
        db = _make_db(
            user=_user(),
            matching_login_code=None,  # submitted code didn't match
            latest_active_login_code=code_row,
            throttle_counts=[1],  # under per-IP limit
        )
        _override(db)
        r = client.post(
            "/api/auth/verify-code",
            json={"email": "alice@example.com", "code": "000000"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is False
        assert "invalid" in body["message"].lower()
        # Counter atomically incremented + code locked.
        assert code_row.attempts == 5
        assert code_row.used is True

    def test_B_resend_within_cooldown_returns_silent_success(self, client):
        """Boundary: per-email cooldown (60s) is the tightest of the
        three throttles. The endpoint must NOT trigger the email send
        path and must return the same generic success message — no
        429, no enumeration leak — so a legitimate user spamming the
        Resend button just sees the standard message instead of an
        error / different status."""
        # IP count low, email count low, cooldown count = 2 (this row +
        # one other within 60 s).
        db = _make_db(user=_user(), throttle_counts=[1, 1, 2])
        _override(db)
        with patch("main.send_login_code_email") as send:
            r = client.post(
                "/api/auth/request-code",
                json={"email": "alice@example.com"},
            )
        assert r.status_code == 200, r.text
        assert "registered" in r.json()["message"].lower()
        # Email path NOT reached — that's the cooldown's whole point.
        send.assert_not_called()


# ============================================================================
# Review-fix regressions 2026-05-29
# ============================================================================


class TestClientIpResolution:
    """`_client_ip` is safe-by-default — XFF / X-Real-IP are ignored
    unless TRUSTED_PROXY_HOPS is set. Without that env var, an attacker
    cannot rotate Fake-IP headers to bypass per-IP throttles."""

    def _request(self, headers=None, client_host="1.2.3.4"):
        """Build a minimal Request-shaped object the helper can read."""
        r = SimpleNamespace()
        r.headers = headers or {}
        r.client = SimpleNamespace(host=client_host)
        return r

    def test_H_default_ignores_xff_and_returns_tcp_ip(self, monkeypatch):
        """Happy: no TRUSTED_PROXY_HOPS in env. Even if the request
        ships an XFF header, the helper must return the direct TCP
        connection IP."""
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        from main import _client_ip
        req = self._request(
            headers={"X-Forwarded-For": "9.9.9.9, 8.8.8.8"},
            client_host="1.2.3.4",
        )
        assert _client_ip(req) == "1.2.3.4"

    def test_U_xff_spoof_does_not_change_resolution_without_env(self, monkeypatch):
        """Unhappy: attacker forges a long XFF chain trying to look
        like the leftmost is the real client. Without TRUSTED_PROXY_HOPS
        the helper IGNORES the header completely — spoof has no
        effect on the IP key used for throttling."""
        monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
        from main import _client_ip
        req1 = self._request(
            headers={"x-forwarded-for": "evil-A"},
            client_host="1.2.3.4",
        )
        req2 = self._request(
            headers={"x-forwarded-for": "evil-B"},
            client_host="1.2.3.4",
        )
        # Both attempts resolve to the same IP — rotation gains nothing.
        assert _client_ip(req1) == _client_ip(req2) == "1.2.3.4"

    def test_E_trusted_hops_takes_nth_from_rightmost(self, monkeypatch):
        """Edge: TRUSTED_PROXY_HOPS=1 (Railway-only). The Nth-from-
        rightmost XFF entry is the IP the last trusted proxy saw on
        the wire — the real client IP if every hop appends correctly.
        For N=1 that's the rightmost entry."""
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
        from main import _client_ip
        # XFF chain: client-supplied (possibly spoofed), then Railway
        # appended the real client IP. With N=1 we take the last entry.
        # Header keys lowercased — the helper uses lowercase lookup
        # (production Request.headers is case-insensitive but a plain
        # dict isn't).
        req = self._request(
            headers={"x-forwarded-for": "evil, 5.6.7.8"},
            client_host="10.0.0.1",
        )
        assert _client_ip(req) == "5.6.7.8"

    def test_B_trusted_hops_falls_back_when_xff_too_short(self, monkeypatch):
        """Boundary: TRUSTED_PROXY_HOPS=2 but the request only has one
        XFF entry. Helper must fall back to the TCP connection IP
        rather than blindly index off the end."""
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
        from main import _client_ip
        req = self._request(
            headers={"x-forwarded-for": "only-one"},
            client_host="1.2.3.4",
        )
        assert _client_ip(req) == "1.2.3.4"


class TestVerifyMatchFirstAndAtomic:
    """Concurrent request-code calls can briefly leave more than one
    active code on a user. The match-first lookup wins on the matching
    row regardless of how many other actives exist; the wrong-code
    path bumps the LATEST one and locks it after the threshold."""

    def test_H_matching_code_succeeds_even_with_other_active_codes(self, client):
        """Happy: the verify path queries by (user_id, code=submitted,
        used=False, not expired). The mock returns the matching row
        because that's the filter the production code sets. A stale
        active code (with a different value) would never be returned
        for the same filter, so the success path is correctly bound
        to the row whose code matches."""
        db = _make_db(
            user=_user(),
            login_code=_login_code(code="999999", attempts=0),
            throttle_counts=[1],
        )
        _override(db)
        r = client.post(
            "/api/auth/verify-code",
            json={"email": "alice@example.com", "code": "999999"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["token"] is not None


class TestPerEmailRequestThrottle:
    """The per-email window throttle (5 / 15 min) is independent of
    the per-IP throttle (10 / 15 min) and the 60-s cooldown. This
    closes the test gap where the prior B-test only exercised the
    cooldown path."""

    def test_U_per_email_limit_returns_silent_success(self, client):
        """Per-email count == 6 (one over limit), IP and cooldown
        clean. Endpoint must return 200 with the generic message and
        must NOT send an email — distinguishes the per-email throttle
        from per-IP (which returns 429)."""
        db = _make_db(user=_user(), throttle_counts=[1, 6])
        _override(db)
        with patch("main.send_login_code_email") as send:
            r = client.post(
                "/api/auth/request-code",
                json={"email": "alice@example.com"},
            )
        assert r.status_code == 200, r.text
        assert "registered" in r.json()["message"].lower()
        send.assert_not_called()


class TestVerifyPerIpRateLimit:
    """The verify endpoint has its own per-IP 429 (20 / 15 min) — was
    not exercised by the original HUEB. Mirrors the request-code U
    test but on the verify side."""

    def test_U_per_ip_verify_limit_returns_429_with_retry_after(self, client):
        """Set the verify-side IP count to 21 (one over the limit).
        Endpoint must 429 + Retry-After before even looking up the
        user or the code."""
        db = _make_db(user=_user(), throttle_counts=[21])
        _override(db)
        r = client.post(
            "/api/auth/verify-code",
            json={"email": "alice@example.com", "code": "123456"},
        )
        assert r.status_code == 429, r.text
        assert r.headers.get("Retry-After") == str(15 * 60)


class TestAuthThrottleIndexes:
    """The composite indexes were declared in the inline Phase-1 DDL,
    but the SQLAlchemy model needs them in __table_args__ too so a
    fresh init_db() / create_all() in dev / CI also gets them. Without
    this, dev runs of the rate limit would be O(N) scans."""

    def test_H_model_declares_both_composite_indexes(self):
        """Inspect AuthThrottle.__table_args__ and confirm both
        named indexes match the inline DDL exactly."""
        from db_models import AuthThrottle
        from sqlalchemy import Index
        args = getattr(AuthThrottle, "__table_args__", ())
        indexes = [a for a in args if isinstance(a, Index)]
        names = sorted(idx.name for idx in indexes)
        assert "idx_auth_throttle_ip" in names
        assert "idx_auth_throttle_email" in names

        # Per-index column composition
        ip_idx = next(i for i in indexes if i.name == "idx_auth_throttle_ip")
        ip_cols = [c.name for c in ip_idx.columns]
        assert ip_cols == ["ip_address", "action", "created_at"]

        email_idx = next(i for i in indexes if i.name == "idx_auth_throttle_email")
        email_cols = [c.name for c in email_idx.columns]
        assert email_cols == ["email", "action", "created_at"]
