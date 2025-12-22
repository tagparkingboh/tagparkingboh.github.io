"""
Tests for the OS Places API Address Lookup integration.

Tests both unit tests (with mocked OS Places API) and integration tests
against the real OS Places API.

Unit tests mock the httpx client to avoid real API calls.
Integration tests require OS_PLACES_API_KEY in .env file.
"""
import pytest
import pytest_asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport, Response

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, POST_TOWN_TO_COUNTY


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Unit Tests (validation and county mapping)
# =============================================================================

# Mock settings fixture for unit tests that need API to be "configured"
@pytest.fixture
def mock_settings():
    """Mock settings with fake API key for validation tests."""
    mock = MagicMock()
    mock.os_places_api_key = "test_api_key_12345"
    return mock


class TestAddressLookupUnit:
    """Unit tests for address lookup input validation.

    These tests mock the external API to test input validation logic.
    """

    @pytest.mark.asyncio
    async def test_lookup_empty_postcode(self, client, mock_settings):
        """Should return error for empty postcode."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/address/postcode-lookup",
                json={"postcode": ""}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "postcode" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_lookup_whitespace_only_postcode(self, client, mock_settings):
        """Should return error for whitespace-only postcode."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/address/postcode-lookup",
                json={"postcode": "   "}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "postcode" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_lookup_too_short_postcode(self, client, mock_settings):
        """Should return error for too short postcode."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/address/postcode-lookup",
                json={"postcode": "BH"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_missing_postcode_field(self, client):
        """Should return 422 for missing postcode field."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_lookup_special_chars_postcode(self, client, mock_settings):
        """Should return error for special characters in postcode."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/address/postcode-lookup",
                json={"postcode": "!@#$%^"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            # Will fail validation (too short after removing special chars)
            assert data["error"] is not None


class TestCountyMapping:
    """Tests for post town to county mapping."""

    def test_bournemouth_maps_to_dorset(self):
        """Bournemouth should map to Dorset."""
        assert POST_TOWN_TO_COUNTY.get("BOURNEMOUTH") == "Dorset"

    def test_poole_maps_to_dorset(self):
        """Poole should map to Dorset."""
        assert POST_TOWN_TO_COUNTY.get("POOLE") == "Dorset"

    def test_christchurch_maps_to_dorset(self):
        """Christchurch should map to Dorset."""
        assert POST_TOWN_TO_COUNTY.get("CHRISTCHURCH") == "Dorset"

    def test_southampton_maps_to_hampshire(self):
        """Southampton should map to Hampshire."""
        assert POST_TOWN_TO_COUNTY.get("SOUTHAMPTON") == "Hampshire"

    def test_ringwood_maps_to_hampshire(self):
        """Ringwood should map to Hampshire."""
        assert POST_TOWN_TO_COUNTY.get("RINGWOOD") == "Hampshire"

    def test_london_maps_to_london(self):
        """London should map to London."""
        assert POST_TOWN_TO_COUNTY.get("LONDON") == "London"

    def test_unknown_town_returns_none(self):
        """Unknown towns should return None."""
        assert POST_TOWN_TO_COUNTY.get("UNKNOWN_TOWN") is None

    def test_case_sensitivity(self):
        """Mapping should be uppercase."""
        # Our code uppercases the post town before lookup
        assert POST_TOWN_TO_COUNTY.get("bournemouth") is None
        assert POST_TOWN_TO_COUNTY.get("BOURNEMOUTH") == "Dorset"


# =============================================================================
# Integration Tests (against real OS Places API)
# =============================================================================

@pytest.mark.integration
class TestAddressLookupIntegration:
    """Integration tests against OS Places API.

    These tests hit the real OS Places API with real postcodes.
    Run with: pytest -m integration tests/test_address_lookup.py
    """

    @pytest.mark.asyncio
    async def test_valid_bournemouth_postcode(self, client):
        """Test BH7 6AW returns addresses in Bournemouth."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_results"] > 0
        assert len(data["addresses"]) > 0

        # Check first address has required fields
        first_addr = data["addresses"][0]
        assert first_addr["uprn"]
        assert first_addr["address"]
        assert first_addr["post_town"] == "BOURNEMOUTH"
        assert first_addr["postcode"] == "BH7 6AW"
        assert first_addr["county"] == "Dorset"

    @pytest.mark.asyncio
    async def test_valid_christchurch_postcode(self, client):
        """Test BH23 6AA returns addresses in Christchurch."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH23 6AA"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total_results"] > 0

        first_addr = data["addresses"][0]
        assert first_addr["post_town"] == "CHRISTCHURCH"
        assert first_addr["county"] == "Dorset"

    @pytest.mark.asyncio
    async def test_postcode_with_no_space(self, client):
        """Test postcode without space is cleaned and works."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH76AW"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["postcode"] == "BH7 6AW"  # Should be formatted with space

    @pytest.mark.asyncio
    async def test_postcode_lowercase(self, client):
        """Test lowercase postcode is uppercased and works."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "bh7 6aw"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["postcode"] == "BH7 6AW"

    @pytest.mark.asyncio
    async def test_postcode_extra_spaces(self, client):
        """Test postcode with extra spaces is cleaned."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "  BH7   6AW  "}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["postcode"] == "BH7 6AW"

    @pytest.mark.asyncio
    async def test_address_has_thoroughfare(self, client):
        """Test that addresses include thoroughfare when available."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()

        # Find an address with thoroughfare
        addr_with_thoroughfare = next(
            (a for a in data["addresses"] if a["thoroughfare"]),
            None
        )
        assert addr_with_thoroughfare is not None
        assert "CHRISTCHURCH ROAD" in addr_with_thoroughfare["thoroughfare"]

    @pytest.mark.asyncio
    async def test_address_has_building_number(self, client):
        """Test that addresses include building number when available."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()

        # Find an address with building number
        addr_with_number = next(
            (a for a in data["addresses"] if a["building_number"]),
            None
        )
        assert addr_with_number is not None

    @pytest.mark.asyncio
    async def test_invalid_postcode_format(self, client):
        """Test completely invalid postcode returns error."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "INVALID123"}
        )

        assert response.status_code == 200
        data = response.json()
        # May return success=False or empty results depending on API
        if data["success"]:
            assert data["total_results"] == 0

    @pytest.mark.asyncio
    async def test_nonexistent_postcode(self, client):
        """Test non-existent but valid-format postcode."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "ZZ99 9ZZ"}
        )

        assert response.status_code == 200
        data = response.json()
        # Should return success but with no addresses
        if data["success"]:
            assert data["total_results"] == 0 or len(data["addresses"]) == 0


# =============================================================================
# Mock Tests (for testing error handling)
# =============================================================================

class TestAddressLookupMocked:
    """Tests with mocked OS Places API responses."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with fake API key."""
        mock = MagicMock()
        mock.os_places_api_key = "test_api_key_12345"
        return mock

    @pytest.mark.asyncio
    async def test_api_timeout_handling(self, client, mock_settings):
        """Test graceful handling of API timeout."""
        import httpx

        with patch('main.get_settings', return_value=mock_settings):
            with patch('main.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
                mock_client_class.return_value = mock_client

                response = await client.post(
                    "/api/address/postcode-lookup",
                    json={"postcode": "BH7 6AW"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "timeout" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_api_401_handling(self, client, mock_settings):
        """Test handling of 401 authentication error."""
        with patch('main.get_settings', return_value=mock_settings):
            with patch('main.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_response.text = "Unauthorized"

                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                response = await client.post(
                    "/api/address/postcode-lookup",
                    json={"postcode": "BH7 6AW"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "authentication" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_api_400_handling(self, client, mock_settings):
        """Test handling of 400 bad request error."""
        with patch('main.get_settings', return_value=mock_settings):
            with patch('main.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.text = "Bad Request"

                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                response = await client.post(
                    "/api/address/postcode-lookup",
                    json={"postcode": "BH7 6AW"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "invalid" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_api_500_handling(self, client, mock_settings):
        """Test handling of 500 server error."""
        with patch('main.get_settings', return_value=mock_settings):
            with patch('main.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"

                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                response = await client.post(
                    "/api/address/postcode-lookup",
                    json={"postcode": "BH7 6AW"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "failed" in data["error"].lower()


# =============================================================================
# Response Structure Tests
# =============================================================================

@pytest.mark.integration
class TestAddressResponseStructure:
    """Tests for the structure of address lookup responses."""

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, client):
        """Test response has all required top-level fields."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "success" in data
        assert "postcode" in data
        assert "addresses" in data
        assert "total_results" in data
        assert "error" in data

    @pytest.mark.asyncio
    async def test_address_has_required_fields(self, client):
        """Test each address has all required fields."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["addresses"]) > 0

        required_fields = [
            "uprn", "address", "building_name", "building_number",
            "thoroughfare", "dependent_locality", "post_town",
            "postcode", "county"
        ]

        for addr in data["addresses"]:
            for field in required_fields:
                assert field in addr, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_total_results_matches_addresses(self, client):
        """Test total_results is consistent with addresses array."""
        response = await client.post(
            "/api/address/postcode-lookup",
            json={"postcode": "BH7 6AW"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # total_results should be >= len(addresses) (API may paginate)
        assert data["total_results"] >= len(data["addresses"])
