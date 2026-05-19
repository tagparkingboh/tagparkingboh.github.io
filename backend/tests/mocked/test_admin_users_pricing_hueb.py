"""
HUEB tests for main.py admin user CRUD + pricing endpoints.

Covers:
  POST   /api/admin/users           — create_user (12230)
  GET    /api/admin/users           — list_users (12282)
  PUT    /api/admin/users/{id}      — update_user (12308)
  DELETE /api/admin/users/{id}      — delete_user (12367)
  GET    /api/admin/pricing         — get_admin_pricing (12870)
  PUT    /api/admin/pricing         — update_pricing (12909)

Auth + DB are overridden via app.dependency_overrides on main.require_admin
and database.get_db.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app, require_admin
from database import get_db


def _admin(id=1):
    return SimpleNamespace(
        id=id, email="admin@tag.test", is_admin=True,
        first_name="Admin", last_name="One",
    )


def _override(db_factory, user=None):
    def gen():
        yield db_factory()
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


def _user(**kw):
    base = dict(
        id=10, email="jo@x.test", first_name="Jo", last_name="K",
        phone="0712345", is_admin=False, is_active=True,
        driver_type="fleet", last_login=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# POST /api/admin/users — create_user
# ============================================================================

class TestCreateUser:
    def teardown_method(self):
        _clear()

    def _wire(self, existing=None):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = existing
        db.query.return_value = chain
        added = []
        def _add(obj):
            obj.id = 42
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db._added = added
        return db

    def test_H_creates_non_admin_with_default_fleet(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "new@tag.test", "first_name": "n", "last_name": "ew",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["user"]["driver_type"] == "fleet"
        assert body["user"]["email"] == "new@tag.test"
        # title-case applied
        assert body["user"]["first_name"] == "N"

    def test_H_admin_default_driver_type_null(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "boss@tag.test", "first_name": "B", "last_name": "B",
            "is_admin": True,
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["driver_type"] is None
        assert resp.json()["user"]["is_admin"] is True

    def test_H_explicit_jockey_for_admin_is_preserved(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "j@tag.test", "first_name": "J", "last_name": "J",
            "is_admin": True, "driver_type": "jockey",
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["driver_type"] == "jockey"

    def test_U_duplicate_email_returns_400(self):
        db = self._wire(existing=_user())
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "jo@x.test", "first_name": "Jo", "last_name": "K",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_E_email_is_lowercased_and_trimmed(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "  MIXED@x.TEST  ", "first_name": "M", "last_name": "X",
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "mixed@x.test"

    def test_U_missing_required_field_returns_422(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={"email": "x@x.test"})
        assert resp.status_code == 422

    def test_U_invalid_driver_type_returns_422(self):
        db = self._wire(existing=None)
        _override(lambda: db)
        resp = TestClient(app).post("/api/admin/users", json={
            "email": "x@x.test", "first_name": "X", "last_name": "Y",
            "driver_type": "bogus",
        })
        assert resp.status_code == 422


# ============================================================================
# GET /api/admin/users — list_users
# ============================================================================

class TestListUsers:
    def teardown_method(self):
        _clear()

    def _wire(self, users):
        db = MagicMock()
        db.query.return_value.all.return_value = users
        return db

    def test_H_returns_users_list(self):
        users = [_user(id=1, last_login=datetime(2026, 5, 1, 9, 0)),
                 _user(id=2)]
        _override(lambda: self._wire(users))
        resp = TestClient(app).get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["users"]) == 2
        assert body["users"][0]["last_login"] is not None
        assert body["users"][1]["last_login"] is None

    def test_E_empty_list(self):
        _override(lambda: self._wire([]))
        resp = TestClient(app).get("/api/admin/users")
        assert resp.status_code == 200
        assert resp.json()["users"] == []


# ============================================================================
# PUT /api/admin/users/{id} — update_user
# ============================================================================

class TestUpdateUser:
    def teardown_method(self):
        _clear()

    def _wire(self, user, dup_email=None):
        db = MagicMock()
        responses = [user, dup_email]  # first call → user, second → dup-check
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.side_effect = responses
        db.query.return_value = chain
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_updates_name_and_phone(self):
        u = _user()
        _override(lambda: self._wire(u))
        resp = TestClient(app).put(f"/api/admin/users/{u.id}", json={
            "first_name": "Jane", "phone": "07999000000",
        })
        assert resp.status_code == 200
        assert u.first_name == "Jane"
        assert u.phone == "07999000000"

    def test_H_clear_driver_type_to_null(self):
        u = _user(driver_type="fleet")
        _override(lambda: self._wire(u))
        resp = TestClient(app).put(f"/api/admin/users/{u.id}", json={
            "driver_type": None,
        })
        assert resp.status_code == 200
        assert u.driver_type is None

    def test_U_not_found(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).put("/api/admin/users/9999", json={"first_name": "X"})
        assert resp.status_code == 404

    def test_U_cannot_remove_own_admin(self):
        admin = _admin(id=1)
        u = _user(id=1, is_admin=True)  # self
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = u
        db.query.return_value = chain
        def _gen():
            yield db
        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_admin] = lambda: admin
        resp = TestClient(app).put("/api/admin/users/1", json={"is_admin": False})
        assert resp.status_code == 400
        assert "admin privileges" in resp.json()["detail"].lower()

    def test_U_cannot_deactivate_self(self):
        admin = _admin(id=1)
        u = _user(id=1, is_active=True)
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = u
        db.query.return_value = chain
        def _gen():
            yield db
        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_admin] = lambda: admin
        resp = TestClient(app).put("/api/admin/users/1", json={"is_active": False})
        assert resp.status_code == 400
        assert "deactivate" in resp.json()["detail"].lower()

    def test_U_duplicate_email_on_another_user(self):
        u = _user(id=10)
        dup = _user(id=99)  # different id, same email
        _override(lambda: self._wire(u, dup_email=dup))
        resp = TestClient(app).put(f"/api/admin/users/{u.id}", json={"email": "taken@x.test"})
        assert resp.status_code == 400
        assert "in use" in resp.json()["detail"].lower()

    def test_E_email_lowercased(self):
        u = _user(id=10)
        _override(lambda: self._wire(u, dup_email=None))
        resp = TestClient(app).put(f"/api/admin/users/{u.id}", json={"email": "  UPPER@X.TEST  "})
        assert resp.status_code == 200
        assert u.email == "upper@x.test"

    def test_E_clear_phone_to_none(self):
        u = _user(id=10, phone="0712345")
        _override(lambda: self._wire(u))
        # phone="" → None in handler (request.phone.strip() if phone else None)
        # JSON null also handled — pass ""
        resp = TestClient(app).put(f"/api/admin/users/{u.id}", json={"phone": ""})
        assert resp.status_code == 200
        assert u.phone is None


# ============================================================================
# DELETE /api/admin/users/{id} — delete_user
# ============================================================================

class TestDeleteUser:
    def teardown_method(self):
        _clear()

    def _wire(self, user):
        db = MagicMock()
        # Three .query() calls happen for cleanup: LoginCode, DbSession, VehicleInspection, PricingSettings.
        # The first call (User) returns the lookup; subsequent calls return chains
        # that support .filter().delete() / .update().
        chain_user = MagicMock()
        chain_user.filter.return_value = chain_user
        chain_user.first.return_value = user

        chain_other = MagicMock()
        chain_other.filter.return_value = chain_other
        chain_other.delete.return_value = 0
        chain_other.update.return_value = 0

        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            return chain_user if calls["n"] == 1 else chain_other

        db.query.side_effect = _query
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes_and_cleans_up(self):
        u = _user(id=10)
        _override(lambda: self._wire(u))
        resp = TestClient(app).delete(f"/api/admin/users/{u.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_U_not_found(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).delete("/api/admin/users/99999")
        assert resp.status_code == 404

    def test_U_cannot_delete_self(self):
        admin = _admin(id=10)
        u = _user(id=10)
        db = self._wire(u)
        def _gen():
            yield db
        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_admin] = lambda: admin
        resp = TestClient(app).delete("/api/admin/users/10")
        assert resp.status_code == 400
        assert "your own" in resp.json()["detail"].lower()


# ============================================================================
# GET /api/admin/pricing — get_admin_pricing
# ============================================================================

class TestGetAdminPricing:
    def teardown_method(self):
        _clear()

    def _wire(self, settings):
        db = MagicMock()
        db.query.return_value.first.return_value = settings
        return db

    def test_H_returns_existing_settings(self):
        updater = SimpleNamespace(first_name="Admin")
        s = SimpleNamespace(
            days_1_4_price=70.0,
            week1_base_price=90.0,
            week2_base_price=160.0,
            daily_increment=9.0,
            tier_increment=6.0,
            peak_day_increment=5.0,
            show_price_range=True,
            updated_at=datetime(2026, 5, 1, 12, 0, 0),
            updater=updater,
        )
        _override(lambda: self._wire(s))
        resp = TestClient(app).get("/api/admin/pricing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["days_1_4_price"] == 70.0
        assert body["show_price_range"] is True
        assert body["updated_by"] == "Admin"

    def test_E_no_settings_returns_defaults(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).get("/api/admin/pricing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["days_1_4_price"] == 65.0
        assert body["week1_base_price"] == 85.0
        assert body["week2_base_price"] == 150.0
        assert body["updated_at"] is None

    def test_E_partial_nones_fall_back_to_defaults(self):
        """When stored values are None, defaults kick in via the `if ... else` ladder."""
        s = SimpleNamespace(
            days_1_4_price=None,
            week1_base_price=None,
            week2_base_price=None,
            daily_increment=None,
            tier_increment=None,
            peak_day_increment=None,
            show_price_range=None,
            updated_at=None,
            updater=None,
        )
        _override(lambda: self._wire(s))
        resp = TestClient(app).get("/api/admin/pricing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["days_1_4_price"] == 65.0
        assert body["updated_by"] is None


# ============================================================================
# PUT /api/admin/pricing — update_pricing
# ============================================================================

class TestUpdatePricing:
    def teardown_method(self):
        _clear()

    def _wire(self, settings):
        db = MagicMock()
        db.query.return_value.first.return_value = settings
        added = []
        def _add(obj):
            added.append(obj)
            # populate updated_at so the response branch works
            obj.updated_at = datetime(2026, 5, 1, 12, 0, 0)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    _payload = {
        "days_1_4_price": 70.0,
        "week1_base_price": 90.0,
        "week2_base_price": 160.0,
        "daily_increment": 9.0,
        "tier_increment": 6.0,
    }

    def test_H_creates_when_no_existing(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).put("/api/admin/pricing", json=self._payload)
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["pricing"]["days_1_4_price"] == 70.0

    def test_H_updates_existing(self):
        s = SimpleNamespace(
            days_1_4_price=60.0, week1_base_price=80.0, week2_base_price=140.0,
            daily_increment=7.0, tier_increment=4.0, peak_day_increment=0.0,
            show_price_range=False, updated_by=None,
            updated_at=datetime(2026, 5, 1, 9, 0, 0),
        )
        _override(lambda: self._wire(s))
        resp = TestClient(app).put("/api/admin/pricing", json=self._payload)
        assert resp.status_code == 200
        assert float(s.days_1_4_price) == 70.0
        assert float(s.week1_base_price) == 90.0

    def test_H_peak_day_increment_optional_defaults_zero(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).put("/api/admin/pricing", json=self._payload)
        assert resp.status_code == 200
        assert resp.json()["pricing"]["peak_day_increment"] == 0.0

    def test_U_missing_required_returns_422(self):
        _override(lambda: self._wire(None))
        resp = TestClient(app).put("/api/admin/pricing", json={"days_1_4_price": 70.0})
        assert resp.status_code == 422

    def test_B_show_price_range_true_flows_through(self):
        _override(lambda: self._wire(None))
        payload = dict(self._payload, show_price_range=True)
        resp = TestClient(app).put("/api/admin/pricing", json=payload)
        assert resp.status_code == 200
        assert resp.json()["pricing"]["show_price_range"] is True
