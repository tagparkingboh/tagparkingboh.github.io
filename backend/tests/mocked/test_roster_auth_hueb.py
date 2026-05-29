"""
Auth-boundary HUEB for the roster admin surface (2026-05-29 critical fix).

Every old /staff, /employees, /roster, /payroll, /holidays endpoint had
no `Depends(require_admin)` — meaning anyone who could reach the API
could read / mutate roster + staff data. This file exercises the
boundary:

    H — admin token → GET /api/roster                       → 200
    U — no token / no override → POST /api/roster           → 401
    E — non-admin (employee) token → POST /api/roster       → 403
    B — non-admin (employee) token → GET /api/employee/shifts → 200

Per project policy (`feedback_no_unilateral_backend.md`) the auth dep
was added with explicit sign-off — these tests pin the contract so a
future "small cleanup" can't quietly take the guard back off.
"""
import sys
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import app
from database import get_db
from routers.roster import get_current_user, require_admin
from db_models import RosterShift


ADMIN_USER = SimpleNamespace(
    id=1, email="admin@tag.test", is_admin=True, is_active=True,
    first_name="Admin", last_name="Test",
)
EMPLOYEE_USER = SimpleNamespace(
    id=2, email="emp@tag.test", is_admin=False, is_active=True,
    first_name="Emp", last_name="Test",
)


def _stub_db():
    """Mock DB that returns empty lists for any roster-shaped query so the
    handler body succeeds (it's the auth boundary we care about, not the
    business logic — that's covered by the existing roster suites)."""
    db = MagicMock()

    def _q(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = []
        chain.first.return_value = None
        return chain
    db.query.side_effect = _q
    db.commit = MagicMock()
    return db


@pytest.fixture
def client():
    """TestClient with `get_db` overridden to a stub. Auth deps are NOT
    overridden by default — each test wires the specific auth shape it
    needs and tears down afterwards."""
    def _gen():
        yield _stub_db()
    app.dependency_overrides[get_db] = _gen
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestAuthBoundaryHUEB:

    def test_H_admin_can_access_admin_endpoint(self, client):
        """Happy: with the admin override in place, GET /api/roster
        passes the auth gate and the handler runs. (Body is empty
        because the DB stub returns no shifts.)"""
        app.dependency_overrides[require_admin] = lambda: ADMIN_USER
        try:
            r = client.get("/api/roster")
            assert r.status_code == 200, r.text
            assert isinstance(r.json(), list)
        finally:
            app.dependency_overrides.pop(require_admin, None)

    def test_U_no_token_returns_401_on_mutating_admin_endpoint(self, client):
        """Unhappy: no Authorization header → get_current_user rejects
        with 401 before the handler ever runs. Verifies the gate is
        actually wired — without the dep added today, this POST would
        have succeeded against an open API."""
        # No auth override → real get_current_user runs and 401s.
        r = client.post("/api/roster", json={
            "staff_id": 1,
            "date": "2026-06-01",
            "start_time": "09:00",
            "end_time": "17:00",
            "shift_type": "morning",
            "status": "scheduled",
        })
        assert r.status_code == 401, r.text
        assert "authent" in r.json()["detail"].lower()

    def test_E_employee_token_gets_403_on_admin_endpoint(self, client):
        """Edge: a valid non-admin (employee) session → get_current_user
        succeeds → require_admin sees is_admin=False → 403 Forbidden.
        Critical: confirms require_admin is actually doing the role check,
        not just the auth check."""
        # Override get_current_user to return the employee user. The
        # real require_admin dependency then runs and must reject.
        app.dependency_overrides[get_current_user] = lambda: EMPLOYEE_USER
        try:
            r = client.post("/api/roster", json={
                "staff_id": 1,
                "date": "2026-06-01",
                "start_time": "09:00",
                "end_time": "17:00",
                "shift_type": "morning",
                "status": "scheduled",
            })
            assert r.status_code == 403, r.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_B_employee_token_still_works_on_employee_endpoint(self, client):
        """Boundary: the lockdown only adds require_admin to old admin
        paths. /employee/* endpoints remain on get_current_user — the
        employee surface must keep working for legit employees. Calls
        GET /api/employee/shifts with a non-admin token and expects
        the handler to run (returns 200 with whatever the stub yields)."""
        app.dependency_overrides[get_current_user] = lambda: EMPLOYEE_USER
        try:
            r = client.get("/api/employee/shifts")
            assert r.status_code == 200, r.text
            assert isinstance(r.json(), list)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
