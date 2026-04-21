"""
Integration tests for Admin Popular Airlines & Destinations Report.

These tests verify the full workflow from bookings data to API response.
All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, datetime
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


def simulate_popular_report_endpoint(bookings, top=10):
    """Simulate the popular report endpoint logic with merged counting."""
    airline_counter = Counter()
    destination_counter = Counter()

    for booking in bookings:
        # Collect unique airlines for this booking
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airlines_in_booking.add(airline_key)
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airlines_in_booking.add(airline_key)
        # Count each unique airline once per booking
        for airline_key in airlines_in_booking:
            airline_counter[airline_key] += 1

        # Collect unique destinations for this booking
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        # Count each unique destination once per booking
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

    # Build top airlines
    top_airlines = []
    total_airline_bookings = sum(airline_counter.values())
    for (code, name), count in airline_counter.most_common(top):
        percent = round((count / total_airline_bookings) * 100, 1) if total_airline_bookings > 0 else 0
        top_airlines.append({
            "airlineCode": code,
            "airlineName": name,
            "count": count,
            "percent": percent,
        })

    # Build top destinations
    top_destinations = []
    total_destination_bookings = sum(destination_counter.values())
    for destination, count in destination_counter.most_common(top):
        percent = round((count / total_destination_bookings) * 100, 1) if total_destination_bookings > 0 else 0
        top_destinations.append({
            "destination": destination,
            "count": count,
            "percent": percent,
        })

    return {
        "meta": {
            "startDate": None,
            "endDate": None,
            "top": top,
            "totalBookings": len(bookings),
            "totalAirlineBookings": total_airline_bookings,
            "totalDestinationBookings": total_destination_bookings,
        },
        "popularAirlines": top_airlines,
        "popularDestinations": top_destinations,
    }


# =============================================================================
# Integration Tests - Full API Response
# =============================================================================

class TestPopularReportIntegration:
    """Integration tests for popular report endpoint."""

    def test_full_response_structure(self):
        """Full API response should have correct structure."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="British Airways", dropoff_airline_code="BA"),
            create_mock_booking(id=2, dropoff_airline_name="Ryanair", dropoff_airline_code="FR"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        assert "meta" in response
        assert "popularAirlines" in response
        assert "popularDestinations" in response
        assert "startDate" in response["meta"]
        assert "endDate" in response["meta"]
        assert "top" in response["meta"]
        assert "totalBookings" in response["meta"]
        assert "totalAirlineBookings" in response["meta"]
        assert "totalDestinationBookings" in response["meta"]

    def test_response_does_not_include_status(self):
        """Response should not include status field (always confirmed+completed)."""
        bookings = [create_mock_booking()]

        response = simulate_popular_report_endpoint(bookings)

        assert "status" not in response["meta"]


# =============================================================================
# Integration Tests - Complete Workflow
# =============================================================================

class TestCompleteWorkflow:
    """Integration tests for complete data processing workflow."""

    def test_bookings_to_airlines_workflow(self):
        """Test complete workflow from bookings to airline rankings."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
            create_mock_booking(id=2, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
            create_mock_booking(id=3, dropoff_airline_name="Ryanair", dropoff_airline_code="FR", pickup_airline_name="Ryanair", pickup_airline_code="FR"),
            create_mock_booking(id=4, dropoff_airline_name="easyJet", dropoff_airline_code="U2", pickup_airline_name="easyJet", pickup_airline_code="U2"),
            create_mock_booking(id=5, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # BA should be first with 3 bookings (merged, so same airline both ways = 1 count per booking)
        assert response["popularAirlines"][0]["airlineName"] == "British Airways"
        assert response["popularAirlines"][0]["count"] == 3

        # FR should be second with 1 booking
        assert response["popularAirlines"][1]["airlineName"] == "Ryanair"
        assert response["popularAirlines"][1]["count"] == 1

    def test_bookings_to_destinations_workflow(self):
        """Test complete workflow from bookings to destination rankings."""
        bookings = [
            create_mock_booking(id=1, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
            create_mock_booking(id=2, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
            create_mock_booking(id=3, dropoff_destination="Malaga Airport", pickup_origin="Malaga Airport"),
            create_mock_booking(id=4, dropoff_destination="Alicante Airport", pickup_origin="Alicante Airport"),
            create_mock_booking(id=5, dropoff_destination="Faro Airport", pickup_origin="Faro Airport"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # Faro should be first with 3 bookings (merged)
        assert response["popularDestinations"][0]["destination"] == "Faro Airport"
        assert response["popularDestinations"][0]["count"] == 3

    def test_different_airlines_outbound_and_return(self):
        """When booking has different airlines outbound/return, both count once."""
        bookings = [
            create_mock_booking(
                id=1,
                dropoff_airline_name="British Airways",
                dropoff_airline_code="BA",
                pickup_airline_name="Ryanair",
                pickup_airline_code="FR"
            ),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # Both airlines should appear with count 1
        airline_names = [a["airlineName"] for a in response["popularAirlines"]]
        assert "British Airways" in airline_names
        assert "Ryanair" in airline_names
        assert response["meta"]["totalAirlineBookings"] == 2  # 2 unique airlines in 1 booking

    def test_same_airline_outbound_and_return_counts_once(self):
        """When booking has same airline both ways, it counts once per booking."""
        bookings = [
            create_mock_booking(
                id=1,
                dropoff_airline_name="Jet2",
                dropoff_airline_code="LS",
                pickup_airline_name="Jet2",
                pickup_airline_code="LS"
            ),
            create_mock_booking(
                id=2,
                dropoff_airline_name="Jet2",
                dropoff_airline_code="LS",
                pickup_airline_name="Jet2",
                pickup_airline_code="LS"
            ),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # Jet2 should have count 2 (one per booking, not 4)
        assert len(response["popularAirlines"]) == 1
        assert response["popularAirlines"][0]["airlineName"] == "Jet2"
        assert response["popularAirlines"][0]["count"] == 2
        assert response["meta"]["totalAirlineBookings"] == 2


# =============================================================================
# Integration Tests - Date Filtering
# =============================================================================

class TestDateFilteringIntegration:
    """Integration tests for date range filtering."""

    def test_filter_bookings_by_date_range(self):
        """Bookings outside date range should be excluded."""
        from db_models import BookingStatus

        start_date = date(2024, 6, 1)
        end_date = date(2024, 6, 30)

        all_bookings = [
            create_mock_booking(id=1, created_at=datetime(2024, 5, 15)),  # Before range
            create_mock_booking(id=2, created_at=datetime(2024, 6, 15)),  # In range
            create_mock_booking(id=3, created_at=datetime(2024, 6, 20)),  # In range
            create_mock_booking(id=4, created_at=datetime(2024, 7, 15)),  # After range
        ]

        # Simulate date filtering
        filtered = [
            b for b in all_bookings
            if start_date <= b.created_at.date() <= end_date
        ]

        response = simulate_popular_report_endpoint(filtered)

        assert response["meta"]["totalBookings"] == 2


# =============================================================================
# Integration Tests - Edge Cases
# =============================================================================

class TestIntegrationEdgeCases:
    """Integration tests for edge cases."""

    def test_empty_bookings(self):
        """Empty bookings list should return empty arrays."""
        response = simulate_popular_report_endpoint([])

        assert response["meta"]["totalBookings"] == 0
        assert response["meta"]["totalAirlineBookings"] == 0
        assert response["meta"]["totalDestinationBookings"] == 0
        assert len(response["popularAirlines"]) == 0
        assert len(response["popularDestinations"]) == 0

    def test_all_same_airline(self):
        """All bookings with same airline should have 100% for that airline."""
        bookings = [
            create_mock_booking(id=i, dropoff_airline_name="Jet2", dropoff_airline_code="LS", pickup_airline_name="Jet2", pickup_airline_code="LS")
            for i in range(10)
        ]

        response = simulate_popular_report_endpoint(bookings)

        assert len(response["popularAirlines"]) == 1
        assert response["popularAirlines"][0]["airlineName"] == "Jet2"
        assert response["popularAirlines"][0]["percent"] == 100.0
        assert response["popularAirlines"][0]["count"] == 10

    def test_mixed_null_and_valid_data(self):
        """Should handle mix of null and valid airline/destination data."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
            create_mock_booking(id=2, dropoff_airline_name=None, dropoff_airline_code=None, pickup_airline_name=None, pickup_airline_code=None),
            create_mock_booking(id=3, dropoff_airline_name="Ryanair", dropoff_airline_code="FR", pickup_airline_name="Ryanair", pickup_airline_code="FR"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # Only 2 bookings have airline data
        assert response["meta"]["totalAirlineBookings"] == 2

    def test_top_5_limit(self):
        """Top 5 should return only 5 items even with more data."""
        bookings = []
        airlines = ["Airline1", "Airline2", "Airline3", "Airline4", "Airline5", "Airline6", "Airline7"]
        for i, airline in enumerate(airlines):
            for j in range(10 - i):  # Different counts
                bookings.append(create_mock_booking(
                    id=len(bookings) + 1,
                    dropoff_airline_name=airline,
                    dropoff_airline_code=f"A{i}",
                    pickup_airline_name=airline,
                    pickup_airline_code=f"A{i}",
                ))

        response = simulate_popular_report_endpoint(bookings, top=5)

        assert len(response["popularAirlines"]) == 5

    def test_percentage_accuracy(self):
        """Percentages should be accurate and sum correctly."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="BA", dropoff_airline_code="BA", pickup_airline_name="BA", pickup_airline_code="BA"),
            create_mock_booking(id=2, dropoff_airline_name="BA", dropoff_airline_code="BA", pickup_airline_name="BA", pickup_airline_code="BA"),
            create_mock_booking(id=3, dropoff_airline_name="FR", dropoff_airline_code="FR", pickup_airline_name="FR", pickup_airline_code="FR"),
            create_mock_booking(id=4, dropoff_airline_name="U2", dropoff_airline_code="U2", pickup_airline_name="U2", pickup_airline_code="U2"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        # BA: 2/4 = 50%, FR: 1/4 = 25%, U2: 1/4 = 25%
        total_percent = sum(a["percent"] for a in response["popularAirlines"])
        assert total_percent == 100.0

    def test_ranking_accuracy(self):
        """Airlines should be ranked correctly by count."""
        bookings = [
            # 5 bookings with Jet2
            *[create_mock_booking(id=i, dropoff_airline_name="Jet2", dropoff_airline_code="LS", pickup_airline_name="Jet2", pickup_airline_code="LS") for i in range(1, 6)],
            # 3 bookings with Ryanair
            *[create_mock_booking(id=i, dropoff_airline_name="Ryanair", dropoff_airline_code="FR", pickup_airline_name="Ryanair", pickup_airline_code="FR") for i in range(6, 9)],
            # 1 booking with BA
            create_mock_booking(id=9, dropoff_airline_name="British Airways", dropoff_airline_code="BA", pickup_airline_name="British Airways", pickup_airline_code="BA"),
        ]

        response = simulate_popular_report_endpoint(bookings)

        assert response["popularAirlines"][0]["airlineName"] == "Jet2"
        assert response["popularAirlines"][0]["count"] == 5
        assert response["popularAirlines"][1]["airlineName"] == "Ryanair"
        assert response["popularAirlines"][1]["count"] == 3
        assert response["popularAirlines"][2]["airlineName"] == "British Airways"
        assert response["popularAirlines"][2]["count"] == 1

    def test_meta_data_accuracy(self):
        """Meta data should accurately reflect the query and results."""
        bookings = [
            create_mock_booking(id=1),
            create_mock_booking(id=2),
            create_mock_booking(id=3),
        ]

        response = simulate_popular_report_endpoint(bookings, top=10)

        assert response["meta"]["totalBookings"] == 3
        assert response["meta"]["top"] == 10


# =============================================================================
# Integration Tests - Status Filtering
# =============================================================================

class TestStatusFilteringIntegration:
    """Integration tests for status filtering."""

    def test_only_confirmed_and_completed_included(self):
        """Only confirmed and completed bookings should be counted."""
        from db_models import BookingStatus

        all_bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
            create_mock_booking(id=5, status="confirmed"),
        ]

        # Simulate status filtering (confirmed + completed only)
        filtered = [
            b for b in all_bookings
            if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        ]

        response = simulate_popular_report_endpoint(filtered)

        assert response["meta"]["totalBookings"] == 3
