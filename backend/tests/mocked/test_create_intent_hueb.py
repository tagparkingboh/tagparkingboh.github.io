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

