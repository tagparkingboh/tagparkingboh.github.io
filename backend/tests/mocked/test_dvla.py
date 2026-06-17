"""
Tests for the DVLA Vehicle Enquiry Service integration.

Tests both unit tests (with mocked DVLA API) and integration tests
against the DVLA UAT environment.

Unit tests mock the httpx client to avoid real API calls.
Integration tests require DVLA_API_KEY_TEST in .env file.
"""
import pytest
import pytest_asyncio
import os
from types import SimpleNamespace
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
# Unit Tests (validation only - mocked external API)
# =============================================================================

# Mock settings fixture for unit tests
@pytest.fixture
def mock_settings():
    """Mock settings with fake API key for validation tests."""
    mock = MagicMock()
    mock.dvla_api_key_test = "test_api_key_12345"
    mock.dvla_api_key_prod = ""
    mock.environment = "development"
    return mock


class TestVehicleLookupUnit:
    """Unit tests for vehicle lookup input validation.

    These tests mock the external API to test input validation logic.
    """

    @pytest.mark.asyncio
    async def test_lookup_empty_registration(self, client, mock_settings):
        """Should return error for empty registration."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/vehicles/dvla-lookup",
                json={"registration": ""}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_whitespace_only_registration(self, client, mock_settings):
        """Should return error for whitespace-only registration."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/vehicles/dvla-lookup",
                json={"registration": "   "}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Invalid" in data["error"]

    @pytest.mark.asyncio
    async def test_lookup_special_chars_only(self, client, mock_settings):
        """Should return error for special characters only."""
        with patch('main.get_settings', return_value=mock_settings):
            response = await client.post(
                "/api/vehicles/dvla-lookup",
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
            "/api/vehicles/dvla-lookup",
            json={}
        )

        assert response.status_code == 422


# =============================================================================
# Mocked DVLA UAT Contract Tests (deterministic CI coverage)
# =============================================================================

MOCK_DVLA_UAT_RESPONSES = {
    "AA19AAA": (200, {"make": "FORD", "colour": "RED", "taxStatus": "Taxed", "motStatus": "Valid"}),
    "AA19MOT": (200, {"make": "AUDI", "colour": "WHITE", "taxStatus": "Taxed", "motStatus": "Valid"}),
    "AA19DSL": (200, {"make": "SKODA", "colour": "GREY", "taxStatus": "Taxed", "motStatus": "Valid"}),
    "L2WPS": (200, {"make": "KAWASAKI", "colour": "BLACK", "taxStatus": "Taxed", "motStatus": "No details held by DVLA"}),
    "ER19NFD": (404, {}),
    "ER19BAD": (400, {}),
}


class MockDvlaResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class MockDvlaAsyncClient:
    calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        })
        registration = (json or {}).get("registrationNumber")
        status_code, payload = MOCK_DVLA_UAT_RESPONSES.get(registration, (404, {}))
        return MockDvlaResponse(status_code, payload)


@pytest.fixture
def mocked_dvla_uat(monkeypatch):
    """Patch the DVLA client so UAT contract examples run without an API key."""
    MockDvlaAsyncClient.calls = []
    monkeypatch.setattr(
        "main.get_settings",
        lambda: SimpleNamespace(
            environment="development",
            dvla_api_key_test="mock-dvla-key",
            dvla_api_key_prod="",
        ),
    )
    monkeypatch.setattr("main.httpx.AsyncClient", MockDvlaAsyncClient)
    return MockDvlaAsyncClient


class TestVehicleLookupMockedUat:
    """Mocked copies of the DVLA UAT examples that always run in CI."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("registration", "expected_registration", "expected_make", "expected_colour"),
        [
            ("AA19AAA", "AA19AAA", "FORD", "RED"),
            ("AA19MOT", "AA19MOT", "AUDI", "WHITE"),
            ("AA19DSL", "AA19DSL", "SKODA", "GREY"),
            ("L2WPS", "L2WPS", "KAWASAKI", "BLACK"),
            ("AA 19 AAA", "AA19AAA", "FORD", "RED"),
            ("aa19aaa", "AA19AAA", "FORD", "RED"),
        ],
    )
    async def test_mocked_dvla_uat_success_cases(
        self,
        client,
        mocked_dvla_uat,
        registration,
        expected_registration,
        expected_make,
        expected_colour,
    ):
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": registration},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["registration"] == expected_registration
        assert data["make"] == expected_make
        assert data["colour"] == expected_colour

        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": expected_registration
        }
        assert "uat.driver-vehicle-licensing.api.gov.uk" in mocked_dvla_uat.calls[-1]["url"]
        assert mocked_dvla_uat.calls[-1]["headers"]["x-api-key"] == "mock-dvla-key"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("registration", "expected_registration", "expected_error"),
        [
            ("ER19NFD", "ER19NFD", "not found"),
            ("ER19BAD", "ER19BAD", "Invalid"),
        ],
    )
    async def test_mocked_dvla_uat_error_cases(
        self,
        client,
        mocked_dvla_uat,
        registration,
        expected_registration,
        expected_error,
    ):
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": registration},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["registration"] == expected_registration
        assert expected_error in data["error"]
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": expected_registration
        }


# =============================================================================
# Mocked UAT Example Tests
# =============================================================================

class TestVehicleLookupIntegration:
    """DVLA UAT examples run against a mocked client in tests/mocked."""

    @pytest.mark.asyncio
    async def test_dvla_uat_ford_red(self, client, mocked_dvla_uat):
        """Test AA19AAA returns Ford Red with tax/MOT status."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AA19AAA"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "FORD"
        assert data["colour"] == "RED"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "Valid"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "AA19AAA"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_audi_white(self, client, mocked_dvla_uat):
        """Test AA19MOT returns Audi White with tax/MOT status."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AA19MOT"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "AUDI"
        assert data["colour"] == "WHITE"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "Valid"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "AA19MOT"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_skoda_grey(self, client, mocked_dvla_uat):
        """Test AA19DSL returns Skoda Grey with tax/MOT status."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AA19DSL"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "SKODA"
        assert data["colour"] == "GREY"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "Valid"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "AA19DSL"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_motorcycle(self, client, mocked_dvla_uat):
        """Test L2WPS returns Kawasaki Black motorcycle with tax/MOT status."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "L2WPS"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["make"] == "KAWASAKI"
        assert data["colour"] == "BLACK"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "No details held by DVLA"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "L2WPS"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_not_found(self, client, mocked_dvla_uat):
        """Test ER19NFD returns not found from the mocked UAT contract."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "ER19NFD"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "ER19NFD"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_bad_request(self, client, mocked_dvla_uat):
        """Test ER19BAD returns bad request from the mocked UAT contract."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "ER19BAD"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["error"]
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "ER19BAD"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_with_spaces(self, client, mocked_dvla_uat):
        """Test registration with spaces is cleaned and works."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "AA 19 AAA"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["registration"] == "AA19AAA"
        assert data["make"] == "FORD"
        assert data["colour"] == "RED"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "Valid"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "AA19AAA"
        }

    @pytest.mark.asyncio
    async def test_dvla_uat_lowercase(self, client, mocked_dvla_uat):
        """Test lowercase registration is uppercased and works."""
        response = await client.post(
            "/api/vehicles/dvla-lookup",
            json={"registration": "aa19aaa"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["registration"] == "AA19AAA"
        assert data["make"] == "FORD"
        assert data["colour"] == "RED"
        assert data["tax_status"] == "Taxed"
        assert data["mot_status"] == "Valid"
        assert mocked_dvla_uat.calls[-1]["json"] == {
            "registrationNumber": "AA19AAA"
        }
