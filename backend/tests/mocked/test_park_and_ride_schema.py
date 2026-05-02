"""
Schema-layer tests for the Park & Ride slice (1/n).

Covers:
  * The two auto-roster pathways short-circuit on `service_type=PARK_RIDE`:
      - auto_roster.auto_create_or_extend_for_booking
      - auto_roster.handle_booking_cancelled
      - roster_planner_runner.auto_link_booking_to_shifts
  * db_service.create_booking accepts the new kwargs and persists them on
    the SQLAlchemy Booking instance with the right defaults.

Per SPEC.md: H/U/E/B coverage per subject. Dates / DST tests live with the
P&R cost logic in a later slice (this slice ships the schema, not pricing).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auto_roster import (  # noqa: E402
    auto_create_or_extend_for_booking,
    handle_booking_cancelled,
)
from db_models import BookingStatus, ServiceType  # noqa: E402
from roster_planner import PlannerSettings  # noqa: E402
from roster_planner_runner import auto_link_booking_to_shifts  # noqa: E402


def _settings() -> PlannerSettings:
    return PlannerSettings(
        window_days=28,
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


def _booking(
    *,
    service_type: ServiceType = ServiceType.MEET_GREET,
    status: BookingStatus = BookingStatus.CONFIRMED,
    booking_id: int = 1,
):
    """SimpleNamespace booking — auto_roster only reads attributes."""
    return SimpleNamespace(
        id=booking_id,
        reference="TAG-PR00001",
        status=status,
        service_type=service_type,
        dropoff_date=date(2026, 6, 10),
        dropoff_time=time(8, 0),
        pickup_date=date(2026, 6, 17),
        pickup_time=time(14, 0),
        flight_arrival_time=None,
    )


# ---------------------------------------------------------------------------
# auto_create_or_extend_for_booking
# ---------------------------------------------------------------------------

class TestAutoCreateGuard:
    def test_happy_park_ride_skips(self):
        """P&R booking should be skipped — no DB touched, summary marks skip."""
        db = MagicMock()
        booking = _booking(service_type=ServiceType.PARK_RIDE)

        result = auto_create_or_extend_for_booking(db, booking, _settings())

        assert result == {"created": 0, "extended": 0, "skipped": 1}
        # Guard fires before any query — proves it's a true short-circuit.
        db.query.assert_not_called()

    def test_unhappy_meet_greet_still_processes(self):
        """M&G booking must NOT short-circuit — guard is P&R-specific."""
        db = MagicMock()
        # Make the query chain return no candidates / no links so the
        # function reaches commit cleanly without doing real work.
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = None

        booking = _booking(service_type=ServiceType.MEET_GREET)
        result = auto_create_or_extend_for_booking(db, booking, _settings())

        # Reached the loop body — query was hit, so guard didn't trigger.
        assert db.query.called
        assert result["skipped"] == 0  # M&G doesn't get the early-skip count

    def test_edge_park_ride_with_pending_status(self):
        """P&R + non-CONFIRMED — the existing status guard fires first.
        This documents that order doesn't matter; both early-returns produce
        the same skip-count summary."""
        db = MagicMock()
        booking = _booking(
            service_type=ServiceType.PARK_RIDE,
            status=BookingStatus.PENDING,
        )

        result = auto_create_or_extend_for_booking(db, booking, _settings())

        assert result == {"created": 0, "extended": 0, "skipped": 1}
        db.query.assert_not_called()

    def test_boundary_none_booking(self):
        """None booking — first guard short-circuits before service_type read."""
        db = MagicMock()
        result = auto_create_or_extend_for_booking(db, None, _settings())
        assert result == {"created": 0, "extended": 0, "skipped": 1}
        db.query.assert_not_called()


# ---------------------------------------------------------------------------
# handle_booking_cancelled
# ---------------------------------------------------------------------------

class TestHandleCancelledGuard:
    def test_happy_park_ride_skips(self):
        """Cancelled P&R booking — no link cleanup, no shift deletes."""
        db = MagicMock()
        booking = _booking(
            service_type=ServiceType.PARK_RIDE,
            status=BookingStatus.CANCELLED,
        )

        result = handle_booking_cancelled(db, booking)

        assert result == {"links_removed": 0, "auto_shifts_deleted": 0}
        db.query.assert_not_called()

    def test_unhappy_meet_greet_still_processes(self):
        """Cancelled M&G booking — guard does NOT fire."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        booking = _booking(
            service_type=ServiceType.MEET_GREET,
            status=BookingStatus.CANCELLED,
        )

        handle_booking_cancelled(db, booking)

        assert db.query.called

    def test_edge_park_ride_status_not_cancelled(self):
        """P&R + non-CANCELLED status — status guard fires first regardless."""
        db = MagicMock()
        booking = _booking(
            service_type=ServiceType.PARK_RIDE,
            status=BookingStatus.CONFIRMED,
        )

        result = handle_booking_cancelled(db, booking)

        assert result == {"links_removed": 0, "auto_shifts_deleted": 0}
        db.query.assert_not_called()

    def test_boundary_none_booking(self):
        db = MagicMock()
        result = handle_booking_cancelled(db, None)
        assert result == {"links_removed": 0, "auto_shifts_deleted": 0}
        db.query.assert_not_called()


# ---------------------------------------------------------------------------
# auto_link_booking_to_shifts (roster_planner_runner)
# ---------------------------------------------------------------------------

class TestAutoLinkGuard:
    def test_happy_park_ride_returns_empty(self):
        """P&R booking — no shift links attempted, returns empty list."""
        db = MagicMock()
        booking = _booking(service_type=ServiceType.PARK_RIDE)

        result = auto_link_booking_to_shifts(db, booking)

        assert result == []
        db.query.assert_not_called()

    def test_unhappy_none_booking(self):
        """Pre-existing None guard still fires before the new P&R guard."""
        db = MagicMock()
        result = auto_link_booking_to_shifts(db, None)
        assert result == []
        db.query.assert_not_called()

    def test_edge_park_ride_with_no_id(self):
        """P&R + booking.id is None — both guards apply; the id guard runs
        first (older code path), so we just assert the empty result and
        no DB activity, regardless of which guard fired."""
        db = MagicMock()
        booking = SimpleNamespace(
            id=None,
            service_type=ServiceType.PARK_RIDE,
        )
        result = auto_link_booking_to_shifts(db, booking)
        assert result == []
        db.query.assert_not_called()

    def test_boundary_meet_greet_proceeds(self):
        """M&G booking with a valid id — guard does NOT fire; query is reached."""
        db = MagicMock()
        # Return no candidate shifts so the function exits cleanly without
        # exercising the link-creation logic (out of scope for this slice).
        db.query.return_value.filter.return_value.all.return_value = []
        booking = _booking(service_type=ServiceType.MEET_GREET)

        auto_link_booking_to_shifts(db, booking)

        assert db.query.called


# ---------------------------------------------------------------------------
# db_service.create_booking — new kwargs
# ---------------------------------------------------------------------------

class TestCreateBookingKwargs:
    """Verify db_service.create_booking accepts service_type and
    traveller_count and forwards them onto the SQLAlchemy Booking instance.
    Uses a real db_service.create_booking call with a MagicMock session,
    asserting on the Booking instance passed to db.add()."""

    def _stub_db(self):
        db = MagicMock()
        # get_customer_by_id is called inside create_booking — return a
        # SimpleNamespace with first/last name to satisfy the snapshot fields.
        return db

    def _call_create(self, db, **overrides):
        from db_service import create_booking

        with MagicMock() as _:
            pass

        # Patch get_customer_by_id at the module level so we don't have to
        # build a full customer query mock.
        from unittest.mock import patch as _patch

        with _patch(
            "db_service.get_customer_by_id",
            return_value=SimpleNamespace(first_name="Jo", last_name="Bloggs"),
        ), _patch(
            "db_service.get_booking_by_reference",
            return_value=None,
        ):
            return create_booking(
                db=db,
                customer_id=1,
                vehicle_id=1,
                package="quick",
                dropoff_date=date(2026, 6, 10),
                dropoff_time=time(8, 0),
                pickup_date=date(2026, 6, 17),
                **overrides,
            )

    def _added_booking(self, db):
        """Pull the Booking instance handed to db.add()."""
        assert db.add.called, "db.add was never called"
        return db.add.call_args.args[0]

    def test_happy_park_ride_with_traveller_count(self):
        db = self._stub_db()
        self._call_create(
            db,
            service_type=ServiceType.PARK_RIDE,
            traveller_count=3,
        )
        booking = self._added_booking(db)
        assert booking.service_type == ServiceType.PARK_RIDE
        assert booking.traveller_count == 3

    def test_unhappy_omitted_defaults_to_meet_greet(self):
        """Existing M&G callers don't pass these kwargs — must default
        cleanly to MEET_GREET / NULL traveller_count."""
        db = self._stub_db()
        self._call_create(db)
        booking = self._added_booking(db)
        assert booking.service_type == ServiceType.MEET_GREET
        assert booking.traveller_count is None

    def test_edge_park_ride_no_traveller_count(self):
        """P&R booking with traveller_count omitted — column is nullable;
        callers can fill in later. Guard against accidental NOT NULL drift."""
        db = self._stub_db()
        self._call_create(db, service_type=ServiceType.PARK_RIDE)
        booking = self._added_booking(db)
        assert booking.service_type == ServiceType.PARK_RIDE
        assert booking.traveller_count is None

    def test_boundary_traveller_count_one(self):
        """Smallest sensible traveller_count = 1 (driver alone). 0 is a
        legitimate edge — passenger picked up by someone else — but the
        UI will enforce ≥1 in slice 3. Verify 1 round-trips."""
        db = self._stub_db()
        self._call_create(
            db,
            service_type=ServiceType.PARK_RIDE,
            traveller_count=1,
        )
        booking = self._added_booking(db)
        assert booking.traveller_count == 1
