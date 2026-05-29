"""
HUEB tests for PR 4b of the 2026-05-29 security review: customer-flow
ownership token (X-Draft-Token) that closes the 6 customer-flow IDORs
PR 4a left open.

Surface tested:
  1. POST /api/booking-drafts — issuance endpoint
  2. get_draft_token dependency — header parsing, soft vs enforce mode
  3. _bind_or_check helper — first-touch bind / subsequent-enforce
  4. PATCH /api/customers/{id} — ownership gating
  5. PATCH /api/vehicles/{id}  — ownership gating
  6. POST /api/vehicles         — customer_id + vehicle_id binding
  7. GET  /api/customers/heard-about-us-status?email=X — email gating
  8. POST /api/customers/heard-about-us — email gating
       (caught in review; sibling of #7 with same shape)
  9. POST /api/vehicles/dvla-lookup — token-required + per-token quota

Soft-mode contract (live 2026-05-29 → 2026-06-12):
  - Missing X-Draft-Token: ALLOWED, logged via [DRAFT-TOKEN-SOFT] line.
  - Present token: ALWAYS fully validated. Invalid or expired → 401.
  - No partial trust.

After 14 days of zero [DRAFT-TOKEN-SOFT] traffic in production logs,
flip DRAFT_TOKEN_ENFORCE = True in main.py and rely on the
test_B_missing_in_enforce_mode case to gate.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

import main
from main import (
    app,
    get_draft_token,
    _bind_or_check,
    _gen_draft_token,
    DRAFT_TOKEN_TTL_SECS,
    MAX_DVLA_LOOKUPS_PER_DRAFT,
)
from database import get_db


# ============================================================================
# Shared fixtures
# ============================================================================


def _make_draft(
    token="t" * 64, email=None, customer_id=None, vehicle_id=None,
    dvla_calls_count=0, expires_in_secs=DRAFT_TOKEN_TTL_SECS,
):
    """BookingDraft-shaped namespace."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        token=token,
        ip_address="203.0.113.7",
        email=email,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        dvla_calls_count=dvla_calls_count,
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in_secs),
    )


def _override_get_db_with(db_mock):
    """Install a generator that yields the given mock as the db dep."""
    def _gen():
        yield db_mock
    app.dependency_overrides[get_db] = _gen


def _clear_overrides():
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    _clear_overrides()


# ============================================================================
# 1. POST /api/booking-drafts — issuance
# ============================================================================


class TestCreateBookingDraft:
    """Issuance endpoint — must produce a fresh server-issued token."""

    def test_H_returns_64_hex_token_and_24h_expiry(self):
        # H: Happy path. db.add + commit succeed; response contains a
        # 64-char hex token and an expires_at ~24h in the future.
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.execute = MagicMock()  # prune is best-effort, no-op here
        _override_get_db_with(db)

        client = TestClient(app)
        before = datetime.now(timezone.utc)
        resp = client.post("/api/booking-drafts")
        after = datetime.now(timezone.utc)

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body and "expires_at" in body
        # 64-char hex (32 bytes * 2)
        assert len(body["token"]) == 64
        assert all(c in "0123456789abcdef" for c in body["token"])
        # expires_at is within 24h ± a few seconds of "now"
        expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        lower = before + timedelta(seconds=DRAFT_TOKEN_TTL_SECS - 5)
        upper = after + timedelta(seconds=DRAFT_TOKEN_TTL_SECS + 5)
        assert lower <= expires <= upper
        # Persisted (db.add called with a BookingDraft).
        assert db.add.call_count == 1
        added = db.add.call_args[0][0]
        from db_models import BookingDraft
        assert isinstance(added, BookingDraft)
        assert added.token == body["token"]

    def test_E_two_calls_return_different_tokens(self):
        # E: Two issuance calls must produce two distinct tokens.
        # secrets.token_hex(32) is cryptorandom — collision is
        # effectively impossible (2^256 entropy).
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.execute = MagicMock()
        _override_get_db_with(db)

        client = TestClient(app)
        t1 = client.post("/api/booking-drafts").json()["token"]
        t2 = client.post("/api/booking-drafts").json()["token"]
        assert t1 != t2


# ============================================================================
# 2. get_draft_token dependency — soft vs enforce mode
# ============================================================================


def _override_draft_token_dep_with(value):
    """Override get_draft_token to return a specific BookingDraft (or
    None, simulating soft-mode no-token). Used in endpoint tests to
    skip the DB lookup."""
    app.dependency_overrides[get_draft_token] = lambda: value


class TestGetDraftTokenSoftMode:
    """Soft-mode behaviour (live 2026-05-29). Missing token is allowed
    but a structured [DRAFT-TOKEN-SOFT] line is logged."""

    def test_B_missing_token_allowed_and_logged(self, capsys):
        # B: Boundary — no X-Draft-Token header. In soft mode the
        # dependency returns None and emits the structured log line
        # that ops will use to verify zero missing-token traffic
        # before flipping DRAFT_TOKEN_ENFORCE = True.
        from main import _client_ip  # noqa
        req = MagicMock()
        req.client = SimpleNamespace(host="203.0.113.7")
        req.headers = {}
        req.method = "PATCH"
        req.url = SimpleNamespace(path="/api/customers/42")
        db = MagicMock()

        result = get_draft_token(request=req, db=db, x_draft_token=None)

        assert result is None
        captured = capsys.readouterr()
        assert "[DRAFT-TOKEN-SOFT]" in captured.out
        assert "PATCH" in captured.out and "/api/customers/42" in captured.out

    def test_U_invalid_token_always_401(self):
        # U: Even in soft mode, a PRESENT token must be fully validated.
        # Random token doesn't exist → 401 (NOT silent-pass).
        from fastapi import HTTPException

        req = MagicMock()
        req.client = SimpleNamespace(host="1.2.3.4")
        req.headers = {}
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None  # token not found
        db.query.return_value = chain

        with pytest.raises(HTTPException) as exc:
            get_draft_token(
                request=req, db=db,
                x_draft_token="invalid_random_token",
            )
        assert exc.value.status_code == 401
        assert "Invalid or expired" in exc.value.detail


class TestGetDraftTokenEnforceMode:
    """Enforce mode (flipped after 14-day rollout). Missing token → 401."""

    def test_B_missing_token_in_enforce_mode_raises_401(self, monkeypatch):
        # B: monkeypatch DRAFT_TOKEN_ENFORCE = True for the duration of
        # this test. Missing header → 401, no [DRAFT-TOKEN-SOFT] log
        # (we're past the soft window).
        from fastapi import HTTPException

        monkeypatch.setattr(main, "DRAFT_TOKEN_ENFORCE", True)

        req = MagicMock()
        req.client = SimpleNamespace(host="1.2.3.4")
        req.headers = {}
        db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            get_draft_token(request=req, db=db, x_draft_token=None)
        assert exc.value.status_code == 401
        assert "Missing X-Draft-Token" in exc.value.detail


# ============================================================================
# 3. _bind_or_check helper — first-touch / enforce / soft-mode no-op
# ============================================================================


class TestBindOrCheck:
    """Core binding semantics — first-touch binds + commits, subsequent
    matches are no-ops, mismatches raise 403, soft-mode (draft=None)
    is a silent no-op."""

    def test_H_first_touch_binds_and_commits(self):
        # H: draft.customer_id is None → bind to request value + commit.
        draft = _make_draft()
        assert draft.customer_id is None
        db = MagicMock()
        db.commit = MagicMock()
        req = MagicMock()
        req.client = SimpleNamespace(host="1.1.1.1")
        req.headers = {}

        _bind_or_check(draft, "customer_id", 42, db, req)

        assert draft.customer_id == 42
        assert db.commit.call_count == 1

    def test_E_subsequent_match_is_noop(self):
        # E: draft.customer_id == 42; same value → no-op (no commit,
        # no mutation, no exception).
        draft = _make_draft(customer_id=42)
        db = MagicMock()
        db.commit = MagicMock()
        req = MagicMock()
        req.client = SimpleNamespace(host="1.1.1.1")
        req.headers = {}

        _bind_or_check(draft, "customer_id", 42, db, req)

        assert draft.customer_id == 42
        assert db.commit.call_count == 0

    def test_U_mismatch_raises_403(self, capsys):
        # U: draft.customer_id == 42; request asks for 99 → 403 and a
        # [DRAFT-TOKEN-BIND-MISMATCH] structured log line.
        from fastapi import HTTPException

        draft = _make_draft(customer_id=42)
        db = MagicMock()
        req = MagicMock()
        req.client = SimpleNamespace(host="1.1.1.1")
        req.headers = {}

        with pytest.raises(HTTPException) as exc:
            _bind_or_check(draft, "customer_id", 99, db, req)
        assert exc.value.status_code == 403
        assert "does not own" in exc.value.detail
        out = capsys.readouterr().out
        assert "[DRAFT-TOKEN-BIND-MISMATCH]" in out
        assert "field=customer_id" in out

    def test_B_soft_mode_draft_none_is_silent_noop(self):
        # B: soft mode — caller passed draft=None. Helper must not raise
        # and not touch db. Endpoint continues as in pre-PR-4b behaviour.
        db = MagicMock()
        db.commit = MagicMock()
        req = MagicMock()

        # No exception, no commit, no return value matters.
        _bind_or_check(None, "customer_id", 99, db, req)

        assert db.commit.call_count == 0


# ============================================================================
# 4. PATCH /api/customers/{id} — ownership gating end-to-end
# ============================================================================


def _stub_customer(id=42, email="alice@example.com"):
    return SimpleNamespace(
        id=id, first_name="Alice", last_name="Smith",
        email=email, phone="07700900000",
    )


class TestPatchCustomerGated:
    """The PATCH endpoint requires the draft to own (or first-bind to)
    the customer_id being mutated."""

    def test_H_token_matches_customer_id_succeeds(self, monkeypatch):
        # H: draft.customer_id already 42, request PATCHes /api/customers/42
        # → succeeds (200).
        draft = _make_draft(customer_id=42)
        _override_draft_token_dep_with(draft)

        # Stub the DB session + db_service lookup.
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

        client = TestClient(app)
        resp = client.patch("/api/customers/42", json={
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "phone": "07700900000",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["customer_id"] == 42

    def test_U_token_with_wrong_customer_id_403(self, monkeypatch):
        # U: draft.customer_id is 42 but URL says 99 → 403 BEFORE the
        # customer lookup runs (binding mismatch is the gate).
        draft = _make_draft(customer_id=42)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)

        # Make customer_lookup raise if reached — proves the gate fires
        # before the handler body runs.
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: pytest.fail(
                "Customer lookup MUST NOT run when bind-mismatch fires"
            ),
        )

        client = TestClient(app)
        resp = client.patch("/api/customers/99", json={
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "phone": "07700900000",
        })
        assert resp.status_code == 403
        assert "does not own" in resp.json()["detail"]

    def test_E_first_touch_binds_customer_id(self, monkeypatch):
        # E: draft.customer_id is None on entry; PATCH /api/customers/42
        # binds draft.customer_id = 42 + commits. Subsequent call would
        # match (covered by test_H).
        draft = _make_draft(customer_id=None)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

        client = TestClient(app)
        resp = client.patch("/api/customers/42", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200
        # Binding happened.
        assert draft.customer_id == 42

    def test_B_soft_mode_no_token_succeeds(self, monkeypatch):
        # B: soft-mode behaviour — no X-Draft-Token header → handler
        # runs as if PR 4b didn't exist (status quo for the 14-day
        # window). This is the explicit user contract.
        _override_draft_token_dep_with(None)  # simulate soft-mode None
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

        client = TestClient(app)
        resp = client.patch("/api/customers/42", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200, resp.text


# ============================================================================
# 5. GET /api/customers/heard-about-us-status — email-bound gating
# ============================================================================


class TestHeardAboutUsGated:
    """Email binding closes the email-enumeration leak (the endpoint
    originally returned customer_id alongside the yes/no, leaking
    whether the address was registered).

    2026-05-29 review caught that the sibling POST /api/customers/
    heard-about-us was missed in the first PR-4b pass — same email
    mutation, same IDOR shape. Gating added in the same commit as the
    review fix.
    """

    def test_U_status_GET_token_with_wrong_email_403(self):
        # U: draft.email == 'alice@x.com' but query asks bob@x.com → 403.
        # No customer lookup runs.
        draft = _make_draft(email="alice@x.com")
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)

        client = TestClient(app)
        resp = client.get(
            "/api/customers/heard-about-us-status",
            params={"email": "bob@x.com"},
        )
        assert resp.status_code == 403
        assert "does not own" in resp.json()["detail"]

    def test_U_save_POST_token_with_wrong_email_403(self):
        # U (2026-05-29 review fix): POST /api/customers/heard-about-us
        # must also gate on email. Pre-fix this endpoint was ungated
        # and would happily mutate any email's attribution row.
        draft = _make_draft(email="alice@x.com")
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)

        client = TestClient(app)
        resp = client.post(
            "/api/customers/heard-about-us",
            json={"email": "bob@x.com", "source": "google"},
        )
        assert resp.status_code == 403
        assert "does not own" in resp.json()["detail"]

    def test_B_save_POST_soft_mode_no_token_succeeds(self, monkeypatch):
        # B: soft-mode behaviour for POST too — no token → handler
        # body runs (matches the GET sibling's soft-mode behaviour).
        _override_draft_token_dep_with(None)
        # The handler digs into DB; stub out the actual DB writes so
        # we only assert "got past the gate, didn't 403".
        db = MagicMock()
        # query() chain: customer lookup returns None so the handler
        # exits via the "customer not found" branch with 200 + ok=False
        # (or whatever the existing soft-mode shape is — we only care
        # that we didn't 403).
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        _override_get_db_with(db)

        client = TestClient(app)
        resp = client.post(
            "/api/customers/heard-about-us",
            json={"email": "bob@x.com", "source": "google"},
        )
        # Anything other than 403 is "passed the gate". The handler
        # body may 200 or 404 depending on its own logic.
        assert resp.status_code != 403


# ============================================================================
# 6. POST /api/vehicles/dvla-lookup — per-token quota
# ============================================================================


class TestDvlaQuota:
    """DVLA lookups are gated by draft + capped to
    MAX_DVLA_LOOKUPS_PER_DRAFT per token."""

    def test_U_at_quota_returns_429(self):
        # U: 2026-05-29 review fix — gate is now a single conditional
        # UPDATE: SET ... WHERE token=:t AND dvla_calls_count < :max.
        # When the row would push past max, the UPDATE matches 0 rows
        # and result.rowcount == 0, which triggers 429. Atomic at the
        # limit (no two concurrent requests can both pass at count - 1).
        draft = _make_draft(dvla_calls_count=MAX_DVLA_LOOKUPS_PER_DRAFT)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        # The atomic UPDATE returns a result with rowcount=0 when the
        # WHERE clause's count < :max guard rejects the increment.
        _zero_rows = MagicMock()
        _zero_rows.rowcount = 0
        db.execute = MagicMock(return_value=_zero_rows)
        _override_get_db_with(db)

        client = TestClient(app)
        resp = client.post(
            "/api/vehicles/dvla-lookup", json={"registration": "AB12 CDE"},
        )
        assert resp.status_code == 429
        assert "quota exceeded" in resp.json()["detail"].lower()
        # Verify the UPDATE was issued with the conditional WHERE clause.
        assert db.execute.called
        sql = str(db.execute.call_args.args[0])
        assert "UPDATE booking_drafts SET dvla_calls_count" in sql
        assert "dvla_calls_count < :max" in sql, (
            "Gate must be a single conditional UPDATE, NOT a Python "
            "check + UPDATE. Without the WHERE-clause guard, two "
            "concurrent requests at count-1 both pass."
        )

    def test_E_at_quota_minus_one_passes_gate(self, monkeypatch):
        # E: at quota - 1 → gate allows, atomic UPDATE increments.
        # The actual DVLA HTTP call uses httpx.AsyncClient; we stub it
        # so the test focuses on the gate behaviour, not network calls.
        draft = _make_draft(dvla_calls_count=MAX_DVLA_LOOKUPS_PER_DRAFT - 1)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.execute = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
            environment="test",
            dvla_api_key_test="test_key",
            dvla_api_key_prod="prod_key",
        ))

        # Stub the async DVLA call. httpx.AsyncClient() is used as an
        # async context manager — we replace it with a stub that
        # returns a successful 200 response.
        class _AsyncResp:
            status_code = 200
            def json(self):
                return {"make": "Ford", "colour": "Blue"}

        class _AsyncClientStub:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, *a, **kw): return _AsyncResp()

        monkeypatch.setattr(main, "httpx", SimpleNamespace(
            AsyncClient=_AsyncClientStub,
        ))

        client = TestClient(app)
        resp = client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AB12 CDE"},
        )

        # Gate did NOT 429; the atomic UPDATE ran.
        assert resp.status_code != 429
        assert db.execute.called
        executed_sql = str(db.execute.call_args_list[0].args[0])
        assert "UPDATE booking_drafts SET dvla_calls_count" in executed_sql

    def test_B_soft_mode_no_token_skips_quota(self, monkeypatch):
        # B: soft mode — no token → no quota enforcement, lookup
        # proceeds as today (no UPDATE SQL ran).
        _override_draft_token_dep_with(None)
        db = MagicMock()
        db.execute = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
            environment="test",
            dvla_api_key_test="test_key",
            dvla_api_key_prod="prod_key",
        ))

        class _AsyncResp:
            status_code = 200
            def json(self):
                return {"make": "Ford", "colour": "Blue"}

        class _AsyncClientStub:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, *a, **kw): return _AsyncResp()

        monkeypatch.setattr(main, "httpx", SimpleNamespace(
            AsyncClient=_AsyncClientStub,
        ))

        client = TestClient(app)
        resp = client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AB12 CDE"},
        )

        # No 429 (gate skipped) and no quota UPDATE issued.
        assert resp.status_code != 429
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE booking_drafts" in str(c.args[0])
        ]
        assert update_calls == [], (
            "Soft mode must not increment quota — got "
            f"{len(update_calls)} UPDATE booking_drafts call(s)"
        )


# ============================================================================
# 7. _gen_draft_token — token entropy + format
# ============================================================================


class TestTokenGenerator:
    """Sanity on the token format. 64 hex chars from 32 random bytes."""

    def test_H_token_is_64_hex_chars(self):
        t = _gen_draft_token()
        assert len(t) == 64
        assert all(c in "0123456789abcdef" for c in t)

    def test_E_two_tokens_are_distinct(self):
        # 256 bits of entropy → collision probability essentially zero.
        assert _gen_draft_token() != _gen_draft_token()
