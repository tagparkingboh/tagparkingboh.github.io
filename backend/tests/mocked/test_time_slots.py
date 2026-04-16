"""
Mocked unit tests for time slot calculation logic.

These tests cover the core time slot calculations including
the critical edge case of overnight drop-offs for early morning flights.

No database connection required.
"""
import pytest
from datetime import date, time, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
    SLOT_OFFSETS,
    ARRIVAL_CLEARANCE_BUFFER,
)
from models import SlotType


class TestCalculateDropOffDatetime:
    """Tests for the calculate_drop_off_datetime function."""

    def test_normal_morning_flight_early_slot(self):
        """Flight at 07:10 with early slot (2.75h before) = 04:25 same day."""
        flight_date = FUTURE_DATE
        flight_time = time(7, 10)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(4, 25)  # 07:10 - 2:45 = 04:25

    def test_normal_morning_flight_standard_slot(self):
        """Flight at 07:10 with standard slot (2h before) = 05:10 same day."""
        flight_date = FUTURE_DATE
        flight_time = time(7, 10)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )

        assert drop_off_date == FUTURE_DATE
        assert drop_off_time == time(5, 10)  # 07:10 - 2:00 = 05:10

    def test_normal_morning_flight_late_slot(self):
        """Flight at 07:10 with late slot (1.5h before) = 05:40 same day."""
        flight_date = FUTURE_DATE
        flight_time = time(7, 10)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE
        assert drop_off_time == time(5, 40)  # 07:10 - 1:30 = 05:40

    def test_overnight_early_morning_flight_early_slot(self):
        """
        Edge case: Flight at 00:35 Tuesday with early slot.
        00:35 - 2:45 = 21:50 on Monday (previous day).
        """
        flight_date = FUTURE_DATE
        flight_time = time(0, 35)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )

        assert drop_off_date == FUTURE_DATE_PREV  # Previous day
        assert drop_off_time == time(21, 50)  # 00:35 - 2:45 = 21:50

    def test_overnight_early_morning_flight_standard_slot(self):
        """
        Edge case: Flight at 00:35 Tuesday with standard slot.
        00:35 - 2:00 = 22:35 on Monday (previous day).
        """
        flight_date = FUTURE_DATE
        flight_time = time(0, 35)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )

        assert drop_off_date == FUTURE_DATE_PREV  # Previous day
        assert drop_off_time == time(22, 35)  # 00:35 - 2:00 = 22:35

    def test_overnight_early_morning_flight_late_slot(self):
        """
        Edge case: Flight at 00:35 Tuesday with late slot.
        00:35 - 1:30 = 23:05 on Monday (previous day).
        """
        flight_date = FUTURE_DATE
        flight_time = time(0, 35)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE_PREV  # Previous day
        assert drop_off_time == time(23, 5)  # 00:35 - 1:30 = 23:05

    def test_midnight_flight_exactly(self):
        """Flight at exactly 00:00 - all slots fall on previous day."""
        flight_date = FUTURE_DATE
        flight_time = time(0, 0)

        # Early slot: 00:00 - 2:45 = 21:15 previous day
        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE_PREV
        assert early_time == time(21, 15)

        # Standard slot: 00:00 - 2:00 = 22:00 previous day
        standard_date, standard_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )
        assert standard_date == FUTURE_DATE_PREV
        assert standard_time == time(22, 0)

        # Late slot: 00:00 - 1:30 = 22:30 previous day
        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE_PREV
        assert late_time == time(22, 30)

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
        """Flight at 02:00 - standard slot exactly at midnight."""
        flight_date = FUTURE_DATE
        flight_time = time(2, 0)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(0, 0)  # Exactly midnight

    def test_boundary_case_1h30m_flight(self):
        """Flight at 01:30 - late slot exactly at midnight."""
        flight_date = FUTURE_DATE
        flight_time = time(1, 30)

        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )

        assert drop_off_date == FUTURE_DATE  # Same day
        assert drop_off_time == time(0, 0)  # Exactly midnight

    def test_afternoon_flight(self):
        """Flight at 14:30 - all slots on same day."""
        flight_date = FUTURE_DATE
        flight_time = time(14, 30)

        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE
        assert early_time == time(11, 45)  # 14:30 - 2:45

        standard_date, standard_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )
        assert standard_date == FUTURE_DATE
        assert standard_time == time(12, 30)  # 14:30 - 2:00

        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE
        assert late_time == time(13, 0)  # 14:30 - 1:30

    def test_evening_flight(self):
        """Flight at 23:00 - all slots on same day."""
        flight_date = FUTURE_DATE
        flight_time = time(23, 0)

        early_date, early_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.EARLY
        )
        assert early_date == FUTURE_DATE
        assert early_time == time(20, 15)  # 23:00 - 2:45

        standard_date, standard_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.STANDARD
        )
        assert standard_date == FUTURE_DATE
        assert standard_time == time(21, 0)  # 23:00 - 2:00

        late_date, late_time = calculate_drop_off_datetime(
            flight_date, flight_time, SlotType.LATE
        )
        assert late_date == FUTURE_DATE
        assert late_time == time(21, 30)  # 23:00 - 1:30


class TestCalculateAllSlots:
    """Tests for the calculate_all_slots function."""

    def test_returns_three_slots(self):
        """Should always return exactly three slots."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )
        assert len(slots) == 3

    def test_slot_types_are_correct(self):
        """Should return one early, one standard, and one late slot."""
        slots = calculate_all_slots(
            FUTURE_DATE,
            time(10, 0),
            "5523",
            "FR"
        )

        slot_types = {s.slot_type for s in slots}
        assert slot_types == {SlotType.EARLY, SlotType.STANDARD, SlotType.LATE}

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


class TestSlotOffsets:
    """Tests to verify slot offset constants."""

    def test_early_slot_offset(self):
        """Early slot should be 165 minutes (2.75h)."""
        assert SLOT_OFFSETS[SlotType.EARLY] == 165

    def test_standard_slot_offset(self):
        """Standard slot should be 120 minutes (2h)."""
        assert SLOT_OFFSETS[SlotType.STANDARD] == 120

    def test_late_slot_offset(self):
        """Late slot should be 90 minutes (1.5h)."""
        assert SLOT_OFFSETS[SlotType.LATE] == 90


class TestFormatTimeDisplay:
    """Tests for the format_time_display function."""

    def test_format_normal_time(self):
        assert format_time_display(time(14, 30)) == "14:30"

    def test_format_midnight(self):
        assert format_time_display(time(0, 0)) == "00:00"

    def test_format_with_leading_zeros(self):
        assert format_time_display(time(5, 5)) == "05:05"


class TestIsOvernightDropOff:
    """Tests for the is_overnight_drop_off function."""

    def test_same_day_not_overnight(self):
        """Drop-off on same day as flight is not overnight."""
        assert is_overnight_drop_off(FUTURE_DATE, FUTURE_DATE) is False

    def test_previous_day_is_overnight(self):
        """Drop-off on previous day is overnight."""
        assert is_overnight_drop_off(FUTURE_DATE, FUTURE_DATE_PREV) is True


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
        assert summary["drop_off_time"] == "07:15"  # 10:00 - 2:45 = 07:15
        assert summary["is_overnight"] is False

    def test_overnight_flight_summary(self):
        """Summary for an early morning flight with overnight drop-off."""
        summary = get_drop_off_summary(
            FUTURE_DATE,
            time(0, 35),
            SlotType.EARLY
        )

        assert summary["drop_off_date"] == FUTURE_DATE_PREV.isoformat()
        assert summary["drop_off_time"] == "21:50"  # 00:35 - 2:45 = 21:50
        assert summary["is_overnight"] is True


class TestPickupDatetime:
    """Tests for pickup time calculations."""

    def test_normal_afternoon_arrival(self):
        """Flight arrives at 14:30, pickup at 15:00 (same day)."""
        arrival_date = FUTURE_DATE
        arrival_time = time(14, 30)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE
        assert pickup_time == time(15, 0)  # 14:30 + 0:30 = 15:00

    def test_late_night_arrival_crosses_midnight(self):
        """Flight arrives at 23:55 - pickup crosses midnight."""
        arrival_date = FUTURE_DATE
        arrival_time = time(23, 55)

        pickup_date, pickup_time = calculate_pickup_datetime(
            arrival_date, arrival_time
        )

        assert pickup_date == FUTURE_DATE + timedelta(days=1)  # Next day
        assert pickup_time == time(0, 25)  # 23:55 + 0:30 = 00:25

    def test_clearance_buffer(self):
        """Verify arrival clearance buffer is 30 minutes."""
        assert ARRIVAL_CLEARANCE_BUFFER == 30
