"""
Roster v4 Phase 1 (2026-07-22) — hueb unit + integration tests.

Covers the owner-agreed spec items shipped in Phase 1:
- Uniform release notice (default 72h, ROSTER_RELEASE_NOTICE_HOURS) for
  claimed AND admin-assigned shifts.
- 72h notice on self-added unavailability (the Lee scenario).
- FOUNDER_EMAIL notification + audit row on claim / release / unavailability.
- Assignment provenance (assigned_source: 'claim' vs 'admin').
- Double-claim race guard (conditional UPDATE).
- Unified ownership rule: the template rebuild never deletes assigned or
  admin-shaped auto shifts (the Aug 1/2/5/6 wipe incident).

Real in-memory ORM rows + TestClient with router-local auth overrides.
"""
from datetime import date as date_type, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import routers.roster as roster_module
from main import app
from db_models import (
    AuditLog,
    AuditLogEvent,
    EmployeeHoliday,
    RosterShift,
    ShiftStatus,
    ShiftType,
)
from routers.roster import (
    get_current_user as roster_get_current_user,
    require_admin as roster_require_admin,
)

DRIVER_ID = 21
OTHER_DRIVER_ID = 22


def _driver(user_id=DRIVER_ID, email="driver@tag.test"):
    return SimpleNamespace(
        id=user_id, email=email, is_admin=False, is_active=True,
        first_name="Test", last_name="Driver", driver_type="jockey",
    )


def _admin():
    return SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True, is_active=True,
        first_name="Ad", last_name="Min", driver_type=None,
    )


@pytest.fixture
def emails(monkeypatch):
    """Capture founder notifications instead of touching email_service."""
    sent = []
    monkeypatch.setattr(
        roster_module, "_notify_founder_roster_event",
        lambda subject, body: sent.append({"subject": subject, "body": body}),
    )
    return sent


@pytest.fixture
def client(db_session):
    app.dependency_overrides[roster_get_current_user] = _driver
    app.dependency_overrides[roster_require_admin] = _admin
    yield TestClient(app)
    app.dependency_overrides.pop(roster_get_current_user, None)
    app.dependency_overrides.pop(roster_require_admin, None)


def _add_users(db, *specs):
    for uid, first, last in specs:
        db.execute(text(
            "INSERT INTO users (id, email, first_name, last_name, is_admin, is_active, "
            "driver_type, preferred_shift_types, excluded_shift_types, preferred_days_off) "
            "VALUES (:id, :email, :fn, :ln, 0, 1, 'jockey', '{}', '{}', '{}')"
        ), {"id": uid, "email": f"{first.lower()}@tag.test", "fn": first, "ln": last})
    db.commit()


def _add_shift(db, *, staff_id=None, assigned_source=None, days_ahead=10,
               start=time(9, 0), end=time(13, 0), created_source="auto",
               status=ShiftStatus.SCHEDULED, admin_shaped_at=None, locked=False):
    shift = RosterShift(
        staff_id=staff_id,
        assigned_source=assigned_source,
        date=date_type.today() + timedelta(days=days_ahead),
        start_time=start,
        end_time=end,
        shift_type=ShiftType.MORNING,
        status=status,
        created_source=created_source,
        admin_shaped_at=admin_shaped_at,
        locked=locked,
    )
    db.add(shift)
    db.commit()
    return shift


def _audit_events(db, event):
    return db.query(AuditLog).filter(AuditLog.event == event).all()


# =============================================================================
# Claim: provenance + audit + email + race guard
# =============================================================================

class TestClaimHUEB:

    def test_H_claim_sets_provenance_audit_and_email(self, client, db_session, emails):
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session)

        response = client.post(f"/api/employee/claim-shift/{shift.id}")

        assert response.status_code == 200
        db_session.refresh(shift)
        assert shift.staff_id == DRIVER_ID
        assert shift.assigned_source == "claim"
        assert len(_audit_events(db_session, AuditLogEvent.ROSTER_SHIFT_CLAIMED)) == 1
        assert len(emails) == 1
        assert "claimed" in emails[0]["subject"].lower()

    def test_U_second_claim_loses_the_race(self, client, db_session, emails):
        """Conditional UPDATE guard: once staff_id is set, a second claim
        gets 400 even though its pre-checks read the shift as free."""
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"), (OTHER_DRIVER_ID, "Other", "Driver"))
        shift = _add_shift(db_session)

        assert client.post(f"/api/employee/claim-shift/{shift.id}").status_code == 200
        second = client.post(f"/api/employee/claim-shift/{shift.id}")

        assert second.status_code == 400
        db_session.refresh(shift)
        assert shift.staff_id == DRIVER_ID  # first winner kept
        assert len(emails) == 1  # loser sent no email

    def test_U_race_at_the_update_itself(self, client, db_session, emails):
        """Simulate the TOCTOU window: shift becomes assigned after the
        pre-checks would have passed — conditional UPDATE still refuses."""
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session, staff_id=OTHER_DRIVER_ID, assigned_source="claim")

        response = client.post(f"/api/employee/claim-shift/{shift.id}")

        assert response.status_code == 400
        db_session.refresh(shift)
        assert shift.staff_id == OTHER_DRIVER_ID


# =============================================================================
# Release: 72h uniform notice + audit + email
# =============================================================================

class TestReleaseHUEB:

    def test_H_release_with_notice_clears_and_notifies(self, client, db_session, emails):
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="claim", days_ahead=10)

        response = client.post(f"/api/employee/release-shift/{shift.id}")

        assert response.status_code == 200
        db_session.refresh(shift)
        assert shift.staff_id is None
        assert shift.assigned_source is None
        assert len(_audit_events(db_session, AuditLogEvent.ROSTER_SHIFT_RELEASED)) == 1
        assert len(emails) == 1
        assert "needs cover" in emails[0]["subject"].lower()

    def test_H_admin_assigned_shift_releases_under_same_rule(self, client, db_session, emails):
        """Owner decision: uniform notice — admin-assigned releases too."""
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="admin", days_ahead=10)

        assert client.post(f"/api/employee/release-shift/{shift.id}").status_code == 200
        assert len(emails) == 1

    def test_B_release_blocked_inside_notice_window(self, client, db_session, emails):
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="claim", days_ahead=2)

        response = client.post(f"/api/employee/release-shift/{shift.id}")

        assert response.status_code == 400
        assert "72 hours" in response.json()["detail"]
        db_session.refresh(shift)
        assert shift.staff_id == DRIVER_ID  # unchanged
        assert emails == []  # no notification on refusal

    def test_B_notice_window_env_boundaries(self, client, db_session, emails, monkeypatch):
        """Boundary either side of the env-configured line (1h notice):
        a shift 2h out releases, a shift 30min out is refused."""
        monkeypatch.setenv("ROSTER_RELEASE_NOTICE_HOURS", "1")
        now = datetime.utcnow()

        near = _add_shift(db_session, staff_id=DRIVER_ID, days_ahead=0,
                          start=(now + timedelta(minutes=30)).time())
        near.date = (now + timedelta(minutes=30)).date()
        far = _add_shift(db_session, staff_id=DRIVER_ID, days_ahead=0,
                         start=(now + timedelta(hours=2)).time())
        far.date = (now + timedelta(hours=2)).date()
        db_session.commit()

        assert client.post(f"/api/employee/release-shift/{near.id}").status_code == 400
        assert client.post(f"/api/employee/release-shift/{far.id}").status_code == 200

    def test_U_invalid_env_falls_back_to_72(self, monkeypatch):
        monkeypatch.setenv("ROSTER_RELEASE_NOTICE_HOURS", "plenty")
        assert roster_module._release_notice_hours() == 72.0
        monkeypatch.delenv("ROSTER_RELEASE_NOTICE_HOURS")
        assert roster_module._release_notice_hours() == 72.0


# =============================================================================
# Unavailability: 72h notice + audit + email
# =============================================================================

class TestUnavailabilityHUEB:

    def _post(self, client, start: date_type, end: date_type):
        fmt = "%d/%m/%Y"
        return client.post(
            "/api/employee/unavailability"
            f"?start_date={start.strftime(fmt)}&end_date={end.strftime(fmt)}"
        )

    def test_H_unavailability_with_notice_created_and_notified(self, client, db_session, emails):
        start = date_type.today() + timedelta(days=10)

        response = self._post(client, start, start + timedelta(days=3))

        assert response.status_code == 200
        assert db_session.query(EmployeeHoliday).count() == 1
        assert len(_audit_events(db_session, AuditLogEvent.STAFF_UNAVAILABILITY_ADDED)) == 1
        assert len(emails) == 1
        assert "unavailab" in emails[0]["subject"].lower()

    def test_B_unavailability_blocked_inside_notice(self, client, db_session, emails):
        """The Lee scenario: short-notice self-added time off is refused
        and routed through an administrator."""
        start = date_type.today() + timedelta(days=1)

        response = self._post(client, start, start + timedelta(days=4))

        assert response.status_code == 400
        assert "72 hours" in response.json()["detail"]
        assert db_session.query(EmployeeHoliday).count() == 0
        assert emails == []


# =============================================================================
# Admin provenance
# =============================================================================

class TestAdminProvenanceHUEB:

    def test_H_admin_unassign_clears_provenance(self, client, db_session):
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="claim")

        response = client.patch(f"/api/roster/{shift.id}/unassign")

        assert response.status_code == 200
        db_session.refresh(shift)
        assert shift.staff_id is None
        assert shift.assigned_source is None


# =============================================================================
# Unified ownership: template rebuild must not delete assigned/shaped shifts
# =============================================================================

class TestTemplateRebuildOwnershipHUEB:

    def test_H_rebuild_preserves_assigned_and_shaped_deletes_untouched(self, db_session, monkeypatch):
        """The Aug 1/2/5/6 incident: an assigned (unlocked) template shift and
        an admin-shaped one must survive a rebuild; the untouched unassigned
        one is fair game."""
        from auto_roster import _rebuild_window_auto_for_dates
        from roster_planner import PlannerSettings

        target = date_type.today() + timedelta(days=20)
        assigned = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="admin",
                              days_ahead=20, start=time(3, 30), end=time(10, 30))
        shaped = _add_shift(db_session, days_ahead=20, start=time(10, 30), end=time(18, 30),
                            admin_shaped_at=datetime.now(timezone.utc))
        untouched = _add_shift(db_session, days_ahead=20, start=time(18, 30), end=time(23, 0))
        locked = _add_shift(db_session, days_ahead=20, start=time(2, 0), end=time(3, 0), locked=True)

        settings = PlannerSettings.from_kv({})
        summary = _rebuild_window_auto_for_dates(db_session, [target], settings)

        remaining = {s.id for s in db_session.query(RosterShift).all()}
        assert assigned.id in remaining
        assert shaped.id in remaining
        assert locked.id in remaining
        assert untouched.id not in remaining
        assert summary["deleted"] == 1


# =============================================================================
# Phase 4: needs-cover lifecycle (release stamps, any assignment clears)
# =============================================================================

class TestNeedsCoverHUEB:

    def test_H_release_stamps_needs_cover(self, client, db_session, emails):
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="claim", days_ahead=10)

        assert client.post(f"/api/employee/release-shift/{shift.id}").status_code == 200

        db_session.refresh(shift)
        assert shift.needs_cover_at is not None

    def test_H_claim_clears_needs_cover(self, client, db_session, emails):
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session)
        shift.needs_cover_at = datetime.utcnow()
        db_session.commit()

        assert client.post(f"/api/employee/claim-shift/{shift.id}").status_code == 200

        db_session.refresh(shift)
        assert shift.needs_cover_at is None

    def test_H_admin_unassign_does_not_stamp(self, client, db_session):
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="admin")

        assert client.patch(f"/api/roster/{shift.id}/unassign").status_code == 200

        db_session.refresh(shift)
        assert shift.needs_cover_at is None

    def test_H_serializer_exposes_needs_cover(self, client, db_session, emails):
        _add_users(db_session, (DRIVER_ID, "Test", "Driver"))
        shift = _add_shift(db_session, staff_id=DRIVER_ID, assigned_source="claim", days_ahead=10)
        client.post(f"/api/employee/release-shift/{shift.id}")

        body = client.get(f"/api/roster/{shift.id}").json()

        assert body["needs_cover_at"] is not None
