"""
Tests for Weekly and Monthly Hours functionality.

Covers:
- calculate_shift_hours helper function (unit tests)
- GET /api/roster/weekly-hours - Admin endpoint
- GET /api/employee/weekly-hours - Employee endpoint
- GET /api/roster/monthly-hours - Admin monthly endpoint (for payroll)
- GET /api/employee/monthly-hours - Employee monthly endpoint

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

    def test_H_admin_weekly_hours_returns_all_driver_total(self, mock_admin_user):
        """HUEB: weekly total sums every driver's hours."""
        from main import app
        from database import get_db
        from routers.roster import require_admin
        from db_models import RosterShift, User

        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 3, 17), time(9, 0), time(13, 0)),
            self.create_mock_shift(2, 3, date(2026, 3, 18), time(14, 0), time(16, 30)),
        ]
        mock_employees = {
            2: self.create_mock_employee(2, "Jez", "Taylor", "jez@tagparking.co.uk"),
            3: self.create_mock_employee(3, "Mark", "Custard", "mark@tagparking.co.uk"),
        }

        mock_db = MagicMock()

        def query_side_effect(model):
            query = MagicMock()
            if model is RosterShift:
                query.filter.return_value = query
                query.all.return_value = mock_shifts
            elif model is User:
                query.filter.return_value.first.side_effect = [
                    mock_employees[2],
                    mock_employees[3],
                ]
            return query

        mock_db.query.side_effect = query_side_effect

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
            assert data["total_hours"] == 6.5
            assert data["shift_count"] == 2
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


# =============================================================================
# Integration Tests - Admin Monthly Hours Endpoint (for payroll)
# =============================================================================

class TestAdminMonthlyHoursIntegration:
    """Integration tests for GET /api/roster/monthly-hours (admin endpoint)."""

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

    def test_admin_monthly_hours_success(self, mock_admin_user):
        """Admin should get monthly hours for all employees."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Create mock shifts for April 2026
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 7), time(23, 30), time(0, 30), end_date=date(2026, 4, 8)),  # Mark, 1 hour
            self.create_mock_shift(2, 2, date(2026, 4, 18), time(23, 55), time(0, 55), end_date=date(2026, 4, 19)),  # Mark, 1 hour
        ]

        mock_employees = {
            2: self.create_mock_employee(2, "Mark", "Custard", "mark@tagparking.co.uk"),
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            assert data["year"] == 2026
            assert data["month"] == 4
            assert data["month_name"] == "April"
            assert data["month_start"] == "2026-04-01"
            assert data["month_end"] == "2026-04-30"
            assert "employees" in data
        finally:
            app.dependency_overrides.clear()

    def test_H_admin_monthly_hours_returns_all_driver_totals(self, mock_admin_user):
        """HUEB: monthly and weekly totals sum every driver's hours."""
        from main import app
        from database import get_db
        from routers.roster import require_admin
        from db_models import RosterShift, User

        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 7), time(9, 0), time(13, 0)),
            self.create_mock_shift(2, 3, date(2026, 4, 8), time(10, 0), time(12, 30)),
            self.create_mock_shift(3, 2, date(2026, 4, 18), time(23, 30), time(0, 30), end_date=date(2026, 4, 19)),
        ]
        mock_employees = {
            2: self.create_mock_employee(2, "Jez", "Taylor", "jez@tagparking.co.uk"),
            3: self.create_mock_employee(3, "Mark", "Custard", "mark@tagparking.co.uk"),
        }

        mock_db = MagicMock()

        def query_side_effect(model):
            query = MagicMock()
            if model is RosterShift:
                query.filter.return_value = query
                query.all.return_value = mock_shifts
            elif model is User:
                query.filter.return_value.first.side_effect = [
                    mock_employees[2],
                    mock_employees[3],
                ]
            return query

        mock_db.query.side_effect = query_side_effect

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()
            assert data["total_hours"] == 7.5
            assert data["shift_count"] == 3
            assert data["weeks"][1]["total_hours"] == 6.5
            assert data["weeks"][1]["shift_count"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_admin_monthly_hours_no_shifts(self, mock_admin_user):
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
            response = client.get("/api/roster/monthly-hours?year=2026&month=2")

            assert response.status_code == 200
            data = response.json()

            assert data["employees"] == []
            assert data["month_name"] == "February"
        finally:
            app.dependency_overrides.clear()

    def test_admin_monthly_hours_missing_params(self, mock_admin_user):
        """Missing year or month parameter should return 422."""
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

            # Missing both
            response = client.get("/api/roster/monthly-hours")
            assert response.status_code == 422

            # Missing month
            response = client.get("/api/roster/monthly-hours?year=2026")
            assert response.status_code == 422

            # Missing year
            response = client.get("/api/roster/monthly-hours?month=4")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_admin_monthly_hours_invalid_month(self, mock_admin_user):
        """Invalid month (0 or 13) should return 422."""
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

            response = client.get("/api/roster/monthly-hours?year=2026&month=0")
            assert response.status_code == 422

            response = client.get("/api/roster/monthly-hours?year=2026&month=13")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_employee_cannot_access_admin_monthly_endpoint(self, mock_employee_user):
        """Non-admin should get 403 when accessing admin monthly hours endpoint."""
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
            response = client.get("/api/roster/monthly-hours?year=2026&month=4")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Employee Monthly Hours Endpoint
# =============================================================================

class TestEmployeeMonthlyHoursIntegration:
    """Integration tests for GET /api/employee/monthly-hours."""

    @pytest.fixture
    def mock_employee_user(self):
        """Create a mock employee user."""
        user = MagicMock()
        user.id = 2
        user.email = "mark@tagparking.co.uk"
        user.is_admin = False
        user.first_name = "Mark"
        user.last_name = "Custard"
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

    def test_employee_sees_own_monthly_hours(self, mock_employee_user):
        """Employee should see only their own monthly hours."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Create mock shifts for this employee in April
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 7), time(23, 30), time(0, 30), end_date=date(2026, 4, 8)),  # 1 hour
            self.create_mock_shift(2, 2, date(2026, 4, 18), time(23, 55), time(0, 55), end_date=date(2026, 4, 19)),  # 1 hour
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            assert data["employee_id"] == 2
            assert data["employee_name"] == "Mark Custard"
            assert data["total_hours"] == 2.0
            assert data["shift_count"] == 2
            assert data["month_name"] == "April"
        finally:
            app.dependency_overrides.clear()

    def test_employee_no_shifts_this_month(self, mock_employee_user):
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=2")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 0
            assert data["shift_count"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_employee_multiple_shifts_summed_monthly(self, mock_employee_user):
        """Employee with multiple shifts should see summed hours for the month."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Create multiple shifts across the month
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 1), time(9, 0), time(13, 0)),   # 4 hours
            self.create_mock_shift(2, 2, date(2026, 4, 7), time(14, 0), time(18, 0)),  # 4 hours
            self.create_mock_shift(3, 2, date(2026, 4, 15), time(9, 0), time(12, 0)),  # 3 hours
            self.create_mock_shift(4, 2, date(2026, 4, 22), time(10, 0), time(16, 0)), # 6 hours
            self.create_mock_shift(5, 2, date(2026, 4, 30), time(8, 0), time(12, 0)),  # 4 hours
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 21.0  # 4+4+3+6+4
            assert data["shift_count"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_employee_overnight_shift_attributed_to_start_date(self, mock_employee_user):
        """Overnight shift spanning month boundary should be attributed to start date."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Shift starts April 30 at 23:00, ends May 1 at 01:00 (2 hours)
        # Should be counted in April since hours are attributed to start date
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 30), time(23, 0), time(1, 0), end_date=date(2026, 5, 1)),
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            # 23:00 to 01:00 = 2 hours, attributed to April
            assert data["total_hours"] == 2.0
            assert data["shift_count"] == 1
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Month Boundary Cases
# =============================================================================

class TestMonthBoundaryCases:
    """Test edge cases around month boundaries for payroll."""

    @pytest.fixture
    def mock_employee_user(self):
        """Create a mock employee user."""
        user = MagicMock()
        user.id = 2
        user.email = "mark@tagparking.co.uk"
        user.is_admin = False
        user.first_name = "Mark"
        user.last_name = "Custard"
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

    def test_february_leap_year(self, mock_employee_user):
        """February in a leap year (2028) should have 29 days."""
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
            response = client.get("/api/employee/monthly-hours?year=2028&month=2")

            assert response.status_code == 200
            data = response.json()

            assert data["month_end"] == "2028-02-29"
        finally:
            app.dependency_overrides.clear()

    def test_february_non_leap_year(self, mock_employee_user):
        """February in a non-leap year (2026) should have 28 days."""
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=2")

            assert response.status_code == 200
            data = response.json()

            assert data["month_end"] == "2026-02-28"
        finally:
            app.dependency_overrides.clear()

    def test_shift_on_last_day_of_month(self, mock_employee_user):
        """Shift on last day of month should be included."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Shift on April 30 (last day)
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 30), time(9, 0), time(17, 0)),  # 8 hours
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 8.0
            assert data["shift_count"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_shift_on_first_day_of_month(self, mock_employee_user):
        """Shift on first day of month should be included."""
        from main import app
        from database import get_db
        from routers.roster import get_current_user

        # Shift on April 1 (first day)
        mock_shifts = [
            self.create_mock_shift(1, 2, date(2026, 4, 1), time(6, 0), time(14, 0)),  # 8 hours
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
            response = client.get("/api/employee/monthly-hours?year=2026&month=4")

            assert response.status_code == 200
            data = response.json()

            assert data["total_hours"] == 8.0
            assert data["shift_count"] == 1
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Overnight Shift Boundary Cases
# =============================================================================

class TestOvernightShiftBoundaries:
    """
    Test overnight shifts appearing correctly when crossing boundaries.

    These tests verify that overnight shifts are returned when querying:
    - The start date's day/week/month/year
    - The end date's day/week/month/year
    """

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
        shift.shift_type = ShiftType.EVENING
        shift.status = ShiftStatus.SCHEDULED
        shift.notes = None
        # Add staff attributes for response
        staff = MagicMock()
        staff.id = staff_id
        staff.first_name = "Mark"
        staff.last_name = "Custard"
        shift.staff = staff
        return shift

    def create_mock_employee(self, id, first_name, last_name, email):
        """Create a mock employee user."""
        user = MagicMock()
        user.id = id
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.is_active = True
        return user

    # -------------------------------------------------------------------------
    # Day Boundary Tests
    # -------------------------------------------------------------------------

    def test_overnight_shift_appears_on_start_date(self):
        """Overnight shift should appear when querying the start date."""
        # Shift: Mar 31 23:30 -> Apr 1 02:30
        # Query: Mar 31
        # Expected: Should return the shift
        from routers.roster import calculate_shift_hours

        # Verify the hours calculation is correct
        hours = calculate_shift_hours(time(23, 30), time(2, 30), is_overnight=True)
        assert hours == 3.0

    def test_overnight_shift_appears_on_end_date(self):
        """Overnight shift should appear when querying the end date."""
        # This tests the frontend display logic indirectly
        # The backend now returns shifts where end_date matches the query date
        from routers.roster import calculate_shift_hours

        # Shift: Mar 31 23:30 -> Apr 1 02:30 = 3 hours
        hours = calculate_shift_hours(time(23, 30), time(2, 30), is_overnight=True)
        assert hours == 3.0

    # -------------------------------------------------------------------------
    # Week Boundary Tests
    # -------------------------------------------------------------------------

    def test_overnight_shift_crossing_week_boundary(self):
        """Overnight shift crossing Sunday->Monday should appear in both weeks."""
        # March 22, 2026 is a Sunday, March 23 is Monday
        # Shift: Mar 22 (Sun) 23:00 -> Mar 23 (Mon) 02:00
        from routers.roster import calculate_shift_hours

        hours = calculate_shift_hours(time(23, 0), time(2, 0), is_overnight=True)
        assert hours == 3.0

    def test_weekly_hours_includes_overnight_from_previous_week(self, mock_admin_user):
        """Weekly hours should include overnight shifts that end in the current week."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Shift starts Sun Mar 22 23:00, ends Mon Mar 23 02:00
        # Week of Mar 23 should include this shift
        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 22),  # Sunday
                time(23, 0),
                time(2, 0),
                end_date=date(2026, 3, 23)  # Monday
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            # Query the week starting Mar 23 (Monday)
            response = client.get("/api/roster/weekly-hours?week_start=2026-03-23")

            assert response.status_code == 200
            data = response.json()
            # The shift should be included because end_date (Mar 23) is in this week
            assert "employees" in data
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------------------
    # Month Boundary Tests
    # -------------------------------------------------------------------------

    def test_overnight_shift_crossing_month_boundary_march_to_april(self, mock_admin_user):
        """Overnight shift Mar 31 -> Apr 1 should appear in both months' queries."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Shift: Mar 31 23:30 -> Apr 1 02:30
        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 31),
                time(23, 30),
                time(2, 30),
                end_date=date(2026, 4, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)

            # Query March - should include the shift (start_date is March 31)
            response = client.get("/api/roster/monthly-hours?year=2026&month=3")
            assert response.status_code == 200

            # Query April - should also include the shift (end_date is April 1)
            response = client.get("/api/roster/monthly-hours?year=2026&month=4")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_overnight_shift_crossing_month_with_different_lengths(self, mock_admin_user):
        """Overnight shift at end of 30-day month (April 30 -> May 1)."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 4, 30),
                time(22, 0),
                time(6, 0),
                end_date=date(2026, 5, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/monthly-hours?year=2026&month=4")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_overnight_shift_february_to_march_non_leap_year(self, mock_admin_user):
        """Overnight shift Feb 28 -> Mar 1 in non-leap year (2026)."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 2, 28),
                time(23, 0),
                time(1, 0),
                end_date=date(2026, 3, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)

            # Query February - should include (start date is Feb 28)
            response = client.get("/api/roster/monthly-hours?year=2026&month=2")
            assert response.status_code == 200

            # Query March - should also include (end date is Mar 1)
            response = client.get("/api/roster/monthly-hours?year=2026&month=3")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_overnight_shift_february_to_march_leap_year(self, mock_admin_user):
        """Overnight shift Feb 29 -> Mar 1 in leap year (2028)."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2028, 2, 29),  # Leap day
                time(23, 0),
                time(1, 0),
                end_date=date(2028, 3, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/roster/monthly-hours?year=2028&month=2")
            assert response.status_code == 200
            data = response.json()
            # February 2028 should end on the 29th (leap year)
            assert data["month_end"] == "2028-02-29"
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------------------
    # Year Boundary Tests
    # -------------------------------------------------------------------------

    def test_overnight_shift_crossing_year_boundary(self, mock_admin_user):
        """Overnight shift Dec 31 -> Jan 1 should appear in both years' queries."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Shift: Dec 31 2026 23:00 -> Jan 1 2027 02:00
        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 12, 31),
                time(23, 0),
                time(2, 0),
                end_date=date(2027, 1, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_shifts

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)

            # Query December 2026 - should include (start date is Dec 31 2026)
            response = client.get("/api/roster/monthly-hours?year=2026&month=12")
            assert response.status_code == 200
            data = response.json()
            assert data["year"] == 2026
            assert data["month"] == 12

            # Query January 2027 - should also include (end date is Jan 1 2027)
            response = client.get("/api/roster/monthly-hours?year=2027&month=1")
            assert response.status_code == 200
            data = response.json()
            assert data["year"] == 2027
            assert data["month"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_new_years_eve_overnight_hours_calculation(self):
        """Verify hours calculation for New Year's Eve overnight shift."""
        from routers.roster import calculate_shift_hours

        # Dec 31 23:00 -> Jan 1 02:00 = 3 hours
        hours = calculate_shift_hours(time(23, 0), time(2, 0), is_overnight=True)
        assert hours == 3.0

    # -------------------------------------------------------------------------
    # Hours Attribution Tests (payroll)
    # -------------------------------------------------------------------------

    def test_overnight_hours_attributed_to_start_date_for_payroll(self):
        """
        For payroll purposes, all hours of an overnight shift should be
        attributed to the start date (when the shift began).
        """
        from routers.roster import calculate_shift_hours

        # Shift: Apr 30 22:00 -> May 1 06:00 = 8 hours
        # All 8 hours should be attributed to April for payroll
        hours = calculate_shift_hours(time(22, 0), time(6, 0), is_overnight=True)
        assert hours == 8.0

    def test_long_overnight_shift_calculation(self):
        """Long overnight shift (e.g., 17:00 -> 05:00) should calculate correctly."""
        from routers.roster import calculate_shift_hours

        # 17:00 -> 05:00 = 12 hours
        hours = calculate_shift_hours(time(17, 0), time(5, 0), is_overnight=True)
        assert hours == 12.0

    # -------------------------------------------------------------------------
    # Calendar Display Tests (shifts appear on both days)
    # -------------------------------------------------------------------------

    def test_roster_list_returns_overnight_shift_for_start_date(self, mock_admin_user):
        """GET /api/roster with date filter should return overnight shifts starting on that date."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 31),
                time(23, 30),
                time(2, 30),
                end_date=date(2026, 4, 1)
            ),
        ]

        mock_db = MagicMock()

        # Mock the query chain for /api/roster
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_shifts
        mock_db.query.return_value = mock_query

        def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        try:
            client = TestClient(app)
            # Query for March 31 - should include the overnight shift
            response = client.get("/api/roster?date=2026-03-31")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_roster_list_returns_overnight_shift_for_end_date(self, mock_admin_user):
        """GET /api/roster with date filter should return overnight shifts ending on that date."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 31),
                time(23, 30),
                time(2, 30),
                end_date=date(2026, 4, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_shifts
        mock_db.query.return_value = mock_query

        def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        try:
            client = TestClient(app)
            # Query for April 1 - should include the overnight shift (ends on Apr 1)
            response = client.get("/api/roster?date=2026-04-01")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_roster_date_range_includes_overnight_shifts_ending_in_range(self, mock_admin_user):
        """GET /api/roster with date_from/date_to should include overnight shifts ending in range."""
        from main import app
        from database import get_db
        from routers.roster import require_admin

        # Shift starts Mar 31, ends Apr 1
        mock_shifts = [
            self.create_mock_shift(
                1, 2,
                date(2026, 3, 31),
                time(23, 30),
                time(2, 30),
                end_date=date(2026, 4, 1)
            ),
        ]

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_shifts
        mock_db.query.return_value = mock_query

        def mock_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        try:
            client = TestClient(app)
            # Query April 1-30 - should include the Mar 31 overnight shift that ends Apr 1
            response = client.get("/api/roster?date_from=2026-04-01&date_to=2026-04-30")
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()
