"""
Mocked-integration tests for the booking lead-time rule (locked 2026-05-12).

Replaces the old 4-hour-notice tests now that the rule is:
  - Same-day drop-offs are blocked outright.
  - Bookings placed past 20:00 UK can't have a drop-off the next day.
    "Past 20:00" means now_uk_minutes > 20*60, so 20:00:00..20:00:59 still
    allow tomorrow's drop-off; 20:01:00 onwards blocks it.

Admin manual booking (/api/admin/bookings) is exempt — only the customer
payment-intent endpoint enforces this gate.

H/U/E/B per SPEC. TestClient-based so it exercises main.py and counts
toward coverage.
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_stripe():
    """Mock Stripe so the test never hits the network. Bookings that pass
    the lead-time gate may still 4xx for unrelated reasons further down
    the handler (we only assert on the lead-time path)."""
    with patch('main.create_payment_intent') as mock_create, \
         patch('main.is_stripe_configured', return_value=True), \
         patch('main.get_settings') as mock_settings:
        mock_settings.return_value.stripe_publishable_key = 'pk_test_xxx'
        mock_create.return_value = MagicMock(
            id='pi_test_123',
            client_secret='pi_test_123_secret_xxx',
        )
        yield mock_create


@pytest.fixture
def base_booking_request():
    """Booking-intent body. drop_off_date / flight_date / pickup_date are
    set per-test to exercise the lead-time gate."""
    return {
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "phone": "07777777777",
        "drop_off_date": None,
        "drop_off_slot": "120",
        "flight_date": None,
        "flight_departure_time": "14:00",
        "flight_number": "FR123",
        "dropoff_airline_code": "FR",
        "dropoff_airline_name": "Ryanair",
        "dropoff_destination_code": "AGP",
        "dropoff_destination_name": "Malaga",
        "pickup_date": None,
        "flight_arrival_time": "16:00",
        "pickup_flight_number": "FR124",
        "registration": "AB12CDE",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "package": "quick",
        "billing_address1": "123 Test Street",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "billing_country": "United Kingdom",
        "session_id": None,
    }


def _make(request, *, dropoff_date, pickup_date=None, slot="120", flight_time="14:00",
          session_id_suffix="x"):
    """Fill the booking request with a target drop-off / pick-up date."""
    r = request.copy()
    r["drop_off_date"] = dropoff_date.isoformat()
    r["flight_date"] = dropoff_date.isoformat()
    r["pickup_date"] = (pickup_date or (dropoff_date + timedelta(days=3))).isoformat()
    r["drop_off_slot"] = slot
    r["flight_departure_time"] = flight_time
    r["session_id"] = f"test_{session_id_suffix}_{datetime.now().timestamp()}"
    return r


# ---------------------------------------------------------------------------
# Happy path — drop-off far enough ahead clears the gate
# ---------------------------------------------------------------------------

class TestLeadTimeHappy:

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_happy_tomorrow_before_2000_allowed(self, client, mock_stripe, base_booking_request):
        """At 10:00 UK, tomorrow's drop-off should clear the lead-time gate."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="tomorrow_before_2000"),
        )
        if response.status_code == 400:
            assert "same-day" not in response.json().get("detail", "").lower()
            assert "after 20:00" not in response.json().get("detail", "")

    @freeze_time("2026-03-17 19:59:59", tz_offset=0)
    def test_happy_tomorrow_at_1959_allowed(self, client, mock_stripe, base_booking_request):
        """One second before the 20:00 boundary still allows tomorrow."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="tomorrow_1959"),
        )
        if response.status_code == 400:
            assert "after 20:00" not in response.json().get("detail", "")

    @freeze_time("2026-03-17 23:30:00", tz_offset=0)
    def test_happy_day_after_tomorrow_always_allowed_even_late_at_night(
        self, client, mock_stripe, base_booking_request,
    ):
        """Day-after-tomorrow is unaffected by the 20:00 cutoff."""
        d = date(2026, 3, 19)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=d,
                       session_id_suffix="day_after"),
        )
        if response.status_code == 400:
            detail = response.json().get("detail", "")
            assert "same-day" not in detail.lower()
            assert "after 20:00" not in detail


# ---------------------------------------------------------------------------
# Unhappy — gated cases return 400 with the new copy
# ---------------------------------------------------------------------------

class TestLeadTimeUnhappy:

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_unhappy_same_day_rejected(self, client, mock_stripe, base_booking_request):
        """Today's drop-off is blocked outright, regardless of how many
        hours' notice the customer claims to be giving."""
        today = date(2026, 3, 17)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=today,
                       session_id_suffix="same_day"),
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "same-day" in detail.lower()
        assert "01202 798710" in detail

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_unhappy_past_date_rejected(self, client, mock_stripe, base_booking_request):
        """A drop-off date in the past gets the same same-day error path."""
        yesterday = date(2026, 3, 16)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=yesterday,
                       session_id_suffix="past_date"),
        )
        assert response.status_code == 400
        assert "same-day" in response.json()["detail"].lower()

    @freeze_time("2026-03-17 20:01:00", tz_offset=0)
    def test_unhappy_tomorrow_at_2001_rejected(self, client, mock_stripe, base_booking_request):
        """One second past the 20:00 boundary blocks tomorrow's drop-off."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="tomorrow_2001"),
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "after 20:00" in detail
        assert "01202 798710" in detail

    @freeze_time("2026-03-17 23:30:00", tz_offset=0)
    def test_unhappy_tomorrow_late_evening_rejected(
        self, client, mock_stripe, base_booking_request,
    ):
        """Anywhere past 20:00 — including 23:30 — blocks tomorrow."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="tomorrow_2330"),
        )
        assert response.status_code == 400
        assert "after 20:00" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Edge — the same-day error message wording is locked
# ---------------------------------------------------------------------------

class TestLeadTimeEdgeMessages:

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_edge_same_day_message_points_to_phone(self, client, mock_stripe, base_booking_request):
        """The customer can't move the date (their flight is fixed), so the
        error must route them to the phone number, not 'pick a later date'."""
        today = date(2026, 3, 17)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=today,
                       session_id_suffix="same_day_phone"),
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "01202 798710" in detail
        assert "pick a later" not in detail.lower()
        assert "try a later" not in detail.lower()

    @freeze_time("2026-03-17 21:00:00", tz_offset=0)
    def test_edge_after_2000_message_points_to_phone(
        self, client, mock_stripe, base_booking_request,
    ):
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="after_2000_phone"),
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "01202 798710" in detail
        assert "pick a later" not in detail.lower()
        assert "try a later" not in detail.lower()


# ---------------------------------------------------------------------------
# Boundary — exactly-on-20:00 and adjacent seconds
# ---------------------------------------------------------------------------

class TestLeadTimeBoundary:

    @freeze_time("2026-03-17 20:00:00", tz_offset=0)
    def test_boundary_tomorrow_at_exactly_2000_still_allowed(
        self, client, mock_stripe, base_booking_request,
    ):
        """The cutoff is > 20*60 minutes, so 20:00 itself (1200 == 1200) is
        the last accepted minute."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="boundary_2000"),
        )
        if response.status_code == 400:
            assert "after 20:00" not in response.json().get("detail", "")

    @freeze_time("2026-03-17 20:00:59", tz_offset=0)
    def test_boundary_tomorrow_at_2000_59_still_allowed(
        self, client, mock_stripe, base_booking_request,
    ):
        """The check truncates to whole minutes, so 20:00:59 is still 20:00."""
        tomorrow = date(2026, 3, 18)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=tomorrow,
                       session_id_suffix="boundary_2000_59"),
        )
        if response.status_code == 400:
            assert "after 20:00" not in response.json().get("detail", "")

    @freeze_time("2026-03-17 00:00:00", tz_offset=0)
    def test_boundary_midnight_same_day_still_blocked(
        self, client, mock_stripe, base_booking_request,
    ):
        """At 00:00 the customer might think 'plenty of notice' — but
        same-day is blocked regardless."""
        today = date(2026, 3, 17)
        response = client.post(
            "/api/payments/create-intent",
            json=_make(base_booking_request, dropoff_date=today,
                       session_id_suffix="midnight_same_day"),
        )
        assert response.status_code == 400
        assert "same-day" in response.json()["detail"].lower()
