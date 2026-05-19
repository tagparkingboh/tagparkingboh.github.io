"""
HUEB tests for the admin promotions family in main.py.

Endpoints covered:
  POST   /api/admin/promotions                          (create_promotion)
  GET    /api/admin/promotions                          (list_promotions)
  GET    /api/admin/promotions/{id}                     (get_promotion)
  PATCH  /api/admin/promotions/{id}                     (update_promotion)
  DELETE /api/admin/promotions/{id}                     (delete_promotion)
  POST   /api/admin/promotions/{id}/generate-codes      (generate_more_codes)
  GET    /api/admin/promotions/{id}/available-codes     (get_available_codes)
  PATCH  /api/admin/promo-codes/{id}/share-socials      (mark_code_shared_on_socials)
  PATCH  /api/admin/promo-codes/{id}/share-privately    (mark_code_shared_privately)
  PATCH  /api/admin/promo-codes/{id}/expiry             (update_promo_code_expiry)
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


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _clear():
    app.dependency_overrides.clear()


def _promotion(**kw):
    base = dict(
        id=1, name="Spring 2026", description=None,
        discount_percent=10, discount_type=None,
        total_codes=10, codes_sent=0, codes_used=0,
        code_prefix="TAG", created_by="admin@tag.test",
        created_at=datetime(2026, 5, 1, 9, 0),
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _code(**kw):
    base = dict(
        id=11, code="TAG-AAAA-BBBB",
        promotion_id=1, promotion=None,
        recipient_email=None, recipient_first_name=None, recipient_last_name=None,
        customer_id=None, subscriber_id=None,
        email_sent=False, email_sent_at=None,
        shared_on_socials=False, shared_on_socials_at=None,
        shared_privately=False, shared_privately_at=None,
        is_used=False, used_at=None,
        booking_id=None,
        expires_at=None,
        created_at=datetime(2026, 5, 1, 9, 0),
        max_uses=None, use_count=0,
        is_multi_use=False,
        uses_remaining=1,
        can_be_used=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# POST /api/admin/promotions — create_promotion
# ============================================================================

class TestCreatePromotion:
    def teardown_method(self):
        _clear()

    def _wire(self, code_collision=None):
        """code_collision: a stub returned by first .first() lookup checking
        if the code exists. None means no collision."""
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = code_collision
        db.query.return_value = chain
        added = []
        def _add(obj):
            obj.id = 100
            obj.created_at = datetime(2026, 5, 1)
            obj.codes_sent = 0
            obj.codes_used = 0
            added.append(obj)
        db.add.side_effect = _add
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_creates_with_random_codes(self, monkeypatch):
        _override(self._wire())
        monkeypatch.setattr(main, "generate_promo_code", lambda prefix=None: "TAG-XYZ")
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "Spring Promo", "discount_percent": 10, "total_codes": 5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Spring Promo"
        assert body["discount_percent"] == 10

    def test_H_with_custom_code(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "Single", "discount_percent": 100,
            "custom_code": "SUMMER10",
        })
        assert resp.status_code == 200

    def test_H_with_expiry(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "Expiring", "discount_percent": 20,
            "custom_code": "EXPIRE1",
            "expiry_date": "31/12/2026", "expiry_time": "23:59",
        })
        assert resp.status_code == 200

    def test_H_with_max_uses(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "Multi", "discount_percent": 25,
            "custom_code": "MULTI",
            "max_uses": 5,
        })
        assert resp.status_code == 200

    def test_U_missing_required_name(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "discount_percent": 10, "total_codes": 5,
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()

    def test_U_invalid_discount_percent(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 99, "total_codes": 5,
        })
        assert resp.status_code == 400
        assert "discount_percent" in resp.json()["detail"]

    def test_U_invalid_total_codes(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "total_codes": 5000,
        })
        assert resp.status_code == 400
        assert "1 and 1000" in resp.json()["detail"]

    def test_U_custom_code_already_exists(self):
        existing = _code(code="TAKEN")
        _override(self._wire(code_collision=existing))
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "custom_code": "TAKEN",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_U_invalid_expiry_format(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "custom_code": "X",
            "expiry_date": "bogus", "expiry_time": "23:59",
        })
        assert resp.status_code == 400

    def test_U_negative_max_uses(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "custom_code": "X",
            "max_uses": -5,
        })
        assert resp.status_code == 400
        assert "negative" in resp.json()["detail"].lower()

    def test_U_invalid_max_uses_string(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "custom_code": "X",
            "max_uses": "abc",
        })
        assert resp.status_code == 400

    def test_U_invalid_discount_type(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10, "custom_code": "X",
            "discount_type": "bogus",
        })
        assert resp.status_code == 400

    def test_E_custom_code_alphanumeric_sanitization(self):
        """Non-alphanumeric chars in custom_code are stripped."""
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/promotions", json={
            "name": "x", "discount_percent": 10,
            "custom_code": "SUM-MER!10",  # becomes SUMMER10
        })
        assert resp.status_code == 200


# ============================================================================
# GET /api/admin/promotions — list_promotions
# ============================================================================

class TestListPromotions:
    def teardown_method(self):
        _clear()

    def test_H_lists(self):
        p = _promotion()
        db = MagicMock()
        # Aggregate queries via .group_by().all() return list of (id, count)
        agg_chain = MagicMock()
        agg_chain.filter.return_value = agg_chain
        agg_chain.group_by.return_value = agg_chain
        agg_chain.all.return_value = [(1, 3)]

        prom_chain = MagicMock()
        prom_chain.order_by.return_value = prom_chain
        prom_chain.all.return_value = [p]

        def _query(*args):
            # Aggregate queries pass tuple/expressions, list query passes Promotion class
            if len(args) > 1:
                return agg_chain
            return prom_chain

        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).get("/api/admin/promotions")
        assert resp.status_code == 200
        promos = resp.json()["promotions"]
        assert len(promos) == 1
        assert promos[0]["name"] == "Spring 2026"

    def test_E_empty(self):
        db = MagicMock()
        agg_chain = MagicMock()
        agg_chain.filter.return_value = agg_chain
        agg_chain.group_by.return_value = agg_chain
        agg_chain.all.return_value = []
        prom_chain = MagicMock()
        prom_chain.order_by.return_value = prom_chain
        prom_chain.all.return_value = []
        def _query(*args):
            return agg_chain if len(args) > 1 else prom_chain
        db.query.side_effect = _query
        _override(db)
        resp = TestClient(app).get("/api/admin/promotions")
        assert resp.status_code == 200
        assert resp.json()["promotions"] == []


# ============================================================================
# GET /api/admin/promotions/{id} — get_promotion
# ============================================================================

class TestGetPromotion:
    def teardown_method(self):
        _clear()

    def _wire(self, promotion, codes=None):
        db = MagicMock()
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            if name == "Promotion":
                chain.first.return_value = promotion
            elif name == "PromoCode":
                chain.all.return_value = codes or []
                chain.count.return_value = 0
            elif name == "PromoCodeUsage":
                chain.all.return_value = []
            elif name == "Booking":
                chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        return db

    def test_H_returns_with_codes(self):
        p = _promotion()
        c = _code()
        _override(self._wire(p, codes=[c]))
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert len(body["codes"]) == 1

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).get("/api/admin/promotions/9999")
        assert resp.status_code == 404

    def test_E_promotion_no_codes(self):
        p = _promotion()
        _override(self._wire(p, codes=[]))
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["codes"] == []

    def test_E_expired_code_branch(self):
        p = _promotion()
        # Code with expiry in the past
        c = _code(expires_at=datetime(2020, 1, 1, tzinfo=__import__('pytz').UTC))
        _override(self._wire(p, codes=[c]))
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["codes"][0]["is_expired"] is True


# ============================================================================
# PATCH /api/admin/promotions/{id} — update_promotion
# ============================================================================

class TestUpdatePromotion:
    def teardown_method(self):
        _clear()

    def _wire(self, promotion):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            if model.__name__ == "Promotion":
                chain.first.return_value = promotion
            elif model.__name__ == "PromoCode":
                chain.count.return_value = 0
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_updates_name(self):
        p = _promotion()
        _override(self._wire(p))
        resp = TestClient(app).patch(f"/api/admin/promotions/{p.id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert p.name == "New Name"
        assert resp.json()["name"] == "New Name"

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).patch("/api/admin/promotions/9999", json={"name": "x"})
        assert resp.status_code == 404

    def test_U_missing_name_returns_422(self):
        p = _promotion()
        _override(self._wire(p))
        resp = TestClient(app).patch(f"/api/admin/promotions/{p.id}", json={})
        assert resp.status_code == 422


# ============================================================================
# DELETE /api/admin/promotions/{id} — delete_promotion
# ============================================================================

class TestDeletePromotion:
    def teardown_method(self):
        _clear()

    def _wire(self, promotion, shared_socials=0, shared_privately=0):
        db = MagicMock()
        # Stash a counter so the two shared queries return different counts
        call_counts = {"PromoCode_count": 0}
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            if name == "Promotion":
                chain.first.return_value = promotion
            elif name == "PromoCode":
                call_counts["PromoCode_count"] += 1
                # First .count() = shared_on_socials, second = shared_privately
                if call_counts["PromoCode_count"] == 1:
                    chain.count.return_value = shared_socials
                else:
                    chain.count.return_value = shared_privately
                chain.delete.return_value = 5
            return chain
        db.query.side_effect = _query
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes_unused(self):
        p = _promotion(codes_sent=0, codes_used=0)
        _override(self._wire(p))
        resp = TestClient(app).delete(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).delete("/api/admin/promotions/9999")
        assert resp.status_code == 404

    def test_U_codes_sent(self):
        p = _promotion(codes_sent=3)
        _override(self._wire(p))
        resp = TestClient(app).delete(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 400
        assert "3 email" in resp.json()["detail"]

    def test_U_codes_used(self):
        p = _promotion(codes_used=2)
        _override(self._wire(p))
        resp = TestClient(app).delete(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 400
        assert "2 code" in resp.json()["detail"]

    def test_U_shared_on_socials(self):
        p = _promotion()
        _override(self._wire(p, shared_socials=1))
        resp = TestClient(app).delete(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 400
        assert "shared on socials" in resp.json()["detail"].lower()

    def test_U_shared_privately(self):
        p = _promotion()
        _override(self._wire(p, shared_privately=1))
        resp = TestClient(app).delete(f"/api/admin/promotions/{p.id}")
        assert resp.status_code == 400
        assert "shared privately" in resp.json()["detail"].lower()


# ============================================================================
# POST /api/admin/promotions/{id}/generate-codes
# ============================================================================

class TestGenerateMoreCodes:
    def teardown_method(self):
        _clear()

    def _wire(self, promotion):
        db = MagicMock()
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            if name == "Promotion":
                chain.first.return_value = promotion
            elif name == "PromoCode":
                chain.first.return_value = None  # no collisions
                chain.count.return_value = 0
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_generates_codes(self, monkeypatch):
        p = _promotion(total_codes=10)
        _override(self._wire(p))
        monkeypatch.setattr(main, "generate_promo_code", lambda prefix=None: "TAG-NEW")
        resp = TestClient(app).post(f"/api/admin/promotions/{p.id}/generate-codes",
                                    json={"count": 3})
        assert resp.status_code == 200
        assert resp.json()["codes_created"] == 3
        assert p.total_codes == 13

    def test_U_promotion_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/promotions/9999/generate-codes",
                                    json={"count": 1})
        assert resp.status_code == 404

    def test_U_invalid_count(self):
        p = _promotion()
        _override(self._wire(p))
        resp = TestClient(app).post(f"/api/admin/promotions/{p.id}/generate-codes",
                                    json={"count": 5000})
        assert resp.status_code == 400

    def test_U_count_zero(self):
        p = _promotion()
        _override(self._wire(p))
        resp = TestClient(app).post(f"/api/admin/promotions/{p.id}/generate-codes",
                                    json={"count": 0})
        assert resp.status_code == 400

    def test_U_invalid_expiry(self):
        p = _promotion()
        _override(self._wire(p))
        resp = TestClient(app).post(f"/api/admin/promotions/{p.id}/generate-codes",
                                    json={"count": 1, "expiry_date": "bogus", "expiry_time": "23:59"})
        assert resp.status_code == 400


# ============================================================================
# GET /api/admin/promotions/{id}/available-codes
# ============================================================================

class TestGetAvailableCodes:
    def teardown_method(self):
        _clear()

    def _wire(self, promotion, codes):
        db = MagicMock()
        def _query(model):
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            if name == "Promotion":
                chain.first.return_value = promotion
            elif name == "PromoCode":
                chain.limit.return_value.all.return_value = codes
            return chain
        db.query.side_effect = _query
        return db

    def test_H_returns_available(self):
        p = _promotion()
        _override(self._wire(p, codes=[_code(), _code(id=12, code="TAG-OTHER")]))
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}/available-codes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available_count"] == 2

    def test_U_promotion_not_found(self):
        _override(self._wire(None, codes=[]))
        resp = TestClient(app).get("/api/admin/promotions/9999/available-codes")
        assert resp.status_code == 404

    def test_E_no_codes_available(self):
        p = _promotion()
        _override(self._wire(p, codes=[]))
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}/available-codes")
        assert resp.status_code == 200
        assert resp.json()["codes"] == []

    def test_B_limit_capped(self):
        p = _promotion()
        _override(self._wire(p, codes=[]))
        # limit must be between 1 and 500 per Query() constraints
        resp = TestClient(app).get(f"/api/admin/promotions/{p.id}/available-codes?limit=999")
        assert resp.status_code == 422


# ============================================================================
# PATCH /api/admin/promo-codes/{id}/share-socials
# ============================================================================

class TestShareSocials:
    def teardown_method(self):
        _clear()

    def _wire(self, code):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = code
        db.commit = MagicMock()
        return db

    def test_H_marks_shared(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-socials")
        assert resp.status_code == 200
        assert resp.json()["shared_on_socials"] is True
        assert c.shared_on_socials is True

    def test_H_toggles_off(self):
        c = _code(shared_on_socials=True, shared_on_socials_at=datetime(2026, 5, 1))
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-socials")
        assert resp.status_code == 200
        assert resp.json()["shared_on_socials"] is False
        assert c.shared_on_socials is False

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).patch("/api/admin/promo-codes/9999/share-socials")
        assert resp.status_code == 404

    def test_U_used_code_cannot_share(self):
        c = _code(is_used=True, shared_on_socials=False)
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-socials")
        assert resp.status_code == 400
        assert "used code" in resp.json()["detail"].lower()

    def test_U_already_shared_privately(self):
        c = _code(shared_privately=True, shared_on_socials=False)
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-socials")
        assert resp.status_code == 400
        assert "already shared privately" in resp.json()["detail"].lower()


# ============================================================================
# PATCH /api/admin/promo-codes/{id}/share-privately
# ============================================================================

class TestSharePrivately:
    def teardown_method(self):
        _clear()

    def _wire(self, code):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = code
        db.commit = MagicMock()
        return db

    def test_H_marks_shared(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-privately")
        assert resp.status_code == 200
        assert c.shared_privately is True

    def test_H_toggles_off(self):
        c = _code(shared_privately=True, shared_privately_at=datetime(2026, 5, 1))
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-privately")
        assert resp.status_code == 200
        assert c.shared_privately is False

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).patch("/api/admin/promo-codes/9999/share-privately")
        assert resp.status_code == 404

    def test_U_used_code_cannot_share(self):
        c = _code(is_used=True, shared_privately=False)
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-privately")
        assert resp.status_code == 400

    def test_U_already_shared_on_socials(self):
        c = _code(shared_on_socials=True, shared_privately=False)
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/share-privately")
        assert resp.status_code == 400


# ============================================================================
# PATCH /api/admin/promo-codes/{id}/expiry
# ============================================================================

class TestUpdateExpiry:
    def teardown_method(self):
        _clear()

    def _wire(self, code):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = code
        db.commit = MagicMock()
        return db

    def test_H_sets_expiry(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "31/12/2026", "expiry_time": "23:59"})
        assert resp.status_code == 200
        assert c.expires_at is not None

    def test_H_removes_expiry(self):
        c = _code(expires_at=datetime(2026, 5, 1))
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": None, "expiry_time": None})
        assert resp.status_code == 200
        assert c.expires_at is None

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).patch("/api/admin/promo-codes/9999/expiry",
                                     json={"expiry_date": "31/12/2026", "expiry_time": "23:59"})
        assert resp.status_code == 404

    def test_U_partial_expiry_rejected(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "31/12/2026"})  # missing time
        assert resp.status_code == 400

    def test_U_invalid_date_format(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "bogus", "expiry_time": "23:59"})
        assert resp.status_code == 400

    def test_U_invalid_time_format(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "31/12/2026", "expiry_time": "bogus"})
        assert resp.status_code == 400

    def test_U_date_out_of_range(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "31/13/2026", "expiry_time": "23:59"})
        assert resp.status_code == 400

    def test_U_time_out_of_range(self):
        c = _code()
        _override(self._wire(c))
        resp = TestClient(app).patch(f"/api/admin/promo-codes/{c.id}/expiry",
                                     json={"expiry_date": "31/12/2026", "expiry_time": "25:00"})
        assert resp.status_code == 400
