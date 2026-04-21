"""
Tests for Payroll functionality.

Covers:
- Calculate shift hours (including overnight shifts)
- Monthly payroll aggregation
- Employee payroll view
- Boundary conditions (month start/end, leap years)
- Edge cases (no shifts, multiple shifts per day)
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch
from calendar import monthrange

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Factories
# =============================================================================

def create_mock_user(**kwargs):
    """Factory to create mock user objects."""
    defaults = {
        "id": 1,
        "first_name": "James",
        "last_name": "Carter",
        "email": "james@tagparking.co.uk",
        "phone": "+447700900123",
        "is_admin": False,
        "is_active": True,
        "created_at": datetime.now(),
        "updated_at": None,
        "last_login": None,
    }
    defaults.update(kwargs)
    user = MagicMock()
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


def create_mock_shift(**kwargs):
    """Factory to create mock roster shift objects."""
    from db_models import ShiftType, ShiftStatus

    defaults = {
        "id": 1,
        "staff_id": 1,
        "booking_id": None,
        "date": date(2026, 3, 20),
        "end_date": None,
        "start_time": time(6, 0),
        "end_time": time(14, 0),
        "shift_type": ShiftType.MORNING,
        "status": ShiftStatus.SCHEDULED,
        "notes": "Test shift",
        "created_at": datetime.now(),
        "updated_at": None,
    }
    defaults.update(kwargs)
    # Default end_date to date if not specified
    if defaults.get("end_date") is None:
        defaults["end_date"] = defaults["date"]
    shift = MagicMock()
    for key, value in defaults.items():
        setattr(shift, key, value)

    # Add staff relationship
    if defaults.get("staff_id"):
        shift.staff = create_mock_user(id=defaults["staff_id"])
    else:
        shift.staff = None

    return shift


# =============================================================================
# Unit Tests - Calculate Shift Hours
# =============================================================================

class TestCalculateShiftHours:
    """Unit tests for shift hours calculation."""

    def test_standard_8_hour_shift(self):
        """Standard 8-hour shift (06:00 - 14:00)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(6, 0), time(14, 0))
        assert hours == 8.0

    def test_half_hour_shift(self):
        """30-minute shift."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(9, 0), time(9, 30))
        assert hours == 0.5

    def test_short_45_minute_shift(self):
        """45-minute shift (typical booking shift)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(6, 0), time(6, 45))
        assert hours == 0.75

    def test_full_12_hour_shift(self):
        """Full 12-hour shift."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(7, 0), time(19, 0))
        assert hours == 12.0

    def test_overnight_shift_standard(self):
        """Overnight shift crossing midnight (22:00 - 06:00)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(22, 0), time(6, 0), is_overnight=True)
        assert hours == 8.0

    def test_overnight_shift_short(self):
        """Short overnight shift (23:00 - 01:00)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(23, 0), time(1, 0), is_overnight=True)
        assert hours == 2.0

    def test_overnight_shift_auto_detect(self):
        """Overnight shift auto-detected (end < start)."""
        from routers.roster import calculate_shift_hours

        # Without is_overnight flag, should still detect based on times
        hours = calculate_shift_hours(time(23, 30), time(0, 30))
        assert hours == 1.0

    def test_midnight_start_shift(self):
        """Shift starting at midnight."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(0, 0), time(8, 0))
        assert hours == 8.0

    def test_midnight_end_shift(self):
        """Shift ending at midnight (treated as overnight)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(16, 0), time(0, 0), is_overnight=True)
        assert hours == 8.0

    def test_very_short_15_min_shift(self):
        """Very short 15-minute shift."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(10, 0), time(10, 15))
        assert hours == 0.25

    def test_boundary_exact_hour(self):
        """Boundary test: exactly 1 hour."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(9, 0), time(10, 0))
        assert hours == 1.0

    def test_early_morning_shift(self):
        """Early morning shift (04:00 - 08:00)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(4, 0), time(8, 0))
        assert hours == 4.0

    def test_late_evening_shift(self):
        """Late evening shift (20:00 - 23:30)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(20, 0), time(23, 30))
        assert hours == 3.5


# =============================================================================
# Unit Tests - Month Date Range Calculation
# =============================================================================

class TestMonthDateRange:
    """Unit tests for month date range boundaries."""

    def test_january_has_31_days(self):
        """January should have 31 days."""
        year, month = 2026, 1
        last_day = monthrange(year, month)[1]
        assert last_day == 31

    def test_february_non_leap_year(self):
        """February in non-leap year has 28 days."""
        year, month = 2026, 2  # 2026 is not a leap year
        last_day = monthrange(year, month)[1]
        assert last_day == 28

    def test_february_leap_year(self):
        """February in leap year has 29 days."""
        year, month = 2028, 2  # 2028 is a leap year
        last_day = monthrange(year, month)[1]
        assert last_day == 29

    def test_april_has_30_days(self):
        """April should have 30 days."""
        year, month = 2026, 4
        last_day = monthrange(year, month)[1]
        assert last_day == 30

    def test_december_has_31_days(self):
        """December should have 31 days."""
        year, month = 2026, 12
        last_day = monthrange(year, month)[1]
        assert last_day == 31

    def test_month_start_is_first_day(self):
        """Month start should be the 1st."""
        year, month = 2026, 3
        first_day = date(year, month, 1)
        assert first_day.day == 1

    def test_month_end_matches_monthrange(self):
        """Month end should match monthrange calculation."""
        year, month = 2026, 3
        last_day_num = monthrange(year, month)[1]
        last_day = date(year, month, last_day_num)
        assert last_day == date(2026, 3, 31)


# =============================================================================
# Unit Tests - Payroll Data Aggregation
# =============================================================================

class TestPayrollAggregation:
    """Unit tests for payroll data aggregation logic."""

    def test_single_shift_aggregation(self):
        """Single shift should aggregate correctly."""
        shifts = [
            create_mock_shift(
                id=1,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(6, 0),
                end_time=time(14, 0)
            )
        ]

        from routers.roster import calculate_shift_hours

        total_hours = 0
        total_shifts = 0
        for shift in shifts:
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
            total_hours += hours
            total_shifts += 1

        assert total_shifts == 1
        assert total_hours == 8.0

    def test_multiple_shifts_same_day(self):
        """Multiple shifts on same day should sum correctly."""
        shifts = [
            create_mock_shift(
                id=1,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(6, 0),
                end_time=time(10, 0)
            ),
            create_mock_shift(
                id=2,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(14, 0),
                end_time=time(18, 0)
            ),
            create_mock_shift(
                id=3,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(20, 0),
                end_time=time(22, 0)
            ),
        ]

        from routers.roster import calculate_shift_hours

        total_hours = 0
        for shift in shifts:
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
            total_hours += hours

        assert len(shifts) == 3
        assert total_hours == 10.0  # 4 + 4 + 2

    def test_shifts_across_multiple_days(self):
        """Shifts across multiple days should aggregate correctly."""
        shifts = [
            create_mock_shift(
                id=1,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(9, 0),
                end_time=time(17, 0)
            ),
            create_mock_shift(
                id=2,
                staff_id=1,
                date=date(2026, 3, 16),
                start_time=time(9, 0),
                end_time=time(17, 0)
            ),
            create_mock_shift(
                id=3,
                staff_id=1,
                date=date(2026, 3, 17),
                start_time=time(9, 0),
                end_time=time(13, 0)
            ),
        ]

        from routers.roster import calculate_shift_hours

        total_hours = 0
        for shift in shifts:
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
            total_hours += hours

        assert len(shifts) == 3
        assert total_hours == 20.0  # 8 + 8 + 4

    def test_overnight_shift_aggregation(self):
        """Overnight shift hours should be calculated correctly."""
        shift = create_mock_shift(
            id=1,
            staff_id=1,
            date=date(2026, 3, 15),
            end_date=date(2026, 3, 16),  # Next day
            start_time=time(22, 0),
            end_time=time(6, 0)
        )

        from routers.roster import calculate_shift_hours

        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

        assert is_overnight is True
        assert hours == 8.0

    def test_mixed_regular_and_overnight_shifts(self):
        """Mix of regular and overnight shifts."""
        shifts = [
            create_mock_shift(
                id=1,
                staff_id=1,
                date=date(2026, 3, 15),
                start_time=time(9, 0),
                end_time=time(17, 0)
            ),
            create_mock_shift(
                id=2,
                staff_id=1,
                date=date(2026, 3, 15),
                end_date=date(2026, 3, 16),
                start_time=time(23, 0),
                end_time=time(3, 0)
            ),
        ]

        from routers.roster import calculate_shift_hours

        total_hours = 0
        for shift in shifts:
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
            total_hours += hours

        assert total_hours == 12.0  # 8 + 4

    def test_empty_shifts_list(self):
        """Empty shifts list should return zero totals."""
        shifts = []

        total_hours = 0
        total_shifts = 0
        for shift in shifts:
            total_shifts += 1

        assert total_shifts == 0
        assert total_hours == 0

    def test_rounding_hours(self):
        """Hours should be rounded to 2 decimal places."""
        from routers.roster import calculate_shift_hours

        # 1 hour 20 minutes = 1.333... hours
        hours = calculate_shift_hours(time(10, 0), time(11, 20))
        assert hours == round(hours, 2)
        assert hours == 1.33


# =============================================================================
# Unit Tests - Shift Grouping by Date
# =============================================================================

class TestShiftGroupingByDate:
    """Unit tests for grouping shifts by date for payroll display."""

    def test_group_single_shift(self):
        """Single shift should create one date group."""
        shifts = [
            {"id": 1, "date": "2026-03-15", "start_time": "09:00", "end_time": "17:00", "hours": 8.0}
        ]

        shifts_by_date = {}
        for shift in shifts:
            date_key = shift["date"]
            if date_key not in shifts_by_date:
                shifts_by_date[date_key] = {"date": date_key, "shifts": [], "daily_hours": 0.0}
            shifts_by_date[date_key]["shifts"].append(shift)
            shifts_by_date[date_key]["daily_hours"] += shift["hours"]

        assert len(shifts_by_date) == 1
        assert "2026-03-15" in shifts_by_date
        assert shifts_by_date["2026-03-15"]["daily_hours"] == 8.0

    def test_group_multiple_shifts_same_day(self):
        """Multiple shifts on same day should be in one group."""
        shifts = [
            {"id": 1, "date": "2026-03-15", "start_time": "06:00", "end_time": "10:00", "hours": 4.0},
            {"id": 2, "date": "2026-03-15", "start_time": "14:00", "end_time": "18:00", "hours": 4.0},
            {"id": 3, "date": "2026-03-15", "start_time": "20:00", "end_time": "22:00", "hours": 2.0},
        ]

        shifts_by_date = {}
        for shift in shifts:
            date_key = shift["date"]
            if date_key not in shifts_by_date:
                shifts_by_date[date_key] = {"date": date_key, "shifts": [], "daily_hours": 0.0}
            shifts_by_date[date_key]["shifts"].append(shift)
            shifts_by_date[date_key]["daily_hours"] += shift["hours"]

        assert len(shifts_by_date) == 1
        assert len(shifts_by_date["2026-03-15"]["shifts"]) == 3
        assert shifts_by_date["2026-03-15"]["daily_hours"] == 10.0

    def test_group_shifts_different_days(self):
        """Shifts on different days should be in separate groups."""
        shifts = [
            {"id": 1, "date": "2026-03-15", "start_time": "09:00", "end_time": "17:00", "hours": 8.0},
            {"id": 2, "date": "2026-03-16", "start_time": "09:00", "end_time": "17:00", "hours": 8.0},
            {"id": 3, "date": "2026-03-17", "start_time": "09:00", "end_time": "13:00", "hours": 4.0},
        ]

        shifts_by_date = {}
        for shift in shifts:
            date_key = shift["date"]
            if date_key not in shifts_by_date:
                shifts_by_date[date_key] = {"date": date_key, "shifts": [], "daily_hours": 0.0}
            shifts_by_date[date_key]["shifts"].append(shift)
            shifts_by_date[date_key]["daily_hours"] += shift["hours"]

        assert len(shifts_by_date) == 3
        assert shifts_by_date["2026-03-15"]["daily_hours"] == 8.0
        assert shifts_by_date["2026-03-16"]["daily_hours"] == 8.0
        assert shifts_by_date["2026-03-17"]["daily_hours"] == 4.0

    def test_six_shifts_same_day(self):
        """Up to 6 shifts on the same day (edge case)."""
        shifts = [
            {"id": i, "date": "2026-03-15", "start_time": f"{6+i*2:02d}:00", "end_time": f"{7+i*2:02d}:00", "hours": 1.0}
            for i in range(6)
        ]

        shifts_by_date = {}
        for shift in shifts:
            date_key = shift["date"]
            if date_key not in shifts_by_date:
                shifts_by_date[date_key] = {"date": date_key, "shifts": [], "daily_hours": 0.0}
            shifts_by_date[date_key]["shifts"].append(shift)
            shifts_by_date[date_key]["daily_hours"] += shift["hours"]

        assert len(shifts_by_date) == 1
        assert len(shifts_by_date["2026-03-15"]["shifts"]) == 6
        assert shifts_by_date["2026-03-15"]["daily_hours"] == 6.0


# =============================================================================
# Unit Tests - Staff Payroll Summary
# =============================================================================

class TestStaffPayrollSummary:
    """Unit tests for staff-level payroll summary."""

    def test_single_staff_member(self):
        """Single staff member summary."""
        staff_data = {
            1: {
                "staff_id": 1,
                "staff_name": "James Carter",
                "total_shifts": 10,
                "total_hours": 80.0
            }
        }

        assert len(staff_data) == 1
        assert staff_data[1]["total_hours"] == 80.0
        assert staff_data[1]["total_shifts"] == 10

    def test_multiple_staff_members(self):
        """Multiple staff members summary."""
        staff_data = {
            1: {"staff_id": 1, "staff_name": "James Carter", "total_shifts": 10, "total_hours": 80.0},
            2: {"staff_id": 2, "staff_name": "Sarah Wilson", "total_shifts": 8, "total_hours": 64.0},
            3: {"staff_id": 3, "staff_name": "Mike Brown", "total_shifts": 12, "total_hours": 96.0},
        }

        total_hours = sum(s["total_hours"] for s in staff_data.values())
        total_shifts = sum(s["total_shifts"] for s in staff_data.values())

        assert len(staff_data) == 3
        assert total_hours == 240.0
        assert total_shifts == 30

    def test_staff_with_no_shifts(self):
        """Staff member with no shifts in month."""
        staff_data = {
            1: {"staff_id": 1, "staff_name": "James Carter", "total_shifts": 0, "total_hours": 0.0},
        }

        assert staff_data[1]["total_shifts"] == 0
        assert staff_data[1]["total_hours"] == 0.0

    def test_staff_sorting_by_name(self):
        """Staff should be sortable by name."""
        staff_list = [
            {"staff_id": 3, "staff_name": "Zara Adams", "total_shifts": 5, "total_hours": 40.0},
            {"staff_id": 1, "staff_name": "Alice Brown", "total_shifts": 8, "total_hours": 64.0},
            {"staff_id": 2, "staff_name": "Mike Carter", "total_shifts": 6, "total_hours": 48.0},
        ]

        sorted_staff = sorted(staff_list, key=lambda x: x["staff_name"])

        assert sorted_staff[0]["staff_name"] == "Alice Brown"
        assert sorted_staff[1]["staff_name"] == "Mike Carter"
        assert sorted_staff[2]["staff_name"] == "Zara Adams"


# =============================================================================
# Unit Tests - Time Input Validation (Frontend Logic)
# =============================================================================

class TestTimeInputValidation:
    """Unit tests for 24-hour time input validation (mirroring frontend)."""

    def test_valid_time_format(self):
        """Valid HH:MM format should pass."""
        import re

        def is_valid_time(time_str):
            if not time_str:
                return False
            match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
            if not match:
                return False
            hours = int(match.group(1))
            mins = int(match.group(2))
            return 0 <= hours <= 23 and 0 <= mins <= 59

        assert is_valid_time("09:00") is True
        assert is_valid_time("23:59") is True
        assert is_valid_time("00:00") is True
        assert is_valid_time("6:30") is True

    def test_invalid_time_format(self):
        """Invalid time formats should fail."""
        import re

        def is_valid_time(time_str):
            if not time_str:
                return False
            match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
            if not match:
                return False
            hours = int(match.group(1))
            mins = int(match.group(2))
            return 0 <= hours <= 23 and 0 <= mins <= 59

        assert is_valid_time("24:00") is False  # Invalid hour
        assert is_valid_time("23:60") is False  # Invalid minutes
        assert is_valid_time("9:5") is False    # Invalid format (single digit mins)
        assert is_valid_time("") is False       # Empty string
        assert is_valid_time("9am") is False    # AM/PM format
        assert is_valid_time("25:00") is False  # Out of range

    def test_time_formatting_from_digits(self):
        """Format time from digit-only input (e.g., "2300" -> "23:00")."""

        def format_time_input(value):
            digits = ''.join(c for c in value if c.isdigit())
            if len(digits) == 0:
                return ''
            elif len(digits) <= 2:
                return digits
            elif len(digits) == 3:
                return f"{digits[0]}:{digits[1:]}"
            else:
                return f"{digits[:2]}:{digits[2:4]}"

        assert format_time_input("2300") == "23:00"
        assert format_time_input("0930") == "09:30"
        assert format_time_input("930") == "9:30"
        assert format_time_input("9") == "9"
        assert format_time_input("") == ""

    def test_time_normalization(self):
        """Normalize time to HH:MM format (pad hours)."""

        def normalize_time(time_str):
            if not time_str:
                return ''
            import re
            match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
            if not match:
                return time_str
            hours = match.group(1).zfill(2)
            mins = match.group(2)
            return f"{hours}:{mins}"

        assert normalize_time("9:30") == "09:30"
        assert normalize_time("23:00") == "23:00"
        assert normalize_time("6:00") == "06:00"


# =============================================================================
# Unit Tests - Payslip Download Availability
# =============================================================================

class TestPayslipDownloadAvailability:
    """Unit tests for payslip download date restrictions."""

    def test_can_download_on_last_day_of_month(self):
        """Download should be allowed on last day of month."""
        # March 31, 2026
        year, month = 2026, 3
        today = date(2026, 3, 31)
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        can_download = today >= last_date
        assert can_download is True

    def test_cannot_download_before_last_day(self):
        """Download should be blocked before last day of month."""
        year, month = 2026, 3
        today = date(2026, 3, 15)
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        can_download = today >= last_date
        assert can_download is False

    def test_can_download_after_month_end(self):
        """Download should be allowed after month has ended."""
        year, month = 2026, 3
        today = date(2026, 4, 5)  # In April, requesting March payslip
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        can_download = today >= last_date
        assert can_download is True

    def test_february_leap_year_download(self):
        """February in leap year should allow download on 29th."""
        year, month = 2028, 2  # 2028 is a leap year
        today = date(2028, 2, 29)
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        assert last_day == 29
        can_download = today >= last_date
        assert can_download is True

    def test_february_non_leap_year_download(self):
        """February in non-leap year should allow download on 28th."""
        year, month = 2026, 2  # 2026 is not a leap year
        today = date(2026, 2, 28)
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        assert last_day == 28
        can_download = today >= last_date
        assert can_download is True

    def test_december_year_end(self):
        """December 31st should allow download."""
        year, month = 2026, 12
        today = date(2026, 12, 31)
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)

        assert last_day == 31
        can_download = today >= last_date
        assert can_download is True


# =============================================================================
# Unit Tests - Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for payroll functionality."""

    def test_shift_spanning_midnight_exactly(self):
        """Shift ending exactly at midnight."""
        from routers.roster import calculate_shift_hours

        # 22:00 to 00:00 (2 hours)
        hours = calculate_shift_hours(time(22, 0), time(0, 0), is_overnight=True)
        assert hours == 2.0

    def test_shift_starting_at_midnight(self):
        """Shift starting at midnight."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(0, 0), time(4, 0))
        assert hours == 4.0

    def test_very_long_shift_16_hours(self):
        """Very long shift (16 hours)."""
        from routers.roster import calculate_shift_hours

        # 06:00 to 22:00
        hours = calculate_shift_hours(time(6, 0), time(22, 0))
        assert hours == 16.0

    def test_shift_with_odd_minutes(self):
        """Shift with non-standard minutes (e.g., 07:23 - 15:47)."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(7, 23), time(15, 47))
        expected = 8 + (24/60)  # 8 hours 24 minutes = 8.4 hours
        assert hours == round(expected, 2)

    def test_single_minute_shift(self):
        """Very short 1-minute shift."""
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(10, 0), time(10, 1))
        expected = 1/60  # ~0.017 hours
        assert hours == round(expected, 2)

    def test_inactive_staff_with_historical_shifts(self):
        """Inactive staff member should still have historical shifts counted."""
        staff = create_mock_user(id=1, is_active=False)
        shift = create_mock_shift(staff_id=staff.id)

        # The shift should still exist and be countable
        assert shift.staff_id == 1
        assert staff.is_active is False

    def test_month_boundary_shift_attribution(self):
        """Shift starting on month boundary should be attributed to start date's month."""
        # Shift on March 31st should count for March
        shift = create_mock_shift(
            date=date(2026, 3, 31),
            start_time=time(22, 0),
            end_time=time(6, 0)
        )

        # Month filtering based on start date
        march_start = date(2026, 3, 1)
        march_end = date(2026, 3, 31)

        in_march = march_start <= shift.date <= march_end
        assert in_march is True
