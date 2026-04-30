"""
Tests for the 02:30 early-pickup cutoff billing rule.

Rule (SPEC.md lock 2026-04-30):
    If the customer-meet (collection) time is before 02:30, the pickup is
    billed as occurring on the previous calendar day. A 7-night trip that
    lands at e.g. 00:50 on the 8th calendar day is billed as 7 days, not 8.

Coverage matrix (per backend/docs/SPEC.md):
- Pure unit tests for `BookingService.billing_pickup_date` (documents the helper;
  does NOT increase coverage on its own).
- Mocked integration tests against `/api/pricing/calculate` using
  `TestClient(app)` (these DO increase coverage).
- Mocked integration tests against `/api/payments/create-intent` to confirm
  the rule fires in the actual charge path.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from booking_service import BookingService
from database import get_db

client = TestClient(app)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default anchor pricing (matches test_anchor_pricing_integration.py)."""
    return {
        "days_1_4_price": 65.0,
        "week1_base_price": 85.0,
        "week2_base_price": 150.0,
        "daily_increment": 8.0,
        "tier_increment": 5.0,
        "peak_day_increment": 0.0,
    }


@pytest.fixture
def mock_db_session(default_pricing):
    with patch('booking_service.get_pricing_from_db', return_value=default_pricing):
        yield default_pricing


# =============================================================================
# Pure unit tests — BookingService.billing_pickup_date
# =============================================================================

class TestBillingPickupDateHelper:
    """Pure unit tests for the helper. Documents the rule precisely."""

    def test_happy_pickup_before_cutoff_shifts_back_one_day(self):
        """Briony's case — collection 01:20 on 19 May → bills as 18 May."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "01:20")
        assert result == date(2026, 5, 18)

    def test_happy_pickup_after_cutoff_unchanged(self):
        """Midday pickup → no shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "12:00")
        assert result == date(2026, 5, 19)

    def test_boundary_exactly_0230_unchanged(self):
        """02:30 is the inclusive boundary — does NOT shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "02:30")
        assert result == date(2026, 5, 19)

    def test_boundary_0229_shifts_back(self):
        """02:29 is one minute before the boundary — DOES shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "02:29")
        assert result == date(2026, 5, 18)

    def test_boundary_midnight_shifts_back(self):
        """00:00 is firmly inside the early-morning window."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "00:00")
        assert result == date(2026, 5, 18)

    def test_edge_no_pickup_time_unchanged(self):
        """No collection time supplied → no adjustment (safe fallback)."""
        assert BookingService.billing_pickup_date(date(2026, 5, 19), None) == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "") == date(2026, 5, 19)

    def test_unhappy_malformed_pickup_time_unchanged(self):
        """Malformed input → no adjustment, no exception."""
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "not-a-time") == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "25:99") == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "12") == date(2026, 5, 19)

    def test_edge_month_boundary_shifts_to_previous_month(self):
        """Scenario B-shape: pickup 00:31 on 1 March → bills as 28 Feb."""
        result = BookingService.billing_pickup_date(date(2027, 3, 1), "00:31")
        assert result == date(2027, 2, 28)

    def test_edge_year_boundary_shifts_to_previous_year(self):
        """Pickup 01:00 on 1 January → bills as 31 December previous year."""
        result = BookingService.billing_pickup_date(date(2027, 1, 1), "01:00")
        assert result == date(2026, 12, 31)


# =============================================================================
# Mocked integration tests — /api/pricing/calculate
# These hit the real endpoint via TestClient and DO increase coverage.
# =============================================================================

def _early_drop_off():
    """A drop-off date >=14 days out so advance_tier is 'early' (£85 1-week base)."""
    return date.today() + timedelta(days=20)


class TestPricingCalculateWithEarlyPickup:
    """Happy path: pickup_time is forwarded and the rule is applied end-to-end."""

    def test_happy_briony_case_calendar_8_billed_as_7(self, mock_db_session):
        """
        Briony shape: calendar gap of 8 days but pickup at 01:20 falls before
        02:30 → bills as 7 days (£85 early-tier 1-week base).
        """
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "01:20",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 7
        assert data["price"] == 85.0  # 1 week early tier

    def test_happy_no_pickup_time_uses_calendar_days(self, mock_db_session):
        """Backwards compatibility: omitting pickup_time = no shift, calendar days used."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 8

    def test_happy_midday_pickup_no_shift(self, mock_db_session):
        """Pickup at 14:00 → no shift, billed as full 8 days."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "14:00",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 8


class TestPricingCalculateBoundaries:
    """Boundary tests at the 02:30 cutoff."""

    def test_boundary_0230_exact_no_shift(self, mock_db_session):
        """02:30 is inclusive of the daytime side — no shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "02:30",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 8

    def test_boundary_0229_shifts(self, mock_db_session):
        """02:29 → shift back, 7 days."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "02:29",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7

    def test_boundary_midnight_shifts(self, mock_db_session):
        """00:00 is firmly inside the early-morning window."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:00",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7


class TestPricingCalculateScenarioB:
    """Scenario B: arrival 00:01, collection 00:31 on the calendar return date.
    Should shift to previous day."""

    def test_edge_scenario_b_drops_one_day(self, mock_db_session):
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)  # calendar gap = 7

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:31",
        })

        assert response.status_code == 200
        data = response.json()
        # Calendar 7, shifted to 6 days
        assert data["duration_days"] == 6


class TestPricingCalculateUnhappy:
    """Unhappy paths: malformed pickup_time should not crash; out-of-range duration still 400s."""

    def test_unhappy_malformed_pickup_time_falls_back_to_calendar(self, mock_db_session):
        """Garbage pickup_time should be silently ignored (no shift, no 500)."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "not-a-time",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 8

    def test_unhappy_shift_would_yield_zero_days_returns_400(self, mock_db_session):
        """If the shift would drop duration below 1, the existing validator rejects."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=1)  # 1-day calendar trip

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "01:00",  # would shift to 0 days
        })

        # Existing validator rejects duration < 1
        assert response.status_code == 400


# =============================================================================
# Mocked integration tests — /api/payments/create-intent
# Confirms the cutoff fires in the actual charge path, not just price-quote.
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
def create_intent_setup(default_pricing):
    """Set up everything create-intent needs: DB override, Stripe mocks, pricing mock."""
    app.dependency_overrides[get_db] = _mock_db_dep
    mock_intent = MagicMock()
    mock_intent.client_secret = "pi_test_secret_cutoff"
    mock_intent.payment_intent_id = "pi_test_cutoff"
    mock_intent.amount = 0  # overwritten by endpoint, but field must exist
    mock_intent.currency = "gbp"
    mock_intent.status = "requires_payment_method"

    with patch("booking_service.get_pricing_from_db", return_value=default_pricing), \
         patch("main.is_stripe_configured", return_value=True), \
         patch("main.create_payment_intent", return_value=mock_intent), \
         patch("main.get_settings") as mock_settings:
        mock_settings.return_value.stripe_publishable_key = "pk_test_cutoff"
        yield
    app.dependency_overrides.clear()


def _create_intent_payload(drop_off, pickup, *, pickup_flight_time=None):
    return {
        "first_name": "Test",
        "last_name": "Cutoff",
        "email": "cutoff@example.com",
        "billing_address1": "1 Test St",
        "billing_city": "Bournemouth",
        "billing_postcode": "BH1 1AA",
        "billing_country": "United Kingdom",
        "package": "quick",
        "flight_number": "FR1234",
        "flight_date": drop_off.isoformat(),
        "drop_off_date": drop_off.isoformat(),
        "pickup_date": pickup.isoformat(),
        **({"pickup_flight_time": pickup_flight_time} if pickup_flight_time else {}),
    }


class TestCreateIntentApplies0230Cutoff:
    """The rule must fire in the create-intent path so the actual charge is correct."""

    def test_happy_briony_shape_charges_7_day_price(self, create_intent_setup):
        """Calendar 8 days but flight arrives 00:50 → collection 01:20 → 7-day charge."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="00:50"),
        )

        assert response.status_code == 200
        data = response.json()
        # 7 days early-tier base = £85.00 = 8500 pence (per default_pricing fixture)
        assert data["amount"] == 8500
        assert data["amount_display"] == "£85.00"

    def test_happy_no_pickup_flight_time_uses_calendar_days(self, create_intent_setup):
        """Without pickup_flight_time, behave as before (calendar 8 days = 8-day price)."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup),
        )

        assert response.status_code == 200
        data = response.json()
        # 8 days early-tier = 85 + 8 daily_increment = £93.00 = 9300 pence
        assert data["amount"] == 9300

    def test_happy_late_landing_no_shift(self, create_intent_setup):
        """Flight arrives 14:00 → collection 14:30 → 8-day charge unchanged."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="14:00"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 9300  # 8 days, no shift

    def test_boundary_arrival_0200_collection_0230_no_shift(self, create_intent_setup):
        """Arrival 02:00 → collection 02:30 (exactly the cutoff) → no shift, 8-day price."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="02:00"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 9300  # 8 days

    def test_boundary_arrival_0159_collection_0229_shifts(self, create_intent_setup):
        """Arrival 01:59 → collection 02:29 (just before cutoff) → shift, 7-day price."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="01:59"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 8500  # 7 days early tier
