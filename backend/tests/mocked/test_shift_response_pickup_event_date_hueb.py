"""
HUEB tests for the pickup-event-date link match in
`routers/roster.shift_to_response`.

Background (TAG-KNL95826 staging incident 2026-05-21): admin edited only
the arrival_date + arrival_time on a booking, leaving pickup_date alone.
Auto-roster correctly created a shift anchored on the new arrival_date,
and linked the booking via shift_booking_links. But the shift card
rendered empty because the linked-bookings response was matching
`booking.pickup_date in shift_dates` — and pickup_date hadn't moved.

Fix: introduce `_pickup_event_date(booking)` mirroring the rule in
`auto_roster._events_for_booking`, and key the pickup-side match off that
instead of pickup_date.

H/U/E/B per SPEC.md, executed against the imported real code so the
coverage counters tick.
"""
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import BookingStatus
from routers.roster import (
    _booking_customer_phone,
    _booking_vehicle_attr,
    _booking_vehicle_registration,
    _pickup_event_date,
    shift_to_response,
)


# ---------------------------------------------------------------------------
# Booking factory
# ---------------------------------------------------------------------------

def _booking(**overrides):
    """SimpleNamespace booking — routers.roster only reads attributes."""
    base = dict(
        id=42,
        reference="TAG-PICKUP01",
        customer_first_name="Jo",
        customer_last_name="K",
        customer=None,
        dropoff_date=date(2026, 6, 1),
        dropoff_time=time(10, 0),
        dropoff_destination="Tenerife",
        dropoff_airline_name="Jet2",
        dropoff_flight_number="LS3641",
        flight_departure_time=time(12, 0),
        pickup_date=date(2026, 7, 2),
        pickup_time=time(18, 30),
        flight_arrival_date=date(2026, 7, 2),
        flight_arrival_time=time(18, 0),
        pickup_origin="Palma de Mallorca Airport",
        pickup_airline_name="easyJet",
        pickup_flight_number="EZY4041",
        status=BookingStatus.CONFIRMED,
        vehicle=None,
        vehicle_registration=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _shift(**overrides):
    from datetime import datetime as dt_datetime
    from db_models import ShiftStatus, ShiftType
    base = dict(
        id=999,
        staff_id=None,
        staff=None,
        date=date(2026, 7, 2),
        end_date=None,
        start_time=time(16, 15),
        end_time=time(18, 45),
        shift_type=ShiftType.AFTERNOON,
        status=ShiftStatus.SCHEDULED,
        created_source="auto",
        notes=None,
        bookings=[],
        booking_id=None,
        planner_run_id=None,
        intended_driver_type=None,
        created_at=dt_datetime(2026, 5, 20, 12, 0, 0),
        updated_at=dt_datetime(2026, 5, 20, 12, 0, 0),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ===========================================================================
# _pickup_event_date — pure logic
# ===========================================================================

class TestPickupEventDate:

    # --- HAPPY ---------------------------------------------------------------

    def test_H_flight_arrival_date_takes_precedence(self):
        """When the canonical column is set, it wins regardless of pickup_date."""
        b = _booking(
            flight_arrival_date=date(2026, 7, 3),
            pickup_date=date(2026, 7, 2),
            flight_arrival_time=time(19, 0),
            pickup_time=time(19, 30),
        )
        assert _pickup_event_date(b) == date(2026, 7, 3)

    def test_H_daytime_legacy_row_returns_pickup_date(self):
        """Legacy row (flight_arrival_date NULL) with daytime arrival: no
        rollover, pickup_date IS the landing day."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 8),
            flight_arrival_time=time(14, 0),
            pickup_time=time(14, 30),
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_no_pickup_date_returns_none(self):
        """Edge of completeness — without pickup_date or flight_arrival_date
        we can't infer anything; return None so the caller skips the link."""
        b = _booking(flight_arrival_date=None, pickup_date=None)
        assert _pickup_event_date(b) is None

    def test_U_missing_times_falls_back_to_pickup_date(self):
        """Legacy row with no arrival/pickup times can't trigger the
        rollover heuristic — falls back to pickup_date safely."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 8),
            flight_arrival_time=None,
            pickup_time=None,
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    # --- EDGE ----------------------------------------------------------------

    def test_E_legacy_rollover_subtracts_one_day(self):
        """flight_arrival_time > pickup_time on a legacy row is the
        overnight-rollover signature — landing was the previous day."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 9),
            flight_arrival_time=time(23, 30),
            pickup_time=time(0, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    def test_E_flight_arrival_date_wins_even_with_rollover_signature(self):
        """If both the canonical column AND the legacy heuristic point at
        different days, the column wins (it's the source of truth)."""
        b = _booking(
            flight_arrival_date=date(2026, 7, 8),
            pickup_date=date(2026, 7, 9),
            flight_arrival_time=time(23, 30),
            pickup_time=time(0, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    # --- BOUNDARY ------------------------------------------------------------
    # Same rollover rule as resolveArrivalDate (frontend) and
    # auto_roster._events_for_booking (engine): triggers when
    # arrival_time > pickup_time on legacy rows.

    def test_B_arrival_one_minute_before_pickup_no_rollover(self):
        """t-ε: 13:59 < 14:00 → arrival not after pickup → no day shift."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 8),
            flight_arrival_time=time(13, 59),
            pickup_time=time(14, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    def test_B_arrival_equal_to_pickup_no_rollover(self):
        """t: 14:00 == 14:00 → not strictly greater → no day shift."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 8),
            flight_arrival_time=time(14, 0),
            pickup_time=time(14, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 8)

    def test_B_arrival_one_minute_after_pickup_rolls_back(self):
        """t+ε: 14:01 > 14:00 → arrival was previous day (overnight)."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 8),
            flight_arrival_time=time(14, 1),
            pickup_time=time(14, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 7)

    def test_B_month_boundary_legacy_rollover(self):
        """Rollover across a month boundary: pickup_date 1 Aug → arrival
        31 Jul when the legacy heuristic fires."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 8, 1),
            flight_arrival_time=time(23, 30),
            pickup_time=time(0, 0),
        )
        assert _pickup_event_date(b) == date(2026, 7, 31)


# ===========================================================================
# vehicle_registration in roster API payloads — unit HUEB
# ===========================================================================

class TestBookingVehicleRegistration:

    # --- HAPPY ---------------------------------------------------------------

    def test_H_vehicle_relationship_registration_wins(self):
        b = _booking(
            vehicle=SimpleNamespace(registration="AB12CDE"),
            vehicle_registration="ZZ99ZZZ",
        )
        assert _booking_vehicle_registration(b) == "AB12CDE"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_missing_registration_returns_none(self):
        b = _booking(vehicle=None, vehicle_registration=None)
        assert _booking_vehicle_registration(b) is None

    # --- EDGE ----------------------------------------------------------------

    def test_E_empty_vehicle_registration_falls_back_to_booking_column(self):
        b = _booking(
            vehicle=SimpleNamespace(registration=""),
            vehicle_registration="EF34GHI",
        )
        assert _booking_vehicle_registration(b) == "EF34GHI"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_magicmock_attributes_are_not_serialized_as_registrations(self):
        """Mocked API tests often use bare MagicMock bookings. The helper must
        ignore non-string placeholder attrs so Pydantic gets None, not a mock."""
        b = MagicMock()
        assert _booking_vehicle_registration(b) is None


# ===========================================================================
# customer phone + vehicle make/colour helpers — unit HUEB (shift card fields)
# ===========================================================================

class TestBookingCustomerPhoneAndVehicleAttrs:

    # --- HAPPY ---------------------------------------------------------------

    def test_H_customer_phone_normalised_to_e164(self):
        b = _booking(customer=SimpleNamespace(phone="07700900123"))
        assert _booking_customer_phone(b) == "+447700900123"

    def test_H_vehicle_make_and_colour_returned(self):
        b = _booking(vehicle=SimpleNamespace(make="Ford", colour="Red"))
        assert _booking_vehicle_attr(b, "make") == "Ford"
        assert _booking_vehicle_attr(b, "colour") == "Red"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_no_customer_returns_none(self):
        assert _booking_customer_phone(_booking(customer=None)) is None

    def test_U_no_vehicle_returns_none(self):
        b = _booking(vehicle=None)
        assert _booking_vehicle_attr(b, "make") is None
        assert _booking_vehicle_attr(b, "colour") is None

    # --- EDGE ----------------------------------------------------------------

    def test_E_empty_phone_returns_none(self):
        assert _booking_customer_phone(_booking(customer=SimpleNamespace(phone=""))) is None

    def test_E_empty_make_returns_none_but_colour_kept(self):
        b = _booking(vehicle=SimpleNamespace(make="", colour="Red"))
        assert _booking_vehicle_attr(b, "make") is None
        assert _booking_vehicle_attr(b, "colour") == "Red"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_magicmock_attrs_not_serialized(self):
        """Bare MagicMock booking → helpers must return None, not a mock."""
        b = MagicMock()
        assert _booking_customer_phone(b) is None
        assert _booking_vehicle_attr(b, "make") is None
        assert _booking_vehicle_attr(b, "colour") is None


# ===========================================================================
# shift_to_response — integration: ensure the link match works end-to-end.
#
# The bug case: shift anchored on flight_arrival_date (7/3); booking.pickup_date
# is 7/2 (un-rolled). Pre-fix, linked_bookings came back empty. Post-fix,
# the booking appears in linked_bookings with type="pickup".
# ===========================================================================

class TestShiftToResponsePickupLinkMatch:

    def _db_mock(self):
        """Minimal MagicMock DB. shift_to_response only calls
        db.query(Booking).filter().first() for the legacy single-FK path,
        which we don't exercise here. Return None so that path is inert."""
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        return db

    # --- HAPPY ---------------------------------------------------------------

    def test_H_link_matches_via_flight_arrival_date_when_pickup_date_differs(self):
        """TAG-KNL95826 regression: shift on 7/3, booking pickup_date=7/2,
        booking flight_arrival_date=7/3 → linked_bookings must include this
        booking with type='pickup'. Pre-fix this returned [] because the
        match looked at pickup_date (7/2) which wasn't in shift_dates."""
        b = _booking(
            id=1286,
            reference="TAG-KNL95826",
            flight_arrival_date=date(2026, 7, 3),
            pickup_date=date(2026, 7, 2),
            flight_arrival_time=time(19, 0),
            pickup_time=time(19, 30),
        )
        s = _shift(
            id=2059,
            date=date(2026, 7, 3),
            end_date=None,
            start_time=time(18, 45),
            end_time=time(19, 45),
            bookings=[b],
        )
        out = shift_to_response(s, self._db_mock())
        refs = [lb.reference for lb in out.bookings]
        assert "TAG-KNL95826" in refs, (
            f"shift card should include the booking; got {refs}"
        )
        link = next(lb for lb in out.bookings if lb.reference == "TAG-KNL95826")
        assert link.type == "pickup"
        # Time shown on the card is the arrival time, per the 2026-05-20 change
        assert link.time == "19:00"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_booking_with_no_pickup_event_date_falls_through(self):
        """A booking that has neither pickup_date nor flight_arrival_date
        (data corruption case) should be silently skipped on the pickup
        side — not crash, not appear as a pickup link."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=None,
            pickup_time=None,
            flight_arrival_time=None,
            dropoff_date=date(2026, 7, 3),  # still has a drop-off so test
        )
        s = _shift(date=date(2026, 7, 3), bookings=[b])
        out = shift_to_response(s, self._db_mock())
        # The drop-off match still picks it up; the pickup branch is inert.
        types = [lb.type for lb in out.bookings]
        assert types.count("pickup") == 0
        assert types.count("dropoff") == 1

    # --- EDGE ----------------------------------------------------------------

    def test_E_overnight_shift_matches_via_end_date_against_arrival(self):
        """Overnight shift: date=7/2, end_date=7/3. Booking lands 7/3 01:30
        with flight_arrival_date=7/3, pickup_time=02:00. Shift_dates =
        {7/2, 7/3}; pickup_event=7/3 ∈ shift_dates → matches."""
        b = _booking(
            flight_arrival_date=date(2026, 7, 3),
            pickup_date=date(2026, 7, 3),
            flight_arrival_time=time(1, 30),
            pickup_time=time(2, 0),
        )
        s = _shift(
            date=date(2026, 7, 2),
            end_date=date(2026, 7, 3),
            start_time=time(21, 30),
            end_time=time(2, 30),
            bookings=[b],
        )
        out = shift_to_response(s, self._db_mock())
        types = [lb.type for lb in out.bookings]
        assert types == ["pickup"]

    def test_E_legacy_row_late_night_arrival_matches_via_rollback(self):
        """Legacy row with flight_arrival_date=NULL and late-night arrival.
        pickup_date=7/9 (rolled forward), pickup_event derives to 7/8. Shift
        date is 7/8 → must still link."""
        b = _booking(
            flight_arrival_date=None,
            pickup_date=date(2026, 7, 9),
            flight_arrival_time=time(23, 30),
            pickup_time=time(0, 0),
        )
        s = _shift(
            date=date(2026, 7, 8),
            end_date=date(2026, 7, 9),
            start_time=time(22, 30),
            end_time=time(0, 30),
            bookings=[b],
        )
        out = shift_to_response(s, self._db_mock())
        assert [lb.type for lb in out.bookings] == ["pickup"]

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_booking_pickup_date_on_shift_dates_but_arrival_not_no_double_link(self):
        """Boundary: if (somehow) only pickup_date matches and arrival_date
        doesn't, the pickup-event-date check correctly skips. This locks in
        that the fix didn't accidentally widen the match — it tightened it
        to the canonical date."""
        b = _booking(
            flight_arrival_date=date(2026, 7, 3),  # canonical event day
            pickup_date=date(2026, 7, 2),
            flight_arrival_time=time(19, 0),
            pickup_time=time(19, 30),
        )
        # Shift on 7/2 (pickup_date day) — should NOT link as a pickup
        # because the canonical event date is 7/3.
        s = _shift(date=date(2026, 7, 2), bookings=[b])
        out = shift_to_response(s, self._db_mock())
        assert [lb.type for lb in out.bookings] == []

    def test_B_only_one_link_per_booking_even_when_dates_collide(self):
        """When dropoff_date and pickup_event happen to share a day (rare,
        but e.g. a same-day turnaround), the dropoff branch wins via the
        `elif` — exactly one link per booking, not two."""
        same_day = date(2026, 7, 5)
        b = _booking(
            dropoff_date=same_day,
            flight_arrival_date=same_day,
            pickup_date=same_day,
        )
        s = _shift(date=same_day, bookings=[b])
        out = shift_to_response(s, self._db_mock())
        assert len(out.bookings) == 1
        # dropoff branch matches first
        assert out.bookings[0].type == "dropoff"


# ===========================================================================
# vehicle_registration in roster API payloads — integration HUEB
# ===========================================================================

class TestShiftToResponseVehicleRegistration:

    def _db_mock(self, booking=None):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = booking
        db.query.return_value = chain
        return db

    # --- HAPPY ---------------------------------------------------------------

    def test_H_many_to_many_dropoff_includes_vehicle_registration_and_legacy_field(self):
        b = _booking(
            id=77,
            reference="TAG-REGHAPPY",
            dropoff_date=date(2026, 7, 2),
            vehicle=SimpleNamespace(registration="HX24TAG"),
        )
        s = _shift(date=date(2026, 7, 2), bookings=[b])

        out = shift_to_response(s, self._db_mock())

        assert out.bookings[0].vehicle_registration == "HX24TAG"
        assert out.booking_vehicle_registration == "HX24TAG"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_cancelled_booking_registration_is_not_returned(self):
        b = _booking(
            reference="TAG-CANCELLED",
            dropoff_date=date(2026, 7, 2),
            status=BookingStatus.CANCELLED,
            vehicle=SimpleNamespace(registration="NO00SHOW"),
        )
        s = _shift(date=date(2026, 7, 2), bookings=[b])

        out = shift_to_response(s, self._db_mock())

        assert out.bookings == []
        assert out.booking_vehicle_registration is None

    # --- EDGE ----------------------------------------------------------------

    def test_E_legacy_booking_id_path_uses_booking_vehicle_registration_column(self):
        b = _booking(
            id=88,
            reference="TAG-LEGACYREG",
            dropoff_date=date(2026, 7, 2),
            vehicle=None,
            vehicle_registration="LG55ACY",
        )
        s = _shift(date=date(2026, 7, 2), booking_id=88, bookings=[])

        out = shift_to_response(s, self._db_mock(booking=b))

        assert out.bookings[0].vehicle_registration == "LG55ACY"
        assert out.booking_vehicle_registration == "LG55ACY"

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_pickup_link_on_arrival_date_carries_vehicle_registration(self):
        b = _booking(
            id=99,
            reference="TAG-PICKUPREG",
            dropoff_date=date(2026, 7, 1),
            flight_arrival_date=date(2026, 7, 3),
            pickup_date=date(2026, 7, 3),
            flight_arrival_time=time(0, 0),
            pickup_time=time(0, 30),
            vehicle=SimpleNamespace(registration="PX00MID"),
        )
        s = _shift(
            date=date(2026, 7, 3),
            start_time=time(0, 0),
            end_time=time(1, 0),
            bookings=[b],
        )

        out = shift_to_response(s, self._db_mock())

        assert out.bookings[0].type == "pickup"
        assert out.bookings[0].vehicle_registration == "PX00MID"
        assert out.booking_vehicle_registration == "PX00MID"


# ===========================================================================
# shift_to_response — customer phone + vehicle make/colour on each link
# ===========================================================================

class TestShiftToResponseCustomerVehicleDetails:

    def _db_mock(self):
        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = None
        db.query.return_value = chain
        return db

    # --- HAPPY ---------------------------------------------------------------

    def test_H_dropoff_link_carries_phone_make_colour(self):
        b = _booking(
            id=620,
            reference="TAG-DETAILS",
            dropoff_date=date(2026, 7, 2),
            customer=SimpleNamespace(phone="07700900123"),
            vehicle=SimpleNamespace(registration="HX24TAG", make="Ford", colour="Red"),
        )
        s = _shift(date=date(2026, 7, 2), bookings=[b])
        lb = shift_to_response(s, self._db_mock()).bookings[0]
        assert lb.customer_phone == "+447700900123"
        assert lb.vehicle_make == "Ford"
        assert lb.vehicle_colour == "Red"

    # --- UNHAPPY -------------------------------------------------------------

    def test_U_missing_customer_and_vehicle_leave_fields_none(self):
        b = _booking(
            id=621,
            reference="TAG-NODETAILS",
            dropoff_date=date(2026, 7, 2),
            customer=None,
            vehicle=None,
        )
        s = _shift(date=date(2026, 7, 2), bookings=[b])
        lb = shift_to_response(s, self._db_mock()).bookings[0]
        assert lb.customer_phone is None
        assert lb.vehicle_make is None
        assert lb.vehicle_colour is None

    # --- BOUNDARY ------------------------------------------------------------

    def test_B_pickup_link_also_carries_details(self):
        b = _booking(
            id=622,
            reference="TAG-PICKDETAILS",
            dropoff_date=date(2026, 7, 1),
            flight_arrival_date=date(2026, 7, 3),
            pickup_date=date(2026, 7, 3),
            flight_arrival_time=time(0, 0),
            pickup_time=time(0, 30),
            customer=SimpleNamespace(phone="+447911123456"),
            vehicle=SimpleNamespace(registration="PX00MID", make="Audi", colour="Black"),
        )
        s = _shift(date=date(2026, 7, 3), start_time=time(0, 0), end_time=time(1, 0), bookings=[b])
        lb = shift_to_response(s, self._db_mock()).bookings[0]
        assert lb.type == "pickup"
        assert lb.customer_phone == "+447911123456"
        assert lb.vehicle_make == "Audi"
        assert lb.vehicle_colour == "Black"


# ===========================================================================
# GET /api/roster JSON payload — integration HUEB target for this API update
# ===========================================================================

class TestRosterVehicleRegistrationApi:

    def test_H_get_roster_serializes_vehicle_registration_fields(self):
        """Real FastAPI route + response serialization: the shift detail payload
        includes both `bookings[].vehicle_registration` and the legacy
        `booking_vehicle_registration` field used by older calendar clients."""
        from fastapi.testclient import TestClient
        from database import get_db
        from main import app
        from routers.roster import require_admin

        b = _booking(
            id=515,
            reference="TAG-APIREG",
            dropoff_date=date(2026, 7, 2),
            vehicle=SimpleNamespace(registration="AP24REG"),
        )
        shift = _shift(id=404, date=date(2026, 7, 2), bookings=[b])

        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [shift]

        db = MagicMock()
        db.query.return_value = query

        def db_override():
            yield db

        admin = SimpleNamespace(id=1, is_admin=True, email="admin@tag.test")
        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_db] = db_override
        try:
            response = TestClient(app).get("/api/roster?source=all&date=2026-07-02")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["bookings"][0]["vehicle_registration"] == "AP24REG"
        assert payload[0]["booking_vehicle_registration"] == "AP24REG"

    def test_H_get_roster_serializes_customer_phone_make_colour(self):
        """The shift card payload exposes customer_phone + vehicle make/colour
        so the roster/employee card can render Name/Phone, Reg/Make/Colour."""
        from fastapi.testclient import TestClient
        from database import get_db
        from main import app
        from routers.roster import require_admin

        b = _booking(
            id=516,
            reference="TAG-APIDETAILS",
            dropoff_date=date(2026, 7, 2),
            customer=SimpleNamespace(phone="07700900123"),
            vehicle=SimpleNamespace(registration="AP24REG", make="Ford", colour="Red"),
        )
        shift = _shift(id=405, date=date(2026, 7, 2), bookings=[b])

        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [shift]
        db = MagicMock()
        db.query.return_value = query

        def db_override():
            yield db

        admin = SimpleNamespace(id=1, is_admin=True, email="admin@tag.test")
        app.dependency_overrides[require_admin] = lambda: admin
        app.dependency_overrides[get_db] = db_override
        try:
            response = TestClient(app).get("/api/roster?source=all&date=2026-07-02")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        booking_json = response.json()[0]["bookings"][0]
        assert booking_json["customer_phone"] == "+447700900123"
        assert booking_json["vehicle_make"] == "Ford"
        assert booking_json["vehicle_colour"] == "Red"
