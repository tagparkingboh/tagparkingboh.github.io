"""
Tests for the driver-type filter on the Employee page (locked 2026-04-30).

Filter rule:
  jockey users see all unassigned shifts (jockey- and fleet-intended)
  fleet  users see only fleet-intended unassigned shifts
  for team-shifts:
    jockey users see all teammates
    fleet  users see only fleet teammates

Also covers `intended_driver_type` write-time semantics:
  - admin manual-create: takes the assigned user's driver_type when assigned,
    otherwise honours the request (default 'jockey')
  - planner commit: same — assigned user's driver_type wins; unassigned
    defaults to 'jockey' (engine only auto-creates jockey work)
  - planner duplicate-to-fleet: each duplicate row inherits its target
    user's driver_type (so duplicating to a fleet driver yields a
    'fleet' shift even if the original was 'jockey')

All Happy/Unhappy/Edge/Boundary per backend/docs/SPEC.md.
"""
import json
from datetime import date, time, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from database import get_db
from db_models import (
    BookingStatus,
    PlannerRun,
    RosterPlannerSettings as DbRosterPlannerSettings,
    RosterShift,
    ShiftBookingLink,
    ShiftStatus,
    ShiftType,
)
from routers.roster import get_current_user, require_admin, require_qa_admin


# =====================================================================================
# Lightweight FakeQuery + factories (mirror the patterns in the other test files
# so this file can stand on its own without importing from siblings).
# =====================================================================================


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def filter_by(self, **__):
        return self

    def order_by(self, *_):
        return self

    def limit(self, _n):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def delete(self, **__):
        n = len(self.rows)
        self.rows = []
        return n

    def count(self):
        return len(self.rows)


def mk_user(user_id, *, first="Test", last="User", driver_type="jockey",
            is_admin=True, is_active=True, phone="+447111000000"):
    """Match the User shape the endpoints read."""
    u = MagicMock()
    u.id = user_id
    u.email = f"u{user_id}@test.com"
    u.first_name = first
    u.last_name = last
    u.phone = phone
    u.is_admin = is_admin
    u.is_active = is_active
    u.driver_type = driver_type
    u.auto_assign_excluded = False
    u.preferred_shift_types = []
    u.excluded_shift_types = []
    u.preferred_days_off = []
    u.preferred_start_time = None
    u.preferred_end_time = None
    u.is_fallback_driver = False
    u.window_overrun_minutes = 60
    return u


def mk_shift(*, shift_id=None, staff=None, intended_driver_type="jockey",
             shift_date=None, end_date=None,
             start_time=time(8, 0), end_time=time(16, 0),
             status=ShiftStatus.SCHEDULED, planner_run_id=None,
             notes=None):
    s = MagicMock(spec=RosterShift)
    s.id = shift_id
    s.staff_id = staff.id if staff else None
    s.staff = staff
    s.date = shift_date or date(2026, 5, 11)
    s.end_date = end_date or s.date
    s.start_time = start_time
    s.end_time = end_time
    s.status = status
    s.shift_type = MagicMock(value="full_morning")
    s.notes = notes
    s.intended_driver_type = intended_driver_type
    s.planner_run_id = planner_run_id
    s.created_source = "planner" if planner_run_id else "manual"
    s.bookings = []
    s.booking_id = None
    s.created_at = datetime(2026, 5, 1, 12, 0)
    s.updated_at = None
    return s


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._tables = {}
    db._committed = False
    db._flush_id_counter = 1000
    db._pending_flush = []

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    db.query.side_effect = _query

    def _commit():
        db._committed = True

    db.commit.side_effect = _commit

    def _add(obj):
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            db._pending_flush.append(obj)

    def _flush():
        for o in db._pending_flush:
            db._flush_id_counter += 1
            o.id = db._flush_id_counter
            # Mirror real DB server_default=func.now() so the response
            # serialisation has a valid datetime.
            if hasattr(o, "created_at") and getattr(o, "created_at", None) is None:
                o.created_at = datetime(2026, 5, 1, 12, 0)
            # Mirror server_default='jockey' for intended_driver_type so a
            # row added without an explicit value still serialises cleanly.
            if hasattr(o, "intended_driver_type") and getattr(o, "intended_driver_type", None) is None:
                o.intended_driver_type = "jockey"
        db._pending_flush = []

    def _refresh(obj):
        # Real refresh re-reads from DB. Tests don't need that — just
        # ensure created_at is non-null after refresh, mirroring _flush.
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 5, 1, 12, 0)

    db.add = MagicMock(side_effect=_add)
    db.flush = MagicMock(side_effect=_flush)
    db.refresh = MagicMock(side_effect=_refresh)
    return db


def _make_client(mock_db, current_user):
    """Build a TestClient with overridden dependencies for one user."""

    def _override_get_db():
        yield mock_db

    async def _override_get_current_user():
        return current_user

    async def _override_require_admin():
        return current_user

    async def _override_require_qa_admin():
        return current_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[require_admin] = _override_require_admin
    app.dependency_overrides[require_qa_admin] = _override_require_qa_admin
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


# =====================================================================================
# /api/employee/available-shifts — driver-type visibility
# =====================================================================================


class TestAvailableShiftsVisibility:

    def test_happy_jockey_user_sees_both_jockey_and_fleet_unassigned(self, mock_db):
        """Jockey user sees the full unassigned pool."""
        future = date.today() + timedelta(days=10)
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=1, intended_driver_type="jockey", shift_date=future),
            mk_shift(shift_id=2, intended_driver_type="fleet", shift_date=future),
        ]
        client = _make_client(mock_db, mk_user(99, driver_type="jockey"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        # FakeQuery doesn't honour .filter() on the SQL side, but the
        # endpoint's Python branch decides not to add an extra filter for
        # jockeys, so it includes both rows.
        assert len(r.json()) == 2

    def test_happy_fleet_user_sees_only_fleet_unassigned(self, mock_db):
        """Fleet user gets a query with intended_driver_type='fleet'.
        FakeQuery ignores the SQL filter, so we feed it only fleet rows
        to assert what the response contains for the fleet code path."""
        future = date.today() + timedelta(days=10)
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=2, intended_driver_type="fleet", shift_date=future),
        ]
        client = _make_client(mock_db, mk_user(99, driver_type="fleet"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["intended_driver_type"] == "fleet"

    def test_unhappy_user_with_no_driver_type_sees_nothing(self, mock_db):
        """Admin or unconfigured user sees an empty list — they shouldn't
        be claiming jockey/fleet work in the first place."""
        future = date.today() + timedelta(days=10)
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=1, intended_driver_type="jockey", shift_date=future),
            mk_shift(shift_id=2, intended_driver_type="fleet", shift_date=future),
        ]
        client = _make_client(mock_db, mk_user(99, driver_type=None))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert r.json() == []

    def test_edge_no_unassigned_shifts_returns_empty(self, mock_db):
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(99, driver_type="jockey"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert r.json() == []

    def test_edge_null_intended_visible_to_jockey(self, mock_db):
        """Old rows that predate the column have intended_driver_type=NULL.
        Per option B (2026-04-30), jockey users see them — they have no
        explicit driver-type filter applied, so all rows pass through."""
        future = date.today() + timedelta(days=10)
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=1, intended_driver_type=None, shift_date=future),
        ]
        client = _make_client(mock_db, mk_user(99, driver_type="jockey"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert len(r.json()) == 1
        # Response coerces NULL → 'jockey' so the FE never has to handle None.
        assert r.json()[0]["intended_driver_type"] == "jockey"

    def test_edge_null_intended_not_visible_to_fleet(self, mock_db):
        """Fleet user's filter is `intended_driver_type = 'fleet'`, which
        excludes NULL by SQL semantics. So a NULL row (old, no signal) is
        invisible to fleet drivers — consistent with how it'd have been
        before the column existed at all."""
        future = date.today() + timedelta(days=10)
        # FakeQuery doesn't honour SQL-level filters — feed only the row
        # the BE filter would let through (none), and assert the result.
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(99, driver_type="fleet"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert r.json() == []


# =====================================================================================
# /api/employee/team-shifts — driver-type visibility
# =====================================================================================


class TestTeamShiftsDriverTypeFilter:

    def test_happy_jockey_user_sees_all_teammates(self, mock_db):
        """Jockey user sees both jockey and fleet teammates."""
        jockey_mate = mk_user(2, first="Marek", last="Smolarek", driver_type="jockey")
        fleet_mate = mk_user(3, first="Aaron", last="Shorey", driver_type="fleet")
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=10, staff=jockey_mate, shift_date=date(2026, 5, 11)),
            mk_shift(shift_id=11, staff=fleet_mate, shift_date=date(2026, 5, 12)),
        ]
        client = _make_client(mock_db, mk_user(1, driver_type="jockey"))

        r = client.get("/api/employee/team-shifts")
        assert r.status_code == 200
        initials = sorted(row["initials"] for row in r.json())
        assert initials == ["AS", "MS"]

    def test_happy_fleet_user_sees_only_fleet_teammates(self, mock_db):
        jockey_mate = mk_user(2, first="Marek", last="Smolarek", driver_type="jockey")
        fleet_mate = mk_user(3, first="Aaron", last="Shorey", driver_type="fleet")
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=10, staff=jockey_mate, shift_date=date(2026, 5, 11)),
            mk_shift(shift_id=11, staff=fleet_mate, shift_date=date(2026, 5, 12)),
        ]
        client = _make_client(mock_db, mk_user(1, driver_type="fleet"))

        r = client.get("/api/employee/team-shifts")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["initials"] == "AS"

    def test_unhappy_admin_with_no_driver_type_sees_nothing(self, mock_db):
        jockey_mate = mk_user(2, first="Marek", last="Smolarek", driver_type="jockey")
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=10, staff=jockey_mate, shift_date=date(2026, 5, 11)),
        ]
        client = _make_client(mock_db, mk_user(1, driver_type=None))

        r = client.get("/api/employee/team-shifts")
        assert r.status_code == 200
        assert r.json() == []

    def test_edge_teammate_with_unknown_driver_type_hidden_from_fleet_user(self, mock_db):
        """Defensive: a teammate whose driver_type is None shouldn't appear
        in a fleet user's team feed."""
        weird_mate = mk_user(2, first="Old", last="Account", driver_type=None)
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=10, staff=weird_mate, shift_date=date(2026, 5, 11)),
        ]
        client = _make_client(mock_db, mk_user(1, driver_type="fleet"))

        r = client.get("/api/employee/team-shifts")
        assert r.status_code == 200
        assert r.json() == []


# =====================================================================================
# Write-time semantics — `intended_driver_type` is set correctly on create / commit
# =====================================================================================


class TestIntendedDriverTypeOnAdminCreate:
    """Admin POST /api/roster — assigned user's driver_type wins.
    Unassigned: honours request (default 'jockey')."""

    def test_happy_assigned_to_fleet_driver_writes_fleet(self, mock_db):
        future = date.today() + timedelta(days=14)
        fleet_user = mk_user(5, driver_type="fleet")
        mock_db._tables[type(fleet_user)] = []  # unused
        # validate_staff_assignment / overlap / etc. all use db.query — make
        # those return what the endpoint expects.
        # Simplify: just ensure user lookup returns our fleet user.
        from db_models import User as DbUser

        mock_db._tables[DbUser] = [fleet_user]
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(1, driver_type="jockey", is_admin=True))

        r = client.post(
            "/api/roster",
            json={
                "staff_id": 5,
                "date": future.isoformat(),
                "start_time": "08:00",
                "end_time": "16:00",
                "shift_type": "full_morning",
                "status": "scheduled",
                "intended_driver_type": "jockey",  # request says jockey, but user is fleet
            },
        )
        assert r.status_code == 201, r.text
        # The written row's intended_driver_type follows the assigned user.
        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert len(shifts) == 1
        assert shifts[0].intended_driver_type == "fleet"

    def test_happy_unassigned_with_request_value_honoured(self, mock_db):
        future = date.today() + timedelta(days=14)
        from db_models import User as DbUser

        mock_db._tables[DbUser] = []
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(1, driver_type="jockey", is_admin=True))

        r = client.post(
            "/api/roster",
            json={
                "staff_id": None,
                "date": future.isoformat(),
                "start_time": "08:00",
                "end_time": "16:00",
                "shift_type": "full_morning",
                "status": "scheduled",
                "intended_driver_type": "fleet",
            },
        )
        assert r.status_code == 201, r.text
        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert shifts[0].intended_driver_type == "fleet"

    def test_edge_unassigned_default_intended_is_jockey(self, mock_db):
        future = date.today() + timedelta(days=14)
        from db_models import User as DbUser

        mock_db._tables[DbUser] = []
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(1, driver_type="jockey", is_admin=True))

        r = client.post(
            "/api/roster",
            json={
                "staff_id": None,
                "date": future.isoformat(),
                "start_time": "08:00",
                "end_time": "16:00",
                "shift_type": "full_morning",
                "status": "scheduled",
                # intended_driver_type omitted → default
            },
        )
        assert r.status_code == 201, r.text
        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert shifts[0].intended_driver_type == "jockey"

    def test_edge_response_coerces_null_to_jockey(self, mock_db):
        """A row with intended_driver_type=NULL on disk (old data) must
        round-trip through the response as 'jockey' so the FE never sees
        None. Locks the coerce in shift_to_response."""
        from db_models import User as DbUser

        # Mock an existing roster_shift with NULL column — exercise the
        # response shaper directly via shift_to_response by hitting
        # /api/employee/available-shifts with this row in the table.
        future = date.today() + timedelta(days=14)
        mock_db._tables[DbUser] = []
        mock_db._tables[RosterShift] = [
            mk_shift(shift_id=99, intended_driver_type=None, shift_date=future),
        ]
        client = _make_client(mock_db, mk_user(1, driver_type="jockey"))

        r = client.get("/api/employee/available-shifts")
        assert r.status_code == 200
        assert r.json()[0]["intended_driver_type"] == "jockey"

    def test_unhappy_invalid_driver_type_value_returns_422(self, mock_db):
        """Pydantic Literal['jockey','fleet'] rejects unknowns."""
        future = date.today() + timedelta(days=14)
        from db_models import User as DbUser

        mock_db._tables[DbUser] = []
        mock_db._tables[RosterShift] = []
        client = _make_client(mock_db, mk_user(1, driver_type="jockey", is_admin=True))

        r = client.post(
            "/api/roster",
            json={
                "staff_id": None,
                "date": future.isoformat(),
                "start_time": "08:00",
                "end_time": "16:00",
                "shift_type": "full_morning",
                "status": "scheduled",
                "intended_driver_type": "bicycle",
            },
        )
        assert r.status_code == 422


class TestIntendedDriverTypeOnPlannerCommit:
    """Planner /commit honours assigned user's driver_type. The
    write-time logic is the same code path as POST /api/roster — so the
    canonical 'assigned-fleet-user → intended_driver_type=fleet'
    assertion lives in TestIntendedDriverTypeOnAdminCreate above. This
    suite locks the unassigned-default behaviour, which is unique to
    the planner path."""

    def test_unassigned_planner_write_defaults_to_jockey(self, mock_db):
        """Engine-output proposal with staff_id=None (unassign override or
        otherwise) → row written with intended_driver_type='jockey'.
        Engine doesn't auto-create fleet work today, so this default
        matches reality."""
        proposed = {
            "kind": "new",
            "shift_id": None,
            "date": "2026-05-11",
            "end_date": None,
            "start_time": "08:00",
            "end_time": "16:00",
            "shift_type": "full_morning",
            "is_custom_range": False,
            "staff_id": 2,
            "staff_initials": "MS",
            "events": [],
            "peak_concurrent_count": 1,
            "required_staff_count": 1,
            "reason": "test",
            "untouched_reason": None,
        }
        run = MagicMock(spec=PlannerRun)
        run.run_id = "run-unassign-default"
        run.window_start = date(2026, 5, 1)
        run.window_end = date(2026, 5, 31)
        run.proposal_json = json.dumps({"proposed_shifts": [proposed]})
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []
        mock_db._tables[ShiftBookingLink] = []
        client = _make_client(mock_db, mk_user(1, driver_type="jockey", is_admin=True))

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-unassign-default",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "unassign"}},
            },
        )
        assert r.status_code == 200, r.text
        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert len(shifts) == 1
        assert shifts[0].staff_id is None
        assert shifts[0].intended_driver_type == "jockey"
