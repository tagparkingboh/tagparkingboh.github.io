"""
Mocked-integration tests for the `flight_arrival_date` column on bookings.

`flight_arrival_date` is the canonical landing date for the return flight,
captured BEFORE the +30-minute overnight rollover at create_payment mutates
`pickup_date` for arrivals after 23:30 UK. Storing it gives audits a reliable
"already rolled vs. needs rolling" signal — which was missing during both the
2026-05-19 rollover bug and the 2026-05-20 over-correction.

H/U/E/B coverage:
  Happy    — payload sends `flight_arrival_date` and it's stored verbatim
  Unhappy  — malformed `flight_arrival_date` → backend returns 400
  Edge     — payload omits the field; backend falls back to `pickup_date`
  Boundary — full 10-point arrival-time grid (23:29 .. 02:01) asserts
             `flight_arrival_date` stays on the customer's landing day even
             when `pickup_date` rolls past midnight.

Pure-unit-test discipline (per the 2026-04-21 SPEC lesson) is honoured by
using `TestClient(app)` and importing from `main`, so these execute the real
endpoint and count for coverage.
"""
import json
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


# Pair landing-date + day-after, well past the same-day-booking gate.
TUE = date(2026, 6, 23)
WED = date(2026, 6, 24)


# =============================================================================
# Mocks — DB session no-op + Stripe stubbed so the endpoint runs without
# touching prod resources. Mirrors test_pickup_date_rollover.py.
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
def captured():
    """Capture the kwargs `db_service.create_full_booking` and the audit
    event are called with. The endpoint hits both, so a single fixture can
    assert the persisted column AND the audit payload from one request.
    """
    app.dependency_overrides[get_db] = _mock_db_dep

    capture = {"booking_kwargs": {}, "audit_event_data": None}

    def _capture_booking(*args, **kwargs):
        capture["booking_kwargs"].update(kwargs)
        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.reference = "TAG-TEST00001"
        return {
            "customer": MagicMock(id=1),
            "vehicle": MagicMock(id=1),
            "booking": mock_booking,
            "payment": None,
        }

    def _capture_audit(*args, **kwargs):
        if kwargs.get("event_data") is not None:
            capture["audit_event_data"] = kwargs["event_data"]
        return None

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
         patch("main.db_service.create_full_booking", side_effect=_capture_booking), \
         patch("main.log_audit_event", side_effect=_capture_audit), \
         patch("main.get_settings") as mock_settings:
        mock_settings.return_value.stripe_publishable_key = "pk_test"
        yield capture

    app.dependency_overrides.clear()


def _payload(*, pickup_date_in: date, arrival_hhmm: str, flight_arrival_date: str = None):
    """Mirror what a customer's browser sends for a manual-entry return flight.

    Customers only enter flight details manually (the flight picker is dead
    per `project_manual_booking_system`), so `pickup_manual_entry=True` and
    `arrival_id=None` on every customer payload.

    `flight_arrival_date` is omitted unless explicitly passed — that lets the
    same helper cover the "frontend not yet updated" backward-compat case.
    """
    drop_off = pickup_date_in - timedelta(days=7)
    payload = {
        "first_name": "Test",
        "last_name": "ArrivalDate",
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
    if flight_arrival_date is not None:
        payload["flight_arrival_date"] = flight_arrival_date
    return payload


# =============================================================================
# H — Happy: explicit flight_arrival_date is persisted verbatim
# =============================================================================


def test_happy_explicit_flight_arrival_date_stored_verbatim(captured):
    """When the frontend sends `flight_arrival_date`, the booking row stores
    that exact value — independent of any rollover applied to pickup_date."""
    # Late arrival on Tuesday → pickup_date rolls to Wednesday, but the
    # arrival date the customer landed on is still Tuesday.
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(
            pickup_date_in=TUE,
            arrival_hhmm="23:30",
            flight_arrival_date=TUE.isoformat(),
        ),
    )

    assert response.status_code == 200, response.text
    assert captured["booking_kwargs"], "create_full_booking was never called"
    assert captured["booking_kwargs"]["flight_arrival_date"] == TUE
    # Verify the rollover still moved pickup_date — flight_arrival_date is
    # a separate concern.
    assert captured["booking_kwargs"]["pickup_date"] == WED


# =============================================================================
# U — Unhappy: malformed flight_arrival_date string → 400
# =============================================================================


def test_unhappy_malformed_flight_arrival_date_rejects(captured):
    """A non-`YYYY-MM-DD` string fails the strptime parse and the endpoint
    surfaces a 400 rather than silently writing a bad row."""
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(
            pickup_date_in=TUE,
            arrival_hhmm="14:00",
            flight_arrival_date="not-a-date",
        ),
    )
    assert response.status_code == 400, response.text
    assert captured["booking_kwargs"] == {}


# =============================================================================
# E — Edge: omitted flight_arrival_date falls back to pickup_date (pre-roll)
# =============================================================================


def test_edge_omitted_field_falls_back_to_pickup_date(captured):
    """A frontend that hasn't been updated yet sends no `flight_arrival_date`.
    The backend must fall back to the (un-rolled) pickup_date so old payloads
    keep working through the rollout."""
    # Day-time arrival → no rollover, so pickup_date == landing date.
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(pickup_date_in=TUE, arrival_hhmm="14:00"),
    )
    assert response.status_code == 200, response.text
    assert captured["booking_kwargs"]["flight_arrival_date"] == TUE


def test_edge_omitted_field_anchors_on_unrolled_date_for_overnight(captured):
    """Even when the rollover fires (23:30 → pickup_date+1), the legacy
    fallback must record the LANDING date, not the rolled pickup date.
    Otherwise the new column would inherit the same conflation it was
    designed to remove."""
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(pickup_date_in=TUE, arrival_hhmm="23:30"),
    )
    assert response.status_code == 200, response.text
    # pickup_date rolled forward …
    assert captured["booking_kwargs"]["pickup_date"] == WED
    # … but the canonical arrival date stays on Tuesday.
    assert captured["booking_kwargs"]["flight_arrival_date"] == TUE


# =============================================================================
# B — Boundary: the 10-point arrival-time grid
#
# Same grid as test_pickup_date_rollover.py, but asserting on
# flight_arrival_date (the un-rolled landing day). Every case here has the
# customer's pickup_date input set to the *landing* day; the expected
# flight_arrival_date is exactly that day, regardless of whether the
# +30-minute rollover then bumps pickup_date forward.
# =============================================================================

BOUNDARY_CASES = [
    # (pickup_date_in, arrival_hhmm, expected_flight_arrival_date, label)
    (TUE, "23:29", TUE, "23:29 Tue — no roll, arrival=Tue"),
    (TUE, "23:30", TUE, "23:30 Tue — rollover fires, arrival stays Tue"),
    (TUE, "23:31", TUE, "23:31 Tue — rollover fires, arrival stays Tue"),
    (TUE, "23:59", TUE, "23:59 Tue — rollover fires, arrival stays Tue"),
    (WED, "00:00", WED, "00:00 Wed — landed on Wed, no roll"),
    (WED, "00:01", WED, "00:01 Wed — landed on Wed"),
    (WED, "01:58", WED, "01:58 Wed — landed on Wed"),
    (WED, "01:59", WED, "01:59 Wed — landed on Wed"),
    (WED, "02:00", WED, "02:00 Wed — landed on Wed"),
    (WED, "02:01", WED, "02:01 Wed — landed on Wed"),
]


@pytest.mark.parametrize(
    "pickup_date_in,arrival_hhmm,expected_arrival_date,label",
    BOUNDARY_CASES,
    ids=[c[3] for c in BOUNDARY_CASES],
)
def test_boundary_flight_arrival_date_is_landing_date(
    captured, pickup_date_in, arrival_hhmm, expected_arrival_date, label
):
    """For every arrival-time boundary the operator cares about, the stored
    `flight_arrival_date` is the customer's landing day — never the rolled
    pickup day. This is the regression fence against the 2026-05-19 /
    2026-05-20 conflation reappearing under a new name."""
    # Frontend will start sending flight_arrival_date explicitly; assert that
    # round-trips through the backend untouched.
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(
            pickup_date_in=pickup_date_in,
            arrival_hhmm=arrival_hhmm,
            flight_arrival_date=expected_arrival_date.isoformat(),
        ),
    )
    assert response.status_code == 200, f"{label}: {response.text}"
    got = captured["booking_kwargs"].get("flight_arrival_date")
    assert got == expected_arrival_date, (
        f"{label}: stored flight_arrival_date={got}, expected={expected_arrival_date}"
    )


# =============================================================================
# Audit payload expansion (2026-05-19 mistakes-log lesson #3)
#
# The original payment_initiated event captured only a curated subset of
# request fields, which made the rollover bug undiagnosable from logs alone.
# These tests pin the full arrival/pickup time field set into event_data so a
# future regression is reproducible from a single audit row.
# =============================================================================


def test_audit_payload_includes_full_arrival_pickup_field_set(captured):
    """The payment_initiated audit event must carry every arrival/pickup
    time field on the incoming request so future bugs of the 2026-05-19
    shape can be diagnosed from the audit log alone."""
    payload = _payload(
        pickup_date_in=TUE,
        arrival_hhmm="23:30",
        flight_arrival_date=TUE.isoformat(),
    )
    # Populate the optional override fields so we can assert they're captured.
    payload["pickup_customer_time"] = "23:25"
    payload["dropoff_customer_time"] = "11:00"

    response = client.post("/api/payments/create-intent", json=payload)
    assert response.status_code == 200, response.text

    event_data = captured["audit_event_data"]
    assert event_data is not None, "payment_initiated audit was not logged"

    for field in (
        "flight_arrival_date",
        "flight_arrival_time",
        "pickup_flight_time",
        "pickup_date",
        "pickup_customer_time",
        "dropoff_customer_time",
    ):
        assert field in event_data, f"audit event_data missing {field}"

    assert event_data["flight_arrival_date"] == TUE.isoformat()
    assert event_data["flight_arrival_time"] == "23:30"
    assert event_data["pickup_flight_time"] == "23:30"
    assert event_data["pickup_customer_time"] == "23:25"
    assert event_data["dropoff_customer_time"] == "11:00"


def test_audit_payload_nulls_propagate_when_field_omitted(captured):
    """When the customer didn't override a time, the audit row records
    `null` for that key (rather than dropping it). Keeping the key present
    means a SQL query that pulls audit logs by event_data->>'flight_arrival_date'
    behaves consistently across payloads."""
    response = client.post(
        "/api/payments/create-intent",
        json=_payload(pickup_date_in=TUE, arrival_hhmm="14:00"),
    )
    assert response.status_code == 200, response.text
    event_data = captured["audit_event_data"]
    assert event_data is not None
    # Omitted on the request → present as None in the audit row.
    assert event_data.get("flight_arrival_date", "missing") is None
    assert event_data.get("pickup_customer_time", "missing") is None
    assert event_data.get("dropoff_customer_time", "missing") is None


# =============================================================================
# Pure-unit (MagicMock-only) coverage of the ORM model presence
#
# These don't count for main.py coverage per SPEC.md but pin the schema
# alignment between the Python model and the migration so a future
# `Booking(...)` instantiation that misses the column would fail loudly.
# =============================================================================


def test_unit_booking_model_has_flight_arrival_date_column():
    """ORM model exposes the column. Cheap insurance that any future column
    rename / drop will surface in CI before it reaches a deploy."""
    from db_models import Booking
    assert "flight_arrival_date" in Booking.__table__.columns, (
        "Booking.flight_arrival_date column missing — did the migration get reverted?"
    )
    col = Booking.__table__.columns["flight_arrival_date"]
    assert col.nullable is True, "flight_arrival_date must stay nullable for legacy-row compatibility"
