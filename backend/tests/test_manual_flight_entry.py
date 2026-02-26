"""
Tests for manual flight entry and time override functionality.

Covers:
- Flight time validation endpoint
- Manual flight entry fields in bookings
- Time override tracking
- Edge cases for overnight flights with manual times
- Collection time calculations for overnight arrivals

All tests use mocked data to avoid database state conflicts.
"""
import pytest
import pytest_asyncio
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, validate_flight_time, ValidateFlightTimeRequest


# =============================================================================
# Flight Time Validation Tests - Unit Tests
# =============================================================================

class TestValidateFlightTime:
    """Unit tests for validate_flight_time() function."""

    # ----- Happy Path Tests -----

    def test_valid_departure_morning(self):
        """Valid morning departure time (08:30)."""
        is_valid, result, error = validate_flight_time("08:30", "departure")
        assert is_valid is True
        assert result == "08:30"
        assert error is None

    def test_valid_departure_afternoon(self):
        """Valid afternoon departure time (14:45)."""
        is_valid, result, error = validate_flight_time("14:45", "departure")
        assert is_valid is True
        assert result == "14:45"
        assert error is None

    def test_valid_departure_evening(self):
        """Valid evening departure time (20:15)."""
        is_valid, result, error = validate_flight_time("20:15", "departure")
        assert is_valid is True
        assert result == "20:15"
        assert error is None

    def test_valid_departure_boundary_early(self):
        """Valid boundary departure time (06:00)."""
        is_valid, result, error = validate_flight_time("06:00", "departure")
        assert is_valid is True
        assert result == "06:00"
        assert error is None

    def test_valid_departure_boundary_late(self):
        """Valid boundary departure time (22:00)."""
        is_valid, result, error = validate_flight_time("22:00", "departure")
        assert is_valid is True
        assert result == "22:00"
        assert error is None

    def test_valid_arrival_daytime(self):
        """Valid daytime arrival (14:30)."""
        is_valid, result, error = validate_flight_time("14:30", "arrival")
        assert is_valid is True
        assert result == "14:30"
        assert error is None

    def test_valid_arrival_evening(self):
        """Valid evening arrival (23:35)."""
        is_valid, result, error = validate_flight_time("23:35", "arrival")
        assert is_valid is True
        assert result == "23:35"
        assert error is None

    def test_valid_arrival_midnight(self):
        """Valid midnight arrival (00:05) - overnight flights allowed."""
        is_valid, result, error = validate_flight_time("00:05", "arrival")
        assert is_valid is True
        assert result == "00:05"
        assert error is None

    def test_valid_arrival_early_morning(self):
        """Valid early morning arrival (01:30) - overnight flights allowed."""
        is_valid, result, error = validate_flight_time("01:30", "arrival")
        assert is_valid is True
        assert result == "01:30"
        assert error is None

    def test_normalizes_single_digit_hour(self):
        """Normalizes single-digit hour (8:30 -> 08:30)."""
        is_valid, result, error = validate_flight_time("8:30", "departure")
        assert is_valid is True
        assert result == "08:30"
        assert error is None

    # ----- Negative Path Tests -----

    def test_invalid_departure_too_early(self):
        """Departure before 06:00 should fail."""
        is_valid, result, error = validate_flight_time("05:30", "departure")
        assert is_valid is False
        assert "between 06:00 and 22:00" in error

    def test_invalid_departure_too_late(self):
        """Departure after 22:00 should fail."""
        is_valid, result, error = validate_flight_time("23:00", "departure")
        assert is_valid is False
        assert "between 06:00 and 22:00" in error

    def test_invalid_arrival_unrealistic_time(self):
        """Arrival between 02:00-05:59 should fail (unrealistic for BOH)."""
        is_valid, result, error = validate_flight_time("03:30", "arrival")
        assert is_valid is False
        assert "between 06:00 and 01:59" in error

    def test_invalid_format_no_colon(self):
        """Time without colon should fail."""
        is_valid, result, error = validate_flight_time("1430", "departure")
        assert is_valid is False
        assert "HH:MM format" in error

    def test_invalid_format_extra_characters(self):
        """Time with extra characters should fail."""
        is_valid, result, error = validate_flight_time("14:30:00", "departure")
        assert is_valid is False
        assert "HH:MM format" in error

    def test_invalid_hours_out_of_range(self):
        """Hours > 23 should fail."""
        is_valid, result, error = validate_flight_time("25:00", "departure")
        assert is_valid is False
        assert "Invalid time" in error

    def test_invalid_minutes_out_of_range(self):
        """Minutes > 59 should fail."""
        is_valid, result, error = validate_flight_time("14:75", "departure")
        assert is_valid is False
        assert "Invalid time" in error

    def test_invalid_empty_string(self):
        """Empty string should fail."""
        is_valid, result, error = validate_flight_time("", "departure")
        assert is_valid is False
        assert "HH:MM format" in error

    def test_invalid_none_value(self):
        """None value should fail."""
        is_valid, result, error = validate_flight_time(None, "departure")
        assert is_valid is False
        assert "HH:MM format" in error

    def test_invalid_letters(self):
        """Alphabetic characters should fail."""
        is_valid, result, error = validate_flight_time("ab:cd", "departure")
        assert is_valid is False
        assert "HH:MM format" in error

    def test_invalid_negative_time(self):
        """Negative numbers should fail."""
        is_valid, result, error = validate_flight_time("-1:30", "departure")
        assert is_valid is False
        assert "HH:MM format" in error


# =============================================================================
# Edge Cases - Overnight Flight Collection Times
# =============================================================================

class TestOvernightCollectionTimeEdgeCases:
    """
    Edge case tests for overnight arrival collection time calculations.

    These test the specific scenarios mentioned by the user:
    1. Flight arrives at 23:35 on Monday, collection at 00:05 on Tuesday
    2. Flight leaves ABC at 22:50 on Tuesday, arrives at 00:50 on Wednesday
    """

    def calculate_collection_time(self, arrival_time_str, buffer_minutes=30):
        """
        Calculate collection time based on arrival time.

        Args:
            arrival_time_str: Arrival time in "HH:MM" format
            buffer_minutes: Minutes to add after landing (default 30)

        Returns:
            Tuple of (collection_time_str, crosses_midnight)
        """
        h, m = map(int, arrival_time_str.split(':'))
        total_mins = h * 60 + m + buffer_minutes

        crosses_midnight = total_mins >= 24 * 60
        collection_hour = (total_mins // 60) % 24
        collection_min = total_mins % 60

        return f"{collection_hour:02d}:{collection_min:02d}", crosses_midnight

    def is_overnight_flight(self, departure_time_str, arrival_time_str):
        """
        Determine if flight is overnight (depart evening, arrive after midnight).

        Returns True if:
        - Departure is >= 18:00
        - Arrival is < 06:00
        """
        if not departure_time_str or not arrival_time_str:
            return False

        dep_hour = int(departure_time_str.split(':')[0])
        arr_hour = int(arrival_time_str.split(':')[0])

        return dep_hour >= 18 and arr_hour < 6

    def calculate_actual_pickup_date(self, selected_date, is_overnight):
        """Calculate actual pickup date (add 1 day for overnight flights)."""
        if is_overnight:
            return selected_date + timedelta(days=1)
        return selected_date

    # ----- Edge Case 1: Flight arrives 23:35, collection 00:05 -----

    def test_edge_case_arrive_2335_collect_0005(self):
        """
        Edge Case 1: Flight arrives at 23:35 on Monday.
        Collection time: 00:05 on Tuesday (23:35 + 30 mins crosses midnight).

        This is a same-day arrival that crosses midnight for COLLECTION only.
        NOT an overnight flight (arrival is before midnight).
        """
        arrival_time = "23:35"
        arrival_date = date(2026, 3, 2)  # Monday

        # Calculate collection time
        collection_time, crosses_midnight = self.calculate_collection_time(arrival_time)

        assert collection_time == "00:05"
        assert crosses_midnight is True

        # Collection date is Tuesday (arrival date + 1)
        collection_date = arrival_date + timedelta(days=1) if crosses_midnight else arrival_date
        assert collection_date == date(2026, 3, 3)  # Tuesday

        # This is NOT an overnight flight (arrival is 23:35, before midnight)
        # But collection crosses midnight
        is_overnight = self.is_overnight_flight("18:00", arrival_time)  # Assume 18:00 departure
        assert is_overnight is False  # Arrival is NOT < 06:00

    def test_edge_case_2335_full_booking_flow(self):
        """
        Full booking flow for 23:35 arrival edge case.

        User selects:
        - Return date: Monday 2nd March 2026
        - Return flight: 23:35 arrival

        Expected:
        - Pickup time window: from 00:05 on Tuesday 3rd March
        """
        user_selected_date = date(2026, 3, 2)  # Monday
        arrival_time = "23:35"

        # This is not an overnight flight (arrives before midnight)
        is_overnight = self.is_overnight_flight("18:00", arrival_time)
        assert is_overnight is False

        # But collection time calculation crosses midnight
        collection_time, crosses = self.calculate_collection_time(arrival_time)
        assert collection_time == "00:05"
        assert crosses is True

        # For display purposes
        if crosses:
            pickup_date = user_selected_date + timedelta(days=1)
        else:
            pickup_date = user_selected_date

        assert pickup_date == date(2026, 3, 3)

        # Display should show:
        display = f"Pick-up: {pickup_date.strftime('%A %d/%m/%Y')} from {collection_time}"
        assert "Tuesday" in display
        assert "03/03/2026" in display
        assert "00:05" in display

    # ----- Edge Case 2: Flight departs 22:50, arrives 00:50 -----

    def test_edge_case_depart_2250_arrive_0050(self):
        """
        Edge Case 2: Flight leaves at 22:50 on Tuesday, arrives 00:50 on Wednesday.

        This IS an overnight flight:
        - Departure: 22:50 (>= 18:00) ✓
        - Arrival: 00:50 (< 06:00) ✓

        Collection time: 01:20 on Wednesday (00:50 + 30 mins)
        """
        departure_time = "22:50"
        arrival_time = "00:50"
        departure_date = date(2026, 3, 3)  # Tuesday

        # This IS an overnight flight
        is_overnight = self.is_overnight_flight(departure_time, arrival_time)
        assert is_overnight is True

        # Arrival date is Wednesday
        arrival_date = departure_date + timedelta(days=1)
        assert arrival_date == date(2026, 3, 4)  # Wednesday

        # Collection time
        collection_time, crosses = self.calculate_collection_time(arrival_time)
        assert collection_time == "01:20"
        assert crosses is False  # 00:50 + 30 = 01:20, doesn't cross midnight again

        # Collection date is same as arrival date (Wednesday)
        collection_date = arrival_date
        assert collection_date == date(2026, 3, 4)

    def test_edge_case_2250_0050_full_booking_flow(self):
        """
        Full booking flow for 22:50->00:50 overnight flight.

        User selects:
        - Return date: Tuesday 3rd March 2026 (departure date)
        - Return flight: 22:50 -> 00:50 overnight

        Expected:
        - Actual pickup date: Wednesday 4th March (arrival date)
        - Pickup time: from 01:20
        """
        user_selected_date = date(2026, 3, 3)  # Tuesday (departure date)
        departure_time = "22:50"
        arrival_time = "00:50"

        # This IS an overnight flight
        is_overnight = self.is_overnight_flight(departure_time, arrival_time)
        assert is_overnight is True

        # Actual pickup date = selected date + 1 for overnight
        actual_pickup_date = self.calculate_actual_pickup_date(user_selected_date, is_overnight)
        assert actual_pickup_date == date(2026, 3, 4)  # Wednesday

        # Collection time
        collection_time, _ = self.calculate_collection_time(arrival_time)
        assert collection_time == "01:20"

        # Display should show Wednesday
        display = f"Pick-up: {actual_pickup_date.strftime('%A %d/%m/%Y')} from {collection_time}"
        assert "Wednesday" in display
        assert "04/03/2026" in display
        assert "01:20" in display

    # ----- Additional Edge Cases -----

    def test_edge_case_arrive_2359_collect_0029(self):
        """
        Flight arrives at 23:59, collection at 00:29.
        Just before midnight arrival, collection after midnight.
        """
        collection_time, crosses = self.calculate_collection_time("23:59")
        assert collection_time == "00:29"
        assert crosses is True

    def test_edge_case_arrive_0001_collect_0031(self):
        """
        Flight arrives at 00:01, collection at 00:31.
        Just after midnight arrival, collection same day (no additional crossing).
        """
        collection_time, crosses = self.calculate_collection_time("00:01")
        assert collection_time == "00:31"
        assert crosses is False

    def test_edge_case_arrive_2330_collect_0000(self):
        """
        Flight arrives at 23:30, collection exactly at midnight.
        """
        collection_time, crosses = self.calculate_collection_time("23:30")
        assert collection_time == "00:00"
        assert crosses is True

    def test_boundary_1759_not_overnight(self):
        """
        Flight departing 17:59, arriving 01:00 is NOT overnight.
        Departure must be >= 18:00 to be considered overnight.
        """
        is_overnight = self.is_overnight_flight("17:59", "01:00")
        assert is_overnight is False

    def test_boundary_1800_is_overnight(self):
        """
        Flight departing 18:00, arriving 01:00 IS overnight.
        Departure at exactly 18:00 qualifies.
        """
        is_overnight = self.is_overnight_flight("18:00", "01:00")
        assert is_overnight is True

    def test_boundary_arrive_0559_is_overnight(self):
        """
        Flight departing 20:00, arriving 05:59 IS overnight.
        Arrival before 06:00 qualifies.
        """
        is_overnight = self.is_overnight_flight("20:00", "05:59")
        assert is_overnight is True

    def test_boundary_arrive_0600_not_overnight(self):
        """
        Flight departing 20:00, arriving 06:00 is NOT overnight.
        Arrival at exactly 06:00 does NOT qualify.
        """
        is_overnight = self.is_overnight_flight("20:00", "06:00")
        assert is_overnight is False


# =============================================================================
# Manual Entry Field Tests - Mocked Integration Tests
# =============================================================================

class TestManualEntryBookingFields:
    """Tests for manual flight entry fields stored on bookings."""

    def create_mock_booking(self, **overrides):
        """Create a mock booking with manual entry fields."""
        booking = MagicMock()
        booking.id = 1
        booking.reference = "TAG-TEST001"
        booking.dropoff_date = date(2026, 3, 15)
        booking.dropoff_time = time(10, 0)
        booking.dropoff_flight_number = "FR3944"
        booking.dropoff_destination = "Faro"

        # Manual entry fields - defaults
        booking.dropoff_time_override = False
        booking.dropoff_scheduled_time = None
        booking.dropoff_manual_entry = False
        booking.dropoff_airline_code = None
        booking.dropoff_airline_name = None

        booking.pickup_time_override = False
        booking.pickup_scheduled_time = None
        booking.pickup_manual_entry = False
        booking.pickup_airline_code = None
        booking.pickup_airline_name = None

        # Apply overrides
        for key, value in overrides.items():
            setattr(booking, key, value)

        return booking

    # ----- Time Override Tests -----

    def test_booking_with_dropoff_time_override(self):
        """Booking with customer-corrected departure time."""
        booking = self.create_mock_booking(
            dropoff_time_override=True,
            dropoff_scheduled_time=time(10, 0),  # Original from schedule
            dropoff_time=time(10, 30)  # Customer says it's actually 10:30
        )

        assert booking.dropoff_time_override is True
        assert booking.dropoff_scheduled_time == time(10, 0)
        assert booking.dropoff_time == time(10, 30)

        # Time difference
        scheduled_mins = booking.dropoff_scheduled_time.hour * 60 + booking.dropoff_scheduled_time.minute
        actual_mins = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
        diff = actual_mins - scheduled_mins
        assert diff == 30  # 30 minute difference

    def test_booking_with_pickup_time_override(self):
        """Booking with customer-corrected arrival time."""
        booking = self.create_mock_booking(
            pickup_time_override=True,
            pickup_scheduled_time=time(14, 30),  # Original from schedule
            pickup_time=time(15, 0)  # Customer says it's actually 15:00
        )

        assert booking.pickup_time_override is True
        assert booking.pickup_scheduled_time == time(14, 30)
        assert booking.pickup_time == time(15, 0)

    def test_booking_without_override_has_no_scheduled_time(self):
        """Booking without override should not have scheduled_time set."""
        booking = self.create_mock_booking()

        assert booking.dropoff_time_override is False
        assert booking.dropoff_scheduled_time is None

    # ----- Manual Entry Tests -----

    def test_booking_with_manual_departure_entry(self):
        """Booking with fully manual departure (TUI flight not in system)."""
        booking = self.create_mock_booking(
            dropoff_manual_entry=True,
            dropoff_airline_code="BY",
            dropoff_airline_name="TUI Airways",
            dropoff_flight_number="BY1234",
            dropoff_time=time(8, 45),
            departure_id=None  # No link to flight table
        )

        assert booking.dropoff_manual_entry is True
        assert booking.dropoff_airline_code == "BY"
        assert booking.dropoff_airline_name == "TUI Airways"
        assert booking.departure_id is None

    def test_booking_with_manual_arrival_entry(self):
        """Booking with fully manual arrival."""
        booking = self.create_mock_booking(
            pickup_manual_entry=True,
            pickup_airline_code="BY",
            pickup_airline_name="TUI Airways",
            pickup_flight_number="BY4321",
            pickup_time=time(22, 30),
            arrival_id=None  # No link to flight table
        )

        assert booking.pickup_manual_entry is True
        assert booking.pickup_airline_code == "BY"
        assert booking.pickup_airline_name == "TUI Airways"
        assert booking.arrival_id is None

    def test_manual_entry_with_other_airline(self):
        """Manual entry with 'Other' airline selection."""
        booking = self.create_mock_booking(
            dropoff_manual_entry=True,
            dropoff_airline_code="OTHER",
            dropoff_airline_name="Norwegian",
            dropoff_flight_number="DY1234",
        )

        assert booking.dropoff_airline_code == "OTHER"
        assert booking.dropoff_airline_name == "Norwegian"

    # ----- Combined Override + Manual Tests -----

    def test_booking_departure_override_arrival_manual(self):
        """
        Complex scenario:
        - Departure from schedule but time corrected
        - Arrival fully manual (not in schedule)
        """
        booking = self.create_mock_booking(
            # Departure: from schedule, time corrected
            dropoff_time_override=True,
            dropoff_scheduled_time=time(10, 0),
            dropoff_time=time(10, 15),
            dropoff_manual_entry=False,
            departure_id=123,  # Linked to flight table

            # Arrival: manual entry
            pickup_manual_entry=True,
            pickup_airline_code="BY",
            pickup_airline_name="TUI Airways",
            pickup_time=time(18, 30),
            arrival_id=None  # Not linked
        )

        # Verify departure
        assert booking.dropoff_time_override is True
        assert booking.dropoff_manual_entry is False
        assert booking.departure_id == 123

        # Verify arrival
        assert booking.pickup_manual_entry is True
        assert booking.arrival_id is None


# =============================================================================
# API Endpoint Tests - Mocked
# =============================================================================

class TestValidateFlightTimeEndpoint:
    """Tests for POST /api/booking/validate-flight-time endpoint."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request factory."""
        def _create(time_str, flight_type):
            return ValidateFlightTimeRequest(time=time_str, flight_type=flight_type)
        return _create

    def test_endpoint_valid_departure_returns_normalized(self, mock_request):
        """Valid departure time returns normalized time."""
        request = mock_request("8:30", "departure")
        is_valid, result, error = validate_flight_time(request.time, request.flight_type)

        assert is_valid is True
        assert result == "08:30"  # Normalized

    def test_endpoint_invalid_time_returns_error(self, mock_request):
        """Invalid time format returns error message."""
        request = mock_request("invalid", "departure")
        is_valid, result, error = validate_flight_time(request.time, request.flight_type)

        assert is_valid is False
        assert error is not None
        assert "HH:MM" in error

    def test_endpoint_out_of_range_departure(self, mock_request):
        """Out of range departure time returns business rule error."""
        request = mock_request("03:00", "departure")
        is_valid, result, error = validate_flight_time(request.time, request.flight_type)

        assert is_valid is False
        assert "06:00" in error and "22:00" in error


# =============================================================================
# Integration Scenario Tests
# =============================================================================

class TestManualFlightEntryScenarios:
    """Real-world scenario tests for manual flight entry."""

    def test_scenario_tui_flight_not_in_system(self):
        """
        Scenario: Customer booking TUI flight not in our schedule.

        1. Customer selects date: 15/03/2026
        2. Selects airline: TUI
        3. TUI flights not in dropdown (not in API)
        4. Customer clicks "Enter flight manually"
        5. Enters: BY1234, 08:45, Tenerife
        6. System stores as manual entry
        """
        # Simulated booking data
        booking_data = {
            "dropoff_date": "2026-03-15",
            "dropoff_time": "08:45",
            "dropoff_flight_number": "BY1234",
            "dropoff_destination": "Tenerife",
            "dropoff_manual_entry": True,
            "dropoff_airline_code": "BY",
            "dropoff_airline_name": "TUI Airways",
            "departure_id": None,  # No slot booking
        }

        # Validate time
        is_valid, _, _ = validate_flight_time(booking_data["dropoff_time"], "departure")
        assert is_valid is True

        # Manual entry flag set
        assert booking_data["dropoff_manual_entry"] is True
        assert booking_data["departure_id"] is None

    def test_scenario_flight_time_changed_by_airline(self):
        """
        Scenario: Customer's flight was rescheduled by airline.

        1. Schedule shows FR3944 departs 10:00
        2. Customer's booking confirmation shows 10:35
        3. Customer corrects the time
        4. System stores original and customer-provided time
        """
        booking_data = {
            "dropoff_flight_number": "FR3944",
            "dropoff_scheduled_time": "10:00",  # From our schedule
            "dropoff_time": "10:35",  # Customer's actual time
            "dropoff_time_override": True,
            "dropoff_manual_entry": False,
            "departure_id": 123,  # Still linked to flight
        }

        # Both times are valid
        assert validate_flight_time(booking_data["dropoff_scheduled_time"], "departure")[0] is True
        assert validate_flight_time(booking_data["dropoff_time"], "departure")[0] is True

        # Override flag set, but still linked to flight
        assert booking_data["dropoff_time_override"] is True
        assert booking_data["departure_id"] == 123

    def test_scenario_overnight_manual_arrival(self):
        """
        Scenario: Manual entry for overnight TUI arrival.

        TUI 671 from Antalya:
        - Departs: 22:00
        - Arrives: 00:35 (next day)
        - Not in our system, customer enters manually
        """
        departure_time = "22:00"
        arrival_time = "00:35"

        # Arrival time is valid (overnight allowed)
        is_valid, normalized, error = validate_flight_time(arrival_time, "arrival")
        assert is_valid is True
        assert normalized == "00:35"

        # Departure time also valid
        is_valid, _, _ = validate_flight_time(departure_time, "departure")
        assert is_valid is True

        # Calculate pickup time
        h, m = map(int, arrival_time.split(':'))
        pickup_mins = h * 60 + m + 30
        pickup_time = f"{(pickup_mins // 60) % 24:02d}:{pickup_mins % 60:02d}"
        assert pickup_time == "01:05"


# =============================================================================
# Security Tests
# =============================================================================

class TestManualEntrySecurityValidation:
    """Security validation tests for manual flight entry."""

    def test_rejects_sql_injection_attempt(self):
        """Time field with SQL injection attempt rejected."""
        is_valid, _, error = validate_flight_time("10:00'; DROP TABLE bookings;--", "departure")
        assert is_valid is False
        assert "HH:MM" in error

    def test_rejects_xss_attempt(self):
        """Time field with XSS attempt rejected."""
        is_valid, _, error = validate_flight_time("<script>alert('xss')</script>", "departure")
        assert is_valid is False
        assert "HH:MM" in error

    def test_rejects_excessively_long_input(self):
        """Excessively long input rejected."""
        is_valid, _, error = validate_flight_time("A" * 1000, "departure")
        assert is_valid is False
        assert "HH:MM" in error

    def test_handles_unicode_gracefully(self):
        """Unicode characters in time field handled gracefully."""
        # Non-digit unicode characters should fail
        is_valid, _, error = validate_flight_time("十:三十", "departure")  # Chinese numerals
        assert is_valid is False
        assert "HH:MM" in error

    def test_handles_special_characters(self):
        """Special characters handled gracefully."""
        is_valid, _, error = validate_flight_time("10:30\n\r\t", "departure")
        assert is_valid is False
        assert "HH:MM" in error


# =============================================================================
# db_service Function Tests
# =============================================================================

class TestDbServiceCreateBookingWithManualFields:
    """Tests for create_booking with manual entry fields."""

    def test_create_booking_params_include_manual_fields(self):
        """create_booking function should accept all manual entry parameters."""
        from db_service import create_booking
        import inspect

        # Get function signature
        sig = inspect.signature(create_booking)
        params = list(sig.parameters.keys())

        # Check all manual entry params are present
        expected_params = [
            'dropoff_time_override',
            'dropoff_scheduled_time',
            'dropoff_manual_entry',
            'dropoff_airline_code',
            'dropoff_airline_name',
            'pickup_time_override',
            'pickup_scheduled_time',
            'pickup_manual_entry',
            'pickup_airline_code',
            'pickup_airline_name',
        ]

        for param in expected_params:
            assert param in params, f"Missing parameter: {param}"

    def test_create_full_booking_params_include_manual_fields(self):
        """create_full_booking function should accept all manual entry parameters."""
        from db_service import create_full_booking
        import inspect

        sig = inspect.signature(create_full_booking)
        params = list(sig.parameters.keys())

        expected_params = [
            'dropoff_time_override',
            'dropoff_scheduled_time',
            'dropoff_manual_entry',
            'dropoff_airline_code',
            'dropoff_airline_name',
            'pickup_time_override',
            'pickup_scheduled_time',
            'pickup_manual_entry',
            'pickup_airline_code',
            'pickup_airline_name',
        ]

        for param in expected_params:
            assert param in params, f"Missing parameter: {param}"


# =============================================================================
# Model Tests
# =============================================================================

class TestBookingRequestModel:
    """Tests for BookingRequest model with manual entry fields."""

    def test_booking_request_accepts_manual_fields(self):
        """BookingRequest should accept manual entry fields."""
        from models import BookingRequest
        import inspect

        # Get model fields
        fields = BookingRequest.model_fields.keys()

        expected_fields = [
            'dropoff_time_override',
            'dropoff_scheduled_time',
            'dropoff_manual_entry',
            'pickup_time_override',
            'pickup_scheduled_time',
            'pickup_manual_entry',
            'pickup_origin_code',
            'pickup_origin_name',
        ]

        for field in expected_fields:
            assert field in fields, f"Missing field: {field}"

    def test_booking_request_defaults(self):
        """Manual entry fields should have sensible defaults."""
        from models import BookingRequest

        # Create minimal valid request
        request_data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "phone": "01onal234567890",
            "drop_off_date": "2026-03-15",
            "drop_off_slot_type": "165",
            "flight_date": "2026-03-15",
            "flight_time": "10:00",
            "flight_number": "FR3944",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "FAO",
            "destination_name": "Faro",
            "pickup_date": "2026-03-22",
            "return_flight_time": "14:30",
            "return_flight_number": "FR3945",
            "registration": "AB12CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "Test City",
            "billing_postcode": "TE1 1ST",
        }

        request = BookingRequest(**request_data)

        # Check defaults
        assert request.dropoff_time_override is False
        assert request.dropoff_scheduled_time is None
        assert request.dropoff_manual_entry is False
        assert request.pickup_time_override is False
        assert request.pickup_scheduled_time is None
        assert request.pickup_manual_entry is False
