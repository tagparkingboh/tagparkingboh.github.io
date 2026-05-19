"""
HUEB tests for admin booking action endpoints in main.py.

  POST   /api/admin/bookings/{id}/cancel
  DELETE /api/admin/bookings/{id}
  POST   /api/admin/bookings/{id}/resend-email
  POST   /api/admin/bookings/{id}/send-cancellation-email
  POST   /api/admin/bookings/{id}/send-refund-email
  POST   /api/admin/bookings/{id}/send-founder-email
"""
from datetime import date as date_type, datetime, time
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


def _customer(**kw):
    base = dict(
        id=42, email="jo@x.test", first_name="Jo", last_name="K",
        founder_followup_sent=False, founder_followup_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _vehicle(**kw):
    base = dict(
        id=21, registration="AB12CDE", make="Ford", model="Focus", colour="Blue",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _payment(**kw):
    from db_models import PaymentStatus
    base = dict(
        id=51,
        amount_pence=9900,
        refund_amount_pence=0,
        status=PaymentStatus.SUCCEEDED,
        stripe_payment_intent_id="pi_123",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _booking(**kw):
    from db_models import BookingStatus
    base = dict(
        id=99, reference="TAG-1",
        status=BookingStatus.CONFIRMED,
        customer=_customer(),
        customer_first_name="Jo", customer_last_name="K",
        vehicle=_vehicle(),
        payment=_payment(),
        dropoff_date=date_type(2026, 6, 1),
        pickup_date=date_type(2026, 6, 8),
        dropoff_time=time(10, 0),
        pickup_time=time(11, 30),
        flight_arrival_time=time(15, 0),
        flight_departure_time=time(12, 0),
        dropoff_destination="Tenerife",
        dropoff_airline_name="TUI Airways",
        dropoff_flight_number="TOM1234",
        pickup_origin="Tenerife",
        pickup_airline_name="TUI Airways",
        pickup_flight_number="TOM1235",
        departure_id=None, dropoff_slot=None,
        package="longer",
        confirmation_email_sent=False, confirmation_email_sent_at=None,
        cancellation_email_sent=False, cancellation_email_sent_at=None,
        refund_email_sent=False, refund_email_sent_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ============================================================================
# POST /api/admin/bookings/{id}/cancel
# ============================================================================

class TestCancelBookingAdmin:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        chain = MagicMock()
        chain.options.return_value = chain
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_cancels_booking(self, monkeypatch):
        b = _booking(departure_id=None, dropoff_slot=None)
        monkeypatch.setattr("db_service.release_departure_slot",
                            lambda *a, **kw: {"success": True})
        monkeypatch.setattr(main, "cancel_payment_intent",
                            lambda pid: {"success": True})
        # auto_roster import lives at endpoint, not patchable easily
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        from db_models import BookingStatus
        assert b.status == BookingStatus.CANCELLED

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/cancel")
        assert resp.status_code == 404

    def test_U_already_cancelled(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/cancel")
        assert resp.status_code == 400
        assert "already cancelled" in resp.json()["detail"].lower()

    def test_U_refunded_cannot_cancel(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.REFUNDED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/cancel")
        assert resp.status_code == 400
        assert "refunded" in resp.json()["detail"].lower()

    def test_H_with_slot_release(self, monkeypatch):
        b = _booking(departure_id=5, dropoff_slot="150")
        monkeypatch.setattr("db_service.release_departure_slot",
                            lambda *a, **kw: {"success": True})
        monkeypatch.setattr(main, "cancel_payment_intent",
                            lambda pid: {"success": False})
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["slot_released"] is True

    def test_E_succeeded_payment_not_cancelled_by_stripe(self, monkeypatch):
        """Stripe cancel only fires for non-succeeded payments."""
        from db_models import PaymentStatus
        b = _booking(payment=_payment(status=PaymentStatus.SUCCEEDED))
        called = {"n": 0}
        def fake_cancel(pid):
            called["n"] += 1
            return {"success": True}
        monkeypatch.setattr(main, "cancel_payment_intent", fake_cancel)
        monkeypatch.setattr("roster_planner_runner.fire_engine_async",
                            lambda *a, **kw: None)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/cancel")
        assert resp.status_code == 200
        assert called["n"] == 0  # not invoked when status is SUCCEEDED


# ============================================================================
# DELETE /api/admin/bookings/{id}
# ============================================================================

class TestDeleteBooking:
    def teardown_method(self):
        _clear()

    def _wire(self, booking, payment=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "Payment":
                chain.first.return_value = payment
            elif name in ("MarketingSubscriber", "PromoCode"):
                chain.update.return_value = 0
            return chain
        db.query.side_effect = _query
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_deletes_cancelled(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        monkeypatch.setattr("db_service.release_departure_slot",
                            lambda *a, **kw: {"success": False})
        _override(self._wire(b, payment=_payment()))
        resp = TestClient(app).delete(f"/api/admin/bookings/{b.id}")
        assert resp.status_code == 200

    def test_H_deletes_pending(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.PENDING)
        monkeypatch.setattr("db_service.release_departure_slot",
                            lambda *a, **kw: {"success": False})
        _override(self._wire(b))
        resp = TestClient(app).delete(f"/api/admin/bookings/{b.id}")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).delete("/api/admin/bookings/9999")
        assert resp.status_code == 404

    def test_U_confirmed_cannot_be_deleted(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CONFIRMED)
        _override(self._wire(b))
        resp = TestClient(app).delete(f"/api/admin/bookings/{b.id}")
        assert resp.status_code == 400
        assert "pending or cancelled" in resp.json()["detail"].lower()


# ============================================================================
# POST /api/admin/bookings/{id}/resend-email
# ============================================================================

class TestResendEmail:
    def teardown_method(self):
        _clear()

    def _wire(self, booking, subscriber=None):
        db = MagicMock()
        calls = {"n": 0}
        def _query(model):
            calls["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            if name == "Booking":
                chain.first.return_value = booking
            elif name == "MarketingSubscriber":
                chain.first.return_value = subscriber
            return chain
        db.query.side_effect = _query
        db.commit = MagicMock()
        return db

    def test_H_sends_confirmation_email(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/resend-email")
        assert resp.status_code == 200
        assert b.confirmation_email_sent is True

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/resend-email")
        assert resp.status_code == 404

    def test_U_send_fails(self, monkeypatch):
        b = _booking()
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: False)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/resend-email")
        assert resp.status_code == 500

    def test_E_with_promo_code_subscriber(self, monkeypatch):
        b = _booking()
        sub = SimpleNamespace(
            promo_10_used_booking_id=b.id, promo_10_code="TAG10",
            promo_free_used_booking_id=None,
            promo_code_used_booking_id=None,
        )
        monkeypatch.setattr(main, "send_booking_confirmation_email",
                            lambda **kw: True)
        monkeypatch.setattr(main, "calculate_price_in_pence", lambda *a, **kw: 11000)
        _override(self._wire(b, subscriber=sub))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/resend-email")
        assert resp.status_code == 200


# ============================================================================
# POST /api/admin/bookings/{id}/send-cancellation-email
# ============================================================================

class TestSendCancellationEmail:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_sends(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        monkeypatch.setattr("email_service.send_cancellation_email", lambda **kw: True)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-cancellation-email")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/send-cancellation-email")
        assert resp.status_code == 404

    def test_U_not_cancelled(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CONFIRMED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-cancellation-email")
        assert resp.status_code == 400

    def test_U_send_fails(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        monkeypatch.setattr("email_service.send_cancellation_email", lambda **kw: False)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-cancellation-email")
        assert resp.status_code == 500


# ============================================================================
# POST /api/admin/bookings/{id}/send-refund-email
# ============================================================================

class TestSendRefundEmail:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_sends_with_refund_amount(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED,
                     payment=_payment(refund_amount_pence=9900))
        monkeypatch.setattr("email_service.send_refund_email", lambda **kw: True)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-refund-email")
        assert resp.status_code == 200

    def test_E_fallback_to_payment_amount(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED,
                     payment=_payment(refund_amount_pence=0))
        monkeypatch.setattr("email_service.send_refund_email", lambda **kw: True)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-refund-email")
        assert resp.status_code == 200

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/send-refund-email")
        assert resp.status_code == 404

    def test_U_not_cancelled(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CONFIRMED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-refund-email")
        assert resp.status_code == 400

    def test_U_send_fails(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CANCELLED)
        monkeypatch.setattr("email_service.send_refund_email", lambda **kw: False)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-refund-email")
        assert resp.status_code == 500


# ============================================================================
# POST /api/admin/bookings/{id}/send-founder-email
# ============================================================================

class TestSendFounderEmail:
    def teardown_method(self):
        _clear()

    def _wire(self, booking):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        db.commit = MagicMock()
        return db

    def test_H_sends(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.PENDING,
                     customer=_customer(founder_followup_sent=False))
        monkeypatch.setattr("email_service.send_founder_followup_email", lambda **kw: True)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-founder-email")
        assert resp.status_code == 200
        assert b.customer.founder_followup_sent is True

    def test_U_not_found(self):
        _override(self._wire(None))
        resp = TestClient(app).post("/api/admin/bookings/9999/send-founder-email")
        assert resp.status_code == 404

    def test_U_not_pending(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.CONFIRMED)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-founder-email")
        assert resp.status_code == 400

    def test_U_no_customer(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.PENDING, customer=None)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-founder-email")
        assert resp.status_code == 400

    def test_U_already_sent(self):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.PENDING,
                     customer=_customer(
                         founder_followup_sent=True,
                         founder_followup_sent_at=datetime(2026, 5, 1, 12, 0),
                     ))
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-founder-email")
        assert resp.status_code == 400

    def test_U_send_fails(self, monkeypatch):
        from db_models import BookingStatus
        b = _booking(status=BookingStatus.PENDING,
                     customer=_customer(founder_followup_sent=False))
        monkeypatch.setattr("email_service.send_founder_followup_email", lambda **kw: False)
        _override(self._wire(b))
        resp = TestClient(app).post(f"/api/admin/bookings/{b.id}/send-founder-email")
        assert resp.status_code == 500
