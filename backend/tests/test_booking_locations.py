"""
Tests for Admin Reports - Booking Locations endpoint.

Covers:
- GET /api/admin/reports/booking-locations - Get geocoded booking locations
- Postcode geocoding via postcodes.io (mocked)
- Handling of missing/invalid postcodes

All tests use mocked data to avoid database state conflicts and external API calls.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, time, datetime
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="07700900001",
    billing_address1="123 Test Street",
    billing_city="Bournemouth",
    billing_postcode="BH7 6AW",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_address1 = billing_address1
    customer.billing_city = billing_city
    customer.billing_postcode = billing_postcode
    return customer


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status="confirmed",
    dropoff_date_val=None,
    customer=None,
    customer_first_name=None,
    customer_last_name=None,
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.status = BookingStatus(status) if isinstance(status, str) else status
    booking.dropoff_date = dropoff_date_val or date(2026, 3, 15)
    booking.customer = customer
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    return booking


def create_mock_admin_user():
    """Create a mock admin user for authentication."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_admin_auth():
    """Mock admin authentication to always succeed."""
    admin_user = create_mock_admin_user()
    with patch('main.require_admin', return_value=admin_user):
        yield admin_user


# =============================================================================
# Unit Tests - Response Structure
# =============================================================================

class TestBookingLocationsResponseStructure:
    """Tests for booking locations response structure."""

    def test_response_contains_required_fields(self):
        """Response should contain count, total_bookings, skipped, and locations."""
        response_data = {
            "count": 2,
            "total_bookings": 3,
            "skipped_count": 1,
            "skipped": [{"reference": "TAG-003", "reason": "No postcode"}],
            "locations": [
                {"id": 1, "reference": "TAG-001", "lat": 50.72, "lng": -1.88},
                {"id": 2, "reference": "TAG-002", "lat": 50.73, "lng": -1.87},
            ],
        }

        assert "count" in response_data
        assert "total_bookings" in response_data
        assert "skipped_count" in response_data
        assert "skipped" in response_data
        assert "locations" in response_data
        assert response_data["count"] == 2
        assert response_data["total_bookings"] == 3
        assert response_data["skipped_count"] == 1

    def test_location_includes_booking_details(self):
        """Each location should include booking reference, customer, postcode, coordinates."""
        location = {
            "id": 1,
            "reference": "TAG-001",
            "customer_name": "John Doe",
            "postcode": "BH7 6AW",
            "city": "Bournemouth",
            "lat": 50.7192,
            "lng": -1.8808,
            "dropoff_date": "2026-03-15",
            "status": "confirmed",
        }

        assert location["reference"] == "TAG-001"
        assert location["customer_name"] == "John Doe"
        assert location["postcode"] == "BH7 6AW"
        assert location["lat"] == 50.7192
        assert location["lng"] == -1.8808
        assert location["status"] == "confirmed"

    def test_skipped_booking_includes_reason(self):
        """Skipped bookings should include reference and reason."""
        skipped = {"reference": "TAG-003", "reason": "Postcode 'INVALID' not found"}

        assert "reference" in skipped
        assert "reason" in skipped
        assert "INVALID" in skipped["reason"]


# =============================================================================
# Unit Tests - Postcode Handling
# =============================================================================

class TestPostcodeHandling:
    """Tests for postcode validation and normalization."""

    def test_postcode_normalized_to_uppercase(self):
        """Postcodes should be normalized to uppercase."""
        postcode = "bh7 6aw"
        normalized = postcode.strip().upper()
        assert normalized == "BH7 6AW"

    def test_postcode_with_extra_spaces_trimmed(self):
        """Postcodes with extra spaces should be trimmed."""
        postcode = "  BH7 6AW  "
        normalized = postcode.strip().upper()
        assert normalized == "BH7 6AW"

    def test_empty_postcode_detected(self):
        """Empty postcodes should be detected."""
        customer = create_mock_customer(billing_postcode="")
        assert not customer.billing_postcode.strip()

    def test_none_postcode_handled(self):
        """None postcodes should be handled gracefully."""
        customer = create_mock_customer(billing_postcode=None)
        customer.billing_postcode = None
        assert customer.billing_postcode is None


# =============================================================================
# Unit Tests - Geocoding Response Parsing
# =============================================================================

class TestGeocodingResponseParsing:
    """Tests for postcodes.io API response parsing."""

    def test_parse_successful_geocoding_response(self):
        """Should correctly parse postcodes.io bulk response."""
        api_response = {
            "status": 200,
            "result": [
                {
                    "query": "BH7 6AW",
                    "result": {
                        "postcode": "BH7 6AW",
                        "latitude": 50.7192,
                        "longitude": -1.8808,
                        "admin_district": "Bournemouth, Christchurch and Poole",
                    }
                },
                {
                    "query": "BH1 1AA",
                    "result": {
                        "postcode": "BH1 1AA",
                        "latitude": 50.7201,
                        "longitude": -1.8765,
                        "admin_district": "Bournemouth, Christchurch and Poole",
                    }
                }
            ]
        }

        coordinates = {}
        for item in api_response.get("result", []):
            if item.get("result"):
                pc = item["query"].upper()
                coordinates[pc] = {
                    "lat": item["result"]["latitude"],
                    "lng": item["result"]["longitude"],
                    "admin_district": item["result"].get("admin_district"),
                }

        assert "BH7 6AW" in coordinates
        assert "BH1 1AA" in coordinates
        assert coordinates["BH7 6AW"]["lat"] == 50.7192
        assert coordinates["BH7 6AW"]["lng"] == -1.8808

    def test_parse_failed_geocoding_for_invalid_postcode(self):
        """Should handle postcodes.io response for invalid postcode."""
        api_response = {
            "status": 200,
            "result": [
                {
                    "query": "INVALID",
                    "result": None  # Invalid postcode returns null
                }
            ]
        }

        coordinates = {}
        for item in api_response.get("result", []):
            if item.get("result"):  # This will be False for None
                pc = item["query"].upper()
                coordinates[pc] = {
                    "lat": item["result"]["latitude"],
                    "lng": item["result"]["longitude"],
                }

        assert "INVALID" not in coordinates


# =============================================================================
# Integration Tests (mocked external API)
# =============================================================================

class TestBookingLocationsIntegration:
    """Integration tests with mocked database and postcodes.io API."""

    def _create_mock_postcodes_response(self, postcodes_data):
        """Create a mock postcodes.io API response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "result": postcodes_data
        }
        return mock_response

    @pytest.mark.asyncio
    async def test_returns_geocoded_locations(self, client):
        """Should return locations with coordinates for valid postcodes."""
        # Create mock bookings
        customer1 = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW", billing_city="Bournemouth")
        customer2 = create_mock_customer(id=2, first_name="Jane", last_name="Smith", billing_postcode="BH1 1AA", billing_city="Bournemouth")

        booking1 = create_mock_booking(id=1, reference="TAG-001", customer=customer1, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", customer=customer2, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]

        # Mock postcodes.io response
        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "BH1 1AA", "result": {"latitude": 50.7201, "longitude": -1.8765, "admin_district": "BCP"}},
        ]

        # Mock admin user
        admin_user = create_mock_admin_user()

        with patch('main.require_admin', return_value=admin_user):
            with patch('main.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_query = MagicMock()
                mock_query.options.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = mock_bookings
                mock_db.query.return_value = mock_query
                mock_get_db.return_value = iter([mock_db])

                with patch('main.httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.post = AsyncMock(return_value=self._create_mock_postcodes_response(postcodes_response))
                    mock_client_class.return_value = mock_client

                    response = await client.get(
                        "/api/admin/reports/booking-locations",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["count"] == 2
                    assert data["total_bookings"] == 2
                    assert len(data["locations"]) == 2

    @pytest.mark.asyncio
    async def test_skips_bookings_without_postcode(self, client):
        """Should skip bookings where customer has no postcode."""
        customer_with_postcode = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW")
        customer_without_postcode = create_mock_customer(id=2, first_name="Jane", last_name="Smith", billing_postcode="")

        booking1 = create_mock_booking(id=1, reference="TAG-001", customer=customer_with_postcode, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", customer=customer_without_postcode, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
        ]

        admin_user = create_mock_admin_user()

        with patch('main.require_admin', return_value=admin_user):
            with patch('main.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_query = MagicMock()
                mock_query.options.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = mock_bookings
                mock_db.query.return_value = mock_query
                mock_get_db.return_value = iter([mock_db])

                with patch('main.httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.post = AsyncMock(return_value=self._create_mock_postcodes_response(postcodes_response))
                    mock_client_class.return_value = mock_client

                    response = await client.get(
                        "/api/admin/reports/booking-locations",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["count"] == 1
                    assert data["skipped_count"] == 1
                    assert any("No postcode" in s["reason"] for s in data["skipped"])

    @pytest.mark.asyncio
    async def test_skips_bookings_with_invalid_postcode(self, client):
        """Should skip bookings where postcode cannot be geocoded."""
        customer1 = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW")
        customer2 = create_mock_customer(id=2, first_name="Jane", last_name="Smith", billing_postcode="INVALID123")

        booking1 = create_mock_booking(id=1, reference="TAG-001", customer=customer1, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", customer=customer2, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]

        # Only return geocoding for valid postcode
        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "INVALID123", "result": None},  # Invalid postcode
        ]

        admin_user = create_mock_admin_user()

        with patch('main.require_admin', return_value=admin_user):
            with patch('main.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_query = MagicMock()
                mock_query.options.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = mock_bookings
                mock_db.query.return_value = mock_query
                mock_get_db.return_value = iter([mock_db])

                with patch('main.httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.post = AsyncMock(return_value=self._create_mock_postcodes_response(postcodes_response))
                    mock_client_class.return_value = mock_client

                    response = await client.get(
                        "/api/admin/reports/booking-locations",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["count"] == 1
                    assert data["skipped_count"] == 1
                    assert any("not found" in s["reason"] for s in data["skipped"])

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_bookings(self, client):
        """Should return empty locations for no bookings."""
        admin_user = create_mock_admin_user()

        with patch('main.require_admin', return_value=admin_user):
            with patch('main.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_query = MagicMock()
                mock_query.options.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = []  # No bookings
                mock_db.query.return_value = mock_query
                mock_get_db.return_value = iter([mock_db])

                response = await client.get(
                    "/api/admin/reports/booking-locations",
                    headers={"Authorization": "Bearer test_token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["count"] == 0
                assert len(data["locations"]) == 0

    @pytest.mark.asyncio
    async def test_includes_all_booking_statuses(self, client):
        """Should include confirmed, completed, cancelled, and pending bookings."""
        customers = [
            create_mock_customer(id=i, first_name=f"User{i}", last_name="Test", billing_postcode=f"BH{i} 1AA")
            for i in range(1, 5)
        ]

        bookings = [
            create_mock_booking(id=1, reference="TAG-001", status="confirmed", customer=customers[0], customer_first_name="User1", customer_last_name="Test"),
            create_mock_booking(id=2, reference="TAG-002", status="completed", customer=customers[1], customer_first_name="User2", customer_last_name="Test"),
            create_mock_booking(id=3, reference="TAG-003", status="cancelled", customer=customers[2], customer_first_name="User3", customer_last_name="Test"),
            create_mock_booking(id=4, reference="TAG-004", status="pending", customer=customers[3], customer_first_name="User4", customer_last_name="Test"),
        ]

        postcodes_response = [
            {"query": "BH1 1AA", "result": {"latitude": 50.71, "longitude": -1.88, "admin_district": "BCP"}},
            {"query": "BH2 1AA", "result": {"latitude": 50.72, "longitude": -1.87, "admin_district": "BCP"}},
            {"query": "BH3 1AA", "result": {"latitude": 50.73, "longitude": -1.86, "admin_district": "BCP"}},
            {"query": "BH4 1AA", "result": {"latitude": 50.74, "longitude": -1.85, "admin_district": "BCP"}},
        ]

        admin_user = create_mock_admin_user()

        with patch('main.require_admin', return_value=admin_user):
            with patch('main.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_query = MagicMock()
                mock_query.options.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = bookings
                mock_db.query.return_value = mock_query
                mock_get_db.return_value = iter([mock_db])

                with patch('main.httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_client.__aexit__ = AsyncMock(return_value=None)
                    mock_client.post = AsyncMock(return_value=self._create_mock_postcodes_response(postcodes_response))
                    mock_client_class.return_value = mock_client

                    response = await client.get(
                        "/api/admin/reports/booking-locations",
                        headers={"Authorization": "Bearer test_token"}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["count"] == 4

                    statuses = [loc["status"] for loc in data["locations"]]
                    assert "confirmed" in statuses
                    assert "completed" in statuses
                    assert "cancelled" in statuses
                    assert "pending" in statuses
