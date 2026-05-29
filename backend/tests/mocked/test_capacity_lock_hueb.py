"""
HUEB tests for the capacity-race fix (PR 3 of the 2026-05-29 security
review): db_service.find_overcapacity_day_in_stay_locked + webhook
re-check on payment_intent.succeeded.

Two suites:

1. TestFindOvercapacityDayInStayLocked — helper-level (H/U/E/B)
   Direct calls against a mocked SQLAlchemy session. Confirms the
   helper acquires per-date pg_advisory_xact_lock SQL in ascending
   order, then runs the existing find_overcapacity_day_in_stay check
   under the locks.

2. TestWebhookCapacityRace — webhook integration (H/U/E/B)
   TestClient(app) against /api/webhooks/stripe. Confirms the
   re-check only fires on PENDING bookings, returns the
   capacity_race_detected payload on over-cap (leaving booking
   PENDING for ops refund), and is skipped for idempotent replays
   (already CONFIRMED) and manual-booking-style misses (booking
   reference not found).

Per project memory: only TestClient(app)+import-from-main tests
increase coverage. Helper-level tests are HUEB completeness but
don't pad coverage on their own.
"""
import sys
from pathlib import Path
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import db_service
import main
from main import app
from database import get_db
from db_models import BookingStatus


# ============================================================================
# Helper-level tests: find_overcapacity_day_in_stay_locked
# ============================================================================


def _mock_db_for_overcapacity_check(existing_bookings):
    """Wire a MagicMock session so db.query(Booking).filter(...).all() returns
    the supplied list. db.execute is captured for lock-call assertions.
    """
    db = MagicMock()
    db.execute = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.all.return_value = list(existing_bookings)
    db.query.return_value = chain
    return db


def _b(dropoff, pickup):
    """Booking-shaped namespace for the bare-helper count loop."""
    return SimpleNamespace(dropoff_date=dropoff, pickup_date=pickup)


class TestFindOvercapacityDayInStayLocked:
    """H/U/E/B for the locked capacity check."""

    def test_H_under_cap_returns_none_and_locks_acquired(self):
        # H: 5 confirmed against cap=10 on a single day → None.
        d = date(2026, 6, 1)
        existing = [_b(d, d) for _ in range(5)]
        db = _mock_db_for_overcapacity_check(existing)

        result = db_service.find_overcapacity_day_in_stay_locked(
            db, dropoff_date=d, pickup_date=d, cap=10,
        )

        assert result is None
        # One date in stay → exactly one lock acquired.
        assert db.execute.call_count == 1
        sql_arg = db.execute.call_args_list[0].args[0]
        params_arg = db.execute.call_args_list[0].args[1]
        assert "pg_advisory_xact_lock" in str(sql_arg)
        assert "hashtext" in str(sql_arg)
        assert params_arg == {"k": "booking_capacity:2026-06-01"}

    def test_U_at_cap_returns_offending_tuple(self):
        # U: cap=10, exactly 10 confirmed on the day → check trips on day 1.
        d = date(2026, 6, 1)
        existing = [_b(d, d) for _ in range(10)]
        db = _mock_db_for_overcapacity_check(existing)

        result = db_service.find_overcapacity_day_in_stay_locked(
            db, dropoff_date=d, pickup_date=d, cap=10,
        )

        assert result == (d, 10)
        assert db.execute.call_count == 1

    def test_E_multi_day_middle_day_full(self):
        # E: 3-day stay, only the middle day is at cap → helper returns
        # (middle_day, count) and locks are acquired for all three days
        # IN ASCENDING ORDER (deadlock-avoidance invariant).
        d1, d2, d3 = date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)
        # 5 bookings span only the middle day; cap=5 → middle trips.
        existing = [_b(d2, d2) for _ in range(5)]
        db = _mock_db_for_overcapacity_check(existing)

        result = db_service.find_overcapacity_day_in_stay_locked(
            db, dropoff_date=d1, pickup_date=d3, cap=5,
        )

        assert result == (d2, 5)
        # 3 dates in stay → 3 locks, acquired ascending.
        assert db.execute.call_count == 3
        keys_in_order = [
            c.args[1]["k"] for c in db.execute.call_args_list
        ]
        assert keys_in_order == [
            "booking_capacity:2026-06-01",
            "booking_capacity:2026-06-02",
            "booking_capacity:2026-06-03",
        ]

    def test_B_single_day_stay_acquires_one_lock(self):
        # B: dropoff_date == pickup_date (zero-night booking edge) → one
        # date in range, one lock acquired, count loop runs once.
        d = date(2026, 6, 15)
        db = _mock_db_for_overcapacity_check([])

        result = db_service.find_overcapacity_day_in_stay_locked(
            db, dropoff_date=d, pickup_date=d, cap=64,
        )

        assert result is None
        assert db.execute.call_count == 1
        assert db.execute.call_args_list[0].args[1] == {
            "k": "booking_capacity:2026-06-15",
        }


class TestLockOrderingInvariant:
    """The helper iterates from dropoff_date to pickup_date in ascending
    order — the deadlock-avoidance invariant the user called out. These
    tests pin that invariant so a future refactor can't silently reverse
    the iteration.
    """

    def test_H_ascending_keys_only(self):
        # Stay spans Jun 1..Jun 5 → 5 locks in ascending date order, never
        # reversed regardless of caller intent.
        d1 = date(2026, 6, 1)
        d5 = date(2026, 6, 5)
        db = _mock_db_for_overcapacity_check([])

        db_service.find_overcapacity_day_in_stay_locked(
            db, dropoff_date=d1, pickup_date=d5, cap=10,
        )

        keys = [c.args[1]["k"] for c in db.execute.call_args_list]
        assert keys == sorted(keys), (
            "Lock keys must be acquired in ascending date order to avoid "
            "cross-deadlock with another request acquiring an overlapping set"
        )

    def test_B_dropoff_after_pickup_acquires_no_locks(self):
        # B: nonsensical input (dropoff > pickup) — while-loop is a no-op,
        # matches the bare find_overcapacity_day_in_stay() behaviour, no
        # lock-leak risk because nothing was acquired.
        db = _mock_db_for_overcapacity_check([])

        result = db_service.find_overcapacity_day_in_stay_locked(
            db,
            dropoff_date=date(2026, 6, 10),
            pickup_date=date(2026, 6, 1),
            cap=10,
        )

        assert result is None
        assert db.execute.call_count == 0


# ============================================================================
# Webhook integration: payment_intent.succeeded over-cap leaves PENDING
# ============================================================================


class _StripeObj(dict):
    """Dict that also exposes its keys via attribute access — minimal
    mimic of Stripe's StripeObject so the webhook handler's mix of
    data["id"] (bracket) and getattr(data, "metadata", {}) (attribute)
    both resolve correctly in tests. Plain dicts would fail the second
    form because dicts don't expose keys as attributes.
    """
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


def _stripe_event(event_type, data):
    return {"type": event_type, "data": {"object": _StripeObj(data)}}


def _make_pending_booking(reference="TAG-RACE1", booking_id=42):
    return SimpleNamespace(
        id=booking_id,
        reference=reference,
        status=BookingStatus.PENDING,
        dropoff_date=date(2026, 7, 10),
        pickup_date=date(2026, 7, 12),
    )


def _make_confirmed_booking(reference="TAG-RACE1", booking_id=42):
    return SimpleNamespace(
        id=booking_id,
        reference=reference,
        status=BookingStatus.CONFIRMED,
        dropoff_date=date(2026, 7, 10),
        pickup_date=date(2026, 7, 12),
    )


def _make_payment(intent_id="pi_test", booking_id=42, payment_id=1):
    """Payment-shaped namespace as returned by db_service.get_payment_by_intent_id."""
    return SimpleNamespace(
        id=payment_id,
        booking_id=booking_id,
        stripe_payment_intent_id=intent_id,
    )


@pytest.fixture
def webhook_client(monkeypatch):
    """TestClient with Stripe signature verification stubbed, get_db
    overridden to a MagicMock, and update_payment_status replaced with
    a spy so the test can assert whether it was called."""
    monkeypatch.setattr(main, "is_stripe_configured", lambda: True)
    monkeypatch.setattr(main, "log_audit_event", lambda **kw: None)
    monkeypatch.setattr(main, "log_error", lambda **kw: None)

    db = MagicMock()
    db.commit = MagicMock()

    def _gen_db():
        yield db

    app.dependency_overrides[get_db] = _gen_db
    try:
        yield db, monkeypatch
    finally:
        app.dependency_overrides.clear()


class TestWebhookCapacityRace:
    """H/U/E/B for the webhook re-check that closes the
    'checkout passed, webhook arrived late' oversell window.

    The webhook gates by Payment → booking_id → Booking (same lookup
    path update_payment_status uses), NOT by Stripe metadata
    booking_reference. Metadata is logging-only. This guarantees the
    recheck and the eventual confirmation are looking at the same row.
    """

    def test_H_under_cap_proceeds_to_update_payment_status(
        self, webhook_client, monkeypatch
    ):
        # H: PENDING booking, recheck under cap → update_payment_status
        # IS called, normal flow resumes.
        db, _ = webhook_client
        booking = _make_pending_booking(booking_id=42)
        payment = _make_payment(intent_id="pi_under", booking_id=42)

        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id",
            lambda d, pi: payment,
        )
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 42 else None,
        )
        # Under cap → helper returns None
        recheck_spy = MagicMock(return_value=None)
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        update_spy = MagicMock(return_value=(None, False))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_under",
            "metadata": {"booking_reference": "TAG-RACE1"},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        assert resp.status_code == 200
        assert resp.json().get("status") != "capacity_race_detected"
        # Helper was called and update proceeded.
        recheck_spy.assert_called_once()
        update_spy.assert_called_once()

    def test_U_over_cap_leaves_pending_and_skips_update(
        self, webhook_client, monkeypatch
    ):
        # U: PENDING booking, recheck OVER cap → response carries
        # capacity_race_detected, update_payment_status NOT called,
        # booking stays PENDING for ops refund.
        db, _ = webhook_client
        booking = _make_pending_booking(booking_id=42)
        payment = _make_payment(intent_id="pi_over", booking_id=42)

        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id",
            lambda d, pi: payment,
        )
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 42 else None,
        )
        recheck_spy = MagicMock(
            return_value=(date(2026, 7, 11), 64),
        )
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        update_spy = MagicMock(return_value=(None, False))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_over",
            "metadata": {"booking_reference": "TAG-RACE1"},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "capacity_race_detected"
        # Response reference comes from the DB booking row (canonical),
        # not Stripe metadata.
        assert body["booking_reference"] == "TAG-RACE1"
        # Recheck happened, update did NOT.
        recheck_spy.assert_called_once()
        update_spy.assert_not_called()
        # Booking remains PENDING (helper didn't mutate it; status check
        # in handler is the gate).
        assert booking.status == BookingStatus.PENDING

    def test_U_metadata_missing_booking_reference_recheck_still_fires(
        self, webhook_client, monkeypatch
    ):
        # U (new — 2026-05-29 review fix): Stripe sends an event where
        # metadata is missing booking_reference entirely (lost during a
        # PaymentIntent rebuild, stale checkout cookie, or operator
        # mistake). update_payment_status still finds the payment row
        # via stripe_payment_intent_id and would still confirm the
        # booking — so the recheck MUST also key off the payment row,
        # not metadata.
        #
        # Pre-fix: recheck silently skipped (booking_reference is None
        # → `if booking_reference:` falls through).
        # Post-fix: recheck fires via Payment.booking_id → Booking.
        db, _ = webhook_client
        booking = _make_pending_booking(reference="TAG-METASILENT",
                                         booking_id=99)
        payment = _make_payment(intent_id="pi_meta_silent", booking_id=99)

        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id",
            lambda d, pi: payment,
        )
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 99 else None,
        )
        recheck_spy = MagicMock(
            return_value=(date(2026, 7, 11), 64),
        )
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        update_spy = MagicMock(return_value=(None, False))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        # Metadata is EMPTY — no booking_reference.
        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_meta_silent",
            "metadata": {},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        assert resp.status_code == 200
        body = resp.json()
        # CRITICAL: recheck fired despite metadata gap, blocked the
        # confirmation, and the response carries the DB-canonical
        # reference (NOT what Stripe sent).
        assert body["status"] == "capacity_race_detected"
        assert body["booking_reference"] == "TAG-METASILENT"
        recheck_spy.assert_called_once()
        update_spy.assert_not_called()

    def test_E_already_confirmed_skips_recheck_idempotent_replay(
        self, webhook_client, monkeypatch
    ):
        # E: webhook for booking already CONFIRMED (replay) → recheck
        # MUST be skipped (no need to gate an already-accepted booking;
        # gating it now would falsely raise on legitimate retries).
        # update_payment_status still called for its idempotency path.
        db, _ = webhook_client
        booking = _make_confirmed_booking(booking_id=42)
        payment = _make_payment(intent_id="pi_replay", booking_id=42)

        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id",
            lambda d, pi: payment,
        )
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 42 else None,
        )
        recheck_spy = MagicMock(
            return_value=(date(2026, 7, 11), 99),  # would trip if called
        )
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        update_spy = MagicMock(return_value=(None, True))  # was_already_processed=True
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_replay",
            "metadata": {"booking_reference": "TAG-RACE1"},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        assert resp.status_code == 200
        assert resp.json().get("status") != "capacity_race_detected"
        # Recheck SKIPPED on already-CONFIRMED bookings.
        recheck_spy.assert_not_called()
        # Update was called (it handles idempotent replays internally).
        update_spy.assert_called_once()

    def test_concurrent_duplicate_post_lock_refresh_clears_race(
        self, webhook_client, monkeypatch
    ):
        # 2026-05-29 review-fix regression. Two webhooks for the same
        # PaymentIntent arrive together. Webhook B loads its
        # race_payment + race_booking BEFORE acquiring the advisory
        # lock — both look PENDING in its session cache. B then blocks
        # on the lock while A confirms + commits + releases.
        #
        # When B acquires the lock and runs its recheck, find_overcap
        # excludes B's own booking_id (= same as A's) so the recheck
        # doesn't detect A's confirmation directly. But A DID just
        # confirm B's booking — B must not return
        # capacity_race_detected (the booking isn't stuck PENDING; A
        # already committed it). Webhook handler's post-lock
        # db.refresh on race_booking reveals the concurrent CONFIRMED,
        # and the handler clears race_offending so it falls through to
        # update_payment_status, which (with its own db.refresh)
        # correctly reports was_already_processed and skips writes.
        db, _ = webhook_client
        # Initially stale-PENDING; refresh will flip them.
        booking = _make_pending_booking(booking_id=77,
                                         reference="TAG-CONCURRENT")
        payment = _make_payment(intent_id="pi_concurrent2", booking_id=77)

        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id",
            lambda d, pi: payment,
        )
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 77 else None,
        )
        # Helper acquires lock + recheck. Returns None (no overcap from
        # OTHER bookings; B's own row is excluded by booking_id).
        recheck_spy = MagicMock(return_value=None)
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        # Simulate A's commit by mutating booking + payment when the
        # webhook's post-lock refresh runs.
        def refresh_side_effect(obj):
            if obj is booking:
                obj.status = BookingStatus.CONFIRMED
            elif obj is payment:
                from db_models import PaymentStatus
                obj.status = PaymentStatus.SUCCEEDED
        db.refresh = MagicMock(side_effect=refresh_side_effect)
        # update_payment_status would internally also refresh + report
        # was_already_processed=True. Spied for assertion only.
        update_spy = MagicMock(return_value=(payment, True))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_concurrent2",
            "metadata": {"booking_reference": "TAG-CONCURRENT"},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        # Critical: NOT a capacity_race_detected response. The booking
        # isn't stuck PENDING — A confirmed it. We fall through to
        # update_payment_status which idempotently handles the dupe.
        assert resp.status_code == 200
        assert resp.json().get("status") != "capacity_race_detected", (
            "Concurrent duplicate webhook must NOT respond as a race "
            "detection. The booking was already confirmed by the "
            "concurrent webhook; the post-lock refresh must reveal "
            "the CONFIRMED status and clear race_offending."
        )
        # Recheck was called (locks acquired); refresh was called for
        # both objects.
        recheck_spy.assert_called_once()
        assert db.refresh.call_count == 2
        # update_payment_status was reached (it handles idempotency
        # internally via its own db.refresh).
        update_spy.assert_called_once()

    def test_B_payment_not_found_skips_recheck(
        self, webhook_client, monkeypatch
    ):
        # B: webhook for a PaymentIntent NOT in our payments table
        # (e.g., manual-booking flow where admin sent the customer a
        # Stripe payment link not tied to a payments row) →
        # get_payment_by_intent_id returns None, recheck skipped, fall
        # through to update_payment_status which logs the not-found case.
        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id", lambda d, pi: None,
        )
        # Should never be called.
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: pytest.fail("get_booking_by_id should not be called when payment is missing"),
        )
        recheck_spy = MagicMock(return_value=(date(2026, 7, 11), 99))
        monkeypatch.setattr(
            db_service, "find_overcapacity_day_in_stay_locked", recheck_spy,
        )
        update_spy = MagicMock(return_value=(None, False))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)

        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_orphan",
            "metadata": {"booking_reference": "TAG-NOTFOUND"},
            "amount": 9900,
        })
        monkeypatch.setattr(
            main, "verify_webhook_signature", lambda payload, sig: evt,
        )

        from fastapi.testclient import TestClient
        resp = TestClient(app).post(
            "/api/webhooks/stripe", json={},
            headers={"Stripe-Signature": "t=1,v1=s"},
        )

        assert resp.status_code == 200
        assert resp.json().get("status") != "capacity_race_detected"
        # Recheck skipped when payment not found.
        recheck_spy.assert_not_called()
        # Update proceeds (it handles the not-found path with a log).
        update_spy.assert_called_once()


# ============================================================================
# Single-commit invariant: update_payment_status under the recheck lock
# ============================================================================
#
# Closes the test gap flagged in the 2026-05-29 code review: the webhook
# integration tests above stub db_service.update_payment_status, so they
# can't see whether the real function commits twice (releasing the
# transaction-scoped advisory lock) or once (lock held throughout).
#
# These tests call the REAL db_service.update_payment_status — no
# monkeypatch — and assert exactly ONE db.commit() per call. That is the
# load-bearing invariant for the webhook capacity race fix: anything
# more than one commit between the find_overcapacity_day_in_stay_locked()
# call and the booking-flip-to-CONFIRMED breaks the lock-held-throughout
# guarantee and re-opens the oversell window.


class TestUpdatePaymentStatusSingleCommit:
    """Regression for the 2026-05-29 tx-boundary fix in
    db_service.update_payment_status. The function previously committed
    twice (payment flip, then booking flip), releasing the caller's
    advisory lock between the two writes. After the fix it commits
    exactly once at the end so the caller's lock stays held across both.
    """

    def _make_db(self, payment, booking):
        """Wire MagicMock so db.query(Payment) returns the payment, and
        db.query(Booking) returns the booking. commit + refresh are
        spies for assertion."""
        from db_models import (
            Payment as DbPayment,
            Booking as DbBooking,
        )

        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        def query_side_effect(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            if model is DbPayment:
                chain.first.return_value = payment
            elif model is DbBooking:
                chain.first.return_value = booking
            else:
                chain.first.return_value = None
            return chain

        db.query.side_effect = query_side_effect
        return db

    def test_H_succeeded_path_commits_exactly_once(self):
        # H: Happy path — payment.status = SUCCEEDED triggers both the
        # payment write AND the booking-flip-to-CONFIRMED write. Critical
        # invariant: exactly ONE commit between them so the caller's
        # advisory lock (xact-scoped) survives both writes.
        from db_models import PaymentStatus
        payment = SimpleNamespace(
            id=1, booking_id=42,
            status=PaymentStatus.PENDING,
            stripe_payment_intent_id="pi_h",
            paid_at=None,
        )
        booking = SimpleNamespace(
            id=42, status=BookingStatus.PENDING,
        )
        db = self._make_db(payment, booking)

        _, was_already = db_service.update_payment_status(
            db,
            stripe_payment_intent_id="pi_h",
            status=PaymentStatus.SUCCEEDED,
            paid_at=datetime(2026, 5, 29, 12, 0, 0),
        )

        # THE invariant.
        assert db.commit.call_count == 1, (
            f"Expected exactly 1 commit for the lock-held-throughout "
            f"invariant; got {db.commit.call_count}. Two commits release "
            f"the xact-scoped advisory lock between payment flip and "
            f"booking flip, re-opening the capacity-race oversell window."
        )
        # And both writes did land.
        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.paid_at == datetime(2026, 5, 29, 12, 0, 0)
        assert booking.status == BookingStatus.CONFIRMED
        assert was_already is False

    def test_U_failed_path_commits_exactly_once_no_booking_flip(self):
        # U: Unhappy path — payment_intent.payment_failed (status=FAILED)
        # writes the payment but does NOT flip booking to CONFIRMED.
        # Single commit invariant must still hold.
        from db_models import PaymentStatus
        payment = SimpleNamespace(
            id=1, booking_id=42,
            status=PaymentStatus.PENDING,
            stripe_payment_intent_id="pi_u",
            paid_at=None,
        )
        booking = SimpleNamespace(
            id=42, status=BookingStatus.PENDING,
        )
        db = self._make_db(payment, booking)

        db_service.update_payment_status(
            db,
            stripe_payment_intent_id="pi_u",
            status=PaymentStatus.FAILED,
        )

        assert db.commit.call_count == 1
        assert payment.status == PaymentStatus.FAILED
        # Booking is NOT confirmed on payment failure.
        assert booking.status == BookingStatus.PENDING

    def test_E_idempotent_replay_skips_all_writes_and_commits(self):
        # E: Edge — duplicate webhook delivery, payment already SUCCEEDED.
        # No writes, no commits, was_already_processed=True. The lock
        # held by the caller doesn't matter here because there's no work
        # to gate.
        from db_models import PaymentStatus
        payment = SimpleNamespace(
            id=1, booking_id=42,
            status=PaymentStatus.SUCCEEDED,
            stripe_payment_intent_id="pi_e",
            paid_at=datetime(2026, 5, 29, 11, 0, 0),
        )
        booking = SimpleNamespace(
            id=42, status=BookingStatus.CONFIRMED,
        )
        db = self._make_db(payment, booking)

        _, was_already = db_service.update_payment_status(
            db,
            stripe_payment_intent_id="pi_e",
            status=PaymentStatus.SUCCEEDED,
        )

        assert was_already is True
        assert db.commit.call_count == 0

    def test_B_payment_not_found_no_writes_no_commits(self):
        # B: Boundary — payment_intent_id not in DB (e.g., manual booking
        # flow where the Stripe PaymentIntent doesn't correspond to a
        # payments row). Returns (None, False), no commits, no writes.
        from db_models import PaymentStatus
        db = self._make_db(payment=None, booking=None)

        result, was_already = db_service.update_payment_status(
            db,
            stripe_payment_intent_id="pi_b_missing",
            status=PaymentStatus.SUCCEEDED,
        )

        assert result is None
        assert was_already is False
        assert db.commit.call_count == 0

    def test_concurrent_duplicate_webhook_refresh_yields_was_already_processed(self):
        # 2026-05-29 review-fix regression. Simulates a concurrent
        # duplicate webhook: webhook A confirmed the payment + flipped
        # the booking inside its own transaction. Webhook B loaded the
        # SAME payment row first (status=PENDING in its session cache),
        # then blocked on the advisory lock until A committed and
        # released. Without db.refresh, B's was_already_processed reads
        # the stale cached status (still PENDING) and B redoes payment
        # + booking writes + all the downstream idempotency-gated tasks
        # (planner fire, dvla check, slot booking, promo mark).
        #
        # Fix: update_payment_status now calls db.refresh(payment)
        # before checking status. This test simulates the concurrent
        # commit by mutating payment.status via the refresh side effect.
        from db_models import PaymentStatus
        payment = SimpleNamespace(
            id=1, booking_id=42,
            status=PaymentStatus.PENDING,  # stale cached state
            stripe_payment_intent_id="pi_concurrent",
            paid_at=None,
        )
        booking = SimpleNamespace(
            id=42, status=BookingStatus.PENDING,
        )
        db = self._make_db(payment, booking)
        # The concurrent webhook's commit lands. Simulate by mutating
        # payment.status when db.refresh(payment) is called.
        def refresh_side_effect(obj):
            if obj is payment:
                obj.status = PaymentStatus.SUCCEEDED
                obj.paid_at = datetime(2026, 5, 29, 11, 59, 0)
        db.refresh.side_effect = refresh_side_effect

        _, was_already = db_service.update_payment_status(
            db,
            stripe_payment_intent_id="pi_concurrent",
            status=PaymentStatus.SUCCEEDED,
            paid_at=datetime(2026, 5, 29, 12, 0, 0),
        )

        # THE invariant: refresh let us see the concurrent webhook's
        # write, so was_already_processed=True and we skip all writes.
        assert was_already is True, (
            "After db.refresh(payment), payment.status is SUCCEEDED — "
            "was_already_processed must be True. Returning False would "
            "cause duplicate downstream tasks (planner, dvla, promo, slot)."
        )
        assert db.commit.call_count == 0, (
            "Concurrent duplicate must produce ZERO writes — the prior "
            "webhook already committed payment + booking. Got "
            f"{db.commit.call_count} commits, indicating a duplicate write."
        )
        # Booking is NOT touched a second time.
        assert booking.status == BookingStatus.PENDING, (
            "Mock booking.status should be unchanged by us — "
            "the concurrent webhook is the one that wrote CONFIRMED. "
            "If we wrote, was_already_processed gated incorrectly."
        )
