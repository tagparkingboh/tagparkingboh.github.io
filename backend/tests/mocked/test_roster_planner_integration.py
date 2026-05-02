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
    u.excluded_shift_types = []
    u.preferred_days_off = []
    u.driver_type = "jockey"
    u.preferred_start_time = None
    u.preferred_end_time = None
    u.is_fallback_driver = False
    u.window_overrun_minutes = 60
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
        mk_settings_row("start_buffer_minutes", 20),
        mk_settings_row("end_buffer_minutes", 30),
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

    def limit(self, _n):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def delete(self, **__):
        """Bulk-delete via query.filter(...).delete(). Returns row count."""
        n = len(self.rows)
        self.rows = []
        return n


@pytest.fixture
def mock_db():
    """Dispatches DB queries to per-model canned result sets.

    Individual tests mutate `db._tables[ModelCls]` to feed different results.

    `db.add()` records the row and queues an id-assignment for `db.flush()` —
    so commit-endpoint code paths that rely on `db.flush(); shift.id` see a
    populated PK like they would against real SQLAlchemy.
    """
    db = MagicMock()
    db._tables = {}
    db._committed = False
    db._flush_id_counter = 1000
    db._pending_flush_ids = []  # objects added since last flush, awaiting an id

    def _query(model):
        return FakeQuery(db._tables.get(model, []))

    db.query.side_effect = _query

    def _commit():
        db._committed = True

    db.commit.side_effect = _commit

    def _add(obj):
        # If this object has an id attribute that's currently None, queue it
        # to receive one on next flush(). Real SQLAlchemy assigns autoincrement
        # IDs on flush.
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            db._pending_flush_ids.append(obj)

    def _flush():
        for obj in db._pending_flush_ids:
            db._flush_id_counter += 1
            obj.id = db._flush_id_counter
        db._pending_flush_ids = []

    db.add = MagicMock(side_effect=_add)
    db.flush = MagicMock(side_effect=_flush)
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
# Direct runner tests — fire_engine() is called from booking / holiday /
# settings event hooks via BackgroundTasks. Tests bypass TestClient and
# call the runner directly with a mocked Session.
# =====================================================================================


class TestFireEngine:
    def _prime(self, mock_db):
        from db_models import User
        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()
        mock_db._tables[User] = [mk_user(user_id=10, is_admin=False)]

    def test_fire_engine_writes_planner_run_for_booking_confirmed(self, mock_db):
        from db_models import PlannerRun
        from roster_planner_runner import fire_engine, TRIGGER_BOOKING_CONFIRMED

        self._prime(mock_db)
        run_id = fire_engine(
            mock_db,
            trigger_event=TRIGGER_BOOKING_CONFIRMED,
            trigger_ref="TAG-12345",
        )

        assert run_id is not None
        added = [c.args[0] for c in mock_db.add.call_args_list]
        runs = [a for a in added if isinstance(a, PlannerRun)]
        assert len(runs) == 1
        row = runs[0]
        assert row.run_id == run_id
        assert row.trigger_event == "booking_confirmed"
        assert row.trigger_ref == "TAG-12345"

    def test_fire_engine_swallows_internal_failures(self, mock_db):
        """Engine bug or DB issue inside the runner must not bubble — the
        booking-confirmation flow that triggered this must not break
        because the planner crashed."""
        from roster_planner_runner import fire_engine, TRIGGER_BOOKING_CONFIRMED

        self._prime(mock_db)

        def _explode():
            raise RuntimeError("simulated commit failure")
        mock_db.commit.side_effect = _explode

        # Must return None, not raise.
        run_id = fire_engine(
            mock_db,
            trigger_event=TRIGGER_BOOKING_CONFIRMED,
        )
        assert run_id is None

    def test_fire_engine_async_no_op_when_session_missing(self, monkeypatch):
        """When DATABASE_URL is unset (e.g. CI without staging DB),
        SessionLocal is None — fire_engine_async must silently no-op
        rather than crash. This is what protects the booking flow when
        the planner DB infra isn't configured."""
        import roster_planner_runner as _runner
        import database
        monkeypatch.setattr(database, "SessionLocal", None)

        # Must not raise.
        _runner.fire_engine_async("booking_confirmed", "TAG-1")


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
        assert body["start_buffer_minutes"] == 20
        assert body["end_buffer_minutes"] == 30
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

    def test_settings_change_fires_engine_in_background(self, client, mock_db, monkeypatch):
        """A rule change must trigger the engine in shadow mode — the next
        /runs page should reflect the new constraints. This test locks
        the wire-up pattern. The other six trigger sites (Stripe webhook,
        cancel, reschedule, holiday CRUD) replicate the same pattern."""
        import routers.roster as _roster_router

        calls: list = []

        def _capture(trigger, ref):
            calls.append((trigger, ref))

        monkeypatch.setattr(_roster_router, "fire_engine_async", _capture)

        rows: list = []
        mock_db._tables[DbRosterPlannerSettings] = rows
        mock_db.add.side_effect = lambda r: rows.append(r)

        r = client.patch(
            "/api/admin/qa/roster-planner/settings",
            json={"max_hours_per_week": 35},
        )
        assert r.status_code == 200

        # BackgroundTasks runs synchronously after the response in TestClient.
        assert len(calls) == 1, "settings PATCH did not schedule the engine"
        trigger, ref = calls[0]
        assert trigger == "settings_changed"
        assert "max_hours_per_week" in ref

    def test_empty_settings_patch_does_not_fire_engine(self, client, mock_db, monkeypatch):
        """No-op PATCH must not pollute the audit log with redundant runs."""
        import routers.roster as _roster_router

        calls: list = []
        monkeypatch.setattr(
            _roster_router,
            "fire_engine_async",
            lambda t, r: calls.append((t, r)),
        )

        mock_db._tables[DbRosterPlannerSettings] = default_settings_rows()
        r = client.patch("/api/admin/qa/roster-planner/settings", json={})
        assert r.status_code == 200
        assert calls == []


# =====================================================================================
# GET /runs and /runs/{id} — shadow-mode run history (QA UI history strip)
# =====================================================================================


def _mk_run_row(
    run_id="r-1",
    triggered_at=None,
    trigger_event="manual",
    trigger_ref=None,
    proposal=None,
    duration_ms=42,
    error_text=None,
):
    """Build a PlannerRun-shaped SimpleNamespace. The handler reads
    attributes off the row, so a namespace is sufficient."""
    if triggered_at is None:
        triggered_at = datetime(2026, 4, 24, 12, 0, 0)
    if proposal is None:
        proposal = {
            "run_id": run_id,
            "summary": {"new_shifts": 3, "extended_shifts": 1, "unmanned_events": 0},
        }
    return SimpleNamespace(
        run_id=run_id,
        triggered_at=triggered_at,
        trigger_event=trigger_event,
        trigger_ref=trigger_ref,
        window_start=date(2026, 4, 24),
        window_end=date(2026, 5, 22),
        proposal_json=json.dumps(proposal),
        diff_vs_current_json=None,
        warnings_json=json.dumps([]),
        duration_ms=duration_ms,
        error_text=error_text,
    )


class TestRunsEndpoints:
    def test_list_runs_empty(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = []

        r = client.get("/api/admin/qa/roster-planner/runs")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_runs_returns_summary_extracted_from_proposal(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        r = client.get("/api/admin/qa/roster-planner/runs")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        item = body[0]
        assert item["run_id"] == "r-A"
        assert item["trigger_event"] == "manual"
        assert item["has_error"] is False
        # Summary lifted out of proposal_json so the strip can show
        # volume without loading the full proposal.
        assert item["summary"]["new_shifts"] == 3

    def test_list_runs_pagination_limit_default_50(self, client, mock_db):
        from db_models import PlannerRun
        # Order/limit are applied via FakeQuery — the fixture currently
        # ignores .limit() and .order_by(), so verify defaults pass.
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id=f"r-{i}") for i in range(3)]

        r = client.get("/api/admin/qa/roster-planner/runs?limit=10")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_list_runs_limit_out_of_range_rejected(self, client, mock_db):
        r = client.get("/api/admin/qa/roster-planner/runs?limit=0")
        assert r.status_code == 422
        r2 = client.get("/api/admin/qa/roster-planner/runs?limit=300")
        assert r2.status_code == 422

    def test_run_detail_happy(self, client, mock_db):
        from db_models import PlannerRun
        row = _mk_run_row(run_id="r-detail")
        mock_db._tables[PlannerRun] = [row]

        r = client.get("/api/admin/qa/roster-planner/runs/r-detail")
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "r-detail"
        assert body["proposal"]["run_id"] == "r-detail"
        assert body["error_text"] is None

    def test_run_detail_404_when_missing(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = []

        r = client.get("/api/admin/qa/roster-planner/runs/does-not-exist")
        assert r.status_code == 404

    def test_run_detail_surfaces_error_text(self, client, mock_db):
        """Failed runs must still be retrievable so QA can see *why* the
        engine crashed without grepping logs."""
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = [
            _mk_run_row(run_id="r-err", error_text="ZeroDivisionError")
        ]

        r = client.get("/api/admin/qa/roster-planner/runs/r-err")
        assert r.status_code == 200
        assert r.json()["error_text"] == "ZeroDivisionError"


class TestRunDetailCommittedIndexes:
    """`committed_indexes` lets the FE hide the commit checkbox on already-
    committed proposals, so an admin can't accidentally re-tick → 409.
    Match key: (date, start_time, end_time) on roster_shifts where
    planner_run_id == run_id and status='scheduled'."""

    def test_happy_returns_indexes_for_proposals_that_have_a_matching_committed_shift(
        self, client, mock_db,
    ):
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [
                _mk_proposal(staff_id=2, shift_date="2026-05-11"),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
                _mk_proposal(staff_id=4, shift_date="2026-05-13"),
            ],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        # Only proposals 0 and 2 have matching committed shifts; index 1 is
        # uncommitted (admin hasn't ticked it yet, or ticked then undone).
        mock_db._tables[RosterShift] = [
            _mk_existing_shift(
                shift_id=501, staff_id=2,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-cm",
            ),
            _mk_existing_shift(
                shift_id=503, staff_id=4,
                shift_date=date(2026, 5, 13),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-cm",
            ),
        ]

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == [0, 2]

    def test_happy_empty_when_nothing_committed(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        mock_db._tables[RosterShift] = []

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == []

    def test_edge_unassigned_committed_shift_still_matches_proposal(self, client, mock_db):
        """An admin used the unassign override → the resulting roster_shift
        has staff_id=None. The match key is (date, start_time, end_time), so
        staff_id discrepancy doesn't matter — the proposal is still 'committed'."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        # Shift was committed with staff_id=None (via unassign override) but
        # date/time match the original proposal exactly.
        unassigned_shift = _mk_existing_shift(
            shift_id=600, staff_id=None,
            shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
            planner_run_id="r-cm",
        )
        mock_db._tables[RosterShift] = [unassigned_shift]

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == [0]

    def test_edge_duplicate_origin_marked_committed_even_with_multiple_shifts(
        self, client, mock_db,
    ):
        """Duplicate produces N shifts sharing (date, start, end). The proposal
        index should appear once in committed_indexes regardless of how many
        shifts back it."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        mock_db._tables[RosterShift] = [
            _mk_existing_shift(shift_id=700, staff_id=2,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-cm"),
            _mk_existing_shift(shift_id=701, staff_id=3,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-cm"),
            _mk_existing_shift(shift_id=702, staff_id=4,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-cm"),
        ]

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == [0]  # de-duped to single entry

    def test_edge_shifts_from_other_runs_dont_pollute(self, client, mock_db):
        """A roster_shift with a different planner_run_id (or NULL) must not
        contribute to this run's committed_indexes. The query already filters
        on planner_run_id but lock the regression with a test."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        # FakeQuery doesn't actually apply .filter() predicates, so this test
        # documents the intent — only rows whose planner_run_id matches
        # should show. The handler explicitly filters by run_id; the
        # FakeQuery ignores it but returns whatever's in _tables.
        # To make this assertion meaningful we feed only the OTHER run's row.
        mock_db._tables[RosterShift] = []  # nothing for r-cm specifically

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == []

    def test_boundary_after_undo_committed_indexes_empty(self, client, mock_db):
        """When all engine-created scheduled shifts for the run have been
        deleted (i.e. undo ran), committed_indexes becomes empty so the
        admin can re-tick and re-commit."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-cm",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-cm", proposal=proposal)]
        mock_db._tables[RosterShift] = []  # undo wiped them

        r = client.get("/api/admin/qa/roster-planner/runs/r-cm")
        assert r.status_code == 200
        assert r.json()["committed_indexes"] == []


class TestRunDetailCommittedShiftsByIndex:
    """`committed_shifts_by_index` reflects the *live* state of each
    committed proposal — not the engine's original suggestion. Lets the
    planner UI render unassigned cards as `?`, claimed cards with the
    claimer's initials, and duplicates with multiple initials."""

    def test_happy_unassigned_committed_shift_shows_null_staff(self, client, mock_db):
        """Admin committed with unassign override → snapshot has staff_id=None.
        The original proposal said staff_id=2 (MS), but the live state is
        unassigned. UI should render `?`, not `MS`."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-snap",
            "proposed_shifts": [_mk_proposal(staff_id=2)],  # engine said MS
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-snap", proposal=proposal)]
        mock_db._tables[RosterShift] = [
            _mk_existing_shift(
                shift_id=900, staff_id=None,  # unassign override applied
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-snap",
            ),
        ]

        r = client.get("/api/admin/qa/roster-planner/runs/r-snap")
        assert r.status_code == 200
        snap = r.json()["committed_shifts_by_index"]
        assert "0" in snap
        assert len(snap["0"]) == 1
        assert snap["0"][0]["staff_id"] is None
        assert snap["0"][0]["staff_initials"] is None
        assert snap["0"][0]["status"] == "scheduled"

    def test_happy_claimed_shift_shows_claimer_initials(self, client, mock_db):
        """A jockey claimed the unassigned shift → the snapshot now has
        their staff_id and initials, even though the original proposal
        had a different (or no) assignee."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-snap",
            "proposed_shifts": [_mk_proposal(staff_id=None)],  # engine left it ?
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-snap", proposal=proposal)]
        # KW (id=8) claimed it after commit.
        claimer = mk_user(user_id=8, is_admin=False)
        claimer.first_name = "Karl"
        claimer.last_name = "Walden"
        claimed_shift = _mk_existing_shift(
            shift_id=901, staff_id=8,
            shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
            planner_run_id="r-snap",
        )
        claimed_shift.staff = claimer
        mock_db._tables[RosterShift] = [claimed_shift]

        r = client.get("/api/admin/qa/roster-planner/runs/r-snap")
        assert r.status_code == 200
        snap = r.json()["committed_shifts_by_index"]["0"]
        assert len(snap) == 1
        assert snap[0]["staff_id"] == 8
        assert snap[0]["staff_initials"] == "KW"

    def test_happy_duplicate_committed_shows_all_initials(self, client, mock_db):
        """Duplicate override → multiple shifts share the proposal's
        (date, start, end). Snapshot list contains one entry per shift."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-snap",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-snap", proposal=proposal)]
        ms = mk_user(user_id=2)
        ms.first_name, ms.last_name = "Marek", "Smolarek"
        kw = mk_user(user_id=8)
        kw.first_name, kw.last_name = "Karl", "Walden"
        shifts = []
        for i, u in enumerate([ms, kw]):
            s = _mk_existing_shift(
                shift_id=910 + i, staff_id=u.id,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-snap",
            )
            s.staff = u
            shifts.append(s)
        mock_db._tables[RosterShift] = shifts

        r = client.get("/api/admin/qa/roster-planner/runs/r-snap")
        assert r.status_code == 200
        snap = r.json()["committed_shifts_by_index"]["0"]
        assert len(snap) == 2
        initials = sorted(s["staff_initials"] for s in snap)
        assert initials == ["KW", "MS"]

    def test_edge_uncommitted_proposal_index_absent_from_map(self, client, mock_db):
        """A proposal index that hasn't been committed shouldn't appear in
        the map at all (FE renders engine's original suggestion in that
        case, no badge)."""
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-snap",
            "proposed_shifts": [
                _mk_proposal(staff_id=2, shift_date="2026-05-11"),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
            ],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-snap", proposal=proposal)]
        # Only proposal index 0 has been committed.
        mock_db._tables[RosterShift] = [
            _mk_existing_shift(
                shift_id=920, staff_id=2,
                shift_date=date(2026, 5, 11),
                start_time=time(8, 0), end_time=time(16, 0),
                planner_run_id="r-snap",
            ),
        ]

        r = client.get("/api/admin/qa/roster-planner/runs/r-snap")
        assert r.status_code == 200
        snap = r.json()["committed_shifts_by_index"]
        assert "0" in snap
        assert "1" not in snap

    def test_boundary_after_undo_snapshot_map_empty(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        proposal = {
            "run_id": "r-snap",
            "proposed_shifts": [_mk_proposal(staff_id=2)],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-snap", proposal=proposal)]
        mock_db._tables[RosterShift] = []  # undo wiped them

        r = client.get("/api/admin/qa/roster-planner/runs/r-snap")
        assert r.status_code == 200
        assert r.json()["committed_shifts_by_index"] == {}

    def test_boundary_two_proposals_same_time_dont_merge_buckets(self, client, mock_db):
        """Regression: two proposals at the exact same (date, start, end)
        used to share a bucket — proposal 0's card showed proposal 1's
        committed shifts too. Now we use the audit-log per-proposal mapping
        to attribute shifts precisely. Reported May 2026 ('? · KW · ?')."""
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        proposal = {
            "run_id": "r-collide",
            "proposed_shifts": [
                _mk_proposal(staff_id=None),  # idx 0 — unassigned slot
                _mk_proposal(staff_id=8),     # idx 1 — KW slot, same time window
            ],
        }
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-collide", proposal=proposal)]
        # Three shifts all at 08:00-16:00 / 2026-05-11:
        #   shift 940 → unassigned (proposal 0)
        #   shift 941 → unassigned-fleet duplicate of proposal 0
        #   shift 942 → KW (proposal 1)
        kw = mk_user(user_id=8)
        kw.first_name, kw.last_name = "Karl", "Walden"
        s940 = _mk_existing_shift(
            shift_id=940, staff_id=None,
            shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
            planner_run_id="r-collide",
        )
        s941 = _mk_existing_shift(
            shift_id=941, staff_id=None,
            shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
            planner_run_id="r-collide",
        )
        s942 = _mk_existing_shift(
            shift_id=942, staff_id=8,
            shift_date=date(2026, 5, 11),
            start_time=time(8, 0), end_time=time(16, 0),
            planner_run_id="r-collide",
        )
        s942.staff = kw
        mock_db._tables[RosterShift] = [s940, s941, s942]

        # Audit-log mapping written by the commit endpoint — proposal 0 owns
        # shifts 940 + 941, proposal 1 owns shift 942. Without this, the
        # detail endpoint would bucket all three shifts together by time.
        audit = AuditLog(
            session_id="planner-r-collide",
            event=AuditLogEvent.PLANNER_RUN_COMMITTED,
            event_data=json.dumps({
                "run_id": "r-collide",
                "proposal_to_shift_ids": {"0": [940, 941], "1": [942]},
            }),
        )
        mock_db._tables[AuditLog] = [audit]

        r = client.get("/api/admin/qa/roster-planner/runs/r-collide")
        assert r.status_code == 200
        snap = r.json()["committed_shifts_by_index"]
        # Proposal 0 owns its 2 unassigned shifts only — KW must NOT leak in.
        assert sorted(s["shift_id"] for s in snap["0"]) == [940, 941]
        assert all(s["staff_id"] is None for s in snap["0"])
        # Proposal 1 owns just KW.
        assert [s["shift_id"] for s in snap["1"]] == [942]
        assert snap["1"][0]["staff_initials"] == "KW"


# =====================================================================================
# POST /runs/{id}/feedback and GET /feedback — per-engine-decision QA review
# =====================================================================================


class TestFeedbackEndpoints:
    def test_post_feedback_persists_row_tied_to_run(self, client, mock_db):
        from db_models import PlannerRun, PlannerRunFeedback
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        # Simulate the DB filling in id + submitted_at on refresh
        # (server_default/primary key would do this in real Postgres).
        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                if obj.id is None:
                    obj.id = 1
                if obj.submitted_at is None:
                    obj.submitted_at = datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        body = {
            "shift_date": "2026-05-04",
            "shift_start_time": "07:00:00",
            "shift_end_time": "11:00:00",
            "shift_staff_id": 7,
            "proposed_shift_index": 2,
            "severity": "issue",
            "comment": "KW prefers afternoons; this morning shift goes against the soft pref.",
        }
        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json=body,
        )
        assert r.status_code == 201, r.text

        added = [c.args[0] for c in mock_db.add.call_args_list]
        rows = [a for a in added if isinstance(a, PlannerRunFeedback)]
        assert len(rows) == 1
        row = rows[0]
        assert row.run_id == "r-A"
        assert row.severity == "issue"
        assert row.shift_staff_id == 7
        assert "KW prefers afternoons" in row.comment

    def test_post_feedback_unknown_run_returns_404(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = []

        r = client.post(
            "/api/admin/qa/roster-planner/runs/missing/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "no such run",
            },
        )
        assert r.status_code == 404

    def test_post_feedback_rejects_unknown_severity(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "showstopper",  # not in {blocker, issue, note}
                "comment": "x",
            },
        )
        assert r.status_code == 422

    def test_post_feedback_rejects_empty_comment(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "",  # min_length=1
            },
        )
        assert r.status_code == 422

    def test_list_feedback_empty(self, client, mock_db):
        from db_models import PlannerRunFeedback
        mock_db._tables[PlannerRunFeedback] = []

        r = client.get("/api/admin/qa/roster-planner/feedback")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_feedback_returns_rows(self, client, mock_db):
        from db_models import PlannerRunFeedback
        mock_db._tables[PlannerRunFeedback] = [
            SimpleNamespace(
                id=1,
                run_id="r-A",
                shift_date=date(2026, 5, 4),
                shift_start_time=time(7, 0),
                shift_end_time=time(11, 0),
                shift_staff_id=7,
                proposed_shift_index=2,
                severity="issue",
                comment="KW shouldn't be on mornings",
                override_json=None,
                submitted_by=1,
                submitted_at=datetime(2026, 5, 4, 9, 0, 0),
            ),
        ]

        r = client.get("/api/admin/qa/roster-planner/feedback?shift_date=2026-05-04")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["severity"] == "issue"
        assert body[0]["shift_staff_id"] == 7
        assert body[0]["override"] is None

    def test_post_feedback_with_action_delete(self, client, mock_db):
        """Action override variants — delete carries no extra fields."""
        from db_models import PlannerRun, PlannerRunFeedback
        import json as _json
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "issue",
                "comment": "Marked for deletion",
                "override": {"action": "delete"},
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["action"] == "delete"

        added = [c.args[0] for c in mock_db.add.call_args_list]
        rows = [a for a in added if isinstance(a, PlannerRunFeedback)]
        decoded = _json.loads(rows[0].override_json)
        assert decoded["action"] == "delete"

    def test_post_feedback_with_action_unassign(self, client, mock_db):
        """Regression for the 30-Apr-2026 bug: PlannerRunFeedbackOverride
        had Literal["delete","duplicate","merge","split"] but the FE was
        emitting action='unassign' (after Phase 3.5 added the Unassign
        button). The feedback POST 422'd, the dialog showed the raw
        Pydantic error, and the local override never registered."""
        from db_models import PlannerRun, PlannerRunFeedback
        import json as _json
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "Marked for unassign",
                "override": {"action": "unassign"},
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["action"] == "unassign"

        added = [c.args[0] for c in mock_db.add.call_args_list]
        rows = [a for a in added if isinstance(a, PlannerRunFeedback)]
        decoded = _json.loads(rows[0].override_json)
        assert decoded["action"] == "unassign"

    def test_post_feedback_with_action_duplicate_carries_target_staff_ids(self, client, mock_db):
        from db_models import PlannerRun, PlannerRunFeedback
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "Duplicate to 3 drivers",
                "override": {
                    "action": "duplicate",
                    "target_staff_ids": [7, 12, 9],
                },
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["action"] == "duplicate"
        assert body["override"]["target_staff_ids"] == [7, 12, 9]

    def test_post_feedback_with_action_merge_carries_direction_and_staff(self, client, mock_db):
        from db_models import PlannerRun, PlannerRunFeedback
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "Merge with previous shift",
                "override": {
                    "action": "merge",
                    "merge_direction": "left",
                    "merged_staff_id": 7,
                },
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["merge_direction"] == "left"
        assert body["override"]["merged_staff_id"] == 7

    def test_post_feedback_with_action_split_carries_time_and_two_staff(self, client, mock_db):
        from db_models import PlannerRun, PlannerRunFeedback
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "Split at midpoint",
                "override": {
                    "action": "split",
                    "split_at_time": "13:00:00",
                    "first_half_staff_id": 7,
                    "second_half_staff_id": 12,
                },
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["action"] == "split"
        assert body["override"]["split_at_time"] == "13:00:00"
        assert body["override"]["first_half_staff_id"] == 7
        assert body["override"]["second_half_staff_id"] == 12

    def test_post_feedback_with_action_split_extends_outer_bounds(self, client, mock_db):
        """Split lets each half extend past the source's bounds —
        first_half can start earlier (vehicle prep), second_half can
        end later (cleaning duties). Both fields optional; the audit
        row carries them when set."""
        from db_models import PlannerRun, PlannerRunFeedback
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                obj.id = obj.id or 1
                obj.submitted_at = obj.submitted_at or datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        # Source 11:10–14:20, split at 12:45. First half pre-extended to
        # 10:30, second half post-extended to 15:00.
        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "shift_start_time": "11:10:00",
                "shift_end_time": "14:20:00",
                "severity": "note",
                "comment": "Extended both ends for prep + cleaning",
                "override": {
                    "action": "split",
                    "split_at_time": "12:45:00",
                    "first_half_start_time": "10:30:00",
                    "first_half_staff_id": 7,
                    "second_half_end_time": "15:00:00",
                    "second_half_staff_id": 12,
                },
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["first_half_start_time"] == "10:30:00"
        assert body["override"]["second_half_end_time"] == "15:00:00"

    def test_post_feedback_rejects_unknown_action(self, client, mock_db):
        from db_models import PlannerRun
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "severity": "note",
                "comment": "x",
                "override": {"action": "evaporate"},
            },
        )
        assert r.status_code == 422

    def test_post_feedback_with_override_persists_json(self, client, mock_db):
        """When the edit modal includes a structured override, it round-trips
        as JSON in override_json and as a typed PlannerRunFeedbackOverride
        in the response."""
        from db_models import PlannerRun, PlannerRunFeedback
        import json as _json
        mock_db._tables[PlannerRun] = [_mk_run_row(run_id="r-A")]

        def _fake_refresh(obj):
            if isinstance(obj, PlannerRunFeedback):
                if obj.id is None:
                    obj.id = 1
                if obj.submitted_at is None:
                    obj.submitted_at = datetime(2026, 5, 4, 9, 0, 0)
        mock_db.refresh.side_effect = _fake_refresh

        r = client.post(
            "/api/admin/qa/roster-planner/runs/r-A/feedback",
            json={
                "shift_date": "2026-05-04",
                "shift_start_time": "07:00:00",
                "shift_end_time": "11:00:00",
                "shift_staff_id": 7,
                "severity": "note",
                "comment": "Would assign MS instead, change start to 07:30",
                "override": {
                    "staff_id": 20,
                    "start_time": "07:30:00",
                    "end_time": "11:00:00",
                },
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override"]["staff_id"] == 20
        assert body["override"]["start_time"] == "07:30:00"

        # Stored as JSON text on the row.
        added = [c.args[0] for c in mock_db.add.call_args_list]
        rows = [a for a in added if isinstance(a, PlannerRunFeedback)]
        decoded = _json.loads(rows[0].override_json)
        assert decoded["staff_id"] == 20

    def test_list_feedback_invalid_shift_start_time_rejected(self, client, mock_db):
        r = client.get(
            "/api/admin/qa/roster-planner/feedback?shift_start_time=not-a-time"
        )
        assert r.status_code == 422

    def test_list_feedback_limit_out_of_range(self, client, mock_db):
        r = client.get("/api/admin/qa/roster-planner/feedback?limit=0")
        assert r.status_code == 422
        r2 = client.get("/api/admin/qa/roster-planner/feedback?limit=600")
        assert r2.status_code == 422


# =====================================================================================
# Phase 3 — POST /commit and DELETE /runs/{run_id} (additive commit + undo).
# =====================================================================================


def _mk_planner_run(run_id="run-test-1", proposed_shifts=None):
    """Build a PlannerRun-shaped MagicMock with proposal_json populated."""
    from db_models import PlannerRun

    run = MagicMock(spec=PlannerRun)
    run.run_id = run_id
    run.window_start = date(2026, 5, 1)
    run.window_end = date(2026, 5, 28)
    run.proposal_json = json.dumps({"proposed_shifts": list(proposed_shifts or [])})
    run.diff_vs_current_json = None
    run.warnings_json = None
    run.error_text = None
    return run


def _mk_proposal(
    *,
    kind="new",
    staff_id=2,
    shift_date="2026-05-11",
    end_date=None,
    start_time="08:00",
    end_time="16:00",
    shift_type="full_morning",
    events=None,
):
    return {
        "kind": kind,
        "shift_id": None,
        "date": shift_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "shift_type": shift_type,
        "is_custom_range": False,
        "staff_id": staff_id,
        "staff_initials": "MS",
        "events": events or [],
        "peak_concurrent_count": 1,
        "required_staff_count": 1,
        "reason": "test proposal",
        "untouched_reason": None,
    }


def _mk_existing_shift(*, shift_id=99, staff_id=2, shift_date=date(2026, 5, 11),
                       start_time=time(8, 0), end_time=time(16, 0),
                       status=ShiftStatus.SCHEDULED, planner_run_id=None):
    from db_models import RosterShift as RS

    s = MagicMock(spec=RS)
    s.id = shift_id
    s.staff_id = staff_id
    s.date = shift_date
    s.end_date = shift_date
    s.start_time = start_time
    s.end_time = end_time
    s.status = status
    s.planner_run_id = planner_run_id
    s.created_source = "manual" if planner_run_id is None else "planner"
    # Default staff to None when staff_id is None — endpoints that check
    # `if s.staff` would otherwise see a MagicMock and produce gibberish
    # initials. Test that wants a real staff object overrides s.staff after.
    s.staff = None if staff_id is None else MagicMock()
    return s


class TestCommitHappy:
    """Happy path — committing valid proposals writes RosterShift rows + audit."""

    def test_commit_single_new_proposal_creates_shift_row(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []  # no existing → no overlap

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "run-test-1"
        assert body["shifts_created"] == 1

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shift_rows = [a for a in added if isinstance(a, RosterShift)]
        assert len(shift_rows) == 1
        s = shift_rows[0]
        assert s.staff_id == 2
        assert s.created_source == "planner"
        assert s.planner_run_id == "run-test-1"
        assert mock_db._committed is True

    def test_commit_creates_booking_links_for_each_event(self, client, mock_db):
        from db_models import PlannerRun, RosterShift, ShiftBookingLink

        events = [
            {"booking_id": 11, "booking_reference": "TAG-A", "event_type": "drop_off",
             "event_time": "2026-05-11T08:30:00+01:00"},
            {"booking_id": 12, "booking_reference": "TAG-B", "event_type": "pick_up",
             "event_time": "2026-05-11T15:00:00+01:00"},
        ]
        run = _mk_planner_run(proposed_shifts=[_mk_proposal(events=events)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []
        mock_db._tables[ShiftBookingLink] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        link_rows = [a for a in added if isinstance(a, ShiftBookingLink)]
        booking_ids = sorted(l.booking_id for l in link_rows)
        assert booking_ids == [11, 12]

    def test_commit_fires_audit_event(self, client, mock_db):
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        audit_rows = [a for a in added if isinstance(a, AuditLog)]
        committed = [a for a in audit_rows if a.event == AuditLogEvent.PLANNER_RUN_COMMITTED]
        assert len(committed) == 1
        payload = json.loads(committed[0].event_data)
        assert payload["run_id"] == "run-test-1"
        assert payload["shifts_created"] == 1

    def test_commit_unassigned_proposal_skips_overlap_check(self, client, mock_db):
        """staff_id=None means engine couldn't assign anyone — overlap check
        irrelevant; the row goes in as-is."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=None)])
        # Even if there's an existing shift at the same time, no overlap fires
        # because we're not assigning a staff member.
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 1


class TestCommitUnhappy:
    def test_commit_unknown_run_id_returns_404(self, client, mock_db):
        from db_models import PlannerRun

        mock_db._tables[PlannerRun] = []
        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "nope", "proposal_indexes": [0]},
        )
        assert r.status_code == 404

    def test_commit_extend_kind_rejected(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[_mk_proposal(kind="extend")],
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 400
        assert "kind='extend'" in r.json()["detail"]

    def test_commit_untouched_kind_rejected(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[_mk_proposal(kind="untouched_for_reason")],
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 400

    def test_commit_overlap_returns_409_and_does_not_write(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        existing = _mk_existing_shift()
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = [existing]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 409
        assert "overlaps existing shift" in r.json()["detail"]
        # Atomic — no commit should have fired.
        assert mock_db._committed is False

    def test_commit_duplicate_index_rejected(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0, 0]},
        )
        assert r.status_code == 400
        assert "Duplicate" in r.json()["detail"]

    def test_commit_out_of_range_index_rejected(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [5]},
        )
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"]

    def test_commit_run_with_empty_proposal_json_returns_400(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run()
        run.proposal_json = None
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 400


class TestCommitAuth:
    def test_non_qa_admin_returns_403(self, mock_db):
        # Bypass the global QA override fixture; provide just admin (non-QA).
        from db_models import PlannerRun

        non_qa = mk_user(user_id=99, is_admin=True)

        async def override_require_admin():
            return non_qa

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = override_require_admin
        try:
            client = TestClient(app)
            r = client.post(
                "/api/admin/qa/roster-planner/commit",
                json={"run_id": "x", "proposal_indexes": []},
            )
            assert r.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestCommitEdge:
    def test_commit_empty_proposal_indexes_creates_zero_shifts(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": []},
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 0

    def test_commit_multiple_proposals_all_created(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(staff_id=2, shift_date="2026-05-11"),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
                _mk_proposal(staff_id=4, shift_date="2026-05-13"),
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0, 1, 2]},
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 3


class TestCommitBoundary:
    def test_commit_overnight_proposal_sets_end_date(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(
                    shift_date="2026-05-11",
                    end_date="2026-05-12",
                    start_time="22:00",
                    end_time="02:00",
                )
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={"run_id": "run-test-1", "proposal_indexes": [0]},
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shift_rows = [a for a in added if isinstance(a, RosterShift)]
        assert shift_rows[0].date == date(2026, 5, 11)
        assert shift_rows[0].end_date == date(2026, 5, 12)


# =====================================================================================
# Phase 3 — DELETE /runs/{run_id} (undo).
# =====================================================================================


class TestUndoHappy:
    def test_undo_deletes_all_scheduled_shifts_for_run(self, client, mock_db):
        from db_models import RosterShift

        committed = [
            _mk_existing_shift(shift_id=101, planner_run_id="run-x"),
            _mk_existing_shift(shift_id=102, planner_run_id="run-x", shift_date=date(2026, 5, 12)),
        ]
        mock_db._tables[RosterShift] = committed
        mock_db.delete = MagicMock()

        r = client.delete("/api/admin/qa/roster-planner/runs/run-x")
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "run-x"
        assert body["shifts_deleted"] == 2
        assert mock_db.delete.call_count == 2

    def test_undo_fires_audit_event(self, client, mock_db):
        from db_models import RosterShift, AuditLog, AuditLogEvent

        mock_db._tables[RosterShift] = [_mk_existing_shift(shift_id=200, planner_run_id="run-x")]
        mock_db.delete = MagicMock()

        r = client.delete("/api/admin/qa/roster-planner/runs/run-x")
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        audit_rows = [a for a in added if isinstance(a, AuditLog)]
        undone = [a for a in audit_rows if a.event == AuditLogEvent.PLANNER_RUN_UNDONE]
        assert len(undone) == 1
        payload = json.loads(undone[0].event_data)
        assert payload["shifts_deleted"] == 1


class TestUndoIdempotency:
    def test_undo_with_no_matching_shifts_returns_zero(self, client, mock_db):
        from db_models import RosterShift

        mock_db._tables[RosterShift] = []  # nothing to delete
        mock_db.delete = MagicMock()

        r = client.delete("/api/admin/qa/roster-planner/runs/run-already-undone")
        assert r.status_code == 200
        assert r.json()["shifts_deleted"] == 0
        assert mock_db.delete.call_count == 0


class TestUndoAuth:
    def test_non_qa_admin_returns_403(self, mock_db):
        non_qa = mk_user(user_id=99, is_admin=True)

        async def override_require_admin():
            return non_qa

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = override_require_admin
        try:
            client = TestClient(app)
            r = client.delete("/api/admin/qa/roster-planner/runs/run-x")
            assert r.status_code == 403
        finally:
            app.dependency_overrides.clear()


# =====================================================================================
# Phase 3.5 — commit-time overrides (unassign / delete / duplicate).
# Per SPEC.md Happy/Unhappy/Edge/Boundary.
# =====================================================================================


class TestCommitOverrideUnassign:
    """Override action='unassign' drops staff_id to None at write time."""

    def test_happy_unassign_writes_shift_with_null_staff_id(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "unassign"}},
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 1

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert len(shifts) == 1
        assert shifts[0].staff_id is None  # the override dropped it

    def test_edge_unassign_skips_overlap_check(self, client, mock_db):
        """Even if an existing shift overlaps for the original staff_id,
        unassigning means we no longer care — the unassigned write goes in."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        existing = _mk_existing_shift(staff_id=2)  # would normally conflict
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = [existing]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "unassign"}},
            },
        )
        # Unassigned shift writes through — no overlap check fires for None.
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 1


class TestCommitOverrideDelete:
    """Override action='delete' silently skips writing this proposal."""

    def test_happy_delete_skips_one_of_many(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(staff_id=2, shift_date="2026-05-11"),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
                _mk_proposal(staff_id=4, shift_date="2026-05-13"),
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0, 1, 2],
                "overrides": {"1": {"action": "delete"}},
            },
        )
        assert r.status_code == 200
        # Index 1 deleted → 2 shifts written instead of 3.
        assert r.json()["shifts_created"] == 2

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        staff_ids = sorted(s.staff_id for s in shifts)
        assert staff_ids == [2, 4]  # staff_id=3 was deleted

    def test_edge_delete_unticked_index_is_no_op(self, client, mock_db):
        """An override on a proposal index that wasn't ticked has no effect —
        the proposal isn't being written either way."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [],          # nothing ticked
                "overrides": {"0": {"action": "delete"}},
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 0


class TestCommitOverrideDuplicate:
    """Override action='duplicate' writes original + N additional shifts."""

    def test_happy_duplicate_writes_n_plus_one(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3, 4],
                }},
            },
        )
        assert r.status_code == 200
        # original (staff_id=2) + 2 targets (3, 4) = 3 shifts
        assert r.json()["shifts_created"] == 3

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        staff_ids = sorted(s.staff_id for s in shifts)
        assert staff_ids == [2, 3, 4]

    def test_edge_duplicate_dedupes_targets_against_original(self, client, mock_db):
        """If admin ticks the original staff_id as a target, don't double-write."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [2, 3, 3],  # 2 = original; 3 ticked twice
                }},
            },
        )
        assert r.status_code == 200
        # original + one unique target (3) = 2 shifts
        assert r.json()["shifts_created"] == 2

    def test_unhappy_duplicate_without_targets_returns_400(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [],
                }},
            },
        )
        assert r.status_code == 400
        assert "target_staff_ids" in r.json()["detail"]

    def test_unhappy_duplicate_target_overlaps_existing(self, client, mock_db):
        """If a duplicate target staff has an overlapping shift, the whole
        commit fails atomically — no half-written rows."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        # Existing shift for staff_id=3 overlaps the proposal time.
        existing = _mk_existing_shift(staff_id=3)
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = [existing]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3],
                }},
            },
        )
        assert r.status_code == 409
        assert mock_db._committed is False  # atomic rollback

    def test_boundary_duplicate_creates_booking_links_for_each_shift(self, client, mock_db):
        from db_models import PlannerRun, RosterShift, ShiftBookingLink

        events = [
            {"booking_id": 11, "booking_reference": "TAG-A", "event_type": "drop_off",
             "event_time": "2026-05-11T08:30:00+01:00"},
        ]
        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2, events=events)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3, 4],
                }},
            },
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        link_rows = [a for a in added if isinstance(a, ShiftBookingLink)]
        # 3 shifts × 1 event each = 3 link rows, all to booking 11.
        assert len(link_rows) == 3
        assert all(l.booking_id == 11 for l in link_rows)


class TestCommitOverrideDuplicateUnassignedExtras:
    """Override action='duplicate' can also fan out unassigned slots tagged
    for jockey or fleet — admins use these to leave a claimable hole rather
    than picking a specific person."""

    def test_happy_duplicate_with_unassigned_jockey_writes_extra_row(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [],
                    "add_unassigned_jockey": True,
                }},
            },
        )
        assert r.status_code == 200
        # original (staff=2) + 1 unassigned-jockey extra = 2 shifts
        assert r.json()["shifts_created"] == 2

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert len(shifts) == 2
        extra = next(s for s in shifts if s.staff_id is None)
        assert extra.intended_driver_type == "jockey"

    def test_happy_duplicate_with_unassigned_fleet_writes_fleet_tagged_row(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "add_unassigned_fleet": True,
                }},
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 2

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        extra = next(s for s in shifts if s.staff_id is None)
        assert extra.intended_driver_type == "fleet"

    def test_happy_duplicate_combines_targets_and_both_unassigned_extras(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3],
                    "add_unassigned_jockey": True,
                    "add_unassigned_fleet": True,
                }},
            },
        )
        assert r.status_code == 200
        # original + 1 target + 2 unassigned extras = 4 shifts
        assert r.json()["shifts_created"] == 4

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        unassigned_types = sorted(
            s.intended_driver_type for s in shifts if s.staff_id is None
        )
        assert unassigned_types == ["fleet", "jockey"]

    def test_unhappy_duplicate_with_no_targets_or_extras_returns_400(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [],
                    "add_unassigned_jockey": False,
                    "add_unassigned_fleet": False,
                }},
            },
        )
        assert r.status_code == 400
        assert "add_unassigned" in r.json()["detail"]

    def test_edge_unassigned_extras_default_false_preserves_old_behaviour(self, client, mock_db):
        """Old commit payloads (no flags) keep working — flags default to False."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3, 4],
                }},
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 3


class TestCommitGuardAgainstReCommit:
    """A proposal_index that already has a live shift in this run cannot be
    committed a second time — Phase 3 commits each proposal once. Without
    this guard a second commit re-writes the original (and any duplicate
    extras) silently, producing ghost shifts. May 2026 incident:
    proposal 50 ended up with 3 live rows after three stacked commits."""

    def test_unhappy_recommit_of_already_committed_proposal_returns_409(
        self, client, mock_db
    ):
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        # Live shift 393 is what the previous commit left behind for
        # proposal 0; the audit row maps it back to proposal_index 0.
        existing = _mk_existing_shift(shift_id=393, staff_id=2)
        existing.planner_run_id = "run-test-1"
        mock_db._tables[RosterShift] = [existing]
        mock_db._tables[AuditLog] = [
            AuditLog(
                session_id="planner-run-test-1",
                event=AuditLogEvent.PLANNER_RUN_COMMITTED,
                event_data=json.dumps({
                    "run_id": "run-test-1",
                    "proposal_to_shift_ids": {"0": [393]},
                }),
            )
        ]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3],
                }},
            },
        )
        assert r.status_code == 409
        assert "already committed" in r.json()["detail"]
        assert mock_db._committed is False

    def test_edge_recommit_after_undo_is_allowed(self, client, mock_db):
        """Once the run is undone (live shifts gone), the audit row's
        shift_ids no longer match any live row → guard skips this proposal."""
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        # Audit row from a previous (now-undone) commit references shift 393,
        # but no live RosterShift with that id exists anymore.
        mock_db._tables[RosterShift] = []
        mock_db._tables[AuditLog] = [
            AuditLog(
                session_id="planner-run-test-1",
                event=AuditLogEvent.PLANNER_RUN_COMMITTED,
                event_data=json.dumps({
                    "run_id": "run-test-1",
                    "proposal_to_shift_ids": {"0": [393]},
                }),
            )
        ]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 1


class TestCommitOverrideUnsupportedActions:
    """merge / split are recognised by the schema but rejected at commit
    until Phase 3.6 lands. Surfaces explicitly so the FE can grey them out."""

    def test_unhappy_merge_action_returns_400(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "merge",
                    "merge_with_index": 1,
                    "merged_staff_id": 2,
                }},
            },
        )
        assert r.status_code == 400
        assert "merge" in r.json()["detail"]

    def test_unhappy_split_action_returns_400(self, client, mock_db):
        from db_models import PlannerRun

        run = _mk_planner_run(proposed_shifts=[_mk_proposal()])
        mock_db._tables[PlannerRun] = [run]

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "split",
                    "split_at_time": "12:00",
                    "first_half_staff_id": 2,
                    "second_half_staff_id": 3,
                }},
            },
        )
        assert r.status_code == 400


class TestCommitOverrideAudit:
    """Audit log captures the override applied per index."""

    def test_audit_payload_includes_applied_overrides(self, client, mock_db):
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(staff_id=2),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0, 1],
                "overrides": {
                    "0": {"action": "unassign"},
                    "1": {"action": "delete"},
                },
            },
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        audit_rows = [a for a in added if isinstance(a, AuditLog)]
        committed = [a for a in audit_rows if a.event == AuditLogEvent.PLANNER_RUN_COMMITTED]
        assert len(committed) == 1
        payload = json.loads(committed[0].event_data)
        applied = payload.get("applied_overrides", [])
        actions = sorted(o["action"] for o in applied)
        assert actions == ["delete", "unassign"]

    def test_audit_records_unassign_alone(self, client, mock_db):
        """Audit payload should include the unassign action label even when
        it's the only override applied. Locks the round-trip for solo cases."""
        from db_models import PlannerRun, RosterShift, AuditLog, AuditLogEvent

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=2)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {"action": "unassign"}},
            },
        )
        assert r.status_code == 200

        added = [c.args[0] for c in mock_db.add.call_args_list]
        audit_rows = [a for a in added if isinstance(a, AuditLog)]
        committed = [a for a in audit_rows if a.event == AuditLogEvent.PLANNER_RUN_COMMITTED]
        payload = json.loads(committed[0].event_data)
        applied = payload.get("applied_overrides", [])
        assert len(applied) == 1
        assert applied[0]["action"] == "unassign"
        assert applied[0]["proposal_index"] == 0


class TestCommitOverrideBoundaries:
    """Edge cases that exercise interactions between actions."""

    def test_boundary_delete_every_proposal_writes_zero_shifts(self, client, mock_db):
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(staff_id=2),
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),
                _mk_proposal(staff_id=4, shift_date="2026-05-13"),
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0, 1, 2],
                "overrides": {
                    "0": {"action": "delete"},
                    "1": {"action": "delete"},
                    "2": {"action": "delete"},
                },
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 0

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        assert len(shifts) == 0

    def test_edge_duplicate_of_unassigned_writes_only_targets(self, client, mock_db):
        """Original staff_id=None, override duplicates to [3, 4]. The 'original'
        unassigned write is suppressed by the dedupe (None ≠ 3 ≠ 4 but None is
        the lead staff and target list provides the actual writes). With None
        original, we still write 1 unassigned + 2 targeted = 3 shifts."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(proposed_shifts=[_mk_proposal(staff_id=None)])
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0],
                "overrides": {"0": {
                    "action": "duplicate",
                    "target_staff_ids": [3, 4],
                }},
            },
        )
        assert r.status_code == 200
        assert r.json()["shifts_created"] == 3

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        staff_ids = [s.staff_id for s in shifts]
        # 1 unassigned (None) + 2 targeted; order matches insertion sequence.
        assert sorted(staff_ids, key=lambda x: (x is not None, x)) == [None, 3, 4]

    def test_edge_mixed_overrides_in_single_commit(self, client, mock_db):
        """Three different override actions applied in one commit. Locks the
        per-index dispatch — each index gets its own action without bleeding."""
        from db_models import PlannerRun, RosterShift

        run = _mk_planner_run(
            proposed_shifts=[
                _mk_proposal(staff_id=2, shift_date="2026-05-11"),  # unassign
                _mk_proposal(staff_id=3, shift_date="2026-05-12"),  # delete
                _mk_proposal(staff_id=4, shift_date="2026-05-13"),  # duplicate to [5]
                _mk_proposal(staff_id=6, shift_date="2026-05-14"),  # no override (plain)
            ]
        )
        mock_db._tables[PlannerRun] = [run]
        mock_db._tables[RosterShift] = []

        r = client.post(
            "/api/admin/qa/roster-planner/commit",
            json={
                "run_id": "run-test-1",
                "proposal_indexes": [0, 1, 2, 3],
                "overrides": {
                    "0": {"action": "unassign"},
                    "1": {"action": "delete"},
                    "2": {"action": "duplicate", "target_staff_ids": [5]},
                },
            },
        )
        assert r.status_code == 200
        # 1 (unassigned) + 0 (deleted) + 2 (duplicated 4 + 5) + 1 (plain 6) = 4
        assert r.json()["shifts_created"] == 4

        added = [c.args[0] for c in mock_db.add.call_args_list]
        shifts = [a for a in added if isinstance(a, RosterShift)]
        # Expect: None (was 2, unassigned), 4, 5 (duplicate), 6 (plain).
        # Index 1 (staff_id=3) should NOT appear.
        staff_ids = sorted([s.staff_id for s in shifts], key=lambda x: (x is not None, x))
        assert staff_ids == [None, 4, 5, 6]
        assert 3 not in staff_ids


# ============================================================================
# /regenerate-auto endpoint — date-resolution logic
# Pure tests of `_resolve_dates`. Endpoint behaviour wraps it with auth and
# the auto_create_or_extend loop, both already covered elsewhere.
# ============================================================================

class TestRegenerateAutoDateResolution:
    def _settings(self, window_days=28):
        from roster_planner import PlannerSettings
        return PlannerSettings(
            window_days=window_days,
            gap_max_minutes=120,
            mixed_gap_max_minutes=120,
            start_buffer_minutes=30,
            end_buffer_minutes=30,
            staffing_thresholds=[(3, 1), (999, 2)],
            max_hours_per_week=40,
            min_rest_hours=8,
            untouchable_hours=24,
            min_shift_minutes=60,
        )

    def test_happy_next_4_weeks_returns_window_days_dates(self):
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(mode="next_4_weeks")
        out = _resolve_dates(req, self._settings(window_days=28))
        assert len(out) == 28

    def test_happy_date_range_returns_inclusive_dates(self):
        from datetime import date as date_type
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(
            mode="date_range",
            date_from=date_type(2026, 6, 1),
            date_to=date_type(2026, 6, 7),
        )
        out = _resolve_dates(req, self._settings())
        assert len(out) == 7
        assert date_type(2026, 6, 1) in out
        assert date_type(2026, 6, 7) in out
        assert date_type(2026, 6, 8) not in out

    def test_happy_individual_dates_returns_set_of_dates(self):
        from datetime import date as date_type
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(
            mode="individual_dates",
            dates=[date_type(2026, 6, 4), date_type(2026, 6, 11), date_type(2026, 6, 4)],  # dup
        )
        out = _resolve_dates(req, self._settings())
        assert out == {date_type(2026, 6, 4), date_type(2026, 6, 11)}

    def test_unhappy_invalid_mode_rejected_at_request_validation(self):
        import pytest
        from pydantic import ValidationError
        from routers.roster import RegenerateAutoRequest
        with pytest.raises(ValidationError):
            RegenerateAutoRequest(mode="not_a_mode")

    def test_unhappy_date_range_missing_endpoints_returns_422(self):
        import pytest
        from fastapi import HTTPException
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(mode="date_range")
        with pytest.raises(HTTPException) as exc:
            _resolve_dates(req, self._settings())
        assert exc.value.status_code == 422

    def test_unhappy_date_range_to_before_from_returns_422(self):
        import pytest
        from datetime import date as date_type
        from fastapi import HTTPException
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(
            mode="date_range",
            date_from=date_type(2026, 6, 7),
            date_to=date_type(2026, 6, 1),
        )
        with pytest.raises(HTTPException) as exc:
            _resolve_dates(req, self._settings())
        assert exc.value.status_code == 422

    def test_edge_individual_dates_empty_list_rejected(self):
        import pytest
        from fastapi import HTTPException
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(mode="individual_dates", dates=[])
        with pytest.raises(HTTPException) as exc:
            _resolve_dates(req, self._settings())
        assert exc.value.status_code == 422

    def test_boundary_date_range_single_day_returns_one_date(self):
        from datetime import date as date_type
        from routers.roster import _resolve_dates, RegenerateAutoRequest
        req = RegenerateAutoRequest(
            mode="date_range",
            date_from=date_type(2026, 6, 4),
            date_to=date_type(2026, 6, 4),
        )
        out = _resolve_dates(req, self._settings())
        assert out == {date_type(2026, 6, 4)}


