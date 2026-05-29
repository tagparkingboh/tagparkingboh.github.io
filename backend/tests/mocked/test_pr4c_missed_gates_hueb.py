"""
HUEB tests for PR 4c of the 2026-05-29 security review.

PR 4c is the follow-up to PR 4b that closes two endpoints missed from
the original PR 4b surface map. Both are called by BookingsNew.jsx
during the customer checkout flow. Both would silently pass in
soft mode (DRAFT_TOKEN_ENFORCE=False) but 401 on the 2026-06-12
enforcement flip if left ungated, breaking the customer journey.

The two endpoints:

  1. POST /api/customers
       - Step 1 of checkout (Contact Details)
       - Creates or updates a Customer row by email
       - PR 4c binding: draft.email + draft.customer_id (returned id)

  2. PATCH /api/customers/{customer_id}/billing
       - Step 5 of checkout (Billing Address)
       - Updates billing address on an existing Customer row
       - PR 4c binding: draft.customer_id matches path param

Both use the same get_draft_token dependency + _bind_or_check helper
that the 6 PR-4b endpoints established. Tests mirror the PR 4b shape
(H matches, U mismatch → 403, E first-touch binds, B soft-mode pass)
so the file reads as a pure extension of the surface map, not a
new mechanism.
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
    DRAFT_TOKEN_TTL_SECS,
)
from database import get_db


# ============================================================================
# Shared scaffolding (parallel to test_pr4b_draft_token_hueb.py)
# ============================================================================


def _make_draft(
    token="t" * 64, email=None, customer_id=None, vehicle_id=None,
    dvla_calls_count=0,
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
        expires_at=now + timedelta(seconds=DRAFT_TOKEN_TTL_SECS),
    )


def _override_get_db_with(db_mock):
    def _gen():
        yield db_mock
    app.dependency_overrides[get_db] = _gen


def _override_draft_token_dep_with(value):
    app.dependency_overrides[get_draft_token] = lambda: value


def _clear_overrides():
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    _clear_overrides()


def _stub_customer(id=42, email="alice@example.com"):
    return SimpleNamespace(
        id=id, first_name="Alice", last_name="Smith",
        email=email, phone="07700900000",
        billing_address1=None, billing_address2=None,
        billing_city=None, billing_county=None,
        billing_postcode=None, billing_country=None,
        billing_updated_at=None,
    )


# ============================================================================
# 1. POST /api/customers — email + customer_id binding
# ============================================================================


class TestPostCustomersGated:
    """Step 1 of checkout — POST /api/customers creates/updates a
    Customer by email and returns the customer_id. PR 4c binds both:
    draft.email is first-touched on entry, draft.customer_id is
    first-touched from the returned row.
    """

    def _wire(self, monkeypatch, draft, returned_customer_id=42):
        """Override get_draft_token + get_db + db_service.create_customer
        to a stub that returns the requested customer id."""
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.commit = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "create_customer",
            lambda **kw: (_stub_customer(id=returned_customer_id), True),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

    def test_H_token_matching_email_succeeds(self, monkeypatch):
        # H: draft.email already 'alice@example.com'. Request with the
        # SAME email passes the gate, customer is created, customer_id
        # is auto-bound to draft.customer_id.
        draft = _make_draft(email="alice@example.com")
        self._wire(monkeypatch, draft, returned_customer_id=42)

        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["customer_id"] == 42

    def test_U_token_with_wrong_email_403(self, monkeypatch):
        # U: draft.email == 'alice@example.com', request submits
        # 'bob@example.com' → 403. Customer create_customer MUST NOT
        # run (binding mismatch is the gate, fires before handler body).
        draft = _make_draft(email="alice@example.com")
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "create_customer",
            lambda **kw: pytest.fail(
                "create_customer MUST NOT run when bind-mismatch fires"
            ),
        )

        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Bob", "last_name": "Other",
            "email": "bob@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 403
        assert "does not own" in resp.json()["detail"]

    def test_E_first_touch_binds_email_and_customer_id(self, monkeypatch):
        # E: draft is empty on entry (email=None, customer_id=None).
        # POST /api/customers binds BOTH on first touch:
        #   - draft.email from request body
        #   - draft.customer_id from the created Customer row
        draft = _make_draft(email=None, customer_id=None)
        self._wire(monkeypatch, draft, returned_customer_id=42)

        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200
        assert draft.email == "alice@example.com"
        assert draft.customer_id == 42

    def test_B_soft_mode_no_token_succeeds(self, monkeypatch):
        # B: soft-mode behaviour — no X-Draft-Token header → handler
        # runs as if PR 4c didn't exist. Same contract as the PR 4b
        # endpoints during the 14-day rollout window.
        _override_draft_token_dep_with(None)
        db = MagicMock()
        db.commit = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "create_customer",
            lambda **kw: (_stub_customer(id=42), True),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200, resp.text

    def test_U_pre_check_email_resolves_to_other_customer_403_no_mutation(
        self, monkeypatch,
    ):
        # 2026-05-29 review fix regression. Reviewer found that the
        # original PR 4c order let create_customer run BEFORE the
        # customer_id binding check — so a draft owning customer 42
        # could submit an email belonging to customer 99, have
        # customer 99's name/phone overwritten, and only THEN get a
        # 403 response. The fix: pre-mutation lookup by email; if it
        # resolves to a different customer than draft.customer_id is
        # bound to, refuse before any write.
        draft = _make_draft(email="alice@example.com", customer_id=42)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)

        # Submitted email resolves to a DIFFERENT customer (99).
        monkeypatch.setattr(
            main.db_service, "get_customer_by_email",
            lambda d, email: _stub_customer(id=99, email=email),
        )
        # create_customer MUST NOT run.
        create_calls = []
        def _spy_create(**kw):
            create_calls.append(kw)
            return (_stub_customer(id=99), False)
        monkeypatch.setattr(main.db_service, "create_customer", _spy_create)

        # The above scenario sets draft.email already, so we send the
        # SAME email so the email-bind check passes; the customer_id
        # ownership check is the gate under test.
        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Alice", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })

        assert resp.status_code == 403, (
            f"Expected 403 from pre-mutation ownership check; got "
            f"{resp.status_code}. The fix must reject BEFORE writing, "
            f"not after."
        )
        assert "does not own" in resp.json()["detail"]
        assert create_calls == [], (
            "CRITICAL: create_customer ran despite the draft owning a "
            "different customer_id. The ownership check must fire "
            "before the mutation, not after — otherwise customer 99's "
            "row gets overwritten and only then the response says 'blocked'."
        )

    def test_E_pre_check_email_resolves_to_owned_customer_succeeds(
        self, monkeypatch,
    ):
        # E: same scenario but email DOES resolve to draft.customer_id.
        # This is the legitimate "same draft, same customer, possible
        # name/phone refresh" case (e.g. couple sharing an email and
        # the second name lands — still the same customer record).
        draft = _make_draft(email="alice@example.com", customer_id=42)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.commit = MagicMock()
        _override_get_db_with(db)

        monkeypatch.setattr(
            main.db_service, "get_customer_by_email",
            lambda d, email: _stub_customer(id=42, email=email),
        )
        monkeypatch.setattr(
            main.db_service, "create_customer",
            lambda **kw: (_stub_customer(id=42), False),
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        monkeypatch.setattr(main, "title_case_name", lambda n: n)

        client = TestClient(app)
        resp = client.post("/api/customers", json={
            "first_name": "Maria", "last_name": "Smith",
            "email": "alice@example.com", "phone": "07700900000",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["customer_id"] == 42


# ============================================================================
# 2. PATCH /api/customers/{customer_id}/billing — customer_id binding
# ============================================================================


class TestPatchBillingGated:
    """Step 5 of checkout — PATCH /api/customers/{id}/billing updates
    the billing address on an existing Customer row. PR 4c binds the
    URL customer_id to draft.customer_id (same shape as the existing
    PATCH /api/customers/{id} gating from PR 4b).
    """

    def _wire(self, monkeypatch, draft, customer_id=42):
        """Override get_draft_token + get_db + db_service helpers."""
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )
        monkeypatch.setattr(
            main.db_service, "find_potential_duplicate_customer",
            lambda **kw: None,
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)

    def _body(self):
        return {
            "billing_address1": "1 Test St",
            "billing_address2": None,
            "billing_city": "London",
            "billing_county": None,
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom",
        }

    def test_H_token_matching_customer_id_succeeds(self, monkeypatch):
        # H: draft.customer_id == 42, PATCH /api/customers/42/billing
        # → succeeds. customer lookup + commit run as normal.
        draft = _make_draft(customer_id=42)
        self._wire(monkeypatch, draft, customer_id=42)

        client = TestClient(app)
        resp = client.patch("/api/customers/42/billing", json=self._body())
        assert resp.status_code == 200, resp.text

    def test_U_token_with_wrong_customer_id_403(self, monkeypatch):
        # U: draft.customer_id == 42 but URL says 99 → 403. With the
        # lookup-first order (review-fix), the customer 99 lookup
        # runs (read-only, no mutation), THEN the bind check fires
        # 403 before any write. Both invariants matter: bind-check
        # 403, AND no commit() landed.
        draft = _make_draft(customer_id=42)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        db.commit = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )

        client = TestClient(app)
        resp = client.patch("/api/customers/99/billing", json=self._body())

        assert resp.status_code == 403
        assert "does not own" in resp.json()["detail"]
        assert db.commit.call_count == 0, (
            "Bind-mismatch must fire before any write to the customer "
            f"row. Got {db.commit.call_count} commit(s), indicating "
            "the billing UPDATE landed before the 403."
        )

    def test_E_first_touch_binds_customer_id(self, monkeypatch):
        # E: draft.customer_id starts None. PATCH /api/customers/42/billing
        # binds draft.customer_id = 42 on first touch. (This happens
        # when an admin pre-populates a draft and the customer arrives
        # at Step 5 without having gone through Step 1 — unusual but
        # the binding contract still applies.)
        draft = _make_draft(customer_id=None)
        self._wire(monkeypatch, draft, customer_id=42)

        client = TestClient(app)
        resp = client.patch("/api/customers/42/billing", json=self._body())
        assert resp.status_code == 200
        assert draft.customer_id == 42

    def test_U_nonexistent_customer_id_404_does_not_poison_draft(
        self, monkeypatch,
    ):
        # 2026-05-29 review LOW fix regression. Original PR 4c order
        # was bind-then-lookup, which let a request against a bogus
        # customer_id first-touch-bind the draft to that bogus value
        # before returning 404. The fix swaps to lookup-first: 404
        # fires cleanly, the draft is untouched.
        draft = _make_draft(customer_id=None)
        _override_draft_token_dep_with(draft)
        db = MagicMock()
        _override_get_db_with(db)

        # Customer lookup returns None → handler should 404.
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: None,
        )

        client = TestClient(app)
        resp = client.patch("/api/customers/99999/billing", json=self._body())

        assert resp.status_code == 404
        assert draft.customer_id is None, (
            "Draft.customer_id was poisoned with a nonexistent id "
            f"({draft.customer_id}) by a 404 request. The lookup-first "
            "order must keep the draft clean when the customer doesn't "
            "exist."
        )

    def test_B_soft_mode_no_token_succeeds(self, monkeypatch):
        # B: soft-mode behaviour — no token → handler runs as today.
        _override_draft_token_dep_with(None)
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_get_db_with(db)
        monkeypatch.setattr(
            main.db_service, "get_customer_by_id",
            lambda d, cid: _stub_customer(id=cid),
        )
        monkeypatch.setattr(
            main.db_service, "find_potential_duplicate_customer",
            lambda **kw: None,
        )
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)

        client = TestClient(app)
        resp = client.patch("/api/customers/42/billing", json=self._body())
        assert resp.status_code == 200, resp.text
