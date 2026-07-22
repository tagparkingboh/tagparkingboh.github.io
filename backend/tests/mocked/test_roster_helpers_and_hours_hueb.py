"""
Additional mocked HUEB coverage for routers/roster.py.

Targets deliberately broad, low-risk surfaces that were under-covered in the
file-level report:

* small helper boundaries
* auth dependency unhappy/edge cases
* staff list/detail endpoints
* weekly/monthly hours API summaries

The tests use mocked DB query chains and FastAPI TestClient where route
serialization matters, so coverage lands on the real router code without
requiring a database.
"""
import json
from datetime import date, datetime, timedelta, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from database import get_db
from db_models import (
    AuditLog,
    AuditLogEvent,
    Booking,
    EmployeeHoliday,
    HolidayType,
    PlannerRun,
    PlannerRunFeedback,
    RosterPlannerSettings as DbRosterPlannerSettings,
    RosterShift,
    ShiftBookingLink,
    ShiftStatus,
    ShiftType,
    User,
)
from main import app
from routers.roster import (
    calculate_shift_hours,
    check_holiday_time_overlap,
    check_shift_overlap,
    check_staff_unavailability,
    format_time,
    get_current_user,
    get_staff_initials,
    normalise_uk_phone,
    check_shift_conflict_for_unavailability,
    _shifts_overlap_for_staff,
    parse_time_string,
    parse_time_for_unavailability,
    require_qa_admin,
    require_admin,
    validate_staff_assignment,
)


def _admin():
    return SimpleNamespace(
        id=1,
        email="admin@tag.test",
        is_admin=True,
        is_active=True,
        first_name="Admin",
        last_name="User",
    )


def _employee(id=2, first_name="Jock", last_name="Ey", email=None, active=True):
    return SimpleNamespace(
        id=id,
        first_name=first_name,
        last_name=last_name,
        email=email or f"{first_name.lower()}@tag.test",
        phone="07911123456",
        is_admin=False,
        is_active=active,
        auto_assign_excluded=False,
        created_at=datetime(2026, 6, 1, 9, 0),
        updated_at=None,
        last_login=None,
        driver_type="jockey",
    )


def _shift(
    staff_id=2,
    shift_date=date(2026, 6, 2),
    start=time(9, 0),
    end=time(17, 0),
    end_date=None,
    source="manual",
    staff=None,
):
    return SimpleNamespace(
        id=100 + (staff_id or 0),
        staff_id=staff_id,
        staff=staff,
        booking_id=None,
        bookings=[],
        notes=None,
        planner_run_id=None,
        intended_driver_type="jockey",
        admin_shaped_at=None,
        suppressed_at=None,
        suppressed_by_user_id=None,
        suppression_reason=None,
        parent_shift_id=None,
        locked=False,
        independent_from_parent=False,
        created_at=datetime(2026, 6, 1, 9, 0),
        updated_at=None,
        date=shift_date,
        end_date=end_date or shift_date,
        start_time=start,
        end_time=end,
        created_source=source,
        status=ShiftStatus.SCHEDULED,
        shift_type=ShiftType.MORNING,
    )


def _holiday(
    id=10,
    staff_id=2,
    start_date=date(2026, 7, 6),
    end_date=date(2026, 7, 6),
    start_time=None,
    end_time=None,
    holiday_type=HolidayType.HOLIDAY,
    staff=None,
):
    staff = staff or _employee(staff_id, "Holly", "Day")
    return SimpleNamespace(
        id=id,
        staff_id=staff_id,
        staff=staff,
        staff_initials=get_staff_initials(staff),
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        holiday_type=holiday_type,
        notes="time away",
        created_at=datetime(2026, 6, 1, 9, 0),
        created_by="admin@tag.test",
    )


def _query(all_result=None, first_result=None, count_result=0):
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.limit.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = [] if all_result is None else all_result
    chain.first.return_value = first_result
    chain.one_or_none.return_value = first_result
    chain.count.return_value = count_result
    chain.delete.return_value = 0
    return chain


def _override_db(db):
    def _gen():
        yield db

    app.dependency_overrides[get_db] = _gen


def _shift_response_payload(shift):
    return {
        "id": getattr(shift, "id", 999),
        "staff_id": getattr(shift, "staff_id", None),
        "staff_first_name": None,
        "staff_last_name": None,
        "staff_initials": None,
        "booking_id": None,
        "booking_reference": None,
        "booking_type": None,
        "booking_customer_name": None,
        "booking_vehicle_registration": None,
        "booking_time": None,
        "booking_flight_number": None,
        "booking_destination": None,
        "bookings": [],
        "date": getattr(shift, "date", date(2026, 6, 1)).isoformat(),
        "end_date": (getattr(shift, "end_date", None) or getattr(shift, "date", date(2026, 6, 1))).isoformat(),
        "start_time": format_time(getattr(shift, "start_time", time(9, 0))),
        "end_time": format_time(getattr(shift, "end_time", time(17, 0))),
        "shift_type": getattr(getattr(shift, "shift_type", ShiftType.MORNING), "value", "morning"),
        "status": getattr(getattr(shift, "status", ShiftStatus.SCHEDULED), "value", "scheduled"),
        "notes": getattr(shift, "notes", None),
        "intended_driver_type": getattr(shift, "intended_driver_type", None) or "jockey",
        "created_source": getattr(shift, "created_source", None),
        "admin_shaped_at": None,
        "created_at": datetime(2026, 6, 1, 9, 0).isoformat(),
        "updated_at": None,
        "suppressed_at": None,
        "suppressed_by_user_id": None,
        "suppression_reason": None,
    }


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestRosterHelperHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_time_and_phone_helpers_normalise_common_inputs(self):
        assert parse_time_string("09:05") == time(9, 5)
        assert format_time(time(23, 30)) == "23:30"
        assert get_staff_initials(SimpleNamespace(first_name="Lee", last_name="Naylor")) == "LN"
        assert normalise_uk_phone("07911 123 456") == "+447911123456"
        assert calculate_shift_hours(time(9, 0), time(17, 30)) == 8.5

    # --- UNHAPPY -------------------------------------------------------------

    @pytest.mark.parametrize("bad", ["", None, "09", "xx:10", "25:00"])
    def test_U_parse_time_string_rejects_invalid_times(self, bad):
        with pytest.raises(HTTPException) as exc:
            parse_time_string(bad)
        assert exc.value.status_code == 400

    def test_U_validate_staff_assignment_rejects_missing_or_inactive_staff(self):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        with pytest.raises(HTTPException) as missing:
            validate_staff_assignment(db, 404)
        assert missing.value.status_code == 404

        db.query.return_value = _query(first_result=SimpleNamespace(is_active=False))
        with pytest.raises(HTTPException) as inactive:
            validate_staff_assignment(db, 2)
        assert inactive.value.status_code == 400

    # --- EDGE ----------------------------------------------------------------

    def test_E_overlap_helpers_detect_full_day_and_partial_conflicts(self):
        assert check_holiday_time_overlap(None, None, time(9), time(10)) is True
        assert check_holiday_time_overlap(time(9), time(12), None, None) is True
        assert check_holiday_time_overlap(time(9), time(12), time(12), time(13)) is False
        assert check_holiday_time_overlap(time(9), time(12), time(11, 59), time(13)) is True

    def test_E_staff_and_phone_helpers_cover_empty_and_stored_variants(self):
        assert get_staff_initials(None) is None
        assert normalise_uk_phone(None) is None
        assert normalise_uk_phone("+") is None
        assert normalise_uk_phone("+447911123456") == "+447911123456"
        assert normalise_uk_phone("447911123456") == "+447911123456"
        assert normalise_uk_phone("12345") == "12345"

    def test_E_staff_unavailability_handles_full_day_and_overnight_overlap(self):
        full_day = SimpleNamespace(start_time=None, end_time=None)
        db = MagicMock()
        db.query.return_value = _query(all_result=[full_day])
        assert check_staff_unavailability(db, 2, date(2026, 6, 2), time(9), time(10)) is full_day

        overnight = SimpleNamespace(start_time=time(22), end_time=time(2))
        db.query.return_value = _query(all_result=[overnight])
        assert check_staff_unavailability(db, 2, date(2026, 6, 2), time(23), time(1)) is overnight

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_shift_overlap_respects_touching_boundaries_and_overnight_windows(self):
        db = MagicMock()
        existing = _shift(start=time(9), end=time(12))
        db.query.return_value = _query(all_result=[existing])
        assert check_shift_overlap(db, 2, date(2026, 6, 2), time(12), time(13)) is None
        assert check_shift_overlap(db, 2, date(2026, 6, 2), time(11, 59), time(13)) is existing

        overnight = _shift(start=time(22), end=time(2))
        db.query.return_value = _query(all_result=[overnight])
        assert check_shift_overlap(db, 2, date(2026, 6, 2), time(1), time(3)) is None
        assert check_shift_overlap(db, 2, date(2026, 6, 2), time(23), time(23, 30)) is overnight

    def test_B_shift_and_unavailability_helpers_skip_unassigned_or_empty_results(self):
        db = MagicMock()
        db.query.return_value = _query(all_result=[])

        assert check_shift_overlap(db, None, date(2026, 6, 2), time(9), time(10)) is None
        assert check_staff_unavailability(db, None, date(2026, 6, 2), time(9), time(10)) is None
        assert check_staff_unavailability(db, 2, date(2026, 6, 2), time(9), time(10)) is None


class TestRosterAuthDependencyHUEB:
    # --- HAPPY ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_H_get_current_user_returns_active_user_for_valid_bearer_session(self):
        session = SimpleNamespace(user_id=7)
        user = SimpleNamespace(id=7, is_active=True)
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=session),
            _query(first_result=user),
        ]

        assert await get_current_user("Bearer abc123", db) is user

    # --- UNHAPPY / EDGE / BOUNDARY ------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "header,detail",
        [
            (None, "Not authenticated"),
            ("Token abc", "Invalid authorization header"),
            ("Bearer", "Invalid authorization header"),
        ],
    )
    async def test_U_get_current_user_rejects_missing_or_malformed_headers(self, header, detail):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(header, MagicMock())
        assert exc.value.status_code == 401
        assert exc.value.detail == detail

    @pytest.mark.asyncio
    async def test_E_get_current_user_rejects_expired_session_and_inactive_user(self):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        with pytest.raises(HTTPException) as expired:
            await get_current_user("Bearer expired", db)
        assert expired.value.detail == "Invalid or expired session"

        db.query.side_effect = [
            _query(first_result=SimpleNamespace(user_id=2)),
            _query(first_result=None),
        ]
        with pytest.raises(HTTPException) as inactive:
            await get_current_user("Bearer valid", db)
        assert inactive.value.detail == "User not found or inactive"

    @pytest.mark.asyncio
    async def test_B_require_admin_accepts_admin_and_rejects_employee(self):
        assert await require_admin(_admin()) == _admin()
        with pytest.raises(HTTPException) as exc:
            await require_admin(SimpleNamespace(is_admin=False))
        assert exc.value.status_code == 403


class TestStaffEndpointsHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_list_staff_filters_and_serializes_all_users(self, client):
        staff = [_employee(2, "Lee", "Naylor"), _employee(3, "Kay", "Able")]
        db = MagicMock()
        db.query.return_value = _query(all_result=staff)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/staff?is_active=true&auto_assign_excluded=false")

        assert response.status_code == 200
        assert [row["first_name"] for row in response.json()] == ["Lee", "Kay"]

    def test_H_get_employee_returns_employee_detail(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=_employee(4, "Mia", "Driver"))
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/employees/4")

        assert response.status_code == 200
        assert response.json()["email"] == "mia@tag.test"

    def test_H_list_employees_filters_active_employee_users(self, client):
        employees = [_employee(2, "Lee", "Naylor"), _employee(3, "Mia", "Driver")]
        db = MagicMock()
        db.query.return_value = _query(all_result=employees)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/employees?is_active=true")

        assert response.status_code == 200
        assert [row["last_name"] for row in response.json()] == ["Naylor", "Driver"]

    def test_H_create_employee_success_sets_defaults_and_serializes(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)

        def refresh(obj):
            obj.id = 42
            obj.created_at = datetime(2026, 6, 1, 9, 0)
            obj.updated_at = None
            obj.last_login = None
            obj.auto_assign_excluded = False

        db.refresh.side_effect = refresh
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.post(
            "/api/employees",
            json={
                "first_name": "New",
                "last_name": "Driver",
                "email": "NEW@TAG.TEST",
                "phone": "07911123456",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["id"] == 42
        assert payload["email"] == "new@tag.test"
        assert payload["is_active"] is True
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_H_update_employee_success_applies_changed_fields(self, client):
        employee = _employee(8, "Old", "Name", email="old@tag.test")
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=employee),
            _query(first_result=None),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.put(
            "/api/employees/8",
            json={
                "first_name": "New",
                "last_name": "Name",
                "email": "NEW@TAG.TEST",
                "phone": "01202123456",
            },
        )

        assert response.status_code == 200
        assert response.json()["first_name"] == "New"
        assert response.json()["email"] == "new@tag.test"
        assert employee.phone == "01202123456"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_get_employee_returns_404_for_missing_employee(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/employees/404")

        assert response.status_code == 404
        assert response.json()["detail"] == "Employee not found"

    # --- EDGE ----------------------------------------------------------------

    def test_E_create_employee_rejects_duplicate_email(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=_employee(9))
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.post(
            "/api/employees",
            json={
                "first_name": "New",
                "last_name": "Driver",
                "email": "exists@tag.test",
                "phone": "07911123456",
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Email already exists"

    def test_E_create_employee_rejects_non_uk_phone(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.post(
            "/api/employees",
            json={
                "first_name": "New",
                "last_name": "Driver",
                "email": "new@tag.test",
                "phone": "555-0100",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid UK phone number"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_deactivate_and_reactivate_employee_toggle_active_flag(self, client):
        employee = _employee(5, "Boundary", "Driver")
        db = MagicMock()
        db.query.return_value = _query(first_result=employee)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        deactivate = client.delete("/api/employees/5")
        assert deactivate.status_code == 200
        assert employee.is_active is False

        reactivate = client.post("/api/employees/5/reactivate")
        assert reactivate.status_code == 200
        assert employee.is_active is True


class TestBookingsForDateEndpointHUEB:
    def _booking(
        self,
        id,
        ref,
        dropoff_date=date(2026, 7, 2),
        pickup_date=date(2026, 7, 9),
        flight_arrival_date=None,
        dropoff_time=time(10, 0),
        pickup_time=time(18, 30),
        flight_departure_time=time(12, 0),
        flight_arrival_time=time(18, 0),
    ):
        return SimpleNamespace(
            id=id,
            reference=ref,
            dropoff_date=dropoff_date,
            pickup_date=pickup_date,
            flight_arrival_date=flight_arrival_date,
            dropoff_time=dropoff_time,
            pickup_time=pickup_time,
            flight_departure_time=flight_departure_time,
            flight_arrival_time=flight_arrival_time,
            customer_first_name="Test",
            customer_last_name="Customer",
            dropoff_flight_number="BY1234",
            dropoff_airline_name="TUI Airways",
            dropoff_destination="Palma de Mallorca",
            pickup_flight_number="BY1235",
            pickup_airline_name="TUI Airways",
            pickup_origin="Palma de Mallorca Airport",
        )

    # --- HAPPY / EDGE / BOUNDARY -------------------------------------------

    def test_H_get_bookings_for_date_returns_sorted_dropoffs_and_canonical_pickups(self, client):
        dropoff = self._booking(
            id=1,
            ref="TAG-DROP",
            dropoff_time=time(10, 30),
            flight_departure_time=time(12, 30),
        )
        pickup = self._booking(
            id=2,
            ref="TAG-PICK",
            dropoff_date=date(2026, 7, 1),
            pickup_date=date(2026, 7, 1),
            flight_arrival_date=date(2026, 7, 2),
            pickup_time=time(8, 30),
            flight_arrival_time=time(8, 0),
        )
        non_matching = self._booking(
            id=3,
            ref="TAG-OTHER",
            dropoff_date=date(2026, 7, 1),
            pickup_date=date(2026, 7, 3),
            flight_arrival_date=date(2026, 7, 3),
            pickup_time=time(9, 0),
        )
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[dropoff]),
            _query(all_result=[pickup, non_matching]),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/bookings-for-date?date=2026-07-02")

        assert response.status_code == 200
        payload = response.json()
        assert [row["reference"] for row in payload] == ["TAG-PICK", "TAG-DROP"]
        assert payload[0]["type"] == "pickup"
        assert payload[0]["flight_time"] == "08:00"
        assert payload[1]["type"] == "dropoff"
        assert payload[1]["flight_time"] == "12:30"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_get_bookings_for_date_empty_day_returns_empty_list(self, client):
        db = MagicMock()
        db.query.side_effect = [_query(all_result=[]), _query(all_result=[])]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/bookings-for-date?date=2026-07-02")

        assert response.status_code == 200
        assert response.json() == []


class TestRosterDetailAndCreateHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_get_shift_returns_serialized_shift_detail(self, client, monkeypatch):
        shift = _shift(staff_id=None, shift_date=date(2026, 7, 6), start=time(7), end=time(11))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.get("/api/roster/100")

        assert response.status_code == 200
        assert response.json()["start_time"] == "07:00"

    def test_H_create_shift_links_booking_and_derives_assigned_driver_type(self, client, monkeypatch):
        added = []
        db = MagicMock()

        def query_for(model):
            if model is Booking:
                return _query(first_result=SimpleNamespace(id=501))
            if model is User:
                return _query(first_result=SimpleNamespace(id=2, is_active=True, driver_type="fleet"))
            return _query()

        def add(obj):
            added.append(obj)

        def flush():
            added[0].id = 991

        db.query.side_effect = query_for
        db.add.side_effect = add
        db.flush.side_effect = flush
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))
        monkeypatch.setattr("routers.roster.sync_shift_pool_for_shift", lambda *a, **k: [])

        response = client.post(
            "/api/roster",
            json={
                "staff_id": 2,
                "booking_ids": [501],
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
                "status": "scheduled",
                "notes": "airport cover",
                "intended_driver_type": "jockey",
            },
        )

        assert response.status_code == 201
        assert response.json()["id"] == 991
        assert response.json()["intended_driver_type"] == "fleet"
        assert added[0].intended_driver_type == "fleet"
        assert any(getattr(obj, "booking_id", None) == 501 for obj in added[1:])

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_get_shift_returns_404_when_missing(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/404")

        assert response.status_code == 404
        assert response.json()["detail"] == "Shift not found"

    def test_U_create_shift_rejects_missing_linked_booking(self, client, monkeypatch):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)

        response = client.post(
            "/api/roster",
            json={
                "staff_id": None,
                "booking_ids": [404],
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Booking 404 not found"

    # --- EDGE ----------------------------------------------------------------

    def test_E_create_shift_rejects_staff_overlap(self, client, monkeypatch):
        conflict = SimpleNamespace(start_time=time(10), end_time=time(12))
        db = MagicMock()
        db.query.return_value = _query(first_result=SimpleNamespace(id=2, is_active=True))
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: conflict)

        response = client.post(
            "/api/roster",
            json={
                "staff_id": 2,
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
            },
        )

        assert response.status_code == 409
        assert "10:00-12:00" in response.json()["detail"]

    def test_E_create_shift_rejects_timed_unavailability(self, client, monkeypatch):
        unavailability = SimpleNamespace(start_time=time(13), end_time=time(15))
        db = MagicMock()
        db.query.return_value = _query(first_result=SimpleNamespace(id=2, is_active=True))
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: unavailability)

        response = client.post(
            "/api/roster",
            json={
                "staff_id": 2,
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
            },
        )

        assert response.status_code == 409
        assert "13:00-15:00" in response.json()["detail"]

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_create_shift_rejects_full_day_unavailability(self, client, monkeypatch):
        unavailability = SimpleNamespace(start_time=None, end_time=None)
        db = MagicMock()
        db.query.return_value = _query(first_result=SimpleNamespace(id=2, is_active=True))
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: unavailability)

        response = client.post(
            "/api/roster",
            json={
                "staff_id": 2,
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
            },
        )

        assert response.status_code == 409
        assert "06/07/2026" in response.json()["detail"]

    def test_B_create_unassigned_overnight_shift_defaults_end_date_to_start_date(self, client, monkeypatch):
        added = []
        db = MagicMock()
        db.add.side_effect = added.append

        def flush():
            added[0].id = 992

        db.flush.side_effect = flush
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.post(
            "/api/roster",
            json={
                "date": "2026-07-06",
                "start_time": "22:00",
                "end_time": "02:00",
                "shift_type": "evening",
                "intended_driver_type": "fleet",
            },
        )

        assert response.status_code == 201
        assert added[0].staff_id is None
        # v4 end_date normalization: times are canonical — 20:00->02:00
        # crosses midnight, so end_date is derived as start_date + 1 (the old
        # "defaults to start date" behaviour WAS the missing-end_date bug).
        assert added[0].end_date == date(2026, 7, 7)
        assert added[0].intended_driver_type == "fleet"

    def test_B_create_shift_accepts_legacy_single_booking_id(self, client, monkeypatch):
        added = []
        db = MagicMock()
        db.query.return_value = _query(first_result=SimpleNamespace(id=601))
        db.add.side_effect = added.append

        def flush():
            added[0].id = 993

        db.flush.side_effect = flush
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.post(
            "/api/roster",
            json={
                "booking_id": 601,
                "date": "2026-07-06",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
            },
        )

        assert response.status_code == 201
        assert any(getattr(obj, "booking_id", None) == 601 for obj in added[1:])


class TestRosterUpdateAndActionsHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_update_shift_applies_window_staff_status_and_booking_links(self, client, monkeypatch):
        added = []
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=shift),
            _query(first_result=SimpleNamespace(id=3, driver_type="fleet")),
            _query(first_result=SimpleNamespace(id=701)),
            _query(),
        ]
        db.add.side_effect = added.append
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda db, staff_id: SimpleNamespace(is_active=True))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))
        monkeypatch.setattr("routers.roster.sync_shift_pool_for_shift", lambda *a, **k: [])

        response = client.put(
            "/api/roster/100",
            json={
                "staff_id": 3,
                "date": "2026-07-07",
                "end_date": "2026-07-08",
                "start_time": "10:00",
                "end_time": "02:00",
                "shift_type": "evening",
                "status": "confirmed",
                "notes": "moved",
                "booking_ids": [701],
            },
        )

        assert response.status_code == 200
        assert shift.staff_id == 3
        assert shift.date == date(2026, 7, 7)
        assert shift.status == ShiftStatus.CONFIRMED
        assert shift.admin_shaped_at is not None
        assert shift.intended_driver_type == "fleet"
        assert any(getattr(obj, "booking_id", None) == 701 for obj in added)

    def test_H_unassign_shift_clears_staff_and_returns_shift(self, client, monkeypatch):
        shift = _shift(staff_id=7, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.patch("/api/roster/100/unassign")

        assert response.status_code == 200
        assert shift.staff_id is None
        db.commit.assert_called_once()

    def test_H_auto_assign_creates_dropoff_and_pickup_shifts(self, client, monkeypatch):
        booking = SimpleNamespace(
            id=501,
            dropoff_date=date(2026, 7, 6),
            pickup_date=date(2026, 7, 6),
            flight_departure_time=time(10, 0),
            flight_arrival_time=time(23, 30),
            customer_first_name="Test",
            customer_last_name="Customer",
            dropoff_airline_name="TUI",
            dropoff_destination="Palma",
        )
        delete_query = _query(all_result=[])
        delete_query.delete.return_value = 2
        db = MagicMock()
        db.query.side_effect = [
            delete_query,
            _query(all_result=[booking]),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: {**_shift_response_payload(s), "id": 900})

        response = client.post(
            "/api/roster/auto-assign",
            json={"date_from": "2026-07-06", "date_to": "2026-07-06", "clear_existing": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["shifts_deleted"] == 2
        assert payload["shifts_created"] == 2
        assert db.add.call_count == 2

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_update_shift_returns_404_for_missing_shift(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.put("/api/roster/404", json={"notes": "missing"})

        assert response.status_code == 404
        assert response.json()["detail"] == "Shift not found"

    def test_U_update_shift_rejects_missing_legacy_booking(self, client, monkeypatch):
        shift = _shift(staff_id=None, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=shift),
            _query(),
            _query(first_result=None),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)

        response = client.put("/api/roster/100", json={"booking_id": 404})

        assert response.status_code == 400
        assert response.json()["detail"] == "Booking not found"

    def test_U_unassign_shift_returns_404_for_missing_shift(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.patch("/api/roster/404/unassign")

        assert response.status_code == 404
        assert response.json()["detail"] == "Shift not found"

    # --- EDGE ----------------------------------------------------------------

    def test_E_update_shift_rejects_overlap_and_full_day_unavailability(self, client, monkeypatch):
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: _shift(start=time(10), end=time(13)))

        overlap = client.put("/api/roster/100", json={"start_time": "10:30"})
        assert overlap.status_code == 409
        assert "10:00-13:00" in overlap.json()["detail"]

        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: SimpleNamespace(start_time=None, end_time=None))

        unavailable = client.put("/api/roster/100", json={"start_time": "10:30"})
        assert unavailable.status_code == 409
        assert "06/07/2026" in unavailable.json()["detail"]

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_unassign_shift_is_idempotent_when_already_unassigned(self, client, monkeypatch):
        shift = _shift(staff_id=None, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.patch("/api/roster/100/unassign")

        assert response.status_code == 200
        db.commit.assert_not_called()


class TestRosterListFiltersHUEB:
    # --- HAPPY / EDGE / BOUNDARY -------------------------------------------

    @pytest.mark.parametrize(
        "url",
        [
            "/api/roster?source=auto&week_start=2026-07-06&staff_id=2",
            "/api/roster?source=manual&date_from=2026-07-01&date_to=2026-07-31",
            "/api/roster?source=all&date=2026-07-06",
        ],
    )
    def test_HUEB_list_roster_applies_source_and_date_filters(self, client, monkeypatch, url):
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.get(url)

        assert response.status_code == 200
        assert response.json()[0]["date"] == "2026-07-06"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_list_roster_empty_filter_result_returns_empty_list(self, client):
        db = MagicMock()
        db.query.return_value = _query(all_result=[])
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster?source=planner&date_from=2026-07-01&date_to=2026-07-31")

        assert response.status_code == 200
        assert response.json() == []

    def test_B_list_roster_default_source_excludes_auto_shifts(self, client, monkeypatch):
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))

        response = client.get("/api/roster?date=2026-07-06")

        assert response.status_code == 200
        assert response.json()[0]["id"] == shift.id


class TestEmployeeRosterFeedsHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_employee_shifts_returns_only_authenticated_users_shifts(self, client):
        employee = _employee(7, "Own", "Shift")
        shift = _shift(
            staff_id=7,
            shift_date=date(2026, 7, 6),
            start=time(8, 0),
            end=time(12, 0),
            staff=employee,
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift], count_result=1)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/shifts?date_from=2026-07-01&date_to=2026-07-31")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["staff_id"] == 7
        assert payload[0]["start_time"] == "08:00"

    def test_H_employee_shifts_week_filter_includes_overnight_end_date(self, client):
        employee = _employee(7, "Own", "Shift")
        shift = _shift(
            staff_id=7,
            shift_date=date(2026, 7, 12),
            start=time(22, 0),
            end=time(2, 0),
            end_date=date(2026, 7, 13),
            staff=employee,
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift], count_result=1)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/shifts?week_start=2026-07-13")

        assert response.status_code == 200
        assert response.json()[0]["end_date"] == "2026-07-13"

    def test_H_team_shifts_returns_stripped_teammate_shape_with_normalised_phone(self, client):
        teammate = _employee(8, "Team", "Mate")
        teammate.phone = "07911 123 456"
        shift = _shift(
            staff_id=8,
            shift_date=date(2026, 7, 6),
            start=time(14, 0),
            end=time(18, 0),
            staff=teammate,
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Own", "Shift")

        response = client.get("/api/employee/team-shifts?week_start=2026-07-06")

        assert response.status_code == 200
        payload = response.json()
        assert payload == [{
            "initials": "TM",
            "first_name": "Team",
            "last_name": "Mate",
            "phone": "+447911123456",
            "date": "2026-07-06",
            "end_date": "2026-07-06",
            "start_time": "14:00",
            "end_time": "18:00",
            "parent_shift_id": None,
            "locked": False,
            "independent_from_parent": False,
            "pool_parent_shift_id": None,
            "pool_child_shift_ids": [],
        }]
        assert "bookings" not in payload[0]
        assert "notes" not in payload[0]

    def test_H_team_shifts_date_range_filter_returns_teammates(self, client):
        teammate = _employee(8, "Range", "Mate")
        shift = _shift(
            staff_id=8,
            shift_date=date(2026, 7, 6),
            start=time(14, 0),
            end=time(18, 0),
            staff=teammate,
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Own", "Shift")

        response = client.get("/api/employee/team-shifts?date_from=2026-07-01&date_to=2026-07-31")

        assert response.status_code == 200
        assert response.json()[0]["initials"] == "RM"

    def test_H_claim_shift_assigns_unassigned_future_shift(self, client, monkeypatch):
        employee = _employee(7, "Claim", "User")
        shift = _shift(staff_id=None, shift_date=date(2099, 1, 1), start=time(9), end=time(11))
        db = MagicMock()
        claim_update = MagicMock()
        claim_update.filter.return_value.update.return_value = 1  # rowcount: won the race
        db.query.side_effect = [
            _query(first_result=shift),
            _query(first_result=None),
            claim_update,
        ]
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _shift_response_payload(s))
        monkeypatch.setattr("routers.roster._notify_founder_roster_event", lambda *a, **k: None)

        response = client.post("/api/employee/claim-shift/100")

        assert response.status_code == 200
        assert response.json()["success"] is True
        # v4: assignment happens via conditional UPDATE (race guard), with
        # provenance stamped alongside staff_id.
        claim_update.filter.return_value.update.assert_called_once_with(
            {"staff_id": 7, "assigned_source": "claim", "needs_cover_at": None},
            synchronize_session=False,
        )
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(shift)

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_available_shifts_returns_empty_for_non_driver_user(self, client):
        admin_without_driver_type = _employee(7, "Office", "User")
        admin_without_driver_type.driver_type = None
        db = MagicMock()
        db.query.return_value = _query(all_result=[_shift(staff_id=None)])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: admin_without_driver_type

        response = client.get("/api/employee/available-shifts")

        assert response.status_code == 200
        assert response.json() == []

    def test_U_release_shift_rejects_shift_owned_by_someone_else(self, client):
        employee = _employee(7, "Own", "Shift")
        shift = _shift(staff_id=8, shift_date=date(2099, 1, 1), start=time(9), end=time(10))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.post("/api/employee/release-shift/108")

        assert response.status_code == 403
        assert response.json()["detail"] == "This shift is not assigned to you"

    def test_U_claim_shift_returns_404_for_missing_shift(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Claim", "User")

        response = client.post("/api/employee/claim-shift/404")

        assert response.status_code == 404
        assert response.json()["detail"] == "Shift not found"

    def test_U_claim_shift_rejects_already_assigned_or_past_shift(self, client):
        employee = _employee(7, "Claim", "User")
        db = MagicMock()
        db.query.return_value = _query(first_result=_shift(staff_id=8, shift_date=date(2099, 1, 1)))
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        assigned = client.post("/api/employee/claim-shift/108")
        assert assigned.status_code == 400
        assert assigned.json()["detail"] == "Shift is already assigned to another employee"

        db.query.return_value = _query(first_result=_shift(staff_id=None, shift_date=date(2000, 1, 1)))
        past = client.post("/api/employee/claim-shift/100")
        assert past.status_code == 400
        assert past.json()["detail"] == "Cannot claim shifts in the past"

    def test_U_release_shift_returns_404_for_missing_shift(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Own", "Shift")

        response = client.post("/api/employee/release-shift/404")

        assert response.status_code == 404
        assert response.json()["detail"] == "Shift not found"

    # --- EDGE ----------------------------------------------------------------

    def test_E_available_shifts_for_jockey_serializes_claimable_shift(self, client):
        employee = _employee(7, "Jock", "User")
        employee.driver_type = "jockey"
        shift = _shift(
            staff_id=None,
            shift_date=date(2099, 1, 1),
            start=time(6),
            end=time(8),
            source="manual",
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/available-shifts")

        assert response.status_code == 200
        assert response.json()[0]["staff_id"] is None
        assert response.json()[0]["start_time"] == "06:00"

    def test_E_available_shifts_for_fleet_filters_to_fleet_intended(self, client):
        employee = _employee(7, "Fleet", "User")
        employee.driver_type = "fleet"
        shift = _shift(
            staff_id=None,
            shift_date=date(2099, 1, 1),
            start=time(6),
            end=time(8),
            source="manual",
        )
        shift.intended_driver_type = "fleet"
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/available-shifts")

        assert response.status_code == 200
        assert response.json()[0]["intended_driver_type"] == "fleet"

    def test_E_employee_weekly_hours_counts_overnight_shift_on_start_day(self, client):
        employee = _employee(7, "Own", "Hours")
        shift = _shift(
            staff_id=7,
            shift_date=date(2026, 7, 6),
            start=time(22, 0),
            end=time(2, 0),
            end_date=date(2026, 7, 7),
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/weekly-hours?week_start=2026-07-06")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_hours"] == 4.0
        assert payload["daily_hours"]["2026-07-06"] == 4.0
        assert payload["daily_hours"]["2026-07-07"] == 0.0

    def test_E_claim_shift_rejects_overlap_and_holiday_conflicts(self, client, monkeypatch):
        employee = _employee(7, "Claim", "User")
        shift = _shift(staff_id=None, shift_date=date(2099, 1, 1), start=time(9), end=time(11))
        overlap = _shift(staff_id=7, shift_date=date(2099, 1, 1), start=time(10), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: overlap)

        overlapping = client.post("/api/employee/claim-shift/100")
        assert overlapping.status_code == 409
        assert "10:00-12:00" in overlapping.json()["detail"]

        db.query.side_effect = [
            _query(first_result=shift),
            _query(first_result=SimpleNamespace(holiday_type=HolidayType.HOLIDAY)),
        ]
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)

        holiday = client.post("/api/employee/claim-shift/100")
        assert holiday.status_code == 409
        assert holiday.json()["detail"] == "You have Holiday booked on this date"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_employee_holidays_supports_date_to_only_filter_and_time_formatting(self, client):
        employee = _employee(7, "Own", "Holiday")
        holiday = SimpleNamespace(
            id=44,
            staff_id=7,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            start_time=time(9, 30),
            end_time=time(12, 45),
            holiday_type=HolidayType.UNAVAILABLE,
            notes="Appointment",
            created_at=datetime(2026, 6, 1, 9, 0),
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[holiday])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/holidays?date_to=2026-07-31")

        assert response.status_code == 200
        payload = response.json()[0]
        assert payload["staff_initials"] == "OH"
        assert payload["start_time"] == "09:30"
        assert payload["holiday_type"] == "unavailable"

    @pytest.mark.parametrize(
        "query",
        [
            "?date_from=2026-07-01&date_to=2026-07-31",
            "?date_from=2026-07-01",
        ],
    )
    def test_B_employee_holidays_supports_from_and_range_filters(self, client, query):
        employee = _employee(7, "Own", "Holiday")
        holiday = SimpleNamespace(
            id=45,
            staff_id=7,
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 10),
            start_time=None,
            end_time=None,
            holiday_type=HolidayType.OTHER,
            notes=None,
            created_at=None,
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[holiday])
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get(f"/api/employee/holidays{query}")

        assert response.status_code == 200
        assert response.json()[0]["holiday_type"] == "other"

    def test_B_release_shift_succeeds_at_more_than_48_hours_notice(self, client):
        employee = _employee(7, "Own", "Shift")
        shift = _shift(staff_id=7, shift_date=date(2099, 1, 1), start=time(9), end=time(10))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.post("/api/employee/release-shift/107")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert shift.staff_id is None
        db.commit.assert_called_once()

    def test_B_release_shift_rejects_less_than_72_hours_notice(self, client):
        employee = _employee(7, "Own", "Shift")
        shift = _shift(staff_id=7, shift_date=date.today() + timedelta(days=1), start=time(23), end=time(23, 30))
        db = MagicMock()
        db.query.return_value = _query(first_result=shift)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.post("/api/employee/release-shift/107")

        assert response.status_code == 400
        assert "less than 72 hours notice" in response.json()["detail"]


class TestEmployeeUnavailabilityHelpersHUEB:
    def test_H_parse_time_for_unavailability_accepts_hhmm(self):
        assert parse_time_for_unavailability("09:30") == time(9, 30)

    def test_H_add_employee_unavailability_creates_partial_day_record(self, client, monkeypatch):
        monkeypatch.setattr("routers.roster._notify_founder_roster_event", lambda *a, **k: None)
        employee = _employee(7, "Own", "Unavailable")
        added = []
        db = MagicMock()
        db.query.return_value = _query(all_result=[])
        db.add.side_effect = added.append

        def refresh(obj):
            obj.id = 77

        db.refresh.side_effect = refresh
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        future = (date.today() + timedelta(days=10)).strftime("%d/%m/%Y")
        response = client.post(
            "/api/employee/unavailability",
            params={
                "start_date": future,
                "end_date": future,
                "start_time": "09:30",
                "end_time": "12:30",
                "notes": "Appointment",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["unavailability"]["id"] == 77
        assert payload["unavailability"]["start_time"] == "09:30"
        assert added[0].staff_id == 7
        assert added[0].holiday_type == HolidayType.UNAVAILABLE
        assert added[0].created_by == employee.email

    @pytest.mark.parametrize("value", [None, "", "bad", "09"])
    def test_U_parse_time_for_unavailability_returns_none_for_invalid_values(self, value):
        assert parse_time_for_unavailability(value) is None

    @pytest.mark.parametrize(
        "params,detail",
        [
            ({"start_date": "2026-07-06", "end_date": "06/07/2026"}, "Invalid start_date format. Use DD/MM/YYYY"),
            ({"start_date": "06/07/2026", "end_date": "2026-07-06"}, "Invalid end_date format. Use DD/MM/YYYY"),
            ({"start_date": "07/07/2026", "end_date": "06/07/2026"}, "End date cannot be before start date"),
            (
                {"start_date": "06/07/2026", "end_date": "06/07/2026", "start_time": "12:00", "end_time": "09:00"},
                "End time must be after start time",
            ),
        ],
    )
    def test_U_add_employee_unavailability_rejects_invalid_dates_and_times(self, client, params, detail):
        db = MagicMock()
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Own", "Unavailable")

        response = client.post("/api/employee/unavailability", params=params)

        assert response.status_code == 400
        assert response.json()["detail"] == detail

    def test_E_unavailability_conflict_returns_first_shift_for_full_day(self):
        shift = _shift(staff_id=7, shift_date=date(2026, 7, 6))
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])

        assert check_shift_conflict_for_unavailability(
            db, 7, date(2026, 7, 6), date(2026, 7, 6), None, None
        ) is shift

    def test_E_add_employee_unavailability_rejects_existing_shift_conflict(self, client):
        db = MagicMock()
        db.query.return_value = _query(
            all_result=[_shift(staff_id=7, shift_date=date(2026, 7, 6), start=time(10), end=time(14))]
        )
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: _employee(7, "Own", "Unavailable")

        response = client.post(
            "/api/employee/unavailability",
            params={"start_date": "06/07/2026", "end_date": "06/07/2026"},
        )

        assert response.status_code == 409
        assert "Please release the shift first" in response.json()["detail"]

    def test_B_unavailability_conflict_detects_touching_and_overlapping_times(self):
        shift = _shift(staff_id=7, shift_date=date(2026, 7, 6), start=time(9), end=time(12))
        db = MagicMock()
        db.query.return_value = _query(all_result=[shift])

        assert check_shift_conflict_for_unavailability(
            db, 7, date(2026, 7, 6), date(2026, 7, 6), time(12), time(13)
        ) is None
        assert check_shift_conflict_for_unavailability(
            db, 7, date(2026, 7, 6), date(2026, 7, 6), time(11, 59), time(13)
        ) is shift

    def test_B_unavailability_conflict_returns_none_when_no_shifts_exist(self):
        db = MagicMock()
        db.query.return_value = _query(all_result=[])

        assert check_shift_conflict_for_unavailability(
            db, 7, date(2026, 7, 6), date(2026, 7, 6), time(9), time(10)
        ) is None


class TestPayrollAndAdminHolidaysHUEB:
    # --- HAPPY ---------------------------------------------------------------

    def test_H_admin_monthly_payroll_groups_active_and_historical_staff(self, client):
        active_staff = _employee(2, "Active", "Driver")
        historical_staff = _employee(9, "Historical", "Driver", active=False)
        shifts = [
            _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(13)),
            _shift(staff_id=9, shift_date=date(2026, 7, 7), start=time(22), end=time(1), end_date=date(2026, 7, 8)),
        ]
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=shifts),
            _query(all_result=[active_staff]),
            _query(first_result=historical_staff),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/payroll/monthly?year=2026&month=7")

        assert response.status_code == 200
        payload = response.json()
        assert payload["totals"]["total_shifts"] == 2
        assert payload["totals"]["total_hours"] == 7.0
        assert {row["staff_name"] for row in payload["staff"]} == {"Active Driver", "Historical Driver"}

    def test_H_employee_monthly_payroll_returns_authenticated_employee_summary(self, client):
        employee = _employee(7, "Own", "Payroll")
        shifts = [
            _shift(staff_id=7, shift_date=date(2026, 7, 6), start=time(9), end=time(12)),
        ]
        db = MagicMock()
        db.query.return_value = _query(all_result=shifts)
        _override_db(db)
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/payroll/monthly?year=2026&month=7")

        assert response.status_code == 200
        payload = response.json()
        assert payload["employee_name"] == "Own Payroll"
        assert payload["total_hours"] == 3.0
        assert payload["shifts_by_date"][0]["daily_hours"] == 3.0

    def test_H_admin_holiday_endpoints_serialize_holiday_rows(self, client):
        holiday = _holiday(id=20, start_time=time(9), end_time=time(11), holiday_type=HolidayType.UNAVAILABLE)
        db = MagicMock()
        db.query.return_value = _query(all_result=[holiday], first_result=holiday)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        listed = client.get("/api/holidays?date_from=2026-07-01&date_to=2026-07-31&staff_id=2")
        for_date = client.get("/api/holidays/for-date?date=2026-07-06")
        detail = client.get("/api/holidays/20")

        assert listed.status_code == 200
        assert listed.json()[0]["start_time"] == "09:00"
        assert for_date.status_code == 200
        assert detail.status_code == 200
        assert detail.json()["staff_initials"] == "HD"

    def test_H_create_holiday_success_adds_background_task(self, client):
        staff = _employee(2, "Holiday", "Owner")
        added = []
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=staff),
            _query(all_result=[]),
            _query(all_result=[]),
        ]
        db.add.side_effect = added.append

        def refresh(obj):
            obj.id = 88
            obj.staff = staff
            obj.created_at = datetime(2026, 6, 1, 9, 0)

        db.refresh.side_effect = refresh
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.post(
            "/api/holidays",
            params={
                "staff_id": 2,
                "start_date": "2026-07-06",
                "end_date": "2026-07-06",
                "holiday_type": "unavailable",
                "start_time": "09:00",
                "end_time": "11:00",
                "notes": "Training",
            },
        )

        assert response.status_code == 201
        assert response.json()["id"] == 88
        assert added[0].holiday_type == HolidayType.UNAVAILABLE

    def test_H_update_and_delete_holiday_success(self, client):
        holiday = _holiday(id=21, start_time=time(9), end_time=time(11))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=holiday),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(first_result=holiday),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        updated = client.put(
            "/api/holidays/21",
            params={
                "start_date": "2026-07-07",
                "end_date": "2026-07-07",
                "holiday_type": "personal",
                "notes": "changed",
                "clear_times": True,
            },
        )
        deleted = client.delete("/api/holidays/21")

        assert updated.status_code == 200
        assert updated.json()["holiday_type"] == "personal"
        assert holiday.start_time is None
        assert deleted.status_code == 200
        assert deleted.json()["success"] is True

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_admin_payroll_skips_shift_when_historical_staff_missing(self, client):
        shift = _shift(staff_id=99, shift_date=date(2026, 7, 6), start=time(9), end=time(13))
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[shift]),
            _query(all_result=[]),
            _query(first_result=None),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/payroll/monthly?year=2026&month=7")

        assert response.status_code == 200
        assert response.json()["totals"]["total_shifts"] == 0

    @pytest.mark.parametrize(
        "query,detail",
        [
            (
                "staff_id=404&start_date=2026-07-06&end_date=2026-07-06",
                "Staff member not found",
            ),
            (
                "staff_id=2&start_date=2026-07-07&end_date=2026-07-06",
                "End date must be on or after start date",
            ),
            (
                "staff_id=2&start_date=2026-07-06&end_date=2026-07-06&holiday_type=bad",
                "Invalid holiday type",
            ),
            (
                "staff_id=2&start_date=2026-07-06&end_date=2026-07-06&start_time=bad",
                "Invalid start_time format. Use HH:MM",
            ),
        ],
    )
    def test_U_create_holiday_rejects_invalid_inputs(self, client, query, detail):
        db = MagicMock()
        db.query.return_value = _query(first_result=_employee(2, "Holiday", "Owner"))
        if "staff_id=404" in query:
            db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.post(f"/api/holidays?{query}")

        assert response.status_code in (400, 404)
        assert detail in response.json()["detail"]

    def test_U_holiday_detail_update_delete_return_404_when_missing(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        detail = client.get("/api/holidays/404")
        updated = client.put("/api/holidays/404", params={"notes": "missing"})
        deleted = client.delete("/api/holidays/404")

        assert detail.status_code == 404
        assert updated.status_code == 404
        assert deleted.status_code == 404

    # --- EDGE ----------------------------------------------------------------

    def test_E_create_holiday_rejects_timed_overlap_and_shift_conflict(self, client):
        staff = _employee(2, "Holiday", "Owner")
        existing = _holiday(start_time=time(9), end_time=time(12))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=staff),
            _query(all_result=[existing]),
        ]
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        overlap = client.post(
            "/api/holidays",
            params={
                "staff_id": 2,
                "start_date": "2026-07-06",
                "end_date": "2026-07-06",
                "holiday_type": "unavailable",
                "start_time": "10:00",
                "end_time": "11:00",
            },
        )
        assert overlap.status_code == 409
        assert "09:00-12:00" in overlap.json()["detail"]

        db.query.side_effect = [
            _query(first_result=staff),
            _query(all_result=[]),
            _query(all_result=[_shift(staff_id=2, shift_date=date(2026, 7, 6))]),
        ]
        shift_conflict = client.post(
            "/api/holidays",
            params={"staff_id": 2, "start_date": "2026-07-06", "end_date": "2026-07-06"},
        )
        assert shift_conflict.status_code == 409
        assert "shift scheduled on 2026-07-06" in shift_conflict.json()["detail"]

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_update_holiday_rejects_invalid_time_and_overlap(self, client):
        holiday = _holiday(id=21, start_time=time(9), end_time=time(11))
        db = MagicMock()
        db.query.return_value = _query(first_result=holiday)
        _override_db(db)
        app.dependency_overrides[require_admin] = lambda: _admin()

        invalid_time = client.put("/api/holidays/21", params={"end_time": "bad"})
        assert invalid_time.status_code == 400

        existing = _holiday(id=22, start_time=time(10), end_time=time(12))
        db.query.side_effect = [
            _query(first_result=holiday),
            _query(all_result=[existing]),
        ]
        overlap = client.put("/api/holidays/21", params={"start_time": "10:30", "end_time": "11:30"})
        assert overlap.status_code == 409
        assert "10:00-12:00" in overlap.json()["detail"]


class TestRosterPlannerAdminHUEB:
    # --- HAPPY ---------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_H_require_qa_admin_accepts_allowlisted_admin(self):
        assert await require_qa_admin(_admin()) == _admin()

    def test_H_get_and_patch_roster_planner_settings(self, client):
        db = MagicMock()
        db.query.return_value = _query(
            all_result=[
                SimpleNamespace(key="gap_max_minutes", value_json="90"),
                SimpleNamespace(key="bad", value_json="{nope"),
            ]
        )
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        settings = client.get("/api/admin/qa/roster-planner/settings")

        assert settings.status_code == 200
        assert settings.json()["gap_max_minutes"] == 90

        db.query.side_effect = [
            _query(first_result=None),
            _query(all_result=[SimpleNamespace(key="max_hours_per_week", value_json="45")]),
        ]
        patched = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"max_hours_per_week": 45},
        )

        assert patched.status_code == 200
        assert patched.json()["max_hours_per_week"] == 45
        db.commit.assert_called()
        db.add.assert_called()

    def test_H_propose_roster_endpoint_runs_engine_and_records_shadow_run(self, client, monkeypatch):
        recorded = []

        def fake_propose_roster(**kwargs):
            now = kwargs["now"]
            return {
                "run_id": "run-1",
                "generated_at": now,
                "window_start": now.date(),
                "window_end": date(9999, 12, 31),
                "proposed_shifts": [],
                "warnings": [],
                "summary": {"new_shifts": 0},
                "jockeys": [],
                "max_hours_per_week": 40,
            }

        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[]),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()
        monkeypatch.setattr("routers.roster.propose_roster", fake_propose_roster)
        monkeypatch.setattr("routers.roster.record_run", lambda *a, **k: recorded.append((a, k)))

        response = client.post("/api/admin/qa/roster-planner/propose")

        assert response.status_code == 200
        assert response.json()["run_id"] == "run-1"
        assert response.json()["settings_snapshot"]["max_hours_per_week"] == 40
        assert len(recorded) == 1

    def test_H_list_and_get_planner_runs(self, client):
        row = SimpleNamespace(
            run_id="run-1",
            triggered_at=datetime(2026, 7, 1, 9, 0),
            trigger_event="manual",
            trigger_ref=None,
            window_start=date(2026, 7, 1),
            window_end=date(2026, 7, 31),
            duration_ms=123,
            error_text=None,
            proposal_json='{"summary":{"new_shifts":2},"proposed_shifts":[]}',
            diff_vs_current_json='{"changed":true}',
            warnings_json='[{"rule":"test"}]',
        )
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[row]),
            _query(first_result=row),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        runs = client.get("/api/admin/qa/roster-planner/runs?trigger_event=manual&limit=5")
        detail = client.get("/api/admin/qa/roster-planner/runs/run-1")

        assert runs.status_code == 200
        assert runs.json()[0]["summary"]["new_shifts"] == 2
        assert detail.status_code == 200
        assert detail.json()["diff_vs_current"]["changed"] is True
        assert detail.json()["warnings"][0]["rule"] == "test"

    def test_H_submit_and_list_planner_feedback(self, client):
        added = []
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=SimpleNamespace(run_id="run-1")),
            _query(
                all_result=[
                    SimpleNamespace(
                        id=44,
                        run_id="run-1",
                        shift_date=date(2026, 7, 6),
                        shift_start_time=time(9),
                        shift_end_time=time(11),
                        shift_staff_id=2,
                        proposed_shift_index=0,
                        severity="note",
                        comment="Looks fine",
                        override_json="{bad",
                        submitted_by=1,
                        submitted_at=datetime(2026, 7, 1, 10, 0),
                    )
                ]
            ),
        ]
        db.add.side_effect = added.append

        def refresh(row):
            row.id = 43
            row.submitted_at = datetime(2026, 7, 1, 9, 30)

        db.refresh.side_effect = refresh
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        submitted = client.post(
            "/api/admin/qa/roster-planner/runs/run-1/feedback",
            json={
                "shift_date": "2026-07-06",
                "shift_start_time": "09:00",
                "shift_end_time": "11:00",
                "shift_staff_id": 2,
                "proposed_shift_index": 0,
                "severity": "note",
                "comment": "Looks fine",
            },
        )
        listed = client.get(
            "/api/admin/qa/roster-planner/feedback?shift_date=2026-07-06&shift_staff_id=2&shift_start_time=09:00&run_id=run-1"
        )

        assert submitted.status_code == 201
        assert submitted.json()["id"] == 43
        assert added[0].run_id == "run-1"
        assert listed.status_code == 200
        assert listed.json()[0]["override"] is None

    def test_H_regenerate_and_delete_auto_shift_endpoints_call_auto_roster(self, client, monkeypatch):
        import auto_roster

        monkeypatch.setattr(
            auto_roster,
            "rebuild_auto_for_dates",
            lambda db, target_dates, settings: {
                "deleted": 1,
                "created": 2,
                "bookings_in_scope": 3,
            },
        )
        monkeypatch.setattr(auto_roster, "delete_all_auto_shifts", lambda db, date_from=None, date_to=None: 4)
        db = MagicMock()
        db.query.return_value = _query(all_result=[])
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        regenerated = client.post(
            "/api/admin/qa/roster-planner/regenerate-auto",
            json={"mode": "date_range", "date_from": "2026-07-01", "date_to": "2026-07-03"},
        )
        deleted = client.delete(
            "/api/admin/qa/roster-planner/auto-shifts?date_from=2026-07-01&date_to=2026-07-03"
        )

        assert regenerated.status_code == 200
        assert regenerated.json()["dates_covered"] == 3
        assert regenerated.json()["created"] == 2
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 4

    # --- UNHAPPY -------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_U_require_qa_admin_rejects_non_allowlisted_admin(self):
        user = _admin()
        user.id = 999
        with pytest.raises(HTTPException) as exc:
            await require_qa_admin(user)
        assert exc.value.status_code == 403

    def test_U_get_planner_run_and_feedback_return_404_for_missing_parent(self, client):
        db = MagicMock()
        db.query.return_value = _query(first_result=None)
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        detail = client.get("/api/admin/qa/roster-planner/runs/missing")
        feedback = client.post(
            "/api/admin/qa/roster-planner/runs/missing/feedback",
            json={
                "shift_date": "2026-07-06",
                "severity": "note",
                "comment": "Missing run",
            },
        )

        assert detail.status_code == 404
        assert feedback.status_code == 404

    def test_U_list_planner_feedback_rejects_bad_shift_start_time(self, client):
        db = MagicMock()
        db.query.return_value = _query(all_result=[])
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.get("/api/admin/qa/roster-planner/feedback?shift_start_time=bad")

        assert response.status_code == 422
        assert response.json()["detail"] == "shift_start_time must be HH:MM"

    @pytest.mark.parametrize(
        "payload,detail",
        [
            ({"mode": "date_range", "date_from": "2026-07-03", "date_to": "2026-07-01"}, "date_to must be >= date_from"),
            ({"mode": "individual_dates", "dates": []}, "individual_dates mode requires a non-empty `dates` list"),
        ],
    )
    def test_U_regenerate_auto_rejects_invalid_date_selection(self, client, payload, detail):
        db = MagicMock()
        db.query.return_value = _query(all_result=[])
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post("/api/admin/qa/roster-planner/regenerate-auto", json=payload)

        assert response.status_code == 422
        assert response.json()["detail"] == detail

    def test_U_delete_auto_shifts_rejects_inverted_date_range(self, client, monkeypatch):
        import auto_roster

        monkeypatch.setattr(auto_roster, "delete_all_auto_shifts", lambda *a, **k: 0)
        _override_db(MagicMock())
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.delete(
            "/api/admin/qa/roster-planner/auto-shifts?date_from=2026-07-03&date_to=2026-07-01"
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "date_to must be on or after date_from"

    # --- EDGE / BOUNDARY -----------------------------------------------------

    def test_E_get_planner_run_ignores_corrupt_json_payloads(self, client):
        row = SimpleNamespace(
            run_id="run-2",
            triggered_at=datetime(2026, 7, 1, 9, 0),
            trigger_event="manual",
            trigger_ref=None,
            window_start=date(2026, 7, 1),
            window_end=date(2026, 7, 31),
            duration_ms=None,
            error_text="bad",
            proposal_json="{bad",
            diff_vs_current_json="{bad",
            warnings_json="{bad",
        )
        db = MagicMock()
        db.query.return_value = _query(first_result=row)
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.get("/api/admin/qa/roster-planner/runs/run-2")

        assert response.status_code == 200
        payload = response.json()
        assert payload["proposal"] is None
        assert payload["warnings"] == []

    def test_E_get_planner_run_maps_committed_shift_ids_from_audit_rows(self, client):
        proposal = {
            "proposed_shifts": [
                {"date": "2026-07-06", "start_time": "09:00", "end_time": "11:00"},
                {"date": "2026-07-06", "start_time": "12:00", "end_time": "14:00"},
            ]
        }
        row = SimpleNamespace(
            run_id="run-3",
            triggered_at=datetime(2026, 7, 1, 9, 0),
            trigger_event="manual",
            trigger_ref=None,
            window_start=date(2026, 7, 1),
            window_end=date(2026, 7, 31),
            duration_ms=None,
            error_text=None,
            proposal_json=json.dumps(proposal),
            diff_vs_current_json=None,
            warnings_json=None,
        )
        staff = _employee(2, "Live", "Staff")
        live = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(11), staff=staff)
        live.id = 333
        audits = [
            SimpleNamespace(event_data="{bad"),
            SimpleNamespace(event_data=json.dumps({"proposal_to_shift_ids": {"bad": [1], "1": "nope", "0": [333, "x"]}})),
        ]
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=row),
            _query(all_result=audits),
            _query(all_result=[live]),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.get("/api/admin/qa/roster-planner/runs/run-3")

        assert response.status_code == 200
        payload = response.json()
        assert payload["committed_indexes"] == [0]
        assert payload["committed_shifts_by_index"]["0"][0]["shift_id"] == 333
        assert payload["committed_shifts_by_index"]["0"][0]["staff_initials"] == "LS"

    def test_B_get_planner_run_falls_back_to_window_matching_without_audit_mapping(self, client):
        proposal = {
            "proposed_shifts": [
                {"date": "2026-07-06", "start_time": "09:00", "end_time": "11:00"},
            ]
        }
        row = SimpleNamespace(
            run_id="run-4",
            triggered_at=datetime(2026, 7, 1, 9, 0),
            trigger_event="manual",
            trigger_ref=None,
            window_start=date(2026, 7, 1),
            window_end=date(2026, 7, 31),
            duration_ms=None,
            error_text=None,
            proposal_json=json.dumps(proposal),
            diff_vs_current_json=None,
            warnings_json=None,
        )
        live = _shift(staff_id=None, shift_date=date(2026, 7, 6), start=time(9), end=time(11))
        live.id = 444
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=row),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[live]),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.get("/api/admin/qa/roster-planner/runs/run-4")

        assert response.status_code == 200
        payload = response.json()
        assert payload["committed_indexes"] == [0]
        assert payload["committed_shifts_by_index"]["0"][0]["shift_id"] == 444


class TestRosterPlannerCommitHUEB:
    def _proposal(self, kind="new", staff_id=2, events=None):
        return {
            "proposed_shifts": [
                {
                    "kind": kind,
                    "date": "2026-07-06",
                    "end_date": "2026-07-06",
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "staff_id": staff_id,
                    "shift_type": "morning",
                    "reason": "engine output",
                    "events": events if events is not None else [{"booking_id": 501}],
                }
            ]
        }

    # --- HAPPY ---------------------------------------------------------------

    def test_H_commit_planner_run_creates_shift_links_and_audit(self, client):
        added = []
        run = SimpleNamespace(run_id="run-commit", proposal_json=json.dumps(self._proposal()))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=run),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(first_result=SimpleNamespace(id=2, driver_type="fleet")),
            _query(first_result=None),
        ]
        db.add.side_effect = added.append

        def flush():
            if added:
                added[-1].id = 900

        db.flush.side_effect = flush
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-commit", "proposal_indexes": [0]},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["shifts_created"] == 1
        assert payload["shift_ids"] == [900]
        assert any(getattr(obj, "booking_id", None) == 501 for obj in added)
        assert any(getattr(obj, "event", None) == AuditLogEvent.PLANNER_RUN_COMMITTED for obj in added)

    def test_H_commit_planner_run_honours_delete_and_duplicate_overrides(self, client):
        added = []
        proposal = self._proposal(events=[])
        proposal["proposed_shifts"].append({
            **self._proposal(events=[])["proposed_shifts"][0],
            "staff_id": 2,
            "reason": "duplicate me",
        })
        run = SimpleNamespace(run_id="run-override", proposal_json=json.dumps(proposal))
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=run),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(first_result=SimpleNamespace(id=2, driver_type="jockey")),
            _query(all_result=[]),
            _query(first_result=SimpleNamespace(id=3, driver_type="fleet")),
        ]
        db.add.side_effect = added.append

        ids = iter([901, 902, 903, 904])

        def flush():
            if added:
                added[-1].id = next(ids)

        db.flush.side_effect = flush
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-override",
                "proposal_indexes": [0, 1],
                "overrides": {
                    "0": {"action": "delete"},
                    "1": {
                        "action": "duplicate",
                        "target_staff_ids": [2, 3, 3],
                        "add_unassigned_jockey": True,
                        "add_unassigned_fleet": True,
                    },
                },
            },
        )

        assert response.status_code == 200
        assert response.json()["shifts_created"] == 4
        created_shifts = [obj for obj in added if isinstance(obj, RosterShift)]
        assert [s.staff_id for s in created_shifts] == [2, 3, None, None]
        assert created_shifts[-1].intended_driver_type == "fleet"

    def test_H_undo_planner_run_deletes_scheduled_planner_shifts_and_links(self, client):
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(11))
        shift.id = 700
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[shift]),
            _query(),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.delete("/api/admin/qa/roster-planner/runs/run-commit")

        assert response.status_code == 200
        assert response.json()["shifts_deleted"] == 1
        db.delete.assert_called_once_with(shift)
        db.commit.assert_called_once()

    def test_H_shifts_overlap_for_staff_detects_same_day_and_cross_day_conflicts(self):
        same_day = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(10), end=time(12))
        cross_day = _shift(
            staff_id=2,
            shift_date=date(2026, 7, 7),
            start=time(0, 30),
            end=time(3),
            end_date=date(2026, 7, 7),
        )
        db = MagicMock()
        db.query.return_value = _query(all_result=[same_day])
        assert _shifts_overlap_for_staff(
            db,
            staff_id=2,
            shift_date=date(2026, 7, 6),
            end_date=None,
            start_time=time(11),
            end_time=time(13),
        ) is same_day

        db.query.return_value = _query(all_result=[cross_day])
        assert _shifts_overlap_for_staff(
            db,
            staff_id=2,
            shift_date=date(2026, 7, 6),
            end_date=date(2026, 7, 7),
            start_time=time(22),
            end_time=time(1),
        ) is cross_day

    # --- UNHAPPY -------------------------------------------------------------

    @pytest.mark.parametrize(
        "run,body,detail,status",
        [
            (None, {"run_id": "missing", "proposal_indexes": [0]}, "Run missing not found", 404),
            (SimpleNamespace(run_id="empty", proposal_json=None), {"run_id": "empty", "proposal_indexes": [0]}, "Run has no proposal payload", 400),
            (SimpleNamespace(run_id="bad", proposal_json="{bad"), {"run_id": "bad", "proposal_indexes": [0]}, "Run proposal_json corrupt", 500),
            (
                SimpleNamespace(run_id="dup", proposal_json=json.dumps({"proposed_shifts": []})),
                {"run_id": "dup", "proposal_indexes": [0, 0]},
                "Duplicate proposal_index 0",
                400,
            ),
            (
                SimpleNamespace(run_id="range", proposal_json=json.dumps({"proposed_shifts": []})),
                {"run_id": "range", "proposal_indexes": [1]},
                "proposal_index 1 out of range",
                400,
            ),
            (
                SimpleNamespace(run_id="kind", proposal_json=json.dumps({"proposed_shifts": [{"kind": "extend"}]})),
                {"run_id": "kind", "proposal_indexes": [0]},
                "Phase 3 commits only kind='new'",
                400,
            ),
        ],
    )
    def test_U_commit_planner_run_rejects_invalid_run_or_selection(self, client, run, body, detail, status):
        db = MagicMock()
        db.query.return_value = _query(first_result=run)
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post("/api/admin/qa/roster-planner/commit", json=body)

        assert response.status_code == status
        assert detail in response.json()["detail"]

    def test_U_commit_planner_run_rejects_unsupported_and_incomplete_overrides(self, client):
        run = SimpleNamespace(run_id="run-commit", proposal_json=json.dumps(self._proposal()))
        db = MagicMock()
        db.query.return_value = _query(first_result=run)
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        merge = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-commit",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "merge"}},
            },
        )
        assert merge.status_code == 400
        assert "not yet supported" in merge.json()["detail"]

        db.query.side_effect = [
            _query(first_result=run),
            _query(all_result=[]),
            _query(all_result=[]),
        ]
        duplicate = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-commit",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "duplicate"}},
            },
        )
        assert duplicate.status_code == 400
        assert "requires target_staff_ids" in duplicate.json()["detail"]

    def test_U_commit_planner_run_rejects_already_committed_live_shift(self, client):
        run = SimpleNamespace(run_id="run-commit", proposal_json=json.dumps(self._proposal()))
        audit = SimpleNamespace(event_data=json.dumps({"proposal_to_shift_ids": {"0": [333]}}))
        live = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(11))
        live.id = 333
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=run),
            _query(all_result=[audit]),
            _query(all_result=[live]),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-commit", "proposal_indexes": [0]},
        )

        assert response.status_code == 409
        assert "already committed" in response.json()["detail"]

    def test_U_commit_planner_run_rolls_back_on_overlap_conflict(self, client):
        run = SimpleNamespace(run_id="run-commit", proposal_json=json.dumps(self._proposal()))
        conflict = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(10), end=time(12))
        conflict.id = 444
        db = MagicMock()
        db.query.side_effect = [
            _query(first_result=run),
            _query(all_result=[]),
            _query(all_result=[]),
            _query(all_result=[conflict]),
        ]
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-commit", "proposal_indexes": [0]},
        )

        assert response.status_code == 409
        assert "overlaps existing shift" in response.json()["detail"]
        db.rollback.assert_called_once()

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_undo_planner_run_rolls_back_on_delete_failure(self, client):
        shift = _shift(staff_id=2, shift_date=date(2026, 7, 6), start=time(9), end=time(11))
        db = MagicMock()
        db.query.side_effect = [
            _query(all_result=[shift]),
            _query(),
        ]
        db.delete.side_effect = RuntimeError("delete failed")
        _override_db(db)
        app.dependency_overrides[require_qa_admin] = lambda: _admin()

        response = client.delete("/api/admin/qa/roster-planner/runs/run-commit")

        assert response.status_code == 500
        assert "Undo failed" in response.json()["detail"]
        db.rollback.assert_called_once()


class TestHoursEndpointsHUEB:
    def _hours_db(self, shifts, user=None):
        user = user or _employee(2, "Lee", "Naylor")
        db = MagicMock()

        def query_for(model):
            if model is RosterShift:
                return _query(all_result=shifts)
            if model is User:
                return _query(first_result=user)
            return _query()

        db.query.side_effect = query_for
        return db

    # --- HAPPY ---------------------------------------------------------------

    def test_H_weekly_hours_groups_staff_and_unassigned_auto_shifts(self, client):
        week_start = date(2026, 6, 1)
        shifts = [
            _shift(staff_id=2, shift_date=week_start, start=time(9), end=time(17)),
            _shift(staff_id=None, shift_date=week_start + timedelta(days=1), start=time(22), end=time(2), end_date=week_start + timedelta(days=2), source="auto"),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/weekly-hours?week_start=2026-06-01&source=auto")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_hours"] == 12.0
        assert payload["shift_count"] == 2
        assert {row["employee_name"] for row in payload["employees"]} == {"Lee Naylor", "Unassigned"}

    def test_H_weekly_hours_source_all_with_staff_filter(self, client):
        week_start = date(2026, 6, 1)
        shifts = [
            _shift(staff_id=2, shift_date=week_start, start=time(9), end=time(12)),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/weekly-hours?week_start=2026-06-01&source=all&staff_id=2")

        assert response.status_code == 200
        assert response.json()["total_hours"] == 3.0

    def test_H_weekly_hours_manual_source_uses_assigned_manual_filter(self, client):
        week_start = date(2026, 6, 1)
        shifts = [
            _shift(staff_id=2, shift_date=week_start, start=time(13), end=time(17), source="manual"),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/weekly-hours?week_start=2026-06-01&source=manual")

        assert response.status_code == 200
        assert response.json()["total_hours"] == 4.0

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_weekly_hours_with_no_shifts_returns_empty_summary(self, client):
        _override_db(self._hours_db([]))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/weekly-hours?week_start=2026-06-01")

        assert response.status_code == 200
        assert response.json()["total_hours"] == 0
        assert response.json()["employees"] == []

    # --- EDGE ----------------------------------------------------------------

    def test_E_monthly_hours_builds_partial_week_breakdown_and_totals(self, client):
        shifts = [
            _shift(staff_id=2, shift_date=date(2026, 6, 1), start=time(8), end=time(12)),
            _shift(staff_id=2, shift_date=date(2026, 6, 30), start=time(23), end=time(1), end_date=date(2026, 7, 1)),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/monthly-hours?year=2026&month=6&source=all")

        assert response.status_code == 200
        payload = response.json()
        assert payload["month_name"] == "June"
        assert payload["total_hours"] == 6.0
        assert payload["shift_count"] == 2
        assert payload["employees"][0]["employee_name"] == "Lee Naylor"
        assert payload["weeks"][0]["week_label"] == "1-7 Jun"

    def test_E_monthly_hours_auto_source_buckets_unassigned_shifts(self, client):
        shifts = [
            _shift(staff_id=None, shift_date=date(2026, 6, 15), start=time(10), end=time(12), source="auto"),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/monthly-hours?year=2026&month=6&source=auto")

        assert response.status_code == 200
        payload = response.json()
        assert payload["employees"][0]["employee_name"] == "Unassigned"
        assert payload["total_hours"] == 2.0

    def test_E_monthly_hours_manual_source_with_staff_filter(self, client):
        shifts = [
            _shift(staff_id=2, shift_date=date(2026, 6, 16), start=time(10), end=time(15), source="manual"),
        ]
        _override_db(self._hours_db(shifts))
        app.dependency_overrides[require_admin] = lambda: _admin()

        response = client.get("/api/roster/monthly-hours?year=2026&month=6&source=manual&staff_id=2")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_hours"] == 5.0
        assert payload["employees"][0]["employee_name"] == "Lee Naylor"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_employee_monthly_hours_only_reports_authenticated_employee(self, client):
        employee = _employee(7, "Own", "Hours")
        shifts = [
            _shift(staff_id=7, shift_date=date(2026, 2, 1), start=time(10), end=time(11)),
            _shift(staff_id=7, shift_date=date(2026, 2, 28), start=time(23), end=time(0), end_date=date(2026, 3, 1)),
        ]
        _override_db(self._hours_db(shifts, user=employee))
        app.dependency_overrides[get_current_user] = lambda: employee

        response = client.get("/api/employee/monthly-hours?year=2026&month=2")

        assert response.status_code == 200
        payload = response.json()
        assert payload["employee_id"] == 7
        assert payload["month_name"] == "February"
        assert payload["total_hours"] == 2.0
        assert payload["weeks"][0]["week_label"] == "1 Feb"
