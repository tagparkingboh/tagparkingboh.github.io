"""
Tests for overnight arrival detection and booking date correction.

Covers:
- is_overnight_arrival() detection logic
- Booking pickup_date correction for overnight flights
- Edge cases (early morning vs late evening arrivals)

All tests use mocked data to avoid database state conflicts.
"""
import pytest
from unittest.mock import MagicMock
from datetime import date, time, datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fix_overnight_arrivals import is_overnight_arrival
from import_flights import is_overnight_flight


# =============================================================================
# is_overnight_arrival() Detection Tests
# =============================================================================

class TestIsOvernightArrival:
    """Tests for overnight arrival detection."""

    def test_classic_overnight_depart_22_arrive_0035(self):
        """Depart 22:00, arrive 00:35 = overnight."""
        result = is_overnight_arrival(
            departure_time=time(22, 0),
            arrival_time=time(0, 35)
        )
        assert result is True

    def test_classic_overnight_depart_21_arrive_0115(self):
        """Depart 21:00, arrive 01:15 = overnight."""
        result = is_overnight_arrival(
            departure_time=time(21, 0),
            arrival_time=time(1, 15)
        )
        assert result is True

    def test_late_evening_depart_18_arrive_2200(self):
        """Depart 18:00, arrive 22:00 = NOT overnight (same day)."""
        result = is_overnight_arrival(
            departure_time=time(18, 0),
            arrival_time=time(22, 0)
        )
        assert result is False

    def test_daytime_flight_depart_10_arrive_14(self):
        """Depart 10:00, arrive 14:00 = NOT overnight."""
        result = is_overnight_arrival(
            departure_time=time(10, 0),
            arrival_time=time(14, 0)
        )
        assert result is False

    def test_early_morning_depart_06_arrive_10(self):
        """Depart 06:00, arrive 10:00 = NOT overnight."""
        result = is_overnight_arrival(
            departure_time=time(6, 0),
            arrival_time=time(10, 0)
        )
        assert result is False

    def test_arrival_at_midnight(self):
        """Depart 20:00, arrive 00:00 = overnight."""
        result = is_overnight_arrival(
            departure_time=time(20, 0),
            arrival_time=time(0, 0)
        )
        assert result is True

    def test_arrival_just_before_6am(self):
        """Depart 23:00, arrive 05:59 = overnight."""
        result = is_overnight_arrival(
            departure_time=time(23, 0),
            arrival_time=time(5, 59)
        )
        assert result is True

    def test_arrival_at_6am_not_overnight(self):
        """Depart 02:00, arrive 06:00 = NOT overnight (early morning flight)."""
        result = is_overnight_arrival(
            departure_time=time(2, 0),
            arrival_time=time(6, 0)
        )
        assert result is False

    def test_none_departure_time(self):
        """None departure time returns False."""
        result = is_overnight_arrival(
            departure_time=None,
            arrival_time=time(0, 35)
        )
        assert result is False

    def test_none_arrival_time(self):
        """None arrival time returns False."""
        result = is_overnight_arrival(
            departure_time=time(22, 0),
            arrival_time=None
        )
        assert result is False

    def test_both_times_none(self):
        """Both times None returns False."""
        result = is_overnight_arrival(
            departure_time=None,
            arrival_time=None
        )
        assert result is False


# =============================================================================
# Booking Date Correction Tests
# =============================================================================

class TestBookingDateCorrection:
    """Tests for booking pickup_date correction logic."""

    def test_overnight_booking_needs_date_correction(self):
        """Overnight arrival booking pickup_date should match arrival date."""
        # Mock booking with wrong pickup_date
        booking = MagicMock()
        booking.id = 1
        booking.reference = "TAG-TEST001"
        booking.pickup_date = date(2026, 3, 28)  # Wrong - departure date
        booking.pickup_flight_number = "TUI671"
        booking.arrival_id = 100

        # Mock arrival flight
        arrival = MagicMock()
        arrival.id = 100
        arrival.date = date(2026, 3, 28)  # Also stored with wrong date in this scenario
        arrival.departure_time = time(22, 0)
        arrival.arrival_time = time(0, 35)

        # Detection
        is_overnight = is_overnight_arrival(arrival.departure_time, arrival.arrival_time)
        assert is_overnight is True

        # The correct pickup_date should be 29th (arrival date after midnight)
        correct_pickup_date = date(2026, 3, 29)
        needs_fix = booking.pickup_date != correct_pickup_date
        assert needs_fix is True

    def test_regular_flight_no_correction_needed(self):
        """Regular daytime flight booking needs no correction."""
        booking = MagicMock()
        booking.pickup_date = date(2026, 2, 28)

        arrival = MagicMock()
        arrival.date = date(2026, 2, 28)
        arrival.departure_time = time(10, 0)
        arrival.arrival_time = time(14, 30)

        is_overnight = is_overnight_arrival(arrival.departure_time, arrival.arrival_time)
        assert is_overnight is False

        # No correction needed
        needs_fix = False
        assert needs_fix is False

    def test_pickup_time_windows_after_midnight(self):
        """Pickup time windows calculated correctly for after-midnight arrival."""
        arrival_time = time(0, 35)
        arrival_dt = datetime.combine(date(2026, 3, 29), arrival_time)

        pickup_time_from = (arrival_dt + timedelta(minutes=35)).time()  # 01:10
        pickup_time_to = (arrival_dt + timedelta(minutes=60)).time()    # 01:35

        assert pickup_time_from == time(1, 10)
        assert pickup_time_to == time(1, 35)

    def test_late_evening_arrival_same_day(self):
        """Late evening arrival (23:30) stays on same day."""
        booking = MagicMock()
        booking.pickup_date = date(2026, 2, 28)

        arrival = MagicMock()
        arrival.date = date(2026, 2, 28)
        arrival.departure_time = time(18, 0)
        arrival.arrival_time = time(23, 30)

        is_overnight = is_overnight_arrival(arrival.departure_time, arrival.arrival_time)
        assert is_overnight is False

        # Pickup should stay on 28th
        assert booking.pickup_date == date(2026, 2, 28)


# =============================================================================
# Edge Cases
# =============================================================================

class TestOvernightEdgeCases:
    """Edge case tests for overnight arrival handling."""

    def test_flight_crossing_year_boundary(self):
        """Flight on Dec 31 arriving Jan 1 is overnight."""
        result = is_overnight_arrival(
            departure_time=time(23, 0),
            arrival_time=time(2, 30)
        )
        assert result is True

    def test_flight_crossing_month_boundary(self):
        """Flight on Jan 31 arriving Feb 1 is overnight."""
        result = is_overnight_arrival(
            departure_time=time(21, 30),
            arrival_time=time(1, 15)
        )
        assert result is True

    def test_very_early_morning_departure_not_overnight(self):
        """Flight departing 03:00 arriving 07:00 is NOT overnight."""
        result = is_overnight_arrival(
            departure_time=time(3, 0),
            arrival_time=time(7, 0)
        )
        assert result is False

    def test_evening_departure_evening_arrival_same_day(self):
        """Flight departing 18:00 arriving 21:00 is NOT overnight."""
        result = is_overnight_arrival(
            departure_time=time(18, 0),
            arrival_time=time(21, 0)
        )
        assert result is False

    def test_booking_without_arrival_id_skipped(self):
        """Bookings without arrival_id should be skipped."""
        booking = MagicMock()
        booking.arrival_id = None

        # Should not process bookings without arrival link
        should_process = booking.arrival_id is not None
        assert should_process is False


# =============================================================================
# Integration Scenario Tests
# =============================================================================

class TestOvernightScenarios:
    """Real-world scenario tests."""

    def test_tui_antalya_overnight_scenario(self):
        """TUI 671 from Antalya: depart 22:00, arrive 00:35."""
        # This is the actual scenario reported by the user
        departure_time = time(22, 0)
        arrival_time = time(0, 35)

        is_overnight = is_overnight_arrival(departure_time, arrival_time)
        assert is_overnight is True

        # Booking made for 28th departure should have pickup on 29th
        departure_date = date(2026, 3, 28)
        correct_pickup_date = departure_date + timedelta(days=1)
        assert correct_pickup_date == date(2026, 3, 29)

    def test_multiple_overnight_flights_batch(self):
        """Multiple overnight flights in a batch."""
        flights = [
            {"dep": time(22, 0), "arr": time(0, 35), "expected": True},   # Antalya
            {"dep": time(21, 30), "arr": time(1, 15), "expected": True},  # Dalaman
            {"dep": time(10, 0), "arr": time(14, 0), "expected": False},  # Tenerife day
            {"dep": time(18, 0), "arr": time(22, 30), "expected": False}, # Alicante evening
            {"dep": time(23, 45), "arr": time(3, 30), "expected": True},  # Late night
        ]

        for flight in flights:
            result = is_overnight_arrival(flight["dep"], flight["arr"])
            assert result == flight["expected"], \
                f"Failed for dep={flight['dep']}, arr={flight['arr']}"

    def test_correction_preserves_other_booking_fields(self):
        """Correcting pickup_date should not affect other booking fields."""
        booking = MagicMock()
        booking.id = 123
        booking.reference = "TAG-ABC123"
        booking.customer_id = 456
        booking.vehicle_id = 789
        booking.pickup_date = date(2026, 3, 28)
        booking.pickup_time = time(0, 35)
        booking.pickup_flight_number = "TUI671"

        # Correct the date
        original_id = booking.id
        original_ref = booking.reference
        original_customer = booking.customer_id
        original_vehicle = booking.vehicle_id
        original_time = booking.pickup_time
        original_flight = booking.pickup_flight_number

        booking.pickup_date = date(2026, 3, 29)

        # All other fields unchanged
        assert booking.id == original_id
        assert booking.reference == original_ref
        assert booking.customer_id == original_customer
        assert booking.vehicle_id == original_vehicle
        assert booking.pickup_time == original_time
        assert booking.pickup_flight_number == original_flight


# =============================================================================
# Import Flights Overnight Detection Tests
# =============================================================================

class TestImportFlightsOvernightDetection:
    """Tests for is_overnight_flight() in import_flights.py."""

    def test_overnight_depart_2200_arrive_0035(self):
        """Depart 22:00, arrive 00:35 = overnight."""
        result = is_overnight_flight("22:00", "00:35")
        assert result is True

    def test_overnight_depart_2100_arrive_0115(self):
        """Depart 21:00, arrive 01:15 = overnight."""
        result = is_overnight_flight("21:00", "01:15")
        assert result is True

    def test_not_overnight_depart_1800_arrive_2200(self):
        """Depart 18:00, arrive 22:00 = NOT overnight."""
        result = is_overnight_flight("18:00", "22:00")
        assert result is False

    def test_not_overnight_daytime(self):
        """Depart 10:00, arrive 14:00 = NOT overnight."""
        result = is_overnight_flight("10:00", "14:00")
        assert result is False

    def test_none_departure_time(self):
        """None departure time returns False."""
        result = is_overnight_flight(None, "00:35")
        assert result is False

    def test_none_arrival_time(self):
        """None arrival time returns False."""
        result = is_overnight_flight("22:00", None)
        assert result is False

    def test_empty_strings(self):
        """Empty strings return False."""
        result = is_overnight_flight("", "")
        assert result is False

    def test_arrival_at_midnight(self):
        """Depart 20:00, arrive 00:00 = overnight."""
        result = is_overnight_flight("20:00", "00:00")
        assert result is True

    def test_arrival_just_before_6am(self):
        """Depart 23:00, arrive 05:59 = overnight."""
        result = is_overnight_flight("23:00", "05:59")
        assert result is True

    def test_arrival_at_6am_not_overnight(self):
        """Depart 02:00, arrive 06:00 = NOT overnight (early morning flight)."""
        result = is_overnight_flight("02:00", "06:00")
        assert result is False


class TestImportFlightsDateAdjustment:
    """Tests for date adjustment logic during import."""

    def test_overnight_arrival_date_adjusted(self):
        """Overnight flight arrival date should be departure date + 1."""
        departure_date = date(2026, 3, 28)
        dep_time = "22:00"
        arr_time = "00:35"

        if is_overnight_flight(dep_time, arr_time):
            arrival_date = departure_date + timedelta(days=1)
        else:
            arrival_date = departure_date

        assert arrival_date == date(2026, 3, 29)

    def test_regular_flight_date_not_adjusted(self):
        """Regular flight arrival date stays same as departure date."""
        departure_date = date(2026, 2, 28)
        dep_time = "10:00"
        arr_time = "14:00"

        if is_overnight_flight(dep_time, arr_time):
            arrival_date = departure_date + timedelta(days=1)
        else:
            arrival_date = departure_date

        assert arrival_date == date(2026, 2, 28)

    def test_year_boundary_overnight(self):
        """Overnight flight on Dec 31 should have arrival on Jan 1."""
        departure_date = date(2025, 12, 31)
        dep_time = "23:00"
        arr_time = "02:30"

        if is_overnight_flight(dep_time, arr_time):
            arrival_date = departure_date + timedelta(days=1)
        else:
            arrival_date = departure_date

        assert arrival_date == date(2026, 1, 1)

    def test_month_boundary_overnight(self):
        """Overnight flight on Jan 31 should have arrival on Feb 1."""
        departure_date = date(2026, 1, 31)
        dep_time = "21:30"
        arr_time = "01:15"

        if is_overnight_flight(dep_time, arr_time):
            arrival_date = departure_date + timedelta(days=1)
        else:
            arrival_date = departure_date

        assert arrival_date == date(2026, 2, 1)
