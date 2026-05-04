"""
Tests for the 02:00 early-arrival billing cutoff.

Rule:
    If the flight ARRIVAL time is before 02:00, the pickup is billed as
    occurring on the previous calendar day. The rule keys off the arrival
    time, NOT the customer-meet time (which is arrival + PICKUP_OFFSET_MINUTES
    and can wrap past midnight even for late-evening arrivals).

    A 7-night trip that lands at 00:50 (meet 01:20) bills as 7 days, not 8.
    A 7-night trip that lands at 23:59 (meet 00:29) bills as 7 days — the
    meet wrapping past midnight is irrelevant; only the arrival time matters.

Coverage matrix:
- Pure unit tests for `BookingService.billing_pickup_date` (documents the helper;
  does NOT increase coverage on its own).
- Mocked integration tests against `/api/pricing/calculate` using
  `TestClient(app)` — the endpoint reverses the +30 offset to recover arrival.
- Mocked integration tests against `/api/payments/create-intent` to confirm
  the rule fires in the actual charge path. That endpoint takes
  `pickup_flight_time` (= arrival HH:MM) directly.
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
# Now keyed off ARRIVAL time, not meet time.
# =============================================================================

class TestBillingPickupDateHelper:
    """Pure unit tests for the helper. Documents the rule precisely."""

    def test_happy_arrival_before_cutoff_shifts_back_one_day(self):
        """Arrival 00:50 → bills as previous day (the canonical early-morning case)."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "00:50")
        assert result == date(2026, 5, 18)

    def test_happy_arrival_after_cutoff_unchanged(self):
        """Midday arrival → no shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "12:00")
        assert result == date(2026, 5, 19)

    def test_boundary_exactly_0200_unchanged(self):
        """02:00 is the boundary — arrivals AT 02:00 do NOT shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "02:00")
        assert result == date(2026, 5, 19)

    def test_boundary_0159_shifts_back(self):
        """01:59 — one minute before the boundary — DOES shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "01:59")
        assert result == date(2026, 5, 18)

    def test_boundary_midnight_arrival_shifts_back(self):
        """00:00 arrival — firmly inside the early-morning window."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "00:00")
        assert result == date(2026, 5, 18)

    def test_late_evening_arrival_2330_does_not_shift(self):
        """REGRESSION: 23:30 arrival (meet wraps to 00:00) must NOT shift.
        This is the TAG-YLB18744 bug — keying off pickup_time saw 00:00 and
        rolled back; keying off arrival sees 23:30 and leaves billing alone."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "23:30")
        assert result == date(2026, 5, 19)

    def test_late_evening_arrival_2359_does_not_shift(self):
        """REGRESSION: 23:59 arrival (meet 00:29) must NOT shift."""
        result = BookingService.billing_pickup_date(date(2026, 5, 19), "23:59")
        assert result == date(2026, 5, 19)

    def test_edge_no_arrival_time_unchanged(self):
        """No arrival time supplied → no adjustment (safe fallback)."""
        assert BookingService.billing_pickup_date(date(2026, 5, 19), None) == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "") == date(2026, 5, 19)

    def test_unhappy_malformed_arrival_time_unchanged(self):
        """Malformed input → no adjustment, no exception."""
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "not-a-time") == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "25:99") == date(2026, 5, 19)
        assert BookingService.billing_pickup_date(date(2026, 5, 19), "12") == date(2026, 5, 19)

    def test_edge_month_boundary_shifts_to_previous_month(self):
        """Arrival 00:01 on 1 March → bills as 28 Feb."""
        result = BookingService.billing_pickup_date(date(2027, 3, 1), "00:01")
        assert result == date(2027, 2, 28)

    def test_edge_year_boundary_shifts_to_previous_year(self):
        """Arrival 00:30 on 1 January → bills as 31 December previous year."""
        result = BookingService.billing_pickup_date(date(2027, 1, 1), "00:30")
        assert result == date(2026, 12, 31)


class TestBillingPickupDateUserBoundaries:
    """The three boundary scenarios A/B/C the user laid out (2026-05-04).

    For all three the customer's drop-off is on the 1st, calendar pickup is on
    the 8th, and the trip is conceptually 7 days. The system must bill as the 7th
    in each case so the price stays at the 1-week rate.
    """

    DROP_OFF = date(2026, 5, 1)
    CALENDAR_PICKUP = date(2026, 5, 8)

    def test_scenario_a_late_evening_2359_no_shift(self):
        """A: arrival 23:59 on the 7th, meet 00:29 on the 8th. Customer enters
        pickup_date = 7th (= arrival date). Bills calendar 7th — no rollback."""
        arrival_date = date(2026, 5, 7)
        result = BookingService.billing_pickup_date(arrival_date, "23:59")
        assert result == date(2026, 5, 7)
        assert (result - self.DROP_OFF).days == 6  # 1st → 7th = 6 nights

    def test_scenario_b_midnight_arrival_shifts(self):
        """B: arrival 00:00 on the 8th, meet 00:30 on the 8th. Bills 7th."""
        result = BookingService.billing_pickup_date(self.CALENDAR_PICKUP, "00:00")
        assert result == date(2026, 5, 7)

    def test_scenario_c_early_morning_0050_shifts(self):
        """C: arrival 00:50 on the 8th, meet 01:20 on the 8th. Bills 7th."""
        result = BookingService.billing_pickup_date(self.CALENDAR_PICKUP, "00:50")
        assert result == date(2026, 5, 7)


# =============================================================================
# Mocked integration tests — /api/pricing/calculate
# The endpoint takes `pickup_time` (customer-meet time) and reverses the
# +30-min offset to recover arrival before applying the rule.
# =============================================================================

def _early_drop_off():
    """A drop-off date >=14 days out so advance_tier is 'early' (£85 1-week base)."""
    return date.today() + timedelta(days=20)


class TestPricingCalculateWithEarlyArrival:
    """Happy path: pickup_time → arrival → rule applied end-to-end."""

    def test_happy_briony_case_calendar_8_billed_as_7(self, mock_db_session):
        """Briony: calendar 8 days, meet 01:20 (arrival 00:50) → bills as 7 days."""
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
        assert data["price"] == 85.0

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

    def test_happy_midday_no_shift(self, mock_db_session):
        """Meet 14:00 (arrival 13:30) → no shift, billed as full 8 days."""
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
    """Boundary tests around the 02:00 arrival cutoff (= 02:30 meet time)."""

    def test_boundary_meet_0230_arrival_0200_no_shift(self, mock_db_session):
        """Meet 02:30 = arrival 02:00 = exact boundary → no shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "02:30",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 8

    def test_boundary_meet_0229_arrival_0159_shifts(self, mock_db_session):
        """Meet 02:29 = arrival 01:59 = one minute inside → shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "02:29",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7


class TestPricingCalculateWrapBand:
    """REGRESSION suite for the TAG-YLB18744 bug class.

    Customer-meet times in [00:00, 00:30) are wrap artifacts of late-evening
    arrivals (23:30–23:59), NOT genuine early-morning pickups. They must
    NOT trigger the rollback.
    """

    def test_meet_0000_arrival_2330_no_shift(self, mock_db_session):
        """Meet 00:00 = arrival 23:30 → no shift, full calendar days."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)  # calendar 7

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:00",
        })

        assert response.status_code == 200
        data = response.json()
        # The actual TAG-YLB18744 case: 7 calendar days → £85, NOT 6 days £83.
        assert data["duration_days"] == 7
        assert data["price"] == 85.0

    def test_meet_0001_arrival_2331_no_shift(self, mock_db_session):
        """Meet 00:01 = arrival 23:31 (just over the wrap) → no shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:01",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7

    def test_meet_0029_arrival_2359_no_shift(self, mock_db_session):
        """Meet 00:29 = arrival 23:59 (latest wrap) → no shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:29",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7

    def test_meet_0030_arrival_0000_shifts(self, mock_db_session):
        """Meet 00:30 = arrival 00:00 (genuine midnight arrival) → shift."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "00:30",
        })

        assert response.status_code == 200
        assert response.json()["duration_days"] == 7  # shifted from 8


class TestPricingCalculateUnhappy:
    """Unhappy paths: malformed pickup_time falls through; out-of-range duration still 400s."""

    def test_unhappy_malformed_pickup_time_falls_back_to_calendar(self, mock_db_session):
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
        """If the shift drops duration below 1, the existing validator rejects."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=1)  # 1-day calendar trip

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
            "pickup_time": "01:00",  # arrival 00:30, would shift to 0 days
        })

        assert response.status_code == 400


# =============================================================================
# Mocked integration tests — /api/payments/create-intent
# This endpoint takes `pickup_flight_time` = arrival HH:MM directly.
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
    mock_intent.amount = 0
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


class TestCreateIntentAppliesArrivalCutoff:
    """The rule must fire in the create-intent path so the actual charge is correct."""

    def test_happy_briony_shape_charges_7_day_price(self, create_intent_setup):
        """Calendar 8 days, arrival 00:50 → 7-day charge (£85)."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="00:50"),
        )

        assert response.status_code == 200
        data = response.json()
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
        assert response.json()["amount"] == 9300

    def test_happy_late_landing_no_shift(self, create_intent_setup):
        """Arrival 14:00 → no shift, 8-day charge."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="14:00"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 9300

    def test_boundary_arrival_0200_no_shift(self, create_intent_setup):
        """Arrival 02:00 = exact boundary → no shift, 8-day price."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="02:00"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 9300

    def test_boundary_arrival_0159_shifts(self, create_intent_setup):
        """Arrival 01:59 = just inside → shift, 7-day price."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=8)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="01:59"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 8500


class TestCreateIntentLateEveningArrivalRegression:
    """REGRESSION suite for TAG-YLB18744: late-evening arrivals must NOT shift.

    Each case is a 7-night trip (calendar 7 days). With the buggy rule, these
    were billing as 6 days (£83). Now they bill as 7 days (£85)."""

    def test_arrival_2330_no_shift(self, create_intent_setup):
        """TAG-YLB18744: arrival 23:30, calendar 7 days → 7-day charge £85."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="23:30"),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 8500
        assert data["amount_display"] == "£85.00"

    def test_arrival_2359_no_shift(self, create_intent_setup):
        """Scenario A: arrival 23:59, calendar 7 days → 7-day charge."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="23:59"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 8500

    def test_arrival_2329_no_shift(self, create_intent_setup):
        """Arrival 23:29 (meet 23:59, no wrap) → 7-day charge.
        Sanity: this case never hit the bug, but adding the boundary."""
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        response = client.post(
            "/api/payments/create-intent",
            json=_create_intent_payload(drop_off, pickup, pickup_flight_time="23:29"),
        )

        assert response.status_code == 200
        assert response.json()["amount"] == 8500


class TestCreateIntentNoCliffAroundWrap:
    """The wrap boundary 23:29 / 23:30 / 23:31 must produce identical billing.

    Under the buggy rule, a 2-minute change at the wrap created a £2 cliff
    because the rule was keyed off meet time (23:59 vs 00:00 vs 00:01).
    Same calendar reality, three identical bills."""

    def test_arrival_2329_2330_2331_all_charge_same(self, create_intent_setup):
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        amounts = []
        for arrival in ("23:29", "23:30", "23:31"):
            response = client.post(
                "/api/payments/create-intent",
                json=_create_intent_payload(drop_off, pickup, pickup_flight_time=arrival),
            )
            assert response.status_code == 200, f"arrival {arrival} failed"
            amounts.append(response.json()["amount"])

        # All three must be the same (and equal to the 7-day price).
        assert amounts == [8500, 8500, 8500], (
            f"Cliff at the wrap boundary — got {amounts} for arrivals "
            f"23:29/23:30/23:31; the rule should be keyed off arrival time, "
            f"not meet time."
        )


class TestPricingCalculateNoCliffAroundWrap:
    """Same wrap-boundary regression check for /api/pricing/calculate.

    Note: this endpoint receives meet time (= arrival + 30), so we feed
    23:59/00:00/00:01 here to represent the same arrivals 23:29/23:30/23:31."""

    def test_meet_2359_0000_0001_all_quote_same(self, mock_db_session):
        drop_off = _early_drop_off()
        pickup = drop_off + timedelta(days=7)

        durations = []
        prices = []
        for meet in ("23:59", "00:00", "00:01"):
            response = client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off.isoformat(),
                "pickup_date": pickup.isoformat(),
                "pickup_time": meet,
            })
            assert response.status_code == 200, f"meet {meet} failed"
            data = response.json()
            durations.append(data["duration_days"])
            prices.append(data["price"])

        assert durations == [7, 7, 7], (
            f"Cliff at the wrap boundary — got durations {durations} for "
            f"meets 23:59/00:00/00:01."
        )
        assert prices == [85.0, 85.0, 85.0]
