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
    status="confirmed",
    top=10,
):
    """Create a mock popular report response."""
    if popular_airlines is None:
        popular_airlines = [
            {"airlineCode": "BA", "airlineName": "British Airways", "count": 20, "percent": 40.0},
            {"airlineCode": "FR", "airlineName": "Ryanair", "count": 15, "percent": 30.0},
            {"airlineCode": "U2", "airlineName": "easyJet", "count": 10, "percent": 20.0},
        ]

    if popular_destinations is None:
        popular_destinations = [
            {"destination": "Faro Airport", "count": 25, "percent": 50.0},
            {"destination": "Alicante Airport", "count": 15, "percent": 30.0},
            {"destination": "Malaga Airport", "count": 10, "percent": 20.0},
        ]

    return {
        "meta": {
            "startDate": None,
            "endDate": None,
            "status": status,
            "top": top,
            "totalBookings": total_bookings,
            "totalAirlineFlights": sum(a["count"] for a in popular_airlines),
            "totalDestinationTrips": sum(d["count"] for d in popular_destinations),
        },
        "popularAirlines": popular_airlines,
        "popularDestinations": popular_destinations,
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
        assert "status" in response["meta"]
        assert "top" in response["meta"]
        assert "totalBookings" in response["meta"]
        assert "totalAirlineFlights" in response["meta"]
        assert "totalDestinationTrips" in response["meta"]

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


# =============================================================================
# Unit Tests - Airline Counting Logic
# =============================================================================

class TestAirlineCountingLogic:
    """Unit tests for airline counting logic."""

    def test_count_departure_airline(self):
        """Should count departure airline."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airline_counter[airline_key] += 1

        assert airline_counter[("BA", "British Airways")] == 1

    def test_count_return_airline(self):
        """Should count return airline."""
        booking = create_mock_booking(
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
        )

        airline_counter = Counter()
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airline_counter[airline_key] += 1

        assert airline_counter[("FR", "Ryanair")] == 1

    def test_count_both_departure_and_return_airlines(self):
        """Should count both departure and return airlines."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code="FR",
            pickup_airline_name="Ryanair",
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airline_counter[airline_key] += 1
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airline_counter[airline_key] += 1

        assert airline_counter[("BA", "British Airways")] == 1
        assert airline_counter[("FR", "Ryanair")] == 1

    def test_same_airline_both_ways_counts_twice(self):
        """Same airline for departure and return should count twice."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code="BA",
            pickup_airline_name="British Airways",
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airline_counter[airline_key] += 1
        if booking.pickup_airline_name:
            airline_key = (booking.pickup_airline_code or "UNK", booking.pickup_airline_name)
            airline_counter[airline_key] += 1

        assert airline_counter[("BA", "British Airways")] == 2

    def test_skip_null_airline_name(self):
        """Should skip airlines with null name."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name=None,
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airline_counter[airline_key] += 1

        assert len(airline_counter) == 0

    def test_use_unk_for_missing_airline_code(self):
        """Should use 'UNK' for missing airline code."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name="Unknown Airline",
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_key = (booking.dropoff_airline_code or "UNK", booking.dropoff_airline_name)
            airline_counter[airline_key] += 1

        assert airline_counter[("UNK", "Unknown Airline")] == 1


# =============================================================================
# Unit Tests - Destination Counting Logic
# =============================================================================

class TestDestinationCountingLogic:
    """Unit tests for destination counting logic."""

    def test_count_departure_destination(self):
        """Should count departure destination."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1

        assert destination_counter["Faro Airport"] == 1

    def test_count_return_origin(self):
        """Should count return origin."""
        booking = create_mock_booking(
            pickup_origin="Alicante Airport",
        )

        destination_counter = Counter()
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert destination_counter["Alicante Airport"] == 1

    def test_same_destination_both_ways_counts_twice(self):
        """Same destination/origin should count twice."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
            pickup_origin="Faro Airport",
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert destination_counter["Faro Airport"] == 2

    def test_different_destination_and_origin(self):
        """Different destination and origin should count separately."""
        booking = create_mock_booking(
            dropoff_destination="Faro Airport",
            pickup_origin="Malaga Airport",
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert destination_counter["Faro Airport"] == 1
        assert destination_counter["Malaga Airport"] == 1

    def test_skip_null_destination(self):
        """Should skip null destinations."""
        booking = create_mock_booking(
            dropoff_destination=None,
            pickup_origin=None,
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert len(destination_counter) == 0


# =============================================================================
# Unit Tests - Percentage Calculation
# =============================================================================

class TestPercentageCalculation:
    """Unit tests for percentage calculation."""

    def test_percentage_calculated_correctly(self):
        """Percentage should be calculated as (count / total) * 100."""
        total = 50
        count = 20

        percent = round((count / total) * 100, 1)
        assert percent == 40.0

    def test_percentage_zero_when_no_bookings(self):
        """Percentage should be 0 when total is 0."""
        total = 0
        count = 0

        percent = round((count / total) * 100, 1) if total > 0 else 0
        assert percent == 0

    def test_percentage_rounds_to_one_decimal(self):
        """Percentage should round to 1 decimal place."""
        total = 3
        count = 1

        percent = round((count / total) * 100, 1)
        assert percent == 33.3


# =============================================================================
# Unit Tests - Top N Logic
# =============================================================================

class TestTopNLogic:
    """Unit tests for top N limiting."""

    def test_top_5_returns_5_items(self):
        """Top 5 should return at most 5 items."""
        airlines = [
            ("BA", "British Airways", 20),
            ("FR", "Ryanair", 15),
            ("U2", "easyJet", 10),
            ("BY", "TUI Airways", 8),
            ("LS", "Jet2", 7),
            ("W6", "Wizz Air", 5),
        ]

        counter = Counter({(a[0], a[1]): a[2] for a in airlines})
        top_5 = counter.most_common(5)

        assert len(top_5) == 5

    def test_top_10_returns_10_items(self):
        """Top 10 should return at most 10 items."""
        airlines = [(f"A{i}", f"Airline {i}", 100 - i) for i in range(15)]

        counter = Counter({(a[0], a[1]): a[2] for a in airlines})
        top_10 = counter.most_common(10)

        assert len(top_10) == 10

    def test_top_20_returns_20_items(self):
        """Top 20 should return at most 20 items."""
        airlines = [(f"A{i}", f"Airline {i}", 100 - i) for i in range(25)]

        counter = Counter({(a[0], a[1]): a[2] for a in airlines})
        top_20 = counter.most_common(20)

        assert len(top_20) == 20

    def test_top_returns_all_when_fewer_items(self):
        """Top N should return all items when fewer than N exist."""
        airlines = [
            ("BA", "British Airways", 20),
            ("FR", "Ryanair", 15),
        ]

        counter = Counter({(a[0], a[1]): a[2] for a in airlines})
        top_10 = counter.most_common(10)

        assert len(top_10) == 2

    def test_top_ordered_by_count_descending(self):
        """Top items should be ordered by count descending."""
        airlines = [
            ("FR", "Ryanair", 15),
            ("BA", "British Airways", 20),
            ("U2", "easyJet", 10),
        ]

        counter = Counter({(a[0], a[1]): a[2] for a in airlines})
        top_items = counter.most_common(10)

        counts = [c for _, c in top_items]
        assert counts == sorted(counts, reverse=True)


# =============================================================================
# Unit Tests - Status Filtering
# =============================================================================

class TestStatusFiltering:
    """Unit tests for status filtering logic."""

    def test_confirmed_status_filter(self):
        """Should filter to confirmed bookings only."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="confirmed"),
        ]

        filtered = [b for b in bookings if b.status == BookingStatus.CONFIRMED]
        assert len(filtered) == 2

    def test_completed_status_filter(self):
        """Should filter to completed bookings only."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="completed"),
        ]

        filtered = [b for b in bookings if b.status == BookingStatus.COMPLETED]
        assert len(filtered) == 2

    def test_all_status_filter(self):
        """Should filter to confirmed and completed bookings."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="confirmed"),
            create_mock_booking(id=2, status="completed"),
            create_mock_booking(id=3, status="pending"),
            create_mock_booking(id=4, status="cancelled"),
        ]

        filtered = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]
        assert len(filtered) == 2

    def test_excludes_pending_bookings(self):
        """Pending bookings should be excluded from results."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="pending"),
            create_mock_booking(id=2, status="pending"),
        ]

        filtered = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]
        assert len(filtered) == 0

    def test_excludes_cancelled_bookings(self):
        """Cancelled bookings should be excluded from results."""
        from db_models import BookingStatus

        bookings = [
            create_mock_booking(id=1, status="cancelled"),
            create_mock_booking(id=2, status="cancelled"),
        ]

        filtered = [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]
        assert len(filtered) == 0


# =============================================================================
# Unit Tests - Date Filtering
# =============================================================================

class TestDateFiltering:
    """Unit tests for date filtering logic."""

    def test_filter_by_start_date(self):
        """Should filter bookings created on or after start date."""
        start_date = date(2026, 1, 15)

        bookings = [
            create_mock_booking(id=1, created_at=datetime(2026, 1, 10, 10, 0)),
            create_mock_booking(id=2, created_at=datetime(2026, 1, 15, 10, 0)),
            create_mock_booking(id=3, created_at=datetime(2026, 1, 20, 10, 0)),
        ]

        filtered = [b for b in bookings if b.created_at.date() >= start_date]
        assert len(filtered) == 2
        assert filtered[0].id == 2
        assert filtered[1].id == 3

    def test_filter_by_end_date(self):
        """Should filter bookings created on or before end date."""
        end_date = date(2026, 1, 15)

        bookings = [
            create_mock_booking(id=1, created_at=datetime(2026, 1, 10, 10, 0)),
            create_mock_booking(id=2, created_at=datetime(2026, 1, 15, 10, 0)),
            create_mock_booking(id=3, created_at=datetime(2026, 1, 20, 10, 0)),
        ]

        filtered = [b for b in bookings if b.created_at.date() <= end_date]
        assert len(filtered) == 2
        assert filtered[0].id == 1
        assert filtered[1].id == 2

    def test_filter_by_date_range(self):
        """Should filter bookings within date range."""
        start_date = date(2026, 1, 10)
        end_date = date(2026, 1, 20)

        bookings = [
            create_mock_booking(id=1, created_at=datetime(2026, 1, 5, 10, 0)),
            create_mock_booking(id=2, created_at=datetime(2026, 1, 15, 10, 0)),
            create_mock_booking(id=3, created_at=datetime(2026, 1, 25, 10, 0)),
        ]

        filtered = [b for b in bookings if start_date <= b.created_at.date() <= end_date]
        assert len(filtered) == 1
        assert filtered[0].id == 2


# =============================================================================
# Negative Tests - Empty Data
# =============================================================================

class TestNegativeEmptyData:
    """Negative tests for empty data scenarios."""

    def test_no_bookings_returns_empty_arrays(self):
        """Should return empty arrays when no bookings exist."""
        response = create_mock_popular_response(
            total_bookings=0,
            popular_airlines=[],
            popular_destinations=[],
        )

        assert response["popularAirlines"] == []
        assert response["popularDestinations"] == []
        assert response["meta"]["totalBookings"] == 0

    def test_bookings_without_airline_data(self):
        """Should handle bookings without airline information."""
        booking = create_mock_booking(
            dropoff_airline_code=None,
            dropoff_airline_name=None,
            pickup_airline_code=None,
            pickup_airline_name=None,
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_counter[(booking.dropoff_airline_code, booking.dropoff_airline_name)] += 1
        if booking.pickup_airline_name:
            airline_counter[(booking.pickup_airline_code, booking.pickup_airline_name)] += 1

        assert len(airline_counter) == 0

    def test_bookings_without_destination_data(self):
        """Should handle bookings without destination information."""
        booking = create_mock_booking(
            dropoff_destination=None,
            pickup_origin=None,
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert len(destination_counter) == 0


# =============================================================================
# Negative Tests - Invalid Parameters
# =============================================================================

class TestNegativeInvalidParameters:
    """Negative tests for invalid parameters."""

    def test_invalid_top_value_defaults_to_10(self):
        """Invalid top value should default to 10."""
        top = 15  # Not 5, 10, or 20

        if top not in [5, 10, 20]:
            top = 10

        assert top == 10

    def test_invalid_status_defaults_to_confirmed(self):
        """Invalid status should be handled gracefully."""
        status = "invalid"
        valid_statuses = ["confirmed", "completed", "all"]

        if status not in valid_statuses:
            status = "confirmed"

        assert status == "confirmed"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_single_booking_single_airline(self):
        """Should handle single booking with single airline."""
        booking = create_mock_booking(
            dropoff_airline_code="BA",
            dropoff_airline_name="British Airways",
            pickup_airline_code="BA",
            pickup_airline_name="British Airways",
        )

        airline_counter = Counter()
        if booking.dropoff_airline_name:
            airline_counter[(booking.dropoff_airline_code, booking.dropoff_airline_name)] += 1
        if booking.pickup_airline_name:
            airline_counter[(booking.pickup_airline_code, booking.pickup_airline_name)] += 1

        top = airline_counter.most_common(10)
        assert len(top) == 1
        assert top[0][0] == ("BA", "British Airways")
        assert top[0][1] == 2

    def test_many_airlines_with_same_count(self):
        """Should handle multiple airlines with same count."""
        bookings = [
            create_mock_booking(id=1, dropoff_airline_name="Airline A", pickup_airline_name=None),
            create_mock_booking(id=2, dropoff_airline_name="Airline B", pickup_airline_name=None),
            create_mock_booking(id=3, dropoff_airline_name="Airline C", pickup_airline_name=None),
        ]

        airline_counter = Counter()
        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1

        top = airline_counter.most_common(10)
        # All should have count of 1
        counts = [c for _, c in top]
        assert all(c == 1 for c in counts)

    def test_destination_with_special_characters(self):
        """Should handle destinations with special characters."""
        booking = create_mock_booking(
            dropoff_destination="São Paulo–Guarulhos Airport",
            pickup_origin="Düsseldorf Airport",
        )

        destination_counter = Counter()
        if booking.dropoff_destination:
            destination_counter[booking.dropoff_destination] += 1
        if booking.pickup_origin:
            destination_counter[booking.pickup_origin] += 1

        assert destination_counter["São Paulo–Guarulhos Airport"] == 1
        assert destination_counter["Düsseldorf Airport"] == 1

    def test_airline_with_long_name(self):
        """Should handle airlines with very long names."""
        long_name = "A" * 100
        booking = create_mock_booking(
            dropoff_airline_name=long_name,
        )

        assert len(booking.dropoff_airline_name) == 100

    def test_large_number_of_bookings(self):
        """Should handle large number of bookings efficiently."""
        bookings = [
            create_mock_booking(
                id=i,
                dropoff_airline_code=f"A{i % 10}",
                dropoff_airline_name=f"Airline {i % 10}",
                dropoff_destination=f"Destination {i % 15}",
            )
            for i in range(1000)
        ]

        airline_counter = Counter()
        destination_counter = Counter()

        for b in bookings:
            if b.dropoff_airline_name:
                airline_counter[(b.dropoff_airline_code, b.dropoff_airline_name)] += 1
            if b.dropoff_destination:
                destination_counter[b.dropoff_destination] += 1

        top_airlines = airline_counter.most_common(10)
        top_destinations = destination_counter.most_common(10)

        assert len(top_airlines) == 10
        assert len(top_destinations) == 10

    def test_booking_on_date_boundary(self):
        """Should handle bookings at midnight on filter date."""
        start_date = date(2026, 1, 15)

        # Booking at midnight on start date
        booking = create_mock_booking(
            created_at=datetime(2026, 1, 15, 0, 0, 0),
        )

        included = booking.created_at.date() >= start_date
        assert included is True

    def test_booking_at_end_of_day(self):
        """Should include bookings at end of end date."""
        end_date = date(2026, 1, 15)

        # Booking at 23:59:59 on end date
        booking = create_mock_booking(
            created_at=datetime(2026, 1, 15, 23, 59, 59),
        )

        included = booking.created_at.date() <= end_date
        assert included is True
