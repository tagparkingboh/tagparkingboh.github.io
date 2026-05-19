"""
HUEB for the smaller scattered main.py endpoints.

  POST   /api/customers/heard-about-us       (9167)
  PATCH  /api/customers/{id}/billing         (9260)
  POST   /api/admin/refund/{pi_id}           (12016)
  POST   /api/admin/sql/execute              (14643)
  GET    /api/admin/marketing/promo-codes    (17491)
"""
from datetime import datetime, timedelta
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


def _admin(id=1):
    return SimpleNamespace(id=id, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    if user is not None:
        app.dependency_overrides[require_admin] = lambda: user


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


def _customer(**kw):
    base = dict(
        id=42, email="jo@x.test", first_name="Jo", last_name="K",
        has_answered_heard_about_us=False,
        billing_address1=None, billing_address2=None,
        billing_city=None, billing_county=None,
        billing_postcode=None, billing_country="United Kingdom",
        billing_updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# POST /api/customers/heard-about-us
# ============================================================================

class TestHeardAboutUs:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, existing_total=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "MarketingSourceMonthlyTotal":
                chain.first.return_value = existing_total
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_H_records_new_source(self):
        c = _customer()
        _override_public(self._wire(c, existing_total=None))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "google"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["already_answered"] is False
        assert c.has_answered_heard_about_us is True

    def test_H_increments_existing_monthly_total(self):
        c = _customer()
        existing = SimpleNamespace(count=5)
        _override_public(self._wire(c, existing_total=existing))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "facebook"
        })
        assert resp.status_code == 200
        assert existing.count == 6

    def test_E_already_answered_is_idempotent(self):
        c = _customer(has_answered_heard_about_us=True)
        _override_public(self._wire(c))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "google"
        })
        assert resp.status_code == 200
        assert resp.json()["already_answered"] is True

    def test_H_other_with_detail(self):
        c = _customer()
        _override_public(self._wire(c))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "other",
            "source_detail": "Friend recommended us",
        })
        assert resp.status_code == 200

    def test_U_invalid_source(self):
        _override_public(self._wire(_customer()))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "bogus"
        })
        assert resp.status_code == 400
        assert "invalid source" in resp.json()["detail"].lower()

    def test_U_other_without_detail(self):
        _override_public(self._wire(_customer()))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "other"
        })
        assert resp.status_code == 400
        assert "minimum 3 characters" in resp.json()["detail"]

    def test_U_other_with_too_short_detail(self):
        _override_public(self._wire(_customer()))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "other", "source_detail": "ab"
        })
        assert resp.status_code == 400

    def test_U_other_with_too_long_detail(self):
        _override_public(self._wire(_customer()))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "other", "source_detail": "x" * 256
        })
        assert resp.status_code == 400
        assert "maximum 255" in resp.json()["detail"].lower()

    def test_U_customer_not_found(self):
        _override_public(self._wire(None))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "missing@x.test", "source": "google"
        })
        assert resp.status_code == 404

    def test_B_other_with_exactly_3_chars(self):
        c = _customer()
        _override_public(self._wire(c))
        resp = TestClient(app).post("/api/customers/heard-about-us", json={
            "email": "jo@x.test", "source": "other", "source_detail": "abc"
        })
        assert resp.status_code == 200


# ============================================================================
# PATCH /api/customers/{customer_id}/billing
# ============================================================================

class TestUpdateCustomerBilling:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, duplicate=None):
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        # Patch db_service helpers
        return db, customer, duplicate

    _payload = dict(
        billing_address1="1 High St",
        billing_city="Bournemouth",
        billing_postcode="BH1 1AA",
    )

    def test_H_updates_billing(self, monkeypatch):
        c = _customer()
        db, _, _ = self._wire(c)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: c)
        monkeypatch.setattr("db_service.find_potential_duplicate_customer", lambda **kw: None)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override_public(db)
        resp = TestClient(app).patch(f"/api/customers/{c.id}/billing", json=self._payload)
        assert resp.status_code == 200
        assert c.billing_address1 == "1 High St"
        assert "potential_duplicate" not in resp.json()

    def test_H_flags_potential_duplicate(self, monkeypatch):
        c = _customer()
        dup = _customer(id=99, email="other@x.test")
        db, _, _ = self._wire(c, duplicate=dup)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: c)
        monkeypatch.setattr("db_service.find_potential_duplicate_customer", lambda **kw: dup)
        monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
        _override_public(db)
        resp = TestClient(app).patch(f"/api/customers/{c.id}/billing", json=self._payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["potential_duplicate"]["customer_id"] == 99
        assert body["potential_duplicate"]["email"] == "other@x.test"

    def test_U_customer_not_found(self, monkeypatch):
        db = MagicMock()
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: None)
        _override_public(db)
        resp = TestClient(app).patch("/api/customers/9999/billing", json=self._payload)
        assert resp.status_code == 404

    def test_U_db_exception_returns_400(self, monkeypatch):
        c = _customer()
        db = MagicMock()
        db.commit.side_effect = RuntimeError("DB down")
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: c)
        _override_public(db)
        resp = TestClient(app).patch(f"/api/customers/{c.id}/billing", json=self._payload)
        assert resp.status_code == 400


# ============================================================================
# POST /api/admin/refund/{payment_intent_id}
# ============================================================================

class TestAdminRefund:
    def teardown_method(self):
        _clear()

    def test_H_refunds(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(main, "refund_payment", lambda pid, reason: {
            "refund_id": "re_1", "status": "succeeded", "amount": 9900,
        })
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/refund/pi_123")
        assert resp.status_code == 200
        assert resp.json()["refund_id"] == "re_1"
        assert resp.json()["amount_refunded"] == "£99.00"

    def test_U_stripe_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: False)
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/refund/pi_123")
        assert resp.status_code == 503

    def test_U_refund_raises(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        def boom(pid, reason):
            raise RuntimeError("Stripe error: charge already refunded")
        monkeypatch.setattr(main, "refund_payment", boom)
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/refund/pi_123")
        assert resp.status_code == 400
        assert "already refunded" in resp.json()["detail"].lower()

    def test_E_custom_reason(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        def fake(pid, reason):
            captured["reason"] = reason
            return {"refund_id": "re_2", "status": "succeeded", "amount": 5000}
        monkeypatch.setattr(main, "refund_payment", fake)
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/refund/pi_123?reason=duplicate")
        assert resp.status_code == 200
        assert captured["reason"] == "duplicate"


# ============================================================================
# POST /api/admin/sql/execute
# ============================================================================

class TestSqlExecute:
    def teardown_method(self):
        _clear()
        # Clear any leftover session tokens
        try:
            main.sql_session_tokens.clear()
        except Exception:
            pass

    def _setup_session(self, user_id=1, expired=False):
        from datetime import datetime as dt
        import pytz
        uk = pytz.timezone("Europe/London")
        exp = dt.now(uk) + (timedelta(hours=-1) if expired else timedelta(hours=2))
        main.sql_session_tokens[user_id] = {"token": "valid-token", "expires_at": exp}

    def test_H_select_query(self, monkeypatch):
        self._setup_session()
        db = MagicMock()
        result = MagicMock()
        result.keys.return_value = ["id", "name"]
        result.fetchmany.return_value = [(1, "Alpha"), (2, "Beta")]
        # First .execute() = SET timeout; second = actual query; third = reset
        db.execute.return_value = result
        _override_admin(db)
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "SELECT id, name FROM users",
            "session_token": "valid-token",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_type"] == "SELECT"
        assert body["row_count"] == 2
        assert body["columns"] == ["id", "name"]

    def test_H_write_op_with_confirmation(self, monkeypatch):
        self._setup_session()
        db = MagicMock()
        result = MagicMock()
        result.rowcount = 3
        db.execute.return_value = result
        _override_admin(db)
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "UPDATE users SET name='X' WHERE id=1",
            "session_token": "valid-token",
            "confirmed": True,
        })
        assert resp.status_code == 200
        assert resp.json()["affected_rows"] == 3

    def test_U_invalid_session_token(self):
        self._setup_session()
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "SELECT 1", "session_token": "wrong",
        })
        assert resp.status_code == 401

    def test_U_expired_session(self):
        self._setup_session(expired=True)
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "SELECT 1", "session_token": "valid-token",
        })
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_U_empty_query(self):
        self._setup_session()
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "   ", "session_token": "valid-token",
        })
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_U_blocked_command(self, monkeypatch):
        self._setup_session()
        monkeypatch.setattr(main, "is_sql_command_blocked", lambda q: (True, "DROP"))
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "DROP TABLE users", "session_token": "valid-token",
        })
        assert resp.status_code == 403
        assert "DROP" in resp.json()["detail"]

    def test_E_write_op_without_confirmation_returns_prompt(self, monkeypatch):
        self._setup_session()
        monkeypatch.setattr(main, "is_sql_command_blocked", lambda q: (False, ""))
        monkeypatch.setattr(main, "is_write_operation", lambda q: True)
        _override_admin(MagicMock())
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "UPDATE users SET x=1", "session_token": "valid-token",
            "confirmed": False,
        })
        assert resp.status_code == 200
        assert resp.json()["requires_confirmation"] is True
        assert resp.json()["operation_type"] == "UPDATE"

    def test_U_query_error_returns_400(self, monkeypatch):
        self._setup_session()
        db = MagicMock()
        # First execute (SET timeout) succeeds, second one raises
        calls = {"n": 0}
        def _exec(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return MagicMock()
            raise RuntimeError("relation does not exist")
        db.execute.side_effect = _exec
        _override_admin(db)
        resp = TestClient(app).post("/api/admin/sql/execute", json={
            "query": "SELECT * FROM missing_table", "session_token": "valid-token",
        })
        assert resp.status_code == 400
        assert "query error" in resp.json()["detail"].lower()


# ============================================================================
# GET /api/admin/marketing/promo-codes
# ============================================================================

class TestGetAvailablePromoCodes:
    def teardown_method(self):
        _clear()

    def test_H_returns_multi_use_codes(self):
        promo = SimpleNamespace(discount_percent=10)
        c1 = SimpleNamespace(
            id=1, code="MULTI1", promotion=promo,
            max_uses=100, use_count=5, expires_at=datetime(2026, 12, 31),
        )
        c2 = SimpleNamespace(
            id=2, code="MULTI2", promotion=None,
            max_uses=50, use_count=0, expires_at=None,
        )
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = [c1, c2]
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/marketing/promo-codes")
        assert resp.status_code == 200
        codes = resp.json()["promo_codes"]
        assert len(codes) == 2
        assert codes[0]["discount_percent"] == 10
        assert codes[1]["discount_percent"] is None  # no promotion linked

    def test_E_no_codes(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = []
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/marketing/promo-codes")
        assert resp.status_code == 200
        assert resp.json()["promo_codes"] == []
