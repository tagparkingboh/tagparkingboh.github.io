"""
Tests for the DVLA Vehicle Enquiry Service integration.

Tests both unit tests (with mocked DVLA API) and integration tests
against the DVLA UAT environment.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport, Response

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Unit Tests (validation only - no mocking of external API)
# =============================================================================

class TestVehicleLookupUnit:
    """Unit tests for vehicle lookup input validation."""

    @pytest.mark.asyncio
    async def test_lookup_empty_registration(self, client):
        """Should return error for empty registration."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": ""}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_whitespace_only_registration(self, client):
        """Should return error for whitespace-only registration."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "   "}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_special_chars_only(self, client):
        """Should return error for special characters only."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "!@#$%"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_missing_registration_field(self, client):
        """Should return 422 for missing registration field."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={}
        )

        assert response.status_code == 422


# =============================================================================
# Integration Tests (against DVLA UAT environment)
# =============================================================================

@pytest.mark.integration
class TestVehicleLookupIntegration:
    """Integration tests against DVLA UAT environment.

    These tests hit the real DVLA UAT API with test registrations.
    Run with: pytest -m integration tests/test_dvla.py
    """

    @pytest.mark.asyncio
    async def test_dvla_uat_ford_red(self, client):
        """Test AA19AAA returns Ford Red from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "AA19AAA"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "FORD"
        assert data["colour"] == "RED"

    @pytest.mark.asyncio
    async def test_dvla_uat_audi_white(self, client):
        """Test AA19MOT returns Audi White from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "AA19MOT"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "AUDI"
        assert data["colour"] == "WHITE"

    @pytest.mark.asyncio
    async def test_dvla_uat_skoda_grey(self, client):
        """Test AA19DSL returns Skoda Grey from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "AA19DSL"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "SKODA"
        assert data["colour"] == "GREY"

    @pytest.mark.asyncio
    async def test_dvla_uat_motorcycle(self, client):
        """Test L2WPS returns Kawasaki Black motorcycle from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "L2WPS"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "KAWASAKI"
        assert data["colour"] == "BLACK"

    @pytest.mark.asyncio
    async def test_dvla_uat_not_found(self, client):
        """Test ER19NFD returns not found from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "ER19NFD"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_dvla_uat_bad_request(self, client):
        """Test ER19BAD returns bad request from DVLA UAT."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "ER19BAD"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_dvla_uat_with_spaces(self, client):
        """Test registration with spaces is cleaned and works."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "AA 19 AAA"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["registration"] == "AA19AAA"
        assert data["make"] == "FORD"

    @pytest.mark.asyncio
    async def test_dvla_uat_lowercase(self, client):
        """Test lowercase registration is uppercased and works."""
        response = await client.post(
            "/api/vehicles/lookup",
            json={"registration": "aa19aaa"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["registration"] == "AA19AAA"
