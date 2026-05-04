"""DVLA compliance — tax/MOT status persistence and email-trigger mapping.

Three layers covered (HUEB matrix per SPEC.md):
  1. `dvla_compliance` helper — which raw DVLA strings should fire an alert
  2. `/api/vehicles/dvla-lookup` endpoint — `tax_status`/`mot_status` are
     forwarded from DVLA's `taxStatus`/`motStatus`
  3. Vehicle creation paths — POST/PATCH /api/vehicles persists the
     statuses to the DB row, sets `dvla_checked_at`, resets `dvla_retry_count`

Layer 3 hits the staging DB via the conftest override and cleans up after
each test. Skip if DB not available.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport, Response

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from dvla_compliance import (
    is_tax_alertable,
    is_mot_alertable,
    should_alert,
    TAX_ALERT_VALUES,
    MOT_ALERT_VALUES,
    COULD_NOT_VERIFY,
)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_settings():
    """DVLA-key-bearing settings for endpoint tests."""
    mock = MagicMock()
    mock.dvla_api_key_test = "test_api_key"
    mock.dvla_api_key_prod = ""
    mock.environment = "development"
    return mock


def _mock_dvla_response(status_code=200, payload=None):
    """Build a fake httpx Response so main.httpx.AsyncClient can return it."""
    response = MagicMock(spec=Response)
    response.status_code = status_code
    response.json = MagicMock(return_value=payload or {})
    return response


def _patch_httpx(mock_response):
    """Context manager assembling the AsyncClient mock chain."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


# =============================================================================
# Layer 1 — email-trigger mapping (pure helper, no I/O)
# =============================================================================

class TestEmailTriggerMapping:
    """Locked 2026-05-03: which DVLA strings warrant emailing Kristian."""

    # ---------- Happy: safe values do NOT alert ----------

    def test_taxed_does_not_alert(self):
        assert is_tax_alertable("Taxed") is False

    def test_valid_mot_does_not_alert(self):
        assert is_mot_alertable("Valid") is False

    def test_both_safe_does_not_alert(self):
        assert should_alert("Taxed", "Valid") is False

    # ---------- Unhappy: every alert-listed value IS alertable ----------

    @pytest.mark.parametrize("value", ["Untaxed", "SORN", "Not Taxed for on Road Use"])
    def test_each_tax_alert_value_triggers(self, value):
        assert is_tax_alertable(value) is True
        assert should_alert(value, "Valid") is True

    @pytest.mark.parametrize(
        "value", ["Not valid", "No details held by DVLA", "No results returned"]
    )
    def test_each_mot_alert_value_triggers(self, value):
        assert is_mot_alertable(value) is True
        assert should_alert("Taxed", value) is True

    def test_both_bad_alerts(self):
        assert should_alert("Untaxed", "Not valid") is True

    # ---------- Edge: None / "Could not verify" never alert ----------

    def test_none_tax_does_not_alert(self):
        assert is_tax_alertable(None) is False

    def test_none_mot_does_not_alert(self):
        assert is_mot_alertable(None) is False

    def test_could_not_verify_does_not_alert(self):
        # Retry policy handles this case — never email.
        assert is_tax_alertable(COULD_NOT_VERIFY) is False
        assert is_mot_alertable(COULD_NOT_VERIFY) is False
        assert should_alert(COULD_NOT_VERIFY, COULD_NOT_VERIFY) is False

    def test_unknown_string_does_not_alert(self):
        # Anything outside the locked enum is treated as benign — we'd
        # rather miss an alert than spam Kristian on a DVLA spec change.
        assert is_tax_alertable("Some New Status") is False
        assert is_mot_alertable("Brand New Value") is False

    # ---------- Boundary: exact set membership ----------

    def test_tax_alert_set_is_exactly_three_values(self):
        assert TAX_ALERT_VALUES == frozenset({
            "Untaxed", "SORN", "Not Taxed for on Road Use",
        })

    def test_mot_alert_set_is_exactly_three_values(self):
        assert MOT_ALERT_VALUES == frozenset({
            "Not valid", "No details held by DVLA", "No results returned",
        })

    def test_case_sensitive(self):
        # DVLA returns these strings verbatim — guard against accidental
        # case-folding on either side breaking the comparison.
        assert is_tax_alertable("UNTAXED") is False
        assert is_mot_alertable("not valid") is False


# =============================================================================
# Layer 2 — /api/vehicles/dvla-lookup forwards tax_status/mot_status
# =============================================================================

class TestDvlaLookupForwardsCompliance:
    """The endpoint must echo DVLA's taxStatus/motStatus on success."""

    @pytest.mark.asyncio
    async def test_happy_returns_both_statuses(self, client, mock_settings):
        mock_response = _mock_dvla_response(200, {
            "make": "CITROEN",
            "colour": "BLUE",
            "taxStatus": "Taxed",
            "motStatus": "Valid",
        })
        with patch("main.get_settings", return_value=mock_settings):
            with patch("main.httpx.AsyncClient", return_value=_patch_httpx(mock_response)):
                response = await client.post(
                    "/api/vehicles/dvla-lookup",
                    json={"registration": "HT14NAO"},
                )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["tax_status"] == "Taxed"
        assert body["mot_status"] == "Valid"

    @pytest.mark.asyncio
    async def test_unhappy_404_omits_statuses(self, client, mock_settings):
        mock_response = _mock_dvla_response(404, {})
        with patch("main.get_settings", return_value=mock_settings):
            with patch("main.httpx.AsyncClient", return_value=_patch_httpx(mock_response)):
                response = await client.post(
                    "/api/vehicles/dvla-lookup",
                    json={"registration": "ZZ99ZZZ"},
                )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body.get("tax_status") is None
        assert body.get("mot_status") is None

    @pytest.mark.asyncio
    async def test_edge_dvla_omits_status_fields(self, client, mock_settings):
        # Some DVLA records omit motStatus entirely (data quirks).
        mock_response = _mock_dvla_response(200, {
            "make": "FORD",
            "colour": "RED",
            "taxStatus": "Taxed",
            # motStatus deliberately missing
        })
        with patch("main.get_settings", return_value=mock_settings):
            with patch("main.httpx.AsyncClient", return_value=_patch_httpx(mock_response)):
                response = await client.post(
                    "/api/vehicles/dvla-lookup",
                    json={"registration": "AB12CDE"},
                )
        body = response.json()
        assert body["tax_status"] == "Taxed"
        assert body["mot_status"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tax,mot",
        [
            ("Untaxed", "Not valid"),
            ("SORN", "No details held by DVLA"),
            ("Not Taxed for on Road Use", "No results returned"),
        ],
    )
    async def test_boundary_each_alertable_combination_forwards(
        self, client, mock_settings, tax, mot
    ):
        # Boundary: every alert-listed string round-trips through the API.
        mock_response = _mock_dvla_response(200, {
            "make": "ROVER",
            "colour": "BLUE",
            "taxStatus": tax,
            "motStatus": mot,
        })
        with patch("main.get_settings", return_value=mock_settings):
            with patch("main.httpx.AsyncClient", return_value=_patch_httpx(mock_response)):
                response = await client.post(
                    "/api/vehicles/dvla-lookup",
                    json={"registration": "ABC1234"},
                )
        body = response.json()
        assert body["tax_status"] == tax
        assert body["mot_status"] == mot


# =============================================================================
# Layer 3 — vehicle creation persists the statuses to the DB
# =============================================================================

@pytest.fixture
def db_test_customer(db_session):
    """Throwaway customer for vehicle-persistence tests; cleaned up after."""
    from db_models import Customer
    customer = Customer(
        first_name="Test",
        last_name="DvlaCompliance",
        email=f"dvla-compliance-test-{id(db_session)}@example.test",
        phone="07700900099",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    yield customer
    # Cleanup — remove any vehicles tied to this customer first
    from db_models import Vehicle
    db_session.query(Vehicle).filter(Vehicle.customer_id == customer.id).delete()
    db_session.delete(customer)
    db_session.commit()


class TestVehicleCreationPersistsCompliance:
    """POST/PATCH /api/vehicles writes tax/MOT to the row."""

    @pytest.mark.asyncio
    async def test_happy_post_with_statuses_persists(
        self, client, db_test_customer, db_session
    ):
        from db_models import Vehicle
        response = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "HT14NAO",
                "make": "Citroen",
                "colour": "Blue",
                "tax_status": "Taxed",
                "mot_status": "Valid",
            },
        )
        assert response.status_code == 200
        vehicle_id = response.json()["vehicle_id"]
        vehicle = db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        assert vehicle.tax_status == "Taxed"
        assert vehicle.mot_status == "Valid"
        assert vehicle.dvla_checked_at is not None
        assert vehicle.dvla_retry_count == 0

    @pytest.mark.asyncio
    async def test_unhappy_post_without_statuses_leaves_null(
        self, client, db_test_customer, db_session
    ):
        from db_models import Vehicle
        response = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "AB12CDE",
                "make": "Ford",
                "colour": "Red",
            },
        )
        assert response.status_code == 200
        vehicle_id = response.json()["vehicle_id"]
        vehicle = db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        assert vehicle.tax_status is None
        assert vehicle.mot_status is None
        assert vehicle.dvla_checked_at is None

    @pytest.mark.asyncio
    async def test_edge_patch_updates_statuses_and_resets_retry(
        self, client, db_test_customer, db_session
    ):
        from db_models import Vehicle

        # Seed a vehicle with stale "Could not verify" + non-zero retry count
        vehicle = Vehicle(
            customer_id=db_test_customer.id,
            registration="STALE99",
            make="Audi",
            colour="White",
            tax_status=COULD_NOT_VERIFY,
            mot_status=COULD_NOT_VERIFY,
            dvla_retry_count=2,
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        response = await client.patch(
            f"/api/vehicles/{vehicle.id}",
            json={
                "customer_id": db_test_customer.id,
                "registration": "STALE99",
                "make": "Audi",
                "colour": "White",
                "tax_status": "Taxed",
                "mot_status": "Valid",
            },
        )
        assert response.status_code == 200
        db_session.refresh(vehicle)
        assert vehicle.tax_status == "Taxed"
        assert vehicle.mot_status == "Valid"
        assert vehicle.dvla_checked_at is not None
        assert vehicle.dvla_retry_count == 0  # reset

    @pytest.mark.asyncio
    async def test_boundary_repost_existing_reg_updates_statuses(
        self, client, db_test_customer, db_session
    ):
        from db_models import Vehicle

        # First save: no DVLA data
        first = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "REUSE1",
                "make": "Mini",
                "colour": "Green",
            },
        )
        vehicle_id = first.json()["vehicle_id"]

        # Same reg, this time with DVLA data — should update in place
        second = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "REUSE1",
                "make": "Mini",
                "colour": "Green",
                "tax_status": "Untaxed",
                "mot_status": "Not valid",
            },
        )
        assert second.json()["vehicle_id"] == vehicle_id  # same row
        vehicle = db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        assert vehicle.tax_status == "Untaxed"
        assert vehicle.mot_status == "Not valid"
        assert vehicle.dvla_checked_at is not None
