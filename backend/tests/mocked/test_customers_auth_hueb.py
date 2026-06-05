"""
HUEB tests for admin customers + auth endpoints in main.py.

Admin customers (3805-4199):
  GET    /api/admin/marketing-subscribers
  GET    /api/admin/abandoned-leads
  GET    /api/admin/customers
  GET    /api/admin/customers/{id}
  PATCH  /api/admin/customers/{id}
  DELETE /api/admin/customers/{id}
  POST   /api/admin/customers/{id}/vehicles

Auth (12966-13176):
  POST   /api/auth/request-code
  POST   /api/auth/verify-code
  POST   /api/auth/logout
  GET    /api/auth/me
"""
from datetime import date as date_type, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import main
from main import app, require_admin, get_current_user
from database import get_db


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True,
                            first_name="Admin", last_name="One")


def _override_admin(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _override_user(db, user):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[get_current_user] = lambda: user


def _clear():
    app.dependency_overrides.clear()


def _subscriber(**kw):
    base = dict(
        id=11, first_name="Jo", last_name="K", email="jo@x.test",
        subscribed_at=datetime(2026, 5, 1, 9, 0),
        welcome_email_sent=True, welcome_email_sent_at=datetime(2026, 5, 1, 9, 5),
        promo_code=None, promo_code_sent=False, promo_code_sent_at=None,
        discount_percent=None, promo_code_used=False, promo_code_used_at=None,
        promo_code_used_booking_id=None,
        promo_10_code=None, promo_10_sent=False, promo_10_sent_at=None,
        promo_10_used=False, promo_10_used_at=None,
        promo_10_reminder_sent=False, promo_10_reminder_sent_at=None,
        promo_free_code=None, promo_free_sent=False, promo_free_sent_at=None,
        promo_free_used=False, promo_free_used_at=None,
        promo_free_reminder_sent=False, promo_free_reminder_sent_at=None,
        founder_promo_code=None, founder_email_sent=False, founder_email_sent_at=None,
        founder_promo_used=False, founder_promo_used_at=None,
        unsubscribed=False, unsubscribed_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _customer(**kw):
    base = dict(
        id=42, first_name="Jo", last_name="K", email="jo@x.test",
        phone="07123456789",
        billing_address1="1 High St", billing_address2=None,
        billing_city="Bournemouth", billing_county=None,
        billing_postcode="BH1 1AA", billing_country="UK",
        created_at=datetime(2026, 5, 1),
        founder_followup_sent=False, founder_followup_sent_at=None,
        marketing_source=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# GET /api/admin/marketing-subscribers
# ============================================================================

class TestMarketingSubscribers:
    def teardown_method(self):
        _clear()

    def test_H_returns_subscribers(self):
        db = MagicMock()
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.all.return_value = [_subscriber()]
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/marketing-subscribers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_E_empty(self):
        db = MagicMock()
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.all.return_value = []
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/marketing-subscribers")
        assert resp.json()["count"] == 0


# ============================================================================
# GET /api/admin/abandoned-leads
# ============================================================================

class TestAbandonedLeads:
    def teardown_method(self):
        _clear()

    def _wire(self, customers, bookings=None):
        db = MagicMock()
        confirmed_subq = MagicMock()
        confirmed_subq.subquery.return_value = MagicMock(
            c=MagicMock(customer_id="confirmed_customer_id")
        )
        cust_chain = MagicMock()
        cust_chain.filter.return_value = cust_chain
        cust_chain.order_by.return_value = cust_chain
        cust_chain.all.return_value = customers
        booking_chain = MagicMock()
        booking_chain.filter.return_value = booking_chain
        booking_chain.subquery.return_value = MagicMock(
            c=MagicMock(customer_id="x")
        )
        booking_chain.all.return_value = bookings or []
        calls = {"n": 0}
        def _query(*args):
            calls["n"] += 1
            model = args[0]
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Customer":
                return cust_chain
            return booking_chain
        db.query.side_effect = _query
        return db

    def test_H_returns_leads(self):
        from db_models import BookingStatus
        c = _customer()
        b = SimpleNamespace(status=BookingStatus.PENDING)
        _override_admin(self._wire([c], bookings=[b]))
        resp = TestClient(app).get("/api/admin/abandoned-leads")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_E_no_leads(self):
        _override_admin(self._wire([], bookings=[]))
        resp = TestClient(app).get("/api/admin/abandoned-leads")
        assert resp.json()["count"] == 0


# ============================================================================
# GET /api/admin/customers
# ============================================================================

class TestListCustomers:
    def teardown_method(self):
        _clear()

    def test_H_with_marketing_source(self):
        c = _customer()
        c.marketing_source = SimpleNamespace(source="google")
        db = MagicMock()
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.all.return_value = [c]
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/customers")
        assert resp.status_code == 200
        assert resp.json()["customers"][0]["marketing_source"] == "google"

    def test_E_no_marketing_source(self):
        c = _customer(marketing_source=None)
        db = MagicMock()
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.all.return_value = [c]
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/customers")
        assert resp.json()["customers"][0]["marketing_source"] is None

    def test_E_empty(self):
        db = MagicMock()
        chain = MagicMock()
        chain.order_by.return_value = chain
        chain.all.return_value = []
        db.query.return_value = chain
        _override_admin(db)
        resp = TestClient(app).get("/api/admin/customers")
        assert resp.json()["count"] == 0


# ============================================================================
# GET /api/admin/customers/{id}
# ============================================================================

class TestGetCustomerDetail:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, vehicles=None, booking_count=0):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "Vehicle":
                chain.all.return_value = vehicles or []
            elif name == "Booking":
                chain.count.return_value = booking_count
            elif name == "ReferralProgram":
                chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        return db

    def test_H_returns_detail(self):
        c = _customer()
        c.marketing_source = SimpleNamespace(source="facebook")
        v = SimpleNamespace(id=1, registration="AB12CDE", make="Ford",
                            model="Focus", colour="Blue",
                            created_at=datetime(2026, 5, 1))
        _override_admin(self._wire(c, vehicles=[v], booking_count=3))
        resp = TestClient(app).get(f"/api/admin/customers/{c.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["marketing_source"] == "facebook"
        assert body["booking_count"] == 3
        assert len(body["vehicles"]) == 1

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).get("/api/admin/customers/9999")
        assert resp.status_code == 404


# ============================================================================
# PATCH /api/admin/customers/{id}
# ============================================================================

class TestUpdateCustomer:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, dup_email=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            if calls["n"] == 1:
                chain.first.return_value = customer
            else:
                chain.first.return_value = dup_email
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_update_email(self):
        c = _customer()
        _override_admin(self._wire(c, dup_email=None))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"email": "new@x.test"})
        assert resp.status_code == 200
        assert c.email == "new@x.test"

    def test_H_update_phone(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"phone": "07999000000"})
        assert resp.status_code == 200

    def test_U_no_fields_provided(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}", json={})
        assert resp.status_code == 400
        assert "at least one" in resp.json()["detail"].lower()

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).patch("/api/admin/customers/9999",
                                     json={"email": "x@x.test"})
        assert resp.status_code == 404

    def test_U_invalid_email_format(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"email": "not-an-email"})
        assert resp.status_code == 400
        assert "invalid email" in resp.json()["detail"].lower()

    def test_U_email_already_exists(self):
        c = _customer()
        dup = _customer(id=99, email="taken@x.test")
        _override_admin(self._wire(c, dup_email=dup))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"email": "taken@x.test"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_U_invalid_phone_too_short(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"phone": "123"})
        assert resp.status_code == 400

    def test_U_invalid_phone_non_numeric(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/customers/{c.id}",
                                     json={"phone": "abcdefghij"})
        assert resp.status_code == 400


# ============================================================================
# DELETE /api/admin/customers/{id}
# ============================================================================

class TestDeleteCustomer:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, booking_count=0):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "Booking":
                chain.count.return_value = booking_count
            return chain
        db.query.side_effect = _query
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes(self):
        c = _customer()
        _override_admin(self._wire(c, booking_count=0))
        resp = TestClient(app).delete(f"/api/admin/customers/{c.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).delete("/api/admin/customers/9999")
        assert resp.status_code == 404

    def test_U_has_bookings(self):
        c = _customer()
        _override_admin(self._wire(c, booking_count=3))
        resp = TestClient(app).delete(f"/api/admin/customers/{c.id}")
        assert resp.status_code == 400
        assert "3 associated" in resp.json()["detail"]


# ============================================================================
# POST /api/admin/customers/{id}/vehicles
# ============================================================================

class TestAddCustomerVehicle:
    def teardown_method(self):
        _clear()

    def _wire(self, customer, existing_vehicle=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "Vehicle":
                chain.first.return_value = existing_vehicle
            return chain
        db.query.side_effect = _query
        added = []
        def _add(obj):
            obj.id = 99
            obj.created_at = datetime(2026, 5, 1)
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    _payload = dict(registration="ab 12 cde", make="Ford", colour="Blue")

    def test_H_creates_vehicle(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).post(f"/api/admin/customers/{c.id}/vehicles",
                                    json=self._payload)
        assert resp.status_code == 200
        # Uppercased, spaces stripped
        assert resp.json()["vehicle"]["registration"] == "AB12CDE"

    def test_H_with_dvla_data(self):
        c = _customer()
        _override_admin(self._wire(c))
        resp = TestClient(app).post(f"/api/admin/customers/{c.id}/vehicles", json=dict(
            self._payload, tax_status="Taxed", mot_status="Valid",
        ))
        assert resp.status_code == 200
        assert resp.json()["vehicle"]["dvla_checked_at"] is not None

    def test_U_customer_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).post("/api/admin/customers/9999/vehicles",
                                    json=self._payload)
        assert resp.status_code == 404

    def test_U_duplicate_registration(self):
        c = _customer()
        existing = SimpleNamespace(id=1, registration="AB12CDE")
        _override_admin(self._wire(c, existing_vehicle=existing))
        resp = TestClient(app).post(f"/api/admin/customers/{c.id}/vehicles",
                                    json=self._payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()


# ============================================================================
# Auth endpoints
# ============================================================================

class TestAuthRequestCode:
    def teardown_method(self):
        _clear()

    def _wire(self, user=None):
        db = MagicMock()
        # First query is User; second is LoginCode.update; third is db.add
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            name = model.__name__
            if name == "User":
                chain.first.return_value = user
            elif name == "LoginCode":
                chain.update.return_value = 0
            elif name == "AuthThrottle":
                # Rate-limit layer added 2026-05-29. Return 1 (just
                # the row the handler inserted) so no throttle fires.
                chain.count.return_value = 1
                chain.delete.return_value = 0
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_sends_code_for_active_user(self, monkeypatch):
        u = SimpleNamespace(id=1, email="jo@x.test", is_active=True, first_name="Jo")
        _override_public(self._wire(u))
        monkeypatch.setattr(main, "send_login_code_email", lambda **kw: True)
        resp = TestClient(app).post("/api/auth/request-code", json={"email": "jo@x.test"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_E_unknown_email_does_not_reveal(self):
        """Returns success message even for unknown email (no info leak)."""
        _override_public(self._wire(None))
        resp = TestClient(app).post("/api/auth/request-code",
                                     json={"email": "missing@x.test"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "registered" in resp.json()["message"].lower()

    def test_E_email_lowercased_and_trimmed(self, monkeypatch):
        """Email matching is case-insensitive."""
        u = SimpleNamespace(id=1, email="jo@x.test", is_active=True, first_name="Jo")
        _override_public(self._wire(u))
        monkeypatch.setattr(main, "send_login_code_email", lambda **kw: True)
        resp = TestClient(app).post("/api/auth/request-code",
                                     json={"email": "  JO@X.TEST  "})
        assert resp.status_code == 200


class TestAuthVerifyCode:
    def teardown_method(self):
        _clear()

    def _wire(self, user=None, login_code=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            name = model.__name__
            if name == "User":
                chain.first.return_value = user
            elif name == "LoginCode":
                # Verify-code endpoint now issues TWO LoginCode queries
                # (match-first then latest-active, 2026-05-29 review).
                # Returning the same value for both is fine for these
                # tests: success-path tests pass a populated login_code
                # (so both succeed), invalid-path tests pass None (so
                # both miss).
                chain.first.return_value = login_code
                chain.update.return_value = 0
            elif name == "AuthThrottle":
                chain.count.return_value = 1
                chain.delete.return_value = 0
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock(side_effect=lambda obj: None)
        return db

    def test_H_valid_code_returns_token(self):
        u = SimpleNamespace(id=1, email="jo@x.test", is_active=True,
                            first_name="Jo", last_name="K", is_admin=False,
                            last_login=None)
        # `code` + `attempts` added 2026-05-29 — the verify endpoint now
        # constant-time-compares the submitted value against login_code.code
        # and tracks wrong attempts per code.
        lc = SimpleNamespace(
            id=1, used=False, code="123456", attempts=0,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        _override_public(self._wire(u, lc))
        resp = TestClient(app).post("/api/auth/verify-code",
                                     json={"email": "jo@x.test", "code": "123456"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["token"] is not None
        assert body["user"]["email"] == "jo@x.test"

    def test_U_unknown_email(self):
        _override_public(self._wire(None))
        resp = TestClient(app).post("/api/auth/verify-code",
                                     json={"email": "missing@x.test", "code": "123456"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_U_invalid_code(self):
        u = SimpleNamespace(id=1, email="jo@x.test", is_active=True,
                            first_name="Jo", last_name="K", is_admin=False)
        _override_public(self._wire(u, login_code=None))
        resp = TestClient(app).post("/api/auth/verify-code",
                                     json={"email": "jo@x.test", "code": "999999"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "invalid or expired" in resp.json()["message"].lower()


class TestAuthLogout:
    def teardown_method(self):
        _clear()

    def test_H_logs_out_with_bearer(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.delete.return_value = 1
        db.query.return_value = chain
        db.commit = MagicMock()
        _override_public(db)
        resp = TestClient(app).post("/api/auth/logout",
                                     headers={"Authorization": "Bearer abc123"})
        assert resp.status_code == 200

    def test_E_no_authorization_header(self):
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/auth/logout")
        assert resp.status_code == 200

    def test_E_malformed_authorization(self):
        _override_public(MagicMock())
        resp = TestClient(app).post("/api/auth/logout",
                                     headers={"Authorization": "weird"})
        assert resp.status_code == 200


class TestAuthMe:
    def teardown_method(self):
        _clear()

    def test_H_returns_user(self):
        u = SimpleNamespace(id=1, email="jo@x.test", first_name="Jo",
                            last_name="K", is_admin=False)
        _override_user(MagicMock(), u)
        resp = TestClient(app).get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "jo@x.test"
