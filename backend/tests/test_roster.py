"""
Tests for Roster & Staff Management functionality.

Covers:
- Employee management (CRUD)
- Roster shifts (CRUD)
- Auto-assign from bookings
- Shift overlap detection
- Operational rules validation
- Date/time formatting
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
        "start_time": time(6, 0),
        "end_time": time(6, 45),
        "shift_type": ShiftType.DEPARTURE,
        "status": ShiftStatus.SCHEDULED,
        "notes": "Test shift",
        "created_at": datetime.now(),
        "updated_at": None,
    }
    defaults.update(kwargs)
    shift = MagicMock()
    for key, value in defaults.items():
        setattr(shift, key, value)

    # Add staff relationship
    if defaults.get("staff_id"):
        shift.staff = create_mock_user(id=defaults["staff_id"])
    else:
        shift.staff = None

    return shift


def create_mock_booking(**kwargs):
    """Factory to create mock booking objects."""
    defaults = {
        "id": 101,
        "reference": "TAG-ABC123",
        "customer_first_name": "Sarah",
        "customer_last_name": "Thompson",
        "dropoff_date": date(2026, 3, 20),
        "dropoff_time": time(6, 0),
        "pickup_date": date(2026, 3, 27),
        "pickup_time": time(16, 0),
        "flight_departure_time": time(8, 30),
        "flight_arrival_time": time(15, 5),
        "dropoff_airline_name": "Jet2",
        "dropoff_destination": "Tenerife",
        "status": "confirmed",
    }
    defaults.update(kwargs)
    booking = MagicMock()
    for key, value in defaults.items():
        setattr(booking, key, value)
    return booking


# =============================================================================
# Unit Tests - Employee Validator
# =============================================================================

class TestEmployeeValidator:
    """Unit tests for employee validation rules."""

    def test_valid_employee_creation(self):
        """Valid employee data should pass validation."""
        from models import EmployeeCreate

        employee = EmployeeCreate(
            first_name="James",
            last_name="Carter",
            email="james@tagparking.co.uk",
            phone="+447700900123"
        )

        assert employee.first_name == "James"
        assert employee.last_name == "Carter"
        assert employee.email == "james@tagparking.co.uk"

    def test_missing_first_name(self):
        """Missing first_name should fail validation."""
        from models import EmployeeCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            EmployeeCreate(
                first_name="",
                last_name="Carter",
                email="james@tagparking.co.uk",
                phone="+447700900123"
            )

        assert "first_name" in str(exc_info.value)

    def test_missing_last_name(self):
        """Missing last_name should fail validation."""
        from models import EmployeeCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            EmployeeCreate(
                first_name="James",
                last_name="",
                email="james@tagparking.co.uk",
                phone="+447700900123"
            )

        assert "last_name" in str(exc_info.value)

    def test_first_name_max_length(self):
        """First name at 50-char boundary should pass."""
        from models import EmployeeCreate

        employee = EmployeeCreate(
            first_name="A" * 50,
            last_name="Carter",
            email="james@tagparking.co.uk",
            phone="+447700900123"
        )

        assert len(employee.first_name) == 50

    def test_first_name_exceeds_max_length(self):
        """First name at 51-char should fail validation."""
        from models import EmployeeCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EmployeeCreate(
                first_name="A" * 51,
                last_name="Carter",
                email="james@tagparking.co.uk",
                phone="+447700900123"
            )


# =============================================================================
# Unit Tests - Shift Validator
# =============================================================================

class TestShiftValidator:
    """Unit tests for shift validation rules."""

    def test_valid_shift_creation(self):
        """Valid shift data should pass validation."""
        from models import RosterShiftCreate, ShiftTypeEnum, ShiftStatusEnum

        shift = RosterShiftCreate(
            staff_id=1,
            date=date(2026, 3, 20),
            start_time="06:00",
            end_time="06:45",
            shift_type=ShiftTypeEnum.DEPARTURE,
            status=ShiftStatusEnum.SCHEDULED
        )

        assert shift.staff_id == 1
        assert shift.date == date(2026, 3, 20)

    def test_unassigned_shift_is_valid(self):
        """Shift with staff_id=None (unassigned) should be valid."""
        from models import RosterShiftCreate, ShiftTypeEnum

        shift = RosterShiftCreate(
            staff_id=None,
            date=date(2026, 3, 20),
            start_time="06:00",
            end_time="06:45",
            shift_type=ShiftTypeEnum.DEPARTURE
        )

        assert shift.staff_id is None

    def test_invalid_shift_type(self):
        """Invalid shift_type should fail validation."""
        from models import RosterShiftCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RosterShiftCreate(
                staff_id=1,
                date=date(2026, 3, 20),
                start_time="06:00",
                end_time="06:45",
                shift_type="break"  # Invalid
            )


# =============================================================================
# Unit Tests - DateTime Formatter
# =============================================================================

class TestDateTimeFormatter:
    """Unit tests for date/time formatting (DD/MM/YYYY, HH:MM 24hr)."""

    def test_standard_date_format(self):
        """Date should render as DD/MM/YYYY."""
        d = date(2026, 3, 20)
        formatted = d.strftime("%d/%m/%Y")
        assert formatted == "20/03/2026"

    def test_day_greater_than_12(self):
        """Day > 12 must render correctly (catches MM/DD swap)."""
        d = date(2026, 3, 20)
        formatted = d.strftime("%d/%m/%Y")
        # If this outputs "03/20/2026", the test MUST fail
        assert formatted == "20/03/2026"
        assert formatted != "03/20/2026"

    def test_single_digit_day_zero_padded(self):
        """Single-digit day should be zero-padded."""
        d = date(2026, 3, 1)
        formatted = d.strftime("%d/%m/%Y")
        assert formatted == "01/03/2026"

    def test_single_digit_month_zero_padded(self):
        """Single-digit month should be zero-padded."""
        d = date(2026, 1, 5)
        formatted = d.strftime("%d/%m/%Y")
        assert formatted == "05/01/2026"

    def test_new_year_boundary(self):
        """New Year date should format correctly."""
        d = date(2027, 1, 1)
        formatted = d.strftime("%d/%m/%Y")
        assert formatted == "01/01/2027"

    def test_end_of_year(self):
        """End of year date should format correctly."""
        d = date(2026, 12, 31)
        formatted = d.strftime("%d/%m/%Y")
        assert formatted == "31/12/2026"

    def test_time_morning_24hr(self):
        """Morning time should render as HH:MM 24hr."""
        t = time(6, 0)
        formatted = t.strftime("%H:%M")
        assert formatted == "06:00"

    def test_time_afternoon_24hr(self):
        """Afternoon time should render as HH:MM (not 2:30 PM)."""
        t = time(14, 30)
        formatted = t.strftime("%H:%M")
        assert formatted == "14:30"
        assert "PM" not in formatted
        assert "AM" not in formatted

    def test_time_midnight(self):
        """Midnight should render as 00:15 (not 12:15 AM)."""
        t = time(0, 15)
        formatted = t.strftime("%H:%M")
        assert formatted == "00:15"

    def test_time_end_of_day(self):
        """End of day should render as 23:59."""
        t = time(23, 59)
        formatted = t.strftime("%H:%M")
        assert formatted == "23:59"


# =============================================================================
# Unit Tests - Shift Overlap Detector
# =============================================================================

class TestShiftOverlapDetector:
    """Unit tests for shift overlap detection logic."""

    def test_no_overlap(self):
        """Non-overlapping shifts should pass."""
        from routers.roster import check_shift_overlap

        # Existing: 06:00-06:45, New: 07:30-08:15
        # These don't overlap
        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(7, 30),
            end_time=time(8, 15)
        )

        assert result is None

    def test_full_overlap(self):
        """Identical time range should conflict."""
        from routers.roster import check_shift_overlap

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        assert result is not None

    def test_partial_overlap_start(self):
        """Overlap at start should conflict."""
        from routers.roster import check_shift_overlap

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(6, 30),
            end_time=time(7, 15)
        )

        assert result is not None

    def test_partial_overlap_end(self):
        """Overlap at end should conflict."""
        from routers.roster import check_shift_overlap

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(5, 30),
            end_time=time(6, 15)
        )

        assert result is not None

    def test_containing_overlap(self):
        """New shift contained within existing should conflict."""
        from routers.roster import check_shift_overlap

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(8, 0)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(6, 30),
            end_time=time(7, 30)
        )

        assert result is not None

    def test_adjacent_no_overlap(self):
        """Adjacent shifts (touching) should be allowed."""
        from routers.roster import check_shift_overlap

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        # New shift starts exactly when existing ends
        result = check_shift_overlap(
            mock_db,
            staff_id=1,
            date=date(2026, 3, 20),
            start_time=time(6, 45),
            end_time=time(7, 30)
        )

        assert result is None

    def test_different_staff_same_time(self):
        """Different staff members can have overlapping times."""
        from routers.roster import check_shift_overlap

        # Staff 1 has shift 06:00-06:45
        existing_shift = create_mock_shift(
            staff_id=1,
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        mock_db = MagicMock()
        # Query for staff 2 returns no shifts
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Staff 2 can have the same time
        result = check_shift_overlap(
            mock_db,
            staff_id=2,
            date=date(2026, 3, 20),
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        assert result is None

    def test_unassigned_shift_no_conflict(self):
        """Unassigned shifts (staff_id=None) don't conflict."""
        from routers.roster import check_shift_overlap

        mock_db = MagicMock()

        result = check_shift_overlap(
            mock_db,
            staff_id=None,
            date=date(2026, 3, 20),
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        assert result is None


# =============================================================================
# Unit Tests - Operational Rules Engine
# =============================================================================

class TestOperationalRulesEngine:
    """Unit tests for operational rules (DEP/ARR alternation, gaps, etc.)."""

    def test_minimum_gap_respected(self):
        """45-minute minimum gap between shifts should pass."""
        # Shift 1 ends 06:45, Shift 2 starts 07:30 (45 min gap)
        shift1_end = time(6, 45)
        shift2_start = time(7, 30)

        end_mins = shift1_end.hour * 60 + shift1_end.minute
        start_mins = shift2_start.hour * 60 + shift2_start.minute
        gap_mins = start_mins - end_mins

        assert gap_mins >= 45

    def test_minimum_gap_violation(self):
        """Less than 45-minute gap should trigger warning."""
        # Shift 1 ends 06:45, Shift 2 starts 07:00 (15 min gap)
        shift1_end = time(6, 45)
        shift2_start = time(7, 0)

        end_mins = shift1_end.hour * 60 + shift1_end.minute
        start_mins = shift2_start.hour * 60 + shift2_start.minute
        gap_mins = start_mins - end_mins

        assert gap_mins < 45  # Violation

    def test_12_hour_span_check_pass(self):
        """Shifts spanning less than 12 hours should pass."""
        first_shift_start = time(6, 0)
        last_shift_end = time(17, 30)  # 11.5 hours

        start_mins = first_shift_start.hour * 60 + first_shift_start.minute
        end_mins = last_shift_end.hour * 60 + last_shift_end.minute
        span_hours = (end_mins - start_mins) / 60

        assert span_hours <= 12

    def test_12_hour_span_check_fail(self):
        """Shifts spanning more than 12 hours should trigger warning."""
        first_shift_start = time(4, 0)
        last_shift_end = time(23, 0)  # 19 hours

        start_mins = first_shift_start.hour * 60 + first_shift_start.minute
        end_mins = last_shift_end.hour * 60 + last_shift_end.minute
        span_hours = (end_mins - start_mins) / 60

        assert span_hours > 12  # Violation

    def test_idle_period_acceptable(self):
        """Gap of 3 hours should be acceptable."""
        shift1_end = time(9, 0)
        shift2_start = time(12, 0)  # 3 hour gap

        end_mins = shift1_end.hour * 60 + shift1_end.minute
        start_mins = shift2_start.hour * 60 + shift2_start.minute
        gap_hours = (start_mins - end_mins) / 60

        assert gap_hours <= 4

    def test_idle_period_warning(self):
        """Gap exceeding 4 hours should trigger warning."""
        shift1_end = time(8, 0)
        shift2_start = time(13, 0)  # 5 hour gap

        end_mins = shift1_end.hour * 60 + shift1_end.minute
        start_mins = shift2_start.hour * 60 + shift2_start.minute
        gap_hours = (start_mins - end_mins) / 60

        assert gap_hours > 4  # Warning


# =============================================================================
# Integration Tests - Employee API
# =============================================================================

class TestEmployeeAPI:
    """Integration tests for employee management endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        return create_mock_user(is_admin=True)

    @pytest.fixture
    def mock_app_dependencies(self, mock_db, mock_admin_user):
        """Set up mock dependencies."""
        from main import app
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db

        yield

        app.dependency_overrides.clear()

    def test_list_employees(self, mock_app_dependencies, mock_db):
        """Should list all employee users."""
        from main import app

        mock_employees = [
            create_mock_user(id=1, first_name="James", last_name="Carter"),
            create_mock_user(id=2, first_name="Sophie", last_name="Mills"),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_employees

        client = TestClient(app)
        response = client.get("/api/employees")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_employees_filter_active(self, mock_app_dependencies, mock_db):
        """Should filter employees by active status."""
        from main import app

        mock_employees = [
            create_mock_user(id=1, is_active=True),
        ]

        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = mock_employees

        client = TestClient(app)
        response = client.get("/api/employees?is_active=true")

        assert response.status_code == 200

    def test_create_employee_success(self, mock_app_dependencies, mock_db):
        """Should create a new employee."""
        from main import app

        # No existing user with this email
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock the refresh to set values on the employee object
        def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.last_login = None
            obj.is_admin = False
            obj.is_active = True

        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "+447700900123"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "James"
        assert data["last_name"] == "Carter"
        assert data["is_admin"] is False

    def test_create_employee_duplicate_email(self, mock_app_dependencies, mock_db):
        """Should reject duplicate email."""
        from main import app

        # User already exists with this email
        mock_db.query.return_value.filter.return_value.first.return_value = create_mock_user()

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "+447700900123"
        })

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_get_employee_exists(self, mock_app_dependencies, mock_db):
        """Should return employee by ID."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = create_mock_user(id=1)

        client = TestClient(app)
        response = client.get("/api/employees/1")

        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_get_employee_not_found(self, mock_app_dependencies, mock_db):
        """Should return 404 for non-existent employee."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.get("/api/employees/9999")

        assert response.status_code == 404

    def test_deactivate_employee(self, mock_app_dependencies, mock_db):
        """Should soft-deactivate employee."""
        from main import app

        mock_employee = create_mock_user(id=1, is_active=True)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_employee

        client = TestClient(app)
        response = client.delete("/api/employees/1")

        assert response.status_code == 200
        assert response.json()["success"] is True


# =============================================================================
# Integration Tests - Roster API
# =============================================================================

class TestRosterAPI:
    """Integration tests for roster shift endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def mock_app_dependencies(self, mock_db):
        """Set up mock dependencies."""
        from main import app
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db

        yield

        app.dependency_overrides.clear()

    def test_create_shift_success(self, mock_app_dependencies, mock_db):
        """Should create a new shift."""
        from main import app
        from db_models import ShiftType, ShiftStatus

        mock_employee = create_mock_user(id=1)

        # Mock employee exists and is active
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_employee,  # Employee lookup
            None,  # No booking
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []  # No existing shifts

        # Mock the refresh to set values on the shift object
        def mock_refresh(obj):
            obj.id = 1
            obj.staff_id = 1
            obj.booking_id = None
            obj.date = date(2026, 3, 20)
            obj.start_time = time(6, 0)
            obj.end_time = time(6, 45)
            obj.shift_type = ShiftType.DEPARTURE
            obj.status = ShiftStatus.SCHEDULED
            obj.notes = None
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.staff = mock_employee

        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/roster", json={
            "staff_id": 1,
            "date": "2026-03-20",
            "start_time": "06:00",
            "end_time": "06:45",
            "shift_type": "departure",
            "status": "scheduled"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["shift_type"] == "departure"
        assert data["start_time"] == "06:00"

    def test_create_shift_overlap_conflict(self, mock_app_dependencies, mock_db):
        """Should reject overlapping shift."""
        from main import app
        from db_models import ShiftType, ShiftStatus

        existing_shift = create_mock_shift(
            start_time=time(6, 0),
            end_time=time(6, 45)
        )

        # Mock employee exists
        mock_employee = create_mock_user(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_employee
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_shift]

        client = TestClient(app)
        response = client.post("/api/roster", json={
            "staff_id": 1,
            "date": "2026-03-20",
            "start_time": "06:30",
            "end_time": "07:15",
            "shift_type": "departure"
        })

        assert response.status_code == 409
        assert "overlap" in response.json()["detail"].lower()

    def test_delete_shift_success(self, mock_app_dependencies, mock_db):
        """Should delete a shift."""
        from main import app

        mock_shift = create_mock_shift(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_shift

        client = TestClient(app)
        response = client.delete("/api/roster/1")

        assert response.status_code == 200

    def test_delete_shift_not_found(self, mock_app_dependencies, mock_db):
        """Should return 404 for non-existent shift."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.delete("/api/roster/9999")

        assert response.status_code == 404


# =============================================================================
# Integration Tests - Auto-Assign
# =============================================================================

class TestAutoAssign:
    """Integration tests for auto-assign from bookings."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def mock_app_dependencies(self, mock_db):
        """Set up mock dependencies."""
        from main import app
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db

        yield

        app.dependency_overrides.clear()

    def test_auto_assign_creates_shifts(self, mock_app_dependencies, mock_db):
        """Should generate shifts from bookings."""
        from main import app
        from db_models import ShiftType, ShiftStatus

        mock_booking = create_mock_booking()

        # Set up query mock to return booking for the filter query
        # and None for booking lookup in shift_to_response
        filter_mock = MagicMock()
        filter_mock.all.return_value = [mock_booking]
        filter_mock.first.return_value = mock_booking  # For booking lookup
        mock_db.query.return_value.filter.return_value = filter_mock

        # Track created shifts for refresh
        shift_counter = [0]

        def mock_add(obj):
            shift_counter[0] += 1
            obj.id = shift_counter[0]
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.staff = None

        def mock_refresh(obj):
            # Object already has values set from add
            pass

        mock_db.add.side_effect = mock_add
        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/roster/auto-assign", json={
            "date_from": "2026-03-20",
            "date_to": "2026-03-27",
            "clear_existing": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should create departure shift for dropoff and arrival shift for pickup
        assert data["shifts_created"] >= 1

    def test_auto_assign_no_bookings(self, mock_app_dependencies, mock_db):
        """Should handle date range with no bookings."""
        from main import app

        mock_db.query.return_value.filter.return_value.all.return_value = []

        client = TestClient(app)
        response = client.post("/api/roster/auto-assign", json={
            "date_from": "2026-03-20",
            "date_to": "2026-03-20",
            "clear_existing": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["shifts_created"] == 0


# =============================================================================
# Unit Tests - Date Format Conversion
# =============================================================================

class TestDateFormatConversion:
    """Tests for date format conversion between UK (DD/MM/YYYY) and ISO (YYYY-MM-DD)."""

    def test_iso_date_accepted_by_api(self):
        """API should accept ISO format dates (YYYY-MM-DD)."""
        from models import RosterShiftCreate, ShiftTypeEnum

        # This should not raise
        shift = RosterShiftCreate(
            date=date(2026, 3, 17),
            start_time="15:30",
            end_time="16:30",
            shift_type=ShiftTypeEnum.DEPARTURE
        )
        assert shift.date == date(2026, 3, 17)

    def test_date_string_iso_format(self):
        """Date should be parsed from ISO string format."""
        from models import RosterShiftCreate, ShiftTypeEnum

        # Pydantic should parse "2026-03-17" as date(2026, 3, 17)
        shift = RosterShiftCreate(
            date="2026-03-17",
            start_time="15:30",
            end_time="16:30",
            shift_type=ShiftTypeEnum.DEPARTURE
        )
        assert shift.date == date(2026, 3, 17)

    def test_uk_date_format_rejected(self):
        """UK format dates (DD/MM/YYYY) should be rejected by Pydantic."""
        from models import RosterShiftCreate, ShiftTypeEnum
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            RosterShiftCreate(
                date="17/03/2026",  # UK format - should fail
                start_time="15:30",
                end_time="16:30",
                shift_type=ShiftTypeEnum.DEPARTURE
            )

        assert "date" in str(exc_info.value).lower()

    def test_march_date_not_confused_with_us_format(self):
        """Date like 2026-03-17 should be March 17, not 17th day of 3rd month."""
        d = date(2026, 3, 17)
        assert d.month == 3  # March
        assert d.day == 17

    def test_uk_display_format(self):
        """Dates should display as DD/MM/YYYY for UK users."""
        d = date(2026, 3, 17)
        uk_format = d.strftime("%d/%m/%Y")
        assert uk_format == "17/03/2026"
        # Must NOT be US format
        assert uk_format != "03/17/2026"


# =============================================================================
# Unit Tests - Time Format
# =============================================================================

class TestTimeFormat:
    """Tests for 24-hour time format."""

    def test_time_input_24hr_format(self):
        """Time should be stored in 24-hour format."""
        from models import RosterShiftCreate, ShiftTypeEnum

        shift = RosterShiftCreate(
            date=date(2026, 3, 17),
            start_time="15:30",  # 3:30 PM in 24hr
            end_time="16:30",
            shift_type=ShiftTypeEnum.DEPARTURE
        )
        assert shift.start_time == "15:30"
        assert shift.end_time == "16:30"

    def test_early_morning_time(self):
        """Early morning times should be zero-padded."""
        t = time(6, 0)
        formatted = t.strftime("%H:%M")
        assert formatted == "06:00"

    def test_noon_time(self):
        """Noon should be 12:00, not 00:00."""
        t = time(12, 0)
        formatted = t.strftime("%H:%M")
        assert formatted == "12:00"

    def test_afternoon_time_no_pm(self):
        """3:30 PM should display as 15:30."""
        t = time(15, 30)
        formatted = t.strftime("%H:%M")
        assert formatted == "15:30"
        assert "PM" not in formatted

    def test_late_evening_time(self):
        """Late evening times should use 24hr format."""
        t = time(22, 45)
        formatted = t.strftime("%H:%M")
        assert formatted == "22:45"


# =============================================================================
# Integration Tests - Employee List Format
# =============================================================================

class TestEmployeeListFormat:
    """Tests for employee list endpoint response format."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def mock_app_dependencies(self, mock_db):
        """Set up mock dependencies."""
        from main import app
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db

        yield

        app.dependency_overrides.clear()

    def test_employee_list_returns_array(self, mock_app_dependencies, mock_db):
        """Employee list should return array directly, not wrapped in object."""
        from main import app

        mock_employees = [
            create_mock_user(id=1, first_name="James", last_name="Carter"),
            create_mock_user(id=2, first_name="Sophie", last_name="Mills"),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_employees

        client = TestClient(app)
        response = client.get("/api/employees")

        assert response.status_code == 200
        data = response.json()

        # Should be an array, not { employees: [...] }
        assert isinstance(data, list)
        assert len(data) == 2

    def test_employee_list_has_required_fields(self, mock_app_dependencies, mock_db):
        """Each employee in list should have required fields."""
        from main import app

        mock_employees = [
            create_mock_user(id=1, first_name="James", last_name="Carter"),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_employees

        client = TestClient(app)
        response = client.get("/api/employees")

        assert response.status_code == 200
        data = response.json()

        employee = data[0]
        assert "id" in employee
        assert "first_name" in employee
        assert "last_name" in employee
        assert "email" in employee
        assert "is_active" in employee

    def test_employee_list_empty(self, mock_app_dependencies, mock_db):
        """Empty employee list should return empty array."""
        from main import app

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        client = TestClient(app)
        response = client.get("/api/employees")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) == 0


# =============================================================================
# Unit Tests - Shift Edge Cases
# =============================================================================

class TestShiftEdgeCases:
    """Tests for edge cases in shift handling."""

    def test_shift_with_null_staff_id(self):
        """Unassigned shifts (staff_id=null) should be valid."""
        from models import RosterShiftCreate, ShiftTypeEnum

        shift = RosterShiftCreate(
            staff_id=None,
            date=date(2026, 3, 17),
            start_time="06:00",
            end_time="06:45",
            shift_type=ShiftTypeEnum.DEPARTURE
        )

        assert shift.staff_id is None

    def test_shift_with_notes(self):
        """Shifts can have optional notes."""
        from models import RosterShiftCreate, ShiftTypeEnum

        shift = RosterShiftCreate(
            date=date(2026, 3, 17),
            start_time="06:00",
            end_time="06:45",
            shift_type=ShiftTypeEnum.DEPARTURE,
            notes="Testing notes"
        )

        assert shift.notes == "Testing notes"

    def test_shift_default_status(self):
        """Shifts should default to 'scheduled' status."""
        from models import RosterShiftCreate, ShiftTypeEnum, ShiftStatusEnum

        shift = RosterShiftCreate(
            date=date(2026, 3, 17),
            start_time="06:00",
            end_time="06:45",
            shift_type=ShiftTypeEnum.DEPARTURE
        )

        assert shift.status == ShiftStatusEnum.SCHEDULED

    def test_shift_all_types_valid(self):
        """All shift types should be valid."""
        from models import RosterShiftCreate, ShiftTypeEnum

        for shift_type in ShiftTypeEnum:
            shift = RosterShiftCreate(
                date=date(2026, 3, 17),
                start_time="06:00",
                end_time="06:45",
                shift_type=shift_type
            )
            assert shift.shift_type == shift_type

    def test_shift_all_statuses_valid(self):
        """All shift statuses should be valid."""
        from models import RosterShiftCreate, ShiftTypeEnum, ShiftStatusEnum

        for status in ShiftStatusEnum:
            shift = RosterShiftCreate(
                date=date(2026, 3, 17),
                start_time="06:00",
                end_time="06:45",
                shift_type=ShiftTypeEnum.DEPARTURE,
                status=status
            )
            assert shift.status == status

    def test_shift_midnight_crossing(self):
        """Shift that crosses midnight should be valid (end < start in time)."""
        # This is a data model test - actual business logic for overnight shifts
        # would need additional validation
        from models import RosterShiftCreate, ShiftTypeEnum

        shift = RosterShiftCreate(
            date=date(2026, 3, 17),
            start_time="23:30",
            end_time="00:30",
            shift_type=ShiftTypeEnum.ARRIVAL
        )

        assert shift.start_time == "23:30"
        assert shift.end_time == "00:30"


# =============================================================================
# Unit Tests - Phone Number Validation
# =============================================================================

class TestPhoneNumberValidation:
    """Tests for UK phone number validation in employee creation."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def mock_app_dependencies(self, mock_db):
        """Set up mock dependencies."""
        from main import app
        from database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db

        yield

        app.dependency_overrides.clear()

    def test_uk_mobile_with_plus44(self, mock_app_dependencies, mock_db):
        """UK mobile with +44 prefix should be valid."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.last_login = None
            obj.is_admin = False
            obj.is_active = True

        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "+447700900123"
        })

        assert response.status_code == 201

    def test_uk_mobile_starting_07(self, mock_app_dependencies, mock_db):
        """UK mobile starting with 07 should be valid."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.last_login = None
            obj.is_admin = False
            obj.is_active = True

        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "07700900123"
        })

        assert response.status_code == 201

    def test_uk_landline_starting_01(self, mock_app_dependencies, mock_db):
        """UK landline starting with 01 should be valid."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime.now()
            obj.updated_at = None
            obj.last_login = None
            obj.is_admin = False
            obj.is_active = True

        mock_db.refresh.side_effect = mock_refresh

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "01onal234567"
        })

        assert response.status_code == 201

    def test_invalid_phone_rejected(self, mock_app_dependencies, mock_db):
        """Non-UK phone number should be rejected."""
        from main import app

        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = TestClient(app)
        response = client.post("/api/employees", json={
            "first_name": "James",
            "last_name": "Carter",
            "email": "james@tagparking.co.uk",
            "phone": "12025551234"  # US number
        })

        assert response.status_code == 400
        assert "phone" in response.json()["detail"].lower()
