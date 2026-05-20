"""
HUEB tests for smaller public-facing endpoints:

  POST /api/promo/validate
  POST /api/marketing/subscribe
  GET  /api/marketing/unsubscribe/{token}
  POST /api/marketing/unsubscribe/{token}
  GET  /api/stripe/config
  GET  /api/payments/{pid}/status
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz
from fastapi.testclient import TestClient
import main
from main import app
from database import get_db

UK = pytz.timezone("Europe/London")


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# POST /api/promo/validate
# ============================================================================

def _promo_code(**kw):
    base = dict(
        id=1, code="TAG-XYZ", promotion_id=1,
        is_used=False, used_at=None,
        max_uses=None, use_count=0,
        email_sent=False, recipient_email=None,
        expires_at=None,
        is_multi_use=False, can_be_used=True, uses_remaining=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _promotion(**kw):
    base = dict(id=1, name="Test Promo", discount_percent=10, discount_type=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestValidatePromo:
    def teardown_method(self):
        _clear()

    def _wire(self, promo_code=None, promotion=None, subscriber=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "PromoCode":
                chain.first.return_value = promo_code
            elif name == "Promotion":
                chain.first.return_value = promotion
            elif name == "MarketingSubscriber":
                chain.first.return_value = subscriber
            return chain
        db.query.side_effect = _query
        return db

    def test_H_valid_percentage_code(self):
        code = _promo_code()
        promo = _promotion(discount_percent=10)
        _override(self._wire(promo_code=code, promotion=promo))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-XYZ"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["discount_percent"] == 10
        assert body["discount_type"] == "percentage"

    def test_H_valid_free_100_code(self):
        code = _promo_code()
        promo = _promotion(discount_percent=100, discount_type="free_100")
        _override(self._wire(promo_code=code, promotion=promo))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-FREE"})
        assert resp.status_code == 200
        assert resp.json()["discount_type"] == "free_100"

    def test_H_100pct_defaults_to_free_week(self):
        """When discount_percent=100 and discount_type not set, defaults to free_week."""
        code = _promo_code()
        promo = _promotion(discount_percent=100, discount_type=None)
        _override(self._wire(promo_code=code, promotion=promo))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-WEEK"})
        assert resp.json()["discount_type"] == "free_week"

    def test_U_empty_code(self):
        _override(self._wire())
        resp = TestClient(app).post("/api/promo/validate", json={"code": ""})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert "enter a promo code" in resp.json()["message"].lower()

    def test_U_expired_code(self):
        code = _promo_code(expires_at=datetime(2020, 1, 1, tzinfo=pytz.UTC))
        _override(self._wire(promo_code=code))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-XYZ"})
        assert resp.json()["valid"] is False
        assert "expired" in resp.json()["message"].lower()

    def test_U_already_used_single_use(self):
        code = _promo_code(is_used=True, can_be_used=False, is_multi_use=False)
        _override(self._wire(promo_code=code))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-XYZ"})
        assert resp.json()["valid"] is False
        assert "beat you to it" in resp.json()["message"].lower()

    def test_U_exhausted_multi_use(self):
        code = _promo_code(is_multi_use=True, can_be_used=False,
                            max_uses=5, use_count=5)
        _override(self._wire(promo_code=code))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "TAG-XYZ"})
        assert resp.json()["valid"] is False
        assert "maximum" in resp.json()["message"].lower()

    def test_U_unknown_code(self):
        _override(self._wire(promo_code=None, subscriber=None))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "NEVER-SEEN"})
        assert resp.json()["valid"] is False
        assert "invalid" in resp.json()["message"].lower()

    def test_H_legacy_founder_promo(self):
        sub = SimpleNamespace(
            founder_promo_code="LEGACY-FNDR", founder_promo_used=False,
            promo_10_code=None, promo_10_used=False,
            promo_free_code=None, promo_free_used=False,
            promo_code=None, promo_code_used=False, discount_percent=None,
        )
        _override(self._wire(promo_code=None, subscriber=sub))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "LEGACY-FNDR"})
        assert resp.json()["valid"] is True
        assert resp.json()["discount_percent"] == 10

    def test_H_legacy_promo_free(self):
        sub = SimpleNamespace(
            founder_promo_code=None, founder_promo_used=False,
            promo_10_code=None, promo_10_used=False,
            promo_free_code="LEGACY-FREE", promo_free_used=False,
            promo_code=None, promo_code_used=False, discount_percent=None,
        )
        _override(self._wire(promo_code=None, subscriber=sub))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "LEGACY-FREE"})
        assert resp.json()["valid"] is True
        assert resp.json()["discount_percent"] == 100
        assert resp.json()["discount_type"] == "free_week"

    def test_U_legacy_already_used(self):
        sub = SimpleNamespace(
            founder_promo_code=None, founder_promo_used=False,
            promo_10_code="USED-CODE", promo_10_used=True,
            promo_free_code=None, promo_free_used=False,
            promo_code=None, promo_code_used=False, discount_percent=None,
        )
        _override(self._wire(promo_code=None, subscriber=sub))
        resp = TestClient(app).post("/api/promo/validate", json={"code": "USED-CODE"})
        assert resp.json()["valid"] is False
        assert "beat you to it" in resp.json()["message"].lower()


# ============================================================================
# POST /api/marketing/subscribe
# ============================================================================

class TestMarketingSubscribe:
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
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_H_new_subscriber(self, monkeypatch):
        monkeypatch.setattr(main, "check_promo_modal_subscriber_limits",
                            lambda db: None)
        _override(self._wire(None))
        resp = TestClient(app).post("/api/marketing/subscribe", json={
            "first_name": "Jo", "last_name": "K", "email": "jo@x.test",
        })
        assert resp.status_code == 200
        assert resp.json()["is_new_subscriber"] is True

    def test_E_already_subscribed(self):
        existing = SimpleNamespace(unsubscribed=False)
        _override(self._wire(existing))
        resp = TestClient(app).post("/api/marketing/subscribe", json={
            "first_name": "Jo", "last_name": "K", "email": "jo@x.test",
        })
        assert resp.status_code == 200
        assert resp.json()["is_new_subscriber"] is False
        assert "already on the list" in resp.json()["message"].lower()

    def test_E_resubscribe_after_unsubscribe(self):
        existing = SimpleNamespace(
            unsubscribed=True, unsubscribed_at=datetime(2026, 5, 1),
            first_name="Old", last_name="Name",
            welcome_email_sent=True, welcome_email_sent_at=datetime(2026, 5, 1),
            unsubscribe_token="old-token",
        )
        _override(self._wire(existing))
        resp = TestClient(app).post("/api/marketing/subscribe", json={
            "first_name": "Jo", "last_name": "K", "email": "jo@x.test",
        })
        assert resp.status_code == 200
        assert resp.json()["is_new_subscriber"] is True
        assert "re-subscribed" in resp.json()["message"].lower()
        assert existing.unsubscribed is False

    def test_U_db_exception(self, monkeypatch):
        db = self._wire(None)
        db.commit.side_effect = RuntimeError("constraint fail")
        _override(db)
        resp = TestClient(app).post("/api/marketing/subscribe", json={
            "first_name": "Jo", "last_name": "K", "email": "jo@x.test",
        })
        assert resp.status_code == 400


# ============================================================================
# GET + POST /api/marketing/unsubscribe/{token}
# ============================================================================

class TestUnsubscribe:
    def teardown_method(self):
        _clear()

    def _wire(self, subscriber):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = subscriber
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_GET_shows_confirmation_page(self):
        sub = SimpleNamespace(unsubscribed=False, email="jo@x.test")
        _override(self._wire(sub))
        resp = TestClient(app).get("/api/marketing/unsubscribe/tok-123")
        assert resp.status_code == 200
        assert "Unsubscribe" in resp.text
        assert "jo@x.test" in resp.text

    def test_E_GET_invalid_token(self):
        _override(self._wire(None))
        resp = TestClient(app).get("/api/marketing/unsubscribe/invalid")
        assert resp.status_code == 404
        assert "Invalid Link" in resp.text

    def test_E_GET_already_unsubscribed(self):
        sub = SimpleNamespace(unsubscribed=True, email="jo@x.test")
        _override(self._wire(sub))
        resp = TestClient(app).get("/api/marketing/unsubscribe/tok-123")
        assert resp.status_code == 200
        assert "Already Unsubscribed" in resp.text

    def test_H_POST_unsubscribes(self):
        sub = SimpleNamespace(
            unsubscribed=False, email="jo@x.test", first_name="Jo",
            unsubscribed_at=None,
        )
        _override(self._wire(sub))
        resp = TestClient(app).post("/api/marketing/unsubscribe/tok-123")
        assert resp.status_code == 200
        assert sub.unsubscribed is True
        assert sub.unsubscribed_at is not None

    def test_E_POST_invalid_token(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/marketing/unsubscribe/invalid")
        # 404 with HTML response
        assert resp.status_code in (200, 404)


# ============================================================================
# GET /api/stripe/config
# ============================================================================

class TestStripeConfig:
    def teardown_method(self):
        _clear()

    def test_H_returns_publishable_key(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(main, "get_settings",
                            lambda: SimpleNamespace(stripe_publishable_key="pk_test_xxx"))
        resp = TestClient(app).get("/api/stripe/config")
        assert resp.status_code == 200
        assert resp.json()["publishable_key"] == "pk_test_xxx"
        assert resp.json()["is_configured"] is True

    def test_U_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: False)
        resp = TestClient(app).get("/api/stripe/config")
        assert resp.status_code == 503


# ============================================================================
# GET /api/payments/{pid}/status
# ============================================================================

class TestPaymentStatus:
    def teardown_method(self):
        _clear()

    def test_H_returns_status(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        monkeypatch.setattr(main, "get_payment_status", lambda pid: SimpleNamespace(
            payment_intent_id=pid, status="succeeded", amount=9900,
            booking_reference="TAG-1",
        ))
        resp = TestClient(app).get("/api/payments/pi_1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "succeeded"
        assert body["paid"] is True
        assert body["amount_display"] == "£99.00"

    def test_U_stripe_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: False)
        resp = TestClient(app).get("/api/payments/pi_1/status")
        assert resp.status_code == 503

    def test_U_exception(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
        def boom(pid):
            raise RuntimeError("Payment not found")
        monkeypatch.setattr(main, "get_payment_status", boom)
        resp = TestClient(app).get("/api/payments/pi_1/status")
        assert resp.status_code == 400
