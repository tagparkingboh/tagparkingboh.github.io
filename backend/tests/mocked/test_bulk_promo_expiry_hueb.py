"""
HUEB tests for PATCH /api/admin/promo-codes/bulk-expiry (main.py:8259-8370).
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


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


def _code(**kw):
    base = dict(id=11, code="TAG-1", expires_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _wire(codes):
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.all.return_value = codes
    db.query.return_value = chain
    db.commit = MagicMock()
    return db


class TestBulkPromoExpiry:
    def teardown_method(self):
        _clear()

    def test_H_sets_expiry(self):
        c1 = _code(id=11)
        c2 = _code(id=12, code="TAG-2")
        _override(_wire([c1, c2]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11, 12],
            "expiry_date": "31/12/2026", "expiry_time": "23:59",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2
        assert c1.expires_at is not None
        assert c2.expires_at is not None

    def test_H_removes_expiry(self):
        c = _code(expires_at=datetime(2026, 5, 1))
        _override(_wire([c]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": None, "expiry_time": None,
        })
        assert resp.status_code == 200
        assert c.expires_at is None

    def test_U_empty_code_ids(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [],
        })
        assert resp.status_code == 400
        assert "no code ids" in resp.json()["detail"].lower()

    def test_U_too_many_codes(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": list(range(501)),
        })
        assert resp.status_code == 400
        assert "500" in resp.json()["detail"]

    def test_U_partial_date_only(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": "31/12/2026",  # missing time
        })
        assert resp.status_code == 400

    def test_U_invalid_date_format(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": "bogus", "expiry_time": "23:59",
        })
        assert resp.status_code == 400

    def test_U_invalid_time_format(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": "31/12/2026", "expiry_time": "bogus",
        })
        assert resp.status_code == 400

    def test_U_date_out_of_range(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": "32/12/2026", "expiry_time": "23:59",
        })
        assert resp.status_code == 400

    def test_U_time_out_of_range(self):
        _override(_wire([]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11], "expiry_date": "31/12/2026", "expiry_time": "25:00",
        })
        assert resp.status_code == 400

    def test_U_some_codes_not_found(self):
        # Request 3 ids but only 2 returned
        c1 = _code(id=11)
        c2 = _code(id=12)
        _override(_wire([c1, c2]))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": [11, 12, 99], "expiry_date": "31/12/2026",
            "expiry_time": "23:59",
        })
        assert resp.status_code == 404
        assert "99" in resp.json()["detail"]

    def test_B_500_codes_exactly(self):
        codes = [_code(id=i) for i in range(1, 501)]
        _override(_wire(codes))
        resp = TestClient(app).patch("/api/admin/promo-codes/bulk-expiry", json={
            "code_ids": list(range(1, 501)),
        })
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 500
