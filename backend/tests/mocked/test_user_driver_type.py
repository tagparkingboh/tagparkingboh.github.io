"""
Mocked-integration tests for the driver_type field on user create / update.

Covers `POST /api/admin/users` and `PUT /api/admin/users/{id}` with:
- Default resolution (non-admin → "fleet", admin → NULL) when the field is
  omitted from the request body
- Caller override (any of jockey / fleet / NULL) regardless of is_admin
- model_fields_set semantics on PUT so an admin can explicitly clear the
  column back to NULL without it being mistaken for "omitted"
- Response payload always echoes driver_type

H/U/E/B per SPEC.md. Uses TestClient(app) + dependency overrides so it
exercises the real handler in main.py and counts toward coverage.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app, require_admin
from database import get_db
from db_models import User


class FakeQuery:
    """Minimal SQLAlchemy query stub. filter()/filter_by() are no-ops — tests
    set up the table contents directly so the filter conditions don't matter."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def filter_by(self, **__):
        return self

    def order_by(self, *_):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)


def mk_user(user_id, *, email="x@test.com", first="Test", last="User",
            is_admin=False, is_active=True, driver_type=None, phone=None):
    """Build a User stub with the attributes the handler reads/writes."""
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    u.first_name = first
    u.last_name = last
    u.phone = phone
    u.is_admin = is_admin
    u.is_active = is_active
    u.driver_type = driver_type
    u.last_login = None
    return u


@pytest.fixture
def mock_db():
    """A fake Session that supports query/add/commit/refresh for User rows."""
    db = MagicMock()
    db._tables = {User: []}
    db._added = []  # captures objects passed to db.add()

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    def _add(obj):
        db._added.append(obj)

    def _commit():
        # Mirror SQLAlchemy's flush-on-commit: assign an id to any added User
        # that doesn't have one yet so the response payload can read user.id.
        next_id = 1000
        for obj in db._added:
            if getattr(obj, "id", None) is None:
                obj.id = next_id
                next_id += 1

    def _refresh(obj):
        # No-op refresh — the handler reads attributes off the same object,
        # so we don't need to round-trip through the DB.
        return None

    db.query.side_effect = _query
    db.add.side_effect = _add
    db.commit.side_effect = _commit
    db.refresh.side_effect = _refresh
    return db


def _make_client(mock_db, current_user):
    """TestClient with get_db and require_admin overridden for one admin."""

    def _override_get_db():
        yield mock_db

    async def _override_require_admin():
        return current_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_admin] = _override_require_admin
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


ADMIN = mk_user(1, email="admin@test.com", first="Site", last="Admin",
                is_admin=True, driver_type=None)


# =====================================================================================
# POST /api/admin/users — default resolution
# =====================================================================================


class TestCreateUserDriverTypeDefaults:
    """Happy/Edge for the "non-admin → fleet, admin → NULL" defaulting rule."""

    def test_happy_non_admin_omitted_defaults_to_fleet(self, mock_db):
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new1@test.com",
            "first_name": "New",
            "last_name": "Hire",
            "is_admin": False,
        })
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] == "fleet"
        assert mock_db._added[0].driver_type == "fleet"

    def test_happy_admin_omitted_defaults_to_null(self, mock_db):
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new2@test.com",
            "first_name": "New",
            "last_name": "Admin",
            "is_admin": True,
        })
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] is None
        assert mock_db._added[0].driver_type is None

    def test_edge_non_admin_explicit_null_overrides_default(self, mock_db):
        """Caller explicitly sends null → stored as NULL, defaulting is skipped."""
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new3@test.com",
            "first_name": "Sys",
            "last_name": "Account",
            "is_admin": False,
            "driver_type": None,
        })
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] is None
        assert mock_db._added[0].driver_type is None

    def test_edge_admin_explicit_jockey_overrides_default(self, mock_db):
        """Admin who's also a jockey: explicit value wins."""
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new4@test.com",
            "first_name": "Mark",
            "last_name": "Custard",
            "is_admin": True,
            "driver_type": "jockey",
        })
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] == "jockey"
        assert mock_db._added[0].driver_type == "jockey"


# =====================================================================================
# POST /api/admin/users — explicit values + validation
# =====================================================================================


class TestCreateUserDriverTypeExplicit:

    def test_happy_non_admin_explicit_jockey(self, mock_db):
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new5@test.com",
            "first_name": "Karl",
            "last_name": "Walden",
            "is_admin": False,
            "driver_type": "jockey",
        })
        assert r.status_code == 200
        assert mock_db._added[0].driver_type == "jockey"

    def test_unhappy_invalid_driver_type_value(self, mock_db):
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new6@test.com",
            "first_name": "Bad",
            "last_name": "Value",
            "is_admin": False,
            "driver_type": "rocket",
        })
        assert r.status_code == 422
        assert mock_db._added == []

    def test_boundary_empty_string_rejected(self, mock_db):
        """Empty string isn't a valid Literal — should 422 before defaulting fires."""
        client = _make_client(mock_db, ADMIN)
        r = client.post("/api/admin/users", json={
            "email": "new7@test.com",
            "first_name": "Empty",
            "last_name": "Str",
            "is_admin": False,
            "driver_type": "",
        })
        assert r.status_code == 422
        assert mock_db._added == []


# =====================================================================================
# PUT /api/admin/users/{id} — model_fields_set semantics
# =====================================================================================


class TestUpdateUserDriverType:

    def test_happy_change_fleet_to_jockey(self, mock_db):
        target = mk_user(50, email="x@test.com", driver_type="fleet")
        mock_db._tables[User] = [target]
        client = _make_client(mock_db, ADMIN)

        r = client.put("/api/admin/users/50", json={"driver_type": "jockey"})
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] == "jockey"
        assert target.driver_type == "jockey"

    def test_happy_explicit_null_clears_existing_value(self, mock_db):
        """An admin reclassifying a former driver to admin-only must be able to
        send `driver_type: null` and have the column cleared."""
        target = mk_user(51, email="x@test.com", driver_type="fleet", is_admin=True)
        mock_db._tables[User] = [target]
        client = _make_client(mock_db, ADMIN)

        r = client.put("/api/admin/users/51", json={"driver_type": None})
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] is None
        assert target.driver_type is None

    def test_edge_omitted_payload_preserves_existing(self, mock_db):
        """A PUT that doesn't mention driver_type at all must leave it alone —
        the whole point of model_fields_set over `is not None`."""
        target = mk_user(52, email="x@test.com", driver_type="jockey")
        mock_db._tables[User] = [target]
        client = _make_client(mock_db, ADMIN)

        r = client.put("/api/admin/users/52", json={"first_name": "Renamed"})
        assert r.status_code == 200
        assert r.json()["user"]["driver_type"] == "jockey"
        assert target.driver_type == "jockey"

    def test_unhappy_invalid_value_rejected(self, mock_db):
        target = mk_user(53, email="x@test.com", driver_type="fleet")
        mock_db._tables[User] = [target]
        client = _make_client(mock_db, ADMIN)

        r = client.put("/api/admin/users/53", json={"driver_type": "rocket"})
        assert r.status_code == 422
        assert target.driver_type == "fleet"  # unchanged

    def test_boundary_user_not_found(self, mock_db):
        """Empty User table → handler raises 404 before the driver_type branch."""
        mock_db._tables[User] = []
        client = _make_client(mock_db, ADMIN)

        r = client.put("/api/admin/users/9999", json={"driver_type": "jockey"})
        assert r.status_code == 404
