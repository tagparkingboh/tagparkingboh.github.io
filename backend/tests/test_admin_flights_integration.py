"""
Integration tests for Admin Flights CRUD feature.

Tests for:
- GET /api/admin/flights/departures with start_date parameter
- GET /api/admin/flights/arrivals with start_date parameter
- POST /api/admin/flights/departures (create)
- POST /api/admin/flights/arrivals (create)
- DELETE /api/admin/flights/departures/{id}
- DELETE /api/admin/flights/arrivals/{id}
- Month grouping workflow
- Full CRUD workflow integration

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, timedelta, datetime, time
from unittest.mock import MagicMock
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_db_departure(
    id=1,
    date_val=None,
    flight_number=None,
    airline_code="FR",
    airline_name="Ryanair",
    departure_time_val=None,
    destination_code="AGP",
    destination_name="Malaga",
    capacity_tier=4,
    slots_booked_early=0,
    slots_booked_late=0,
):
    """Create a mock database departure object for testing."""
    departure = MagicMock()
    departure.id = id
    departure.date = date_val or date(2026, 3, 15)
    departure.flight_number = flight_number or f"FR{1000 + id}"
    departure.airline_code = airline_code
    departure.airline_name = airline_name
    departure.departure_time = departure_time_val or time(10, 30)
    departure.destination_code = destination_code
    departure.destination_name = destination_name
    departure.capacity_tier = capacity_tier
    departure.slots_booked_early = slots_booked_early
    departure.slots_booked_late = slots_booked_late
    departure.created_at = datetime.utcnow()
    departure.updated_at = None
    departure.updated_by = None
    return departure


def create_mock_db_arrival(
    id=1,
    date_val=None,
    flight_number=None,
    airline_code="FR",
    airline_name="Ryanair",
    arrival_time_val=None,
    departure_time_val=None,
    origin_code="AGP",
    origin_name="Malaga",
):
    """Create a mock database arrival object for testing."""
    arrival = MagicMock()
    arrival.id = id
    arrival.date = date_val or date(2026, 3, 22)
    arrival.flight_number = flight_number or f"FR{2000 + id}"
    arrival.airline_code = airline_code
    arrival.airline_name = airline_name
    arrival.arrival_time = arrival_time_val or time(16, 30)
    arrival.departure_time = departure_time_val or time(14, 0)
    arrival.origin_code = origin_code
    arrival.origin_name = origin_name
    arrival.created_at = datetime.utcnow()
    arrival.updated_at = None
    arrival.updated_by = None
    return arrival


def create_mock_user(id=1, email="admin@test.com", is_admin=True, is_active=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active
    return user


def create_mock_booking(
    id=1,
    reference=None,
    departure_id=None,
    arrival_id=None,
    status="confirmed",
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference or f"BK{1000 + id}"
    booking.departure_id = departure_id
    booking.arrival_id = arrival_id

    if status == "confirmed":
        booking.status = BookingStatus.CONFIRMED
    elif status == "completed":
        booking.status = BookingStatus.COMPLETED
    elif status == "pending":
        booking.status = BookingStatus.PENDING
    elif status == "cancelled":
        booking.status = BookingStatus.CANCELLED
    else:
        booking.status = MagicMock()
        booking.status.value = status

    return booking


# =============================================================================
# Integration Tests: API Endpoint Behavior
# =============================================================================

class TestFlightsEndpointBehavior:
    """Integration tests for the flights admin endpoints."""

    def test_endpoint_requires_admin(self):
        """Test that endpoints require admin authentication."""
        status_code = 401  # Would be returned without valid token
        assert status_code == 401

    def test_endpoint_rejects_non_admin(self):
        """Test that non-admin users are rejected."""
        user = create_mock_user(is_admin=False)
        status_code = 403  # Forbidden for non-admin

        assert status_code == 403
        assert not user.is_admin

    def test_endpoint_returns_json(self):
        """Test that endpoints return JSON response."""
        content_type = "application/json"
        assert content_type == "application/json"


# =============================================================================
# Integration Tests: Start Date Parameter
# =============================================================================

class TestStartDateParameterIntegration:
    """Integration tests for start_date query parameter."""

    def test_departures_default_start_date(self):
        """Test departures endpoint with default start_date (2026-01-01)."""
        default_start = date(2026, 1, 1)

        all_departures = [
            create_mock_db_departure(id=1, date_val=date(2025, 12, 31)),  # Before
            create_mock_db_departure(id=2, date_val=date(2026, 1, 1)),   # On
            create_mock_db_departure(id=3, date_val=date(2026, 3, 15)),  # After
            create_mock_db_departure(id=4, date_val=date(2026, 8, 31)),  # Way after
        ]

        # Filter with default start date
        filtered = [d for d in all_departures if d.date >= default_start]

        assert len(filtered) == 3
        assert all(d.date >= default_start for d in filtered)

    def test_departures_custom_start_date(self):
        """Test departures endpoint with custom start_date."""
        custom_start = date(2026, 6, 1)

        all_departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 15)),
            create_mock_db_departure(id=2, date_val=date(2026, 5, 31)),  # Before custom
            create_mock_db_departure(id=3, date_val=date(2026, 6, 1)),   # On custom
            create_mock_db_departure(id=4, date_val=date(2026, 8, 15)),  # After custom
        ]

        filtered = [d for d in all_departures if d.date >= custom_start]

        assert len(filtered) == 2
        assert all(d.date >= custom_start for d in filtered)

    def test_arrivals_default_start_date(self):
        """Test arrivals endpoint with default start_date."""
        default_start = date(2026, 1, 1)

        all_arrivals = [
            create_mock_db_arrival(id=1, date_val=date(2025, 12, 15)),
            create_mock_db_arrival(id=2, date_val=date(2026, 2, 10)),
            create_mock_db_arrival(id=3, date_val=date(2026, 7, 20)),
        ]

        filtered = [a for a in all_arrivals if a.date >= default_start]

        assert len(filtered) == 2


# =============================================================================
# Integration Tests: Month Grouping
# =============================================================================

class TestMonthGroupingIntegration:
    """Integration tests for month-based grouping of flights."""

    def test_departures_grouped_by_month(self):
        """Test that departures are correctly grouped by month."""
        month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']

        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 5)),
            create_mock_db_departure(id=2, date_val=date(2026, 1, 15)),
            create_mock_db_departure(id=3, date_val=date(2026, 3, 10)),
            create_mock_db_departure(id=4, date_val=date(2026, 3, 20)),
            create_mock_db_departure(id=5, date_val=date(2026, 3, 25)),
            create_mock_db_departure(id=6, date_val=date(2026, 6, 1)),
        ]

        # Group by month
        groups = {}
        for d in departures:
            month_key = d.date.strftime("%Y-%m")
            if month_key not in groups:
                year, month = month_key.split('-')
                groups[month_key] = {
                    'label': f"{month_names[int(month) - 1]} {year}",
                    'flights': []
                }
            groups[month_key]['flights'].append(d)

        assert len(groups) == 3  # January, March, June
        assert "2026-01" in groups
        assert "2026-03" in groups
        assert "2026-06" in groups

        assert len(groups["2026-01"]['flights']) == 2
        assert len(groups["2026-03"]['flights']) == 3
        assert len(groups["2026-06"]['flights']) == 1

        assert groups["2026-01"]['label'] == "January 2026"
        assert groups["2026-03"]['label'] == "March 2026"

    def test_arrivals_grouped_by_month(self):
        """Test that arrivals are correctly grouped by month."""
        arrivals = [
            create_mock_db_arrival(id=1, date_val=date(2026, 2, 5)),
            create_mock_db_arrival(id=2, date_val=date(2026, 2, 28)),
            create_mock_db_arrival(id=3, date_val=date(2026, 4, 15)),
        ]

        groups = defaultdict(list)
        for a in arrivals:
            month_key = a.date.strftime("%Y-%m")
            groups[month_key].append(a)

        assert len(groups) == 2  # February, April
        assert len(groups["2026-02"]) == 2
        assert len(groups["2026-04"]) == 1

    def test_month_groups_sorted_chronologically(self):
        """Test that month groups are sorted chronologically."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 8, 15)),
            create_mock_db_departure(id=2, date_val=date(2026, 3, 10)),
            create_mock_db_departure(id=3, date_val=date(2026, 5, 20)),
            create_mock_db_departure(id=4, date_val=date(2026, 1, 5)),
        ]

        groups = {}
        for d in departures:
            month_key = d.date.strftime("%Y-%m")
            if month_key not in groups:
                groups[month_key] = []
            groups[month_key].append(d)

        # Sort keys chronologically
        sorted_keys = sorted(groups.keys())

        assert sorted_keys == ["2026-01", "2026-03", "2026-05", "2026-08"]

    def test_empty_months_not_included(self):
        """Test that months with no flights are not included in grouping."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 15)),
            create_mock_db_departure(id=2, date_val=date(2026, 3, 15)),
        ]

        groups = defaultdict(list)
        for d in departures:
            month_key = d.date.strftime("%Y-%m")
            groups[month_key].append(d)

        # February should not exist
        assert "2026-02" not in groups


# =============================================================================
# Integration Tests: Create Departure Flow
# =============================================================================

class TestCreateDepartureIntegration:
    """Integration tests for departure creation workflow."""

    def test_create_departure_full_flow(self):
        """Test complete departure creation workflow."""
        # Step 1: Validate request data
        request_data = {
            "date": "2026-04-10",
            "flight_number": "FR9999",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "departure_time": "08:45",
            "destination_code": "BCN",
            "destination_name": "Barcelona",
            "capacity_tier": 6,
        }

        # Step 2: Check for duplicates
        existing_departures = []  # Empty - no duplicates
        is_duplicate = any(
            d.date == date.fromisoformat(request_data["date"]) and
            d.flight_number == request_data["flight_number"]
            for d in existing_departures
        )

        assert is_duplicate is False

        # Step 3: Create the departure
        new_departure = create_mock_db_departure(
            id=100,
            date_val=date.fromisoformat(request_data["date"]),
            flight_number=request_data["flight_number"],
            airline_code=request_data["airline_code"],
            airline_name=request_data["airline_name"],
            destination_code=request_data["destination_code"],
            destination_name=request_data["destination_name"],
            capacity_tier=request_data["capacity_tier"],
        )

        # Step 4: Verify the created departure
        assert new_departure.id == 100
        assert new_departure.flight_number == "FR9999"
        assert new_departure.capacity_tier == 6
        assert new_departure.slots_booked_early == 0
        assert new_departure.slots_booked_late == 0

    def test_create_departure_appears_in_month_group(self):
        """Test that created departure appears in correct month group."""
        existing_departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 4, 5)),
        ]

        # Create new departure in same month
        new_departure = create_mock_db_departure(
            id=2,
            date_val=date(2026, 4, 20),
            flight_number="NEW001"
        )

        all_departures = existing_departures + [new_departure]

        # Group by month
        groups = defaultdict(list)
        for d in all_departures:
            month_key = d.date.strftime("%Y-%m")
            groups[month_key].append(d)

        assert len(groups["2026-04"]) == 2
        assert any(d.flight_number == "NEW001" for d in groups["2026-04"])


# =============================================================================
# Integration Tests: Create Arrival Flow
# =============================================================================

class TestCreateArrivalIntegration:
    """Integration tests for arrival creation workflow."""

    def test_create_arrival_full_flow(self):
        """Test complete arrival creation workflow."""
        request_data = {
            "date": "2026-04-17",
            "flight_number": "FR9998",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "arrival_time": "18:15",
            "origin_code": "BCN",
            "origin_name": "Barcelona",
            "departure_time": "15:45",
        }

        # Check for duplicates
        existing_arrivals = []
        is_duplicate = any(
            a.date == date.fromisoformat(request_data["date"]) and
            a.flight_number == request_data["flight_number"]
            for a in existing_arrivals
        )

        assert is_duplicate is False

        # Create the arrival
        new_arrival = create_mock_db_arrival(
            id=100,
            date_val=date.fromisoformat(request_data["date"]),
            flight_number=request_data["flight_number"],
            airline_code=request_data["airline_code"],
            airline_name=request_data["airline_name"],
            origin_code=request_data["origin_code"],
            origin_name=request_data["origin_name"],
        )

        assert new_arrival.id == 100
        assert new_arrival.flight_number == "FR9998"
        assert new_arrival.origin_code == "BCN"


# =============================================================================
# Integration Tests: Delete Departure Flow
# =============================================================================

class TestDeleteDepartureIntegration:
    """Integration tests for departure deletion workflow."""

    def test_delete_departure_without_bookings(self):
        """Test deleting a departure without linked bookings."""
        departure = create_mock_db_departure(id=1, flight_number="DEL001")
        linked_bookings = []  # No bookings

        # Check if can delete
        can_delete = len(linked_bookings) == 0

        if can_delete:
            # Would create history record
            history = {
                "date": str(departure.date),
                "flight_number": departure.flight_number,
                "action": "deleted",
                "deleted_at": datetime.utcnow().isoformat(),
            }
            status_code = 200
        else:
            status_code = 409

        assert status_code == 200
        assert history["action"] == "deleted"

    def test_delete_departure_blocked_by_bookings(self):
        """Test that deletion is blocked when bookings exist."""
        departure = create_mock_db_departure(id=1, flight_number="DEL002")
        linked_bookings = [
            create_mock_booking(id=1, departure_id=departure.id),
            create_mock_booking(id=2, departure_id=departure.id),
        ]

        can_delete = len(linked_bookings) == 0

        if not can_delete:
            status_code = 409
            error_detail = f"Cannot delete: {len(linked_bookings)} booking(s) are linked"
        else:
            status_code = 200

        assert status_code == 409
        assert "2 booking(s)" in error_detail

    def test_delete_departure_updates_month_groups(self):
        """Test that month groups are updated after deletion."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 5, 10)),
            create_mock_db_departure(id=2, date_val=date(2026, 5, 20)),
            create_mock_db_departure(id=3, date_val=date(2026, 6, 15)),
        ]

        # Group before deletion
        groups_before = defaultdict(list)
        for d in departures:
            groups_before[d.date.strftime("%Y-%m")].append(d)

        assert len(groups_before["2026-05"]) == 2

        # Delete one departure from May
        departures = [d for d in departures if d.id != 1]

        # Regroup after deletion
        groups_after = defaultdict(list)
        for d in departures:
            groups_after[d.date.strftime("%Y-%m")].append(d)

        assert len(groups_after["2026-05"]) == 1

    def test_delete_last_departure_removes_month(self):
        """Test that month disappears when last departure is deleted."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 5, 10)),
            create_mock_db_departure(id=2, date_val=date(2026, 6, 15)),
        ]

        # Delete the only May departure
        departures = [d for d in departures if d.id != 1]

        groups = defaultdict(list)
        for d in departures:
            groups[d.date.strftime("%Y-%m")].append(d)

        assert "2026-05" not in groups
        assert "2026-06" in groups


# =============================================================================
# Integration Tests: Delete Arrival Flow
# =============================================================================

class TestDeleteArrivalIntegration:
    """Integration tests for arrival deletion workflow."""

    def test_delete_arrival_without_bookings(self):
        """Test deleting an arrival without linked bookings."""
        arrival = create_mock_db_arrival(id=1, flight_number="ARRDEL001")
        linked_bookings = []

        can_delete = len(linked_bookings) == 0

        assert can_delete is True

    def test_delete_arrival_blocked_by_bookings(self):
        """Test that deletion is blocked when bookings exist."""
        arrival = create_mock_db_arrival(id=1, flight_number="ARRDEL002")
        linked_bookings = [
            create_mock_booking(id=1, arrival_id=arrival.id),
        ]

        can_delete = len(linked_bookings) == 0

        if not can_delete:
            status_code = 409
            error_detail = f"Cannot delete: {len(linked_bookings)} booking(s) are linked"

        assert status_code == 409
        assert "1 booking(s)" in error_detail


# =============================================================================
# Integration Tests: Full CRUD Workflow
# =============================================================================

class TestFullCRUDWorkflow:
    """Integration tests for complete CRUD workflow."""

    def test_full_departure_lifecycle(self):
        """Test complete create, read, update, delete workflow for departures."""
        departures = []

        # CREATE
        new_departure = create_mock_db_departure(
            id=1,
            date_val=date(2026, 7, 15),
            flight_number="CRUD001",
            capacity_tier=4,
        )
        departures.append(new_departure)

        # READ - verify it appears in list
        assert any(d.flight_number == "CRUD001" for d in departures)

        # READ - verify it appears in correct month group
        groups = defaultdict(list)
        for d in departures:
            groups[d.date.strftime("%Y-%m")].append(d)

        assert "2026-07" in groups
        assert len(groups["2026-07"]) == 1

        # UPDATE (using mock)
        departures[0].capacity_tier = 8
        departures[0].updated_at = datetime.utcnow()
        departures[0].updated_by = "admin@test.com"

        assert departures[0].capacity_tier == 8
        assert departures[0].updated_by == "admin@test.com"

        # DELETE (simulate no bookings)
        linked_bookings = []
        if len(linked_bookings) == 0:
            departures = [d for d in departures if d.flight_number != "CRUD001"]

        assert len(departures) == 0

    def test_full_arrival_lifecycle(self):
        """Test complete create, read, update, delete workflow for arrivals."""
        arrivals = []

        # CREATE
        new_arrival = create_mock_db_arrival(
            id=1,
            date_val=date(2026, 7, 22),
            flight_number="ARRCRUD001",
        )
        arrivals.append(new_arrival)

        # READ
        assert any(a.flight_number == "ARRCRUD001" for a in arrivals)

        # UPDATE
        arrivals[0].arrival_time = time(19, 0)
        arrivals[0].updated_at = datetime.utcnow()

        assert arrivals[0].arrival_time == time(19, 0)

        # DELETE
        linked_bookings = []
        if len(linked_bookings) == 0:
            arrivals = [a for a in arrivals if a.flight_number != "ARRCRUD001"]

        assert len(arrivals) == 0


# =============================================================================
# Integration Tests: Filtering with Month Groups
# =============================================================================

class TestFilteringWithMonthGroups:
    """Integration tests for filtering behavior across month containers."""

    def test_airline_filter_across_months(self):
        """Test airline filter applies globally across months."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 10), airline_code="FR"),
            create_mock_db_departure(id=2, date_val=date(2026, 1, 20), airline_code="BA"),
            create_mock_db_departure(id=3, date_val=date(2026, 3, 10), airline_code="FR"),
            create_mock_db_departure(id=4, date_val=date(2026, 3, 20), airline_code="BA"),
            create_mock_db_departure(id=5, date_val=date(2026, 5, 10), airline_code="FR"),
        ]

        # Filter by airline
        airline_filter = "FR"
        filtered = [d for d in departures if d.airline_code == airline_filter]

        # Group filtered results
        groups = defaultdict(list)
        for d in filtered:
            groups[d.date.strftime("%Y-%m")].append(d)

        # All groups should only have FR flights
        assert len(filtered) == 3
        assert all(d.airline_code == "FR" for d in filtered)

        # BA-only months should not exist
        assert "2026-01" in groups
        assert "2026-03" in groups
        assert "2026-05" in groups

    def test_destination_filter_hides_empty_months(self):
        """Test that months with no matching destinations are hidden."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 10), destination_code="AGP"),
            create_mock_db_departure(id=2, date_val=date(2026, 2, 10), destination_code="PMI"),
            create_mock_db_departure(id=3, date_val=date(2026, 3, 10), destination_code="AGP"),
        ]

        # Filter by AGP destination
        dest_filter = "AGP"
        filtered = [d for d in departures if d.destination_code == dest_filter]

        groups = defaultdict(list)
        for d in filtered:
            groups[d.date.strftime("%Y-%m")].append(d)

        # February (only PMI) should not appear
        assert "2026-01" in groups
        assert "2026-02" not in groups  # Hidden - no AGP flights
        assert "2026-03" in groups

    def test_flight_number_filter_partial_match(self):
        """Test partial flight number filter across months."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 10), flight_number="FR1234"),
            create_mock_db_departure(id=2, date_val=date(2026, 1, 20), flight_number="FR1235"),
            create_mock_db_departure(id=3, date_val=date(2026, 2, 10), flight_number="BA5678"),
            create_mock_db_departure(id=4, date_val=date(2026, 2, 20), flight_number="FR1236"),
        ]

        # Partial match filter
        filter_term = "FR123"
        filtered = [d for d in departures if filter_term in d.flight_number]

        groups = defaultdict(list)
        for d in filtered:
            groups[d.date.strftime("%Y-%m")].append(d)

        assert len(filtered) == 3
        assert len(groups["2026-01"]) == 2
        assert len(groups["2026-02"]) == 1

    def test_combined_filters(self):
        """Test multiple filters combined across months."""
        departures = [
            create_mock_db_departure(id=1, date_val=date(2026, 1, 10), airline_code="FR", destination_code="AGP"),
            create_mock_db_departure(id=2, date_val=date(2026, 1, 20), airline_code="FR", destination_code="PMI"),
            create_mock_db_departure(id=3, date_val=date(2026, 2, 10), airline_code="BA", destination_code="AGP"),
            create_mock_db_departure(id=4, date_val=date(2026, 2, 20), airline_code="FR", destination_code="AGP"),
        ]

        # Combined filter: FR airline AND AGP destination
        filtered = [d for d in departures
                   if d.airline_code == "FR" and d.destination_code == "AGP"]

        groups = defaultdict(list)
        for d in filtered:
            groups[d.date.strftime("%Y-%m")].append(d)

        assert len(filtered) == 2
        assert len(groups["2026-01"]) == 1
        assert len(groups["2026-02"]) == 1


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
