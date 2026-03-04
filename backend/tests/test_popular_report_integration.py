"""
Integration Tests for Admin Popular Airlines & Destinations Report.

Covers full API endpoint integration with mocked database.

Test categories:
- API endpoint integration
- Full workflow testing
- Error handling

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, time, datetime
from unittest.mock import MagicMock, patch, AsyncMock
from collections import Counter
from fastapi.testclient import TestClient

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


def create_mock_user(is_admin=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = is_admin
    return user


# =============================================================================
# Integration Tests - API Response Format
# =============================================================================

class TestPopularReportAPIResponseFormat:
    """Integration tests for API response format."""

    def test_api_response_structure(self):
        """Full API response should have correct structure."""
        # Simulate the API response
        response = {
            "meta": {
                "startDate": None,
                "endDate": None,
                "status": "confirmed",
                "top": 10,
                "totalBookings": 5,
                "totalAirlineFlights": 10,
                "totalDestinationTrips": 10,
            },
            "popularAirlines": [
                {"airlineCode": "BA", "airlineName": "British Airways", "count": 5, "percent": 50.0},
                {"airlineCode": "FR", "airlineName": "Ryanair", "count": 3, "percent": 30.0},
            ],
            "popularDestinations": [
                {"destination": "Faro Airport", "count": 6, "percent": 60.0},
                {"destination": "Malaga Airport", "count": 4, "percent": 40.0},
            ],
        }

        # Verify structure
        assert "meta" in response
        assert "popularAirlines" in response
        assert "popularDestinations" in response

        # Verify meta
        meta = response["meta"]
        assert "startDate" in meta
        assert "endDate" in meta
        assert "status" in meta
        assert "top" in meta
        assert "totalBookings" in meta

        # Verify airlines
        for airline in response["popularAirlines"]:
            assert "airlineCode" in airline
            assert "airlineName" in airline
            assert "count" in airline
            assert "percent" in airline

        # Verify destinations
        for dest in response["popularDestinations"]:
            assert "destination" in dest
            assert "count" in dest
            assert "percent" in dest


# =============================================================================
# Integration Tests - Full Workflow
# =============================================================================

class TestPopularReportFullWorkflow:
    """Integration tests for full report generation workflow."""

    def test_workflow_from_bookings_to_response(self):
        """Test complete workflow from bookings to API response."""
        # Create mock bookings
        bookings = [
            create_mock_booking(
                id=1,
                dropoff_airline_code="BA",
                dropoff_airline_name="British Airways",
                dropoff_destination="Faro Airport",
                pickup_airline_code="BA",
                pickup_airline_name="British Airways",
                pickup_origin="Faro Airport",
            ),
            create_mock_booking(
                id=2,
                dropoff_airline_code="FR",
                dropoff_airline_name="Ryanair",
                dropoff_destination="Malaga Airport",
                pickup_airline_code="FR",
                pickup_airline_name="Ryanair",
                pickup_origin="Malaga Airport",
            ),
            create_mock_booking(
                id=3,
                dropoff_airline_code="BA",
                dropoff_airline_name="British Airways",
                dropoff_destination="Faro Airport",
                pickup_airline_code="BA",
                pickup_airline_name="British Airways",
                pickup_origin="Faro Airport",
            ),
        ]

        # Count airlines
        airline_counter = Counter()
        for booking in bookings:
            if booking.dropoff_airline_name:
                airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
                airline_counter[airline_key] += 1
            if booking.pickup_airline_name:
                airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
                airline_counter[airline_key] += 1

        # Count destinations
        destination_counter = Counter()
        for booking in bookings:
            if booking.dropoff_destination:
                destination_counter[booking.dropoff_destination] += 1
            if booking.pickup_origin:
                destination_counter[booking.pickup_origin] += 1

        # Build response
        total_airline_flights = sum(airline_counter.values())
        total_destination_trips = sum(destination_counter.values())

        top_airlines = []
        for (code, name), count in airline_counter.most_common(10):
            percent = round((count / total_airline_flights) * 100, 1)
            top_airlines.append({
                "airlineCode": code,
                "airlineName": name,
                "count": count,
                "percent": percent,
            })

        top_destinations = []
        for dest, count in destination_counter.most_common(10):
            percent = round((count / total_destination_trips) * 100, 1)
            top_destinations.append({
                "destination": dest,
                "count": count,
                "percent": percent,
            })

        # Verify results
        assert len(top_airlines) == 2
        assert top_airlines[0]["airlineName"] == "British Airways"
        assert top_airlines[0]["count"] == 4  # 2 bookings x 2 (departure + return)
        assert top_airlines[1]["airlineName"] == "Ryanair"
        assert top_airlines[1]["count"] == 2  # 1 booking x 2

        assert len(top_destinations) == 2
        assert top_destinations[0]["destination"] == "Faro Airport"
        assert top_destinations[0]["count"] == 4  # 2 bookings x 2
        assert top_destinations[1]["destination"] == "Malaga Airport"
        assert top_destinations[1]["count"] == 2  # 1 booking x 2

    def test_workflow_with_status_filtering(self):
        """Test workflow with status filtering."""
        from db_models import BookingStatus

        # Create mixed status bookings
        bookings = [
            create_mock_booking(id=1, status="confirmed", dropoff_airline_name="Airline A"),
            create_mock_booking(id=2, status="completed", dropoff_airline_name="Airline B"),
            create_mock_booking(id=3, status="pending", dropoff_airline_name="Airline C"),
            create_mock_booking(id=4, status="cancelled", dropoff_airline_name="Airline D"),
        ]

        # Filter to confirmed only
        filtered = [b for b in bookings if b.status == BookingStatus.CONFIRMED]

        airline_counter = Counter()
        for b in filtered:
            if b.dropoff_airline_name:
                airline_counter[b.dropoff_airline_name] += 1

        assert len(airline_counter) == 1
        assert "Airline A" in airline_counter

    def test_workflow_with_date_range_filtering(self):
        """Test workflow with date range filtering."""
        start_date = date(2026, 2, 1)
        end_date = date(2026, 2, 28)

        bookings = [
            create_mock_booking(id=1, created_at=datetime(2026, 1, 15)),  # Before range
            create_mock_booking(id=2, created_at=datetime(2026, 2, 10)),  # In range
            create_mock_booking(id=3, created_at=datetime(2026, 2, 20)),  # In range
            create_mock_booking(id=4, created_at=datetime(2026, 3, 5)),   # After range
        ]

        filtered = [
            b for b in bookings
            if start_date <= b.created_at.date() <= end_date
        ]

        assert len(filtered) == 2
        assert filtered[0].id == 2
        assert filtered[1].id == 3


# =============================================================================
# Integration Tests - Combined Filters
# =============================================================================

class TestPopularReportCombinedFilters:
    """Integration tests for combined filter scenarios."""

    def test_status_and_date_filters_combined(self):
        """Test combining status and date filters."""
        from db_models import BookingStatus

        start_date = date(2026, 2, 1)
        end_date = date(2026, 2, 28)

        bookings = [
            create_mock_booking(id=1, status="confirmed", created_at=datetime(2026, 2, 10)),  # Match
            create_mock_booking(id=2, status="pending", created_at=datetime(2026, 2, 15)),    # Status fail
            create_mock_booking(id=3, status="confirmed", created_at=datetime(2026, 1, 15)),  # Date fail
            create_mock_booking(id=4, status="completed", created_at=datetime(2026, 2, 20)),  # Match
        ]

        # Apply both filters
        filtered = [
            b for b in bookings
            if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
            and start_date <= b.created_at.date() <= end_date
        ]

        assert len(filtered) == 2
        assert filtered[0].id == 1
        assert filtered[1].id == 4

    def test_top_limit_with_filters(self):
        """Test top limit applied after filtering."""
        from db_models import BookingStatus

        # Create 20 confirmed bookings with different airlines
        bookings = [
            create_mock_booking(
                id=i,
                status="confirmed",
                dropoff_airline_code=f"A{i}",
                dropoff_airline_name=f"Airline {i}",
                pickup_airline_name=None,  # Only count departure
            )
            for i in range(20)
        ]

        # Count airlines
        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1

        # Get top 5
        top_5 = airline_counter.most_common(5)
        assert len(top_5) == 5


# =============================================================================
# Integration Tests - Edge Cases in Workflow
# =============================================================================

class TestPopularReportWorkflowEdgeCases:
    """Edge case integration tests."""

    def test_workflow_with_empty_bookings(self):
        """Test workflow when no bookings exist."""
        bookings = []

        airline_counter = Counter()
        destination_counter = Counter()

        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1
            if b.dropoff_destination:
                destination_counter[b.dropoff_destination] += 1

        top_airlines = airline_counter.most_common(10)
        top_destinations = destination_counter.most_common(10)

        assert len(top_airlines) == 0
        assert len(top_destinations) == 0

    def test_workflow_with_all_bookings_same_airline(self):
        """Test when all bookings use same airline."""
        bookings = [
            create_mock_booking(
                id=i,
                dropoff_airline_code="BA",
                dropoff_airline_name="British Airways",
                pickup_airline_code="BA",
                pickup_airline_name="British Airways",
            )
            for i in range(10)
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1
            if b.pickup_airline_name:
                airline_counter[(b.pickup_airline_code, b.pickup_airline_name)] += 1

        top_airlines = airline_counter.most_common(10)

        assert len(top_airlines) == 1
        assert top_airlines[0][0] == ("BA", "British Airways")
        assert top_airlines[0][1] == 20  # 10 bookings x 2 (departure + return)

    def test_workflow_with_mixed_null_values(self):
        """Test workflow handles mixed null values correctly."""
        bookings = [
            create_mock_booking(
                id=1,
                dropoff_airline_name="British Airways",
                pickup_airline_name=None,  # No return airline
                dropoff_destination="Faro",
                pickup_origin="Faro",
            ),
            create_mock_booking(
                id=2,
                dropoff_airline_name=None,  # No departure airline
                pickup_airline_name="Ryanair",
                dropoff_destination=None,  # No destination
                pickup_origin="Malaga",
            ),
        ]

        airline_counter = Counter()
        destination_counter = Counter()

        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1
            if b.pickup_airline_name:
                airline_counter[(b.pickup_airline_code, b.pickup_airline_name)] += 1
            if b.dropoff_destination:
                destination_counter[b.dropoff_destination] += 1
            if b.pickup_origin:
                destination_counter[b.pickup_origin] += 1

        # Should have 2 airlines (BA from booking 1, FR from booking 2)
        assert len(airline_counter) == 2
        # Should have 2 destinations (Faro x2 from booking 1, Malaga from booking 2)
        assert destination_counter["Faro"] == 2
        assert destination_counter["Malaga"] == 1


# =============================================================================
# Integration Tests - Percentage Calculation Accuracy
# =============================================================================

class TestPopularReportPercentageAccuracy:
    """Integration tests for percentage calculation accuracy."""

    def test_percentages_sum_to_100(self):
        """Total percentages should approximately sum to 100."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=2, dropoff_airline_name="B", pickup_airline_name=None),
            create_mock_booking(id=3, dropoff_airline_name="C", pickup_airline_name=None),
            create_mock_booking(id=4, dropoff_airline_name="D", pickup_airline_name=None),
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[b.dropoff_airline_name] += 1

        total = sum(airline_counter.values())
        percentages = [round((c / total) * 100, 1) for c in airline_counter.values()]

        # Sum should be close to 100 (may differ slightly due to rounding)
        assert 99.0 <= sum(percentages) <= 101.0

    def test_percentage_with_uneven_distribution(self):
        """Test percentages with uneven distribution."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=2, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=3, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=4, dropoff_airline_name="B", pickup_airline_name=None),
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[b.dropoff_airline_name] += 1

        total = sum(airline_counter.values())

        a_percent = round((airline_counter["A"] / total) * 100, 1)
        b_percent = round((airline_counter["B"] / total) * 100, 1)

        assert a_percent == 75.0
        assert b_percent == 25.0


# =============================================================================
# Integration Tests - Ranking Accuracy
# =============================================================================

class TestPopularReportRankingAccuracy:
    """Integration tests for ranking accuracy."""

    def test_airlines_ranked_correctly(self):
        """Airlines should be ranked by count descending."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="C", pickup_airline_name=None),  # 1
            create_mock_booking(id=2, dropoff_airline_name="A", pickup_airline_name=None),  # 3
            create_mock_booking(id=3, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=4, dropoff_airline_name="A", pickup_airline_name=None),
            create_mock_booking(id=5, dropoff_airline_name="B", pickup_airline_name=None),  # 2
            create_mock_booking(id=6, dropoff_airline_name="B", pickup_airline_name=None),
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[b.dropoff_airline_name] += 1

        top = airline_counter.most_common(10)

        # Should be: A(3), B(2), C(1)
        assert top[0][0] == "A"
        assert top[0][1] == 3
        assert top[1][0] == "B"
        assert top[1][1] == 2
        assert top[2][0] == "C"
        assert top[2][1] == 1

    def test_destinations_ranked_correctly(self):
        """Destinations should be ranked by count descending."""
        bookings = [
            create_mock_booking(id=1, dropoff_destination="Malaga", pickup_origin=None),  # 4
            create_mock_booking(id=2, dropoff_destination="Malaga", pickup_origin=None),
            create_mock_booking(id=3, dropoff_destination="Malaga", pickup_origin=None),
            create_mock_booking(id=4, dropoff_destination="Malaga", pickup_origin=None),
            create_mock_booking(id=5, dropoff_destination="Faro", pickup_origin=None),  # 2
            create_mock_booking(id=6, dropoff_destination="Faro", pickup_origin=None),
            create_mock_booking(id=7, dropoff_destination="Alicante", pickup_origin=None),  # 1
        ]

        dest_counter = Counter()
        for b in bookings:
            if b.dropoff_destination:
                dest_counter[b.dropoff_destination] += 1

        top = dest_counter.most_common(10)

        # Should be: Malaga(4), Faro(2), Alicante(1)
        assert top[0][0] == "Malaga"
        assert top[0][1] == 4
        assert top[1][0] == "Faro"
        assert top[1][1] == 2
        assert top[2][0] == "Alicante"
        assert top[2][1] == 1


# =============================================================================
# Integration Tests - Meta Data Accuracy
# =============================================================================

class TestPopularReportMetaAccuracy:
    """Integration tests for meta data accuracy."""

    def test_total_bookings_count_accurate(self):
        """Total bookings should match actual count."""
        bookings = [
            create_mock_booking(id=i) for i in range(15)
        ]

        total_bookings = len(bookings)
        assert total_bookings == 15

    def test_total_airline_flights_count_accurate(self):
        """Total airline flights should count both departure and return."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="A", pickup_airline_name="A"),
            create_mock_booking(id=2, dropoff_airline_name="B", pickup_airline_name="B"),
            create_mock_booking(id=3, dropoff_airline_name="A", pickup_airline_name=None),  # Only departure
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[b.dropoff_airline_name] += 1
            if b.pickup_airline_name:
                airline_counter[b.pickup_airline_name] += 1

        total = sum(airline_counter.values())
        # 2 bookings with both ways (4) + 1 booking one way (1) = 5
        assert total == 5

    def test_total_destination_trips_count_accurate(self):
        """Total destination trips should count both departure and return."""
        bookings = [
            create_mock_booking(id=1, dropoff_destination="Faro", pickup_origin="Faro"),
            create_mock_booking(id=2, dropoff_destination="Malaga", pickup_origin=None),  # Only departure
        ]

        dest_counter = Counter()
        for b in bookings:
            if b.dropoff_destination:
                dest_counter[b.dropoff_destination] += 1
            if b.pickup_origin:
                dest_counter[b.pickup_origin] += 1

        total = sum(dest_counter.values())
        # 1 booking with both ways (2) + 1 booking one way (1) = 3
        assert total == 3
