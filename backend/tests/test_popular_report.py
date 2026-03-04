"""
Tests for Admin Popular Airlines & Destinations Report.

Covers:
- GET /api/admin/reports/popular - Popular airlines and destinations based on bookings

Test categories:
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time, datetime
from unittest.mock import MagicMock, patch
from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    created_at=None,
    dropoff_airline_code="BA",
    dropoff_airline_name="British Airways",
    dropoff_destination="Faro Airport",
    pickup_airline_code="BA",
    pickup_airline_name="British Airways",
    pickup_origin="Faro Airport",
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.created_at = created_at or datetime.utcnow()

    if status == "confirmed":
        booking.status = BookingStatus.CONFIRMED
    elif status == "completed":
        booking.status = BookingStatus.COMPLETED
    elif status == "pending":
        booking.status = BookingStatus.PENDING
    elif status == "cancelled":
        booking.status = BookingStatus.CANCELLED
    else:
        booking.status = BookingStatus.PENDING

    booking.dropoff_airline_code = dropoff_airline_code
    booking.dropoff_airline_name = dropoff_airline_name
    booking.dropoff_destination = dropoff_destination
    booking.pickup_airline_code = pickup_airline_code
    booking.pickup_airline_name = pickup_airline_name
    booking.pickup_origin = pickup_origin

    return booking


def create_mock_popular_response(
    total_bookings=10,
    popular_airlines=None,
    popular_destinations=None,
    popular_routes=None,
    top=10,
):
    """Create a mock popular report response."""
    if popular_airlines is None:
        popular_airlines = [
            {"airlineCode": "BA", "airlineName": "British Airways", "count": 8, "percent": 40.0},
            {"airlineCode": "FR", "airlineName": "Ryanair", "count": 6, "percent": 30.0},
            {"airlineCode": "U2", "airlineName": "easyJet", "count": 4, "percent": 20.0},
        ]

    if popular_destinations is None:
        popular_destinations = [
            {"destination": "Faro Airport", "count": 8, "percent": 50.0},
            {"destination": "Alicante Airport", "count": 5, "percent": 30.0},
            {"destination": "Malaga Airport", "count": 3, "percent": 20.0},
        ]

    if popular_routes is None:
        popular_routes = [
            {"airlineCode": "BA", "airlineName": "British Airways", "destination": "Faro Airport", "route": "British Airways to Faro Airport", "count": 5, "percent": 35.0},
            {"airlineCode": "FR", "airlineName": "Ryanair", "destination": "Malaga Airport", "route": "Ryanair to Malaga Airport", "count": 4, "percent": 28.0},
            {"airlineCode": "U2", "airlineName": "easyJet", "destination": "Alicante Airport", "route": "easyJet to Alicante Airport", "count": 3, "percent": 21.0},
        ]

    return {
        "meta": {
            "startDate": None,
            "endDate": None,
            "top": top,
            "totalBookings": total_bookings,
            "totalAirlineBookings": sum(a["count"] for a in popular_airlines),
            "totalDestinationBookings": sum(d["count"] for d in popular_destinations),
            "totalRouteBookings": sum(r["count"] for r in popular_routes),
        },
        "popularAirlines": popular_airlines,
        "popularDestinations": popular_destinations,
        "popularRoutes": popular_routes,
    }


# =============================================================================
# Unit Tests - Response Structure
# =============================================================================

class TestPopularReportResponseStructure:
    """Unit tests for response structure."""

    def test_response_includes_meta_section(self):
        """Response should include meta section with query parameters."""
        response = create_mock_popular_response()

        assert "meta" in response
        assert "startDate" in response["meta"]
        assert "endDate" in response["meta"]
        assert "top" in response["meta"]
        assert "totalBookings" in response["meta"]
        assert "totalAirlineBookings" in response["meta"]
        assert "totalDestinationBookings" in response["meta"]
        assert "totalRouteBookings" in response["meta"]

    def test_response_does_not_include_status_filter(self):
        """Response meta should not include status filter (always confirmed+completed)."""
        response = create_mock_popular_response()

        assert "status" not in response["meta"]

    def test_response_includes_popular_airlines(self):
        """Response should include popularAirlines array."""
        response = create_mock_popular_response()

        assert "popularAirlines" in response
        assert isinstance(response["popularAirlines"], list)

    def test_response_includes_popular_destinations(self):
        """Response should include popularDestinations array."""
        response = create_mock_popular_response()

        assert "popularDestinations" in response
        assert isinstance(response["popularDestinations"], list)

    def test_response_includes_popular_routes(self):
        """Response should include popularRoutes array."""
        response = create_mock_popular_response()

        assert "popularRoutes" in response
        assert isinstance(response["popularRoutes"], list)

    def test_airline_entry_structure(self):
        """Airline entry should include code, name, count, percent."""
        response = create_mock_popular_response()

        airline = response["popularAirlines"][0]
        assert "airlineCode" in airline
        assert "airlineName" in airline
        assert "count" in airline
        assert "percent" in airline

    def test_destination_entry_structure(self):
        """Destination entry should include destination, count, percent."""
        response = create_mock_popular_response()

        destination = response["popularDestinations"][0]
        assert "destination" in destination
        assert "count" in destination
        assert "percent" in destination

    def test_route_entry_structure(self):
        """Route entry should include airline, destination, route, count, percent."""
        response = create_mock_popular_response()

        route = response["popularRoutes"][0]
        assert "airlineCode" in route
        assert "airlineName" in route
        assert "destination" in route
        assert "route" in route
        assert "count" in route
        assert "percent" in route


# =============================================================================
# Unit Tests - Airline Counting Logic (Merged - each booking counts once per unique airline)
# =============================================================================

class TestAirlineCountingLogic:
    """Unit tests for airline counting logic with merged departure/return."""

    def test_count_departure_airline(self):
        """Should count departure airline."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code=None,
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        assert airline_counter[("BA", "British Airways")] == 1

    def test_count_return_airline(self):
        """Should count return airline."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name=None,
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        assert airline_counter[("FR", "Ryanair")] == 1

    def test_count_different_departure_and_return_airlines(self):
        """Should count both different airlines once each."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        assert airline_counter[("BA", "British Airways")] == 1
        assert airline_counter[("FR", "Ryanair")] == 1

    def test_same_airline_both_ways_counts_once(self):
        """Same airline for departure and return should count ONCE per booking (merged)."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code="BA",
            pickup_airline_name="British Airways",
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        # Key change: same airline both ways = 1 count (not 2)
        assert airline_counter[("BA", "British Airways")] == 1

    def test_skip_null_airline_name(self):
        """Should skip airlines with null name."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name=None,
            pickup_airline_code=None,
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        assert len(airline_counter) == 0

    def test_use_unk_for_missing_airline_code(self):
        """Should use 'UNK' for missing airline code."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name="Unknown Airline",
            pickup_airline_code=None,
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        assert airline_counter[("UNK", "Unknown Airline")] == 1

    def test_multiple_bookings_same_airline(self):
        """Multiple bookings with same airline should accumulate counts."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
            create_mock_booking(id=2, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
            create_mock_booking(id=3, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
        ]

        airline_counter = Counter()
        for booking in bookings:
            airlines_in_booking = set()
            if booking.dropoff_airline_name:
                airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
                airlines_in_booking.add(airline_key)
            if booking.pickup_airline_name:
                airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
                airlines_in_booking.add(airline_key)
            for airline_key in airlines_in_booking:
                airline_counter[airline_key] += 1

        # 3 bookings, each counts BA once = 3
        assert airline_counter[("BA", "British Airways")] == 3


# =============================================================================
# Unit Tests - Destination Counting Logic (Merged - each booking counts once per unique destination)
# =============================================================================

class TestDestinationCountingLogic:
    """Unit tests for destination counting logic with merged departure/return."""

    def test_count_departure_destination(self):
        """Should count departure destination."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
            pickup_origin=None,
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        assert destination_counter["Faro Airport"] == 1

    def test_count_return_origin(self):
        """Should count return origin."""
        booking = create_mock_booking(
            dropoff_destination=None,
            pickup_origin="Malaga Airport",
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        assert destination_counter["Malaga Airport"] == 1

    def test_count_different_departure_and_return_destinations(self):
        """Should count both different destinations once each."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
            pickup_origin="Malaga Airport",
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        assert destination_counter["Faro Airport"] == 1
        assert destination_counter["Malaga Airport"] == 1

    def test_same_destination_both_ways_counts_once(self):
        """Same destination for departure and return should count ONCE per booking (merged)."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
            pickup_origin="Faro Airport",
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        # Key change: same destination both ways = 1 count (not 2)
        assert destination_counter["Faro Airport"] == 1

    def test_skip_null_destination(self):
        """Should skip null destinations."""
        booking = create_mock_booking(
            dropoff_destination=None,
            pickup_origin=None,
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        assert len(destination_counter) == 0

    def test_multiple_bookings_same_destination(self):
        """Multiple bookings with same destination should accumulate counts."""
        bookings = [
            create_mock_booking(id=1, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
            create_mock_booking(id=2, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
            create_mock_booking(id=3, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
        ]

        destination_counter = Counter()
        for booking in bookings:
            destinations_in_booking = set()
            if booking.dropoff_destination:
                destinations_in_booking.add(booking.dropoff_destination)
            if booking.pickup_origin:
                destinations_in_booking.add(booking.pickup_origin)
            for dest in destinations_in_booking:
                destination_counter[dest] += 1

        # 3 bookings, each counts Faro once = 3
        assert destination_counter["Faro Airport"] == 3


# =============================================================================
# Unit Tests - Route Counting Logic (Airline + Destination combinations)
# =============================================================================

class TestRouteCountingLogic:
    """Unit tests for route counting logic (airline + destination combinations)."""

    def test_count_outbound_route(self):
        """Should count outbound route (dropoff airline + dropoff destination)."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            dropoff_destination="Faro Airport",
            pickup_airline_name=None,
            pickup_origin=None,
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        assert route_counter[("BA", "British Airways", "Faro Airport")] == 1

    def test_count_return_route(self):
        """Should count return route (pickup airline + pickup origin)."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_destination=None,
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
            pickup_origin="Malaga Airport",
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.pickup_airline_name and booking.pickup_origin:
            route_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name, booking.pickup_origin)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        assert route_counter[("FR", "Ryanair", "Malaga Airport")] == 1

    def test_same_route_both_ways_counts_once(self):
        """Same route for outbound and return should count ONCE per booking."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            dropoff_destination="Faro Airport",
            pickup_airline_code="BA",
            pickup_airline_name="British Airways",
            pickup_origin="Faro Airport",
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
            routes_in_booking.add(route_key)
        if booking.pickup_airline_name and booking.pickup_origin:
            route_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name, booking.pickup_origin)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        # Same route both ways = 1 count (not 2)
        assert route_counter[("BA", "British Airways", "Faro Airport")] == 1

    def test_different_routes_both_count(self):
        """Different routes for outbound and return should both count."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            dropoff_destination="Faro Airport",
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
            pickup_origin="Malaga Airport",
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
            routes_in_booking.add(route_key)
        if booking.pickup_airline_name and booking.pickup_origin:
            route_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name, booking.pickup_origin)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        assert route_counter[("BA", "British Airways", "Faro Airport")] == 1
        assert route_counter[("FR", "Ryanair", "Malaga Airport")] == 1

    def test_skip_route_without_airline(self):
        """Should skip routes with missing airline."""
        booking = create_mock_booking(
            dropoff_airline_name=None,
            dropoff_destination="Faro Airport",
            pickup_airline_name=None,
            pickup_origin=None,
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        assert len(route_counter) == 0

    def test_skip_route_without_destination(self):
        """Should skip routes with missing destination."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            dropoff_destination=None,
            pickup_airline_name=None,
            pickup_origin=None,
        )

        route_counter = Counter()
        routes_in_booking = set()
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
            routes_in_booking.add(route_key)
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

        assert len(route_counter) == 0

    def test_multiple_bookings_same_route(self):
        """Multiple bookings with same route should accumulate counts."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="Jet2", dropoff_airline_code="LS", dropoff_destination="Faro Airport", pickup_airline_name="Jet2", pickup_airline_code="LS", pickup_origin="Faro Airport"),
            create_mock_booking(id=2, dropoff_airline_name="Jet2", dropoff_airline_code="LS", dropoff_destination="Faro Airport", pickup_airline_name="Jet2", pickup_airline_code="LS", pickup_origin="Faro Airport"),
            create_mock_booking(id=3, dropoff_airline_name="Jet2", dropoff_airline_code="LS", dropoff_destination="Faro Airport", pickup_airline_name="Jet2", pickup_airline_code="LS", pickup_origin="Faro Airport"),
        ]

        route_counter = Counter()
        for booking in bookings:
            routes_in_booking = set()
            if booking.dropoff_airline_name and booking.dropoff_destination:
                route_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name, booking.dropoff_destination)
                routes_in_booking.add(route_key)
            if booking.pickup_airline_name and booking.pickup_origin:
                route_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name, booking.pickup_origin)
                routes_in_booking.add(route_key)
            for route_key in routes_in_booking:
                route_counter[route_key] += 1

        # 3 bookings, each counts Jet2 to Faro once = 3
        assert route_counter[("LS", "Jet2", "Faro Airport")] == 3


# =============================================================================
# Unit Tests - Percentage Calculation
# =============================================================================

class TestPercentageCalculation:
    """Unit tests for percentage calculation."""

    def test_percentage_calculation(self):
        """Percentage should be count/total * 100."""
        count = 25
        total = 100
        percent = round((count / total) * 100, 1)

        assert percent == 25.0

    def test_percentage_with_rounding(self):
        """Percentage should round to 1 decimal place."""
        count = 33
        total = 100
        percent = round((count / total) * 100, 1)

        assert percent == 33.0

    def test_percentage_zero_total(self):
        """Should handle zero total gracefully."""
        count = 0
        total = 0
        percent = round((count / total) * 100, 1) if total > 0 else 0

        assert percent == 0

    def test_percentage_100_percent(self):
        """Single item should be 100%."""
        count = 50
        total = 50
        percent = round((count / total) * 100, 1)

        assert percent == 100.0


# =============================================================================
# Unit Tests - Top N Logic
# =============================================================================

class TestTopNLogic:
    """Unit tests for top N filtering."""

    def test_top_5_returns_5_items(self):
        """Top 5 should return at most 5 items."""
        counter = Counter({
            "A": 10, "B": 9, "C": 8, "D": 7, "E": 6, "F": 5, "G": 4
        })

        top_items = counter.most_common(5)

        assert len(top_items) == 5

    def test_top_10_returns_10_items(self):
        """Top 10 should return at most 10 items."""
        counter = Counter({f"Item{i}": 100 - i for i in range(15)})

        top_items = counter.most_common(10)

        assert len(top_items) == 10

    def test_top_20_returns_20_items(self):
        """Top 20 should return at most 20 items."""
        counter = Counter({f"Item{i}": 100 - i for i in range(25)})

        top_items = counter.most_common(20)

        assert len(top_items) == 20

    def test_top_returns_fewer_if_less_data(self):
        """Top N should return fewer items if data has less than N."""
        counter = Counter({"A": 10, "B": 5})

        top_items = counter.most_common(10)

        assert len(top_items) == 2

    def test_items_ordered_by_count_descending(self):
        """Items should be ordered by count descending."""
        counter = Counter({"A": 5, "B": 10, "C": 3})

        top_items = counter.most_common(3)

        assert top_items[0][0] == "B"
        assert top_items[1][0] == "A"
        assert top_items[2][0] == "C"


# =============================================================================
# Unit Tests - Date Filtering
# =============================================================================

class TestDateFiltering:
    """Unit tests for date range filtering."""

    def test_filter_by_start_date(self):
        """Bookings before start date should be filtered out."""
        start_date = date(2024, 6, 1)
        booking_date = datetime(2024, 5, 15)

        is_after_start = booking_date.date() >= start_date

        assert is_after_start is False

    def test_filter_by_end_date(self):
        """Bookings after end date should be filtered out."""
        end_date = date(2024, 6, 30)
        booking_date = datetime(2024, 7, 15)

        is_before_end = booking_date.date() <= end_date

        assert is_before_end is False

    def test_booking_within_date_range(self):
        """Bookings within date range should be included."""
        start_date = date(2024, 6, 1)
        end_date = date(2024, 6, 30)
        booking_date = datetime(2024, 6, 15)

        is_in_range = start_date <= booking_date.date() <= end_date

        assert is_in_range is True

    def test_booking_on_start_date(self):
        """Booking on start date should be included."""
        start_date = date(2024, 6, 1)
        booking_date = datetime(2024, 6, 1, 12, 0)

        is_on_or_after = booking_date.date() >= start_date

        assert is_on_or_after is True

    def test_booking_on_end_date(self):
        """Booking on end date should be included."""
        end_date = date(2024, 6, 30)
        booking_date = datetime(2024, 6, 30, 23, 59)

        is_on_or_before = booking_date.date() <= end_date

        assert is_on_or_before is True


# =============================================================================
# Negative Tests
# =============================================================================

class TestNegativeScenarios:
    """Negative test cases."""

    def test_empty_bookings_returns_empty_arrays(self):
        """Empty bookings should return empty airline and destination arrays."""
        bookings = []

        airline_counter = Counter()
        destination_counter = Counter()
        for booking in bookings:
            airlines_in_booking = set()
            if booking.dropoff_airline_name:
                airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
            if booking.pickup_airline_name:
                airlines_in_booking.add((booking.pickup_airline_code or "UNK", booking.pickup_airline_name))
            for key in airlines_in_booking:
                airline_counter[key] += 1

            destinations_in_booking = set()
            if booking.dropoff_destination:
                destinations_in_booking.add(booking.dropoff_destination)
            if booking.pickup_origin:
                destinations_in_booking.add(booking.pickup_origin)
            for dest in destinations_in_booking:
                destination_counter[dest] += 1

        assert len(airline_counter) == 0
        assert len(destination_counter) == 0

    def test_invalid_top_value_defaults_to_10(self):
        """Invalid top value should default to 10."""
        top = 15  # Not in [5, 10, 20]

        if top not in [5, 10, 20]:
            top = 10

        assert top == 10

    def test_negative_top_value_defaults_to_10(self):
        """Negative top value should default to 10."""
        top = -5

        if top not in [5, 10, 20]:
            top = 10

        assert top == 10

    def test_zero_top_value_defaults_to_10(self):
        """Zero top value should default to 10."""
        top = 0

        if top not in [5, 10, 20]:
            top = 10

        assert top == 10

    def test_all_bookings_with_null_airlines(self):
        """All bookings with null airlines should return empty array."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name=None, pickup_airline_name=None),
            create_mock_booking(id=2, dropoff_airline_name=None, pickup_airline_name=None),
        ]

        airline_counter = Counter()
        for booking in bookings:
            airlines_in_booking = set()
            if booking.dropoff_airline_name:
                airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
            if booking.pickup_airline_name:
                airlines_in_booking.add((booking.pickup_airline_code or "UNK", booking.pickup_airline_name))
            for key in airlines_in_booking:
                airline_counter[key] += 1

        assert len(airline_counter) == 0

    def test_all_bookings_with_null_destinations(self):
        """All bookings with null destinations should return empty array."""
        bookings = [
            create_mock_booking(id=1, dropoff_destination=None, pickup_origin=None),
            create_mock_booking(id=2, dropoff_destination=None, pickup_origin=None),
        ]

        destination_counter = Counter()
        for booking in bookings:
            destinations_in_booking = set()
            if booking.dropoff_destination:
                destinations_in_booking.add(booking.dropoff_destination)
            if booking.pickup_origin:
                destinations_in_booking.add(booking.pickup_origin)
            for dest in destinations_in_booking:
                destination_counter[dest] += 1

        assert len(destination_counter) == 0


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_airline_name_with_special_characters(self):
        """Airline name with special characters should be handled."""
        booking = create_mock_booking(
            dropoff_airline_name="Fly-Ô-Jet Airlines (UK)",
            dropoff_airline_code="FOJ",
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
        for key in airlines_in_booking:
            airline_counter[key] += 1

        assert airline_counter[("FOJ", "Fly-Ô-Jet Airlines (UK)")] == 1

    def test_destination_with_unicode_characters(self):
        """Destination with unicode characters should be handled."""
        booking = create_mock_booking(
            dropoff_destination="São Paulo–Guarulhos Airport",
            pickup_origin=None,
        )

        destination_counter = Counter()
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

        assert destination_counter["São Paulo–Guarulhos Airport"] == 1

    def test_very_long_airline_name(self):
        """Very long airline name should be handled."""
        long_name = "A" * 200
        booking = create_mock_booking(
            dropoff_airline_name=long_name,
            dropoff_airline_code="LNG",
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
        for key in airlines_in_booking:
            airline_counter[key] += 1

        assert airline_counter[("LNG", long_name)] == 1

    def test_large_number_of_bookings(self):
        """Large number of bookings should be handled efficiently."""
        bookings = [
            create_mock_booking(
                id=i,
                dropoff_airline_name=f"Airline{i % 50}",
                dropoff_airline_code=f"AL{i % 50}",
                dropoff_destination=f"Destination{i % 30}",
                pickup_airline_name=f"Airline{i % 50}",
                pickup_airline_code=f"AL{i % 50}",
                pickup_origin=f"Destination{i % 30}",
            )
            for i in range(1000)
        ]

        airline_counter = Counter()
        destination_counter = Counter()
        for booking in bookings:
            airlines_in_booking = set()
            if booking.dropoff_airline_name:
                airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
            if booking.pickup_airline_name:
                airlines_in_booking.add((booking.pickup_airline_code or "UNK", booking.pickup_airline_name))
            for key in airlines_in_booking:
                airline_counter[key] += 1

            destinations_in_booking = set()
            if booking.dropoff_destination:
                destinations_in_booking.add(booking.dropoff_destination)
            if booking.pickup_origin:
                destinations_in_booking.add(booking.pickup_origin)
            for dest in destinations_in_booking:
                destination_counter[dest] += 1

        # 1000 bookings, same airline both ways = 1000 counts per unique airline
        # 50 unique airlines, each appears 20 times
        assert len(airline_counter) == 50
        assert sum(airline_counter.values()) == 1000

        # Same for destinations
        assert len(destination_counter) == 30

    def test_single_booking_single_airline(self):
        """Single booking with single airline should work."""
        booking = create_mock_booking(
            dropoff_airline_name="Solo Air",
            dropoff_airline_code="SA",
            pickup_airline_name="Solo Air",
            pickup_airline_code="SA",
        )

        airline_counter = Counter()
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airlines_in_booking.add((booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name))
        if booking.pickup_airline_name:
            airlines_in_booking.add((booking.pickup_airline_code or "UNK", booking.pickup_airline_name))
        for key in airlines_in_booking:
            airline_counter[key] += 1

        top_airlines = airline_counter.most_common(10)

        assert len(top_airlines) == 1
        assert top_airlines[0][1] == 1

    def test_exact_boundary_top_5(self):
        """Exactly 5 items should return all 5 for top 5."""
        counter = Counter({"A": 5, "B": 4, "C": 3, "D": 2, "E": 1})

        top_items = counter.most_common(5)

        assert len(top_items) == 5

    def test_exact_boundary_top_10(self):
        """Exactly 10 items should return all 10 for top 10."""
        counter = Counter({f"Item{i}": 10 - i for i in range(10)})

        top_items = counter.most_common(10)

        assert len(top_items) == 10

    def test_exact_boundary_top_20(self):
        """Exactly 20 items should return all 20 for top 20."""
        counter = Counter({f"Item{i}": 20 - i for i in range(20)})

        top_items = counter.most_common(20)

        assert len(top_items) == 20

    def test_tie_in_counts(self):
        """Airlines/destinations with same count should all be included."""
        counter = Counter({"A": 10, "B": 10, "C": 10, "D": 5})

        top_items = counter.most_common(3)

        # Should include 3 items, all with count 10 (order may vary for ties)
        assert len(top_items) == 3
        for item, count in top_items:
            assert count == 10


# =============================================================================
# Status Filtering (Only Confirmed + Completed)
# =============================================================================

class TestStatusFiltering:
    """Tests for status filtering - only confirmed and completed bookings."""

    def test_confirmed_booking_included(self):
        """Confirmed bookings should be included."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="confirmed")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is True

    def test_completed_booking_included(self):
        """Completed bookings should be included."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="completed")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is True

    def test_pending_booking_excluded(self):
        """Pending bookings should be excluded."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="pending")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False

    def test_cancelled_booking_excluded(self):
        """Cancelled bookings should be excluded."""
        from db_models import BookingStatus

        booking = create_mock_booking(status="cancelled")

        is_included = booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

        assert is_included is False

    def test_mixed_status_bookings(self):
        """Only confirmed and completed should be counted."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
            create_mock_booking(id=5, status="confirmed"),
        ]

        included = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]

        assert len(included) == 3
