"""
HUEB tests for the four marketing-subscriber send endpoints in main.py.

Endpoints:
  POST /api/admin/marketing-subscribers/{id}/send-promo                 (10% or 100%)
  POST /api/admin/marketing-subscribers/{id}/send-founder-email
  POST /api/admin/marketing-subscribers/{id}/send-promo-10-reminder
  POST /api/admin/marketing-subscribers/{id}/send-promo-free-reminder
"""
from datetime import datetime
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


def _sub(**kw):
    base = dict(
        id=11, email="jo@x.test", first_name="Jo",
        unsubscribed=False,
        promo_code=None,
        promo_10_code=None, promo_10_used=False, promo_10_sent=False, promo_10_sent_at=None,
        promo_10_reminder_sent=False, promo_10_reminder_sent_at=None,
        promo_free_code=None, promo_free_used=False, promo_free_sent=False, promo_free_sent_at=None,
        promo_free_reminder_sent=False, promo_free_reminder_sent_at=None,
        founder_promo_code=None, founder_promo_used=False, founder_email_sent=False,
        founder_email_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _wire_first(sub, collision_subscriber=None):
    """DB stub: first .first() returns the target sub; subsequent .first() calls
    (for uniqueness checks) return collision_subscriber."""
    db = MagicMock()
    calls = {"n": 0}
    chain = MagicMock()
    chain.filter.return_value = chain
    def first():
        calls["n"] += 1
        if calls["n"] == 1:
            return sub
        return collision_subscriber
    chain.first.side_effect = first
    db.query.return_value = chain
    db.commit = MagicMock()
    return db


# ============================================================================
# send-promo (10% or 100%)
# ============================================================================

class TestSendPromo:
    def teardown_method(self):
        _clear()

    def test_H_10pct_generates_and_sends(self, monkeypatch):
        sub = _sub()
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.generate_promo_code", lambda: "TAG-10PC-CODE")
        monkeypatch.setattr("email_service.send_promo_code_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["discount_percent"] == 10
        assert sub.promo_10_code == "TAG-10PC-CODE"
        assert sub.promo_10_sent is True

    def test_H_100pct_uses_free_branch(self, monkeypatch):
        sub = _sub()
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.generate_promo_code", lambda: "TAG-FREE-CODE")
        monkeypatch.setattr(main, "send_free_parking_promo_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo?discount_percent=100")
        assert resp.status_code == 200
        assert sub.promo_free_code == "TAG-FREE-CODE"
        assert sub.promo_free_sent is True

    def test_H_reuse_existing_promo_10_code(self, monkeypatch):
        sub = _sub(promo_10_code="TAG-EXIST")
        _override(_wire_first(sub))
        gen_calls = {"n": 0}
        def gen():
            gen_calls["n"] += 1
            return "should-not-be-used"
        monkeypatch.setattr("email_service.generate_promo_code", gen)
        monkeypatch.setattr("email_service.send_promo_code_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo")
        assert resp.status_code == 200
        assert gen_calls["n"] == 0
        assert sub.promo_10_code == "TAG-EXIST"

    def test_U_subscriber_not_found(self):
        _override(_wire_first(None))
        resp = TestClient(app).post("/api/admin/marketing-subscribers/9999/send-promo")
        assert resp.status_code == 404

    def test_U_unsubscribed(self):
        sub = _sub(unsubscribed=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo")
        assert resp.status_code == 400
        assert "unsubscribed" in resp.json()["detail"].lower()

    def test_U_invalid_discount_percent(self):
        sub = _sub()
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo?discount_percent=50")
        assert resp.status_code == 400
        assert "10 or 100" in resp.json()["detail"]

    def test_U_promo_10_already_used(self):
        sub = _sub(promo_10_used=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo")
        assert resp.status_code == 400
        assert "10% promo" in resp.json()["detail"]

    def test_U_promo_free_already_used(self):
        sub = _sub(promo_free_used=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo?discount_percent=100")
        assert resp.status_code == 400
        assert "FREE promo" in resp.json()["detail"]

    def test_U_email_send_fails(self, monkeypatch):
        sub = _sub()
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.generate_promo_code", lambda: "TAG-X")
        monkeypatch.setattr("email_service.send_promo_code_email", lambda **kw: False)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo")
        assert resp.status_code == 500
        assert "failed to send" in resp.json()["detail"].lower()


# ============================================================================
# send-founder-email
# ============================================================================

class TestSendFounderEmail:
    def teardown_method(self):
        _clear()

    def test_H_sends_with_new_code(self, monkeypatch):
        sub = _sub()
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.generate_promo_code", lambda: "TAG-FNDR")
        monkeypatch.setattr("email_service.send_founder_thank_you_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-founder-email")
        assert resp.status_code == 200
        assert sub.founder_promo_code == "TAG-FNDR"
        assert sub.founder_email_sent is True

    def test_H_reuses_existing_founder_code(self, monkeypatch):
        sub = _sub(founder_promo_code="TAG-FNDR-OLD")
        _override(_wire_first(sub))
        gen_calls = {"n": 0}
        monkeypatch.setattr("email_service.generate_promo_code",
                            lambda: (gen_calls.__setitem__("n", gen_calls["n"] + 1) or "X"))
        monkeypatch.setattr("email_service.send_founder_thank_you_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-founder-email")
        assert resp.status_code == 200
        assert gen_calls["n"] == 0
        assert sub.founder_promo_code == "TAG-FNDR-OLD"

    def test_U_not_found(self):
        _override(_wire_first(None))
        resp = TestClient(app).post("/api/admin/marketing-subscribers/9999/send-founder-email")
        assert resp.status_code == 404

    def test_U_unsubscribed(self):
        sub = _sub(unsubscribed=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-founder-email")
        assert resp.status_code == 400

    def test_U_founder_promo_used(self):
        sub = _sub(founder_promo_used=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-founder-email")
        assert resp.status_code == 400

    def test_U_send_fails(self, monkeypatch):
        sub = _sub()
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.generate_promo_code", lambda: "X")
        monkeypatch.setattr("email_service.send_founder_thank_you_email", lambda **kw: False)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-founder-email")
        assert resp.status_code == 500


# ============================================================================
# send-promo-10-reminder
# ============================================================================

class TestSendPromo10Reminder:
    def teardown_method(self):
        _clear()

    def test_H_sends(self, monkeypatch):
        sub = _sub(promo_10_code="TAG-A")
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.send_promo_10_reminder_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 200
        assert sub.promo_10_reminder_sent is True

    def test_U_not_found(self):
        _override(_wire_first(None))
        resp = TestClient(app).post("/api/admin/marketing-subscribers/9999/send-promo-10-reminder")
        assert resp.status_code == 404

    def test_U_unsubscribed(self):
        sub = _sub(unsubscribed=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 400

    def test_U_no_promo_10_code(self):
        sub = _sub(promo_10_code=None)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 400
        assert "does not have" in resp.json()["detail"].lower()

    def test_U_already_used(self):
        sub = _sub(promo_10_code="TAG-A", promo_10_used=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 400
        assert "already used" in resp.json()["detail"].lower()

    def test_U_already_sent_with_timestamp(self):
        sub = _sub(promo_10_code="TAG-A",
                   promo_10_reminder_sent=True,
                   promo_10_reminder_sent_at=datetime(2026, 5, 1, 12, 0, 0))
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 400
        # Verify the UK-formatted timestamp made it into the message
        assert "01 May 2026" in resp.json()["detail"]

    def test_U_already_sent_unknown_date(self):
        sub = _sub(promo_10_code="TAG-A",
                   promo_10_reminder_sent=True,
                   promo_10_reminder_sent_at=None)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 400
        assert "unknown date" in resp.json()["detail"].lower()

    def test_U_email_fails(self, monkeypatch):
        sub = _sub(promo_10_code="TAG-A")
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.send_promo_10_reminder_email", lambda **kw: False)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-10-reminder")
        assert resp.status_code == 500


# ============================================================================
# send-promo-free-reminder
# ============================================================================

class TestSendPromoFreeReminder:
    def teardown_method(self):
        _clear()

    def test_H_sends(self, monkeypatch):
        sub = _sub(promo_free_code="TAG-FREE")
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.send_promo_free_reminder_email", lambda **kw: True)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 200
        assert sub.promo_free_reminder_sent is True

    def test_U_not_found(self):
        _override(_wire_first(None))
        resp = TestClient(app).post("/api/admin/marketing-subscribers/9999/send-promo-free-reminder")
        assert resp.status_code == 404

    def test_U_unsubscribed(self):
        sub = _sub(unsubscribed=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 400

    def test_U_no_free_code(self):
        sub = _sub(promo_free_code=None)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 400

    def test_U_already_used(self):
        sub = _sub(promo_free_code="TAG-FREE", promo_free_used=True)
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 400

    def test_U_already_sent(self):
        sub = _sub(promo_free_code="TAG-FREE",
                   promo_free_reminder_sent=True,
                   promo_free_reminder_sent_at=datetime(2026, 5, 1, 12, 0, 0))
        _override(_wire_first(sub))
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 400

    def test_U_email_fails(self, monkeypatch):
        sub = _sub(promo_free_code="TAG-FREE")
        _override(_wire_first(sub))
        monkeypatch.setattr("email_service.send_promo_free_reminder_email", lambda **kw: False)
        resp = TestClient(app).post(f"/api/admin/marketing-subscribers/{sub.id}/send-promo-free-reminder")
        assert resp.status_code == 500
