"""Focused coverage for defensive branches in ``db_service.py``."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import db_service
from db_models import BookingStatus, PaymentStatus


class QueryStub:
    def __init__(self, rows=None, first=None):
        self.rows = list(rows or [])
        self._first = first

    def filter(self, *_, **__):
        return self

    def join(self, *_, **__):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        if self._first is not None:
            return self._first
        return self.rows[0] if self.rows else None


def test_H_duplicate_customer_normalizes_names_postcodes_and_excludes_email():
    duplicate = SimpleNamespace(
        first_name="  jo ",
        last_name="coverage",
        billing_postcode="bh1 1aa",
        email="old@tag.test",
    )
    other = SimpleNamespace(
        first_name="Jane",
        last_name="Other",
        billing_postcode="ZZ1 1ZZ",
        email="other@tag.test",
    )
    db = MagicMock()
    db.query.return_value = QueryStub(rows=[other, duplicate])

    found = db_service.find_potential_duplicate_customer(
        db,
        first_name="JO",
        last_name="Coverage",
        postcode="BH11AA",
        exclude_email="new@tag.test",
    )

    assert found is duplicate


def test_H_duplicate_customer_handles_missing_inputs_and_no_match():
    assert db_service.find_potential_duplicate_customer(MagicMock(), "", "Guest", "BH1 1AA") is None
    assert db_service.normalize_name(None) == ""
    assert db_service.normalize_postcode(None) == ""

    db = MagicMock()
    db.query.return_value = QueryStub(rows=[
        SimpleNamespace(first_name="No", last_name="Match", billing_postcode="BH1 1AA"),
    ])

    assert db_service.find_potential_duplicate_customer(
        db,
        first_name="Jo",
        last_name="Coverage",
        postcode="BH1 1AA",
    ) is None


def test_H_staging_e2e_capacity_exclusion_skips_mock_queries(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", " staging ")
    query = MagicMock()

    assert db_service.should_exclude_staging_e2e_capacity_bookings() is True
    assert db_service.exclude_staging_e2e_capacity_bookings(query) is query


def test_H_book_departure_slot_unhappy_branches(monkeypatch):
    monkeypatch.setattr(db_service, "record_departure_history", MagicMock())
    db = MagicMock()

    db.query.return_value = QueryStub()
    assert db_service.book_departure_slot(db, 1, "early") == {
        "success": False,
        "message": "Flight not found",
    }

    flight = SimpleNamespace(capacity_tier=0, max_slots_per_time=2, slots_booked_early=0, slots_booked_late=0)
    db.query.return_value = QueryStub(first=flight)
    assert db_service.book_departure_slot(db, 1, "early")["call_us"] is True

    flight.capacity_tier = 4
    flight.slots_booked_early = 2
    result = db_service.book_departure_slot(db, 1, "early")
    assert result == {"success": False, "message": "No early slots available", "slots_remaining": 0}

    flight.slots_booked_early = 0
    flight.slots_booked_late = 2
    result = db_service.book_departure_slot(db, 1, "late")
    assert result == {"success": False, "message": "No late slots available", "slots_remaining": 0}

    assert db_service.book_departure_slot(db, 1, "standard") == {
        "success": False,
        "message": "Invalid slot type. Use 'early' or 'late'",
    }


def test_H_release_departure_slot_unhappy_branches(monkeypatch):
    monkeypatch.setattr(db_service, "record_departure_history", MagicMock())
    db = MagicMock()

    db.query.return_value = QueryStub()
    assert db_service.release_departure_slot(db, 1, "early") == {
        "success": False,
        "message": "Flight not found",
    }

    flight = SimpleNamespace(slots_booked_early=0, slots_booked_late=0)
    db.query.return_value = QueryStub(first=flight)
    assert db_service.release_departure_slot(db, 1, "early") == {
        "success": False,
        "message": "No early slots to release",
    }
    assert db_service.release_departure_slot(db, 1, "late") == {
        "success": False,
        "message": "No late slots to release",
    }
    assert db_service.release_departure_slot(db, 1, "standard") == {
        "success": False,
        "message": "Invalid slot type. Use 'early' or 'late'",
    }


def test_H_record_refund_full_refund_survives_referral_disqualification_error(monkeypatch):
    payment = SimpleNamespace(
        booking_id=7,
        amount_pence=10000,
        refund_id=None,
        refund_amount_pence=None,
        refund_reason=None,
        refunded_at=None,
        status=PaymentStatus.SUCCEEDED,
    )
    booking = SimpleNamespace(id=7, status=BookingStatus.CONFIRMED)
    db = MagicMock()
    monkeypatch.setattr(db_service, "get_payment_by_intent_id", lambda *_: payment)
    monkeypatch.setattr(db_service, "get_booking_by_id", lambda *_: booking)
    monkeypatch.setattr(
        "referral_service.disqualify_referral_for_booking",
        MagicMock(side_effect=RuntimeError("referral down")),
    )

    result = db_service.record_refund(db, "pi_123", "re_123", 10000, "requested")

    assert result is payment
    assert payment.status == PaymentStatus.REFUNDED
    assert booking.status == BookingStatus.REFUNDED
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(payment)
