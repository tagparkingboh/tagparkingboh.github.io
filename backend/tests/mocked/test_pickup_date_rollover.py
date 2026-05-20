"""
Integration tests for the late-evening arrival pickup_date rollover bug.

Production bug (observed 2026-05-19): manual-entry bookings with arrival
>= 23:30 store pickup_time correctly (= arrival + 30 wrapped to HH:MM)
but pickup_date is NOT rolled forward to the next day. Result: 20 affected
bookings (TAG-TPI05272 "Lynn Powell" is tonight's example) appear on the
wrong day in the roster.

The rollover lives in main.py:10880-10896 inside `create_payment`:

    if request.pickup_flight_time:
        total_minutes = landing_hour * 60 + landing_min + 30
        if total_minutes >= 24 * 60:
            pickup_date = pickup_date + timedelta(days=1)
        pickup_time = time((total_minutes // 60) % 24, total_minutes % 60)

This file POSTs to /api/payments/create-intent for each of the 10
arrival-time cases the operator asked about and captures what
db_service.create_full_booking actually receives — that's where the bug
manifests.

Cases (return-flight date = 2026-05-19 Tue / 2026-05-20 Wed):

    arrival_date arrival_time   expected pickup_date   expected pickup_time
    Tue          23:29          Tue (no roll)          23:59
    Tue          23:30          Wed (rolled)           00:00
    Tue          23:31          Wed (rolled)           00:01
    Tue          23:59          Wed (rolled)           00:29
    Wed          00:00          Wed (no roll)          00:30
    Wed          00:01          Wed                    00:31
    Wed          01:58          Wed                    02:28
    Wed          01:59          Wed                    02:29
    Wed          02:00          Wed                    02:30
    Wed          02:01          Wed                    02:31

The first 8 land on the Tuesday operational shift after the calendar's
02:30 re-bucket; the last 2 land on the Wednesday shift. The bucketing
itself is verified in tag-website/src/test/RosterCalendar.test.jsx — this
file verifies the upstream data the bucketing reads.
"""
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import get_db  # noqa: E402


client = TestClient(app)


# Dates ~5 weeks ahead so the lead-time gate doesn't reject the booking;
# Tue/Wed pair preserves the operational-day semantics under test.
TUE = date(2026, 6, 23)
WED = date(2026, 6, 24)


# =============================================================================
# Mocks — DB session no-op + Stripe stubbed so the endpoint can run end-to-end
# without touching prod resources.
# =============================================================================

class _MockSession:
    def query(self, model): return self
    def filter(self, *a, **k): return self
    def options(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def first(self): return None
    def all(self): return []
    def add(self, obj): pass
    def flush(self): pass
    def commit(self): pass
    def refresh(self, obj): pass
    def rollback(self): pass
    def close(self): pass
    def execute(self, *a, **k): return MagicMock()


def _mock_db_dep():
    db = _MockSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def captured_booking():
    """Capture the kwargs passed to db_service.create_full_booking.

    create_payment routes to create_full_booking when no customer_id
    is in the request — i.e., the public new-customer path the website
    uses for every customer who isn't already in the DB.
    """
    app.dependency_overrides[get_db] = _mock_db_dep

    capture = {}

    def _capture(*args, **kwargs):
        capture.update(kwargs)
        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.reference = "TAG-TEST00001"
        mock_customer = MagicMock()
        mock_customer.id = 1
        # create_full_booking returns {customer, vehicle, booking, payment}
        return {
            "customer": mock_customer,
            "vehicle": MagicMock(id=1),
            "booking": mock_booking,
            "payment": None,
        }

    mock_intent = MagicMock()
    mock_intent.client_secret = "pi_test_secret"
    mock_intent.payment_intent_id = "pi_test"
    mock_intent.amount = 8500
    mock_intent.currency = "gbp"
    mock_intent.status = "requires_payment_method"

    default_pricing = {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 8.0,
        "tier_increment": 5.0,
        "peak_day_increment": 0.0,
    }

    with patch("booking_service.get_pricing_from_db", return_value=default_pricing), \
         patch("main.is_stripe_configured", return_value=True), \
         patch("main.create_payment_intent", return_value=mock_intent), \
         patch("main.db_service.create_full_booking", side_effect=_capture), \
         patch("main.get_settings") as mock_settings:
        mock_settings.return_value.stripe_publishable_key = "pk_test"
        yield capture

    app.dependency_overrides.clear()


def _payload(*, pickup_date_in: date, arrival_hhmm: str):
    """Mirror what the customer's browser sends for a manual-entry return flight.

    Per project memory: customers can only enter flight details manually
    (no flight picker), so pickup_manual_entry is True on every customer
    booking. arrival_id stays None (no link to flights table).
    """
    drop_off = pickup_date_in - timedelta(days=7)
    return {
        "first_name": "Test",
        "last_name": "Rollover",
        "email": "test@example.com",
        "phone": "+447000000000",
        "billing_address1": "1 Test St",
        "billing_city": "Bournemouth",
        "billing_postcode": "BH1 1AA",
        "billing_country": "United Kingdom",
        "registration": "AB12CDE",
        "make": "Ford",
        "colour": "Blue",
        "package": "quick",
        "flight_number": "LS3649",
        "flight_date": drop_off.isoformat(),
        "drop_off_date": drop_off.isoformat(),
        "pickup_date": pickup_date_in.isoformat(),
        "drop_off_slot": "120",
        "pickup_flight_time": arrival_hhmm,
        "flight_arrival_time": arrival_hhmm,
        "pickup_manual_entry": True,
        "pickup_airline_code": "LS",
        "pickup_airline_name": "Jet2",
        "pickup_origin_code": "TFS",
        "pickup_origin_name": "Tenerife, ES",
    }


# =============================================================================
# Test matrix
# =============================================================================

CASES = [
    # (arrival_date, arrival_hhmm, expected_pickup_date, expected_pickup_hhmm, label)
    (TUE, "23:29", TUE, "23:59", "23:29 Tue → 23:59 Tue (no roll)"),
    (TUE, "23:30", WED, "00:00", "23:30 Tue → 00:00 Wed (rollover)"),
    (TUE, "23:31", WED, "00:01", "23:31 Tue → 00:01 Wed (rollover)"),
    (TUE, "23:59", WED, "00:29", "23:59 Tue → 00:29 Wed (rollover)"),
    (WED, "00:00", WED, "00:30", "00:00 Wed → 00:30 Wed (no roll)"),
    (WED, "00:01", WED, "00:31", "00:01 Wed → 00:31 Wed"),
    (WED, "01:58", WED, "02:28", "01:58 Wed → 02:28 Wed"),
    (WED, "01:59", WED, "02:29", "01:59 Wed → 02:29 Wed"),
    (WED, "02:00", WED, "02:30", "02:00 Wed → 02:30 Wed"),
    (WED, "02:01", WED, "02:31", "02:01 Wed → 02:31 Wed"),
]


@pytest.mark.parametrize(
    "arrival_date,arrival_hhmm,exp_pickup_date,exp_pickup_hhmm,label",
    CASES,
    ids=[c[4] for c in CASES],
)
def test_create_intent_stores_correct_pickup_date_for_arrival(
    captured_booking,
    arrival_date,
    arrival_hhmm,
    exp_pickup_date,
    exp_pickup_hhmm,
    label,
):
    """The booking row stored after create-intent must match the +30 rule.

    A wrong pickup_date here is the root cause of the late-night shift
    landing on the wrong calendar day — the front-end calendar's 02:30
    re-bucket then compounds the error.
    """
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(pickup_date_in=arrival_date, arrival_hhmm=arrival_hhmm),
    )

    assert response.status_code == 200, f"{label}: {response.text}"
    assert captured_booking, f"{label}: create_full_booking was never called"

    got_pickup_date = captured_booking["pickup_date"]
    got_pickup_time = captured_booking["pickup_time"]
    got_pickup_hhmm = got_pickup_time.strftime("%H:%M") if got_pickup_time else None

    assert got_pickup_date == exp_pickup_date, (
        f"{label}: pickup_date got {got_pickup_date}, expected {exp_pickup_date} "
        f"(arrival {arrival_hhmm} on {arrival_date})"
    )
    assert got_pickup_hhmm == exp_pickup_hhmm, (
        f"{label}: pickup_time got {got_pickup_hhmm}, expected {exp_pickup_hhmm}"
    )


# =============================================================================
# Regression lock-in: the field-shape that produced the production bug
#
# Bug observed 2026-05-19: 20 manual-entry bookings (TAG-TPI05272 "Lynn"
# included) stored flight_arrival_time correctly but pickup_date un-rolled.
# Root cause: the rollover was gated on request.pickup_flight_time only,
# so requests that sent only flight_arrival_time skipped the date roll.
#
# Fix: rollover now anchors on flight_arrival_time (canonical input — pickup
# is a pure calculation off arrival), with pickup_flight_time as a legacy
# fallback. These tests pin both shapes to the rolled result.
# =============================================================================


@pytest.mark.parametrize(
    "arrival_hhmm,exp_pickup_date,exp_pickup_hhmm",
    [
        ("23:30", WED, "00:00"),
        ("23:59", WED, "00:29"),
        ("23:29", TUE, "23:59"),
    ],
    ids=["23:30 rolls", "23:59 rolls", "23:29 does not roll"],
)
def test_arrival_only_field_still_rolls_pickup_date(
    captured_booking, arrival_hhmm, exp_pickup_date, exp_pickup_hhmm
):
    """Request with only flight_arrival_time (no pickup_flight_time) must
    still roll pickup_date past midnight. Locks in the 2026-05-19 fix."""
    payload = _payload(pickup_date_in=TUE, arrival_hhmm=arrival_hhmm)
    payload.pop("pickup_flight_time", None)

    response = client.post("/api/payments/create-intent", json=payload)
    assert response.status_code == 200, response.text

    assert captured_booking["flight_arrival_time"].strftime("%H:%M") == arrival_hhmm
    assert captured_booking["pickup_date"] == exp_pickup_date
    assert captured_booking["pickup_time"].strftime("%H:%M") == exp_pickup_hhmm
