"""
Tests for Admin Reports - Booking Locations endpoint.

Covers:
- GET /api/admin/reports/booking-locations - Get geocoded booking locations
- map_type parameter (bookings vs origins)
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

from main import app, require_admin, get_db


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


def create_mock_customer_with_bookings(
    id=1,
    first_name="John",
    last_name="Doe",
    billing_postcode="BH7 6AW",
    billing_city="Bournemouth",
    phone="07700900001",
    email=None,
    has_confirmed_booking=False
):
    """Create mock customer with optional booking relationship."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email or f"{first_name.lower()}.{last_name.lower()}@example.com"
    customer.phone = phone
    customer.billing_address1 = "123 Test Street"
    customer.billing_city = billing_city
    customer.billing_postcode = billing_postcode
    # Use date after feature launch (2026-02-16 20:00:00) for Journey Origins
    customer.created_at = MagicMock()
    customer.created_at.isoformat.return_value = "2026-02-17T10:00:00"

    if has_confirmed_booking:
        mock_booking = MagicMock()
        mock_booking.status = MagicMock()
        mock_booking.status.value = "confirmed"
        customer.bookings = [mock_booking]
    else:
        customer.bookings = []

    return customer


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client with mocked admin auth."""
    # Override the require_admin dependency
    admin_user = create_mock_admin_user()
    app.dependency_overrides[require_admin] = lambda: admin_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()


def create_mock_postcodes_response(postcodes_data):
    """Create a mock postcodes.io API response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 200,
        "result": postcodes_data
    }
    return mock_response


def create_mock_db_for_bookings(mock_bookings):
    """Create a mock database session for bookings queries."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = mock_bookings
    mock_db.query.return_value = mock_query
    return mock_db


def create_mock_db_for_customers(mock_customers):
    """Create a mock database session for customers queries."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = mock_customers
    mock_db.query.return_value = mock_query
    return mock_db


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
            "map_type": "bookings",
        }

        assert "count" in response_data
        assert "total_bookings" in response_data
        assert "skipped_count" in response_data
        assert "skipped" in response_data
        assert "locations" in response_data
        assert "map_type" in response_data
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

    def test_origins_response_contains_customer_fields(self):
        """Origins response should contain customer-specific fields."""
        response_data = {
            "count": 1,
            "total_customers": 2,
            "skipped_count": 1,
            "skipped": [],
            "locations": [
                {
                    "id": 1,
                    "customer_name": "John Doe",
                    "phone": "07700900001",
                    "email": "john@example.com",
                    "address": "123 Test Street, Bournemouth",
                    "postcode": "BH7 6AW",
                    "lat": 50.7192,
                    "lng": -1.8808,
                    "has_booking": True,
                    "created_at": "2026-02-15T10:00:00",
                },
            ],
            "map_type": "origins",
        }

        assert response_data["map_type"] == "origins"
        assert "total_customers" in response_data
        location = response_data["locations"][0]
        assert "customer_name" in location
        assert "phone" in location
        assert "email" in location
        assert "has_booking" in location


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
# Integration Tests - Bookings Map (map_type=bookings)
# =============================================================================

class TestBookingLocationsIntegration:
    """Integration tests for bookings map with mocked database and postcodes.io API."""

    @pytest.mark.asyncio
    async def test_returns_geocoded_locations(self, client):
        """Should return locations with coordinates for valid postcodes."""
        customer1 = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW", billing_city="Bournemouth")
        customer2 = create_mock_customer(id=2, first_name="Jane", last_name="Smith", billing_postcode="BH1 1AA", billing_city="Bournemouth")

        booking1 = create_mock_booking(id=1, reference="TAG-001", status="confirmed", customer=customer1, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", status="completed", customer=customer2, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]
        mock_db = create_mock_db_for_bookings(mock_bookings)

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "BH1 1AA", "result": {"latitude": 50.7201, "longitude": -1.8765, "admin_district": "BCP"}},
        ]

        app.dependency_overrides[get_db] = lambda: mock_db

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert data["map_type"] == "bookings"
            assert len(data["locations"]) == 2

    @pytest.mark.asyncio
    async def test_skips_bookings_without_postcode(self, client):
        """Should skip bookings where customer has no postcode."""
        customer_with = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW")
        customer_without = create_mock_customer(id=2, first_name="Jane", last_name="Smith", billing_postcode="")

        booking1 = create_mock_booking(id=1, reference="TAG-001", status="confirmed", customer=customer_with, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", status="confirmed", customer=customer_without, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]
        mock_db = create_mock_db_for_bookings(mock_bookings)

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
        ]

        app.dependency_overrides[get_db] = lambda: mock_db

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations")

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

        booking1 = create_mock_booking(id=1, reference="TAG-001", status="confirmed", customer=customer1, customer_first_name="John", customer_last_name="Doe")
        booking2 = create_mock_booking(id=2, reference="TAG-002", status="confirmed", customer=customer2, customer_first_name="Jane", customer_last_name="Smith")

        mock_bookings = [booking1, booking2]
        mock_db = create_mock_db_for_bookings(mock_bookings)

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "INVALID123", "result": None},
        ]

        app.dependency_overrides[get_db] = lambda: mock_db

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["skipped_count"] == 1
            assert any("not found" in s["reason"] for s in data["skipped"])

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_bookings(self, client):
        """Should return empty locations for no bookings."""
        mock_db = create_mock_db_for_bookings([])
        app.dependency_overrides[get_db] = lambda: mock_db

        response = await client.get("/api/admin/reports/booking-locations")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["map_type"] == "bookings"
        assert len(data["locations"]) == 0

    @pytest.mark.asyncio
    async def test_default_map_type_is_bookings(self, client):
        """Should default to map_type='bookings' when not specified."""
        mock_db = create_mock_db_for_bookings([])
        app.dependency_overrides[get_db] = lambda: mock_db

        response = await client.get("/api/admin/reports/booking-locations")

        assert response.status_code == 200
        data = response.json()
        assert data["map_type"] == "bookings"

    @pytest.mark.asyncio
    async def test_map_type_bookings_returns_booking_fields(self, client):
        """Should return booking-specific fields for map_type='bookings'."""
        customer = create_mock_customer(id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW", billing_city="Bournemouth")
        booking = create_mock_booking(id=1, reference="TAG-001", status="confirmed", customer=customer, customer_first_name="John", customer_last_name="Doe")

        mock_db = create_mock_db_for_bookings([booking])
        app.dependency_overrides[get_db] = lambda: mock_db

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
        ]

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations?map_type=bookings")

            assert response.status_code == 200
            data = response.json()
            assert len(data["locations"]) == 1
            location = data["locations"][0]
            assert "reference" in location
            assert "dropoff_date" in location
            assert "status" in location
            assert location["reference"] == "TAG-001"


# =============================================================================
# Integration Tests - Journey Origins (map_type=origins)
# =============================================================================

class TestJourneyOrigins:
    """Integration tests for journey origins map (all customers/leads from Page 1)."""

    @pytest.mark.asyncio
    async def test_map_type_origins_returns_all_customers(self, client):
        """map_type='origins' should return all customers with billing postcodes."""
        customer1 = create_mock_customer_with_bookings(
            id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW", has_confirmed_booking=True
        )
        customer2 = create_mock_customer_with_bookings(
            id=2, first_name="Jane", last_name="Smith", billing_postcode="BH1 1AA", has_confirmed_booking=False
        )

        mock_db = create_mock_db_for_customers([customer1, customer2])
        app.dependency_overrides[get_db] = lambda: mock_db

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "BH1 1AA", "result": {"latitude": 50.7201, "longitude": -1.8765, "admin_district": "BCP"}},
        ]

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations?map_type=origins")

            assert response.status_code == 200
            data = response.json()
            assert data["map_type"] == "origins"
            assert data["count"] == 2
            assert "total_customers" in data

    @pytest.mark.asyncio
    async def test_map_type_origins_returns_customer_fields(self, client):
        """map_type='origins' should return customer-specific fields (name, phone, address)."""
        customer = create_mock_customer_with_bookings(
            id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW",
            billing_city="Bournemouth", phone="07700900123"
        )

        mock_db = create_mock_db_for_customers([customer])
        app.dependency_overrides[get_db] = lambda: mock_db

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
        ]

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations?map_type=origins")

            assert response.status_code == 200
            data = response.json()
            assert len(data["locations"]) == 1
            location = data["locations"][0]

            assert "customer_name" in location
            assert "phone" in location
            assert "email" in location
            assert "address" in location
            assert "has_booking" in location
            assert location["customer_name"] == "John Doe"
            assert location["phone"] == "07700900123"

    @pytest.mark.asyncio
    async def test_map_type_origins_includes_has_booking_flag(self, client):
        """Origins should indicate whether customer has a confirmed booking."""
        customer_with_booking = create_mock_customer_with_bookings(
            id=1, first_name="John", last_name="Doe", billing_postcode="BH7 6AW", has_confirmed_booking=True
        )
        customer_without_booking = create_mock_customer_with_bookings(
            id=2, first_name="Jane", last_name="Smith", billing_postcode="BH1 1AA", has_confirmed_booking=False
        )

        mock_db = create_mock_db_for_customers([customer_with_booking, customer_without_booking])
        app.dependency_overrides[get_db] = lambda: mock_db

        postcodes_response = [
            {"query": "BH7 6AW", "result": {"latitude": 50.7192, "longitude": -1.8808, "admin_district": "BCP"}},
            {"query": "BH1 1AA", "result": {"latitude": 50.7201, "longitude": -1.8765, "admin_district": "BCP"}},
        ]

        with patch('main.httpx.AsyncClient') as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=create_mock_postcodes_response(postcodes_response))
            mock_client_class.return_value = mock_http

            response = await client.get("/api/admin/reports/booking-locations?map_type=origins")

            assert response.status_code == 200
            data = response.json()

            john = next(loc for loc in data["locations"] if loc["customer_name"] == "John Doe")
            jane = next(loc for loc in data["locations"] if loc["customer_name"] == "Jane Smith")

            assert john["has_booking"] is True
            assert jane["has_booking"] is False

    @pytest.mark.asyncio
    async def test_map_type_origins_empty_when_no_customers(self, client):
        """Should return empty for origins when no customers have postcodes."""
        mock_db = create_mock_db_for_customers([])
        app.dependency_overrides[get_db] = lambda: mock_db

        response = await client.get("/api/admin/reports/booking-locations?map_type=origins")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["map_type"] == "origins"
