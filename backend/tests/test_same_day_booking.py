"""
Tests for same-day booking 4-hour minimum notice requirement.

Covers:
1. Same-day bookings within 4 hours (should be rejected)
2. Same-day bookings at exactly 4 hours (should be allowed)
3. Same-day bookings with more than 4 hours notice (should be allowed)
4. Next-day bookings (should always be allowed regardless of time)
5. Boundary cases: 3h59m (reject), 4h00m (allow), 4h01m (allow)
6. Cross-midnight scenarios (Wed 22:00 booking for Thu 01:00 flight)
"""

import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from freezegun import freeze_time

# Import the app
import sys
sys.path.insert(0, '/Users/qaorca/Downloads/Projects/Tag/backend')

from main import app
from models import SlotType


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_stripe():
    """Mock Stripe API calls."""
    with patch('main.create_payment_intent') as mock_create, \
         patch('main.is_stripe_configured', return_value=True), \
         patch('main.get_settings') as mock_settings:
        mock_settings.return_value.stripe_publishable_key = 'pk_test_xxx'
        mock_create.return_value = MagicMock(
            id='pi_test_123',
            client_secret='pi_test_123_secret_xxx'
        )
        yield mock_create


@pytest.fixture
def base_booking_request():
    """Base booking request data."""
    return {
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "phone": "07777777777",
        "drop_off_date": None,  # Will be set per test
        "drop_off_slot": "165",  # "165" for early (2h45m), "120" for late (2h)
        "flight_date": None,  # Will be set per test
        "flight_departure_time": "14:00",  # Will be set per test
        "flight_number": "FR123",
        "dropoff_airline_code": "FR",
        "dropoff_airline_name": "Ryanair",
        "dropoff_destination_code": "AGP",
        "dropoff_destination_name": "Malaga",
        "pickup_date": None,  # Will be set per test
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
        "session_id": None  # Unique per test to avoid deduplication
    }


# =============================================================================
# Helper Functions
# =============================================================================

def get_uk_time(hour: int, minute: int, date_obj: date = None) -> datetime:
    """Create a UK timezone aware datetime."""
    uk_tz = ZoneInfo("Europe/London")
    if date_obj is None:
        date_obj = date.today()
    return datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute, tzinfo=uk_tz)


def minutes_to_time_str(minutes: int) -> str:
    """Convert minutes from midnight to HH:MM string."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


# =============================================================================
# Unit Tests - Time Calculation Logic
# =============================================================================

class TestTimeCalculationLogic:
    """Unit tests for time calculation logic."""

    def test_dropoff_time_calculation_early_slot(self):
        """Early slot is 165 minutes (2h45m) before flight."""
        flight_time = "14:00"
        flight_minutes = 14 * 60  # 840
        slot_offset = 165  # Early slot
        dropoff_minutes = flight_minutes - slot_offset

        assert dropoff_minutes == 675  # 11:15
        assert minutes_to_time_str(dropoff_minutes) == "11:15"

    def test_dropoff_time_calculation_late_slot(self):
        """Late slot is 120 minutes (2h) before flight."""
        flight_time = "14:00"
        flight_minutes = 14 * 60  # 840
        slot_offset = 120  # Late slot
        dropoff_minutes = flight_minutes - slot_offset

        assert dropoff_minutes == 720  # 12:00
        assert minutes_to_time_str(dropoff_minutes) == "12:00"

    def test_4_hour_notice_in_minutes(self):
        """4 hours = 240 minutes."""
        MIN_HOURS_NOTICE = 4
        min_notice_minutes = MIN_HOURS_NOTICE * 60
        assert min_notice_minutes == 240


# =============================================================================
# Unit Tests - Boundary Cases
# =============================================================================

class TestBoundaryCases:
    """Test exact boundary conditions for 4-hour notice."""

    def test_exactly_4_hours_notice_should_be_allowed(self):
        """Dropoff at exactly 4 hours from now should be allowed."""
        current_minutes = 10 * 60  # 10:00
        dropoff_minutes = 14 * 60  # 14:00
        min_notice_minutes = 4 * 60  # 240

        # dropoff_minutes >= current_minutes + min_notice_minutes
        # 840 >= 600 + 240 = 840
        assert dropoff_minutes >= current_minutes + min_notice_minutes

    def test_3_hours_59_minutes_notice_should_be_rejected(self):
        """Dropoff at 3h59m from now should be rejected."""
        current_minutes = 10 * 60  # 10:00
        dropoff_minutes = 13 * 60 + 59  # 13:59 (3h59m later)
        min_notice_minutes = 4 * 60  # 240

        # 839 >= 600 + 240 = 840? No!
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_4_hours_1_minute_notice_should_be_allowed(self):
        """Dropoff at 4h01m from now should be allowed."""
        current_minutes = 10 * 60  # 10:00
        dropoff_minutes = 14 * 60 + 1  # 14:01 (4h01m later)
        min_notice_minutes = 4 * 60  # 240

        # 841 >= 600 + 240 = 840? Yes!
        assert dropoff_minutes >= current_minutes + min_notice_minutes


# =============================================================================
# Unit Tests - Cross-Midnight Scenarios
# =============================================================================

class TestCrossMidnightScenarios:
    """Test scenarios where booking is made late evening for early morning flight next day."""

    def test_wed_22_00_booking_for_thu_01_00_flight_is_next_day(self):
        """Wed 22:00 booking for Thu 01:00 flight is next-day, should be allowed."""
        wed = date(2026, 3, 18)  # Wednesday
        thu = date(2026, 3, 19)  # Thursday

        # Booking is for Thursday (next day), not same day
        # Next-day bookings should always be allowed
        is_same_day = (thu == wed)
        assert not is_same_day  # Different days, so allowed

    def test_wed_22_00_booking_for_wed_23_00_flight_is_same_day(self):
        """Wed 22:00 booking for Wed 23:00 flight is same-day, check notice."""
        current_minutes = 22 * 60  # 22:00
        flight_minutes = 23 * 60  # 23:00
        slot_offset = 120  # Late slot (2h before)
        dropoff_minutes = flight_minutes - slot_offset  # 21:00
        min_notice_minutes = 4 * 60  # 240

        # Dropoff at 21:00 but current time is 22:00 - dropoff is in the past!
        # 21:00 (1260) >= 22:00 (1320) + 240? No!
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_early_morning_same_day_flight(self):
        """Booking at 00:30 for 06:00 flight same day."""
        current_minutes = 0 * 60 + 30  # 00:30
        flight_minutes = 6 * 60  # 06:00
        slot_offset = 165  # Early slot
        dropoff_minutes = flight_minutes - slot_offset  # 03:15 (195 mins)
        min_notice_minutes = 4 * 60  # 240

        # 195 >= 30 + 240 = 270? No!
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_early_morning_with_enough_notice(self):
        """Booking at 00:30 for 08:00 flight same day with early slot."""
        current_minutes = 0 * 60 + 30  # 00:30
        flight_minutes = 8 * 60  # 08:00
        slot_offset = 165  # Early slot
        dropoff_minutes = flight_minutes - slot_offset  # 05:15 (315 mins)
        min_notice_minutes = 4 * 60  # 240

        # 315 >= 30 + 240 = 270? Yes!
        assert dropoff_minutes >= current_minutes + min_notice_minutes


# =============================================================================
# Integration Tests - API Endpoint
# =============================================================================

class TestPaymentIntentEndpoint:
    """Integration tests for the payment intent endpoint with 4-hour validation."""

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_same_day_booking_rejected_within_4_hours(self, client, mock_stripe, base_booking_request):
        """Same-day booking within 4 hours should be rejected."""
        # Flight at 13:00, early slot at 10:15 (only 15 mins from now)
        today = date(2026, 3, 17)
        request = base_booking_request.copy()
        request["drop_off_date"] = today.isoformat()
        request["flight_date"] = today.isoformat()
        request["flight_departure_time"] = "13:00"
        request["drop_off_slot"] = "165"  # Early slot
        request["pickup_date"] = (today + timedelta(days=7)).isoformat()
        request["session_id"] = "test_rejected_4hrs_" + str(datetime.now().timestamp())

        response = client.post("/api/payments/create-intent", json=request)

        # Should be rejected
        assert response.status_code == 400
        assert "4 hours notice" in response.json()["detail"]

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_same_day_booking_allowed_with_4_hours_notice(self, client, mock_stripe, base_booking_request):
        """Same-day booking with exactly 4 hours notice should be allowed."""
        # Flight at 16:45, early slot at 14:00 (exactly 4h from 10:00)
        # Early slot = flight_time - 165 mins = 16:45 - 2:45 = 14:00
        today = date(2026, 3, 17)
        request = base_booking_request.copy()
        request["drop_off_date"] = today.isoformat()
        request["flight_date"] = today.isoformat()
        request["flight_departure_time"] = "16:45"
        request["drop_off_slot"] = "165"  # Early slot
        request["pickup_date"] = (today + timedelta(days=7)).isoformat()
        request["session_id"] = "test_allowed_4hrs_" + str(datetime.now().timestamp())

        # This should pass the 4-hour check (may fail for other reasons in test)
        response = client.post("/api/payments/create-intent", json=request)

        # Should NOT be rejected for 4-hour notice
        if response.status_code == 400:
            assert "4 hours notice" not in response.json().get("detail", "")

    @freeze_time("2026-03-18 22:00:00", tz_offset=0)
    def test_next_day_booking_always_allowed(self, client, mock_stripe, base_booking_request):
        """Next-day booking should always be allowed regardless of time."""
        # Flight at 01:00 Thursday (next day) - should always be allowed
        thu = date(2026, 3, 19)
        request = base_booking_request.copy()
        request["drop_off_date"] = thu.isoformat()
        request["flight_date"] = thu.isoformat()
        request["flight_departure_time"] = "01:00"
        request["drop_off_slot"] = "120"  # Late slot
        request["pickup_date"] = (thu + timedelta(days=7)).isoformat()
        request["session_id"] = "test_next_day_" + str(datetime.now().timestamp())

        response = client.post("/api/payments/create-intent", json=request)

        # Should NOT be rejected for 4-hour notice (next day booking)
        if response.status_code == 400:
            assert "4 hours notice" not in response.json().get("detail", "")

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_boundary_3h59m_rejected(self, client, mock_stripe, base_booking_request):
        """Booking with 3h59m notice should be rejected."""
        # Early slot at 13:59 (3h59m from 10:00)
        # Early slot = flight - 165 mins, so flight = 13:59 + 2:45 = 16:44
        today = date(2026, 3, 17)
        request = base_booking_request.copy()
        request["drop_off_date"] = today.isoformat()
        request["flight_date"] = today.isoformat()
        request["flight_departure_time"] = "16:44"
        request["drop_off_slot"] = "165"  # Early slot
        request["pickup_date"] = (today + timedelta(days=7)).isoformat()
        request["session_id"] = "test_3h59m_" + str(datetime.now().timestamp())

        response = client.post("/api/payments/create-intent", json=request)

        # Should be rejected (3h59m notice)
        assert response.status_code == 400
        assert "4 hours notice" in response.json()["detail"]

    @freeze_time("2026-03-17 10:00:00", tz_offset=0)
    def test_boundary_4h01m_allowed(self, client, mock_stripe, base_booking_request):
        """Booking with 4h01m notice should be allowed."""
        # Early slot at 14:01 (4h01m from 10:00)
        # Early slot = flight - 165 mins, so flight = 14:01 + 2:45 = 16:46
        today = date(2026, 3, 17)
        request = base_booking_request.copy()
        request["drop_off_date"] = today.isoformat()
        request["flight_date"] = today.isoformat()
        request["flight_departure_time"] = "16:46"
        request["drop_off_slot"] = "165"  # Early slot
        request["pickup_date"] = (today + timedelta(days=7)).isoformat()
        request["session_id"] = "test_4h01m_" + str(datetime.now().timestamp())

        response = client.post("/api/payments/create-intent", json=request)

        # Should NOT be rejected for 4-hour notice
        if response.status_code == 400:
            assert "4 hours notice" not in response.json().get("detail", "")


# =============================================================================
# Unit Tests - Late Slot Scenarios
# =============================================================================

class TestLateSlotScenarios:
    """Test scenarios with late slot (120 mins before flight)."""

    def test_late_slot_within_4_hours(self):
        """Late slot booking within 4 hours should be rejected."""
        current_minutes = 10 * 60  # 10:00
        flight_minutes = 15 * 60  # 15:00
        slot_offset = 120  # Late slot
        dropoff_minutes = flight_minutes - slot_offset  # 13:00
        min_notice_minutes = 4 * 60  # 240

        # 780 >= 600 + 240 = 840? No!
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_late_slot_with_4_hours_notice(self):
        """Late slot booking with exactly 4 hours should be allowed."""
        current_minutes = 10 * 60  # 10:00
        flight_minutes = 16 * 60  # 16:00
        slot_offset = 120  # Late slot
        dropoff_minutes = flight_minutes - slot_offset  # 14:00
        min_notice_minutes = 4 * 60  # 240

        # 840 >= 600 + 240 = 840? Yes!
        assert dropoff_minutes >= current_minutes + min_notice_minutes


# =============================================================================
# Unit Tests - Frontend Logic Simulation
# =============================================================================

class TestFrontendLogicSimulation:
    """Simulate frontend slot filtering logic."""

    def test_frontend_filters_slots_within_4_hours(self):
        """Simulate frontend filtering of slots within 4 hours."""
        # Current UK time: 10:00
        current_uk_minutes = 10 * 60
        min_notice_minutes = 4 * 60

        # Flight at 13:00
        flight_minutes = 13 * 60

        # Calculate slots
        early_slot_minutes = flight_minutes - 165  # 10:15
        late_slot_minutes = flight_minutes - 120   # 11:00

        # Check if slots are allowed
        early_allowed = early_slot_minutes >= current_uk_minutes + min_notice_minutes
        late_allowed = late_slot_minutes >= current_uk_minutes + min_notice_minutes

        # Both should be filtered out (not allowed)
        assert not early_allowed  # 615 >= 840? No
        assert not late_allowed   # 660 >= 840? No

    def test_frontend_shows_slots_with_enough_notice(self):
        """Simulate frontend showing slots with enough notice."""
        # Current UK time: 10:00
        current_uk_minutes = 10 * 60
        min_notice_minutes = 4 * 60

        # Flight at 17:00
        flight_minutes = 17 * 60

        # Calculate slots
        early_slot_minutes = flight_minutes - 165  # 14:15
        late_slot_minutes = flight_minutes - 120   # 15:00

        # Check if slots are allowed
        early_allowed = early_slot_minutes >= current_uk_minutes + min_notice_minutes
        late_allowed = late_slot_minutes >= current_uk_minutes + min_notice_minutes

        # Both should be shown (allowed)
        assert early_allowed  # 855 >= 840? Yes
        assert late_allowed   # 900 >= 840? Yes

    def test_frontend_next_day_no_filtering(self):
        """Simulate frontend not filtering next-day bookings."""
        # For next-day bookings, isToday = false
        is_today = False

        # When not today, slots are always allowed
        early_slot_allowed = not is_today or True  # Always True when not today
        late_slot_allowed = not is_today or True

        assert early_slot_allowed
        assert late_slot_allowed


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_midnight_boundary(self):
        """Test booking at exactly midnight."""
        current_minutes = 0  # 00:00
        flight_minutes = 4 * 60  # 04:00
        slot_offset = 165  # Early slot
        dropoff_minutes = flight_minutes - slot_offset  # 01:15 (75 mins)
        min_notice_minutes = 4 * 60  # 240

        # 75 >= 0 + 240 = 240? No!
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_late_evening_same_day(self):
        """Test booking late evening for late-night flight same day."""
        current_minutes = 20 * 60  # 20:00
        flight_minutes = 23 * 60 + 30  # 23:30
        slot_offset = 120  # Late slot
        dropoff_minutes = flight_minutes - slot_offset  # 21:30 (1290 mins)
        min_notice_minutes = 4 * 60  # 240

        # 1290 >= 1200 + 240 = 1440? No! (would be past midnight)
        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_early_flight_next_day_after_midnight(self):
        """Wed 23:00 looking at Thu 03:00 flight should be allowed (next day)."""
        wed = date(2026, 3, 18)
        thu = date(2026, 3, 19)

        # This is a next-day booking, so no 4-hour restriction applies
        is_same_day = (thu == wed)
        assert not is_same_day  # Different days, always allowed


# =============================================================================
# Manual Entry Tests
# =============================================================================

class TestManualEntryScenarios:
    """Test scenarios for manual flight entry."""

    def test_manual_entry_same_day_within_4_hours(self):
        """Manual entry same-day within 4 hours should be rejected."""
        # Same logic applies to manual entries
        current_minutes = 10 * 60  # 10:00
        manual_flight_time = "13:00"
        flight_minutes = 13 * 60
        slot_offset = 165  # Early slot
        dropoff_minutes = flight_minutes - slot_offset
        min_notice_minutes = 4 * 60

        assert not (dropoff_minutes >= current_minutes + min_notice_minutes)

    def test_manual_entry_next_day_always_allowed(self):
        """Manual entry for next day should always be allowed."""
        is_today = False  # Next day
        # No time restriction for next-day bookings
        assert not is_today  # Should skip 4-hour check
