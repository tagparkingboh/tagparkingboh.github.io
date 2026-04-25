"""Mocked integration tests for the QA Roster Planner endpoints.

These tests exercise the real endpoint handlers in routers/roster.py via
TestClient(app) with a mocked database session. Unlike pure-function tests,
they count toward coverage (per SPEC.md § Testing Requirements).

Endpoints covered:
- POST   /api/admin/qa/roster-planner/propose
- GET    /api/admin/qa/roster-planner/settings
- PATCH  /api/admin/qa/roster-planner/settings

Auth matrix (SPEC.md § Endpoint auth):
- no token → 401
- admin not in QA_USER_IDS → 403
- QA admin (id in {1, 2}) → 200
"""
import json
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from database import get_db
from db_models import (
    BookingStatus,
    RosterPlannerSettings as DbRosterPlannerSettings,
    ShiftStatus,
    ShiftType,
)
from routers.roster import require_admin, require_qa_admin


# =====================================================================================
# Factories — lightweight stand-ins, engine reads attributes off these.
# =====================================================================================


def mk_user(user_id=1, is_admin=True, is_active=True):
    u = MagicMock()
    u.id = user_id
    u.email = f"user{user_id}@test.com"
    u.first_name = "Qa"
    u.last_name = "Admin"
    u.is_admin = is_admin
    u.is_active = is_active
    u.auto_assign_excluded = False
    u.preferred_shift_types = []
    return u


def mk_settings_row(key, value):
    row = MagicMock(spec=DbRosterPlannerSettings)
    row.key = key
    row.value_json = json.dumps(value)
    return row


def default_settings_rows():
    return [
        mk_settings_row("window_days", 28),
        mk_settings_row("gap_max_minutes", 120),
        mk_settings_row("buffer_minutes", 30),
        mk_settings_row(
            "staffing_thresholds",
            [{"max_peak": 3, "staff": 1}, {"max_peak": 999, "staff": 2}],
        ),
        mk_settings_row("max_hours_per_week", 40),
        mk_settings_row("min_rest_hours", 8),
        mk_settings_row("untouchable_hours", 24),
        mk_settings_row("preview_enabled", True),
        mk_settings_row("commit_enabled", False),
    ]


def mk_db_booking(
    booking_id=1,
    reference="TAG-00001",
    status=BookingStatus.CONFIRMED,
    drop_date=None,
    drop_time=time(9, 0),
    pick_date=None,
    pick_time=time(17, 0),
):
    drop_date = drop_date or (date.today() + timedelta(days=2))
    pick_date = pick_date or (date.today() + timedelta(days=5))
    b = SimpleNamespace(
        id=booking_id,
        reference=reference,
        status=status,
        dropoff_date=drop_date,
        dropoff_time=drop_time,
        pickup_date=pick_date,
        pickup_time=pick_time,
    )
    return b


# =====================================================================================
# Fixtures — DB query mocking + dependency overrides.
# =====================================================================================


class FakeQuery:
    """Tiny SQLAlchemy-query stand-in. Mocks must survive `.filter(...)` chains."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_, **__):
        return self

    def filter_by(self, **__):
        return self

    def order_by(self, *_):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


@pytest.fixture
def mock_db():
    """Dispatches DB queries to per-model canned result sets.

    Individual tests mutate `db._tables[ModelCls]` to feed different results.
    """
    db = MagicMock()
    db._tables = {}
    db._committed = False

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    db.query.side_effect = _query

    def _commit():
        db._committed = True

    db.commit.side_effect = _commit
    db.add = MagicMock()
    return db


@pytest.fixture
def qa_admin():
    return mk_user(user_id=1, is_admin=True)


@pytest.fixture
def client(mock_db, qa_admin):
    """Test client with QA-admin identity and mocked DB session."""

    def override_get_db():
        yield mock_db

    async def override_require_qa_admin():
        return qa_admin

    async def override_require_admin():
        return qa_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_qa_admin] = override_require_qa_admin
    app.dependency_overrides[require_admin] = override_require_admin

    # NB: do NOT use `with TestClient(app) as ...` — that would fire FastAPI's
    # lifespan events, which include init_db() + migration checks against the
    # real DB URL and add several seconds per test. Plain TestClient(app) just
    # wraps the ASGI app without running startup.
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# =====================================================================================
# GET /settings
# =====================================================================================


class TestGetSettings:
    def test_happy_returns_defaults(self, client, mock_db):
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()

        r = client.get("/api/admin/qa/roster-planner/settings")
        assert r.status_code == 200
        body = r.json()
        assert body["window_days"] == 28
        assert body["gap_max_minutes"] == 120
        assert body["max_hours_per_week"] == 40
        assert body["preview_enabled"] is True
        assert body["commit_enabled"] is False

    def test_happy_empty_settings_table_falls_back_to_locked_defaults(
        self, client, mock_db
    ):
        mock_db._tables[DbRosterPlannerSettings] = []

        r = client.get("/api/admin/qa/roster-planner/settings")
        assert r.status_code == 200
        body = r.json()
        assert body["window_days"] == 28
        assert body["min_rest_hours"] == 8

    def test_edge_custom_value_roundtrips(self, client, mock_db):
        rows = default_settings_rows()
        for row in rows:
            if row.key == "max_hours_per_week":
                row.value_json = json.dumps(45)
        mock_db._tables[DbRosterPlannerSettings] = rows

        r = client.get("/api/admin/qa/roster-planner/settings")
        assert r.status_code == 200
        assert r.json()["max_hours_per_week"] == 45


# =====================================================================================
# Auth — defence-in-depth (SPEC.md § Endpoint auth)
# =====================================================================================


class TestAuth:
    def test_no_token_returns_401(self, mock_db):
        """With no overrides, the real require_admin dependency rejects."""

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            c = TestClient(app)
            r = c.get("/api/admin/qa/roster-planner/settings")
            assert r.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_admin_not_in_qa_list_returns_403(self, mock_db):
        """Override require_admin with a valid admin whose id is NOT in {1, 2}."""
        non_qa_admin = mk_user(user_id=99, is_admin=True)

        async def override_require_admin():
            return non_qa_admin

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = override_require_admin
        try:
            c = TestClient(app)
            r = c.get("/api/admin/qa/roster-planner/settings")
            assert r.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_qa_user_id_2_accepted(self, mock_db):
        """id=2 is the second QA user per SPEC restrictToUserIds=[1, 2]."""
        qa_admin_2 = mk_user(user_id=2, is_admin=True)

        async def override_require_admin():
            return qa_admin_2

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = override_require_admin
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()
        try:
            c = TestClient(app)
            r = c.get("/api/admin/qa/roster-planner/settings")
            assert r.status_code == 200
        finally:
            app.dependency_overrides.clear()


# =====================================================================================
# POST /propose
# =====================================================================================


class TestProposeEndpoint:
    def _prime(self, mock_db, bookings=None, shifts=None, staff=None, holidays=None):
        from db_models import Booking as DbBooking, RosterShift, User, EmployeeHoliday

        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()
        mock_db._tables[DbBooking] = bookings or []
        mock_db._tables[RosterShift] = shifts or []
        mock_db._tables[User] = staff or []
        mock_db._tables[EmployeeHoliday] = holidays or []

    def test_happy_returns_proposal_shape(self, client, mock_db):
        staff = [mk_user(user_id=10, is_admin=False)]
        bookings = [mk_db_booking()]
        self._prime(mock_db, bookings=bookings, staff=staff)

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200
        body = r.json()
        assert "run_id" in body
        assert "generated_at" in body
        assert "window_start" in body
        assert "window_end" in body
        assert "proposed_shifts" in body
        assert "warnings" in body
        assert "summary" in body
        assert "settings_snapshot" in body
        assert body["settings_snapshot"]["window_days"] == 28

    def test_unhappy_empty_db_produces_empty_proposal(self, client, mock_db):
        self._prime(mock_db)

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200
        body = r.json()
        assert body["proposed_shifts"] == []
        assert body["warnings"] == []
        assert body["summary"]["new_shifts"] == 0

    def test_edge_propose_is_read_only_for_roster_shifts(self, client, mock_db):
        """The preview endpoint must not write to roster_shifts. It DOES
        write one PlannerRun audit row (shadow mode), but no RosterShift
        rows ever go through this code path."""
        from db_models import PlannerRun, RosterShift
        staff = [mk_user(user_id=10, is_admin=False)]
        bookings = [mk_db_booking()]
        self._prime(mock_db, bookings=bookings, staff=staff)

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200
        added = [c.args[0] for c in mock_db.add.call_args_list]
        # No RosterShift writes — the shadow-mode invariant.
        assert not any(isinstance(a, RosterShift) for a in added), (
            "shadow mode: /propose must not write any RosterShift rows"
        )
        mock_db.delete.assert_not_called()
        # Exactly one PlannerRun audit row — that's the only allowed write.
        runs = [a for a in added if isinstance(a, PlannerRun)]
        assert len(runs) == 1

    def test_edge_unmanned_warning_when_no_eligible_staff(self, client, mock_db):
        self._prime(mock_db, bookings=[mk_db_booking()], staff=[])

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["unmanned_events"] >= 1
        assert any(w["rule"] == "unmanned" for w in body["warnings"])

    def test_boundary_window_dates_returned(self, client, mock_db):
        self._prime(mock_db)

        r = client.post("/api/admin/qa/roster-planner/propose")
        body = r.json()
        ws = date.fromisoformat(body["window_start"])
        we = date.fromisoformat(body["window_end"])
        assert (we - ws).days == 28


# =====================================================================================
# Shadow-mode audit — every /propose call must persist a planner_runs row
# =====================================================================================


class TestPlannerRunsAudit:
    """`/propose` is the first trigger wired into the shadow-mode runner.
    Booking / holiday / settings triggers come in follow-up commits. Each
    call must leave one PlannerRun row tagged trigger_event='manual'."""

    def _prime_minimal(self, mock_db):
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()
        mock_db._tables[__import__('db_models').User] = [mk_user(user_id=10, is_admin=False)]

    def test_propose_writes_one_planner_run(self, client, mock_db):
        from db_models import PlannerRun
        self._prime_minimal(mock_db)

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200
        body = r.json()

        # mock_db.add gets called with the PlannerRun instance.
        added = [c.args[0] for c in mock_db.add.call_args_list]
        runs = [a for a in added if isinstance(a, PlannerRun)]
        assert len(runs) == 1, f"expected 1 planner_runs row, got {len(runs)}"
        row = runs[0]
        assert row.run_id == body["run_id"]
        assert row.trigger_event == "manual"
        assert row.trigger_ref is None
        # Window dates on the row match the response dates.
        assert row.window_start.isoformat() == body["window_start"]
        assert row.window_end.isoformat() == body["window_end"]
        # proposal_json round-trips back to the response.
        decoded = json.loads(row.proposal_json)
        assert decoded["run_id"] == body["run_id"]

    def test_audit_failure_does_not_break_propose(self, client, mock_db):
        """Force the runner's internal try/except to fire (commit raises).
        The /propose endpoint must still return 200 — the booking flow
        safety invariant — and the audit row is simply dropped."""
        self._prime_minimal(mock_db)

        def _explode():
            raise RuntimeError("simulated commit failure")

        mock_db.commit.side_effect = _explode

        r = client.post("/api/admin/qa/roster-planner/propose")
        assert r.status_code == 200


# =====================================================================================
# PATCH /settings — explicit-fields semantics (2026-04-06 regression guard)
# =====================================================================================


class TestPatchSettings:
    def test_happy_partial_payload_only_touches_one_key(self, client, mock_db):
        # Start with an empty settings table — handler takes the "add new row" branch
        # for the one key we PATCH. Every other key stays missing, so the response
        # falls back to the locked defaults (from `_PLANNER_DEFAULT_SETTINGS`).
        # That gives us a clean assertion: the PATCH must never silently rewrite
        # fields the admin didn't send (regression guard for 2026-04-06 bug).
        rows: list = []
        mock_db._tables[DbRosterPlannerSettings] = rows

        def _append(row):
            rows.append(row)

        mock_db.add.side_effect = _append

        r = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"max_hours_per_week": 45},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["max_hours_per_week"] == 45
        # Other fields remain at their locked defaults — nothing clobbered.
        assert body["min_rest_hours"] == 8
        assert body["buffer_minutes"] == 30
        # Exactly one row was added — the one key the admin sent.
        assert mock_db.add.call_count == 1
        assert mock_db._committed is True

    def test_unhappy_invalid_type_returns_422(self, client, mock_db):
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()

        r = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"max_hours_per_week": "not a number"},
        )
        assert r.status_code == 422

    def test_edge_empty_payload_is_noop(self, client, mock_db):
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()

        r = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={},
        )
        assert r.status_code == 200
        assert mock_db._committed is False
        mock_db.add.assert_not_called()

    def test_boundary_window_days_out_of_range_rejected(self, client, mock_db):
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()

        r = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"window_days": 0},  # schema says ge=1
        )
        assert r.status_code == 422

        r2 = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"window_days": 91},  # schema says le=90
        )
        assert r2.status_code == 422


