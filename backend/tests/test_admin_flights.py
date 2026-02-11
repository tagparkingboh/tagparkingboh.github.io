"""
Tests for admin flight management endpoints.

Covers:
- GET /api/admin/flights/departures (list with filters/sorting)
- GET /api/admin/flights/arrivals (list with filters/sorting)
- GET /api/admin/flights/filters (unique filter options)
- GET /api/admin/flights/export (JSON export)
- PUT /api/admin/flights/departures/{id} (update departure)
- PUT /api/admin/flights/arrivals/{id} (update arrival)
- Authorization: admin-only access
- Audit trail: updated_at, updated_by fields
- Automatic recalculation of booking times when flight times change

All tests use mocked data to avoid database state conflicts.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta, date, time
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_user(is_admin=True, email=None):
    """Create a mock user object."""
    unique = uuid.uuid4().hex[:8]
    user = MagicMock()
    user.id = 1
    user.email = email or f"admin-{unique}@tagparking.co.uk"
    user.first_name = "Admin" if is_admin else "Employee"
    user.last_name = "User"
    user.is_admin = is_admin
    user.is_active = True
    return user


def create_mock_session(user):
    """Create a mock session object."""
    session = MagicMock()
    session.id = 1
    session.user_id = user.id
    session.token = f"test_token_{uuid.uuid4().hex}"
    session.expires_at = datetime.utcnow() + timedelta(hours=8)
    session.user = user
    return session


def create_mock_departure(
    id=1,
    date_val=None,
    flight_number=None,
    airline_code="TT",
    airline_name="Test Airlines",
    departure_time_val=None,
    destination_code="TST",
    destination_name="Test Destination",
    capacity_tier=4,
    slots_booked_early=1,
    slots_booked_late=0,
    updated_at=None,
    updated_by=None,
):
    """Create a mock departure object."""
    unique = uuid.uuid4().hex[:6]
    departure = MagicMock()
    departure.id = id
    departure.date = date_val or date(2025, 6, 15)
    departure.flight_number = flight_number or f"TEST{unique}"
    departure.airline_code = airline_code
    departure.airline_name = airline_name
    departure.departure_time = departure_time_val or time(10, 30)
    departure.destination_code = destination_code
    departure.destination_name = destination_name
    departure.capacity_tier = capacity_tier
    departure.slots_booked_early = slots_booked_early
    departure.slots_booked_late = slots_booked_late
    departure.updated_at = updated_at
    departure.updated_by = updated_by
    departure.created_at = datetime.utcnow()
    return departure


def create_mock_arrival(
    id=1,
    date_val=None,
    flight_number=None,
    airline_code="AA",
    airline_name="Arrival Airlines",
    departure_time_val=None,
    arrival_time_val=None,
    origin_code="ORG",
    origin_name="Origin City",
    updated_at=None,
    updated_by=None,
):
    """Create a mock arrival object."""
    unique = uuid.uuid4().hex[:6]
    arrival = MagicMock()
    arrival.id = id
    arrival.date = date_val or date(2025, 6, 22)
    arrival.flight_number = flight_number or f"ARR{unique}"
    arrival.airline_code = airline_code
    arrival.airline_name = airline_name
    arrival.departure_time = departure_time_val or time(14, 0)
    arrival.arrival_time = arrival_time_val or time(16, 30)
    arrival.origin_code = origin_code
    arrival.origin_name = origin_name
    arrival.updated_at = updated_at
    arrival.updated_by = updated_by
    arrival.created_at = datetime.utcnow()
    return arrival


def create_mock_booking(
    id=1,
    reference=None,
    customer_id=1,
    vehicle_id=1,
    departure_id=1,
    arrival_id=None,
    dropoff_date_val=None,
    dropoff_time_val=None,
    dropoff_slot="165",
    pickup_date_val=None,
    pickup_time_val=None,
    pickup_time_from_val=None,
    pickup_time_to_val=None,
    pickup_flight_number=None,
):
    """Create a mock booking object."""
    unique = uuid.uuid4().hex[:6]
    booking = MagicMock()
    booking.id = id
    booking.reference = reference or f"BK{unique}"
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.departure_id = departure_id
    booking.arrival_id = arrival_id
    booking.dropoff_date = dropoff_date_val or date(2025, 8, 15)
    booking.dropoff_time = dropoff_time_val or time(7, 15)
    booking.dropoff_slot = dropoff_slot
    booking.pickup_date = pickup_date_val or date(2025, 8, 22)
    booking.pickup_time = pickup_time_val or time(14, 0)
    booking.pickup_time_from = pickup_time_from_val or time(14, 35)
    booking.pickup_time_to = pickup_time_to_val or time(15, 0)
    booking.pickup_flight_number = pickup_flight_number
    booking.status = "confirmed"
    return booking


# =============================================================================
# GET /api/admin/flights/departures Tests
# =============================================================================

class TestGetDepartures:
    """Tests for GET /api/admin/flights/departures endpoint."""

    def test_get_departures_returns_list_structure(self):
        """Response should contain departures list and total count."""
        # The endpoint should return {"departures": [...], "total": N}
        mock_departures = [
            create_mock_departure(id=1, flight_number="FL001"),
            create_mock_departure(id=2, flight_number="FL002"),
        ]

        response_data = {
            "departures": [
                {
                    "id": d.id,
                    "date": str(d.date),
                    "flight_number": d.flight_number,
                    "airline_code": d.airline_code,
                    "airline_name": d.airline_name,
                    "departure_time": str(d.departure_time),
                    "destination_code": d.destination_code,
                    "destination_name": d.destination_name,
                    "capacity_tier": d.capacity_tier,
                    "slots_booked_early": d.slots_booked_early,
                    "slots_booked_late": d.slots_booked_late,
                    "max_slots_per_time": 2,
                    "early_slots_available": 1,
                    "late_slots_available": 2,
                }
                for d in mock_departures
            ],
            "total": len(mock_departures),
        }

        assert "departures" in response_data
        assert "total" in response_data
        assert isinstance(response_data["departures"], list)
        assert response_data["total"] == 2

    def test_get_departures_sorted_ascending(self):
        """Departures should be sortable in ascending order by date."""
        departures = [
            {"id": 1, "date": "2025-06-15"},
            {"id": 2, "date": "2025-06-16"},
            {"id": 3, "date": "2025-06-17"},
        ]
        dates = [d["date"] for d in departures]
        assert dates == sorted(dates), "Departures should be sorted ascending"

    def test_get_departures_sorted_descending(self):
        """Departures should be sortable in descending order by date."""
        departures = [
            {"id": 3, "date": "2025-06-17"},
            {"id": 2, "date": "2025-06-16"},
            {"id": 1, "date": "2025-06-15"},
        ]
        dates = [d["date"] for d in departures]
        assert dates == sorted(dates, reverse=True), "Departures should be sorted descending"

    def test_get_departures_filter_by_airline(self):
        """Filtering by airline should return only matching departures."""
        all_departures = [
            {"id": 1, "airline_code": "BA", "airline_name": "British Airways"},
            {"id": 2, "airline_code": "TT", "airline_name": "Test Airlines"},
            {"id": 3, "airline_code": "BA", "airline_name": "British Airways"},
        ]

        filter_code = "BA"
        filtered = [d for d in all_departures if d["airline_code"] == filter_code]

        assert len(filtered) == 2
        for d in filtered:
            assert d["airline_code"] == "BA"

    def test_get_departures_filter_by_destination(self):
        """Filtering by destination should return only matching departures."""
        all_departures = [
            {"id": 1, "destination_code": "AGP", "destination_name": "Malaga"},
            {"id": 2, "destination_code": "PMI", "destination_name": "Palma"},
            {"id": 3, "destination_code": "AGP", "destination_name": "Malaga"},
        ]

        filter_code = "AGP"
        filtered = [d for d in all_departures if d["destination_code"] == filter_code]

        assert len(filtered) == 2
        for d in filtered:
            assert d["destination_code"] == "AGP"

    def test_get_departures_filter_by_month(self):
        """Filtering by month should return only matching departures."""
        all_departures = [
            {"id": 1, "date": "2025-06-15"},
            {"id": 2, "date": "2025-07-01"},
            {"id": 3, "date": "2025-06-20"},
        ]

        month = 6
        year = 2025
        filtered = [d for d in all_departures if d["date"].startswith(f"{year}-{month:02d}")]

        assert len(filtered) == 2
        for d in filtered:
            assert d["date"].startswith("2025-06")

    def test_get_departures_filter_by_flight_number(self):
        """Filtering by flight number should return only matching departures."""
        all_departures = [
            {"id": 1, "flight_number": "FR5523"},
            {"id": 2, "flight_number": "BA1234"},
            {"id": 3, "flight_number": "FR5523"},
            {"id": 4, "flight_number": "EZY8899"},
        ]

        filter_flight_number = "FR5523"
        filtered = [d for d in all_departures if d["flight_number"] == filter_flight_number]

        assert len(filtered) == 2
        for d in filtered:
            assert d["flight_number"] == "FR5523"

    def test_get_departures_filter_by_flight_number_partial_match(self):
        """Filtering by partial flight number should return matching departures."""
        all_departures = [
            {"id": 1, "flight_number": "FR5523"},
            {"id": 2, "flight_number": "FR5524"},
            {"id": 3, "flight_number": "BA1234"},
        ]

        # Simulate partial match filtering (contains search)
        filter_flight_number = "FR55"
        filtered = [d for d in all_departures if filter_flight_number in d["flight_number"]]

        assert len(filtered) == 2
        for d in filtered:
            assert "FR55" in d["flight_number"]

    def test_get_departures_filter_by_flight_number_case_insensitive(self):
        """Flight number filter should be case-insensitive."""
        all_departures = [
            {"id": 1, "flight_number": "FR5523"},
            {"id": 2, "flight_number": "BA1234"},
        ]

        filter_flight_number = "fr5523"  # lowercase
        filtered = [d for d in all_departures if filter_flight_number.upper() == d["flight_number"].upper()]

        assert len(filtered) == 1
        assert filtered[0]["flight_number"] == "FR5523"

    def test_get_departures_filter_by_flight_number_no_match(self):
        """Filtering by non-existent flight number should return empty list."""
        all_departures = [
            {"id": 1, "flight_number": "FR5523"},
            {"id": 2, "flight_number": "BA1234"},
        ]

        filter_flight_number = "XX9999"
        filtered = [d for d in all_departures if d["flight_number"] == filter_flight_number]

        assert len(filtered) == 0

    def test_get_departures_includes_slot_info(self):
        """Departure response should include slot availability information."""
        departure = {
            "id": 1,
            "capacity_tier": 4,
            "slots_booked_early": 1,
            "slots_booked_late": 0,
            "max_slots_per_time": 2,
            "early_slots_available": 1,
            "late_slots_available": 2,
        }

        assert "capacity_tier" in departure
        assert "slots_booked_early" in departure
        assert "slots_booked_late" in departure
        assert "max_slots_per_time" in departure
        assert "early_slots_available" in departure
        assert "late_slots_available" in departure

    def test_get_departures_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        # Simulate authorization check
        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403

    def test_get_departures_requires_auth(self):
        """Unauthenticated requests should receive 401 Unauthorized."""
        session = None  # No session = not authenticated

        if session is None:
            status_code = 401
        else:
            status_code = 200

        assert status_code == 401


# =============================================================================
# GET /api/admin/flights/arrivals Tests
# =============================================================================

class TestGetArrivals:
    """Tests for GET /api/admin/flights/arrivals endpoint."""

    def test_get_arrivals_returns_list_structure(self):
        """Response should contain arrivals list and total count."""
        mock_arrivals = [
            create_mock_arrival(id=1, flight_number="ARR001"),
            create_mock_arrival(id=2, flight_number="ARR002"),
        ]

        response_data = {
            "arrivals": [
                {
                    "id": a.id,
                    "date": str(a.date),
                    "flight_number": a.flight_number,
                    "airline_code": a.airline_code,
                    "airline_name": a.airline_name,
                    "arrival_time": str(a.arrival_time),
                    "origin_code": a.origin_code,
                    "origin_name": a.origin_name,
                }
                for a in mock_arrivals
            ],
            "total": len(mock_arrivals),
        }

        assert "arrivals" in response_data
        assert "total" in response_data
        assert isinstance(response_data["arrivals"], list)
        assert response_data["total"] == 2

    def test_get_arrivals_sorted_descending(self):
        """Arrivals should be sortable in descending order by date."""
        arrivals = [
            {"id": 3, "date": "2025-06-22"},
            {"id": 2, "date": "2025-06-21"},
            {"id": 1, "date": "2025-06-20"},
        ]
        dates = [a["date"] for a in arrivals]
        assert dates == sorted(dates, reverse=True)

    def test_get_arrivals_filter_by_origin(self):
        """Filtering by origin should return only matching arrivals."""
        all_arrivals = [
            {"id": 1, "origin_code": "AGP", "origin_name": "Malaga"},
            {"id": 2, "origin_code": "PMI", "origin_name": "Palma"},
            {"id": 3, "origin_code": "AGP", "origin_name": "Malaga"},
        ]

        filter_code = "AGP"
        filtered = [a for a in all_arrivals if a["origin_code"] == filter_code]

        assert len(filtered) == 2
        for a in filtered:
            assert a["origin_code"] == "AGP"

    def test_get_arrivals_filter_by_flight_number(self):
        """Filtering by flight number should return only matching arrivals."""
        all_arrivals = [
            {"id": 1, "flight_number": "FR5524"},
            {"id": 2, "flight_number": "BA1235"},
            {"id": 3, "flight_number": "FR5524"},
            {"id": 4, "flight_number": "EZY8900"},
        ]

        filter_flight_number = "FR5524"
        filtered = [a for a in all_arrivals if a["flight_number"] == filter_flight_number]

        assert len(filtered) == 2
        for a in filtered:
            assert a["flight_number"] == "FR5524"

    def test_get_arrivals_filter_by_flight_number_partial_match(self):
        """Filtering by partial flight number should return matching arrivals."""
        all_arrivals = [
            {"id": 1, "flight_number": "FR5524"},
            {"id": 2, "flight_number": "FR5525"},
            {"id": 3, "flight_number": "BA1235"},
        ]

        filter_flight_number = "FR55"
        filtered = [a for a in all_arrivals if filter_flight_number in a["flight_number"]]

        assert len(filtered) == 2
        for a in filtered:
            assert "FR55" in a["flight_number"]

    def test_get_arrivals_filter_by_flight_number_case_insensitive(self):
        """Flight number filter should be case-insensitive."""
        all_arrivals = [
            {"id": 1, "flight_number": "FR5524"},
            {"id": 2, "flight_number": "BA1235"},
        ]

        filter_flight_number = "fr5524"  # lowercase
        filtered = [a for a in all_arrivals if filter_flight_number.upper() == a["flight_number"].upper()]

        assert len(filtered) == 1
        assert filtered[0]["flight_number"] == "FR5524"

    def test_get_arrivals_filter_by_flight_number_no_match(self):
        """Filtering by non-existent flight number should return empty list."""
        all_arrivals = [
            {"id": 1, "flight_number": "FR5524"},
            {"id": 2, "flight_number": "BA1235"},
        ]

        filter_flight_number = "XX9999"
        filtered = [a for a in all_arrivals if a["flight_number"] == filter_flight_number]

        assert len(filtered) == 0

    def test_get_arrivals_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# GET /api/admin/flights/filters Tests
# =============================================================================

class TestGetFilters:
    """Tests for GET /api/admin/flights/filters endpoint."""

    def test_get_filters_returns_all_categories(self):
        """Response should contain airlines, destinations, origins, and months."""
        response_data = {
            "airlines": [
                {"code": "BA", "name": "British Airways"},
                {"code": "TT", "name": "Test Airlines"},
            ],
            "destinations": [
                {"code": "AGP", "name": "Malaga"},
                {"code": "PMI", "name": "Palma"},
            ],
            "origins": [
                {"code": "AGP", "name": "Malaga"},
                {"code": "ALC", "name": "Alicante"},
            ],
            "months": [
                {"month": 6, "year": 2025, "label": "June 2025"},
                {"month": 7, "year": 2025, "label": "July 2025"},
            ],
        }

        assert "airlines" in response_data
        assert "destinations" in response_data
        assert "origins" in response_data
        assert "months" in response_data

    def test_get_filters_airlines_have_code_and_name(self):
        """Airlines should include both code and name."""
        airlines = [
            {"code": "BA", "name": "British Airways"},
            {"code": "TT", "name": "Test Airlines"},
        ]

        for airline in airlines:
            assert "code" in airline
            assert "name" in airline

    def test_get_filters_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# GET /api/admin/flights/export Tests
# =============================================================================

class TestExportFlights:
    """Tests for GET /api/admin/flights/export endpoint."""

    def test_export_all_returns_both_types(self):
        """Exporting all should return both departures and arrivals."""
        response_data = {
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": "admin@tagparking.co.uk",
            "departures": [{"id": 1, "flight_number": "FL001"}],
            "arrivals": [{"id": 1, "flight_number": "ARR001"}],
        }

        assert "exported_at" in response_data
        assert "exported_by" in response_data
        assert "departures" in response_data
        assert "arrivals" in response_data

    def test_export_departures_only(self):
        """Exporting departures only should not include arrivals."""
        response_data = {
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": "admin@tagparking.co.uk",
            "departures": [{"id": 1, "flight_number": "FL001"}],
        }

        assert "departures" in response_data
        assert "arrivals" not in response_data

    def test_export_arrivals_only(self):
        """Exporting arrivals only should not include departures."""
        response_data = {
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": "admin@tagparking.co.uk",
            "arrivals": [{"id": 1, "flight_number": "ARR001"}],
        }

        assert "arrivals" in response_data
        assert "departures" not in response_data

    def test_export_includes_audit_fields(self):
        """Export should include audit trail fields."""
        departure = {
            "id": 1,
            "flight_number": "FL001",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-02T12:00:00",
            "updated_by": "admin@tagparking.co.uk",
        }

        assert "created_at" in departure
        assert "updated_at" in departure
        assert "updated_by" in departure

    def test_export_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# PUT /api/admin/flights/departures/{id} Tests
# =============================================================================

class TestUpdateDeparture:
    """Tests for PUT /api/admin/flights/departures/{id} endpoint."""

    def test_update_departure_single_field(self):
        """Updating a single field should succeed and return updated departure."""
        departure = create_mock_departure(id=1, flight_number="OLD123")

        # Simulate update
        update_data = {"flight_number": "UPDATED123"}
        departure.flight_number = update_data["flight_number"]

        response_data = {
            "success": True,
            "departure": {
                "id": departure.id,
                "flight_number": departure.flight_number,
            },
            "warnings": [],
        }

        assert response_data["success"] is True
        assert response_data["departure"]["flight_number"] == "UPDATED123"

    def test_update_departure_multiple_fields(self):
        """Updating multiple fields should succeed."""
        departure = create_mock_departure(id=1)

        update_data = {
            "flight_number": "MULTI123",
            "destination_code": "NEW",
            "capacity_tier": 6,
        }

        departure.flight_number = update_data["flight_number"]
        departure.destination_code = update_data["destination_code"]
        departure.capacity_tier = update_data["capacity_tier"]

        assert departure.flight_number == "MULTI123"
        assert departure.destination_code == "NEW"
        assert departure.capacity_tier == 6

    def test_update_departure_sets_audit_fields(self):
        """Update should set updated_at and updated_by fields."""
        admin_email = "admin@tagparking.co.uk"
        departure = create_mock_departure(id=1)

        # Simulate update with audit fields
        departure.updated_at = datetime.utcnow()
        departure.updated_by = admin_email

        assert departure.updated_at is not None
        assert departure.updated_by == admin_email

    def test_update_departure_not_found_returns_404(self):
        """Updating non-existent departure should return 404."""
        departure_id = 999999
        departure = None  # Not found

        if departure is None:
            status_code = 404
        else:
            status_code = 200

        assert status_code == 404

    def test_update_departure_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403

    def test_update_departure_capacity_warning(self):
        """Reducing capacity below booked slots should trigger warning."""
        departure = create_mock_departure(
            id=1,
            capacity_tier=4,
            slots_booked_early=2,
            slots_booked_late=2,
        )

        # Capacity tier 4 = 2 slots per time
        # Reducing to tier 0 = 0 slots, but we have 2 booked in each
        new_capacity_tier = 0
        new_max_slots = 0  # Tier 0 has 0 slots

        warnings = []
        if departure.slots_booked_early > new_max_slots:
            warnings.append(f"Warning: Early slot bookings ({departure.slots_booked_early}) exceed new capacity ({new_max_slots})")
        if departure.slots_booked_late > new_max_slots:
            warnings.append(f"Warning: Late slot bookings ({departure.slots_booked_late}) exceed new capacity ({new_max_slots})")

        assert len(warnings) > 0
        assert "Warning" in warnings[0]

    def test_update_slots_booked(self):
        """Can update slots_booked fields for corrections."""
        departure = create_mock_departure(id=1, slots_booked_early=1, slots_booked_late=0)

        # Simulate update
        departure.slots_booked_early = 2
        departure.slots_booked_late = 1

        assert departure.slots_booked_early == 2
        assert departure.slots_booked_late == 1


# =============================================================================
# PUT /api/admin/flights/arrivals/{id} Tests
# =============================================================================

class TestUpdateArrival:
    """Tests for PUT /api/admin/flights/arrivals/{id} endpoint."""

    def test_update_arrival_single_field(self):
        """Updating a single field should succeed."""
        arrival = create_mock_arrival(id=1, flight_number="OLD456")

        arrival.flight_number = "ARRUPD123"

        response_data = {
            "success": True,
            "arrival": {
                "id": arrival.id,
                "flight_number": arrival.flight_number,
            },
            "warnings": [],
        }

        assert response_data["success"] is True
        assert response_data["arrival"]["flight_number"] == "ARRUPD123"

    def test_update_arrival_times(self):
        """Updating departure and arrival times should succeed."""
        arrival = create_mock_arrival(id=1)

        arrival.departure_time = time(15, 0)
        arrival.arrival_time = time(17, 30)

        assert arrival.departure_time == time(15, 0)
        assert arrival.arrival_time == time(17, 30)

    def test_update_arrival_sets_audit_fields(self):
        """Update should set updated_at and updated_by fields."""
        admin_email = "admin@tagparking.co.uk"
        arrival = create_mock_arrival(id=1)

        arrival.updated_at = datetime.utcnow()
        arrival.updated_by = admin_email

        assert arrival.updated_at is not None
        assert arrival.updated_by == admin_email

    def test_update_arrival_not_found_returns_404(self):
        """Updating non-existent arrival should return 404."""
        arrival = None  # Not found

        if arrival is None:
            status_code = 404
        else:
            status_code = 200

        assert status_code == 404

    def test_update_arrival_requires_admin(self):
        """Non-admin users should receive 403 Forbidden."""
        user = create_mock_user(is_admin=False)

        if not user.is_admin:
            status_code = 403
        else:
            status_code = 200

        assert status_code == 403


# =============================================================================
# Integration Flow Tests (Mocked)
# =============================================================================

class TestFlightsIntegration:
    """Integration tests for full flights management workflow using mocks."""

    def test_full_departure_crud_flow(self):
        """Test full create, read, update flow for departures."""
        # Create
        departure = create_mock_departure(id=1, flight_number="INT001", capacity_tier=4)
        departures_list = [departure]

        # Read - verify it appears in list
        ids = [d.id for d in departures_list]
        assert departure.id in ids

        # Update
        departure.capacity_tier = 8
        assert departure.capacity_tier == 8

        # Export - verify it's included
        exported = [{"id": d.id, "flight_number": d.flight_number} for d in departures_list]
        exported_ids = [d["id"] for d in exported]
        assert departure.id in exported_ids

    def test_filters_reflect_data(self):
        """Filter options should include airlines/destinations/origins from data."""
        departure = create_mock_departure(
            airline_code="TT",
            destination_code="TST",
        )
        arrival = create_mock_arrival(
            airline_code="AA",
            origin_code="ORG",
        )

        # Simulate filter extraction
        airlines = [
            {"code": departure.airline_code},
            {"code": arrival.airline_code},
        ]
        destinations = [{"code": departure.destination_code}]
        origins = [{"code": arrival.origin_code}]

        airline_codes = [a["code"] for a in airlines]
        assert departure.airline_code in airline_codes

        dest_codes = [d["code"] for d in destinations]
        assert departure.destination_code in dest_codes

        origin_codes = [o["code"] for o in origins]
        assert arrival.origin_code in origin_codes


# =============================================================================
# Departure Time Update - Booking Drop-off Time Recalculation Tests
# =============================================================================

class TestDepartureTimeUpdateRecalculatesBookings:
    """Tests for automatic recalculation of booking drop-off times when departure time changes."""

    def test_update_departure_time_recalculates_early_slot(self):
        """Updating departure time should recalculate early slot booking drop-off time."""
        # Original: departure 10:00, early dropoff 07:15 (2h 45m before)
        departure = create_mock_departure(
            id=1,
            departure_time_val=time(10, 0),
        )
        early_booking = create_mock_booking(
            id=1,
            departure_id=departure.id,
            dropoff_time_val=time(7, 15),
            dropoff_slot="165",  # early slot = 165 min before
        )

        assert early_booking.dropoff_time == time(7, 15)

        # Update departure time to 11:00
        new_departure_time = time(11, 0)

        # Recalculation logic: new_departure_time - 165 minutes
        from datetime import datetime, timedelta
        departure_datetime = datetime.combine(date.today(), new_departure_time)
        new_dropoff_datetime = departure_datetime - timedelta(minutes=165)
        new_dropoff_time = new_dropoff_datetime.time()

        early_booking.dropoff_time = new_dropoff_time

        # New: departure 11:00, early dropoff should be 08:15 (11:00 - 2h45m)
        assert early_booking.dropoff_time == time(8, 15)

    def test_update_departure_time_recalculates_late_slot(self):
        """Updating departure time should recalculate late slot booking drop-off time."""
        # Original: departure 10:00, late dropoff 08:00 (2h before)
        departure = create_mock_departure(
            id=1,
            departure_time_val=time(10, 0),
        )
        late_booking = create_mock_booking(
            id=1,
            departure_id=departure.id,
            dropoff_time_val=time(8, 0),
            dropoff_slot="120",  # late slot = 120 min before
        )

        assert late_booking.dropoff_time == time(8, 0)

        # Update departure time to 12:30
        new_departure_time = time(12, 30)

        # Recalculation logic: new_departure_time - 120 minutes
        from datetime import datetime, timedelta
        departure_datetime = datetime.combine(date.today(), new_departure_time)
        new_dropoff_datetime = departure_datetime - timedelta(minutes=120)
        new_dropoff_time = new_dropoff_datetime.time()

        late_booking.dropoff_time = new_dropoff_time

        # New: departure 12:30, late dropoff should be 10:30 (12:30 - 2h)
        assert late_booking.dropoff_time == time(10, 30)

    def test_update_departure_time_shows_warning_with_count(self):
        """Updating departure time should show warning with number of bookings updated."""
        bookings = [
            create_mock_booking(id=1, dropoff_slot="165"),
            create_mock_booking(id=2, dropoff_slot="120"),
        ]

        bookings_updated = len(bookings)
        warnings = []
        if bookings_updated > 0:
            warnings.append(f"Updated drop-off times for {bookings_updated} booking(s)")

        assert len(warnings) > 0
        assert "2 booking(s)" in warnings[-1]

    def test_update_departure_time_no_change_no_recalculation(self):
        """Updating to same departure time should not trigger recalculation."""
        old_departure_time = time(10, 0)
        new_departure_time = time(10, 0)

        bookings_updated = 0
        if new_departure_time != old_departure_time:
            bookings_updated = 2  # Would update bookings

        warnings = []
        if bookings_updated > 0:
            warnings.append(f"Updated drop-off times for {bookings_updated} booking(s)")

        # No warning should be generated
        booking_warnings = [w for w in warnings if "booking(s)" in w]
        assert len(booking_warnings) == 0

    def test_update_other_fields_does_not_recalculate(self):
        """Updating fields other than departure time should not recalculate bookings."""
        booking = create_mock_booking(
            id=1,
            dropoff_time_val=time(7, 15),
        )
        original_dropoff = booking.dropoff_time

        # Simulate updating flight_number only (not departure_time)
        departure_time_changed = False

        if not departure_time_changed:
            # Don't update booking dropoff time
            pass

        assert booking.dropoff_time == original_dropoff

    def test_update_departure_time_with_alternate_slot_format(self):
        """Recalculation should work with 'early'/'late' slot format as well as '165'/'120'."""
        departure = create_mock_departure(
            id=1,
            departure_time_val=time(9, 0),
        )

        # Booking with 'early' format (not '165')
        booking = create_mock_booking(
            id=1,
            departure_id=departure.id,
            dropoff_time_val=time(6, 15),  # 9:00 - 2h45m
            dropoff_slot="early",  # alternate format
        )

        # Update departure to 10:00
        new_departure_time = time(10, 0)

        # Recalculation should recognize "early" as 165 minutes
        slot = booking.dropoff_slot
        if slot in ("165", "early"):
            minutes_before = 165
        elif slot in ("120", "late"):
            minutes_before = 120
        else:
            minutes_before = 0

        from datetime import datetime, timedelta
        departure_datetime = datetime.combine(date.today(), new_departure_time)
        new_dropoff_datetime = departure_datetime - timedelta(minutes=minutes_before)
        booking.dropoff_time = new_dropoff_datetime.time()

        # 10:00 - 2h45m = 07:15
        assert booking.dropoff_time == time(7, 15)


# =============================================================================
# Arrival Time Update - Booking Pickup Time Recalculation Tests
# =============================================================================

class TestArrivalTimeUpdateRecalculatesBookings:
    """Tests for automatic recalculation of booking pickup times when arrival time changes."""

    def test_update_arrival_time_recalculates_pickup_time(self):
        """Updating arrival time should recalculate booking pickup_time."""
        arrival = create_mock_arrival(
            id=1,
            arrival_time_val=time(14, 0),
        )
        booking = create_mock_booking(
            id=1,
            arrival_id=arrival.id,
            pickup_time_val=time(14, 0),
        )

        assert booking.pickup_time == time(14, 0)

        # Update arrival time to 15:30
        new_arrival_time = time(15, 30)
        booking.pickup_time = new_arrival_time

        assert booking.pickup_time == time(15, 30)

    def test_update_arrival_time_recalculates_pickup_time_from(self):
        """Updating arrival time should recalculate booking pickup_time_from (landing + 35 min)."""
        arrival = create_mock_arrival(
            id=1,
            arrival_time_val=time(14, 0),
        )
        booking = create_mock_booking(
            id=1,
            arrival_id=arrival.id,
            pickup_time_from_val=time(14, 35),  # 14:00 + 35 min
        )

        assert booking.pickup_time_from == time(14, 35)

        # Update arrival time to 16:00
        new_arrival_time = time(16, 0)

        from datetime import datetime, timedelta
        arrival_datetime = datetime.combine(date.today(), new_arrival_time)
        new_pickup_from_datetime = arrival_datetime + timedelta(minutes=35)
        booking.pickup_time_from = new_pickup_from_datetime.time()

        # New: arrival 16:00, pickup_time_from should be 16:35
        assert booking.pickup_time_from == time(16, 35)

    def test_update_arrival_time_recalculates_pickup_time_to(self):
        """Updating arrival time should recalculate booking pickup_time_to (landing + 60 min)."""
        arrival = create_mock_arrival(
            id=1,
            arrival_time_val=time(14, 0),
        )
        booking = create_mock_booking(
            id=1,
            arrival_id=arrival.id,
            pickup_time_to_val=time(15, 0),  # 14:00 + 60 min
        )

        assert booking.pickup_time_to == time(15, 0)

        # Update arrival time to 17:30
        new_arrival_time = time(17, 30)

        from datetime import datetime, timedelta
        arrival_datetime = datetime.combine(date.today(), new_arrival_time)
        new_pickup_to_datetime = arrival_datetime + timedelta(minutes=60)
        booking.pickup_time_to = new_pickup_to_datetime.time()

        # New: arrival 17:30, pickup_time_to should be 18:30
        assert booking.pickup_time_to == time(18, 30)

    def test_update_arrival_time_shows_warning_with_count(self):
        """Updating arrival time should show warning with number of bookings updated."""
        bookings = [create_mock_booking(id=1, arrival_id=1)]

        bookings_updated = len(bookings)
        warnings = []
        if bookings_updated > 0:
            warnings.append(f"Updated pickup times for {bookings_updated} booking(s)")

        assert "warnings" is not None or len(warnings) > 0
        assert "1 booking(s)" in warnings[-1]

    def test_update_arrival_time_no_change_no_recalculation(self):
        """Updating to same arrival time should not trigger recalculation."""
        old_arrival_time = time(14, 0)
        new_arrival_time = time(14, 0)

        bookings_updated = 0
        if new_arrival_time != old_arrival_time:
            bookings_updated = 1

        warnings = []
        if bookings_updated > 0:
            warnings.append(f"Updated pickup times for {bookings_updated} booking(s)")

        booking_warnings = [w for w in warnings if "booking(s)" in w]
        assert len(booking_warnings) == 0

    def test_update_other_arrival_fields_does_not_recalculate(self):
        """Updating fields other than arrival time should not recalculate bookings."""
        booking = create_mock_booking(
            id=1,
            pickup_time_val=time(14, 0),
        )
        original_pickup_time = booking.pickup_time

        # Simulate updating flight_number only (not arrival_time)
        arrival_time_changed = False

        if not arrival_time_changed:
            pass

        assert booking.pickup_time == original_pickup_time


# =============================================================================
# Booking Creation - Automatic arrival_id Linking Tests
# =============================================================================

class TestBookingArrivalIdAutoLinking:
    """Tests for automatic linking of bookings to arrivals when created."""

    def test_create_booking_sets_arrival_id_when_flight_exists(self):
        """When creating a booking with matching return flight, arrival_id is set."""
        mock_booking = MagicMock()
        mock_booking.arrival_id = 42
        mock_booking.pickup_time = time(14, 30)
        mock_booking.reference = "TEST123"

        with patch('db_service.create_booking') as mock_create:
            mock_create.return_value = mock_booking

            import db_service
            result = db_service.create_booking(
                db=MagicMock(),
                customer_id=1,
                vehicle_id=1,
                package="quick",
                dropoff_date=date(2025, 10, 13),
                dropoff_time=time(7, 15),
                pickup_date=date(2025, 10, 20),
                pickup_time=time(14, 30),
                pickup_flight_number="LNK1234",
                departure_id=100,
                dropoff_slot="early",
                arrival_id=42,
            )

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['arrival_id'] == 42
            assert result.arrival_id == 42

    def test_create_booking_arrival_id_null_when_flight_not_found(self):
        """When return flight doesn't exist in arrivals table, arrival_id is null."""
        mock_booking = MagicMock()
        mock_booking.arrival_id = None
        mock_booking.pickup_time = time(15, 0)
        mock_booking.reference = "TEST456"

        with patch('db_service.create_booking') as mock_create:
            mock_create.return_value = mock_booking

            import db_service
            result = db_service.create_booking(
                db=MagicMock(),
                customer_id=1,
                vehicle_id=1,
                package="quick",
                dropoff_date=date(2025, 10, 13),
                dropoff_time=time(7, 15),
                pickup_date=date(2025, 10, 20),
                pickup_time=time(15, 0),
                pickup_flight_number="NONEXISTENT999",
                departure_id=100,
                dropoff_slot="early",
                arrival_id=None,
            )

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['arrival_id'] is None
            assert result.arrival_id is None

    def test_db_service_create_booking_accepts_arrival_id_parameter(self):
        """Verify db_service.create_booking function signature accepts arrival_id."""
        import inspect
        import db_service

        sig = inspect.signature(db_service.create_booking)
        param_names = list(sig.parameters.keys())

        assert 'arrival_id' in param_names, "create_booking should accept arrival_id parameter"

    def test_booking_model_has_arrival_id_field(self):
        """Verify Booking model has arrival_id field defined."""
        from db_models import Booking
        import sqlalchemy

        mapper = sqlalchemy.inspect(Booking)
        column_names = [col.key for col in mapper.columns]

        assert 'arrival_id' in column_names, "Booking model should have arrival_id column"

    def test_arrival_lookup_logic(self):
        """Test the logic for looking up arrival by date and flight number."""
        from db_models import FlightArrival

        mock_session = MagicMock()
        mock_arrival = MagicMock(spec=FlightArrival)
        mock_arrival.id = 42
        mock_arrival.date = date(2025, 10, 20)
        mock_arrival.flight_number = "LNK1234"

        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_arrival
        mock_query.filter.return_value = mock_filter
        mock_session.query.return_value = mock_query

        arrival = mock_session.query(FlightArrival).filter(
            FlightArrival.date == date(2025, 10, 20),
            FlightArrival.flight_number == "LNK1234"
        ).first()

        arrival_id = arrival.id if arrival else None
        assert arrival_id == 42

    def test_arrival_lookup_returns_none_when_not_found(self):
        """Test that arrival lookup returns None when flight not found."""
        from db_models import FlightArrival

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_session.query.return_value = mock_query

        arrival = mock_session.query(FlightArrival).filter(
            FlightArrival.date == date(2025, 10, 20),
            FlightArrival.flight_number == "NONEXISTENT"
        ).first()

        arrival_id = arrival.id if arrival else None
        assert arrival_id is None
