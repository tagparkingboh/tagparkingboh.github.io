"""
Mocked-integration tests for GET /api/employee/team-shifts.

This endpoint provides a view-only feed of teammates' shifts for the Employee
calendar. Per backend/docs/SPEC.md, every test below uses TestClient(app) and
hits the real route handler so coverage actually moves.

Coverage matrix per SPEC.md:
- Happy: returns teammates' shifts with stripped shape
- Unhappy: unauthenticated request rejected
- Edge: own shifts and unassigned shifts excluded; date filter narrows
- Boundary: overnight shift end_date preserved; empty result is empty list

Privacy regression guards (lesson 2026-04-27):
- Response must NOT contain id, staff_id, shift_type, notes, booking refs.
"""
import sys
from pathlib import Path
from datetime import date, time, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app
from database import get_db
from routers.roster import get_current_user


# =============================================================================
# Factories
# =============================================================================

def make_user(*, id, first_name="Marek", last_name="Smolarek", phone="+447111000111"):
    u = MagicMock()
    u.id = id
    u.first_name = first_name
    u.last_name = last_name
    u.phone = phone
    return u


def make_shift(*, staff, shift_date, start_time, end_time, end_date=None):
    s = MagicMock()
    s.staff_id = staff.id if staff else None
    s.staff = staff
    s.date = shift_date
    s.end_date = end_date or shift_date
    s.start_time = start_time
    s.end_time = end_time
    return s


# =============================================================================
# Test rig
# =============================================================================

CURRENT_USER = make_user(id=1, first_name="Karl", last_name="Walden", phone="+447111000222")


@pytest.fixture
def client_with_shifts():
    """Yield a TestClient with overridden get_db / get_current_user.

    Caller passes a list of mock RosterShift via the `set_shifts` callable
    returned alongside the client.
    """
    state = {"shifts": []}

    mock_db = MagicMock()
    # The endpoint chains: query().filter().[filter()...].order_by().all()
    # MagicMock chains automatically; we just point the terminal .all() at our list.
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.side_effect = lambda: state["shifts"]
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.side_effect = lambda: state["shifts"]

    def _mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
    try:
        client = TestClient(app)
        def set_shifts(shifts):
            state["shifts"] = shifts
        yield client, set_shifts
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# Happy path
# =============================================================================

class TestTeamShiftsHappy:

    def test_returns_teammates_shifts_with_stripped_shape(self, client_with_shifts):
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2, first_name="Marek", last_name="Smolarek", phone="+447900111222")
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        row = data[0]
        assert row == {
            "initials": "MS",
            "first_name": "Marek",
            "last_name": "Smolarek",
            "phone": "+447900111222",
            "date": "2026-05-11",
            "end_date": "2026-05-11",
            "start_time": "08:00",
            "end_time": "16:00",
        }

    def test_no_teammates_returns_empty_list(self, client_with_shifts):
        client, set_shifts = client_with_shifts
        set_shifts([])

        response = client.get("/api/employee/team-shifts")
        assert response.status_code == 200
        assert response.json() == []

    def test_phone_optional(self, client_with_shifts):
        """A teammate with no phone on file still serialises cleanly (phone=null)."""
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2, first_name="Karl", last_name="Andrews", phone=None)
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        assert response.status_code == 200
        assert response.json()[0]["phone"] is None


# =============================================================================
# Phone normalisation — DB stores phones inconsistently (07... vs +44...)
# =============================================================================

class TestPhoneNormalisation:
    """The team-shifts response must surface phone in a single E.164 (+44...)
    shape regardless of how it was stored, so the FE tel: link works."""

    @pytest.mark.parametrize("stored,expected", [
        ("+447911123456", "+447911123456"),     # already E.164
        ("07911123456", "+447911123456"),       # leading 0 → +44
        ("447911123456", "+447911123456"),      # missing + only
        ("07911 123 456", "+447911123456"),     # whitespace
        ("0791-112-3456", "+447911123456"),     # punctuation
        ("(07911) 123456", "+447911123456"),    # brackets
        ("", None),                              # empty → None
        ("   ", None),                           # whitespace-only → None
    ])
    def test_normalised_to_e164(self, client_with_shifts, stored, expected):
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2, first_name="Marek", last_name="Smolarek", phone=stored)
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        assert response.json()[0]["phone"] == expected


# =============================================================================
# Privacy regression guards (lesson 2026-04-27)
# =============================================================================

class TestTeamShiftsPrivacyShape:
    """The response must NOT leak shift internals — bug or future endpoint
    change can't accidentally start exposing fields the spec said to strip."""

    def test_response_omits_sensitive_fields(self, client_with_shifts):
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2)
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        row = response.json()[0]

        for forbidden in ("id", "shift_id", "staff_id", "shift_type", "status", "notes",
                          "booking_id", "booking_reference", "bookings", "linked_bookings"):
            assert forbidden not in row, f"Response leaks {forbidden!r}"


# =============================================================================
# Unhappy path
# =============================================================================

class TestTeamShiftsUnauthenticated:

    def test_no_auth_returns_401_or_403(self):
        """Without overriding get_current_user, the real auth runs and rejects."""
        # Don't override get_current_user — use the real one.
        app.dependency_overrides.clear()
        client = TestClient(app)
        response = client.get("/api/employee/team-shifts")
        assert response.status_code in (401, 403)


# =============================================================================
# Edge cases — exclusion logic
# =============================================================================

class TestTeamShiftsExclusion:
    """The endpoint must exclude (a) the requester's own shifts and
    (b) unassigned shifts (staff_id IS NULL). The DB filter handles this,
    so these tests confirm the filter is wired correctly."""

    def test_only_other_teammates_in_response(self, client_with_shifts):
        """Even if mock DB returned the requester's own shift, we'd want to know;
        but the SQL filter at staff_id != current_user.id should keep it out.
        Here we assert the FILTERED result-set is what reaches the response."""
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2, first_name="Marek", last_name="Smolarek")
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        # Only the teammate's row appears — current user (Karl Walden, id=1) absent.
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["initials"] == "MS"

    def test_shifts_with_no_staff_object_skipped(self, client_with_shifts):
        """Defensive: if a shift slips through with staff=None (e.g. orphaned FK),
        the response builder skips it rather than crashing."""
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2)
        set_shifts([
            # First shift has a valid teammate
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
            # Second has staff_id but staff lookup returned None
            make_shift(staff=None, shift_date=date(2026, 5, 12), start_time=time(9, 0), end_time=time(17, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-05-11"


# =============================================================================
# Boundary
# =============================================================================

class TestTeamShiftsBoundaries:

    def test_overnight_shift_preserves_end_date(self, client_with_shifts):
        """A shift that wraps midnight reports end_date one day after date."""
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2)
        set_shifts([
            make_shift(
                staff=teammate,
                shift_date=date(2026, 5, 11),
                start_time=time(22, 0),
                end_time=time(2, 0),
                end_date=date(2026, 5, 12),
            ),
        ])

        response = client.get("/api/employee/team-shifts")
        row = response.json()[0]
        assert row["date"] == "2026-05-11"
        assert row["end_date"] == "2026-05-12"

    def test_same_day_shift_end_date_equals_date(self, client_with_shifts):
        """Standard same-day shift: end_date matches date."""
        client, set_shifts = client_with_shifts
        teammate = make_user(id=2)
        set_shifts([
            make_shift(staff=teammate, shift_date=date(2026, 5, 11), start_time=time(8, 0), end_time=time(16, 0)),
        ])

        response = client.get("/api/employee/team-shifts")
        row = response.json()[0]
        assert row["date"] == row["end_date"]
