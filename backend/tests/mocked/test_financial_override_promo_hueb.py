"""
HUEB tests for the financial-override edit with promo attribution.

Covers:
  - PUT /api/admin/bookings/{id}/financial-override — validation, figures,
    promo attribution (multi-use insert, single-use conflict, clear/replace,
    subscriber-attribution 409)
  - mark_promo_code_used(allow_exhausted=...) retro-attribution branch
  - _unmark_promotions_attribution inverse bookkeeping
  - financial report rows expose bookingSource / canEditFinancials
"""
from datetime import date as date_type, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import main
from main import app, require_admin
from database import get_db
from db_models import (
    Booking, MarketingSubscriber, PromoCode, PromoCodeUsage,
    Promotion, BookingStatus, PaymentStatus,
)


def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _override(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: _admin()


def _model_db(handlers=None):
    """MagicMock session whose query(model) routes to per-model stubs.

    handlers: {Model: {"first": obj_or_None, "all": [rows]}}
    Unlisted models get first=None / all=[].
    """
    handlers = handlers or {}
    db = MagicMock()

    def _query(model, *args):
        spec = handlers.get(model, {})
        chain = MagicMock()
        chain.join.return_value = chain
        chain.filter.return_value = chain
        chain.options.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = spec.get("first")
        chain.all.return_value = spec.get("all", [])
        return chain

    db.query.side_effect = _query
    return db


def _booking_stub(**kw):
    base = dict(
        id=42,
        reference="TAG-2NSWW130",
        status=BookingStatus.CONFIRMED,
        booking_source="manual",
        created_at=datetime(2026, 6, 1, 9, 0),
        dropoff_date=date_type(2026, 6, 11),
        pickup_date=date_type(2026, 6, 18),
        dropoff_time=time(10, 0),
        pickup_time=time(11, 30),
        override_gross_pence=None,
        override_discount_pence=None,
        customer=SimpleNamespace(first_name="Hazel", last_name="Firth"),
        payment=SimpleNamespace(
            amount_pence=8100,
            refund_amount_pence=0,
            status=PaymentStatus.SUCCEEDED,
            paid_at=datetime(2026, 6, 11, 10, 0),
        ),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _promotion_stub(discount_percent=15, codes_used=3):
    return SimpleNamespace(id=9, discount_percent=discount_percent, codes_used=codes_used)


def _multi_use_code(promotion=None, use_count=2, max_uses=0, is_used=False, booking_id=None):
    return SimpleNamespace(
        id=7,
        code="TAG-AAAA-BBBB",
        promotion_id=9,
        promotion=promotion or _promotion_stub(),
        max_uses=max_uses,
        use_count=use_count,
        is_used=is_used,
        booking_id=booking_id,
        used_at=None,
        is_multi_use=True,
        can_be_used=(max_uses == 0 or use_count < max_uses),
    )


def _single_use_code(promotion=None, is_used=False, booking_id=None):
    return SimpleNamespace(
        id=8,
        code="TAG-CCCC-DDDD",
        promotion_id=9,
        promotion=promotion or _promotion_stub(),
        max_uses=None,
        use_count=1 if is_used else 0,
        is_used=is_used,
        booking_id=booking_id,
        used_at=None,
        is_multi_use=False,
        can_be_used=not is_used,
    )


def _added_instances(db, cls):
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], cls)]


from fastapi.testclient import TestClient


class TestFinancialOverrideEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _put(self, db, booking_id=42, gross=9000, discount=900, promo=None):
        _override(db)
        url = f"/api/admin/bookings/{booking_id}/financial-override?gross_pence={gross}&discount_pence={discount}"
        if promo is not None:
            url += f"&promo_code={promo}"
        return TestClient(app).put(url)

    # --- HAPPY ---------------------------------------------------------------

    def test_H_figures_only_sets_overrides_without_touching_promo(self):
        booking = _booking_stub()
        db = _model_db({Booking: {"first": booking}})

        resp = self._put(db)

        assert resp.status_code == 200
        body = resp.json()
        assert body["override_gross_pence"] == 9000
        assert body["override_discount_pence"] == 900
        assert body["promo"] is None
        assert booking.override_gross_pence == 9000
        assert booking.override_discount_pence == 900
        assert not _added_instances(db, PromoCodeUsage)

    def test_H_attributes_multi_use_code_via_usage_row(self):
        booking = _booking_stub()
        code = _multi_use_code()
        db = _model_db({
            Booking: {"first": booking},
            PromoCode: {"first": code, "all": []},
            MarketingSubscriber: {"first": None},
            PromoCodeUsage: {"all": []},
            Promotion: {"first": code.promotion},
        })

        resp = self._put(db, promo="TAG-AAAA-BBBB")

        assert resp.status_code == 200
        assert resp.json()["promo"] == {"cleared": [], "attributed": "TAG-AAAA-BBBB"}
        usages = _added_instances(db, PromoCodeUsage)
        assert len(usages) == 1
        assert usages[0].booking_id == 42
        assert usages[0].promo_code_id == 7
        assert usages[0].discount_percent == 15
        assert usages[0].discount_amount_pence == 900
        assert code.use_count == 3
        assert code.booking_id == 42

    def test_H_lowercase_code_is_matched_case_insensitively(self):
        booking = _booking_stub()
        code = _multi_use_code()
        db = _model_db({
            Booking: {"first": booking},
            PromoCode: {"first": code, "all": []},
            MarketingSubscriber: {"first": None},
            PromoCodeUsage: {"all": []},
            Promotion: {"first": code.promotion},
        })

        resp = self._put(db, promo="tag-aaaa-bbbb")

        assert resp.status_code == 200
        assert resp.json()["promo"]["attributed"] == "TAG-AAAA-BBBB"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_negative_gross_rejected(self):
        resp = self._put(_model_db(), gross=-1, discount=0)
        assert resp.status_code == 400
        assert "negative" in resp.json()["detail"].lower()

    def test_U_discount_above_gross_rejected(self):
        resp = self._put(_model_db(), gross=1000, discount=1001)
        assert resp.status_code == 400
        assert "exceed" in resp.json()["detail"].lower()

    def test_U_booking_not_found(self):
        resp = self._put(_model_db({Booking: {"first": None}}))
        assert resp.status_code == 404

    def test_U_unknown_promo_code(self):
        booking = _booking_stub()
        db = _model_db({
            Booking: {"first": booking},
            PromoCode: {"first": None, "all": []},
            MarketingSubscriber: {"first": None},
            PromoCodeUsage: {"all": []},
        })
        resp = self._put(db, promo="TAG-ZZZZ-ZZZZ")
        assert resp.status_code == 404
        assert "TAG-ZZZZ-ZZZZ" in resp.json()["detail"]

    def test_U_single_use_code_used_by_another_booking_conflicts(self):
        booking = _booking_stub()
        other = _booking_stub(id=99, reference="TAG-OTHER999")
        code = _single_use_code(is_used=True, booking_id=99)
        db = _model_db({
            Booking: {"first": booking},
            PromoCode: {"first": code, "all": []},
            MarketingSubscriber: {"first": None},
            PromoCodeUsage: {"all": []},
        })
        # The conflict branch re-queries Booking for the other reference;
        # the shared Booking handler returns `booking`, so the detail names
        # a reference either way — the status code is the contract here.
        resp = self._put(db, promo="TAG-CCCC-DDDD")
        assert resp.status_code == 409
        assert "single-use" in resp.json()["detail"]

    def test_U_subscriber_attributed_booking_conflicts(self):
        booking = _booking_stub()
        sub = SimpleNamespace(
            promo_10_code="SUB-CODE-10",
            promo_free_code=None,
            founder_promo_code=None,
            promo_code=None,
        )
        db = _model_db({
            Booking: {"first": booking},
            MarketingSubscriber: {"first": sub},
        })
        resp = self._put(db, promo="TAG-AAAA-BBBB")
        assert resp.status_code == 409
        assert "SUB-CODE-10" in resp.json()["detail"]

    # --- EDGE ----------------------------------------------------------------

    def test_E_empty_promo_clears_existing_attribution(self):
        booking = _booking_stub()
        code = _multi_use_code(use_count=3, max_uses=3, is_used=True)
        usage = SimpleNamespace(promo_code=code, booking_id=42)
        db = _model_db({
            Booking: {"first": booking},
            MarketingSubscriber: {"first": None},
            PromoCodeUsage: {"all": [usage]},
            PromoCode: {"first": code, "all": []},
            Promotion: {"first": code.promotion},
        })

        resp = self._put(db, promo="")

        assert resp.status_code == 200
        assert resp.json()["promo"] == {"cleared": ["TAG-AAAA-BBBB"], "attributed": None}
        db.delete.assert_called_once_with(usage)
        assert code.use_count == 2
        assert code.is_used is False  # dropped back under its limit
        assert code.promotion.codes_used == 2

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_discount_equal_to_gross_allowed(self):
        booking = _booking_stub()
        db = _model_db({Booking: {"first": booking}})
        resp = self._put(db, gross=5000, discount=5000)
        assert resp.status_code == 200

    def test_B_zero_values_allowed(self):
        booking = _booking_stub()
        db = _model_db({Booking: {"first": booking}})
        resp = self._put(db, gross=0, discount=0)
        assert resp.status_code == 200


class TestMarkPromoCodeUsedAllowExhausted:
    def _db(self, code):
        return _model_db({
            Booking: {"first": None},
            Promotion: {"first": code.promotion},
        })

    def test_U_exhausted_multi_use_rejected_by_default(self):
        code = _multi_use_code(use_count=3, max_uses=3, is_used=True)
        db = self._db(code)

        assert main.mark_promo_code_used(db, code, 42, 15) is False
        assert code.use_count == 3
        assert not _added_instances(db, PromoCodeUsage)

    def test_H_exhausted_multi_use_recorded_with_allow_exhausted(self):
        code = _multi_use_code(use_count=3, max_uses=3, is_used=True)
        db = self._db(code)

        result = main.mark_promo_code_used(
            db, code, 42, 15, discount_amount_pence=900, allow_exhausted=True
        )

        assert result is True
        assert code.use_count == 4
        assert code.is_used is True
        usages = _added_instances(db, PromoCodeUsage)
        assert len(usages) == 1
        assert usages[0].discount_amount_pence == 900

    def test_B_live_redemption_path_unchanged_when_usable(self):
        code = _multi_use_code(use_count=1, max_uses=3, is_used=False)
        db = self._db(code)

        assert main.mark_promo_code_used(db, code, 42, 15) is True
        assert code.use_count == 2
        assert code.is_used is False


class TestUnmarkPromotionsAttribution:
    def test_H_multi_use_usage_row_reversed(self):
        code = _multi_use_code(use_count=3, max_uses=3, is_used=True, booking_id=42)
        usage = SimpleNamespace(promo_code=code, booking_id=42)
        db = _model_db({
            PromoCodeUsage: {"all": [usage]},
            PromoCode: {"all": []},
            Promotion: {"first": code.promotion},
        })

        cleared = main._unmark_promotions_attribution(db, 42)

        assert cleared == ["TAG-AAAA-BBBB"]
        assert code.use_count == 2
        assert code.is_used is False
        assert code.booking_id is None
        assert code.promotion.codes_used == 2
        db.delete.assert_called_once_with(usage)

    def test_H_single_use_code_reset(self):
        code = _single_use_code(is_used=True, booking_id=42)
        db = _model_db({
            PromoCodeUsage: {"all": []},
            PromoCode: {"all": [code]},
            Promotion: {"first": code.promotion},
        })

        cleared = main._unmark_promotions_attribution(db, 42)

        assert cleared == ["TAG-CCCC-DDDD"]
        assert code.is_used is False
        assert code.booking_id is None
        assert code.used_at is None
        assert code.use_count == 0
        assert code.promotion.codes_used == 2

    def test_E_no_attribution_returns_empty(self):
        db = _model_db({PromoCodeUsage: {"all": []}, PromoCode: {"all": []}})
        assert main._unmark_promotions_attribution(db, 42) == []
        db.delete.assert_not_called()


class TestFinancialReportEditFields:
    def setup_method(self):
        main._financial_cache = {"data": None, "cached_at": None}

    def teardown_method(self):
        app.dependency_overrides.clear()
        main._financial_cache = {"data": None, "cached_at": None}

    def _report(self, booking):
        db = _model_db({
            Booking: {"first": booking, "all": [booking]},
            PromoCode: {"all": []},
            MarketingSubscriber: {"all": []},
            PromoCodeUsage: {"all": []},
        })
        _override(db)
        return TestClient(app).get("/api/admin/reports/financial?refresh=true")

    def test_H_manual_booking_is_editable(self):
        resp = self._report(_booking_stub(booking_source="manual"))
        assert resp.status_code == 200
        rows = [b for m in resp.json()["monthlyData"] for b in m["bookings"]] if "monthlyData" in resp.json() else None
        if rows is None:
            # Fall back to whatever key carries rows — fail loudly with payload
            raise AssertionError(f"unexpected report shape: {list(resp.json().keys())}")
        assert rows, "expected the manual booking in the report"
        assert rows[0]["bookingSource"] == "manual"
        assert rows[0]["canEditFinancials"] is True

    def test_E_online_booking_without_flags_is_not_editable(self):
        resp = self._report(_booking_stub(booking_source="online"))
        assert resp.status_code == 200
        rows = [b for m in resp.json()["monthlyData"] for b in m["bookings"]]
        assert rows
        assert rows[0]["bookingSource"] == "online"
        assert rows[0]["canEditFinancials"] is False
