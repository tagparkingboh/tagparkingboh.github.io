"""
Unit + integration tests for the new `accepted` field on vehicle_inspections.

Background: prior to 2026-05-18 the return inspection UI had a "Customer
Declined Inspection" checkbox bound to the boolean column `declined`. The
new UI flips to positive framing — "Customer accepted return inspection",
ticked by default — and persists to a new nullable column `accepted`.
The legacy `declined` column is preserved for historical records.

Test scope (per backend/docs/SPEC.md test conventions — TestClient + import-
from-main integration tests count toward coverage; unit tests document):

Unit tests (logic-only):
  - Defaults: new VehicleInspection rows have accepted=None until set.
  - Setting accepted=True doesn't touch declined (they're independent fields).
  - Setting accepted=False doesn't touch declined.

Integration tests (TestClient + monkeypatched DB):
  - POST /api/employee/inspections with accepted=True returns 200 and the
    response carries accepted: true.
  - POST with accepted=False does the same and stores False.
  - POST without `accepted` in the body (legacy clients) stores NULL.
  - PUT /api/employee/inspections/{id} can update accepted independently
    of declined.
  - GET /api/employee/inspections/{booking_id} returns the accepted field.
  - Drop-off (dropoff) inspections leave accepted untouched.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import VehicleInspection, InspectionType


# =============================================================================
# Helpers
# =============================================================================

def _mock_user():
    u = MagicMock()
    u.id = 42
    u.email = "employee@tag.test"
    u.role = "employee"
    return u


def _override_auth(user=None):
    from main import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user or _mock_user()


def _mock_booking(id=1, reference="TAG-ACC0001"):
    b = MagicMock()
    b.id = id
    b.reference = reference
    return b


def _mock_inspection_row(id=99, accepted=None, declined=False, inspection_type=InspectionType.PICKUP):
    insp = MagicMock(spec=VehicleInspection)
    insp.id = id
    insp.booking_id = 1
    insp.inspection_type = inspection_type
    insp.notes = None
    insp.photos = None
    insp.customer_name = None
    insp.signed_date = None
    insp.signature = None
    insp.vehicle_inspection_read = False
    insp.acknowledgement_confirmed = False
    insp.declined = declined
    insp.accepted = accepted
    insp.mileage = 12345
    insp.inspector_id = 42
    insp.created_at = datetime(2026, 5, 18, 10, 0, 0)
    insp.updated_at = None
    return insp


def _wire_create_endpoint(existing_inspection=None, booking=None):
    """Standard DB wiring for the create-inspection path:
       - booking lookup → booking (or _mock_booking())
       - existing inspection check (uq_inspection_booking_type) → existing or None
       - db.add() captures the new row; db.commit() / refresh() noop
       Returns (db, added_rows_list).
    """
    db = MagicMock()
    booking = booking or _mock_booking()
    added = []

    def _query(model):
        q = MagicMock()
        # Booking lookup
        if model.__name__ == "Booking" or "Booking" in str(model):
            q.filter.return_value.first.return_value = booking
            return q
        # VehicleInspection: existing check uses .filter().first()
        q.filter.return_value.first.return_value = existing_inspection
        q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = _query
    db.add.side_effect = lambda r: added.append(r)
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.refresh = MagicMock(side_effect=lambda r: setattr(r, "id", 7) if not getattr(r, "id", None) else None)
    return db, added


def _override_db(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


# =============================================================================
# Unit tests — model defaults + independence of accepted vs declined
# =============================================================================

class TestModelDefaults:
    def test_new_inspection_has_accepted_none_by_default(self):
        insp = VehicleInspection(booking_id=1, inspection_type=InspectionType.PICKUP)
        # On a fresh in-memory instance (never persisted), the column default
        # of None applies — `accepted` is genuinely unset.
        assert insp.accepted is None

    def test_setting_accepted_true_does_not_change_declined(self):
        insp = VehicleInspection(booking_id=1, inspection_type=InspectionType.PICKUP, declined=False)
        insp.accepted = True
        assert insp.accepted is True
        assert insp.declined is False

    def test_setting_accepted_false_does_not_change_declined(self):
        insp = VehicleInspection(booking_id=1, inspection_type=InspectionType.PICKUP, declined=True)
        insp.accepted = False
        assert insp.accepted is False
        assert insp.declined is True  # legacy field untouched

    def test_dropoff_inspection_leaves_accepted_none(self):
        """Drop-off inspections shouldn't set accepted at all — kept NULL."""
        insp = VehicleInspection(booking_id=1, inspection_type=InspectionType.DROPOFF)
        assert insp.accepted is None


# =============================================================================
# Integration tests — POST /api/employee/inspections (create)
# =============================================================================

class TestCreateInspectionWithAccepted:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_create_pickup_with_accepted_true(self):
        db, added = _wire_create_endpoint()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1,
            "inspection_type": "pickup",
            "mileage": 54321,
            "accepted": True,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["inspection"]["accepted"] is True
        assert body["inspection"]["inspection_type"] == "pickup"

        # The row added to the DB has accepted=True too.
        assert len(added) == 1
        assert added[0].accepted is True
        assert added[0].declined is False  # default — not flipped

    def test_create_pickup_with_accepted_false(self):
        db, added = _wire_create_endpoint()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1,
            "inspection_type": "pickup",
            "mileage": 54321,
            "accepted": False,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["inspection"]["accepted"] is False
        assert added[0].accepted is False

    def test_create_without_accepted_field_stores_null(self):
        """Legacy/dropoff clients omit `accepted` entirely; should store NULL."""
        db, added = _wire_create_endpoint()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1,
            "inspection_type": "pickup",
            "mileage": 54321,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["inspection"]["accepted"] is None
        assert added[0].accepted is None

    def test_dropoff_inspection_accepts_request_but_stores_null(self):
        """Drop-off requests don't carry `accepted`; verify nothing odd happens."""
        db, added = _wire_create_endpoint()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1,
            "inspection_type": "dropoff",
            "mileage": 100,
            "customer_name": "Test",
            "signed_date": "2026-05-18",
            "signature": "data:image/png;base64,xxx",
            "vehicle_inspection_read": True,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["inspection"]["accepted"] is None

    def test_accepted_and_declined_are_independent_on_create(self):
        """Sending both fields persists both — they don't override each other."""
        db, added = _wire_create_endpoint()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).post("/api/employee/inspections", json={
            "booking_id": 1,
            "inspection_type": "pickup",
            "mileage": 54321,
            "accepted": True,
            "declined": False,
        })
        assert resp.status_code == 200, resp.text
        assert added[0].accepted is True
        assert added[0].declined is False


# =============================================================================
# Integration tests — PUT /api/employee/inspections/{id} (update)
# =============================================================================

class TestUpdateInspectionWithAccepted:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_update_accepted_independently_of_declined(self):
        # Existing row with declined=True (legacy) — we toggle accepted=True
        # and the API must not alter declined.
        existing = _mock_inspection_row(accepted=None, declined=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).put("/api/employee/inspections/99", json={
            "accepted": True,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["inspection"]["accepted"] is True
        # The on-row `declined` must remain True (we didn't touch it).
        assert existing.declined is True
        assert existing.accepted is True

    def test_update_can_set_accepted_to_false(self):
        existing = _mock_inspection_row(accepted=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).put("/api/employee/inspections/99", json={"accepted": False})
        assert resp.status_code == 200, resp.text
        assert existing.accepted is False
        assert resp.json()["inspection"]["accepted"] is False

    def test_update_without_accepted_leaves_it_unchanged(self):
        """Omitting `accepted` in PUT body is the canonical 'don't touch' signal."""
        existing = _mock_inspection_row(accepted=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.commit = MagicMock()
        db.refresh = MagicMock()
        _override_db(db)
        _override_auth()

        resp = TestClient(app).put("/api/employee/inspections/99", json={"notes": "test"})
        assert resp.status_code == 200, resp.text
        # Untouched.
        assert existing.accepted is True


# =============================================================================
# Integration tests — GET /api/employee/inspections/{booking_id}
# =============================================================================

class TestGetInspectionExposesAccepted:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_get_returns_accepted_field(self):
        insp = _mock_inspection_row(accepted=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [insp]
        _override_db(db)
        _override_auth()

        resp = TestClient(app).get("/api/employee/inspections/1")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["inspections"]
        assert len(rows) == 1
        assert rows[0]["accepted"] is True

    def test_get_returns_null_accepted_for_historical_row(self):
        """Pre-migration rows have accepted=NULL — must serialise as null, not False."""
        insp = _mock_inspection_row(accepted=None, declined=False)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [insp]
        _override_db(db)
        _override_auth()

        resp = TestClient(app).get("/api/employee/inspections/1")
        assert resp.status_code == 200, resp.text
        rows = resp.json()["inspections"]
        assert rows[0]["accepted"] is None
        # And `declined` still defaults to False on historical rows.
        assert rows[0]["declined"] is False
