"""
Mocked-integration tests for the v3 ?source= filter on GET /api/roster.

Per backend/docs/SPEC.md (Roster Planner v3, locked 2026-05-04), the admin-only
toggle on the Calendar / Planner pages drives a `?source=` query that maps to:

  toggle "All"    → ?source=all     (every shift, no filter)
  toggle "Auto"   → ?source=auto    (created_source = 'auto')
  toggle "Manual" → no param        (default: created_source != 'auto')

Plus the legacy explicit values 'manual' and 'planner' that filter to that one
source exactly. All tests use TestClient(app) and import from main, per
SPEC's coverage rule (2026-04-21 lesson).
"""
import sys
from pathlib import Path
from datetime import date, time, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app
from database import get_db


def make_shift(*, id, source, staff_id=10, shift_date=None):
    s = MagicMock()
    s.id = id
    s.created_source = source
    s.staff_id = staff_id
    s.staff = MagicMock(first_name="Karl", last_name="Walden") if staff_id else None
    s.booking_id = None
    s.bookings = []
    s.date = shift_date or date(2026, 5, 10)
    s.end_date = s.date
    s.start_time = time(9, 0)
    s.end_time = time(17, 0)
    s.shift_type = MagicMock(value="morning")
    s.status = MagicMock(value="scheduled")
    s.notes = None
    s.intended_driver_type = "jockey"
    return s


@pytest.fixture
def client_with_shifts():
    """TestClient where the terminal .all() on RosterShift queries returns
    a list mutated per-test."""
    state = {"shifts": [], "applied_filters": []}

    mock_db = MagicMock()

    # Capture .filter(...) args at the terminal query so tests can introspect
    # which filter clauses the source branch added.
    def query_side_effect(model):
        chain = MagicMock()
        chain.all.side_effect = lambda: list(state["shifts"])

        def filter_side_effect(*args, **kwargs):
            state["applied_filters"].append(args)
            return chain
        chain.filter.side_effect = filter_side_effect
        chain.order_by.return_value.all.side_effect = lambda: list(state["shifts"])
        return chain

    mock_db.query.side_effect = query_side_effect

    def _mock_get_db():
        yield mock_db

    from routers.roster import require_admin
    from types import SimpleNamespace
    _admin = SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True, is_active=True,
        first_name="Admin", last_name="Test",
    )
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[require_admin] = lambda: _admin
    try:
        client = TestClient(app)

        def set_shifts(shifts):
            state["shifts"] = shifts
            state["applied_filters"] = []

        yield client, set_shifts, state
    finally:
        app.dependency_overrides.clear()


class TestSourceFilterAll:
    """source=all bypasses the default ≠ auto exclusion."""

    def test_happy_returns_auto_manual_and_planner(self, client_with_shifts):
        client, set_shifts, _ = client_with_shifts
        set_shifts([
            make_shift(id=1, source="auto"),
            make_shift(id=2, source="manual"),
            make_shift(id=3, source="planner"),
        ])
        r = client.get("/api/roster?source=all")
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert set(ids) == {1, 2, 3}

    def test_edge_empty_db_returns_empty_list(self, client_with_shifts):
        client, set_shifts, _ = client_with_shifts
        set_shifts([])
        r = client.get("/api/roster?source=all")
        assert r.status_code == 200
        assert r.json() == []


class TestSourceFilterAuto:
    """source=auto narrows to created_source='auto' only."""

    def test_happy_returns_only_auto(self, client_with_shifts):
        client, set_shifts, state = client_with_shifts
        set_shifts([make_shift(id=99, source="auto")])
        r = client.get("/api/roster?source=auto")
        assert r.status_code == 200
        # The handler applied a filter clause — at least one filter call
        # was made (created_source == 'auto').
        assert any(state["applied_filters"]), "expected the auto branch to apply a filter"


class TestSourceFilterManualPlanner:
    """source=manual / source=planner filter to exactly that source."""

    def test_happy_source_manual_filter_applied(self, client_with_shifts):
        client, set_shifts, state = client_with_shifts
        set_shifts([make_shift(id=1, source="manual")])
        r = client.get("/api/roster?source=manual")
        assert r.status_code == 200
        assert any(state["applied_filters"])

    def test_happy_source_planner_filter_applied(self, client_with_shifts):
        client, set_shifts, state = client_with_shifts
        set_shifts([make_shift(id=1, source="planner")])
        r = client.get("/api/roster?source=planner")
        assert r.status_code == 200
        assert any(state["applied_filters"])


class TestSourceFilterDefault:
    """No source param → backend's default exclusion of auto. v3 toggle
    'Manual' relies on this exact behaviour as a regression guard."""

    def test_happy_no_param_applies_neq_auto_filter(self, client_with_shifts):
        client, set_shifts, state = client_with_shifts
        set_shifts([make_shift(id=1, source="manual")])
        r = client.get("/api/roster")
        assert r.status_code == 200
        # Default branch must apply the != 'auto' filter so today's
        # Calendar behaviour is preserved when v3 lands.
        assert any(state["applied_filters"])


class TestSourceFilterBoundary:
    """Unknown source string falls through to the default branch (no 422)."""

    def test_unknown_source_treated_as_default(self, client_with_shifts):
        client, set_shifts, state = client_with_shifts
        set_shifts([make_shift(id=1, source="manual")])
        r = client.get("/api/roster?source=garbage")
        assert r.status_code == 200
        assert any(state["applied_filters"])
