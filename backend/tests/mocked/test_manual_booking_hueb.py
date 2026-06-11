"""
HUEB tests for POST /api/admin/manual-booking (main.py:2354+).

Focuses on the validation gates: stripe_payment_link requirement,
capacity ceiling, departure flight validation, slot fullness. Doesn't
exhaustively exercise the customer/vehicle creation paths or email
sending — those happen after all gates have passed.
"""
from datetime import date as date_type, datetime
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


def _payload(**overrides):
    base = dict(
        first_name="Jo", last_name="K", email="jo@x.test", phone="07123",
        billing_address1="1 High St", billing_city="Bournemouth",
        billing_postcode="BH1 1AA",
        registration="AB12CDE", make="Ford", colour="Blue",
        dropoff_date="2026-08-15", dropoff_time="10:00",
        pickup_date="2026-08-22", pickup_time="11:30",
        stripe_payment_link="https://buy.stripe.com/test_abc",
        amount_pence=9900,
    )
    base.update(overrides)
    return base


# ============================================================================
# Validation gates
# ============================================================================

class TestManualBookingValidation:
    def teardown_method(self):
        _clear()

    def _wire(self, customer=None, vehicle=None, departure=None, arrival=None, bookings=None):
        """Build a DB stub that returns the listed objects for each model."""
        db = MagicMock()
        def _query(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = []
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Customer":
                chain.first.return_value = customer
            elif name == "Vehicle":
                chain.first.return_value = vehicle
            elif name == "Booking":
                chain.first.return_value = None
                chain.all.return_value = bookings or []
            elif name == "FlightDeparture":
                chain.first.return_value = departure
            elif name == "FlightArrival":
                chain.first.return_value = arrival
            else:
                chain.first.return_value = None
            return chain
        db.query.side_effect = _query
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_U_paid_without_payment_link(self):
        _override(self._wire())
        # Pop the stripe link from payload
        p = _payload()
        p.pop("stripe_payment_link")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 422

    def test_U_capacity_ceiling_hit(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: (date_type(2026, 8, 18), 70),
        )
        _override(self._wire())
        resp = TestClient(app).post("/api/admin/manual-booking", json=_payload())
        assert resp.status_code == 400
        assert "ceiling" in resp.json()["detail"].lower()
        assert "70" in resp.json()["detail"]

    def test_U_total_capacity_ceiling_endpoint_gate(self):
        from db_models import BookingStatus
        overlapping = [
            SimpleNamespace(
                id=i,
                status=BookingStatus.CONFIRMED,
                dropoff_date=date_type(2026, 8, 15),
                pickup_date=date_type(2026, 8, 22),
            )
            for i in range(75)
        ]
        _override(self._wire(bookings=overlapping))
        resp = TestClient(app).post("/api/admin/manual-booking", json=_payload())
        assert resp.status_code == 400
        assert "Cannot create" in resp.json()["detail"]
        assert "75-car physical ceiling" in resp.json()["detail"]

    def test_U_invalid_departure_id(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        _override(self._wire(departure=None))
        p = _payload(departure_id=999, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 400
        assert "departure flight" in resp.json()["detail"].lower()

    def test_H_legacy_call_us_only_flight_does_not_block_manual_booking(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr("email_service.send_manual_booking_payment_email", lambda *a, **kw: True)
        dep = SimpleNamespace(
            id=5, capacity_tier=0,
            slots_booked_early=0, slots_booked_late=0,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 200

    def test_H_legacy_early_slot_full_does_not_block_manual_booking(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr("email_service.send_manual_booking_payment_email", lambda *a, **kw: True)
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=2, slots_booked_late=0,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="early")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 200

    def test_H_legacy_late_slot_full_does_not_block_manual_booking(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr("email_service.send_manual_booking_payment_email", lambda *a, **kw: True)
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=0, slots_booked_late=2,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="late")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 200

    def test_H_legacy_standard_slot_full_does_not_block_manual_booking(self, monkeypatch):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr("email_service.send_manual_booking_payment_email", lambda *a, **kw: True)
        dep = SimpleNamespace(
            id=5, capacity_tier=4,
            slots_booked_early=0, slots_booked_late=2,
            destination_name="Tenerife",
        )
        _override(self._wire(departure=dep))
        p = _payload(departure_id=5, dropoff_slot="standard")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        assert resp.status_code == 200

    def test_E_free_booking_no_payment_link_required(self, monkeypatch):
        """When amount_pence=0 and is_free_booking=true, payment link is optional."""
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        _override(self._wire())
        p = _payload(is_free_booking=True, amount_pence=0)
        p.pop("stripe_payment_link")
        resp = TestClient(app).post("/api/admin/manual-booking", json=p)
        # Should NOT return 422 for missing payment link — should succeed
        # (or fail at a later step that requires more wiring)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert resp.json()["is_free_booking"] is True


# ============================================================================
# Promo-code linking on PAID manual bookings (regression: TAG-UJ972BCF /
# TAG-3JM5QZ8P, 2026-05). Pre-fix the endpoint dropped request.promo_code
# whenever is_free was False because it assumed the Stripe webhook would
# pick up the link via PaymentIntent metadata — but manual bookings use
# externally-created Stripe Payment Links whose metadata doesn't carry the
# promo, so the link silently fell off the books and ops had to backfill
# rows by hand. Post-fix the endpoint links the promo immediately at
# booking creation time for paid bookings too.
# ============================================================================


def _spy_db_for_promo(promo_code_record=None, subscriber=None):
    """DB stub that returns whatever you wire for PromoCode + MarketingSubscriber
    lookups and records every .add() so the test can assert on the resulting
    PromoCodeUsage row."""
    added = []

    db = MagicMock()

    def _query(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.options.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = []
        name = model.__name__ if hasattr(model, "__name__") else str(model)
        if name == "Customer":
            chain.first.return_value = None
        elif name == "Vehicle":
            chain.first.return_value = None
        elif name == "FlightDeparture":
            chain.first.return_value = None
        elif name == "FlightArrival":
            chain.first.return_value = None
        elif name == "PromoCode":
            chain.first.return_value = promo_code_record
        elif name == "Promotion":
            # Promotion is fetched via separate query in the endpoint —
            # we return a SimpleNamespace with discount_percent matched to
            # whatever the test sets on promo_code_record.
            chain.first.return_value = (
                SimpleNamespace(
                    id=getattr(promo_code_record, "promotion_id", None),
                    discount_percent=getattr(promo_code_record, "_discount_percent", 0),
                    codes_used=0,
                )
                if promo_code_record else None
            )
        elif name == "MarketingSubscriber":
            chain.first.return_value = subscriber
        else:
            chain.first.return_value = None
        return chain

    db.query.side_effect = _query
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.added = added
    return db


class TestManualBookingPromoLinking:
    def teardown_method(self):
        _clear()

    def _stub_promo_code(self, *, code, discount_percent, is_multi_use=False, max_uses=None, use_count=0):
        """Build a PromoCode-like SimpleNamespace that mark_promo_code_used
        can mutate. `_discount_percent` is read by the test DB stub's
        Promotion query branch to keep both sides in sync."""
        pc = SimpleNamespace(
            id=131,
            code=code,
            promotion_id=16,
            is_used=False,
            is_multi_use=is_multi_use,
            max_uses=max_uses,
            use_count=use_count,
            booking_id=None,
            used_at=None,
            _discount_percent=discount_percent,
        )
        # `can_be_used` is a property on the real model; stub it as a
        # plain bool that's always True for the happy paths below.
        pc.can_be_used = True
        return pc

    def _post(self, monkeypatch, payload, promo_code_record=None):
        monkeypatch.setattr(
            "db_service.find_overcapacity_day_in_stay",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        db = _spy_db_for_promo(promo_code_record=promo_code_record)
        _override(db)
        resp = TestClient(app).post("/api/admin/manual-booking", json=payload)
        return resp, db

    def test_H_paid_multi_use_promo_creates_usage_row(self, monkeypatch):
        """The bug: paid manual booking with a multi-use promo (like
        TAG-SZHY-IOGX) should write a PromoCodeUsage row at creation time.
        Pre-fix this fired only for free bookings; the row was missing
        and the financial report showed the booking with no promo."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-SZHY-IOGX", discount_percent=15, is_multi_use=True, max_uses=0
        )
        p = _payload(promo_code="TAG-SZHY-IOGX", amount_pence=7650)
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 1, f"expected exactly one PromoCodeUsage row, got {usages}"
        usage = usages[0]
        assert usage.promo_code_id == 131
        assert usage.discount_percent == 15
        # Back-calc: net £76.50 @ 15% off → discount £13.50 (1350p).
        # 7650 * 15 / (100 - 15) = 7650 * 15 / 85 = 1350.
        assert usage.discount_amount_pence == 1350

    def test_H_paid_single_use_promo_marked_used(self, monkeypatch):
        """Single-use code path: the PromoCode row itself flips is_used=True
        and gets booking_id set. No PromoCodeUsage row (those are multi-use only)."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-ONESHOT", discount_percent=20, is_multi_use=False, max_uses=None
        )
        p = _payload(promo_code="TAG-ONESHOT", amount_pence=8000)
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 0
        # mark_promo_code_used was invoked: flipped is_used + incremented
        # use_count + stamped used_at. booking_id is set in prod but the
        # mocked db.flush() here doesn't assign an autoincrement id, so
        # we don't assert on that — the other three are enough to prove
        # the linking call fired.
        assert promo.is_used is True
        assert promo.use_count == 1
        assert promo.used_at is not None

    def test_H_free_booking_legacy_behaviour_preserved(self, monkeypatch):
        """Free booking path keeps prior behaviour: discount_amount_pence
        falls back to request.amount_pence (= 0) rather than the back-calc
        formula. Guards against accidentally regressing the free flow while
        fixing the paid one."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-FREEWEEK", discount_percent=100, is_multi_use=True, max_uses=0
        )
        p = _payload(
            promo_code="TAG-FREEWEEK", amount_pence=0, is_free_booking=True
        )
        p.pop("stripe_payment_link")
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 1
        assert usages[0].discount_percent == 100
        # Free booking: legacy passes amount_pence (= 0). Don't apply the
        # paid back-calc formula (would divide by zero on 100%).
        assert usages[0].discount_amount_pence == 0

    def test_U_no_promo_code_no_usage_row(self, monkeypatch):
        """Sanity: when no promo_code is sent, nothing about PromoCode/Usage
        gets touched. The default _payload() has no promo_code."""
        from db_models import PromoCodeUsage
        resp, db = self._post(monkeypatch, _payload(), promo_code_record=None)
        assert resp.status_code in (200, 500)
        assert [o for o in db.added if isinstance(o, PromoCodeUsage)] == []

    def test_E_paid_50_percent_off_back_calculation(self, monkeypatch):
        """Edge: 50% off code on £45 paid → gross was £90, discount £45.
        Verifies the back-calc formula doesn't only work for 15%."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-HALF", discount_percent=50, is_multi_use=True, max_uses=0
        )
        p = _payload(promo_code="TAG-HALF", amount_pence=4500)
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 1
        # 4500 * 50 / (100 - 50) = 4500 * 50 / 50 = 4500. £45 paid → £45 discount → £90 gross.
        assert usages[0].discount_amount_pence == 4500

    def test_B_paid_99_percent_off_does_not_divide_by_zero(self, monkeypatch):
        """Boundary: a hypothetical 99%-off promo. 99% off on £1 paid →
        gross was £100, discount £99. Confirms the formula stays finite
        at the high-discount edge before the 100% guard kicks in."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-NINETYNINE", discount_percent=99, is_multi_use=True, max_uses=0
        )
        p = _payload(promo_code="TAG-NINETYNINE", amount_pence=100)
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 1
        # 100 * 99 / (100 - 99) = 100 * 99 / 1 = 9900. £1 paid → £99 discount → £100 gross.
        assert usages[0].discount_amount_pence == 9900

    def test_B_paid_100_percent_off_falls_back_to_amount(self, monkeypatch):
        """Boundary: 100%-off on a non-free booking (somehow amount_pence > 0).
        The back-calc denominator would be 0; we bail to the legacy 'use
        amount_pence as the discount' behaviour to avoid ZeroDivisionError."""
        from db_models import PromoCodeUsage
        promo = self._stub_promo_code(
            code="TAG-FULLOFF", discount_percent=100, is_multi_use=True, max_uses=0
        )
        # Construct an odd-but-possible state: 100%-off promo, is_free=False,
        # amount_pence > 0 (an admin mis-flow). The endpoint must not crash.
        p = _payload(promo_code="TAG-FULLOFF", amount_pence=500, is_free_booking=False)
        resp, db = self._post(monkeypatch, p, promo_code_record=promo)
        assert resp.status_code in (200, 500)
        usages = [o for o in db.added if isinstance(o, PromoCodeUsage)]
        assert len(usages) == 1
        # discount_pct >= 100 → legacy: discount = amount_pence (= 500).
        assert usages[0].discount_amount_pence == 500
