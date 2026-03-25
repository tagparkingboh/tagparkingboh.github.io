"""
Unit tests for roster shift duplication and bulk edit features.

Tests cover:
- Shift duplication to multiple staff members
- Preventing duplicate shifts for same person on same time
- Bulk editing shift times
- Bulk adding bookings to shifts
- Bulk deletion of shifts
- Happy paths, unhappy paths, edge cases, and boundary conditions
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from sqlalchemy.orm import Session

from db_models import RosterShift, ShiftType, ShiftStatus, User, Booking, BookingStatus


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def sample_staff():
    """Sample staff members for testing."""
    staff1 = MagicMock(spec=User)
    staff1.id = 1
    staff1.first_name = "John"
    staff1.last_name = "Doe"
    staff1.is_active = True
    staff1.is_admin = False

    staff2 = MagicMock(spec=User)
    staff2.id = 2
    staff2.first_name = "Jane"
    staff2.last_name = "Smith"
    staff2.is_active = True
    staff2.is_admin = False

    staff3 = MagicMock(spec=User)
    staff3.id = 3
    staff3.first_name = "Bob"
    staff3.last_name = "Wilson"
    staff3.is_active = True
    staff3.is_admin = False

    return [staff1, staff2, staff3]


@pytest.fixture
def sample_shift():
    """Sample shift for testing."""
    shift = MagicMock(spec=RosterShift)
    shift.id = 1
    shift.staff_id = 1
    shift.date = date(2026, 3, 25)
    shift.end_date = date(2026, 3, 25)
    shift.start_time = time(9, 0)
    shift.end_time = time(17, 0)
    shift.shift_type = ShiftType.MORNING
    shift.status = ShiftStatus.SCHEDULED
    shift.notes = "Test shift"
    shift.bookings = []
    return shift


@pytest.fixture
def sample_booking():
    """Sample booking for testing."""
    booking = MagicMock(spec=Booking)
    booking.id = 101
    booking.reference = "TAG-TEST001"
    booking.dropoff_date = date(2026, 3, 25)
    booking.dropoff_time = time(10, 0)
    booking.customer_first_name = "Test"
    booking.customer_last_name = "Customer"
    booking.status = BookingStatus.CONFIRMED
    return booking


# =============================================================================
# Unit Tests: Shift Overlap Detection - Happy Paths
# =============================================================================

class TestShiftOverlapDetectionHappy:
    """Happy path tests for shift overlap detection."""

    def test_no_overlap_different_times(self, mock_db, sample_staff):
        """Non-overlapping shifts should not conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-12:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(12, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 14:00-17:00 should not overlap
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(14, 0),
            end_time=time(17, 0)
        )

        assert result is None

    def test_no_overlap_adjacent_times(self, mock_db, sample_staff):
        """Adjacent shifts (end time = start time) should not conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-12:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(12, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 12:00-17:00 should not overlap (starts exactly when other ends)
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(12, 0),
            end_time=time(17, 0)
        )

        assert result is None

    def test_unassigned_shift_no_conflict(self, mock_db):
        """Unassigned shifts (staff_id=None) should never conflict."""
        from routers.roster import check_shift_overlap

        result = check_shift_overlap(
            mock_db,
            staff_id=None,
            date=date(2026, 3, 25),
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        assert result is None


# =============================================================================
# Unit Tests: Shift Overlap Detection - Unhappy Paths
# =============================================================================

class TestShiftOverlapDetectionUnhappy:
    """Unhappy path tests for shift overlap detection."""

    def test_overlap_partial_start(self, mock_db):
        """Shift starting during another shift should conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-12:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(12, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 10:00-14:00 overlaps
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(10, 0),
            end_time=time(14, 0)
        )

        assert result == existing_shift

    def test_overlap_partial_end(self, mock_db):
        """Shift ending during another shift should conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-12:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(12, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 08:00-10:00 overlaps
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(8, 0),
            end_time=time(10, 0)
        )

        assert result == existing_shift

    def test_overlap_contained(self, mock_db):
        """Shift completely within another shift should conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-17:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(17, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 10:00-12:00 is completely inside
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(10, 0),
            end_time=time(12, 0)
        )

        assert result == existing_shift

    def test_overlap_surrounding(self, mock_db):
        """Shift completely surrounding another shift should conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 10:00-12:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(10, 0)
        existing_shift.end_time = time(12, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift 08:00-17:00 completely surrounds
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(8, 0),
            end_time=time(17, 0)
        )

        assert result == existing_shift


# =============================================================================
# Unit Tests: Shift Overlap Detection - Edge Cases
# =============================================================================

class TestShiftOverlapDetectionEdgeCases:
    """Edge case tests for shift overlap detection."""

    def test_exact_same_times_conflicts(self, mock_db):
        """Exactly matching shift times should conflict."""
        from routers.roster import check_shift_overlap

        # Existing shift 09:00-17:00
        existing_shift = MagicMock(spec=RosterShift)
        existing_shift.id = 1
        existing_shift.start_time = time(9, 0)
        existing_shift.end_time = time(17, 0)

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [existing_shift]

        # New shift with exact same times
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        assert result == existing_shift

    def test_exclude_self_when_editing(self, mock_db):
        """Editing a shift should exclude itself from overlap check."""
        from routers.roster import check_shift_overlap

        # Mock the chained calls properly
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []  # No shifts found after excluding self

        # Check overlap excluding shift ID 5
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 25),
            start_time=time(9, 0),
            end_time=time(17, 0),
            exclude_shift_id=5
        )

        assert result is None


# =============================================================================
# Unit Tests: Staff Validation - Happy Paths
# =============================================================================

class TestStaffValidationHappy:
    """Happy path tests for staff validation."""

    def test_active_user_is_valid(self, mock_db, sample_staff):
        """Active user should pass validation."""
        from routers.roster import validate_staff_assignment

        mock_db.query.return_value.filter.return_value.first.return_value = sample_staff[0]

        result = validate_staff_assignment(mock_db, staff_id=1)

        assert result == sample_staff[0]


# =============================================================================
# Unit Tests: Staff Validation - Unhappy Paths
# =============================================================================

class TestStaffValidationUnhappy:
    """Unhappy path tests for staff validation."""

    def test_nonexistent_user_raises_404(self, mock_db):
        """Non-existent user should raise 404."""
        from routers.roster import validate_staff_assignment
        from fastapi import HTTPException

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            validate_staff_assignment(mock_db, staff_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_inactive_user_raises_400(self, mock_db):
        """Inactive user should raise 400."""
        from routers.roster import validate_staff_assignment
        from fastapi import HTTPException

        inactive_user = MagicMock(spec=User)
        inactive_user.id = 1
        inactive_user.is_active = False

        mock_db.query.return_value.filter.return_value.first.return_value = inactive_user

        with pytest.raises(HTTPException) as exc_info:
            validate_staff_assignment(mock_db, staff_id=1)

        assert exc_info.value.status_code == 400
        assert "inactive" in exc_info.value.detail.lower()


# =============================================================================
# Unit Tests: Shift Hours Calculation - Happy Paths
# =============================================================================

class TestShiftHoursCalculationHappy:
    """Happy path tests for shift hours calculation."""

    def test_standard_8_hour_shift(self):
        """Standard 8-hour shift should return 8.0 hours."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        assert result == 8.0

    def test_4_hour_shift(self):
        """4-hour shift should return 4.0 hours."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(9, 0),
            end_time=time(13, 0)
        )

        assert result == 4.0

    def test_shift_with_minutes(self):
        """Shift with minutes should calculate correctly."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(9, 30),
            end_time=time(13, 0)
        )

        assert result == 3.5


# =============================================================================
# Unit Tests: Shift Hours Calculation - Overnight Shifts
# =============================================================================

class TestShiftHoursCalculationOvernight:
    """Tests for overnight shift hours calculation."""

    def test_overnight_shift(self):
        """Overnight shift (e.g., 21:00-01:00) should calculate correctly."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(21, 0),
            end_time=time(1, 0),
            is_overnight=True
        )

        assert result == 4.0

    def test_long_overnight_shift(self):
        """Long overnight shift (e.g., 18:00-06:00) should calculate correctly."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(18, 0),
            end_time=time(6, 0),
            is_overnight=True
        )

        assert result == 12.0


# =============================================================================
# Unit Tests: Shift Hours Calculation - Edge Cases
# =============================================================================

class TestShiftHoursCalculationEdgeCases:
    """Edge case tests for shift hours calculation."""

    def test_very_short_shift_30_minutes(self):
        """30-minute shift should return 0.5 hours."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(9, 0),
            end_time=time(9, 30)
        )

        assert result == 0.5

    def test_very_short_shift_15_minutes(self):
        """15-minute shift should return 0.25 hours."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(9, 0),
            end_time=time(9, 15)
        )

        assert result == 0.25

    def test_midnight_start(self):
        """Shift starting at midnight should calculate correctly."""
        from routers.roster import calculate_shift_hours

        result = calculate_shift_hours(
            start_time=time(0, 0),
            end_time=time(4, 0)
        )

        assert result == 4.0


# =============================================================================
# Unit Tests: Staff Initials Generation
# =============================================================================

class TestStaffInitialsGeneration:
    """Tests for staff initials generation."""

    def test_generates_correct_initials(self, sample_staff):
        """Should generate correct uppercase initials."""
        from routers.roster import get_staff_initials

        result = get_staff_initials(sample_staff[0])  # John Doe

        assert result == "JD"

    def test_returns_none_for_no_user(self):
        """Should return None for None user."""
        from routers.roster import get_staff_initials

        result = get_staff_initials(None)

        assert result is None


# =============================================================================
# Unit Tests: Time Parsing
# =============================================================================

class TestTimeParsing:
    """Tests for time string parsing."""

    def test_parse_standard_time(self):
        """Should parse HH:MM format correctly."""
        from routers.roster import parse_time_string

        result = parse_time_string("09:30")

        assert result == time(9, 30)

    def test_parse_midnight(self):
        """Should parse midnight correctly."""
        from routers.roster import parse_time_string

        result = parse_time_string("00:00")

        assert result == time(0, 0)

    def test_parse_just_before_midnight(self):
        """Should parse 23:59 correctly."""
        from routers.roster import parse_time_string

        result = parse_time_string("23:59")

        assert result == time(23, 59)


# =============================================================================
# Unit Tests: Time Formatting
# =============================================================================

class TestTimeFormatting:
    """Tests for time formatting."""

    def test_format_standard_time(self):
        """Should format time as HH:MM."""
        from routers.roster import format_time

        result = format_time(time(9, 30))

        assert result == "09:30"

    def test_format_midnight(self):
        """Should format midnight correctly."""
        from routers.roster import format_time

        result = format_time(time(0, 0))

        assert result == "00:00"

    def test_format_single_digit_hour(self):
        """Should zero-pad single digit hours."""
        from routers.roster import format_time

        result = format_time(time(5, 30))

        assert result == "05:30"
