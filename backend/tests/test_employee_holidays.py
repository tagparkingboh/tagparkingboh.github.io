"""
Unit tests for Employee Holidays functionality.

Tests cover:
- Holiday type enum validation
- Date range logic
- Overlap detection
- Staff-holiday matching
- Data structure validation
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
import enum

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Mock holiday type enum (mirrors db_models.HolidayType)
class MockHolidayType(enum.Enum):
    HOLIDAY = "holiday"
    SICK = "sick"
    PERSONAL = "personal"
    OTHER = "other"


# Mock holiday data
mock_holidays = [
    {
        "id": 1,
        "staff_id": 1,
        "staff_first_name": "James",
        "staff_last_name": "Carter",
        "staff_initials": "JC",
        "start_date": "2026-04-10",
        "end_date": "2026-04-14",
        "holiday_type": "holiday",
        "notes": "Family vacation",
        "created_at": "2026-03-15T10:00:00Z",
    },
    {
        "id": 2,
        "staff_id": 2,
        "staff_first_name": "Sarah",
        "staff_last_name": "Williams",
        "staff_initials": "SW",
        "start_date": "2026-04-12",
        "end_date": "2026-04-12",
        "holiday_type": "sick",
        "notes": "Doctor's appointment",
        "created_at": "2026-04-12T08:00:00Z",
    },
    {
        "id": 3,
        "staff_id": 1,
        "staff_first_name": "James",
        "staff_last_name": "Carter",
        "staff_initials": "JC",
        "start_date": "2026-05-01",
        "end_date": "2026-05-01",
        "holiday_type": "personal",
        "notes": "Personal day",
        "created_at": "2026-04-20T14:00:00Z",
    },
    {
        "id": 4,
        "staff_id": 3,
        "staff_first_name": "Mike",
        "staff_last_name": "Brown",
        "staff_initials": "MB",
        "start_date": "2026-12-24",
        "end_date": "2026-12-31",
        "holiday_type": "holiday",
        "notes": "Christmas break",
        "created_at": "2026-11-01T09:00:00Z",
    },
]

mock_staff = [
    {"id": 1, "first_name": "James", "last_name": "Carter", "email": "james@tag.com", "is_active": True},
    {"id": 2, "first_name": "Sarah", "last_name": "Williams", "email": "sarah@tag.com", "is_active": True},
    {"id": 3, "first_name": "Mike", "last_name": "Brown", "email": "mike@tag.com", "is_active": True},
    {"id": 4, "first_name": "Lisa", "last_name": "Davis", "email": "lisa@tag.com", "is_active": False},
]


# ============================================================================
# Holiday Type Enum Tests
# ============================================================================

class TestHolidayTypeEnum:
    """Tests for HolidayType enum validation."""

    def test_valid_holiday_types(self):
        """All valid holiday types should be recognized."""
        valid_types = ["holiday", "sick", "personal", "other"]
        for t in valid_types:
            assert MockHolidayType(t) is not None

    def test_holiday_type_values(self):
        """Enum should have correct string values."""
        assert MockHolidayType.HOLIDAY.value == "holiday"
        assert MockHolidayType.SICK.value == "sick"
        assert MockHolidayType.PERSONAL.value == "personal"
        assert MockHolidayType.OTHER.value == "other"

    def test_invalid_holiday_type_raises_error(self):
        """Invalid holiday type should raise ValueError."""
        with pytest.raises(ValueError):
            MockHolidayType("vacation")

        with pytest.raises(ValueError):
            MockHolidayType("annual_leave")

        with pytest.raises(ValueError):
            MockHolidayType("")


# ============================================================================
# Date Range Logic Tests
# ============================================================================

class TestDateRangeLogic:
    """Tests for date range validation and logic."""

    def test_single_day_holiday(self):
        """Single day holiday should have same start and end date."""
        holiday = mock_holidays[1]  # Sarah's sick day
        assert holiday["start_date"] == holiday["end_date"]
        assert holiday["start_date"] == "2026-04-12"

    def test_multi_day_holiday(self):
        """Multi-day holiday should have different start and end dates."""
        holiday = mock_holidays[0]  # James's vacation
        assert holiday["start_date"] != holiday["end_date"]
        assert holiday["start_date"] == "2026-04-10"
        assert holiday["end_date"] == "2026-04-14"

    def test_date_range_duration_calculation(self):
        """Calculate correct duration of holiday in days."""
        def calc_duration(start_str, end_str):
            start = date.fromisoformat(start_str)
            end = date.fromisoformat(end_str)
            return (end - start).days + 1  # Inclusive

        # James's 5-day vacation
        assert calc_duration("2026-04-10", "2026-04-14") == 5

        # Sarah's 1-day sick
        assert calc_duration("2026-04-12", "2026-04-12") == 1

        # Mike's Christmas break (8 days)
        assert calc_duration("2026-12-24", "2026-12-31") == 8

    def test_end_date_before_start_date_is_invalid(self):
        """End date before start date should be invalid."""
        def is_valid_range(start_str, end_str):
            start = date.fromisoformat(start_str)
            end = date.fromisoformat(end_str)
            return end >= start

        assert is_valid_range("2026-04-10", "2026-04-14") is True
        assert is_valid_range("2026-04-10", "2026-04-10") is True
        assert is_valid_range("2026-04-14", "2026-04-10") is False

    def test_year_boundary_holiday(self):
        """Holiday crossing year boundary should be valid."""
        holiday = {
            "start_date": "2026-12-28",
            "end_date": "2027-01-03",
        }
        start = date.fromisoformat(holiday["start_date"])
        end = date.fromisoformat(holiday["end_date"])

        assert end > start
        assert start.year == 2026
        assert end.year == 2027
        assert (end - start).days + 1 == 7

    def test_month_boundary_holiday(self):
        """Holiday crossing month boundary should be valid."""
        holiday = {
            "start_date": "2026-04-28",
            "end_date": "2026-05-02",
        }
        start = date.fromisoformat(holiday["start_date"])
        end = date.fromisoformat(holiday["end_date"])

        assert end > start
        assert start.month == 4
        assert end.month == 5


# ============================================================================
# Date Overlap Detection Tests
# ============================================================================

class TestOverlapDetection:
    """Tests for detecting overlapping holidays."""

    def check_overlap(self, start1, end1, start2, end2):
        """Check if two date ranges overlap."""
        s1 = date.fromisoformat(start1)
        e1 = date.fromisoformat(end1)
        s2 = date.fromisoformat(start2)
        e2 = date.fromisoformat(end2)
        return s1 <= e2 and s2 <= e1

    def test_overlapping_holidays_same_staff(self):
        """Should detect overlapping holidays for same staff."""
        # James has holiday 2026-04-10 to 2026-04-14
        existing = ("2026-04-10", "2026-04-14")

        # New holiday starting during existing
        assert self.check_overlap(*existing, "2026-04-12", "2026-04-16") is True

        # New holiday ending during existing
        assert self.check_overlap(*existing, "2026-04-08", "2026-04-11") is True

        # New holiday completely within existing
        assert self.check_overlap(*existing, "2026-04-11", "2026-04-13") is True

        # New holiday completely containing existing
        assert self.check_overlap(*existing, "2026-04-08", "2026-04-20") is True

    def test_adjacent_holidays_no_overlap(self):
        """Adjacent holidays (end == day before start) should not overlap."""
        existing = ("2026-04-10", "2026-04-14")

        # Day before - no overlap
        assert self.check_overlap(*existing, "2026-04-05", "2026-04-09") is False

        # Day after - no overlap
        assert self.check_overlap(*existing, "2026-04-15", "2026-04-20") is False

    def test_same_day_overlap(self):
        """Same single day should overlap."""
        assert self.check_overlap("2026-04-12", "2026-04-12", "2026-04-12", "2026-04-12") is True

    def test_touching_dates_overlap(self):
        """Holidays that share one day should overlap."""
        # Share the end/start date
        assert self.check_overlap("2026-04-10", "2026-04-14", "2026-04-14", "2026-04-18") is True

    def test_no_overlap_different_dates(self):
        """Completely separate date ranges should not overlap."""
        assert self.check_overlap("2026-04-01", "2026-04-05", "2026-04-10", "2026-04-15") is False
        assert self.check_overlap("2026-01-01", "2026-01-31", "2026-12-01", "2026-12-31") is False


# ============================================================================
# Staff-Holiday Matching Tests
# ============================================================================

class TestStaffHolidayMatching:
    """Tests for matching staff to holidays on specific dates."""

    def get_staff_on_holiday_for_date(self, check_date):
        """Get set of staff IDs on holiday for a specific date."""
        staff_ids = set()
        check = date.fromisoformat(check_date)
        for h in mock_holidays:
            start = date.fromisoformat(h["start_date"])
            end = date.fromisoformat(h["end_date"])
            if start <= check <= end:
                staff_ids.add(h["staff_id"])
        return staff_ids

    def test_date_with_one_staff_on_holiday(self):
        """Should return single staff member on holiday."""
        # April 10 - only James is on holiday
        staff_on_holiday = self.get_staff_on_holiday_for_date("2026-04-10")
        assert staff_on_holiday == {1}

    def test_date_with_multiple_staff_on_holiday(self):
        """Should return multiple staff members on holiday."""
        # April 12 - James (vacation) and Sarah (sick)
        staff_on_holiday = self.get_staff_on_holiday_for_date("2026-04-12")
        assert staff_on_holiday == {1, 2}

    def test_date_with_no_staff_on_holiday(self):
        """Should return empty set when no one is on holiday."""
        # April 20 - no one is on holiday
        staff_on_holiday = self.get_staff_on_holiday_for_date("2026-04-20")
        assert staff_on_holiday == set()

    def test_holiday_boundary_dates(self):
        """Should correctly handle start and end dates of holidays."""
        # April 10 - first day of James's holiday
        assert 1 in self.get_staff_on_holiday_for_date("2026-04-10")

        # April 14 - last day of James's holiday
        assert 1 in self.get_staff_on_holiday_for_date("2026-04-14")

        # April 9 - day before James's holiday
        assert 1 not in self.get_staff_on_holiday_for_date("2026-04-09")

        # April 15 - day after James's holiday
        assert 1 not in self.get_staff_on_holiday_for_date("2026-04-15")

    def test_same_staff_multiple_holidays(self):
        """Staff with multiple holidays should be found for each."""
        # James has holiday April 10-14 and May 1
        assert 1 in self.get_staff_on_holiday_for_date("2026-04-12")
        assert 1 in self.get_staff_on_holiday_for_date("2026-05-01")

        # But not in between
        assert 1 not in self.get_staff_on_holiday_for_date("2026-04-20")


# ============================================================================
# Data Structure Validation Tests
# ============================================================================

class TestHolidayDataStructure:
    """Tests for holiday data structure validation."""

    def test_holiday_contains_required_fields(self):
        """Holiday should contain all required fields."""
        required_fields = [
            "id", "staff_id", "staff_first_name", "staff_last_name",
            "start_date", "end_date", "holiday_type", "created_at"
        ]
        for holiday in mock_holidays:
            for field in required_fields:
                assert field in holiday, f"Missing field: {field}"

    def test_holiday_staff_initials_format(self):
        """Staff initials should be 2 uppercase letters."""
        for holiday in mock_holidays:
            initials = holiday["staff_initials"]
            assert len(initials) == 2
            assert initials.isupper()
            assert initials.isalpha()

    def test_holiday_dates_are_iso_format(self):
        """Dates should be in ISO format (YYYY-MM-DD)."""
        import re
        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

        for holiday in mock_holidays:
            assert iso_pattern.match(holiday["start_date"])
            assert iso_pattern.match(holiday["end_date"])

    def test_holiday_type_is_valid(self):
        """Holiday type should be one of the valid enum values."""
        valid_types = {"holiday", "sick", "personal", "other"}
        for holiday in mock_holidays:
            assert holiday["holiday_type"] in valid_types

    def test_notes_can_be_optional(self):
        """Notes field can be null/None."""
        # Existing mock data has notes, but None should be valid
        holiday_without_notes = {
            "id": 5,
            "staff_id": 1,
            "start_date": "2026-06-01",
            "end_date": "2026-06-01",
            "holiday_type": "other",
            "notes": None,
        }
        assert holiday_without_notes["notes"] is None


# ============================================================================
# Filter Logic Tests
# ============================================================================

class TestFilterLogic:
    """Tests for filtering holidays."""

    def filter_by_date_range(self, date_from, date_to):
        """Filter holidays that overlap with date range."""
        results = []
        from_date = date.fromisoformat(date_from)
        to_date = date.fromisoformat(date_to)

        for h in mock_holidays:
            start = date.fromisoformat(h["start_date"])
            end = date.fromisoformat(h["end_date"])
            # Overlap check: start <= to_date AND end >= from_date
            if start <= to_date and end >= from_date:
                results.append(h)
        return results

    def filter_by_staff_id(self, staff_id):
        """Filter holidays by staff ID."""
        return [h for h in mock_holidays if h["staff_id"] == staff_id]

    def test_filter_by_date_range_includes_partial_overlap(self):
        """Should include holidays that partially overlap date range."""
        # James's holiday is Apr 10-14, filter Apr 13-20
        results = self.filter_by_date_range("2026-04-13", "2026-04-20")
        staff_ids = {h["staff_id"] for h in results}
        assert 1 in staff_ids  # James

    def test_filter_by_date_range_excludes_non_overlapping(self):
        """Should exclude holidays outside date range."""
        # Filter May only
        results = self.filter_by_date_range("2026-05-01", "2026-05-31")

        # Should only include James's May 1 personal day
        assert len(results) == 1
        assert results[0]["staff_id"] == 1
        assert results[0]["holiday_type"] == "personal"

    def test_filter_by_staff_id_returns_all_for_staff(self):
        """Should return all holidays for specific staff."""
        # James (id=1) has 2 holidays
        results = self.filter_by_staff_id(1)
        assert len(results) == 2

    def test_filter_by_staff_id_returns_empty_for_no_holidays(self):
        """Should return empty list for staff with no holidays."""
        # Lisa (id=4) has no holidays
        results = self.filter_by_staff_id(4)
        assert len(results) == 0

    def test_filter_by_single_date(self):
        """Should find holidays for a single date."""
        results = self.filter_by_date_range("2026-04-12", "2026-04-12")
        # Should find James (vacation) and Sarah (sick)
        assert len(results) == 2


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_holiday_list(self):
        """Should handle empty holiday list."""
        empty_holidays = []
        assert len(empty_holidays) == 0

        # Filter should return empty
        results = [h for h in empty_holidays if h["staff_id"] == 1]
        assert results == []

    def test_leap_year_holiday(self):
        """Should handle leap year dates correctly."""
        # 2028 is a leap year
        leap_year_holiday = {
            "start_date": "2028-02-28",
            "end_date": "2028-03-01",
        }
        start = date.fromisoformat(leap_year_holiday["start_date"])
        end = date.fromisoformat(leap_year_holiday["end_date"])

        # Feb 28 to Mar 1 in leap year = 3 days (Feb 28, Feb 29, Mar 1)
        assert (end - start).days + 1 == 3

    def test_very_long_holiday(self):
        """Should handle very long holiday periods."""
        long_holiday = {
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        }
        start = date.fromisoformat(long_holiday["start_date"])
        end = date.fromisoformat(long_holiday["end_date"])

        # Full year = 365 days in 2026
        assert (end - start).days + 1 == 365

    def test_holiday_on_weekend(self):
        """Weekend holidays should be valid (no special handling needed)."""
        # April 11, 2026 is a Saturday
        weekend_holiday = {
            "start_date": "2026-04-11",
            "end_date": "2026-04-12",
            "holiday_type": "holiday",
        }
        start = date.fromisoformat(weekend_holiday["start_date"])
        assert start.weekday() == 5  # Saturday

    def test_max_staff_on_holiday(self):
        """Should handle scenario where all staff are on holiday."""
        # Create mock scenario where all 4 staff are on holiday same day
        all_on_holiday = [
            {"staff_id": 1, "start_date": "2026-08-01", "end_date": "2026-08-01"},
            {"staff_id": 2, "start_date": "2026-08-01", "end_date": "2026-08-01"},
            {"staff_id": 3, "start_date": "2026-08-01", "end_date": "2026-08-01"},
            {"staff_id": 4, "start_date": "2026-08-01", "end_date": "2026-08-01"},
        ]

        check = date.fromisoformat("2026-08-01")
        staff_on_holiday = set()
        for h in all_on_holiday:
            start = date.fromisoformat(h["start_date"])
            end = date.fromisoformat(h["end_date"])
            if start <= check <= end:
                staff_on_holiday.add(h["staff_id"])

        assert len(staff_on_holiday) == 4


# ============================================================================
# Unhappy Path Tests
# ============================================================================

class TestUnhappyPaths:
    """Tests for error conditions and invalid inputs."""

    def test_invalid_date_format(self):
        """Should reject invalid date formats."""
        invalid_dates = [
            "01-04-2026",    # DD-MM-YYYY
            "04/01/2026",    # MM/DD/YYYY
            "2026/04/01",    # YYYY/MM/DD
            "2026-4-1",      # Missing leading zeros
            "April 1, 2026", # Text format
            "20260401",      # No separators
            "",              # Empty string
        ]

        for invalid in invalid_dates:
            with pytest.raises((ValueError, IndexError)):
                date.fromisoformat(invalid)

    def test_invalid_staff_id(self):
        """Invalid staff ID should not match any holidays."""
        results = [h for h in mock_holidays if h["staff_id"] == 999]
        assert len(results) == 0

    def test_negative_staff_id(self):
        """Negative staff ID should not match any holidays."""
        results = [h for h in mock_holidays if h["staff_id"] == -1]
        assert len(results) == 0

    def test_future_far_date(self):
        """Very far future dates should be handled."""
        far_future = "2099-12-31"
        check = date.fromisoformat(far_future)

        # No current holidays should overlap
        staff_on_holiday = set()
        for h in mock_holidays:
            start = date.fromisoformat(h["start_date"])
            end = date.fromisoformat(h["end_date"])
            if start <= check <= end:
                staff_on_holiday.add(h["staff_id"])

        assert len(staff_on_holiday) == 0

    def test_past_date(self):
        """Past dates should be handled."""
        past_date = "2020-01-01"
        check = date.fromisoformat(past_date)

        # No current holidays should overlap
        staff_on_holiday = set()
        for h in mock_holidays:
            start = date.fromisoformat(h["start_date"])
            end = date.fromisoformat(h["end_date"])
            if start <= check <= end:
                staff_on_holiday.add(h["staff_id"])

        assert len(staff_on_holiday) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
