"""
HUEB tests for the auto-roster trigger on PUT /api/admin/bookings/{id}.

Locked 2026-05-21: editing arrival/pickup/dropoff date or time on Admin →
Edit Booking must now ALSO schedule `auto_create_or_extend_async` as a
BackgroundTask (alongside the existing shadow-planner fire-engine task) so
the live shift cards reflect the change immediately instead of staying
stale until the next regenerate-auto run.

The trigger field set is:
  dropoff_date, dropoff_time,
  pickup_date, pickup_time,
  flight_arrival_time, flight_arrival_date

Customer-detail-only edits (airline name, flight number, origin) must NOT
fire either task — the shadow planner is expensive and the auto-roster
rebuild is unnecessary when the booking's event times don't move.

Per SPEC.md: TestClient(app) + import-from-main, MagicMock for the DB so
these execute the real endpoint and count for coverage.
"""
from datetime import date as date_type, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app, require_admin
from database import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _admin():
    return SimpleNamespace(id=1, email="admin@tag.test", is_admin=True)


def _booking(**overrides):
    from db_models import BookingStatus
    base = dict(
        id=99,
        reference="TAG-EDIT0001",
        status=BookingStatus.CONFIRMED,
        # Drop-off
        dropoff_date=date_type(2026, 6, 1),
        dropoff_time=time(10, 0),
        dropoff_destination="Tenerife",
        dropoff_airline_name="TUI Airways",
        dropoff_flight_number="TOM1234",
        flight_departure_time=time(12, 0),
        # Pickup / arrival
        pickup_date=date_type(2026, 6, 8),
        pickup_time=time(15, 30),
        flight_arrival_date=date_type(2026, 6, 8),
        flight_arrival_time=time(15, 0),
        pickup_origin="Tenerife",
        pickup_airline_name="TUI Airways",
        pickup_flight_number="TOM1235",
        arrival_id=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def captured(monkeypatch):
    """Capture the BackgroundTask schedule calls + audit-log writes.

    - `fire_engine_async` (shadow planner) and `auto_create_or_extend_async`
      (live auto-roster) get patched to record their invocation.
    - `log_audit_event` (booking_updated diff) gets patched to record the
      event_data so tests can assert on the before/after diff shape.

    The test assertions then check what the endpoint fired.
    """
    state = {
        "shadow_planner_called": 0,
        "auto_roster_called": 0,
        "auto_roster_booking_id": None,
        "audit_events": [],  # list of (event, event_data) tuples
    }

    def _shadow(*args, **kwargs):
        state["shadow_planner_called"] += 1

    def _auto(booking_id, *args, **kwargs):
        state["auto_roster_called"] += 1
        state["auto_roster_booking_id"] = booking_id

    def _audit(*args, **kwargs):
        state["audit_events"].append((
            kwargs.get("event"),
            kwargs.get("event_data") or {},
        ))

    monkeypatch.setattr("roster_planner_runner.fire_engine_async", _shadow)
    monkeypatch.setattr("auto_roster.auto_create_or_extend_async", _auto)
    monkeypatch.setattr("main.log_audit_event", _audit)
    return state


def _wire(db_booking):
    """Mount a MagicMock DB returning `db_booking` for any Booking query."""
    db = MagicMock()
    chain = MagicMock()
    chain.options.return_value = chain
    chain.filter.return_value = chain
    chain.first.return_value = db_booking
    db.query.return_value = chain
    db.commit = MagicMock()
    db.refresh = MagicMock()

    def gen():
        yield db

    app.dependency_overrides[get_db] = gen
    app.dependency_overrides[require_admin] = lambda: _admin()
    return db


def _clear():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# H/U/E/B coverage
# ---------------------------------------------------------------------------

class TestUpdateBookingTriggersAutoRoster:
    def teardown_method(self):
        _clear()

    # --- HAPPY ----------------------------------------------------------------

    def test_H_flight_arrival_time_change_schedules_both_tasks(self, captured):
        """Editing arrival time is the canonical event-moving field: shadow
        planner runs AND the live auto-roster rebuild fires for this booking."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"flight_arrival_time": "16:00"},
        )
        assert resp.status_code == 200, resp.text
        assert "flight_arrival_time" in resp.json()["fields_updated"]
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1
        assert captured["auto_roster_booking_id"] == b.id

    # --- UNHAPPY --------------------------------------------------------------

    def test_U_customer_detail_only_edit_does_not_fire_tasks(self, captured):
        """Renaming an airline / changing a flight number doesn't move any
        event in time — neither the shadow planner nor the auto-roster
        rebuild should run. Wasteful otherwise."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={
                "pickup_airline_name": "Jet2",
                "pickup_flight_number": "LS999",
                "pickup_origin": "Palma",
            },
        )
        assert resp.status_code == 200, resp.text
        assert captured["shadow_planner_called"] == 0
        assert captured["auto_roster_called"] == 0

    def test_U_no_fields_to_update_returns_400_no_tasks(self, captured):
        """Empty PATCH body fails before reaching the trigger block — no
        BackgroundTask schedule, no DB commit."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={},
        )
        assert resp.status_code == 400
        assert captured["shadow_planner_called"] == 0
        assert captured["auto_roster_called"] == 0

    # --- EDGE -----------------------------------------------------------------

    def test_E_flight_arrival_date_only_change_fires_tasks(self, captured):
        """flight_arrival_date is the new field added 2026-05-20; updating
        ONLY this (e.g. correcting an overnight roll on a legacy row) must
        still trigger both roster tasks — without this case the trigger set
        would miss the new column and the shift cards would stay stale."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"flight_arrival_date": "2026-06-07"},  # back-date by one day
        )
        assert resp.status_code == 200, resp.text
        assert "flight_arrival_date" in resp.json()["fields_updated"]
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1

    def test_E_multiple_fields_fire_tasks_once_each(self, captured):
        """A PATCH that touches multiple trigger fields must schedule each
        background task exactly once — not once per modified field."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={
                "flight_arrival_time": "16:00",
                "flight_arrival_date": "2026-06-07",
                "pickup_date": "2026-06-08",
            },
        )
        assert resp.status_code == 200, resp.text
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1

    # --- BOUNDARY -------------------------------------------------------------

    def test_B_pickup_date_alone_still_triggers(self, captured):
        """pickup_date was in the legacy trigger set pre-2026-05-20. The
        2026-05-21 refactor must not have dropped it from the new list —
        this is the regression guard."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"pickup_date": "2026-06-09"},
        )
        assert resp.status_code == 200, resp.text
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1

    def test_B_dropoff_time_alone_still_triggers(self, captured):
        """dropoff_time was likewise in the legacy set. Boundary check that
        the drop-off side is still wired to the rebuild trigger."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"dropoff_time": "11:15"},
        )
        assert resp.status_code == 200, resp.text
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1

    def test_B_pickup_time_alone_still_triggers(self, captured):
        """pickup_time edits (admin manual override of handoff moment, even
        though the auto-roster derives this from arrival now) still move an
        event in the engine's view — must fire the rebuild."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"pickup_time": "16:00"},
        )
        assert resp.status_code == 200, resp.text
        assert captured["shadow_planner_called"] == 1
        assert captured["auto_roster_called"] == 1


# ===========================================================================
# Audit logging — every successful PUT must write a booking_updated row
# with the field-change diff. Diagnosed via the TAG-KNL95826 2026-05-21
# incident (no audit existed → couldn't tell what each save changed).
# ===========================================================================

class TestUpdateBookingAuditLog:
    def teardown_method(self):
        _clear()

    # --- HAPPY ---------------------------------------------------------------

    def test_H_audit_row_written_with_field_diff(self, captured):
        """A successful PATCH writes exactly one booking_updated audit event
        containing the booking_id, fields_updated, before, and after."""
        from db_models import AuditLogEvent
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"flight_arrival_date": "2026-06-07"},
        )
        assert resp.status_code == 200, resp.text
        assert len(captured["audit_events"]) == 1, captured["audit_events"]
        event, data = captured["audit_events"][0]
        assert event == AuditLogEvent.BOOKING_UPDATED
        assert data["booking_id"] == b.id
        assert "flight_arrival_date" in data["fields_updated"]
        # Before snapshot reflects the row at PATCH entry
        assert data["before"]["flight_arrival_date"] == "2026-06-08"
        # After snapshot reflects the committed row
        assert data["after"]["flight_arrival_date"] == "2026-06-07"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_empty_patch_does_not_write_audit_row(self, captured):
        """Empty PATCH body 400s before the audit log step — no row should
        be written, otherwise the audit table fills with no-op churn."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={},
        )
        assert resp.status_code == 400
        assert captured["audit_events"] == []

    # --- EDGE ----------------------------------------------------------------

    def test_E_customer_detail_only_edit_still_writes_audit(self, captured):
        """Non-roster fields (airline name etc.) don't fire the background
        tasks but DO write an audit row — the admin still made a change to
        the row and we want the trail."""
        from db_models import AuditLogEvent
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={"pickup_airline_name": "Jet2", "pickup_origin": "Palma"},
        )
        assert resp.status_code == 200, resp.text
        assert len(captured["audit_events"]) == 1
        event, data = captured["audit_events"][0]
        assert event == AuditLogEvent.BOOKING_UPDATED
        # fields_updated reflects the customer-detail-only edit
        assert set(data["fields_updated"]) == {"pickup_airline_name", "pickup_origin"}
        # Background tasks NOT fired (roster trigger checked separately above)
        assert captured["shadow_planner_called"] == 0
        assert captured["auto_roster_called"] == 0

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_multi_field_diff_only_lists_changed_fields(self, captured):
        """When several fields change at once, before/after dicts contain
        exactly those keys — no untouched fields leak into the diff (keeps
        the audit row compact and the diff actionable)."""
        b = _booking()
        _wire(b)
        resp = TestClient(app).put(
            f"/api/admin/bookings/{b.id}",
            json={
                "flight_arrival_date": "2026-06-07",
                "flight_arrival_time": "23:30",
                "pickup_date": "2026-06-08",
            },
        )
        assert resp.status_code == 200, resp.text
        assert len(captured["audit_events"]) == 1
        _, data = captured["audit_events"][0]
        expected = {"flight_arrival_date", "flight_arrival_time", "pickup_date", "pickup_time"}
        # pickup_time recalculates as a side-effect of changing flight_arrival_time
        assert set(data["fields_updated"]) == expected
        assert set(data["before"].keys()) == expected
        assert set(data["after"].keys()) == expected
        # Sanity: every key in `after` reflects the new value
        assert data["after"]["flight_arrival_date"] == "2026-06-07"
        assert data["after"]["flight_arrival_time"] == "23:30"
        assert data["after"]["pickup_date"] == "2026-06-08"
