"""
HUEB integration tests for routers/roster.py — targets the largest
uncovered handler blocks per coverage --show-missing output.

Endpoints covered:
  PUT    /api/roster/{shift_id}   (update_shift — 1319-1422, ~100 lines)
  DELETE /api/roster/{shift_id}   (delete_shift — small but bracketed)
  GET    /api/holidays            (list_holidays + filters)
  GET    /api/holidays/for-date
  GET    /api/holidays/{id}
  POST   /api/holidays            (create_holiday — 2862-2956, ~90 lines)

Hits the real FastAPI routes via TestClient. Auth + DB are overridden
via app.dependency_overrides on routers.roster.get_current_user /
require_admin (these are router-local, not main.py's versions).
"""
from datetime import date, date as date_type, datetime, time, timedelta
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app
from database import get_db
from routers.roster import (
    build_roster_review_generate_gate,
    get_current_user as roster_get_current_user,
    require_admin as roster_require_admin,
    shift_to_response,
)
from db_models import AuditLogEvent, ShiftStatus, ShiftType, HolidayType, BookingStatus, ServiceType
from roster_planner import PlannerSettings, UK_TZ


# ============================================================================
# Helpers
# ============================================================================

def _admin():
    u = MagicMock()
    u.id = 1
    u.email = "admin@tag.test"
    u.is_admin = True
    u.driver_type = None
    return u


def _override_auth():
    app.dependency_overrides[roster_get_current_user] = lambda: _admin()
    app.dependency_overrides[roster_require_admin] = lambda: _admin()


def _override_db(db):
    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen


def _mock_shift(
    id=1,
    staff_id=2,
    date_=None,
    start_time=time(9, 0),
    end_time=time(17, 0),
    shift_type=None,
    status=None,
    booking_id=None,
    intended_driver_type="jockey",
    created_source="manual",
):
    s = MagicMock()
    s.id = id
    s.staff_id = staff_id
    s.booking_id = booking_id
    s.date = date_ or date_type(2026, 6, 15)
    s.end_date = s.date
    s.start_time = start_time
    s.end_time = end_time
    s.shift_type = shift_type or ShiftType.MORNING
    s.status = status or ShiftStatus.SCHEDULED
    s.notes = None
    s.intended_driver_type = intended_driver_type
    s.created_source = created_source
    s.planner_run_id = None
    s.admin_shaped_at = None
    s.locked = False
    s.suppressed_at = None
    s.suppressed_by_user_id = None
    s.suppression_reason = None
    s.created_at = datetime(2026, 5, 1, 9, 0, 0)
    s.updated_at = None
    s.bookings = []
    s.staff = None
    return s


def _mock_booking(
    id=99,
    reference="TAG-WARN999",
    dropoff_date=None,
    dropoff_time=None,
    pickup_date=None,
    pickup_time=None,
    flight_arrival_date=None,
    flight_arrival_time=None,
    status=BookingStatus.CONFIRMED,
    service_type=ServiceType.MEET_GREET,
):
    b = MagicMock()
    b.id = id
    b.reference = reference
    b.status = status
    b.service_type = service_type
    b.dropoff_date = dropoff_date
    b.dropoff_time = dropoff_time
    b.pickup_date = pickup_date
    b.pickup_time = pickup_time
    b.flight_arrival_date = flight_arrival_date
    b.flight_arrival_time = flight_arrival_time
    b.customer_first_name = "Test"
    b.customer_last_name = "Customer"
    b.dropoff_flight_number = None
    b.dropoff_destination = None
    b.pickup_flight_number = None
    b.pickup_origin = None
    return b


def _mock_staff(id=2, driver_type="jockey", is_active=True, is_admin=False):
    u = MagicMock()
    u.id = id
    u.email = f"staff{id}@tag.test"
    u.first_name = "Jock"
    u.last_name = "Ey"
    u.driver_type = driver_type
    u.is_active = is_active
    u.is_admin = is_admin
    return u


def _full_shift_response(s):
    """Build a RosterShiftResponse-shaped dict from a mock shift, so the
    response_model validator doesn't reject our stub."""
    return {
        "id": s.id,
        "staff_id": s.staff_id,
        "booking_id": s.booking_id,
        "bookings": [],
        "date": s.date.isoformat() if hasattr(s.date, "isoformat") else str(s.date),
        "end_date": (s.end_date.isoformat() if s.end_date and hasattr(s.end_date, "isoformat") else None),
        "start_time": s.start_time.strftime("%H:%M") if hasattr(s.start_time, "strftime") else str(s.start_time),
        "end_time": s.end_time.strftime("%H:%M") if hasattr(s.end_time, "strftime") else str(s.end_time),
        "shift_type": s.shift_type.value if hasattr(s.shift_type, "value") else str(s.shift_type),
        "status": s.status.value if hasattr(s.status, "value") else str(s.status),
        "notes": s.notes,
        "intended_driver_type": s.intended_driver_type or "jockey",
        "created_at": datetime(2026, 5, 1, 9, 0, 0).isoformat(),
    }


def _mock_holiday(id=1, staff_id=2, start=None, end=None, hol_type=None, start_t=None, end_t=None):
    h = MagicMock()
    h.id = id
    h.staff_id = staff_id
    h.start_date = start or date_type(2026, 7, 1)
    h.end_date = end or date_type(2026, 7, 7)
    h.start_time = start_t
    h.end_time = end_t
    h.holiday_type = hol_type or HolidayType.HOLIDAY
    h.notes = None
    h.created_by = "admin@tag.test"
    h.created_at = datetime(2026, 5, 1, 9, 0, 0)
    h.updated_at = None
    return h


def _planner_settings():
    return PlannerSettings.from_kv({
        "gap_max_minutes": 150,
        "mixed_gap_max_minutes": 150,
        "start_buffer_minutes": 30,
        "end_buffer_minutes": 15,
        "min_shift_minutes": 60,
    })


# ============================================================================
# Roster Review Generate Gate — HUEB
# ============================================================================

class TestRosterReviewGenerateGate:
    def test_happy_review_exists_without_suppression_allows_generate(self):
        booking = _mock_booking(
            id=1,
            reference="TAG-GENERATE",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
        )

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [],
            [],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["blocked_by_suppressed"] is False
        assert gate["can_generate_roster"] is True
        assert gate["missing_events"][0]["booking_reference"] == "TAG-GENERATE"

    def test_happy_null_service_type_booking_still_allows_generate(self):
        booking = _mock_booking(
            id=7,
            reference="TAG-LEGACY",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
            service_type=None,
        )

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [],
            [],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["can_generate_roster"] is True

    def test_edge_same_day_dropoff_link_does_not_hide_pickup_review(self):
        booking = _mock_booking(
            id=8,
            reference="TAG-SAMEDAY",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
            pickup_date=date_type(2026, 7, 5),
            pickup_time=time(18, 0),
            flight_arrival_date=date_type(2026, 7, 5),
            flight_arrival_time=time(17, 30),
        )
        dropoff_shift = _mock_shift(
            id=7008,
            staff_id=7,
            date_=date_type(2026, 7, 5),
            start_time=time(10, 10),
            end_time=time(11, 10),
            created_source="auto",
        )
        dropoff_shift.bookings = [booking]

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [dropoff_shift],
            [],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["missing_events"][0]["event_type"] == "pick_up"
        assert gate["can_generate_roster"] is True

    def test_unhappy_suppressed_shift_retaining_missing_booking_hides_generate(self):
        booking = _mock_booking(
            id=2,
            reference="TAG-SUPPRESSED",
            pickup_date=date_type(2026, 6, 21),
            pickup_time=time(23, 30),
            flight_arrival_date=date_type(2026, 6, 21),
            flight_arrival_time=time(23, 0),
        )
        suppressed = _mock_shift(
            id=5408,
            staff_id=None,
            date_=date_type(2026, 6, 21),
            start_time=time(22, 15),
            end_time=time(23, 55),
            status=ShiftStatus.CANCELLED,
            created_source="auto",
        )
        suppressed.suppressed_at = datetime(2026, 6, 9, 17, 59)
        suppressed.bookings = [booking]

        gate = build_roster_review_generate_gate(
            date_type(2026, 6, 21),
            [booking],
            [],
            [suppressed],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["blocked_by_suppressed"] is True
        assert gate["suppressed_shift_ids"] == [5408]
        assert gate["can_generate_roster"] is False

    def test_edge_suppressed_window_covering_required_cluster_hides_generate(self):
        booking = _mock_booking(
            id=3,
            reference="TAG-WINDOW",
            dropoff_date=date_type(2026, 6, 17),
            dropoff_time=time(14, 35),
        )
        suppressed = _mock_shift(
            id=5422,
            staff_id=None,
            date_=date_type(2026, 6, 17),
            start_time=time(14, 0),
            end_time=time(15, 45),
            status=ShiftStatus.CANCELLED,
            created_source="auto",
        )
        suppressed.suppressed_at = datetime(2026, 6, 10, 4, 53)
        suppressed.bookings = []

        gate = build_roster_review_generate_gate(
            date_type(2026, 6, 17),
            [booking],
            [],
            [suppressed],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["suppressed_shift_ids"] == [5422]
        assert gate["can_generate_roster"] is False

    def test_edge_overnight_suppressed_shift_without_end_date_hides_generate(self):
        booking = _mock_booking(
            id=9,
            reference="TAG-OVERNIGHT",
            pickup_date=date_type(2026, 7, 6),
            pickup_time=time(0, 45),
            flight_arrival_date=date_type(2026, 7, 6),
            flight_arrival_time=time(0, 15),
        )
        suppressed = _mock_shift(
            id=7009,
            staff_id=None,
            date_=date_type(2026, 7, 5),
            start_time=time(23, 30),
            end_time=time(1, 0),
            status=ShiftStatus.CANCELLED,
            created_source="auto",
        )
        suppressed.end_date = None
        suppressed.suppressed_at = datetime(2026, 7, 1, 9, 0)

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [],
            [suppressed],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["suppressed_shift_ids"] == [7009]
        assert gate["can_generate_roster"] is False

    def test_boundary_nearby_suppressed_shift_that_does_not_cover_cluster_allows_generate(self):
        booking = _mock_booking(
            id=4,
            reference="TAG-NEARBY",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
        )
        suppressed = _mock_shift(
            id=6000,
            staff_id=None,
            date_=date_type(2026, 7, 5),
            start_time=time(8, 0),
            end_time=time(9, 0),
            status=ShiftStatus.CANCELLED,
            created_source="auto",
        )
        suppressed.suppressed_at = datetime(2026, 7, 1, 9, 0)
        suppressed.bookings = []

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [],
            [suppressed],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 1
        assert gate["blocked_by_suppressed"] is False
        assert gate["can_generate_roster"] is True

    def test_boundary_no_review_means_no_generate(self):
        booking = _mock_booking(
            id=5,
            reference="TAG-LINKED",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
        )
        live_shift = _mock_shift(
            id=7000,
            staff_id=7,
            date_=date_type(2026, 7, 5),
            start_time=time(10, 10),
            end_time=time(11, 10),
            created_source="auto",
        )
        live_shift.bookings = [booking]

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [live_shift],
            [],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 0
        assert gate["can_generate_roster"] is False

    def test_edge_park_and_ride_booking_is_not_a_review_event(self):
        booking = _mock_booking(
            id=6,
            reference="TAG-PARKRIDE",
            dropoff_date=date_type(2026, 7, 5),
            dropoff_time=time(10, 40),
            service_type=ServiceType.PARK_RIDE,
        )

        gate = build_roster_review_generate_gate(
            date_type(2026, 7, 5),
            [booking],
            [],
            [],
            _planner_settings(),
        )

        assert gate["missing_review_count"] == 0
        assert gate["can_generate_roster"] is False


class TestRosterReviewGenerateGateRoutes:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_integration_get_gate_returns_backend_decision(self, monkeypatch):
        expected = {
            "date": "2026-07-05",
            "missing_review_count": 5,
            "blocked_by_suppressed": False,
            "suppressed_blocker_count": 0,
            "suppressed_shift_ids": [],
            "suppressed_booking_references": [],
            "can_generate_roster": True,
            "missing_events": [],
        }
        monkeypatch.setattr("routers.roster._load_roster_review_generate_gate", lambda db, d: expected)
        _override_db(MagicMock())

        resp = TestClient(app).get("/api/admin/roster/review-generate-gate?date=2026-07-05")

        assert resp.status_code == 200
        assert resp.json() == expected

    def test_integration_get_gate_range_returns_backend_decisions(self, monkeypatch):
        calls = []

        def fake_gate(db, d):
            calls.append(d)
            return {
                "date": d.isoformat(),
                "missing_review_count": 1 if d == date_type(2026, 7, 14) else 0,
                "blocked_by_suppressed": False,
                "suppressed_blocker_count": 0,
                "suppressed_shift_ids": [],
                "suppressed_booking_references": [],
                "can_generate_roster": d == date_type(2026, 7, 14),
                "missing_events": [{
                    "booking_id": 804,
                    "booking_reference": "TAG-WLJ80128",
                    "event_type": "pick_up",
                    "event_time": "18:00",
                }] if d == date_type(2026, 7, 14) else [],
            }

        monkeypatch.setattr("routers.roster._load_roster_review_generate_gate", fake_gate)
        _override_db(MagicMock())

        resp = TestClient(app).get(
            "/api/admin/roster/review-generate-gates?date_from=2026-07-13&date_to=2026-07-14"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["date_from"] == "2026-07-13"
        assert body["date_to"] == "2026-07-14"
        assert [g["date"] for g in body["gates"]] == ["2026-07-13", "2026-07-14"]
        assert body["gates"][1]["missing_events"][0]["booking_reference"] == "TAG-WLJ80128"
        assert calls == [date_type(2026, 7, 13), date_type(2026, 7, 14)]

    def test_integration_get_gate_range_rejects_inverted_dates(self):
        _override_db(MagicMock())

        resp = TestClient(app).get(
            "/api/admin/roster/review-generate-gates?date_from=2026-07-14&date_to=2026-07-13"
        )

        assert resp.status_code == 422

    def test_integration_dry_run_auto_sweep_returns_backend_report(self, monkeypatch):
        calls = {}
        expected = {
            "write": False,
            "date_from": "2026-07-05",
            "date_to": "2026-07-05",
            "dates_scanned": 1,
            "clusters_missing_coverage": 1,
            "clusters_would_generate": 1,
            "clusters_skipped_suppressed": 0,
            "clusters_skipped_owned_coverage": 0,
            "focus_rebuild_count": 1,
            "dates": [{
                "date": "2026-07-05",
                "missing_review_count": 5,
                "cluster_count": 1,
                "would_generate_count": 1,
                "skipped_suppressed_count": 0,
                "skipped_owned_coverage_count": 0,
                "clusters": [],
            }],
        }

        def fake_dry_run(db, date_from, date_to, settings):
            calls["date_from"] = date_from
            calls["date_to"] = date_to
            calls["settings"] = settings
            return expected

        monkeypatch.setattr("routers.roster._load_planner_settings_rows", lambda db: {})
        monkeypatch.setattr("auto_roster.dry_run_auto_roster_sweep", fake_dry_run)
        _override_db(MagicMock())

        resp = TestClient(app).get(
            "/api/admin/qa/roster-planner/auto-sweep/dry-run?date_from=2026-07-05&date_to=2026-07-05"
        )

        assert resp.status_code == 200
        assert resp.json() == expected
        assert calls["date_from"] == date_type(2026, 7, 5)
        assert calls["date_to"] == date_type(2026, 7, 5)

    def test_integration_dry_run_auto_sweep_rejects_inverted_dates(self):
        _override_db(MagicMock())

        resp = TestClient(app).get(
            "/api/admin/qa/roster-planner/auto-sweep/dry-run?date_from=2026-07-06&date_to=2026-07-05"
        )

        assert resp.status_code == 422

    def test_integration_dry_run_auto_sweep_rejects_large_ranges(self):
        _override_db(MagicMock())

        resp = TestClient(app).get(
            "/api/admin/qa/roster-planner/auto-sweep/dry-run?date_from=2026-07-01&date_to=2026-09-15"
        )

        assert resp.status_code == 422

    def test_integration_post_generate_runs_only_when_gate_allows(self, monkeypatch):
        calls = {"gate": 0, "rebuild_dates": None}
        before = {
            "date": "2026-07-05",
            "missing_review_count": 5,
            "blocked_by_suppressed": False,
            "suppressed_blocker_count": 0,
            "suppressed_shift_ids": [],
            "suppressed_booking_references": [],
            "can_generate_roster": True,
            "missing_events": [],
        }
        after = {**before, "missing_review_count": 0, "can_generate_roster": False}

        def fake_gate(db, d):
            calls["gate"] += 1
            return before if calls["gate"] == 1 else after

        def fake_rebuild(db, dates, settings):
            calls["rebuild_dates"] = dates
            return {"deleted": 2, "created": 3, "bookings_in_scope": 7, "skipped_suppressed": 0}

        monkeypatch.setattr("routers.roster._load_roster_review_generate_gate", fake_gate)
        monkeypatch.setattr("routers.roster._load_planner_settings_rows", lambda db: {})
        monkeypatch.setattr("auto_roster.rebuild_auto_for_dates", fake_rebuild)
        _override_db(MagicMock())

        resp = TestClient(app).post("/api/admin/roster/generate-date", json={"date": "2026-07-05"})

        assert resp.status_code == 200
        assert calls["rebuild_dates"] == {date_type(2026, 7, 5)}
        assert resp.json()["created"] == 3
        assert resp.json()["after_gate"]["missing_review_count"] == 0

    def test_integration_post_generate_returns_409_when_suppressed_blocks(self, monkeypatch):
        blocked = {
            "date": "2026-06-21",
            "missing_review_count": 2,
            "blocked_by_suppressed": True,
            "suppressed_blocker_count": 2,
            "suppressed_shift_ids": [5408, 5423],
            "suppressed_booking_references": ["TAG-LGG16579", "TAG-WTE58588"],
            "can_generate_roster": False,
            "missing_events": [],
        }
        rebuild = MagicMock()
        monkeypatch.setattr("routers.roster._load_roster_review_generate_gate", lambda db, d: blocked)
        monkeypatch.setattr("auto_roster.rebuild_auto_for_dates", rebuild)
        _override_db(MagicMock())

        resp = TestClient(app).post("/api/admin/roster/generate-date", json={"date": "2026-06-21"})

        assert resp.status_code == 409
        assert resp.json()["detail"]["gate"]["suppressed_shift_ids"] == [5408, 5423]
        rebuild.assert_not_called()


# ============================================================================
# shift_to_response — HUEB
# ============================================================================

class TestShiftToResponseBookingStatus:
    def test_happy_cancelled_many_to_many_booking_is_hidden(self):
        active = _mock_booking(
            id=10,
            reference="TAG-ACTIVE",
            dropoff_date=date_type(2026, 6, 15),
            dropoff_time=time(9, 30),
            status=BookingStatus.CONFIRMED,
        )
        cancelled = _mock_booking(
            id=11,
            reference="TAG-CANCELLED",
            dropoff_date=date_type(2026, 6, 15),
            dropoff_time=time(10, 30),
            status=BookingStatus.CANCELLED,
        )
        shift = _mock_shift(
            id=99,
            date_=date_type(2026, 6, 15),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        shift.bookings = [active, cancelled]

        response = shift_to_response(shift, MagicMock())

        assert [booking.reference for booking in response.bookings] == ["TAG-ACTIVE"]
        assert response.booking_reference == "TAG-ACTIVE"

    def test_unhappy_cancelled_legacy_booking_id_is_hidden(self):
        cancelled = _mock_booking(
            id=11,
            reference="TAG-CANCELLED",
            dropoff_date=date_type(2026, 6, 15),
            dropoff_time=time(10, 30),
            status=BookingStatus.CANCELLED,
        )
        shift = _mock_shift(
            id=99,
            booking_id=cancelled.id,
            date_=date_type(2026, 6, 15),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        shift.bookings = []
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = cancelled

        response = shift_to_response(shift, db)

        assert response.bookings == []
        assert response.booking_reference is None

    def test_boundary_admin_shaped_timestamp_is_exposed_for_auto_shift_ui(self):
        shaped_at = datetime(2026, 6, 9, 10, 15, 0)
        shift = _mock_shift(
            id=100,
            date_=date_type(2026, 6, 15),
            start_time=time(8, 0),
            end_time=time(12, 0),
            created_source="auto",
        )
        shift.admin_shaped_at = shaped_at

        response = shift_to_response(shift, MagicMock())

        assert response.created_source == "auto"
        assert response.admin_shaped_at == shaped_at


# ============================================================================
# PUT /api/roster/{shift_id} — HUEB
# ============================================================================

class TestUpdateShift:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, shift=None, staff=None, conflicting_shift=None, unavail=None, booking=None):
        """Build a Session that returns specific things for each model query.
        update_shift queries: RosterShift (shift lookup), User (assigned staff),
        Booking (booking_ids validation), ShiftBookingLink (delete), and
        helpers check_shift_overlap / check_staff_unavailability via separate
        chains. We feed responses by model name."""
        db = MagicMock()
        responses = {
            "RosterShift": shift,
            "User": staff,
            "Booking": booking,
        }

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            # First chain: .filter().first()
            q.filter.return_value.first.return_value = responses.get(name)
            # check_shift_overlap chain: .filter(...).first()
            # check_staff_unavailability: similar chain
            q.filter.return_value.all.return_value = []
            # ShiftBookingLink.delete()
            q.filter.return_value.delete.return_value = 0
            return q

        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db.flush = MagicMock()
        db.add = MagicMock()
        return db

    # ---- HAPPY ----

    def test_H_update_notes_only(self, monkeypatch):
        shift = _mock_shift()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _full_shift_response(s))
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"notes": "Updated note"})
        assert resp.status_code == 200, resp.text
        assert shift.notes == "Updated note"

    def test_H_update_time(self, monkeypatch):
        shift = _mock_shift()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _full_shift_response(s))
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"start_time": "08:00", "end_time": "16:00"})
        assert resp.status_code == 200
        assert shift.start_time == time(8, 0)
        assert shift.end_time == time(16, 0)

    def test_H_unassign_via_staff_id_none(self, monkeypatch):
        shift = _mock_shift()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.shift_to_response", lambda s, db: _full_shift_response(s))
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"staff_id": None})
        assert resp.status_code == 200
        assert shift.staff_id is None

    # ---- UNHAPPY ----

    def test_U_not_found_returns_404(self):
        _override_db(self._wire(shift=None))
        resp = TestClient(app).put("/api/roster/9999", json={"notes": "x"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_U_overlap_returns_409(self, monkeypatch):
        shift = _mock_shift()
        conflict = _mock_shift(id=99, start_time=time(10, 0), end_time=time(12, 0))
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: conflict)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda *a, **k: None)
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"start_time": "10:30"})
        assert resp.status_code == 409
        assert "overlap" in resp.json()["detail"].lower()

    def test_U_staff_unavailable_returns_409(self, monkeypatch):
        shift = _mock_shift()
        unavail = MagicMock()
        unavail.start_time = time(8, 0)
        unavail.end_time = time(12, 0)
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: unavail)
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda *a, **k: None)
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"notes": "x"})
        assert resp.status_code == 409
        assert "unavailable" in resp.json()["detail"].lower()

    def test_U_invalid_booking_id_returns_400(self, monkeypatch):
        shift = _mock_shift()
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda *a, **k: None)
        # Wire DB so Booking lookup returns None
        _override_db(self._wire(shift=shift, staff=_mock_staff(), booking=None))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"booking_ids": [99999]})
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    # ---- EDGE ----

    def test_E_unavailable_all_day_message(self, monkeypatch):
        shift = _mock_shift()
        unavail = MagicMock()
        unavail.start_time = None
        unavail.end_time = None
        monkeypatch.setattr("routers.roster.check_shift_overlap", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.check_staff_unavailability", lambda *a, **k: unavail)
        monkeypatch.setattr("routers.roster.validate_staff_assignment", lambda *a, **k: None)
        _override_db(self._wire(shift=shift, staff=_mock_staff()))
        resp = TestClient(app).put(f"/api/roster/{shift.id}", json={"notes": "x"})
        assert resp.status_code == 409
        # Full-day phrasing uses the date
        assert "/" in resp.json()["detail"] or "unavailable on" in resp.json()["detail"].lower()


# ============================================================================
# DELETE /api/roster/{shift_id} — HUEB
# ============================================================================

class TestDeleteShift:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, shift, other_shifts=None):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = shift
        q.filter.return_value.all.return_value = list(other_shifts or [])
        q.filter.return_value.delete.return_value = 0
        db.query.return_value = q
        db.commit = MagicMock()
        db.delete = MagicMock()
        return db

    def test_H_delete_existing_shift(self):
        s = _mock_shift()
        db = self._wire(s)
        _override_db(db)
        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        db.add.assert_called_once()
        audit = db.add.call_args.args[0]
        assert audit.event == AuditLogEvent.ROSTER_SHIFT_DELETED
        assert audit.session_id == f"roster-shift-{s.id}"
        assert f'"shift_id": {s.id}' in audit.event_data
        assert '"deleted_by_email": "admin@tag.test"' in audit.event_data
        db.delete.assert_called_once_with(s)

    def test_H_delete_auto_unassigned_shift_soft_suppresses(self):
        s = _mock_shift(staff_id=None, created_source="auto")
        db = self._wire(s)
        _override_db(db)
        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suppressed"] is True
        assert body["message"] == "Shift suppressed"
        assert s.status == ShiftStatus.CANCELLED
        assert s.suppressed_by_user_id == 1
        assert s.suppression_reason == "admin_delete"
        assert s.suppressed_at is not None
        db.delete.assert_not_called()

    def test_H_delete_auto_assigned_shift_soft_suppresses(self):
        """Claimed auto shifts still suppress so rebuilds do not recreate them."""
        s = _mock_shift(staff_id=44, created_source="auto")
        db = self._wire(s)
        _override_db(db)
        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suppressed"] is True
        assert body["message"] == "Shift suppressed"
        assert s.status == ShiftStatus.CANCELLED
        assert s.suppressed_by_user_id == 1
        assert s.suppression_reason == "admin_delete"
        assert s.suppressed_at is not None
        db.delete.assert_not_called()

    def test_H_delete_auto_confirmed_unassigned_shift_hard_deletes(self):
        """Only scheduled auto shifts can be suppressed; confirmed shifts are
        treated as owned operational records."""
        s = _mock_shift(staff_id=None, created_source="auto", status=ShiftStatus.CONFIRMED)
        db = self._wire(s)
        _override_db(db)
        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suppressed"] is False
        assert s.status == ShiftStatus.CONFIRMED
        assert s.suppressed_at is None
        db.delete.assert_called_once_with(s)

    def test_H_delete_manual_shift_hard_deletes_not_suppressed(self):
        """Suppression is gated to created_source=='auto'. Dropping the
        staff_id guard must not widen it: a claimed, scheduled MANUAL shift
        still hard-deletes and is never turned into a suppression tombstone."""
        s = _mock_shift(staff_id=44, created_source="manual")
        db = self._wire(s)
        _override_db(db)
        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suppressed"] is False
        assert s.suppressed_at is None
        assert s.suppression_reason is None
        db.delete.assert_called_once_with(s)

    def test_H_delete_preview_warns_for_orphaned_booking_within_96h(self):
        soon = datetime.now(UK_TZ).date() + timedelta(days=1)
        s = _mock_shift(date_=soon, start_time=time(9, 0), end_time=time(10, 0))
        b = _mock_booking(dropoff_date=soon, dropoff_time=time(9, 30))
        s.bookings = [b]

        db = self._wire(s)
        _override_db(db)

        resp = TestClient(app).get(f"/api/roster/{s.id}/delete-preview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["warning"] is True
        assert body["within_96h"] is True
        assert body["orphaned_booking_event_count"] == 1
        assert body["orphaned_booking_events"][0]["booking_reference"] == "TAG-WARN999"

    def test_H_delete_preview_no_warning_when_no_linked_bookings(self):
        soon = datetime.now(UK_TZ).date() + timedelta(days=1)
        s = _mock_shift(date_=soon, start_time=time(9, 0), end_time=time(10, 0))
        db = self._wire(s)
        _override_db(db)

        resp = TestClient(app).get(f"/api/roster/{s.id}/delete-preview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["linked_booking_count"] == 0
        assert body["orphaned_booking_event_count"] == 0
        assert body["within_96h"] is True
        assert body["warning"] is False

    def test_H_delete_preview_no_warning_when_other_live_shift_covers_booking(self):
        soon = datetime.now(UK_TZ).date() + timedelta(days=1)
        s = _mock_shift(id=10, date_=soon, start_time=time(9, 0), end_time=time(10, 0))
        s.bookings = [_mock_booking(dropoff_date=soon, dropoff_time=time(9, 30))]
        cover = _mock_shift(id=11, date_=soon, start_time=time(9, 0), end_time=time(10, 0))
        db = self._wire(s, other_shifts=[cover])
        _override_db(db)

        resp = TestClient(app).get(f"/api/roster/{s.id}/delete-preview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["linked_booking_count"] == 1
        assert body["orphaned_booking_event_count"] == 0
        assert body["within_96h"] is True
        assert body["warning"] is False

    def test_E_delete_preview_orphan_outside_96h_does_not_warn(self):
        later = datetime.now(UK_TZ).date() + timedelta(days=5)
        s = _mock_shift(date_=later, start_time=time(9, 0), end_time=time(10, 0))
        s.bookings = [_mock_booking(dropoff_date=later, dropoff_time=time(9, 30))]
        db = self._wire(s)
        _override_db(db)

        resp = TestClient(app).get(f"/api/roster/{s.id}/delete-preview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["orphaned_booking_event_count"] == 1
        assert body["within_96h"] is False
        assert body["warning"] is False

    def test_H_delete_response_and_audit_include_preview_payload(self):
        soon = datetime.now(UK_TZ).date() + timedelta(days=1)
        s = _mock_shift(staff_id=None, created_source="auto", date_=soon, start_time=time(9, 0), end_time=time(10, 0))
        s.bookings = [_mock_booking(dropoff_date=soon, dropoff_time=time(9, 30))]
        db = self._wire(s)
        _override_db(db)

        resp = TestClient(app).delete(f"/api/roster/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["delete_preview"]["warning"] is True
        assert body["delete_preview"]["orphaned_booking_event_count"] == 1

        audit = db.add.call_args.args[0]
        assert '"delete_preview"' in audit.event_data
        assert '"orphaned_booking_event_count": 1' in audit.event_data
        assert '"warning": true' in audit.event_data

    def test_U_delete_nonexistent_returns_404(self):
        _override_db(self._wire(None))
        resp = TestClient(app).delete("/api/roster/9999")
        assert resp.status_code == 404

    def test_U_delete_preview_nonexistent_returns_404(self):
        _override_db(self._wire(None))
        resp = TestClient(app).get("/api/roster/9999/delete-preview")
        assert resp.status_code == 404


# ============================================================================
# GET /api/holidays + variants — HUEB
# ============================================================================

class TestListHolidays:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, holidays, monkeypatch=None):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = holidays
        db.query.return_value = chain
        return db

    # ---- HAPPY ----

    def test_H_list_all(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id, "staff_id": h.staff_id})
        h = _mock_holiday()
        _override_db(self._wire([h]))
        resp = TestClient(app).get("/api/holidays")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_H_filter_by_date_range(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([_mock_holiday()]))
        resp = TestClient(app).get("/api/holidays?date_from=2026-07-01&date_to=2026-07-31")
        assert resp.status_code == 200

    def test_H_filter_by_staff_id(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([_mock_holiday()]))
        resp = TestClient(app).get("/api/holidays?staff_id=2")
        assert resp.status_code == 200

    def test_H_filter_date_from_only(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([_mock_holiday()]))
        resp = TestClient(app).get("/api/holidays?date_from=2026-07-01")
        assert resp.status_code == 200

    def test_H_filter_date_to_only(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([_mock_holiday()]))
        resp = TestClient(app).get("/api/holidays?date_to=2026-07-31")
        assert resp.status_code == 200

    # ---- UNHAPPY ----

    def test_U_invalid_date_format_returns_422(self):
        _override_db(self._wire([]))
        resp = TestClient(app).get("/api/holidays?date_from=not-a-date")
        assert resp.status_code == 422

    # ---- EDGE ----

    def test_E_empty_list_returns_empty(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([]))
        resp = TestClient(app).get("/api/holidays")
        assert resp.status_code == 200
        assert resp.json() == []

    # ---- BOUNDARY ----

    def test_B_date_from_equals_date_to(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire([_mock_holiday()]))
        resp = TestClient(app).get("/api/holidays?date_from=2026-07-05&date_to=2026-07-05")
        assert resp.status_code == 200


class TestGetHolidaysForDate:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_H_returns_holidays_for_date(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [_mock_holiday()]
        _override_db(db)
        resp = TestClient(app).get("/api/holidays/for-date?date=2026-07-05")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_U_missing_date_param_returns_422(self):
        _override_db(MagicMock())
        resp = TestClient(app).get("/api/holidays/for-date")
        assert resp.status_code == 422

    def test_E_no_holidays_returns_empty(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        _override_db(db)
        resp = TestClient(app).get("/api/holidays/for-date?date=2026-07-05")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetHoliday:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_H_get_existing(self, monkeypatch):
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        h = _mock_holiday()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = h
        _override_db(db)
        resp = TestClient(app).get(f"/api/holidays/{h.id}")
        assert resp.status_code == 200

    def test_U_not_found_returns_404(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        _override_db(db)
        resp = TestClient(app).get("/api/holidays/9999")
        assert resp.status_code == 404


# ============================================================================
# POST /api/holidays — HUEB
# ============================================================================

class TestCreateHoliday:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, staff=None, overlapping_holidays=None, conflicting_shifts=None):
        db = MagicMock()
        responses_first = {"User": staff}
        responses_all = {
            "EmployeeHoliday": overlapping_holidays or [],
            "RosterShift": conflicting_shifts or [],
        }

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            q.filter.return_value.first.return_value = responses_first.get(name)
            q.filter.return_value.all.return_value = responses_all.get(name, [])
            return q

        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def _post(self, **params):
        """Endpoint accepts params as query string per its signature."""
        from urllib.parse import urlencode
        return TestClient(app).post(f"/api/holidays?{urlencode(params)}")

    # ---- HAPPY ----

    def test_H_create_basic_holiday(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-07")
        assert resp.status_code == 201, resp.text

    def test_H_create_with_holiday_type_sick(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-01", holiday_type="sick")
        assert resp.status_code == 201

    def test_H_create_partial_day_with_times(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", lambda s: time(9, 0))
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-01", start_time="09:00", end_time="13:00")
        assert resp.status_code == 201

    # ---- UNHAPPY ----

    def test_U_staff_not_found_returns_404(self):
        _override_db(self._wire(staff=None))
        resp = self._post(staff_id=99999, start_date="2026-08-01", end_date="2026-08-07")
        assert resp.status_code == 404

    def test_U_invalid_holiday_type_returns_400(self):
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-07", holiday_type="bogus")
        assert resp.status_code == 400
        assert "invalid holiday type" in resp.json()["detail"].lower()

    def test_U_overlapping_holiday_returns_409(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: True)
        overlap = _mock_holiday(start=date_type(2026, 8, 3), end=date_type(2026, 8, 5))
        _override_db(self._wire(staff=_mock_staff(), overlapping_holidays=[overlap]))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-07")
        assert resp.status_code == 409
        assert "overlap" in resp.json()["detail"].lower()

    def test_U_invalid_start_time_returns_400(self, monkeypatch):
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", lambda s: None)
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-01", start_time="bogus")
        assert resp.status_code == 400

    def test_U_invalid_end_time_returns_400(self, monkeypatch):
        # First parse returns time, second returns None
        calls = {"n": 0}
        def fake_parse(s):
            calls["n"] += 1
            return time(9, 0) if calls["n"] == 1 else None
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", fake_parse)
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-01", start_time="09:00", end_time="bogus")
        assert resp.status_code == 400

    def test_U_existing_shift_returns_409(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        shift = _mock_shift(date_=date_type(2026, 8, 3))
        _override_db(self._wire(staff=_mock_staff(), conflicting_shifts=[shift]))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-07")
        assert resp.status_code == 409
        assert "shift" in resp.json()["detail"].lower()

    # ---- BOUNDARY ----

    def test_B_end_date_before_start_date_returns_400(self):
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-07", end_date="2026-08-01")
        assert resp.status_code == 400
        assert "end date" in resp.json()["detail"].lower()

    def test_B_single_day_holiday_succeeds(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        _override_db(self._wire(staff=_mock_staff()))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-01")
        assert resp.status_code == 201

    def test_B_multiple_conflicting_shifts_returns_count_in_detail(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        shifts = [
            _mock_shift(date_=date_type(2026, 8, 1)),
            _mock_shift(date_=date_type(2026, 8, 3)),
            _mock_shift(date_=date_type(2026, 8, 5)),
        ]
        _override_db(self._wire(staff=_mock_staff(), conflicting_shifts=shifts))
        resp = self._post(staff_id=2, start_date="2026-08-01", end_date="2026-08-07")
        assert resp.status_code == 409
        assert "3 shifts" in resp.json()["detail"] or "shifts scheduled" in resp.json()["detail"].lower()


# ============================================================================
# PUT /api/holidays/{id} — HUEB
# ============================================================================

class TestUpdateHoliday:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, holiday=None, overlapping_holidays=None, conflicting_shifts=None):
        db = MagicMock()
        responses_first = {"EmployeeHoliday": holiday}
        responses_all = {
            "EmployeeHoliday": overlapping_holidays or [],
            "RosterShift": conflicting_shifts or [],
        }

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            q.filter.return_value.first.return_value = responses_first.get(name)
            q.filter.return_value.all.return_value = responses_all.get(name, [])
            return q

        db.query.side_effect = _query
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    def _put(self, holiday_id, **params):
        from urllib.parse import urlencode
        qs = urlencode({k: v for k, v in params.items() if v is not None})
        return TestClient(app).put(f"/api/holidays/{holiday_id}?{qs}")

    # ---- HAPPY ----

    def test_H_update_notes_only(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id, "notes": h.notes})
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, notes="Updated reason")
        assert resp.status_code == 200, resp.text
        assert h.notes == "Updated reason"

    def test_H_change_holiday_type(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, holiday_type="sick")
        assert resp.status_code == 200

    def test_H_clear_times(self, monkeypatch):
        h = _mock_holiday(start_t=time(9, 0), end_t=time(13, 0))
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, clear_times="true")
        assert resp.status_code == 200
        assert h.start_time is None
        assert h.end_time is None

    def test_H_set_partial_day_times(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.holiday_to_response", lambda h: {"id": h.id})
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", lambda s: time(int(s.split(":")[0]), int(s.split(":")[1])))
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, start_time="09:00", end_time="13:00")
        assert resp.status_code == 200

    # ---- UNHAPPY ----

    def test_U_not_found(self):
        _override_db(self._wire(holiday=None))
        resp = self._put(99999, notes="x")
        assert resp.status_code == 404

    def test_U_invalid_holiday_type(self):
        h = _mock_holiday()
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, holiday_type="bogus")
        assert resp.status_code == 400
        assert "invalid holiday type" in resp.json()["detail"].lower()

    def test_U_invalid_start_time(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", lambda s: None)
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, start_time="bogus")
        assert resp.status_code == 400
        assert "start_time" in resp.json()["detail"].lower()

    def test_U_invalid_end_time(self, monkeypatch):
        h = _mock_holiday()
        calls = {"n": 0}
        def fake(s):
            calls["n"] += 1
            return time(9, 0) if calls["n"] == 1 else None
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", fake)
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, start_time="09:00", end_time="bogus")
        assert resp.status_code == 400

    def test_U_overlapping_holiday(self, monkeypatch):
        h = _mock_holiday()
        overlap = _mock_holiday(id=2, start_t=time(8, 0), end_t=time(12, 0))
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: True)
        monkeypatch.setattr("routers.roster.format_time", lambda t: t.strftime("%H:%M"))
        _override_db(self._wire(holiday=h, overlapping_holidays=[overlap]))
        resp = self._put(h.id, notes="x")
        assert resp.status_code == 409
        assert "overlap" in resp.json()["detail"].lower()

    def test_U_conflicting_shift_single(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        shift = _mock_shift(date_=date_type(2026, 7, 3))
        _override_db(self._wire(holiday=h, conflicting_shifts=[shift]))
        resp = self._put(h.id, notes="x")
        assert resp.status_code == 409
        assert "shift" in resp.json()["detail"].lower()

    def test_U_conflicting_shifts_multiple(self, monkeypatch):
        h = _mock_holiday()
        monkeypatch.setattr("routers.roster.check_holiday_time_overlap", lambda *a, **k: False)
        shifts = [
            _mock_shift(date_=date_type(2026, 7, 2)),
            _mock_shift(date_=date_type(2026, 7, 4)),
        ]
        _override_db(self._wire(holiday=h, conflicting_shifts=shifts))
        resp = self._put(h.id, notes="x")
        assert resp.status_code == 409
        assert "shifts" in resp.json()["detail"].lower()

    # ---- BOUNDARY ----

    def test_B_end_date_before_start_date(self, monkeypatch):
        h = _mock_holiday(start=date_type(2026, 7, 1), end=date_type(2026, 7, 7))
        # Trigger a validation error by setting end_date < start_date via PUT
        _override_db(self._wire(holiday=h))
        resp = self._put(h.id, end_date="2026-06-30")
        assert resp.status_code == 400


# ============================================================================
# DELETE /api/holidays/{id} — HUEB
# ============================================================================

class TestDeleteHoliday:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, holiday):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = holiday
        db.delete = MagicMock()
        db.commit = MagicMock()
        return db

    def test_H_delete_existing(self):
        h = _mock_holiday()
        _override_db(self._wire(h))
        resp = TestClient(app).delete(f"/api/holidays/{h.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_U_not_found_returns_404(self):
        _override_db(self._wire(None))
        resp = TestClient(app).delete("/api/holidays/99999")
        assert resp.status_code == 404


# ============================================================================
# GET /api/payroll/monthly — HUEB
# ============================================================================

class TestMonthlyPayroll:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, shifts=None, staff=None):
        db = MagicMock()
        responses_all = {
            "RosterShift": shifts or [],
            "User": staff or [],
        }

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = responses_all.get(name, [])
            # Single-shot for the inactive-staff-with-historical-shift branch
            chain.first.return_value = staff[0] if staff else None
            return chain

        db.query.side_effect = _query
        return db

    # ---- HAPPY ----

    def test_H_no_shifts_no_staff_returns_zero_totals(self):
        _override_db(self._wire(shifts=[], staff=[]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["year"] == 2026
        assert body["month"] == 5
        assert body["totals"]["total_shifts"] == 0

    def test_H_one_staff_one_shift(self):
        staff = _mock_staff()
        shift = _mock_shift(staff_id=staff.id, date_=date_type(2026, 5, 15))
        _override_db(self._wire(shifts=[shift], staff=[staff]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["totals"]["total_shifts"] == 1
        assert body["totals"]["total_hours"] > 0

    def test_H_overnight_shift_branch(self):
        staff = _mock_staff()
        s = _mock_shift(staff_id=staff.id, date_=date_type(2026, 5, 15),
                        start_time=time(22, 0), end_time=time(2, 0))
        s.end_date = date_type(2026, 5, 16)
        _override_db(self._wire(shifts=[s], staff=[staff]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200
        body = resp.json()
        # Overnight (22:00–02:00) = 4 hours when computed correctly
        assert body["totals"]["total_hours"] > 0

    def test_H_inactive_staff_with_shift_recovered(self):
        """A shift assigned to a staff not in `all_staff` should still be
        included after looking up by id."""
        active = _mock_staff(id=2)
        inactive = _mock_staff(id=99, is_active=False)
        s = _mock_shift(staff_id=inactive.id, date_=date_type(2026, 5, 1))

        # Build a custom DB so User query returns active list AND single-shot for inactive
        db = MagicMock()
        def _query(model):
            q = MagicMock()
            name = model.__name__
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            if name == "RosterShift":
                chain.all.return_value = [s]
            elif name == "User":
                chain.all.return_value = [active]   # active list
                chain.first.return_value = inactive  # single-shot lookup
            return chain
        db.query.side_effect = _query
        _override_db(db)
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200
        body = resp.json()
        # Inactive staff name should appear in result list
        names = [s["staff_name"] for s in body["staff"]]
        assert any(n for n in names)

    # ---- UNHAPPY ----

    def test_U_month_out_of_range(self):
        _override_db(self._wire(shifts=[], staff=[]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=13")
        assert resp.status_code == 422

    def test_U_month_zero_returns_422(self):
        _override_db(self._wire(shifts=[], staff=[]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=0")
        assert resp.status_code == 422

    def test_U_missing_year(self):
        _override_db(self._wire(shifts=[], staff=[]))
        resp = TestClient(app).get("/api/payroll/monthly?month=5")
        assert resp.status_code == 422

    # ---- BOUNDARY ----

    def test_B_february_leap_year(self):
        _override_db(self._wire(shifts=[], staff=[]))
        # 2024 is a leap year — handler uses calendar.monthrange so this exercises 29
        resp = TestClient(app).get("/api/payroll/monthly?year=2024&month=2")
        assert resp.status_code == 200

    def test_B_december_year_wrap(self):
        _override_db(self._wire(shifts=[], staff=[]))
        resp = TestClient(app).get("/api/payroll/monthly?year=2026&month=12")
        assert resp.status_code == 200
        assert resp.json()["month_name"] == "December"


# ============================================================================
# GET /api/employee/payroll/monthly — HUEB (subset)
# ============================================================================

class TestEmployeeMonthlyPayroll:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, shifts):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.all.return_value = shifts
        db.query.return_value = chain
        return db

    def test_H_no_shifts(self):
        _override_db(self._wire([]))
        resp = TestClient(app).get("/api/employee/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200
        # Endpoint signature returns dict — verify totals
        body = resp.json()
        assert "year" in body
        assert body["year"] == 2026

    def test_H_with_shifts(self):
        s = _mock_shift(staff_id=1, date_=date_type(2026, 5, 10))
        _override_db(self._wire([s]))
        resp = TestClient(app).get("/api/employee/payroll/monthly?year=2026&month=5")
        assert resp.status_code == 200

    def test_U_month_out_of_range(self):
        _override_db(self._wire([]))
        resp = TestClient(app).get("/api/employee/payroll/monthly?year=2026&month=99")
        assert resp.status_code == 422


# ============================================================================
# Employee unavailability CRUD — HUEB
# ============================================================================

class TestEmployeeUnavailability:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, records=None, conflicting_shift=None, holiday=None):
        db = MagicMock()
        responses_all = {"EmployeeHoliday": records or []}
        responses_first = {"EmployeeHoliday": holiday}

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = responses_all.get(name, [])
            chain.first.return_value = responses_first.get(name)
            return chain

        db.query.side_effect = _query
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db.delete = MagicMock()
        return db

    def _post(self, **params):
        from urllib.parse import urlencode
        return TestClient(app).post(f"/api/employee/unavailability?{urlencode(params)}")

    # ---- POST happy ----

    def test_H_post_full_day(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_shift_conflict_for_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster._notify_founder_roster_event", lambda *a, **k: None)
        _override_db(self._wire())
        # v4: self-added unavailability needs 72h notice — use future dates.
        start = date.today() + timedelta(days=10)
        end = start + timedelta(days=2)
        resp = self._post(start_date=start.strftime("%d/%m/%Y"), end_date=end.strftime("%d/%m/%Y"), notes="Holiday")
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    def test_H_post_partial_day_with_times(self, monkeypatch):
        monkeypatch.setattr("routers.roster.check_shift_conflict_for_unavailability", lambda *a, **k: None)
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability", lambda s: time(int(s.split(":")[0]), int(s.split(":")[1])) if s else None)
        monkeypatch.setattr("routers.roster._notify_founder_roster_event", lambda *a, **k: None)
        _override_db(self._wire())
        start = date.today() + timedelta(days=10)
        resp = self._post(start_date=start.strftime("%d/%m/%Y"), end_date=start.strftime("%d/%m/%Y"), start_time="09:00", end_time="13:00")
        assert resp.status_code == 200

    # ---- POST unhappy ----

    def test_U_post_invalid_start_date_format(self):
        _override_db(self._wire())
        resp = self._post(start_date="2026-06-01", end_date="03/06/2026")  # wrong format (YYYY-MM-DD)
        assert resp.status_code == 400
        assert "start_date" in resp.json()["detail"].lower()

    def test_U_post_invalid_end_date_format(self):
        _override_db(self._wire())
        resp = self._post(start_date="01/06/2026", end_date="bogus")
        assert resp.status_code == 400
        assert "end_date" in resp.json()["detail"].lower()

    def test_U_post_end_before_start(self):
        _override_db(self._wire())
        resp = self._post(start_date="05/06/2026", end_date="01/06/2026")
        assert resp.status_code == 400
        assert "end date" in resp.json()["detail"].lower()

    def test_U_post_end_time_not_after_start_time(self, monkeypatch):
        monkeypatch.setattr("routers.roster.parse_time_for_unavailability",
                            lambda s: time(int(s.split(":")[0]), int(s.split(":")[1])) if s else None)
        _override_db(self._wire())
        resp = self._post(start_date="01/06/2026", end_date="01/06/2026",
                          start_time="13:00", end_time="13:00")
        assert resp.status_code == 400
        assert "end time" in resp.json()["detail"].lower()

    def test_U_post_conflicting_shift(self, monkeypatch):
        shift = _mock_shift(date_=date_type(2026, 6, 2))
        monkeypatch.setattr("routers.roster.check_shift_conflict_for_unavailability", lambda *a, **k: shift)
        _override_db(self._wire())
        resp = self._post(start_date="01/06/2026", end_date="03/06/2026")
        assert resp.status_code == 409
        assert "shift" in resp.json()["detail"].lower()

    # ---- GET ----

    def test_H_get_no_filter(self):
        rec = _mock_holiday(hol_type=HolidayType.UNAVAILABLE)
        _override_db(self._wire(records=[rec]))
        resp = TestClient(app).get("/api/employee/unavailability")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1

    def test_H_get_with_date_filters(self):
        rec = _mock_holiday(hol_type=HolidayType.UNAVAILABLE)
        _override_db(self._wire(records=[rec]))
        resp = TestClient(app).get("/api/employee/unavailability?date_from=01/06/2026&date_to=30/06/2026")
        assert resp.status_code == 200

    def test_E_get_invalid_date_filter_ignored(self):
        """Bad DD/MM/YYYY filters are silently dropped — endpoint still returns 200."""
        rec = _mock_holiday(hol_type=HolidayType.UNAVAILABLE)
        _override_db(self._wire(records=[rec]))
        resp = TestClient(app).get("/api/employee/unavailability?date_from=bogus&date_to=alsobad")
        assert resp.status_code == 200

    # ---- DELETE ----

    def test_H_delete_existing(self):
        rec = _mock_holiday(hol_type=HolidayType.UNAVAILABLE)
        _override_db(self._wire(holiday=rec))
        resp = TestClient(app).delete(f"/api/employee/unavailability/{rec.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_U_delete_not_found(self):
        _override_db(self._wire(holiday=None))
        resp = TestClient(app).delete("/api/employee/unavailability/99999")
        assert resp.status_code == 404


# ============================================================================
# GET /api/roster/export — CSV export HUEB
# ============================================================================

class TestRosterExport:
    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _wire(self, shifts=None, booking=None):
        db = MagicMock()
        responses_all = {"RosterShift": shifts or []}
        responses_first = {"Booking": booking}

        def _query(model):
            q = MagicMock()
            name = model.__name__ if hasattr(model, "__name__") else str(model)
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.order_by.return_value = chain
            chain.all.return_value = responses_all.get(name, [])
            chain.first.return_value = responses_first.get(name)
            return chain

        db.query.side_effect = _query
        return db

    def test_H_empty_week(self):
        _override_db(self._wire(shifts=[]))
        resp = TestClient(app).get("/api/roster/export?week_start=2026-06-01")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        # Header row present
        assert "Date,Employee Name" in resp.text

    def test_H_unassigned_shift(self):
        shift = _mock_shift(staff_id=None)
        shift.staff = None
        _override_db(self._wire(shifts=[shift]))
        resp = TestClient(app).get("/api/roster/export?week_start=2026-06-15")
        assert resp.status_code == 200
        assert "Unassigned" in resp.text

    def test_H_assigned_shift_with_staff(self):
        shift = _mock_shift()
        # `shift.staff` attribute used by the handler
        staff = MagicMock()
        staff.first_name = "Jane"
        staff.last_name = "Doe"
        shift.staff = staff
        _override_db(self._wire(shifts=[shift]))
        resp = TestClient(app).get("/api/roster/export?week_start=2026-06-15")
        assert resp.status_code == 200
        assert "Jane Doe" in resp.text

    def test_H_shift_with_booking_ref(self):
        shift = _mock_shift(booking_id=42)
        shift.staff = None
        booking = MagicMock()
        booking.reference = "TAG-XYZ123"
        _override_db(self._wire(shifts=[shift], booking=booking))
        resp = TestClient(app).get("/api/roster/export?week_start=2026-06-15")
        assert resp.status_code == 200
        assert "TAG-XYZ123" in resp.text

    def test_U_missing_week_start(self):
        _override_db(self._wire(shifts=[]))
        resp = TestClient(app).get("/api/roster/export")
        assert resp.status_code == 422

    def test_U_invalid_week_start(self):
        _override_db(self._wire(shifts=[]))
        resp = TestClient(app).get("/api/roster/export?week_start=not-a-date")
        assert resp.status_code == 422

    def test_E_filename_uses_ddmmyyyy(self):
        _override_db(self._wire(shifts=[]))
        resp = TestClient(app).get("/api/roster/export?week_start=2026-03-07")
        cd = resp.headers.get("content-disposition", "")
        assert "07032026" in cd
