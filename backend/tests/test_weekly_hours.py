"""
Tests for Weekly Hours functionality.

Covers:
- calculate_shift_hours helper function (unit tests)
- GET /api/roster/weekly-hours - Admin endpoint
- GET /api/employee/weekly-hours - Employee endpoint

Test categories:
- Unit tests: calculate_shift_hours calculation logic
- Integration tests: API endpoints with mocked database
- Authentication: Admin vs Employee access
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Unit Tests - calculate_shift_hours
# =============================================================================

class TestCalculateShiftHours:
    """Unit tests for the calculate_shift_hours helper function."""

    def test_standard_daytime_shift(self):
        """Standard daytime shift (e.g., 09:00-17:00) should return 8 hours."""
        from routers.roster import calculate_shift_hours

        start = time(9, 0)
        end = time(17, 0)

        result = calculate_shift_hours(start, end)

        assert result == 8.0

    def test_short_shift(self):
        """Short shift (e.g., 14:00-15:00) should return 1 hour."""
        from routers.roster import calculate_shift_hours

        start = time(14, 0)
        end = time(15, 0)

        result = calculate_shift_hours(start, end)

        assert result == 1.0

    def test_half_hour_shift(self):
        """Half-hour shift (e.g., 10:00-10:30) should return 0.5 hours."""
        from routers.roster import calculate_shift_hours

        start = time(10, 0)
        end = time(10, 30)

        result = calculate_shift_hours(start, end)

        assert result == 0.5

    def test_partial_hour_shift(self):
        """Partial hour shift (e.g., 09:00-10:45) should return 1.75 hours."""
        from routers.roster import calculate_shift_hours

        start = time(9, 0)
        end = time(10, 45)

        result = calculate_shift_hours(start, end)

        assert result == 1.75

    def test_overnight_shift_explicit_flag(self):
        """Overnight shift with is_overnight=True (e.g., 23:30-00:30) should return 1 hour."""
        from routers.roster import calculate_shift_hours

        start = time(23, 30)
        end = time(0, 30)

        result = calculate_shift_hours(start, end, is_overnight=True)

        assert result == 1.0

    def test_overnight_shift_inferred_from_times(self):
        """Overnight shift should be inferred when end_time < start_time."""
        from routers.roster import calculate_shift_hours

        start = time(23, 0)
        end = time(2, 0)

        # Should infer overnight since 02:00 < 23:00
        result = calculate_shift_hours(start, end, is_overnight=False)

        assert result == 3.0

    def test_overnight_shift_crossing_midnight(self):
        """Overnight shift crossing midnight (e.g., 22:00-06:00) should return 8 hours."""
        from routers.roster import calculate_shift_hours

        start = time(22, 0)
        end = time(6, 0)

        result = calculate_shift_hours(start, end, is_overnight=True)

        assert result == 8.0

    def test_late_night_to_early_morning(self):
        """Late night to early morning (e.g., 23:55-00:55) should return 1 hour."""
        from routers.roster import calculate_shift_hours

        start = time(23, 55)
        end = time(0, 55)

        result = calculate_shift_hours(start, end, is_overnight=True)

        assert result == 1.0

    def test_full_day_shift(self):
        """Full day shift (e.g., 06:00-18:00) should return 12 hours."""
        from routers.roster import calculate_shift_hours

        start = time(6, 0)
        end = time(18, 0)

        result = calculate_shift_hours(start, end)

        assert result == 12.0

    def test_early_morning_shift(self):
        """Early morning shift (e.g., 03:50-07:00) should return 3.17 hours."""
        from routers.roster import calculate_shift_hours

        start = time(3, 50)
        end = time(7, 0)

        result = calculate_shift_hours(start, end)

        # 3 hours 10 minutes = 3.17 hours (rounded to 2 decimal places)
        assert result == 3.17

    def test_same_start_and_end_time_treated_as_overnight(self):
        """Same start and end time should be treated as 24-hour shift."""
        from routers.roster import calculate_shift_hours

        start = time(9, 0)
        end = time(9, 0)

        # When end <= start, it adds a day (24 hours)
        result = calculate_shift_hours(start, end)

        assert result == 24.0


# =============================================================================
# Integration Tests - Admin Weekly Hours Endpoint
# =============================================================================

class TestAdminWeeklyHoursIntegration:
    """Integration tests for GET /api/roster/weekly-hours (admin endpoint)."""

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        user = MagicMock()
        user.id = 1
        user.email = "admin@tagparking.co.uk"
        user.is_admin = True
        user.first_name = "Admin"
        user.last_name = "User"
        return user

    @pytest.fixture
    def mock_employee_user(self):
        """Create a mock employee user (non-admin)."""
        user = MagicMock()
        user.id = 2
        user.email = "employee@tagparking.co.uk"
        user.is_admin = False
        user.first_name = "Jez"
        user.last_name = "Taylor"
        return user

    def create_mock_shift(self, id, staff_id, shift_date, start_time, end_time, end_date=None):
        """Create a mock shift for database queries."""
        from db_models import ShiftType, ShiftStatus
        shift = MagicMock()
        shift.id = id
        shift.staff_id = staff_id
        shift.date = shift_date
        shift.end_date = end_date or shift_date
        shift.start_time = start_time
        shift.end_time = end_time
        shift.shift_type = ShiftType.MORNING
        shift.status = ShiftStatus.SCHEDULED
        return shift

    def create_mock_employee(self, id, first_name, last_name, email):
        """Create a mock employee user."""
        user = MagicMock()
        user.id = id
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        return user

    def test_admin_weekly_hours_success(self, mock_admin_user):
        """Admin should get weekly hours for all employees."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Create mock shifts for the week of March 16, 2026
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 3, 17), time(14, 0), time(15, 0)),  # Jez Taylor, 1 hour
            self.create_mock_shift(2, 3, date(2026, 3, 18), time(9, 0), time(13, 0)),   # Another employee, 4 hours
        ]

        mock_employees = {
            2: self.create_mock_employee(2, "Jez", "Taylor", "jez@tagparking.co.uk"),
            3: self.create_mock_employee(3, "Mark", "Custard", "mark@tagparking.co.uk"),
        }

        mock_db = MagicMock()

        # Mock the roster shift query
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        # Mock the user lookup
        def mock_user_filter(user_id_filter):
            # Extract the ID from the filter
            result = MagicMock()
            for emp_id, emp in mock_employees.items():
                result.first.return_value = emp
                break
            return result

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 200
            data = response.json()

            assert "week_start" in data
            assert "week_end" in data
            assert "employees" in data
            assert data["week_start"] == "2026-03-16"
            assert data["week_end"] == "2026-03-22"
        finally:
            app.dependency_overrides.clear()

    def test_admin_weekly_hours_no_shifts(self, mock_admin_user):
        """Admin should get empty employees list when no shifts exist."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/weekly-hours?week_start=2026-02-23")

            assert response.status_code == 200
            data = response.json()

            assert data["employees"] == []
        finally:
            app.dependency_overrides.clear()

    def test_admin_weekly_hours_missing_week_start(self, mock_admin_user):
        """Missing week_start parameter should return 422."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_db = MagicMock()

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/weekly-hours")

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_employee_cannot_access_admin_endpoint(self, mock_employee_user):
        """Non-admin should get 403 when accessing admin weekly hours endpoint."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_db = MagicMock()

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin privileges required")

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Employee Weekly Hours Endpoint
# =============================================================================

class TestEmployeeWeeklyHoursIntegration:
    """Integration tests for GET /api/employee/weekly-hours."""

    @pytest.fixture
    def mock_employee_user(self):
        """Create a mock employee user."""
        user = MagicMock()
        user.id = 2
        user.email = "jez@tagparking.co.uk"
        user.is_admin = False
        user.first_name = "Jez"
        user.last_name = "Taylor"
        return user

    def create_mock_shift(self, id, staff_id, shift_date, start_time, end_time, end_date=None):
        """Create a mock shift for database queries."""
        from db_models import ShiftType, ShiftStatus
        shift = MagicMock()
        shift.id = id
        shift.staff_id = staff_id
        shift.date = shift_date
        shift.end_date = end_date or shift_date
        shift.start_time = start_time
        shift.end_time = end_time
        shift.shift_type = ShiftType.MORNING
        shift.status = ShiftStatus.SCHEDULED
        return shift

    def test_employee_sees_own_hours(self, mock_employee_user):
        """Employee should see only their own weekly hours."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Create mock shift for this employee
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 3, 17), time(14, 0), time(15, 0)),  # 1 hour
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_employee_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            client = TestClient(app)
            response = client.get("/api/employee/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 200
            data = response.json()

            assert data["employee_id"] == 2
            assert data["employee_name"] == "Jez Taylor"
            assert data["total_hours"] == 1.0
            assert data["shift_count"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_employee_no_shifts_this_week(self, mock_employee_user):
        """Employee with no shifts should see 0 hours."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_employee_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            client = TestClient(app)
            response = client.get("/api/employee/weekly-hours?week_start=2026-02-23")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 0
            assert data["shift_count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_employee_multiple_shifts_summed(self, mock_employee_user):
        """Employee with multiple shifts should see summed hours."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Create multiple shifts for this employee
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 3, 16), time(9, 0), time(13, 0)),   # 4 hours
            self.create_mock_shift(2, 2, date(2026, 3, 17), time(14, 0), time(18, 0)),  # 4 hours
            self.create_mock_shift(3, 2, date(2026, 3, 18), time(9, 0), time(12, 0)),   # 3 hours
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_employee_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            client = TestClient(app)
            response = client.get("/api/employee/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 11.0
            assert data["shift_count"] == 3
        finally:
            app.dependency_overrides.clear()

    def test_employee_overnight_shift_hours(self, mock_employee_user):
        """Employee with overnight shift should see correct hours."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Create overnight shift (23:30 -> 00:30 next day)
        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 16),
                time(23, 30),
                time(0, 30),
                end_date=date(2026, 3, 17)  # Overnight flag
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_employee_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            client = TestClient(app)
            response = client.get("/api/employee/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 200
            data = response.json()

            # 23:30 to 00:30 = 1 hour
            assert data["total_hours"] == 1.0
            assert data["shift_count"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_employee_daily_hours_breakdown(self, mock_employee_user):
        """Employee should see daily hours breakdown."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 3, 17), time(9, 0), time(13, 0)),  # Tuesday, 4 hours
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_employee_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[get_current_user] = mock_get_current_user

        try:
            client = TestClient(app)
            response = client.get("/api/employee/weekly-hours?week_start=2026-03-16")

            assert response.status_code == 200
            data = response.json()

            assert "daily_hours" in data
            # Should have entries for all 7 days
            assert len(data["daily_hours"]) == 7
            # Tuesday (17th) should have 4 hours
            assert data["daily_hours"]["2026-03-17"] == 4.0
            # Other days should be 0
            assert data["daily_hours"]["2026-03-16"] == 0.0
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Unit Tests - Week Boundary Edge Cases
# =============================================================================

class TestWeekBoundaryEdgeCases:
    """Test edge cases around week boundaries."""

    def test_shift_hours_at_week_start(self):
        """Shift starting exactly at Monday 00:00 should be counted in that week."""
        from routers.roster import calculate_shift_hours

        start = time(0, 0)
        end = time(4, 0)

        result = calculate_shift_hours(start, end)

        assert result == 4.0

    def test_shift_hours_at_week_end(self):
        """Shift ending exactly at Sunday 23:59 should be counted in that week."""
        from routers.roster import calculate_shift_hours

        start = time(20, 0)
        end = time(23, 59)

        result = calculate_shift_hours(start, end)

        # 3 hours 59 minutes = 3.98 hours
        assert result == 3.98

    def test_very_short_shift(self):
        """Very short shift (15 minutes) should be calculated correctly."""
        from routers.roster import calculate_shift_hours

        start = time(12, 0)
        end = time(12, 15)

        result = calculate_shift_hours(start, end)

        assert result == 0.25

    def test_long_overnight_shift(self):
        """Long overnight shift (e.g., 18:00-06:00) should be 12 hours."""
        from routers.roster import calculate_shift_hours

        start = time(18, 0)
        end = time(6, 0)

        result = calculate_shift_hours(start, end, is_overnight=True)

        assert result == 12.0
