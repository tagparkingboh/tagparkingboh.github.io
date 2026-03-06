"""
Unit tests for time slot calculation logic.

These tests cover the core time slot calculations including
the critical edge case of overnight drop-offs for early morning flights.
"""
import pytest
from datetime import date, time, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use relative dates for future-proof tests
TODAY = date.today()
FUTURE_DATE = TODAY + timedelta(days=90)  # ~3 months from now
FUTURE_DATE_PREV = FUTURE_DATE - timedelta(days=1)  # Day before FUTURE_DATE

from time_slots import (
    calculate_drop_off_datetime,
    calculate_all_slots,
    format_time_display,
    is_overnight_drop_off,
    get_day_name,
    get_drop_off_summary,
    calculate_pickup_datetime,
    is_overnight_pickup,
    get_pickup_summary,
    SlotType,
    SLOT_OFFSETS,
    ARRIVAL_CLEARANCE_BUFFER,
)


class TestCalculateDropOffDatetime:
    """Tests for the calculate_drop_off_datetime function."""

    def test_normal_morning_flight_early_slot(self):
        """Flight at 07:10 with early slot (2h45m before) = 04:25 same day."""
        flight_date = FUTURE_DATE  # Tuesday
        flight_time = time(7, 10)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(4, 25)  # 07:10 - 2:45 = 04:25

    def test_normal_morning_flight_late_slot(self):
        """Flight at 07:10 with late slot (2h before) = 05:10 same day."""
        flight_date = FUTURE_DATE
        flight_time = time(7, 10)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE
        assert drop_off_time == time(5, 10)  # 07:10 - 2:00 = 05:10

    def test_overnight_early_morning_flight_early_slot(self):
        """
        Edge case: Flight at 00:35 Tuesday with early slot.
        00:35 - 2:45 = 21:50 on Monday (previous day).
        """
        flight_date = FUTURE_DATE  # Tuesday
        flight_time = time(0, 35)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == FUTURE_DATE_PREV  # Monday (previous day)
        assert drop_off_time == time(21, 50)  # 00:35 - 2:45 = 21:50

    def test_overnight_early_morning_flight_late_slot(self):
        """
        Edge case: Flight at 00:35 Tuesday with late slot.
        00:35 - 2:00 = 22:35 on Monday (previous day).
        """
        flight_date = FUTURE_DATE  # Tuesday
        flight_time = time(0, 35)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE_PREV  # Monday (previous day)
        assert drop_off_time == time(22, 35)  # 00:35 - 2:00 = 22:35

    def test_midnight_flight_exactly(self):
        """Flight at exactly 00:00 - both slots fall on previous day."""
        flight_date = FUTURE_DATE
        flight_time = time(0, 0)

        # Early slot: 00:00 - 2:45 = 21:15 previous day
        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE_PREV
        assert early_time == time(21, 15)

        # Late slot: 00:00 - 2:00 = 22:00 previous day
        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE_PREV
        assert late_time == time(22, 0)

    def test_boundary_case_2h45m_flight(self):
        """Flight at 02:45 - early slot exactly at midnight."""
        flight_date = FUTURE_DATE
        flight_time = time(2, 45)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(0, 0)  # Exactly midnight

    def test_boundary_case_2h_flight(self):
        """Flight at 02:00 - late slot exactly at midnight."""
        flight_date = FUTURE_DATE
        flight_time = time(2, 0)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(0, 0)  # Exactly midnight

    def test_afternoon_flight(self):
        """Flight at 14:30 - both slots on same day."""
        flight_date = FUTURE_DATE
        flight_time = time(14, 30)

        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE
        assert early_time == time(11, 45)  # 14:30 - 2:45

        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE
        assert late_time == time(12, 30)  # 14:30 - 2:00

    def test_evening_flight(self):
        """Flight at 23:00 - both slots on same day."""
        flight_date = FUTURE_DATE
        flight_time = time(23, 0)

        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE
        assert early_time == time(20, 15)

        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE
        assert late_time == time(21, 0)

    def test_year_boundary_overnight(self):
        """Flight at 00:30 on Jan 1st - drop-off on Dec 31st previous year."""
        year = TODAY.year + 1
        flight_date = date(year, 1, 1)
        flight_time = time(0, 30)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == date(year - 1, 12, 31)  # Previous year
        assert drop_off_time == time(21, 45)

    def test_month_boundary_overnight(self):
        """Flight at 01:00 on March 1st - drop-off on Feb 28th/29th."""
        # Use a future non-leap year March 1st
        year = TODAY.year + 1
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            year += 1  # Skip to non-leap year for consistent test
        flight_date = date(year, 3, 1)
        flight_time = time(1, 0)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == date(year, 2, 28)
        assert drop_off_time == time(22, 15)


class TestCalculateAllSlots:
    """Tests for the calculate_all_slots function."""

    def test_returns_two_slots(self):
        """Should always return exactly two slots."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )
        assert len(slots) == 2

    def test_slot_types_are_correct(self):
        """Should return one early and one late slot."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )

        slot_types = {s.slot_type for s in slots}
        assert slot_types == {SlotType.EARLY, SlotType.LATE}

    def test_slot_ids_are_unique(self):
        """Each slot should have a unique ID."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )

        slot_ids = [s.slot_id for s in slots]
        assert len(slot_ids) == len(set(slot_ids))

    def test_slots_are_marked_available(self):
        """New slots should be marked as available."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )

        for slot in slots:
            assert slot.is_available is True
            assert slot.booking_id is None

    def test_slot_contains_flight_info(self):
        """Slots should contain correct flight information."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )

        for slot in slots:
            assert slot.flight_date == FUTURE_DATE
            assert slot.flight_time == time(10, 0)
            assert slot.flight_number == "5523"
            assert slot.airline_code == "FR"

    def test_overnight_slots_have_different_dates(self):
        """For early morning flights, slots should be on previous day."""
        slots = calculate_all_slots(
            FUTURE_DATE,  # Tuesday
            time(0, 35),
            "5523",
            "FR"
        )

        for slot in slots:
            assert slot.drop_off_date == FUTURE_DATE_PREV  # Monday
            assert slot.flight_date == FUTURE_DATE  # Tuesday


class TestIsOvernightDropOff:
    """Tests for the is_overnight_drop_off function."""

    def test_same_day_not_overnight(self):
        """Drop-off on same day as flight is not overnight."""
        assert is_overnight_drop_off(
            FUTURE_DATE,
            FUTURE_DATE
        ) is False

    def test_previous_day_is_overnight(self):
        """Drop-off on previous day is overnight."""
        assert is_overnight_drop_off(
            FUTURE_DATE,
            FUTURE_DATE_PREV
        ) is True


class TestFormatTimeDisplay:
    """Tests for the format_time_display function."""

    def test_format_normal_time(self):
        assert format_time_display(time(14, 30)) == "14:30"

    def test_format_midnight(self):
        assert format_time_display(time(0, 0)) == "00:00"

    def test_format_with_leading_zeros(self):
        assert format_time_display(time(5, 5)) == "05:05"

    def test_format_end_of_day(self):
        assert format_time_display(time(23, 59)) == "23:59"


class TestGetDayName:
    """Tests for the get_day_name function."""

    def test_future_date_prev_day_name(self):
        """Test that FUTURE_DATE_PREV returns correct day name."""
        expected_day = FUTURE_DATE_PREV.strftime("%A")
        assert get_day_name(FUTURE_DATE_PREV) == expected_day

    def test_future_date_day_name(self):
        """Test that FUTURE_DATE returns correct day name."""
        expected_day = FUTURE_DATE.strftime("%A")
        assert get_day_name(FUTURE_DATE) == expected_day

    def test_sunday(self):
        # Find the next Sunday from FUTURE_DATE
        days_until_sunday = (6 - FUTURE_DATE.weekday()) % 7
        next_sunday = FUTURE_DATE + timedelta(days=days_until_sunday)
        assert get_day_name(next_sunday) == "Sunday"


class TestGetDropOffSummary:
    """Tests for the get_drop_off_summary function."""

    def test_normal_flight_summary(self):
        """Summary for a normal daytime flight."""
        summary = get_drop_off_summary(
            FUTURE_DATE,
            time(10, 0),
            SlotType.EARLY
        )

        assert summary["flight_date"] == FUTURE_DATE.isoformat()
        assert summary["flight_time"] == "10:00"
        assert summary["drop_off_date"] == FUTURE_DATE.isoformat()
        assert summary["drop_off_time"] == "07:15"
        assert summary["is_overnight"] is False
        assert summary["display_message"] is None

    def test_overnight_flight_summary(self):
        """Summary for an early morning flight with overnight drop-off."""
        summary = get_drop_off_summary(
            FUTURE_DATE,
            time(0, 35),
            SlotType.EARLY
        )

        expected_day = FUTURE_DATE.strftime("%A")
        expected_prev_day = FUTURE_DATE_PREV.strftime("%A")

        assert summary["flight_date"] == FUTURE_DATE.isoformat()
        assert summary["flight_day"] == expected_day
        assert summary["drop_off_date"] == FUTURE_DATE_PREV.isoformat()
        assert summary["drop_off_day"] == expected_prev_day
        assert summary["drop_off_time"] == "21:50"
        assert summary["is_overnight"] is True
        assert expected_prev_day in summary["display_message"]
        assert "21:50" in summary["display_message"]

    def test_overnight_late_slot_summary(self):
        """Summary for early morning flight with late slot."""
        summary = get_drop_off_summary(
            FUTURE_DATE,
            time(0, 35),
            SlotType.LATE
        )

        assert summary["drop_off_date"] == FUTURE_DATE_PREV.isoformat()
        assert summary["drop_off_time"] == "22:35"
        assert summary["is_overnight"] is True


class TestSlotOffsets:
    """Tests to verify slot offset constants."""

    def test_early_slot_offset(self):
        """Early slot should be 165 minutes (2h45m)."""
        assert SLOT_OFFSETS[SlotType.EARLY] == 165

    def test_late_slot_offset(self):
        """Late slot should be 120 minutes (2h)."""
        assert SLOT_OFFSETS[SlotType.LATE] == 120


class TestArrivalClearanceBuffer:
    """Tests to verify the arrival clearance buffer constant."""

    def test_clearance_buffer_is_30_minutes(self):
        """Passengers need at least 30 minutes to clear security/immigration."""
        assert ARRIVAL_CLEARANCE_BUFFER == 30


class TestCalculatePickupDatetime:
    """
    Tests for the calculate_pickup_datetime function.

    Passengers arriving won't be past security/immigration for at least
    30 minutes after landing, so pickup time = arrival time + 30 min.
    """

    def test_normal_afternoon_arrival(self):
        """Flight arrives at 14:30, pickup at 15:00 (same day)."""
        arrival_date = FUTURE_DATE  # Tuesday
        arrival_time = time(14, 30)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE  # Same day
        assert pickup_time == time(15, 0)  # 14:30 + 0:30 = 15:00

    def test_morning_arrival(self):
        """Flight arrives at 08:00, pickup at 08:30 (same day)."""
        arrival_date = FUTURE_DATE
        arrival_time = time(8, 0)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE
        assert pickup_time == time(8, 30)

    def test_late_night_arrival_crosses_midnight(self):
        """
        Edge case: Flight arrives at 23:55 on Tuesday.
        23:55 + 0:30 = 00:25 on Wednesday (next day).
        """
        arrival_date = FUTURE_DATE  # Tuesday
        arrival_time = time(23, 55)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE + timedelta(days=1)  # Wednesday (next day)
        assert pickup_time == time(0, 25)  # 23:55 + 0:30 = 00:25

    def test_late_night_arrival_just_crosses_midnight(self):
        """
        Edge case: Flight arrives at 23:30 on Tuesday.
        23:30 + 0:30 = 00:00 on Wednesday.
        """
        arrival_date = FUTURE_DATE  # Tuesday
        arrival_time = time(23, 30)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE + timedelta(days=1)  # Wednesday
        assert pickup_time == time(0, 0)  # 23:30 + 0:30 = 00:00

    def test_arrival_exactly_at_2330_boundary(self):
        """
        Boundary case: Flight arrives at 23:30.
        23:30 + 0:30 = 00:00 exactly midnight (next day).
        """
        arrival_date = FUTURE_DATE
        arrival_time = time(23, 30)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE + timedelta(days=1)  # Next day
        assert pickup_time == time(0, 0)  # Exactly midnight

    def test_arrival_at_2329_stays_same_day(self):
        """
        Boundary case: Flight arrives at 23:29.
        23:29 + 0:30 = 23:59 (same day, just before midnight).
        """
        arrival_date = FUTURE_DATE
        arrival_time = time(23, 29)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE  # Same day
        assert pickup_time == time(23, 59)

    def test_year_boundary_overnight_pickup(self):
        """
        Edge case: Flight arrives at 23:45 on Dec 31st.
        Pickup at 00:15 on Jan 1st (next year).
        """
        year = TODAY.year
        arrival_date = date(year, 12, 31)
        arrival_time = time(23, 45)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == date(year + 1, 1, 1)  # Next year
        assert pickup_time == time(0, 15)

    def test_month_boundary_overnight_pickup(self):
        """
        Edge case: Flight arrives at 23:40 on Feb 28th.
        Pickup at 00:10 on March 1st.
        """
        # Use a future non-leap year for consistent test
        year = TODAY.year + 1
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            year += 1  # Skip to non-leap year
        arrival_date = date(year, 2, 28)
        arrival_time = time(23, 40)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == date(year, 3, 1)  # March 1st
        assert pickup_time == time(0, 10)

    def test_midnight_arrival(self):
        """Flight arriving at exactly 00:00, pickup at 00:30 same day."""
        arrival_date = FUTURE_DATE
        arrival_time = time(0, 0)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE  # Same day
        assert pickup_time == time(0, 30)


class TestIsOvernightPickup:
    """Tests for the is_overnight_pickup function."""

    def test_same_day_not_overnight(self):
        """Pickup on same day as arrival is not overnight."""
        assert is_overnight_pickup(
            FUTURE_DATE,
            FUTURE_DATE
        ) is False

    def test_next_day_is_overnight(self):
        """Pickup on next day is overnight."""
        assert is_overnight_pickup(
            FUTURE_DATE,
            FUTURE_DATE + timedelta(days=1)
        ) is True


class TestGetPickupSummary:
    """Tests for the get_pickup_summary function."""

    def test_normal_daytime_arrival_summary(self):
        """Summary for a normal daytime arrival."""
        summary = get_pickup_summary(
            FUTURE_DATE,
            time(14, 30)
        )

        assert summary["arrival_date"] == FUTURE_DATE.isoformat()
        assert summary["arrival_time"] == "14:30"
        assert summary["pickup_date"] == FUTURE_DATE.isoformat()
        assert summary["pickup_time"] == "15:00"
        assert summary["clearance_buffer_minutes"] == 30
        assert summary["is_overnight"] is False
        assert "15:00" in summary["display_message"]
        assert "30 minutes" in summary["display_message"]

    def test_late_night_arrival_overnight_summary(self):
        """
        Summary for late night arrival (23:55) crossing midnight.
        Should show pickup on next day with appropriate warning.
        """
        next_day = FUTURE_DATE + timedelta(days=1)
        summary = get_pickup_summary(
            FUTURE_DATE,
            time(23, 55)
        )

        expected_day = FUTURE_DATE.strftime("%A")
        expected_next_day = next_day.strftime("%A")

        assert summary["arrival_date"] == FUTURE_DATE.isoformat()
        assert summary["arrival_day"] == expected_day
        assert summary["arrival_time"] == "23:55"
        assert summary["pickup_date"] == next_day.isoformat()
        assert summary["pickup_day"] == expected_next_day
        assert summary["pickup_time"] == "00:25"
        assert summary["is_overnight"] is True
        assert expected_next_day in summary["display_message"]
        assert "after midnight" in summary["display_message"]

    def test_2330_arrival_overnight_summary(self):
        """
        Summary for 23:30 arrival crossing midnight.
        Pickup at 00:00 next day.
        """
        next_day = FUTURE_DATE + timedelta(days=1)
        summary = get_pickup_summary(
            FUTURE_DATE,
            time(23, 30)
        )

        expected_next_day = next_day.strftime("%A")

        assert summary["pickup_date"] == next_day.isoformat()
        assert summary["pickup_time"] == "00:00"
        assert summary["is_overnight"] is True
        assert expected_next_day in summary["display_message"]

    def test_evening_arrival_same_day(self):
        """Evening arrival (21:00) stays on same day."""
        summary = get_pickup_summary(
            FUTURE_DATE,
            time(21, 0)
        )

        assert summary["pickup_date"] == FUTURE_DATE.isoformat()
        assert summary["pickup_time"] == "21:30"
        assert summary["is_overnight"] is False
