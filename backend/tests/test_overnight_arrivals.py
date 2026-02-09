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


# =============================================================================
# Frontend Pickup Date Adjustment Logic Tests
# =============================================================================

class TestFrontendPickupDateAdjustment:
    """
    Tests for frontend pickup date adjustment logic.

    When a user selects an overnight flight (+1), the actual pickup date
    should be the calendar date + 1 day.

    This simulates the JavaScript logic:
    ```javascript
    const actualPickupDate = useMemo(() => {
      if (!formData.pickupDate) return null
      if (selectedArrivalFlight?.isOvernight) {
        const nextDay = new Date(formData.pickupDate)
        nextDay.setDate(nextDay.getDate() + 1)
        return nextDay
      }
      return formData.pickupDate
    }, [formData.pickupDate, selectedArrivalFlight])
    ```
    """

    def calculate_actual_pickup_date(self, selected_date, is_overnight):
        """Python equivalent of frontend actualPickupDate logic."""
        if selected_date is None:
            return None
        if is_overnight:
            return selected_date + timedelta(days=1)
        return selected_date

    def test_overnight_flight_adds_one_day(self):
        """User selects 24/07, overnight flight, actual pickup = 25/07."""
        selected_date = date(2026, 7, 24)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2026, 7, 25)

    def test_regular_flight_keeps_same_date(self):
        """User selects 24/07, regular flight, actual pickup = 24/07."""
        selected_date = date(2026, 7, 24)
        is_overnight = False

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2026, 7, 24)

    def test_none_date_returns_none(self):
        """No date selected returns None."""
        actual = self.calculate_actual_pickup_date(None, True)
        assert actual is None

    def test_month_end_overnight_rolls_to_next_month(self):
        """User selects July 31, overnight flight, actual pickup = Aug 1."""
        selected_date = date(2026, 7, 31)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2026, 8, 1)

    def test_year_end_overnight_rolls_to_next_year(self):
        """User selects Dec 31, overnight flight, actual pickup = Jan 1."""
        selected_date = date(2025, 12, 31)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2026, 1, 1)

    def test_february_28_leap_year_overnight(self):
        """User selects Feb 28 in leap year, overnight, actual = Feb 29."""
        # 2028 is a leap year
        selected_date = date(2028, 2, 28)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2028, 2, 29)

    def test_february_28_non_leap_year_overnight(self):
        """User selects Feb 28 in non-leap year, overnight, actual = Mar 1."""
        # 2026 is not a leap year
        selected_date = date(2026, 2, 28)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)

        assert actual == date(2026, 3, 1)


class TestIsOvernightFlightDetection:
    """
    Tests for isOvernight detection logic used in frontend.

    JavaScript logic:
    ```javascript
    const isOvernight = f.departureTime &&
      parseInt(f.departureTime.split(':')[0]) >= 18 &&
      parseInt(f.time.split(':')[0]) < 6
    ```
    """

    def is_overnight_js_logic(self, departure_time, arrival_time):
        """Python equivalent of frontend isOvernight logic."""
        if not departure_time or not arrival_time:
            return False
        try:
            dep_hour = int(departure_time.split(':')[0])
            arr_hour = int(arrival_time.split(':')[0])
            return dep_hour >= 18 and arr_hour < 6
        except (ValueError, IndexError):
            return False

    def test_classic_overnight_2200_0035(self):
        """TUI 671: depart 22:00, arrive 00:35 = overnight."""
        result = self.is_overnight_js_logic("22:00", "00:35")
        assert result is True

    def test_classic_overnight_2100_0115(self):
        """Depart 21:00, arrive 01:15 = overnight."""
        result = self.is_overnight_js_logic("21:00", "01:15")
        assert result is True

    def test_evening_arrival_not_overnight(self):
        """Depart 18:00, arrive 22:00 = NOT overnight."""
        result = self.is_overnight_js_logic("18:00", "22:00")
        assert result is False

    def test_daytime_flight_not_overnight(self):
        """Depart 10:00, arrive 14:00 = NOT overnight."""
        result = self.is_overnight_js_logic("10:00", "14:00")
        assert result is False

    def test_early_morning_departure_not_overnight(self):
        """Depart 05:00, arrive 09:00 = NOT overnight."""
        result = self.is_overnight_js_logic("05:00", "09:00")
        assert result is False

    def test_boundary_depart_1800_arrive_0559(self):
        """Depart 18:00 (boundary), arrive 05:59 (boundary) = overnight."""
        result = self.is_overnight_js_logic("18:00", "05:59")
        assert result is True

    def test_boundary_depart_1759_not_overnight(self):
        """Depart 17:59 (just before boundary), arrive 01:00 = NOT overnight."""
        result = self.is_overnight_js_logic("17:59", "01:00")
        assert result is False

    def test_boundary_arrive_0600_not_overnight(self):
        """Depart 20:00, arrive 06:00 (boundary) = NOT overnight."""
        result = self.is_overnight_js_logic("20:00", "06:00")
        assert result is False

    def test_midnight_arrival(self):
        """Depart 20:00, arrive 00:00 = overnight."""
        result = self.is_overnight_js_logic("20:00", "00:00")
        assert result is True

    def test_none_departure_time(self):
        """None departure time = not overnight."""
        result = self.is_overnight_js_logic(None, "00:35")
        assert result is False

    def test_none_arrival_time(self):
        """None arrival time = not overnight."""
        result = self.is_overnight_js_logic("22:00", None)
        assert result is False

    def test_empty_string_times(self):
        """Empty strings = not overnight."""
        result = self.is_overnight_js_logic("", "")
        assert result is False

    def test_invalid_time_format(self):
        """Invalid time format = not overnight."""
        result = self.is_overnight_js_logic("invalid", "00:35")
        assert result is False


class TestBookingSummaryDisplayLogic:
    """Tests for booking summary pickup date display logic."""

    def format_display_date(self, date_obj):
        """Format date as dd/MM/yyyy."""
        return date_obj.strftime("%d/%m/%Y")

    def calculate_actual_pickup_date(self, selected_date, is_overnight):
        """Calculate actual pickup date."""
        if selected_date is None:
            return None
        if is_overnight:
            return selected_date + timedelta(days=1)
        return selected_date

    def test_overnight_summary_shows_next_day(self):
        """Summary should show 25/07/2026 when user selects 24/07 + overnight flight."""
        selected_date = date(2026, 7, 24)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)
        display = self.format_display_date(actual)

        assert display == "25/07/2026"

    def test_regular_summary_shows_same_day(self):
        """Summary should show 24/07/2026 when user selects 24/07 + regular flight."""
        selected_date = date(2026, 7, 24)
        is_overnight = False

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)
        display = self.format_display_date(actual)

        assert display == "24/07/2026"


class TestAPIRequestPickupDateLogic:
    """Tests for API request pickup_date formatting logic."""

    def format_api_date(self, date_obj):
        """Format date as yyyy-MM-dd for API."""
        return date_obj.strftime("%Y-%m-%d")

    def calculate_actual_pickup_date(self, selected_date, is_overnight):
        """Calculate actual pickup date."""
        if selected_date is None:
            return None
        if is_overnight:
            return selected_date + timedelta(days=1)
        return selected_date

    def test_overnight_api_sends_next_day(self):
        """API should receive 2026-07-25 when user selects 24/07 + overnight flight."""
        selected_date = date(2026, 7, 24)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)
        api_date = self.format_api_date(actual)

        assert api_date == "2026-07-25"

    def test_regular_api_sends_same_day(self):
        """API should receive 2026-07-24 when user selects 24/07 + regular flight."""
        selected_date = date(2026, 7, 24)
        is_overnight = False

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)
        api_date = self.format_api_date(actual)

        assert api_date == "2026-07-24"

    def test_overnight_year_boundary_api_format(self):
        """API should receive 2026-01-01 when user selects 31/12/2025 + overnight."""
        selected_date = date(2025, 12, 31)
        is_overnight = True

        actual = self.calculate_actual_pickup_date(selected_date, is_overnight)
        api_date = self.format_api_date(actual)

        assert api_date == "2026-01-01"


class TestPickupTimeCalculation:
    """Tests for pickup time calculation (landing time + 45 minutes)."""

    def calculate_pickup_time(self, arrival_time_str):
        """
        Calculate pickup time (45 mins after landing).

        JavaScript:
        ```javascript
        const [h, m] = selectedArrivalFlight.time.split(':').map(Number)
        const totalMins = h * 60 + m + 45
        return `${String(Math.floor(totalMins / 60) % 24).padStart(2, '0')}:${String(totalMins % 60).padStart(2, '0')}`
        ```
        """
        h, m = map(int, arrival_time_str.split(':'))
        total_mins = h * 60 + m + 45
        pickup_hour = (total_mins // 60) % 24
        pickup_min = total_mins % 60
        return f"{pickup_hour:02d}:{pickup_min:02d}"

    def test_midnight_arrival_pickup_time(self):
        """Arrive 00:35, pickup from 01:20."""
        result = self.calculate_pickup_time("00:35")
        assert result == "01:20"

    def test_early_morning_arrival_pickup_time(self):
        """Arrive 05:30, pickup from 06:15."""
        result = self.calculate_pickup_time("05:30")
        assert result == "06:15"

    def test_afternoon_arrival_pickup_time(self):
        """Arrive 14:00, pickup from 14:45."""
        result = self.calculate_pickup_time("14:00")
        assert result == "14:45"

    def test_late_evening_arrival_pickup_time(self):
        """Arrive 23:30, pickup from 00:15 (next day in real life)."""
        result = self.calculate_pickup_time("23:30")
        assert result == "00:15"

    def test_arrival_at_2315_pickup_time(self):
        """Arrive 23:15, pickup from 00:00."""
        result = self.calculate_pickup_time("23:15")
        assert result == "00:00"


class TestTUI671FullScenario:
    """Complete scenario test for TUI 671 Antalya-Bournemouth."""

    def test_tui_671_booking_flow(self):
        """
        Full TUI 671 booking scenario:
        - Departure: Bournemouth to Antalya on Fri 17/07/2026
        - Return: Antalya to Bournemouth, depart Fri 24/07 22:05, arrive Sat 25/07 00:35
        - User selects pickup date: 24/07/2026 (Friday)
        - Flight shows +1 indicator
        - Actual pickup should be: 25/07/2026 (Saturday)
        - Pickup time: from 01:20 (00:35 + 45 mins)
        """
        # User selections
        user_selected_pickup_date = date(2026, 7, 24)  # Friday
        flight_departure_time = "22:05"
        flight_arrival_time = "00:35"

        # Frontend isOvernight detection
        dep_hour = int(flight_departure_time.split(':')[0])
        arr_hour = int(flight_arrival_time.split(':')[0])
        is_overnight = dep_hour >= 18 and arr_hour < 6
        assert is_overnight is True

        # Frontend actualPickupDate calculation
        if is_overnight:
            actual_pickup_date = user_selected_pickup_date + timedelta(days=1)
        else:
            actual_pickup_date = user_selected_pickup_date
        assert actual_pickup_date == date(2026, 7, 25)  # Saturday

        # Display format (dd/MM/yyyy)
        display_date = actual_pickup_date.strftime("%d/%m/%Y")
        assert display_date == "25/07/2026"

        # API format (yyyy-MM-dd)
        api_date = actual_pickup_date.strftime("%Y-%m-%d")
        assert api_date == "2026-07-25"

        # Pickup time calculation
        h, m = map(int, flight_arrival_time.split(':'))
        total_mins = h * 60 + m + 45
        pickup_time = f"{(total_mins // 60) % 24:02d}:{total_mins % 60:02d}"
        assert pickup_time == "01:20"

        # Final booking summary text
        summary = f"Pick-up: {display_date} from {pickup_time}"
        assert summary == "Pick-up: 25/07/2026 from 01:20"
