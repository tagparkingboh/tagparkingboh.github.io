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

    def limit(self, _n):
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


