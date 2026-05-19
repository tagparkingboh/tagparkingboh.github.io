"""
HUEB tests for testimonials + promo-modal endpoints in main.py.

Testimonials (lines 14844-15166):
  GET    /api/admin/testimonials                     (list with filters)
  POST   /api/admin/testimonials                     (create)
  PUT    /api/admin/testimonials/{id}                (update)
  DELETE /api/admin/testimonials/{id}                (delete)
  PATCH  /api/admin/testimonials/{id}/status         (toggle)
  GET    /api/testimonials                           (public weighted pool + stats)

Promo modal (lines 15173-15733):
  GET    /api/admin/promo-modals                     (list)
  POST   /api/admin/promo-modals                     (create)
  PUT    /api/admin/promo-modals/{id}                (update)
  DELETE /api/admin/promo-modals/{id}                (delete)
  PATCH  /api/admin/promo-modals/{id}/status         (toggle)
  GET    /api/promo-modal                            (public info_modal lookup)
  GET    /api/promo-section                          (public promo_section lookup)
  POST   /api/promo-modal/{id}/view                  (track view)
  POST   /api/promo-modal/{id}/click                 (track click)
"""
from datetime import date as date_type, datetime
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


def _override_admin(db, user=None):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: user or _admin()


def _override_public(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


# ============================================================================
# Testimonials
# ============================================================================

def _testimonial(**kw):
    from db_models import TestimonialStatus
    try:
        active = TestimonialStatus.ACTIVE
    except Exception:
        active = SimpleNamespace(value="active")
    base = dict(
        id=1, customer_name="Jane Doe",
        review_text="Amazing parking service, friendly staff, would use again. Very professional.",
        star_rating=5,
        date_of_travel=date_type(2026, 4, 1),
        date_added=datetime(2026, 5, 1),
        status=active, is_featured=False, source="Google",
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestAdminListTestimonials:
    def teardown_method(self):
        _clear()

    def _wire(self, items):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = items
        db.query.return_value = chain
        return db

    def test_H_list_returns_items(self):
        _override_admin(self._wire([_testimonial()]))
        resp = TestClient(app).get("/api/admin/testimonials")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_H_filter_by_star_rating(self):
        _override_admin(self._wire([_testimonial(star_rating=5)]))
        resp = TestClient(app).get("/api/admin/testimonials?star_rating=5")
        assert resp.status_code == 200

    def test_H_filter_by_status_active(self):
        _override_admin(self._wire([_testimonial()]))
        resp = TestClient(app).get("/api/admin/testimonials?status=active")
        assert resp.status_code == 200

    def test_H_filter_by_status_inactive(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/testimonials?status=inactive")
        assert resp.status_code == 200

    def test_H_sort_by_star_rating_asc(self):
        _override_admin(self._wire([_testimonial()]))
        resp = TestClient(app).get("/api/admin/testimonials?sort=star_rating&order=asc")
        assert resp.status_code == 200

    def test_E_empty(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/testimonials")
        assert resp.json()["total"] == 0


class TestAdminCreateTestimonial:
    def teardown_method(self):
        _clear()

    def _wire(self):
        db = MagicMock()
        added = []
        def _add(obj):
            obj.id = 99
            obj.date_added = datetime(2026, 5, 1)
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_creates(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "Jane Doe",
            "review_text": "Excellent service all round - friendly staff",
            "star_rating": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_H_unrated(self):
        """LinkedIn/FB-style reviews without star ratings."""
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "Jane Doe",
            "review_text": "Loved the service from start to finish - amazing experience",
            "source": "LinkedIn",
        })
        assert resp.status_code == 200

    def test_U_review_too_short(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "x", "review_text": "short",
        })
        assert resp.status_code == 422

    def test_U_star_out_of_range(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "Jane",
            "review_text": "Great service for the price - amazing",
            "star_rating": 99,
        })
        assert resp.status_code == 422

    def test_U_customer_name_too_long(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "x" * 101,
            "review_text": "Great service all round - amazing experience",
        })
        assert resp.status_code == 422

    def test_U_invalid_status(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/testimonials", json={
            "customer_name": "Jane",
            "review_text": "Great service for the price - amazing experience",
            "status": "bogus",
        })
        assert resp.status_code == 422


class TestAdminUpdateTestimonial:
    def teardown_method(self):
        _clear()

    def _wire(self, t):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = t
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_updates(self):
        t = _testimonial()
        _override_admin(self._wire(t))
        resp = TestClient(app).put(f"/api/admin/testimonials/{t.id}",
                                   json={"customer_name": "Jane Updated"})
        assert resp.status_code == 200
        assert t.customer_name == "Jane Updated"

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).put("/api/admin/testimonials/9999", json={"customer_name": "x"})
        assert resp.status_code == 404

    def test_U_validation_error(self):
        t = _testimonial()
        _override_admin(self._wire(t))
        resp = TestClient(app).put(f"/api/admin/testimonials/{t.id}",
                                   json={"star_rating": 99})
        assert resp.status_code == 422

    def test_H_status_change(self):
        t = _testimonial()
        _override_admin(self._wire(t))
        resp = TestClient(app).put(f"/api/admin/testimonials/{t.id}",
                                   json={"status": "inactive"})
        assert resp.status_code == 200


class TestAdminDeleteTestimonial:
    def teardown_method(self):
        _clear()

    def _wire(self, t):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = t
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes(self):
        t = _testimonial()
        _override_admin(self._wire(t))
        resp = TestClient(app).delete(f"/api/admin/testimonials/{t.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).delete("/api/admin/testimonials/9999")
        assert resp.status_code == 404


class TestAdminToggleTestimonialStatus:
    def teardown_method(self):
        _clear()

    def _wire(self, t):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = t
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_toggle_active_to_inactive(self):
        from db_models import TestimonialStatus
        t = _testimonial(status=TestimonialStatus.ACTIVE)
        _override_admin(self._wire(t))
        resp = TestClient(app).patch(f"/api/admin/testimonials/{t.id}/status")
        assert resp.status_code == 200

    def test_H_toggle_inactive_to_active(self):
        from db_models import TestimonialStatus
        t = _testimonial(status=TestimonialStatus.INACTIVE)
        _override_admin(self._wire(t))
        resp = TestClient(app).patch(f"/api/admin/testimonials/{t.id}/status")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).patch("/api/admin/testimonials/9999/status")
        assert resp.status_code == 404


class TestPublicTestimonials:
    def teardown_method(self):
        _clear()

    def _wire(self, items):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = items
        db.query.return_value = chain
        return db

    def test_H_returns_weighted_pool_and_stats(self):
        items = [
            _testimonial(id=1, star_rating=5,
                         review_text="Friendly staff, great service, would use again"),
            _testimonial(id=2, star_rating=4,
                         review_text="Excellent service, recommend to all"),
            _testimonial(id=3, star_rating=3,
                         review_text="Adequate parking, did the job"),
            _testimonial(id=4, star_rating=None,
                         review_text="Smooth experience from start to finish"),
            _testimonial(id=5, star_rating=2, is_featured=True,
                         review_text="Had some issues but staff fixed everything quickly"),
        ]
        _override_public(self._wire(items))
        resp = TestClient(app).get("/api/testimonials")
        assert resp.status_code == 200
        body = resp.json()
        # 5★ x5 + 4★ x3 + 3★ x1 + unrated x3 + featured 2★ x1 = 13
        assert body["total"] == 13
        assert body["stats"]["average_rating"] > 0
        # buzz words appear in at least 2 reviews
        # "service" and "staff" appear in 2+ of the example reviews
        buzz_words = body["stats"]["buzz_words"]
        assert isinstance(buzz_words, list)

    def test_E_no_active_testimonials(self):
        _override_public(self._wire([]))
        resp = TestClient(app).get("/api/testimonials")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["stats"]["average_rating"] == 0

    def test_H_buzz_word_merging(self):
        """The endpoint merges 'cheaper' → 'value for money' and several
        'use again' variants → 'use again'."""
        items = [
            _testimonial(id=1, review_text="cheaper than the rest, definitely use again"),
            _testimonial(id=2, review_text="value for money, will use again"),
            _testimonial(id=3, review_text="will be back again, what a service"),
        ]
        _override_public(self._wire(items))
        resp = TestClient(app).get("/api/testimonials")
        assert resp.status_code == 200
        # Just verify no error and structure intact
        assert "buzz_words" in resp.json()["stats"]


# ============================================================================
# Promo modal — admin CRUD
# ============================================================================

def _modal(**kw):
    from db_models import PromoModalStatus, PromoModalType
    base = dict(
        id=1, type=PromoModalType.INFO_MODAL,
        title="Spring promo", message="10% off this month",
        button_text="Subscribe", button_action="subscribe", button_link=None,
        start_date=None, end_date=None,
        background_color="#1e3a5f", text_color="#ffffff",
        button_color="#22c55e", button_text_color="#ffffff",
        status=PromoModalStatus.ACTIVE,
        created_at=datetime(2026, 5, 1),
        view_count=0, click_count=0,
        max_subscribers=None, subscribers_at_activation=None,
        promo_code=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestAdminListPromoModals:
    def teardown_method(self):
        _clear()

    def _wire(self, items):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = items
        db.query.return_value = chain
        return db

    def test_H_list(self):
        _override_admin(self._wire([_modal()]))
        resp = TestClient(app).get("/api/admin/promo-modals")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_H_filter_by_status(self):
        _override_admin(self._wire([_modal()]))
        resp = TestClient(app).get("/api/admin/promo-modals?status=active")
        assert resp.status_code == 200

    def test_H_filter_by_type(self):
        _override_admin(self._wire([_modal()]))
        resp = TestClient(app).get("/api/admin/promo-modals?type=info_modal")
        assert resp.status_code == 200

    def test_E_invalid_status_filter_silently_ignored(self):
        _override_admin(self._wire([_modal()]))
        resp = TestClient(app).get("/api/admin/promo-modals?status=bogus")
        assert resp.status_code == 200

    def test_E_empty(self):
        _override_admin(self._wire([]))
        resp = TestClient(app).get("/api/admin/promo-modals")
        assert resp.json()["total"] == 0


class TestAdminCreatePromoModal:
    def teardown_method(self):
        _clear()

    def _wire(self):
        db = MagicMock()
        added = []
        def _add(obj):
            obj.id = 99
            obj.created_at = datetime(2026, 5, 1)
            obj.view_count = 0
            obj.click_count = 0
            obj.subscribers_at_activation = None
            added.append(obj)
        db.add.side_effect = _add
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_creates_info_modal(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "Test", "message": "Hello",
        })
        assert resp.status_code == 200, resp.text

    def test_H_creates_promo_section(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "type": "promo_section", "title": "Spring",
            "message": "10% off", "promo_code": "SPRING10",
        })
        assert resp.status_code == 200

    def test_H_with_date_range(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "x", "message": "y",
            "start_date": "01/05/2026", "end_date": "31/05/2026",
        })
        assert resp.status_code == 200

    def test_U_invalid_start_date(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "x", "message": "y", "start_date": "bogus",
        })
        assert resp.status_code == 400

    def test_U_invalid_end_date(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "x", "message": "y", "end_date": "bogus",
        })
        assert resp.status_code == 400

    def test_U_invalid_status(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "x", "message": "y", "status": "bogus",
        })
        assert resp.status_code == 400

    def test_U_invalid_type(self):
        _override_admin(self._wire())
        resp = TestClient(app).post("/api/admin/promo-modals", json={
            "title": "x", "message": "y", "type": "bogus",
        })
        assert resp.status_code == 400


class TestAdminDeletePromoModal:
    def teardown_method(self):
        _clear()

    def _wire(self, m):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = m
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes(self):
        m = _modal()
        _override_admin(self._wire(m))
        resp = TestClient(app).delete(f"/api/admin/promo-modals/{m.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).delete("/api/admin/promo-modals/9999")
        assert resp.status_code == 404


class TestAdminToggleModalStatus:
    def teardown_method(self):
        _clear()

    def _wire(self, m, sub_count=0):
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__
            if name == "PromoModal":
                chain.first.return_value = m
            elif name == "MarketingSubscriber":
                chain.count.return_value = sub_count
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def test_H_active_to_inactive(self):
        from db_models import PromoModalStatus
        m = _modal(status=PromoModalStatus.ACTIVE, subscribers_at_activation=10)
        _override_admin(self._wire(m))
        resp = TestClient(app).patch(f"/api/admin/promo-modals/{m.id}/status")
        assert resp.status_code == 200
        assert m.subscribers_at_activation is None

    def test_H_inactive_to_active_captures_subscriber_count(self):
        from db_models import PromoModalStatus
        m = _modal(status=PromoModalStatus.INACTIVE, max_subscribers=50)
        _override_admin(self._wire(m, sub_count=25))
        resp = TestClient(app).patch(f"/api/admin/promo-modals/{m.id}/status")
        assert resp.status_code == 200
        assert m.subscribers_at_activation == 25

    def test_E_no_max_subscribers_does_not_capture_count(self):
        from db_models import PromoModalStatus
        m = _modal(status=PromoModalStatus.INACTIVE, max_subscribers=None)
        _override_admin(self._wire(m))
        resp = TestClient(app).patch(f"/api/admin/promo-modals/{m.id}/status")
        assert resp.status_code == 200
        assert m.subscribers_at_activation is None

    def test_U_not_found(self):
        _override_admin(self._wire(None))
        resp = TestClient(app).patch("/api/admin/promo-modals/9999/status")
        assert resp.status_code == 404


# ============================================================================
# Public promo-modal / promo-section / view / click
# ============================================================================

class TestPublicPromoModal:
    def teardown_method(self):
        _clear()

    def _wire(self, modals):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = modals
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_returns_active_info_modal(self):
        from db_models import PromoModalType
        m = _modal(type=PromoModalType.INFO_MODAL)
        _override_public(self._wire([m]))
        resp = TestClient(app).get("/api/promo-modal")
        assert resp.status_code == 200
        assert resp.json()["promoModal"] is not None

    def test_E_no_active_returns_none(self):
        _override_public(self._wire([]))
        resp = TestClient(app).get("/api/promo-modal")
        assert resp.status_code == 200
        assert resp.json()["promoModal"] is None

    def test_E_future_start_date_skipped(self):
        from db_models import PromoModalType
        m = _modal(type=PromoModalType.INFO_MODAL,
                   start_date=date_type(2099, 1, 1))
        _override_public(self._wire([m]))
        resp = TestClient(app).get("/api/promo-modal")
        assert resp.json()["promoModal"] is None

    def test_E_expired_end_date_auto_deactivates(self):
        from db_models import PromoModalType, PromoModalStatus
        m = _modal(type=PromoModalType.INFO_MODAL,
                   end_date=date_type(2020, 1, 1))
        _override_public(self._wire([m]))
        resp = TestClient(app).get("/api/promo-modal")
        assert resp.json()["promoModal"] is None
        assert m.status == PromoModalStatus.INACTIVE


class TestPublicPromoSection:
    def teardown_method(self):
        _clear()

    def _wire(self, modals):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.all.return_value = modals
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_returns_active_promo_section(self):
        from db_models import PromoModalType
        m = _modal(type=PromoModalType.PROMO_SECTION, promo_code="SPRING10")
        _override_public(self._wire([m]))
        resp = TestClient(app).get("/api/promo-section")
        assert resp.status_code == 200
        assert resp.json()["promoSection"] is not None

    def test_E_no_active(self):
        _override_public(self._wire([]))
        resp = TestClient(app).get("/api/promo-section")
        assert resp.json()["promoSection"] is None

    def test_E_expired_auto_deactivates(self):
        from db_models import PromoModalType, PromoModalStatus
        m = _modal(type=PromoModalType.PROMO_SECTION,
                   end_date=date_type(2020, 1, 1))
        _override_public(self._wire([m]))
        resp = TestClient(app).get("/api/promo-section")
        assert resp.json()["promoSection"] is None
        assert m.status == PromoModalStatus.INACTIVE


class TestTrackView:
    def teardown_method(self):
        _clear()

    def test_H_increments_view_count(self):
        m = _modal(view_count=5)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = m
        db.commit = MagicMock()
        _override_public(db)
        resp = TestClient(app).post("/api/promo-modal/1/view")
        assert resp.status_code == 200
        assert m.view_count == 6

    def test_E_not_found_returns_success_no_op(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        _override_public(db)
        resp = TestClient(app).post("/api/promo-modal/9999/view")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_E_null_view_count_starts_at_1(self):
        m = _modal(view_count=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = m
        db.commit = MagicMock()
        _override_public(db)
        resp = TestClient(app).post("/api/promo-modal/1/view")
        assert m.view_count == 1


class TestTrackClick:
    def teardown_method(self):
        _clear()

    def test_H_increments_click_count(self):
        m = _modal(click_count=2)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = m
        db.commit = MagicMock()
        _override_public(db)
        resp = TestClient(app).post("/api/promo-modal/1/click")
        assert resp.status_code == 200
        assert m.click_count == 3

    def test_E_not_found_returns_success_no_op(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        _override_public(db)
        resp = TestClient(app).post("/api/promo-modal/9999/click")
        assert resp.status_code == 200
