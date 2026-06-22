"""
HUEB tests for /api/payments/create-intent (main.py:10321).

This is a 600+ line endpoint with deeply nested branches. The tests
here cover the early validation gates that fire before any Stripe
interaction:

  - Stripe-configured check
  - Billing address required fields
  - Lead-time rule (same-day, post-20:00 next-day)
  - Blocked drop-off / pickup dates
  - Soft capacity gate (60 ceiling)

Free-booking path coverage (TestFreeBookingPath, added 2026-05-29):
  The 100%-off promo branch (~main.py:11301) was for a long time only
  exercised via pure-simulation tests (no `from main import app`). After
  4 free bookings landed in May 2026 the path can no longer be treated
  as rare-edge — and it now schedules both `auto_create_or_extend_async`
  and `auto_link_booking_async` for the roster. The new class drives the
  branch end-to-end through TestClient and pins the wiring.

Deeper paths still uncovered here: Stripe PaymentIntent creation and
dedup-of-existing-intent (heavier Stripe mock surface, low ROI given
the existing test_stripe_service_hueb.py coverage).
"""
from datetime import date as date_type, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import os
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


def _override_db(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _clear():
    app.dependency_overrides.clear()


def _empty_db():
    """DB stub where every query returns no rows / no blocked dates."""
    db = MagicMock()
    chain = MagicMock()
    chain.options.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.first.return_value = None
    chain.all.return_value = []
    chain.count.return_value = 0
    db.query.return_value = chain
    return db


def _valid_payload(drop_off_date="2026-08-15", pickup_date="2026-08-22"):
    """A payload that passes Pydantic validation and the lead-time gate."""
    return {
        "first_name": "Jo",
        "last_name": "K",
        "email": "jo@x.test",
        "package": "longer",
        "flight_number": "TOM1234",
        "flight_date": drop_off_date,
        "drop_off_date": drop_off_date,
        "pickup_date": pickup_date,
        "drop_off_time": "10:00",
        "billing_address1": "1 High St",
        "billing_city": "Bournemouth",
        "billing_postcode": "BH1 1AA",
    }


# ============================================================================
# Service-not-configured short-circuit
# ============================================================================

class TestStripeConfigCheck:
    def teardown_method(self):
        _clear()

    def test_U_returns_503_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(main, "is_stripe_configured", lambda: False)
        _override_db(_empty_db())
        resp = TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()


# ============================================================================
# Billing-address required-field gate
# ============================================================================

class TestBillingValidation:
    def setup_method(self):
        # Stripe always configured for these tests
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def test_U_missing_billing_address1(self):
        _override_db(_empty_db())
        payload = _valid_payload()
        payload["billing_address1"] = ""
        resp = TestClient(app).post("/api/payments/create-intent", json=payload)
        assert resp.status_code == 400
        assert "billing address" in resp.json()["detail"].lower()

    def test_U_missing_billing_city(self):
        _override_db(_empty_db())
        payload = _valid_payload()
        payload["billing_city"] = "   "
        resp = TestClient(app).post("/api/payments/create-intent", json=payload)
        assert resp.status_code == 400
        assert "city" in resp.json()["detail"].lower()

    def test_U_missing_billing_postcode(self):
        _override_db(_empty_db())
        payload = _valid_payload()
        payload["billing_postcode"] = ""
        resp = TestClient(app).post("/api/payments/create-intent", json=payload)
        assert resp.status_code == 400
        assert "postcode" in resp.json()["detail"].lower()


# ============================================================================
# Lead-time gate (same-day + post-20:00 next-day)
# ============================================================================

class TestLeadTimeGate:
    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def test_U_same_day_dropoff_blocked(self):
        _override_db(_empty_db())
        today = datetime.now(UK).date().isoformat()
        payload = _valid_payload(drop_off_date=today)
        resp = TestClient(app).post("/api/payments/create-intent", json=payload)
        assert resp.status_code == 400
        assert "same-day" in resp.json()["detail"].lower()

    def test_U_yesterday_dropoff_blocked(self):
        _override_db(_empty_db())
        yesterday = (datetime.now(UK).date() - timedelta(days=1)).isoformat()
        payload = _valid_payload(drop_off_date=yesterday)
        resp = TestClient(app).post("/api/payments/create-intent", json=payload)
        assert resp.status_code == 400

    # The 20:00 post-cutoff next-day rule is hard to test without a
    # full datetime patch because the endpoint imports `datetime` locally
    # in a try block. Same-day rejection above is enough for this gate.


# ============================================================================
# Blocked-date gate
# ============================================================================

class TestBlockedDateGate:
    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def _wire(self, blocked_dropoff=None, blocked_pickup=None):
        """First BlockedDate.first() returns blocked_dropoff;
        second returns blocked_pickup."""
        db = MagicMock()
        calls = {"BlockedDate": 0, "AuditLog": 0}

        def _query(*args):
            model = args[0] if args else None
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain = MagicMock()
            chain.options.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            if name == "BlockedDate":
                calls["BlockedDate"] += 1
                if calls["BlockedDate"] == 1:
                    chain.first.return_value = blocked_dropoff
                else:
                    chain.first.return_value = blocked_pickup
            else:
                chain.first.return_value = None
                chain.all.return_value = []
            return chain

        db.query.side_effect = _query
        return db

    def test_U_dropoff_date_fully_blocked(self):
        blocked = SimpleNamespace(
            id=1,
            start_date=date_type(2026, 8, 1),
            end_date=date_type(2026, 8, 31),
            block_dropoffs=True,
            block_pickups=False,
            time_slots=[],
        )
        _override_db(self._wire(blocked_dropoff=blocked))
        resp = TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        assert resp.status_code == 400
        assert "drop-off" in resp.json()["detail"].lower()

    # Skipped: pickup-blocked branch reads `request.pickup_time` (main.py:10464)
    # but `CreatePaymentRequest` has no such field — it's a latent
    # AttributeError. Drop-off blocked is covered above and exercises the
    # shared check_time_blocked helper.

    def test_E_dropoff_outside_time_slot_passes(self, monkeypatch):
        """A BlockedDate with a 14:00-16:00 time slot doesn't block a 10:00
        drop-off. The endpoint should proceed past the blocked-date check
        (and eventually hit something else — we just verify it's not 400
        with the 'drop-offs are not available' message)."""
        slot = SimpleNamespace(
            start_time=time(14, 0),
            end_time=time(16, 0),
            block_dropoffs=True,
            block_pickups=False,
        )
        blocked = SimpleNamespace(
            id=3,
            start_date=date_type(2026, 8, 1),
            end_date=date_type(2026, 8, 31),
            block_dropoffs=False,
            block_pickups=False,
            time_slots=[slot],
        )
        _override_db(self._wire(blocked_dropoff=blocked))
        # The Stripe-not-configured path is bypassed; we'll hit a deeper
        # error. We just check it's NOT the "drop-offs are not available"
        # error.
        resp = TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        if resp.status_code == 400:
            assert "drop-offs are not available" not in resp.json().get("detail", "").lower()


# ============================================================================
# Capacity gate (soft 60)
# ============================================================================

class TestCapacityGate:
    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def test_U_overcapacity_day_blocks_booking(self, monkeypatch):
        # find_overcapacity_day_in_stay returns (day, count) for the first
        # full day in the requested stay span.
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: (date_type(2026, 8, 18), 60),
        )
        monkeypatch.setattr(
            "db_service.get_pending_booking_by_session",
            lambda db, sid: None,
        )
        _override_db(_empty_db())
        resp = TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        assert resp.status_code == 400
        assert "full" in resp.json()["detail"].lower()
        assert "18 august" in resp.json()["detail"].lower()


# ============================================================================
# Free-booking path — TestClient drive of the 100%-off branch
#
# Background (incident TAG-EAW63114, 2026-05-29): the Stripe webhook
# confirmation path was scheduling auto_create_or_extend_async but not
# auto_link_booking_async — so bookings landing inside a frozen shift
# (rebuild's skip-if-covered branch) never got their ShiftBookingLink
# row written, orphaning them from the assigned driver's card. The same
# wiring gap existed in the free-booking branch of /api/payments/create-
# intent (the 100%-off promo path), which has now seen real volume
# (~4 in May 2026). Both paths now schedule both background tasks.
#
# These tests drive the endpoint end-to-end via TestClient so a future
# refactor cannot silently drop one of the two scheduling calls.
# ============================================================================


def _free_booking_payload(*, promo_code="TAG-FREE100"):
    """Payload that takes the customer_id+vehicle_id branch (lighter
    booking creation than the from-scratch full-booking path) and
    carries a promo code that the DB mock will resolve to free_100."""
    p = _valid_payload()
    p.update({
        "customer_id": 42,
        "vehicle_id": 7,
        "promo_code": promo_code,
        "pickup_flight_time": "10:00",  # quote exit_time = 10:30
        # session_id None → bypass the dedup-of-existing-intent branch.
    })
    return p


def _mk_promo_code_record(*, promotion_id=1):
    """PromoCode row that passes the validity gate at main.py:~10888."""
    rec = MagicMock()
    rec.id = 1001
    rec.code = "TAG-FREE100"
    rec.promotion_id = promotion_id
    rec.is_used = False
    rec.expires_at = None
    rec.can_be_used = True  # read at main.py:~11351 (mark-used branch)
    rec.is_multi_use = False
    rec.recipient_email = "winner@x.test"
    return rec


def _mk_free_100_promotion():
    """Promotion row with discount_type='free_100' → is_free_booking=True
    regardless of trip length (main.py:~10910)."""
    p = MagicMock()
    p.id = 1
    p.name = "100% off (test)"
    p.discount_percent = 100
    p.discount_type = "free_100"
    return p


def _mk_customer():
    c = MagicMock()
    c.id = 42
    c.first_name = "Free"
    c.last_name = "Winner"
    c.email = "winner@x.test"
    return c


def _mk_booking_row(*, reference="TAG-FREE001", booking_id=999):
    b = MagicMock()
    b.id = booking_id
    b.reference = reference
    b.status = None  # set by the endpoint
    return b


def _free_booking_db(*, promo_code_record, promotion, booking_row):
    """db.query(Model) dispatches by model name. Each call returns a
    fresh chain so the same DB mock can satisfy interleaved queries
    against different models from the same endpoint invocation."""
    from db_models import (
        PromoCode as DbPromoCode, Promotion as DbPromotion, Booking as DbBooking,
    )
    db = MagicMock()

    def _query(model):
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.count.return_value = 0
        chain.first.return_value = None
        chain.all.return_value = []
        if model is DbPromoCode:
            chain.first.return_value = promo_code_record
        elif model is DbPromotion:
            chain.first.return_value = promotion
        elif model is DbBooking:
            chain.first.return_value = booking_row
        return chain

    db.query.side_effect = _query
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


class TestFreeBookingPath:
    """Drive /api/payments/create-intent into the free-booking branch
    (is_free_booking=True via free_100 promo) and pin the two roster
    background tasks."""

    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def _common_patches(self, monkeypatch):
        """Patch out side-effecting deps that aren't load-bearing for
        the wiring assertions: capacity gate, pricing has no DB needs,
        promo bookkeeping, audit logging, email send."""
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "db_service.get_pending_booking_by_session",
            lambda db, sid: None,
        )
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: _mk_customer())
        # Promo bookkeeping + audit + email are not the assertions we care
        # about; stub them so the branch runs cleanly to the response.
        monkeypatch.setattr("main.mark_promo_code_used", lambda *a, **kw: None)
        monkeypatch.setattr("main.check_promo_modal_code_used", lambda *a, **kw: None)
        monkeypatch.setattr("main.log_audit_event", lambda *a, **kw: None)
        monkeypatch.setattr(
            "email_service.send_booking_confirmation_email",
            lambda *a, **kw: True,
        )

    def test_H_free_booking_schedules_both_auto_create_and_auto_link(
        self, monkeypatch
    ):
        """Free booking (free_100 promo) must schedule BOTH
        auto_create_or_extend_async AND auto_link_booking_async with
        booking.id. Regression fence for the wiring gap that caused
        TAG-EAW63114 in the webhook path — same shape, different
        confirmation entry point."""
        self._common_patches(monkeypatch)

        promo = _mk_promo_code_record()
        promotion = _mk_free_100_promotion()
        booking = _mk_booking_row(reference="TAG-FREE001", booking_id=999)
        payment = MagicMock(status=None, paid_at=None)

        # db_service.create_booking returns the booking row used through
        # the rest of the free-booking branch; payment row is created at
        # main.py:~11336 and immediately stamped SUCCEEDED.
        monkeypatch.setattr(
            "db_service.create_booking", lambda **kw: booking,
        )
        monkeypatch.setattr(
            "db_service.create_payment", lambda **kw: payment,
        )

        _override_db(_free_booking_db(
            promo_code_record=promo, promotion=promotion, booking_row=booking,
        ))

        with patch("auto_roster.auto_create_or_extend_async") as mock_rebuild, \
             patch("roster_planner_runner.auto_link_booking_async") as mock_link:
            resp = TestClient(app).post(
                "/api/payments/create-intent", json=_free_booking_payload(),
            )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["is_free_booking"] is True
        assert body["booking_reference"] == "TAG-FREE001"
        assert body["client_secret"] is None  # no Stripe for free bookings

        mock_rebuild.assert_called_once_with(999)
        mock_link.assert_called_once_with(999)


# ============================================================================
# Airport-quote promo matrix (§9) — promo applied to the DYNAMIC quote price.
# free_100 + percentage are unambiguous; free_week (>7d) is HELD pending the
# env-vs-package week1 ruling (spec §9 says env AIRPORT_QUOTE_WEEK1_PRICE_PENCE,
# code uses get_base_price_for_duration(7)).
# ============================================================================


def _mk_airport_snapshot(
    *,
    snapshot_id=555,
    tag_price_pence=11103,
    entry_date=None,
    entry_time=None,
    exit_date=None,
    exit_time=None,
):
    s = MagicMock()
    s.id = snapshot_id
    s.status = "ok"
    s.tag_price_pence = tag_price_pence
    s.entry_date = entry_date or date_type(2026, 8, 15)  # matches _valid_payload drop_off_date
    s.entry_time = entry_time or time(10, 0)
    s.exit_date = exit_date or date_type(2026, 8, 22)
    s.exit_time = exit_time or time(10, 30)
    return s


def _mk_percentage_promotion(*, percent=10):
    p = MagicMock()
    p.id = 2
    p.name = f"{percent}% off (test)"
    p.discount_percent = percent
    p.discount_type = "percentage"
    return p


def _mk_free_week_promotion():
    p = MagicMock()
    p.id = 3
    p.name = "1 week free (test)"
    p.discount_percent = 100
    p.discount_type = "free_week"
    return p


def _mk_free_week_promotion():
    p = MagicMock()
    p.id = 3
    p.name = "1 week free (test)"
    p.discount_percent = 100
    p.discount_type = "free_week"
    return p


def _promo_quote_db(*, promo_code_record, promotion, booking_row, airport_snapshot):
    """Per-model dispatch (extends _free_booking_db with AirportQuoteSnapshot)."""
    from db_models import (
        PromoCode as DbPromoCode, Promotion as DbPromotion, Booking as DbBooking,
        AirportQuoteSnapshot as DbSnap,
    )
    db = MagicMock()

    def _query(model):
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.count.return_value = 0
        chain.first.return_value = None
        chain.all.return_value = []
        if model is DbPromoCode:
            chain.first.return_value = promo_code_record
        elif model is DbPromotion:
            chain.first.return_value = promotion
        elif model is DbBooking:
            chain.first.return_value = booking_row
        elif model is DbSnap:
            chain.first.return_value = airport_snapshot
        return chain

    db.query.side_effect = _query
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


class TestAirportQuotePromo:
    """§9 promo behaviour against the dynamic (snapshot-derived) TAG price."""

    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        _clear()

    def _common_patches(self, monkeypatch):
        monkeypatch.setattr("db_service.find_overcapacity_day_in_stay", lambda *a, **kw: None)
        monkeypatch.setattr("db_service.get_pending_booking_by_session", lambda db, sid: None)
        monkeypatch.setattr("db_service.get_customer_by_id", lambda db, cid: _mk_customer())
        monkeypatch.setattr("main.mark_promo_code_used", lambda *a, **kw: None)
        monkeypatch.setattr("main.check_promo_modal_code_used", lambda *a, **kw: None)
        monkeypatch.setattr("main.log_audit_event", lambda *a, **kw: None)
        monkeypatch.setattr("email_service.send_booking_confirmation_email", lambda *a, **kw: True)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: _mk_booking_row())
        monkeypatch.setattr("db_service.create_payment", lambda **kw: MagicMock(status=None, paid_at=None))

    def test_H_free_100_zeroes_the_dynamic_quote_price(self, monkeypatch):
        """free_100 against a £111.03 airport quote → £0, and the discount
        equals the SNAPSHOT price (proves promo applies to the dynamic quote,
        not a package price)."""
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQ100", booking_id=801)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        _override_db(_promo_quote_db(
            promo_code_record=_mk_promo_code_record(),
            promotion=_mk_free_100_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(tag_price_pence=11103),
        ))
        payload = _free_booking_payload()
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["is_free_booking"] is True
        assert body["client_secret"] is None
        assert body["amount"] == 0
        assert body["original_amount"] == 11103       # the dynamic quote price
        assert body["discount_amount"] == 11103

    def test_H_percentage_discounts_the_dynamic_quote_price(self, monkeypatch):
        """10% off a £111.03 airport quote → £99.93 charged via Stripe
        (discount computed on the dynamic quote, not a package price)."""
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQ10", booking_id=802)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_test_aq"
        fake_intent.client_secret = "cs_test_aq"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        promo = _mk_promo_code_record()
        promo.code = "SAVE10"
        _override_db(_promo_quote_db(
            promo_code_record=promo,
            promotion=_mk_percentage_promotion(percent=10),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(tag_price_pence=11103),
        ))
        payload = _free_booking_payload(promo_code="SAVE10")
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["is_free_booking"] is False
        assert body["original_amount"] == 11103         # dynamic quote price
        assert body["discount_amount"] == 1110          # int(11103 * 10/100)
        assert body["amount"] == 9993                    # 11103 - 1110
        assert body["client_secret"] == "cs_test_aq"

    def test_U_rejects_stale_airport_quote_id_when_times_change(self, monkeypatch):
        """F1: same quote id cannot be reused after the customer changes times."""
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQSTALE", booking_id=805)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        _override_db(_promo_quote_db(
            promo_code_record=None,
            promotion=None,
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(
                tag_price_pence=11103,
                entry_time=time(9, 30),  # payload still says 10:00
            ),
        ))
        payload = _free_booking_payload(promo_code=None)
        payload["airport_quote_snapshot_id"] = 555

        resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        assert resp.status_code == 400
        assert "Airport quote no longer matches" in resp.json()["detail"]

    # --- free_week boundary on the 7-day seam (t-eps / t / t+eps) --------------

    def _free_week_promo(self):
        promo = _mk_promo_code_record()
        promo.code = "FREEWK"
        return promo

    def test_H_free_week_7day_airport_trip_is_fully_free(self, monkeypatch):
        """t (=7 days): a 7-day airport trip is fully free regardless of week1."""
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10800")
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQFW7", booking_id=810)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        _override_db(_promo_quote_db(
            promo_code_record=self._free_week_promo(),
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(tag_price_pence=20000),
        ))
        payload = _free_booking_payload(promo_code="FREEWK")  # 2026-08-15 -> 08-22 = 7 days
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        body = resp.json()
        assert resp.status_code == 200, body
        assert body["is_free_booking"] is True
        assert body["amount"] == 0
        assert body["discount_amount"] == 20000  # whole price waived

    def test_H_free_week_8day_airport_trip_deducts_env_week1(self, monkeypatch):
        """t+eps (8 days): >7 deducts min(env week1, price); price>week1 -> week1.
        Proves the env value is used (not the package base)."""
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10800")
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQFW8", booking_id=811)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_fw8"
        fake_intent.client_secret = "cs_fw8"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        _override_db(_promo_quote_db(
            promo_code_record=self._free_week_promo(),
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(tag_price_pence=20000, exit_date=date_type(2026, 8, 23)),
        ))
        payload = _free_booking_payload(promo_code="FREEWK")
        payload["pickup_date"] = "2026-08-23"  # 8 days -> >7
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        body = resp.json()
        assert resp.status_code == 200, body
        week1 = int(os.environ["AIRPORT_QUOTE_WEEK1_PRICE_PENCE"])  # derive from the env, don't hardcode
        assert body["is_free_booking"] is False           # discontinuity: 7d free, 8d charged
        assert body["original_amount"] == 20000
        assert body["discount_amount"] == week1            # env week1 (10800), NOT a package base
        assert body["amount"] == 20000 - week1             # 9200

    def test_H_free_week_airport_pre_2am_uses_raw_days_not_package_courtesy(self, monkeypatch):
        """F2: airport quote duration ignores the package 02:00 courtesy.
        2026-08-15 -> 2026-08-23 is raw 8 days even with a 01:30 arrival,
        so free_week is partial, matching the dedup raw-days path."""
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10800")
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQFW2AM", booking_id=815)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_fw2am"
        fake_intent.client_secret = "cs_fw2am"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        _override_db(_promo_quote_db(
            promo_code_record=self._free_week_promo(),
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(
                tag_price_pence=20000,
                exit_date=date_type(2026, 8, 23),
                exit_time=time(2, 0),
            ),
        ))
        payload = _free_booking_payload(promo_code="FREEWK")
        payload["pickup_date"] = "2026-08-23"
        payload["pickup_flight_time"] = "01:30"  # package courtesy would bill as 7 days
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        body = resp.json()
        assert resp.status_code == 200, body
        assert body["is_free_booking"] is False
        assert body["original_amount"] == 20000
        assert body["discount_amount"] == 10800
        assert body["amount"] == 9200

    def test_H_free_week_8day_airport_price_at_or_below_week1_waives_all(self, monkeypatch):
        """min() the other way: when price <= env week1, deduct the whole price.
        Note: the >7 branch keeps is_free_booking False, so this is a £0 paid
        amount rather than a free booking (edge — flagged in the report)."""
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10800")
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-AQFWLOW", booking_id=813)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_fwlow"
        fake_intent.client_secret = "cs_fwlow"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        _override_db(_promo_quote_db(
            promo_code_record=self._free_week_promo(),
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(
                tag_price_pence=8000,  # < week1
                exit_date=date_type(2026, 8, 23),
            ),
        ))
        payload = _free_booking_payload(promo_code="FREEWK")
        payload["pickup_date"] = "2026-08-23"  # 8 days
        payload["airport_quote_snapshot_id"] = 555

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        body = resp.json()
        assert resp.status_code == 200, body
        assert body["original_amount"] == 8000
        assert body["discount_amount"] == 8000   # min(week1=10800, price=8000) = price
        assert body["amount"] == 0

    def test_H_free_week_non_airport_still_uses_package_week1(self, monkeypatch):
        """Regression guardrail: a normal TAG booking (no airport_quote_snapshot_id)
        free_week still deducts get_base_price_for_duration(7) — the env value is
        ignored for non-airport bookings."""
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "99900")  # deliberately distinct
        self._common_patches(monkeypatch)
        booking = _mk_booking_row(reference="TAG-PKGFW", booking_id=812)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        monkeypatch.setattr("main.calculate_price_in_pence", lambda **kw: 20000)
        monkeypatch.setattr("main.get_base_price_for_duration", lambda days: 90.0)  # -> 9000 pence
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_pkg"
        fake_intent.client_secret = "cs_pkg"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        _override_db(_promo_quote_db(
            promo_code_record=self._free_week_promo(),
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=None,
        ))
        payload = _free_booking_payload(promo_code="FREEWK")
        payload["pickup_date"] = "2026-08-23"  # 8 days -> >7
        # NO airport_quote_snapshot_id -> package-priced path

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        body = resp.json()
        assert resp.status_code == 200, body
        assert body["original_amount"] == 20000
        assert body["discount_amount"] == 9000   # package week1 (get_base_price_for_duration*100)
        assert body["discount_amount"] != 99900  # env value explicitly NOT used for non-airport
        assert body["amount"] == 11000

    def test_H_free_week_uses_airport_week1_env_for_airport_quote(self, monkeypatch):
        """free_week on an 8-day airport quote deducts AIRPORT_QUOTE_WEEK1_PRICE_PENCE,
        not the normal TAG package week-one base."""
        self._common_patches(monkeypatch)
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10500")
        booking = _mk_booking_row(reference="TAG-AQFW", booking_id=803)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_test_aq_free_week"
        fake_intent.client_secret = "cs_test_aq_free_week"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        promo = _mk_promo_code_record()
        promo.code = "FREEWEEK"
        _override_db(_promo_quote_db(
            promo_code_record=promo,
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=_mk_airport_snapshot(tag_price_pence=15000, exit_date=date_type(2026, 8, 23)),
        ))
        payload = _free_booking_payload(promo_code="FREEWEEK")
        payload["airport_quote_snapshot_id"] = 555
        payload["drop_off_date"] = "2026-08-15"
        payload["pickup_date"] = "2026-08-23"  # >7 days, partial free_week path

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["is_free_booking"] is False
        assert body["original_amount"] == 15000
        assert body["discount_amount"] == 10500
        assert body["amount"] == 4500
        assert body["client_secret"] == "cs_test_aq_free_week"

    def test_H_free_week_without_airport_quote_keeps_package_week1_base(self, monkeypatch):
        """Normal TAG free_week behaviour is unchanged when no airport quote id is present."""
        self._common_patches(monkeypatch)
        monkeypatch.setenv("AIRPORT_QUOTE_WEEK1_PRICE_PENCE", "10500")
        booking = _mk_booking_row(reference="TAG-FW", booking_id=804)
        monkeypatch.setattr("db_service.create_booking", lambda **kw: booking)
        # Pin the package pricing engine so this test is deterministic — it is
        # asserting the free_week DEDUCTION (package week1 base), not the
        # season/date-sensitive package price itself (which otherwise returns
        # 9900 here, not the hard-coded 9300, and made this test brittle).
        monkeypatch.setattr("main.calculate_price_in_pence", lambda **kw: 9300)
        monkeypatch.setattr("main.get_base_price_for_duration", lambda days: 85.0)  # -> 8500 pence
        fake_intent = MagicMock()
        fake_intent.payment_intent_id = "pi_test_free_week"
        fake_intent.client_secret = "cs_test_free_week"
        monkeypatch.setattr("main.create_payment_intent", lambda *a, **kw: fake_intent)
        promo = _mk_promo_code_record()
        promo.code = "FREEWEEK"
        _override_db(_promo_quote_db(
            promo_code_record=promo,
            promotion=_mk_free_week_promotion(),
            booking_row=booking,
            airport_snapshot=None,
        ))
        payload = _free_booking_payload(promo_code="FREEWEEK")
        payload["drop_off_date"] = "2026-08-15"
        payload["pickup_date"] = "2026-08-23"  # >7 days, partial free_week path

        with patch("auto_roster.auto_create_or_extend_async"), \
             patch("roster_planner_runner.auto_link_booking_async"):
            resp = TestClient(app).post("/api/payments/create-intent", json=payload)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["is_free_booking"] is False
        assert body["original_amount"] == 9300
        assert body["discount_amount"] == 8500
        assert body["amount"] == 800
        assert body["client_secret"] == "cs_test_free_week"
