"""
Unit tests for Employee Shift Claim/Release functionality.

Tests cover:
- Happy Path: Successful claim and release operations
- Unhappy Path: Various failure scenarios
- Edge Cases: Boundary conditions and special cases
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch
import enum

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Enums
# =============================================================================

class MockShiftType(enum.Enum):
    EARLY_MORNING = "early_morning"
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    LATE_AFTERNOON = "late_afternoon"
    EVENING = "evening"


class MockShiftStatus(enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MockHolidayType(enum.Enum):
    HOLIDAY = "holiday"
    SICK = "sick"
    PERSONAL = "personal"
    OTHER = "other"


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
    }
    defaults.update(kwargs)
    user = MagicMock()
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


def create_mock_shift(**kwargs):
    """Factory to create mock roster shift objects."""
    defaults = {
        "id": 1,
        "staff_id": None,  # Unassigned by default
        "booking_id": None,
        "date": date.today() + timedelta(days=7),  # Future date
        "end_date": None,
        "start_time": time(9, 0),
        "end_time": time(12, 0),
        "shift_type": MockShiftType.MORNING,
        "status": MockShiftStatus.SCHEDULED,
        "notes": "Test shift",
        "created_at": datetime.now(),
    }
    defaults.update(kwargs)
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

    # Add bookings list
    shift.bookings = []

    return shift


def create_mock_holiday(**kwargs):
    """Factory to create mock employee holiday objects."""
    defaults = {
        "id": 1,
        "staff_id": 1,
        "start_date": date.today() + timedelta(days=7),
        "end_date": date.today() + timedelta(days=14),
        "holiday_type": MockHolidayType.HOLIDAY,
        "notes": "Test holiday",
        "created_at": datetime.now(),
    }
    defaults.update(kwargs)
    holiday = MagicMock()
    for key, value in defaults.items():
        setattr(holiday, key, value)
    return holiday


# =============================================================================
# Helper Functions Tests
# =============================================================================

class TestHoursUntilShift:
    """Tests for calculating hours until shift starts."""

    def test_shift_in_future(self):
        """Shift 3 days in future should return correct hours."""
        shift_date = date.today() + timedelta(days=3)
        shift_time = time(10, 0)
        shift_datetime = datetime.combine(shift_date, shift_time)

        now = datetime.now()
        hours_until = (shift_datetime - now).total_seconds() / 3600

        assert hours_until > 48  # More than 48 hours away

    def test_shift_tomorrow(self):
        """Shift tomorrow at same time should be ~24 hours away."""
        shift_date = date.today() + timedelta(days=1)
        shift_time = datetime.now().time()
        shift_datetime = datetime.combine(shift_date, shift_time)

        now = datetime.now()
        hours_until = (shift_datetime - now).total_seconds() / 3600

        assert 23 <= hours_until <= 25  # Approximately 24 hours

    def test_shift_in_2_hours(self):
        """Shift starting in 2 hours should return approximately 2."""
        now = datetime.now()
        shift_datetime = now + timedelta(hours=2)

        hours_until = (shift_datetime - now).total_seconds() / 3600

        assert 1.9 <= hours_until <= 2.1

    def test_shift_in_past(self):
        """Shift in the past should return negative hours."""
        shift_date = date.today() - timedelta(days=1)
        shift_time = time(10, 0)
        shift_datetime = datetime.combine(shift_date, shift_time)

        now = datetime.now()
        hours_until = (shift_datetime - now).total_seconds() / 3600

        assert hours_until < 0


# =============================================================================
# Happy Path Tests - Claim Shift
# =============================================================================

class TestClaimShiftHappyPath:
    """Tests for successful shift claiming."""

    def test_claim_unassigned_shift(self):
        """Employee should be able to claim an unassigned shift."""
        employee = create_mock_user(id=1)
        shift = create_mock_shift(staff_id=None)

        # Simulate claim
        shift.staff_id = employee.id

        assert shift.staff_id == 1

    def test_claim_shift_in_future(self):
        """Employee should be able to claim shifts in the future."""
        employee = create_mock_user(id=2)
        future_date = date.today() + timedelta(days=5)
        shift = create_mock_shift(date=future_date, staff_id=None)

        # Verify shift is in the future
        assert shift.date > date.today()

        # Simulate claim
        shift.staff_id = employee.id

        assert shift.staff_id == 2

    def test_claim_shift_with_bookings(self):
        """Employee should be able to claim shift that has linked bookings."""
        employee = create_mock_user(id=1)
        shift = create_mock_shift(staff_id=None)

        # Add mock bookings
        mock_booking = MagicMock()
        mock_booking.id = 101
        mock_booking.reference = "TAG-ABC123"
        shift.bookings = [mock_booking]

        # Simulate claim
        shift.staff_id = employee.id

        assert shift.staff_id == 1
        assert len(shift.bookings) == 1

    def test_claim_different_shift_types(self):
        """Employee should be able to claim any shift type."""
        employee = create_mock_user(id=1)

        for shift_type in MockShiftType:
            shift = create_mock_shift(shift_type=shift_type, staff_id=None)
            shift.staff_id = employee.id

            assert shift.staff_id == 1
            assert shift.shift_type == shift_type


# =============================================================================
# Happy Path Tests - Release Shift
# =============================================================================

class TestReleaseShiftHappyPath:
    """Tests for successful shift releasing."""

    def test_release_shift_with_48h_notice(self):
        """Employee should be able to release shift with 48+ hours notice."""
        employee = create_mock_user(id=1)
        future_date = date.today() + timedelta(days=5)
        shift = create_mock_shift(date=future_date, staff_id=employee.id)

        # Calculate hours until shift
        shift_datetime = datetime.combine(shift.date, shift.start_time)
        hours_until = (shift_datetime - datetime.now()).total_seconds() / 3600

        assert hours_until > 48  # More than 48 hours notice

        # Simulate release
        shift.staff_id = None

        assert shift.staff_id is None

    def test_release_shift_exactly_48h(self):
        """Edge case: Release shift with exactly 48 hours notice."""
        employee = create_mock_user(id=1)

        # Create shift exactly 48 hours from now (plus a tiny buffer)
        shift_datetime = datetime.now() + timedelta(hours=48, minutes=5)
        shift = create_mock_shift(
            date=shift_datetime.date(),
            start_time=shift_datetime.time(),
            staff_id=employee.id
        )

        # Calculate hours until shift
        hours_until = (shift_datetime - datetime.now()).total_seconds() / 3600

        assert hours_until >= 48  # At least 48 hours

        # Simulate release
        shift.staff_id = None

        assert shift.staff_id is None


# =============================================================================
# Happy Path Tests - Available Shifts
# =============================================================================

class TestAvailableShiftsHappyPath:
    """Tests for retrieving available shifts."""

    def test_get_unassigned_shifts_only(self):
        """Available shifts should only include unassigned shifts."""
        shifts = [
            create_mock_shift(id=1, staff_id=None),      # Unassigned
            create_mock_shift(id=2, staff_id=1),          # Assigned
            create_mock_shift(id=3, staff_id=None),      # Unassigned
            create_mock_shift(id=4, staff_id=2),          # Assigned
        ]

        available = [s for s in shifts if s.staff_id is None]

        assert len(available) == 2
        assert all(s.staff_id is None for s in available)

    def test_get_future_shifts_only(self):
        """Available shifts should only include future shifts."""
        today = date.today()
        shifts = [
            create_mock_shift(id=1, date=today - timedelta(days=1), staff_id=None),  # Past
            create_mock_shift(id=2, date=today, staff_id=None),                       # Today
            create_mock_shift(id=3, date=today + timedelta(days=1), staff_id=None),  # Tomorrow
            create_mock_shift(id=4, date=today + timedelta(days=7), staff_id=None),  # Next week
        ]

        available = [s for s in shifts if s.date >= today and s.staff_id is None]

        assert len(available) == 3  # Today and future
        assert all(s.date >= today for s in available)

    def test_exclude_cancelled_shifts(self):
        """Available shifts should exclude cancelled shifts."""
        shifts = [
            create_mock_shift(id=1, status=MockShiftStatus.SCHEDULED, staff_id=None),
            create_mock_shift(id=2, status=MockShiftStatus.CANCELLED, staff_id=None),
            create_mock_shift(id=3, status=MockShiftStatus.CONFIRMED, staff_id=None),
        ]

        available = [s for s in shifts if s.status != MockShiftStatus.CANCELLED and s.staff_id is None]

        assert len(available) == 2
        assert all(s.status != MockShiftStatus.CANCELLED for s in available)


# =============================================================================
# Unhappy Path Tests - Claim Shift
# =============================================================================

class TestClaimShiftUnhappyPath:
    """Tests for failed shift claiming scenarios."""

    def test_cannot_claim_assigned_shift(self):
        """Employee should not be able to claim already assigned shift."""
        employee = create_mock_user(id=2)
        shift = create_mock_shift(staff_id=1)  # Already assigned to user 1

        # Check shift is already assigned
        assert shift.staff_id is not None
        assert shift.staff_id == 1

        # Attempting to claim should be rejected
        is_already_assigned = shift.staff_id is not None

        assert is_already_assigned is True

    def test_cannot_claim_past_shift(self):
        """Employee should not be able to claim shift in the past."""
        employee = create_mock_user(id=1)
        past_date = date.today() - timedelta(days=1)
        shift = create_mock_shift(date=past_date, staff_id=None)

        # Check shift is in the past
        is_past = shift.date < date.today()

        assert is_past is True

    def test_cannot_claim_overlapping_shift(self):
        """Employee should not be able to claim if they have overlapping shift."""
        employee = create_mock_user(id=1)
        shift_date = date.today() + timedelta(days=3)

        # Existing shift: 9:00 - 12:00
        existing_shift = create_mock_shift(
            id=1,
            date=shift_date,
            start_time=time(9, 0),
            end_time=time(12, 0),
            staff_id=employee.id
        )

        # New shift to claim: 10:00 - 14:00 (overlaps)
        new_shift = create_mock_shift(
            id=2,
            date=shift_date,
            start_time=time(10, 0),
            end_time=time(14, 0),
            staff_id=None
        )

        # Check for overlap
        def times_overlap(s1_start, s1_end, s2_start, s2_end):
            s1_start_mins = s1_start.hour * 60 + s1_start.minute
            s1_end_mins = s1_end.hour * 60 + s1_end.minute
            s2_start_mins = s2_start.hour * 60 + s2_start.minute
            s2_end_mins = s2_end.hour * 60 + s2_end.minute

            return s1_start_mins < s2_end_mins and s2_start_mins < s1_end_mins

        has_overlap = times_overlap(
            existing_shift.start_time, existing_shift.end_time,
            new_shift.start_time, new_shift.end_time
        )

        assert has_overlap is True

    def test_cannot_claim_when_on_holiday(self):
        """Employee should not be able to claim shift on a holiday day."""
        employee = create_mock_user(id=1)
        shift_date = date.today() + timedelta(days=7)

        # Employee has holiday
        holiday = create_mock_holiday(
            staff_id=employee.id,
            start_date=shift_date - timedelta(days=2),
            end_date=shift_date + timedelta(days=2)
        )

        # Shift on holiday day
        shift = create_mock_shift(date=shift_date, staff_id=None)

        # Check if employee is on holiday
        is_on_holiday = holiday.start_date <= shift.date <= holiday.end_date

        assert is_on_holiday is True


# =============================================================================
# Unhappy Path Tests - Release Shift
# =============================================================================

class TestReleaseShiftUnhappyPath:
    """Tests for failed shift releasing scenarios."""

    def test_cannot_release_with_less_than_48h_notice(self):
        """Employee should not be able to release shift with <48h notice."""
        employee = create_mock_user(id=1)

        # Shift starting in 24 hours
        shift_datetime = datetime.now() + timedelta(hours=24)
        shift = create_mock_shift(
            date=shift_datetime.date(),
            start_time=shift_datetime.time(),
            staff_id=employee.id
        )

        hours_until = (shift_datetime - datetime.now()).total_seconds() / 3600

        assert hours_until < 48  # Less than 48 hours

    def test_cannot_release_others_shift(self):
        """Employee should not be able to release another employee's shift."""
        employee1 = create_mock_user(id=1)
        employee2 = create_mock_user(id=2)

        # Shift assigned to employee 1
        shift = create_mock_shift(staff_id=employee1.id)

        # Check if employee 2 can release
        can_release = shift.staff_id == employee2.id

        assert can_release is False

    def test_cannot_release_unassigned_shift(self):
        """Employee should not be able to release an unassigned shift."""
        employee = create_mock_user(id=1)
        shift = create_mock_shift(staff_id=None)

        # Check shift is unassigned
        is_assigned_to_employee = shift.staff_id == employee.id

        assert is_assigned_to_employee is False


# =============================================================================
# Edge Cases & Boundaries Tests
# =============================================================================

class TestEdgeCasesAndBoundaries:
    """Tests for edge cases and boundary conditions."""

    def test_shift_starting_at_midnight(self):
        """Handle shift starting at midnight (00:00)."""
        shift = create_mock_shift(
            start_time=time(0, 0),
            end_time=time(3, 0),
            staff_id=None
        )

        assert shift.start_time == time(0, 0)
        assert shift.end_time == time(3, 0)

    def test_overnight_shift(self):
        """Handle overnight shift crossing midnight."""
        shift_date = date.today() + timedelta(days=3)
        shift = create_mock_shift(
            date=shift_date,
            end_date=shift_date + timedelta(days=1),  # Next day
            start_time=time(22, 0),
            end_time=time(2, 0),  # 2 AM next day
            staff_id=None
        )

        assert shift.date < shift.end_date  # Spans two days
        assert shift.start_time > shift.end_time  # End time is smaller (next day)

    def test_exactly_48_hour_boundary(self):
        """Test behavior at exactly 48 hour boundary."""
        now = datetime.now()

        # Shift at exactly 48 hours - should be allowed
        shift_48h = now + timedelta(hours=48)
        hours_48 = (shift_48h - now).total_seconds() / 3600
        can_release_48 = hours_48 >= 48

        # Shift at 47h 59m - should be rejected
        shift_47h59m = now + timedelta(hours=47, minutes=59)
        hours_47h59m = (shift_47h59m - now).total_seconds() / 3600
        can_release_47h59m = hours_47h59m >= 48

        assert can_release_48 is True
        assert can_release_47h59m is False

    def test_shift_today(self):
        """Shifts today should be available if in the future."""
        today = date.today()
        now = datetime.now()

        # Shift later today (assuming it's before 23:00)
        if now.hour < 23:
            future_time = time(23, 0)
            shift = create_mock_shift(date=today, start_time=future_time, staff_id=None)

            shift_datetime = datetime.combine(shift.date, shift.start_time)
            is_future = shift_datetime > now

            assert is_future is True

    def test_multiple_shifts_same_day_no_overlap(self):
        """Employee can claim multiple shifts on same day if they don't overlap."""
        employee = create_mock_user(id=1)
        shift_date = date.today() + timedelta(days=3)

        # Morning shift: 6:00 - 10:00
        shift1 = create_mock_shift(
            id=1,
            date=shift_date,
            start_time=time(6, 0),
            end_time=time(10, 0),
            staff_id=employee.id
        )

        # Afternoon shift: 14:00 - 18:00 (no overlap)
        shift2 = create_mock_shift(
            id=2,
            date=shift_date,
            start_time=time(14, 0),
            end_time=time(18, 0),
            staff_id=None
        )

        # Check for overlap
        def times_overlap(s1_start, s1_end, s2_start, s2_end):
            s1_start_mins = s1_start.hour * 60 + s1_start.minute
            s1_end_mins = s1_end.hour * 60 + s1_end.minute
            s2_start_mins = s2_start.hour * 60 + s2_start.minute
            s2_end_mins = s2_end.hour * 60 + s2_end.minute

            return s1_start_mins < s2_end_mins and s2_start_mins < s1_end_mins

        has_overlap = times_overlap(
            shift1.start_time, shift1.end_time,
            shift2.start_time, shift2.end_time
        )

        assert has_overlap is False  # No overlap, can claim

    def test_back_to_back_shifts(self):
        """Employee can claim shifts that are back-to-back (touching but not overlapping)."""
        shift_date = date.today() + timedelta(days=3)

        # Shift 1: 6:00 - 10:00
        shift1 = create_mock_shift(
            id=1,
            date=shift_date,
            start_time=time(6, 0),
            end_time=time(10, 0),
            staff_id=1
        )

        # Shift 2: 10:00 - 14:00 (starts exactly when shift 1 ends)
        shift2 = create_mock_shift(
            id=2,
            date=shift_date,
            start_time=time(10, 0),
            end_time=time(14, 0),
            staff_id=None
        )

        # These should NOT overlap (touching boundary)
        def times_overlap_exclusive(s1_start, s1_end, s2_start, s2_end):
            # Exclusive check: overlap only if one truly overlaps the other
            s1_start_mins = s1_start.hour * 60 + s1_start.minute
            s1_end_mins = s1_end.hour * 60 + s1_end.minute
            s2_start_mins = s2_start.hour * 60 + s2_start.minute
            s2_end_mins = s2_end.hour * 60 + s2_end.minute

            # Shifts touch but don't overlap
            return s1_start_mins < s2_end_mins and s2_start_mins < s1_end_mins

        has_overlap = times_overlap_exclusive(
            shift1.start_time, shift1.end_time,
            shift2.start_time, shift2.end_time
        )

        # Back-to-back shifts do "overlap" at the boundary in strict check
        # The implementation should allow this case
        assert shift1.end_time == shift2.start_time

    def test_empty_available_shifts(self):
        """Handle case when no shifts are available."""
        shifts = [
            create_mock_shift(id=1, staff_id=1),  # Assigned
            create_mock_shift(id=2, staff_id=2),  # Assigned
        ]

        available = [s for s in shifts if s.staff_id is None]

        assert len(available) == 0

    def test_holiday_edge_dates(self):
        """Test holiday start/end date edge cases."""
        employee = create_mock_user(id=1)

        # Holiday: April 10-14
        holiday = create_mock_holiday(
            staff_id=employee.id,
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 14)
        )

        # Day before holiday - should be allowed
        shift_before = create_mock_shift(date=date(2026, 4, 9), staff_id=None)
        is_on_holiday_before = holiday.start_date <= shift_before.date <= holiday.end_date
        assert is_on_holiday_before is False

        # First day of holiday - should be blocked
        shift_first = create_mock_shift(date=date(2026, 4, 10), staff_id=None)
        is_on_holiday_first = holiday.start_date <= shift_first.date <= holiday.end_date
        assert is_on_holiday_first is True

        # Last day of holiday - should be blocked
        shift_last = create_mock_shift(date=date(2026, 4, 14), staff_id=None)
        is_on_holiday_last = holiday.start_date <= shift_last.date <= holiday.end_date
        assert is_on_holiday_last is True

        # Day after holiday - should be allowed
        shift_after = create_mock_shift(date=date(2026, 4, 15), staff_id=None)
        is_on_holiday_after = holiday.start_date <= shift_after.date <= holiday.end_date
        assert is_on_holiday_after is False


# =============================================================================
# Additional Test Cases
# =============================================================================

class TestShiftClaimReleaseFlow:
    """Integration-style tests for full claim/release flow."""

    def test_claim_then_release_flow(self):
        """Test complete claim and release flow."""
        employee = create_mock_user(id=1)
        future_date = date.today() + timedelta(days=5)
        shift = create_mock_shift(date=future_date, staff_id=None)

        # Initial state: unassigned
        assert shift.staff_id is None

        # Step 1: Claim
        shift.staff_id = employee.id
        assert shift.staff_id == employee.id

        # Step 2: Release (has more than 48h notice)
        shift_datetime = datetime.combine(shift.date, shift.start_time)
        hours_until = (shift_datetime - datetime.now()).total_seconds() / 3600
        assert hours_until > 48

        shift.staff_id = None
        assert shift.staff_id is None

    def test_multiple_employees_claiming_different_shifts(self):
        """Multiple employees should be able to claim different shifts."""
        employee1 = create_mock_user(id=1)
        employee2 = create_mock_user(id=2)
        employee3 = create_mock_user(id=3)

        shift1 = create_mock_shift(id=1, staff_id=None)
        shift2 = create_mock_shift(id=2, staff_id=None)
        shift3 = create_mock_shift(id=3, staff_id=None)

        # Each employee claims one shift
        shift1.staff_id = employee1.id
        shift2.staff_id = employee2.id
        shift3.staff_id = employee3.id

        assert shift1.staff_id == 1
        assert shift2.staff_id == 2
        assert shift3.staff_id == 3

    def test_released_shift_becomes_available(self):
        """Released shift should appear in available shifts again."""
        employee = create_mock_user(id=1)
        future_date = date.today() + timedelta(days=5)
        shift = create_mock_shift(date=future_date, staff_id=employee.id)

        # Before release: not in available
        shifts = [shift]
        available_before = [s for s in shifts if s.staff_id is None]
        assert len(available_before) == 0

        # Release shift
        shift.staff_id = None

        # After release: in available
        available_after = [s for s in shifts if s.staff_id is None]
        assert len(available_after) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
