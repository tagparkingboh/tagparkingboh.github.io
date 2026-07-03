"""
TestClient wiring tests for the time-aware capacity gate
(CAPACITY_GATE_TIME_AWARE) across its three endpoint surfaces:

  1. GET /api/capacity/check-slot — now delegates to
     db_service.peak_concurrent_occupancy; tie rule REVERSED vs the old
     inline sweep (departures free space before same-instant arrivals) and
     REFUNDED added to the status set.
  2. GET /api/capacity/daily — additive daily_through_occupancy field
     (strictly dropoff < day < pickup, CONFIRMED+COMPLETED+REFUNDED);
     daily_occupancy keeps its historical touching semantics and still
     EXCLUDES REFUNDED.
  3. POST /api/payments/create-intent — flag OFF → per-day gate
     (find_overcapacity_day_in_stay), flag ON → moment gate
     (find_overcapacity_moment_in_stay) fed with the derived entry/exit
     times; 400 message still names the offending day.
  4. POST /api/webhooks/stripe — flag ON → locked moment gate with the
     booking's STORED times; flag OFF → locked per-day gate. Race handling
     (capacity_race_detected, PENDING left for ops) unchanged.

TestClient + import-from-main per project convention so these count
toward coverage. FakeQuery stubs ignore filter clauses — status-filter
assertions live in test_capacity_time_aware.py's clause-capture tests.
"""
import sys
from datetime import date as date_type, date, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import db_service
import main
from main import app
from database import get_db
from db_models import Booking, BookingStatus, ParkingCapacitySetting


# =============================================================================
# Shared stubs (FakeQuery convention from test_capacity_check_slot.py)
# =============================================================================

class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def mk_booking(*, dropoff_date, dropoff_time, pickup_date, pickup_time,
               status=BookingStatus.CONFIRMED):
    return SimpleNamespace(
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
        status=status,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._tables = {Booking: [], ParkingCapacitySetting: []}

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    db.query.side_effect = _query
    return db


def _client(mock_db):
    def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


def _qs(*, dd, dt, pd, pt):
    return f"dropoff_date={dd}&dropoff_time={dt}&pickup_date={pd}&pickup_time={pt}"


# =============================================================================
# 1. check-slot: departures-first tie rule (reversal) + REFUNDED
# =============================================================================

class TestCheckSlotTieRuleReversal:
    """Old sweep sorted arrivals BEFORE departures at the same instant
    ('transient collision'); the shared helper reverses that. These pin the
    new semantics at t-ε / t / t+ε with the swap INSIDE the customer's
    window (the pre-existing boundary test only covered swaps at the
    window edge, which truncation already zeroed out).

    Reviewer fix (2026-07-02): check-slot only adopts the new tie rule
    when CAPACITY_GATE_TIME_AWARE is on — flag-off keeps the legacy
    arrivals-first order. These tests therefore run flag-on; the t±ε
    cases are flag-insensitive and double as legacy sanity checks."""

    D = date(2026, 6, 15)

    @pytest.fixture(autouse=True)
    def _flag_on(self, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")

    def _peak(self, mock_db, *, other_arrival):
        mock_db._tables[Booking] = [
            # Car A: in the lot 09:00 → 16:00 (departs mid-window)
            mk_booking(dropoff_date=self.D, dropoff_time=time(9, 0),
                       pickup_date=self.D, pickup_time=time(16, 0)),
            # Car B: arrives around A's departure, stays overnight
            mk_booking(dropoff_date=self.D, dropoff_time=other_arrival,
                       pickup_date=self.D + timedelta(days=1),
                       pickup_time=time(10, 0)),
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="08:00", pd="2026-06-16", pt="12:00",
            )
        )
        assert r.status_code == 200
        return r.json()["peak"]

    def test_B_arrival_minute_before_departure_collides(self, mock_db):
        assert self._peak(mock_db, other_arrival=time(15, 59)) == 2

    def test_B_same_instant_swap_does_not_collide(self, mock_db):
        # REVERSAL: old code counted this as peak 2 (transient collision);
        # departures-first makes it a clean handover → peak 1.
        assert self._peak(mock_db, other_arrival=time(16, 0)) == 1

    def test_B_arrival_minute_after_departure_no_collision(self, mock_db):
        assert self._peak(mock_db, other_arrival=time(16, 1)) == 1

    def test_H_at_cap_swap_now_allowed(self, mock_db):
        """73 cars leave 12:00, 72 fresh cars arrive 12:00 (default cap
        73): peak stays 73, customer is the 73rd+1... peak+1=74 — build at
        72 leavers so customer fits: the swap must not phantom-block."""
        d = self.D
        mock_db._tables[Booking] = (
            [mk_booking(dropoff_date=d, dropoff_time=time(8, 0),
                        pickup_date=d, pickup_time=time(12, 0))
             for _ in range(72)]
            + [mk_booking(dropoff_date=d, dropoff_time=time(12, 0),
                          pickup_date=d + timedelta(days=1), pickup_time=time(10, 0))
               for _ in range(72)]
        )
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="07:00", pd="2026-06-16", pt="12:00",
            )
        )
        body = r.json()
        assert body["peak"] == 72
        assert body["allowed"] is True


class TestCheckSlotLegacyFlagOff:
    """Reviewer fix: with CAPACITY_GATE_TIME_AWARE off (or unset),
    check-slot keeps its pre-change semantics — a same-instant swap
    still counts as a transient collision (arrivals-first tie order)."""

    D = date(2026, 6, 15)

    def test_B_same_instant_swap_still_collides_flag_off(
            self, mock_db, monkeypatch):
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=self.D, dropoff_time=time(9, 0),
                       pickup_date=self.D, pickup_time=time(16, 0)),
            mk_booking(dropoff_date=self.D, dropoff_time=time(16, 0),
                       pickup_date=self.D + timedelta(days=1),
                       pickup_time=time(10, 0)),
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="08:00", pd="2026-06-16", pt="12:00",
            )
        )
        assert r.status_code == 200
        assert r.json()["peak"] == 2


class TestCheckSlotRefunded:
    def test_H_refunded_car_counts_in_peak(self, mock_db):
        """FakeQuery bypasses the status filter, but the endpoint passes the
        row through the shared sweep — a REFUNDED row seeded here must
        contribute, proving the sweep doesn't re-filter by status in
        Python. (Clause-level status assertions live in the helper suite.)"""
        d = date(2026, 6, 15)
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=d, dropoff_time=time(9, 0),
                       pickup_date=d + timedelta(days=2), pickup_time=time(10, 0),
                       status=BookingStatus.REFUNDED),
        ]
        r = _client(mock_db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.json()["peak"] == 1


# =============================================================================
# 2. capacity/daily: daily_through_occupancy
# =============================================================================

class TestCapacityDailyThrough:
    def test_H_through_field_present_and_additive(self, mock_db):
        """3-day stay: dropoff/pickup days are touching-only; the middle
        day is a through-day. daily_occupancy must be unchanged by the new
        field."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=date(2026, 6, 15), dropoff_time=time(10, 0),
                       pickup_date=date(2026, 6, 17), pickup_time=time(9, 0)),
        ]
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        assert r.status_code == 200
        body = r.json()
        assert body["daily_occupancy"] == {
            "2026-06-15": 1, "2026-06-16": 1, "2026-06-17": 1,
        }
        assert body["daily_through_occupancy"] == {
            "2026-06-15": 0, "2026-06-16": 1, "2026-06-17": 0,
        }

    def test_B_boundary_edges_dropoff_and_pickup_days_not_through(self, mock_db):
        """t-ε/t/t+ε on both edges: day before dropoff (not touching, not
        through), dropoff day (touching only), first full day (through),
        last full day (through), pickup day (touching only)."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=date(2026, 6, 15), dropoff_time=None,
                       pickup_date=date(2026, 6, 19), pickup_time=None),
        ]
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-14&date_to=2026-06-20")
        body = r.json()
        assert body["daily_through_occupancy"] == {
            "2026-06-14": 0,
            "2026-06-15": 0,   # dropoff day: touching, NOT through
            "2026-06-16": 1,
            "2026-06-17": 1,
            "2026-06-18": 1,
            "2026-06-19": 0,   # pickup day: touching, NOT through
            "2026-06-20": 0,
        }
        assert body["daily_occupancy"]["2026-06-14"] == 0
        assert body["daily_occupancy"]["2026-06-15"] == 1
        assert body["daily_occupancy"]["2026-06-19"] == 1
        assert body["daily_occupancy"]["2026-06-20"] == 0

    def test_B_single_day_booking_is_never_through(self, mock_db):
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=date(2026, 6, 15), dropoff_time=time(8, 0),
                       pickup_date=date(2026, 6, 15), pickup_time=time(20, 0)),
        ]
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        body = r.json()
        assert body["daily_occupancy"]["2026-06-15"] == 1
        assert body["daily_through_occupancy"]["2026-06-15"] == 0

    def test_E_refunded_counts_through_but_not_touching(self, mock_db):
        """REFUNDED rows are now fetched by the handler's widened query:
        they must appear in the through map (car still on site) while
        daily_occupancy keeps excluding them (its historical meaning)."""
        mock_db._tables[Booking] = [
            mk_booking(dropoff_date=date(2026, 6, 15), dropoff_time=time(10, 0),
                       pickup_date=date(2026, 6, 17), pickup_time=time(9, 0),
                       status=BookingStatus.REFUNDED),
        ]
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-17")
        body = r.json()
        assert body["daily_occupancy"] == {
            "2026-06-15": 0, "2026-06-16": 0, "2026-06-17": 0,
        }
        assert body["daily_through_occupancy"] == {
            "2026-06-15": 0, "2026-06-16": 1, "2026-06-17": 0,
        }

    def test_H_prod_july_4_shape(self, mock_db):
        """The incident shape in miniature: touching >> through on a
        turnover day. 3 through + 2 leaving + 2 arriving → touching 7,
        through 3."""
        d = date(2026, 7, 4)
        mock_db._tables[Booking] = (
            [mk_booking(dropoff_date=d - timedelta(days=1), dropoff_time=time(9, 0),
                        pickup_date=d + timedelta(days=1), pickup_time=time(9, 0))
             for _ in range(3)]
            + [mk_booking(dropoff_date=d - timedelta(days=2), dropoff_time=time(9, 0),
                          pickup_date=d, pickup_time=time(8, 0))
               for _ in range(2)]
            + [mk_booking(dropoff_date=d, dropoff_time=time(15, 0),
                          pickup_date=d + timedelta(days=3), pickup_time=time(9, 0))
               for _ in range(2)]
        )
        r = _client(mock_db).get(
            f"/api/capacity/daily?date_from={d.isoformat()}&date_to={d.isoformat()}")
        body = r.json()
        assert body["daily_occupancy"][d.isoformat()] == 7
        assert body["daily_through_occupancy"][d.isoformat()] == 3


# =============================================================================
# 3. create-intent: flag routing + message
# =============================================================================

def _empty_db():
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


def _override_db(db):
    def gen():
        yield db
    app.dependency_overrides[get_db] = gen


def _valid_payload(drop_off_date="2026-08-15", pickup_date="2026-08-22"):
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
        # Return flight lands 18:15 → exit window 18:45 same day. This is
        # the field the gate's time derivation actually reads
        # (_exit_window_for_quote_request); CreatePaymentRequest has NO
        # `pickup_time` field.
        "flight_arrival_time": "18:15",
        "billing_address1": "1 High St",
        "billing_city": "Bournemouth",
        "billing_postcode": "BH1 1AA",
    }


class TestCreateIntentGateRouting:
    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        app.dependency_overrides.clear()

    def _spies(self, monkeypatch, *, day_result=None, moment_result=None):
        day_spy = MagicMock(return_value=day_result)
        moment_spy = MagicMock(return_value=moment_result)
        monkeypatch.setattr("db_service.find_overcapacity_day_in_stay", day_spy)
        monkeypatch.setattr("db_service.find_overcapacity_moment_in_stay", moment_spy)
        monkeypatch.setattr(
            "db_service.get_pending_booking_by_session", lambda db, sid: None)
        return day_spy, moment_spy

    def test_H_flag_off_uses_per_day_gate_only(self, monkeypatch):
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        day_spy, moment_spy = self._spies(monkeypatch)
        _override_db(_empty_db())
        TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        day_spy.assert_called_once()
        moment_spy.assert_not_called()

    def test_H_flag_on_uses_moment_gate_with_derived_times(self, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        day_spy, moment_spy = self._spies(monkeypatch)
        _override_db(_empty_db())
        TestClient(app).post("/api/payments/create-intent", json=_valid_payload())
        moment_spy.assert_called_once()
        day_spy.assert_not_called()
        kw = moment_spy.call_args.kwargs
        # drop_off_time straight from the payload; pickup_time derived from
        # flight_arrival_time 18:15 + 30min exit buffer = 18:45 same day.
        assert kw["dropoff_time"] == time(10, 0)
        assert kw["pickup_time"] == time(18, 45)
        assert kw["dropoff_date"] == date_type(2026, 8, 15)
        assert kw["pickup_date"] == date_type(2026, 8, 22)

    def test_U_flag_on_without_arrival_time_worst_cases_instead_of_erroring(
            self, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        day_spy, moment_spy = self._spies(monkeypatch)
        _override_db(_empty_db())
        payload = _valid_payload()
        del payload["flight_arrival_time"]  # no arrival time anywhere
        resp = TestClient(app).post(
            "/api/payments/create-intent", json=payload)
        # Must not be rejected by the broken derivation…
        if resp.status_code == 400:
            assert "pickup_time" not in resp.json().get("detail", "")
        # …and the gate must still run, worst-casing the missing time.
        moment_spy.assert_called_once()
        assert moment_spy.call_args.kwargs["pickup_time"] is None

    def test_H_flag_on_arrival_time_rolls_exit_past_midnight(self, monkeypatch):
        """pickup_flight_time 23:50 → exit 00:20 NEXT day: the gate must be
        called with the rolled date and the capacity map must cover it."""
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        day_spy, moment_spy = self._spies(monkeypatch)
        _override_db(_empty_db())
        payload = _valid_payload()
        # flight_arrival_time takes priority in the derivation — replace it
        # so the 23:50 landing drives the exit window.
        payload["flight_arrival_time"] = "23:50"
        TestClient(app).post("/api/payments/create-intent", json=payload)
        kw = moment_spy.call_args.kwargs
        assert kw["pickup_date"] == date_type(2026, 8, 23)
        assert kw["pickup_time"] == time(0, 20)
        # cap map extended through the rolled exit day
        assert "2026-08-23" in kw["cap_by_date"]

    def test_U_flag_on_over_cap_message_names_offending_day(self, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        self._spies(monkeypatch, moment_result=(date_type(2026, 8, 18), 80, 80))
        _override_db(_empty_db())
        resp = TestClient(app).post(
            "/api/payments/create-intent", json=_valid_payload())
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "full" in detail
        assert "18 august" in detail

    def test_U_flag_off_over_cap_message_unchanged(self, monkeypatch):
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        self._spies(monkeypatch, day_result=(date_type(2026, 8, 18), 80))
        _override_db(_empty_db())
        resp = TestClient(app).post(
            "/api/payments/create-intent", json=_valid_payload())
        assert resp.status_code == 400
        assert "18 august" in resp.json()["detail"].lower()

    def test_H_flag_on_under_cap_proceeds_past_gate(self, monkeypatch):
        """moment gate returns None → request proceeds beyond the capacity
        400 (it will fail later for unrelated mock reasons; just assert it
        is not the capacity rejection)."""
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        self._spies(monkeypatch)
        _override_db(_empty_db())
        resp = TestClient(app).post(
            "/api/payments/create-intent", json=_valid_payload())
        if resp.status_code == 400:
            assert "we're full" not in resp.json().get("detail", "").lower()


# =============================================================================
# 4. webhook re-check: flag routing with stored times
# =============================================================================

class _StripeObj(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


def _stripe_event(event_type, data):
    return {"type": event_type, "data": {"object": _StripeObj(data)}}


def _make_pending_booking(booking_id=42):
    return SimpleNamespace(
        id=booking_id,
        reference="TAG-RACE1",
        status=BookingStatus.PENDING,
        dropoff_date=date(2026, 7, 10),
        pickup_date=date(2026, 7, 12),
        dropoff_time=time(14, 0),
        pickup_time=time(9, 30),
    )


@pytest.fixture
def webhook_client(monkeypatch):
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


def _wire_webhook(monkeypatch, booking, *, day_result=None, moment_result=None):
    payment = SimpleNamespace(
        id=1, booking_id=booking.id, stripe_payment_intent_id="pi_ta")
    monkeypatch.setattr(
        db_service, "get_payment_by_intent_id", lambda d, pi: payment)
    monkeypatch.setattr(
        db_service, "get_booking_by_id",
        lambda d, bid: booking if bid == booking.id else None)
    day_spy = MagicMock(return_value=day_result)
    moment_spy = MagicMock(return_value=moment_result)
    monkeypatch.setattr(
        db_service, "find_overcapacity_day_in_stay_locked", day_spy)
    monkeypatch.setattr(
        db_service, "find_overcapacity_moment_in_stay_locked", moment_spy)
    update_spy = MagicMock(return_value=(None, False))
    monkeypatch.setattr(db_service, "update_payment_status", update_spy)
    evt = _stripe_event("payment_intent.succeeded", {
        "id": "pi_ta",
        "metadata": {"booking_reference": "TAG-RACE1"},
        "amount": 9900,
    })
    monkeypatch.setattr(main, "verify_webhook_signature", lambda p, s: evt)
    return day_spy, moment_spy, update_spy


def _post_webhook():
    return TestClient(app).post(
        "/api/webhooks/stripe", json={},
        headers={"Stripe-Signature": "t=1,v1=s"},
    )


class TestWebhookGateRouting:
    def test_H_flag_on_moment_locked_called_with_stored_times(
            self, webhook_client):
        db, monkeypatch = webhook_client
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        booking = _make_pending_booking()
        day_spy, moment_spy, update_spy = _wire_webhook(monkeypatch, booking)

        resp = _post_webhook()

        assert resp.status_code == 200
        moment_spy.assert_called_once()
        day_spy.assert_not_called()
        kw = moment_spy.call_args.kwargs
        assert kw["dropoff_time"] == time(14, 0)
        assert kw["pickup_time"] == time(9, 30)
        assert kw["dropoff_date"] == date(2026, 7, 10)
        assert kw["pickup_date"] == date(2026, 7, 12)
        assert kw["exclude_booking_id"] == booking.id
        update_spy.assert_called_once()  # under cap → confirmation proceeds

    def test_H_flag_off_day_locked_called(self, webhook_client):
        db, monkeypatch = webhook_client
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        booking = _make_pending_booking()
        day_spy, moment_spy, update_spy = _wire_webhook(monkeypatch, booking)

        resp = _post_webhook()

        assert resp.status_code == 200
        day_spy.assert_called_once()
        moment_spy.assert_not_called()
        update_spy.assert_called_once()

    def test_U_flag_on_over_cap_leaves_pending(self, webhook_client):
        """Consistency with create-intent: same helper family decides; on
        over-cap the webhook reports capacity_race_detected and does NOT
        confirm."""
        db, monkeypatch = webhook_client
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        booking = _make_pending_booking()
        day_spy, moment_spy, update_spy = _wire_webhook(
            monkeypatch, booking,
            moment_result=(date(2026, 7, 11), 80, 80),
        )

        resp = _post_webhook()

        assert resp.status_code == 200
        assert resp.json().get("status") == "capacity_race_detected"
        update_spy.assert_not_called()
        assert booking.status == BookingStatus.PENDING


# =============================================================================
# 5. Re-verification additions (2026-07-02, post-review fixes)
# =============================================================================

class TestCapacityDailyFlagEcho:
    """Fix 2 (flag echo): /api/capacity/daily reports the backend's
    CAPACITY_GATE_TIME_AWARE state so the frontend only relaxes its hard
    blocks to the through-count when the backend gate is actually
    time-aware. An older backend that omits the field entirely reads as
    flag-off on the frontend (data.time_aware_gate === true)."""

    def test_H_field_true_when_flag_on(self, mock_db, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.status_code == 200
        assert r.json()["time_aware_gate"] is True

    def test_H_field_false_when_flag_unset(self, mock_db, monkeypatch):
        monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.json()["time_aware_gate"] is False

    def test_B_falsy_env_value_reads_false(self, mock_db, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "0")
        r = _client(mock_db).get(
            "/api/capacity/daily?date_from=2026-06-15&date_to=2026-06-15")
        assert r.json()["time_aware_gate"] is False


class _StatusSpyQuery:
    """Captures the BookingStatus list passed to .in_() via the filter
    clause (same technique as test_capacity_daily's _SpyChain — FakeQuery
    can't observe filters)."""

    def __init__(self, sink):
        self.sink = sink

    def filter(self, *args, **_kw):
        for a in args:
            try:
                vals = a.right.value
            except AttributeError:
                continue
            if isinstance(vals, (list, tuple)) and vals and hasattr(vals[0], "name"):
                self.sink["statuses"] = list(vals)
        return self

    def first(self):
        return None

    def all(self):
        return []


class TestCheckSlotStatusClause:
    """Fix 3: flag-off check-slot must filter exactly the ORIGINAL status
    set (CONFIRMED+COMPLETED+PENDING, no REFUNDED); flag-on adds
    REFUNDED."""

    def _capture(self, monkeypatch_env_value, monkeypatch):
        if monkeypatch_env_value is None:
            monkeypatch.delenv("CAPACITY_GATE_TIME_AWARE", raising=False)
        else:
            monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", monkeypatch_env_value)
        sink = {}
        db = MagicMock()

        def _query(model):
            if model is Booking:
                return _StatusSpyQuery(sink)
            return FakeQuery([])

        db.query.side_effect = _query
        r = _client(db).get(
            "/api/capacity/check-slot?" + _qs(
                dd="2026-06-15", dt="14:00", pd="2026-06-16", pt="10:00",
            )
        )
        assert r.status_code == 200
        return set(sink["statuses"])

    def test_H_flag_off_original_status_set_no_refunded(self, monkeypatch):
        assert self._capture(None, monkeypatch) == {
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.PENDING,
        }

    def test_H_flag_on_adds_refunded(self, monkeypatch):
        assert self._capture("true", monkeypatch) == {
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
            BookingStatus.REFUNDED,
            BookingStatus.PENDING,
        }


class TestCreateIntentInvertedWindow:
    """Fix 1 at the create-intent gate: flag on, same-day stay whose
    derived exit (arrival+30) lands BEFORE the entry time → the REAL
    moment helper (no spy) fails closed with a 400 naming the drop-off
    day, instead of silently passing an unsatisfiable window."""

    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        main.is_stripe_configured = self._real_is_configured
        app.dependency_overrides.clear()

    def test_U_flag_on_inverted_same_day_window_rejected_naming_day(
            self, monkeypatch):
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        monkeypatch.setattr(
            "db_service.get_pending_booking_by_session", lambda db, sid: None)
        _override_db(_empty_db())
        payload = _valid_payload(
            drop_off_date="2026-08-15", pickup_date="2026-08-15")
        payload["drop_off_time"] = "14:00"
        payload["flight_arrival_time"] = "09:30"  # exit 10:00 < entry 14:00
        resp = TestClient(app).post(
            "/api/payments/create-intent", json=payload)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "full" in detail
        assert "15 august" in detail


class TestWebhookInvertedWindow:
    """Fix 1 at the webhook gate: a PENDING booking stored with an
    inverted window (exit <= entry on the same day) must trip the REAL
    locked moment helper's fail-closed branch — capacity_race_detected,
    booking left PENDING, and no advisory locks taken (the inversion is
    rejected before locking)."""

    def test_U_inverted_stored_booking_left_pending_no_locks(
            self, webhook_client):
        db, monkeypatch = webhook_client
        monkeypatch.setenv("CAPACITY_GATE_TIME_AWARE", "true")
        booking = SimpleNamespace(
            id=42,
            reference="TAG-INV1",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 7, 10),
            pickup_date=date(2026, 7, 10),
            dropoff_time=time(14, 0),
            pickup_time=time(9, 30),
        )
        payment = SimpleNamespace(
            id=1, booking_id=42, stripe_payment_intent_id="pi_inv")
        monkeypatch.setattr(
            db_service, "get_payment_by_intent_id", lambda d, pi: payment)
        monkeypatch.setattr(
            db_service, "get_booking_by_id",
            lambda d, bid: booking if bid == 42 else None)
        update_spy = MagicMock(return_value=(None, False))
        monkeypatch.setattr(db_service, "update_payment_status", update_spy)
        evt = _stripe_event("payment_intent.succeeded", {
            "id": "pi_inv",
            "metadata": {"booking_reference": "TAG-INV1"},
            "amount": 9900,
        })
        monkeypatch.setattr(main, "verify_webhook_signature", lambda p, s: evt)
        # NOTE: find_overcapacity_moment_in_stay_locked is NOT spied — the
        # real fail-closed branch must fire.

        resp = _post_webhook()

        assert resp.status_code == 200
        assert resp.json().get("status") == "capacity_race_detected"
        update_spy.assert_not_called()
        assert booking.status == BookingStatus.PENDING
        lock_calls = [
            c for c in db.execute.call_args_list
            if "pg_advisory_xact_lock" in str(c.args[0])
        ]
        assert lock_calls == []  # rejected before any lock acquisition


class TestBlockedPickupDerivation:
    """Fix 4: the blocked-pickup branch derives the customer-meet time
    from the arrival-time fields (arrival + 30, same priority as the
    capacity gate) instead of the nonexistent request.pickup_time.
    Boundary matrix per the time/day/date discipline: no-time date-level
    block, meet inside / at slot start / at slot end / outside the slot."""

    def setup_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = lambda: True

    def teardown_method(self):
        self._real_is_configured = main.is_stripe_configured
        main.is_stripe_configured = self._real_is_configured
        app.dependency_overrides.clear()

    def _wire(self, blocked_pickup):
        """First BlockedDate query (dropoff) → None; second (pickup) →
        the supplied row. Everything else empty (pattern from
        test_create_intent_hueb.TestBlockedDateGate)."""
        db = MagicMock()
        calls = {"n": 0}

        def _query(*args):
            model = args[0] if args else None
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain = MagicMock()
            chain.options.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = []
            if name == "BlockedDate":
                calls["n"] += 1
                chain.first.return_value = (
                    None if calls["n"] == 1 else blocked_pickup)
            else:
                chain.first.return_value = None
            return chain

        db.query.side_effect = _query
        return db

    @staticmethod
    def _full_day_pickup_block():
        return SimpleNamespace(
            id=9,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            block_dropoffs=False,
            block_pickups=True,
            time_slots=[],
        )

    @staticmethod
    def _slot_pickup_block():
        slot = SimpleNamespace(
            start_time=time(16, 30),
            end_time=time(18, 0),
            block_dropoffs=False,
            block_pickups=True,
        )
        return SimpleNamespace(
            id=10,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            block_dropoffs=False,
            block_pickups=False,
            time_slots=[slot],
        )

    def _post(self, blocked, *, arrival=None):
        _override_db(self._wire(blocked))
        payload = _valid_payload()
        payload.pop("flight_arrival_time", None)
        if arrival is not None:
            payload["flight_arrival_time"] = arrival
        return TestClient(app).post(
            "/api/payments/create-intent", json=payload)

    def test_U_full_day_block_no_arrival_time_rejects_with_block_message(self):
        """(a) date-level block + no arrival time anywhere: must be the
        proper blocked-date 400 — the pre-fix code AttributeError'd on
        request.pickup_time here and 400'd with a Python error string."""
        resp = self._post(self._full_day_pickup_block())
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "pick-ups are not available" in detail.lower()
        assert "pickup_time" not in detail

    def test_U_meet_time_inside_blocked_slot_rejected(self):
        # (b) arrival 16:15 → meet 16:45, inside 16:30-18:00.
        resp = self._post(self._slot_pickup_block(), arrival="16:15")
        assert resp.status_code == 400
        assert "pick-ups are not available" in resp.json()["detail"].lower()

    def test_B_meet_time_at_slot_start_rejected(self):
        # arrival 16:00 → meet exactly 16:30 (slot start, inclusive).
        resp = self._post(self._slot_pickup_block(), arrival="16:00")
        assert resp.status_code == 400
        assert "pick-ups are not available" in resp.json()["detail"].lower()

    def test_B_meet_time_at_slot_end_passes(self):
        # arrival 17:30 → meet exactly 18:00 (slot end, exclusive).
        resp = self._post(self._slot_pickup_block(), arrival="17:30")
        if resp.status_code == 400:
            assert "pick-ups are not available" not in resp.json()["detail"].lower()

    def test_E_meet_time_outside_slot_passes(self):
        # (c) arrival 17:45 → meet 18:15, outside the slot.
        resp = self._post(self._slot_pickup_block(), arrival="17:45")
        if resp.status_code == 400:
            assert "pick-ups are not available" not in resp.json()["detail"].lower()

    def test_E_slot_block_with_no_derivable_time_passes(self):
        """Slots present but no arrival time: check_time_blocked returns
        False for missing times (date-level semantics only apply to
        no-slot rows)."""
        resp = self._post(self._slot_pickup_block())
        if resp.status_code == 400:
            assert "pick-ups are not available" not in resp.json()["detail"].lower()
