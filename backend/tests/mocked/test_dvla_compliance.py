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
from datetime import datetime, timedelta
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

    @pytest.mark.parametrize("value", ["Not valid", "No results returned"])
    def test_each_mot_alert_value_triggers(self, value):
        assert is_mot_alertable(value) is True
        assert should_alert("Taxed", value) is True

    def test_no_details_held_is_NOT_alertable(self):
        # Locked 2026-05-03 (revised): MOT-exempt cars under 3 years old
        # come back as "No details held by DVLA" — alerting on every nearly-
        # new car was too noisy (real prod fleet had 41/223 in this state).
        assert is_mot_alertable("No details held by DVLA") is False
        assert should_alert("Taxed", "No details held by DVLA") is False

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

    def test_mot_alert_set_is_exactly_two_values(self):
        # "No details held by DVLA" deliberately excluded — see locked rules.
        assert MOT_ALERT_VALUES == frozenset({
            "Not valid", "No results returned",
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
            "taxDueDate": "2026-09-01",
            "motExpiryDate": "2026-09-20",
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
        # Expiry dates round-trip as ISO strings
        assert body["tax_due_date"] == "2026-09-01"
        assert body["mot_expiry_date"] == "2026-09-20"

    @pytest.mark.asyncio
    async def test_edge_motexempt_omits_mot_expiry(self, client, mock_settings):
        # MOT-exempt vehicles under 3 years old: DVLA omits motExpiryDate
        mock_response = _mock_dvla_response(200, {
            "make": "TESLA",
            "colour": "WHITE",
            "taxStatus": "Taxed",
            "motStatus": "No details held by DVLA",
            "taxDueDate": "2027-01-01",
            # motExpiryDate intentionally absent
        })
        with patch("main.get_settings", return_value=mock_settings):
            with patch("main.httpx.AsyncClient", return_value=_patch_httpx(mock_response)):
                response = await client.post(
                    "/api/vehicles/dvla-lookup",
                    json={"registration": "HG24SVV"},
                )
        body = response.json()
        assert body["tax_due_date"] == "2027-01-01"
        assert body["mot_expiry_date"] is None

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
            ("SORN", "No results returned"),
            ("Not Taxed for on Road Use", "Not valid"),
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
        from datetime import date as date_type
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
                "tax_due_date": "2026-09-01",
                "mot_expiry_date": "2026-09-20",
            },
        )
        assert response.status_code == 200
        vehicle_id = response.json()["vehicle_id"]
        vehicle = db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        assert vehicle.tax_status == "Taxed"
        assert vehicle.mot_status == "Valid"
        assert vehicle.tax_due_date == date_type(2026, 9, 1)
        assert vehicle.mot_expiry_date == date_type(2026, 9, 20)
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
        assert vehicle.tax_due_date is None
        assert vehicle.mot_expiry_date is None
        assert vehicle.dvla_checked_at is None

    @pytest.mark.asyncio
    async def test_unhappy_post_with_malformed_date_returns_422(
        self, client, db_test_customer
    ):
        # Pydantic guards the date field — bad strings are rejected at
        # the boundary, never hit the DB.
        response = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "BADDT1",
                "make": "Ford",
                "colour": "Red",
                "tax_due_date": "not-a-date",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_boundary_post_only_tax_due_date_persists(
        self, client, db_test_customer, db_session
    ):
        # Boundary: only one expiry field provided, no statuses. The
        # has_dvla detector still triggers and the timestamp is set.
        from datetime import date as date_type
        from db_models import Vehicle
        response = await client.post(
            "/api/vehicles",
            json={
                "customer_id": db_test_customer.id,
                "registration": "ONLYDT1",
                "make": "Ford",
                "colour": "Red",
                "tax_due_date": "2026-09-01",
            },
        )
        assert response.status_code == 200
        vehicle_id = response.json()["vehicle_id"]
        vehicle = db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        assert vehicle.tax_due_date == date_type(2026, 9, 1)
        assert vehicle.mot_expiry_date is None
        assert vehicle.tax_status is None
        assert vehicle.dvla_checked_at is not None  # has_dvla detected

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


# =============================================================================
# Layer 4 — Phase C: server-side DVLA fetch helper (sync, no DB)
# =============================================================================

def _mock_sync_response(status_code=200, payload=None):
    """Build a fake httpx.Response for the sync httpx.Client."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=payload or {})
    return resp


def _patch_sync_httpx(mock_response=None, raise_exc=None):
    """Context-manager mock for httpx.Client used in dvla_compliance."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=None)
    if raise_exc is not None:
        mock_client.post = MagicMock(side_effect=raise_exc)
    else:
        mock_client.post = MagicMock(return_value=mock_response)
    return mock_client


class TestParseIsoDate:
    """`_parse_iso_date` — coerces DVLA's date strings to date objects.

    DVLA dates are always 'YYYY-MM-DD' on success, but the helper has to
    tolerate None / missing / malformed input so a quirky DVLA response
    doesn't poison the persistence path.
    """

    def test_happy_iso_date(self):
        from datetime import date as date_type
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date("2026-09-01") == date_type(2026, 9, 1)

    def test_unhappy_returns_none_for_garbage(self):
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date("not a date") is None

    def test_edge_none_returns_none(self):
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date(None) is None

    def test_edge_empty_string_returns_none(self):
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date("") is None

    def test_boundary_leap_year_accepted(self):
        from datetime import date as date_type
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date("2028-02-29") == date_type(2028, 2, 29)

    def test_boundary_invalid_leap_day_rejected(self):
        from dvla_compliance import _parse_iso_date
        assert _parse_iso_date("2026-02-29") is None  # 2026 isn't a leap year


class TestFetchDvlaStatus:
    """Sync DVLA HTTP wrapper used by scheduler + at-creation hooks."""

    def test_happy_returns_both_statuses(self):
        from dvla_compliance import fetch_dvla_status
        resp = _mock_sync_response(200, {"taxStatus": "Taxed", "motStatus": "Valid"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            result = fetch_dvla_status("HT14NAO", "fake_key", is_production=False)
        assert result.success is True
        assert result.tax_status == "Taxed"
        assert result.mot_status == "Valid"
        assert result.not_found is False

    def test_unhappy_404_marks_not_found(self):
        from dvla_compliance import fetch_dvla_status
        resp = _mock_sync_response(404, {})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            result = fetch_dvla_status("ZZZ", "fake_key", is_production=False)
        assert result.success is False
        assert result.not_found is True
        assert result.http_status == 404

    def test_edge_500_is_not_found_false(self):
        from dvla_compliance import fetch_dvla_status
        resp = _mock_sync_response(500, {})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            result = fetch_dvla_status("ABC1234", "fake_key", is_production=False)
        assert result.success is False
        assert result.not_found is False
        assert result.http_status == 500

    def test_boundary_timeout_caught(self):
        import httpx
        from dvla_compliance import fetch_dvla_status
        with patch(
            "dvla_compliance.httpx.Client",
            return_value=_patch_sync_httpx(raise_exc=httpx.TimeoutException("timeout")),
        ):
            result = fetch_dvla_status("ABC1234", "fake_key", is_production=False)
        assert result.success is False
        assert result.not_found is False
        assert "timeout" in (result.error or "").lower()

    def test_edge_200_with_missing_status_field(self):
        from dvla_compliance import fetch_dvla_status
        # DVLA omits motStatus on this record (data quirk)
        resp = _mock_sync_response(200, {"taxStatus": "Taxed"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            result = fetch_dvla_status("ABC1234", "fake_key", is_production=False)
        assert result.success is True
        assert result.tax_status == "Taxed"
        assert result.mot_status is None


# =============================================================================
# Layer 5 — Phase C: refresh_vehicle_dvla persists + handles retry/freeze
# =============================================================================

class TestRefreshVehicleDvla:
    """Persistence-side: DB row updated correctly per fetch outcome."""

    def test_happy_success_resets_retry_count(self, db_test_customer, db_session):
        from datetime import date as date_type
        from db_models import Vehicle
        from dvla_compliance import refresh_vehicle_dvla
        vehicle = Vehicle(
            customer_id=db_test_customer.id, registration="HAPPY1",
            make="X", colour="Y", dvla_retry_count=2,
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        resp = _mock_sync_response(200, {
            "taxStatus": "Taxed", "motStatus": "Valid",
            "taxDueDate": "2026-09-01", "motExpiryDate": "2026-09-20",
        })
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            alertable = refresh_vehicle_dvla(
                db_session, vehicle, api_key="k", is_production=False,
            )
        db_session.refresh(vehicle)
        assert alertable is False  # Taxed/Valid → no alert
        assert vehicle.tax_status == "Taxed"
        assert vehicle.mot_status == "Valid"
        # Expiry dates persisted alongside the statuses
        assert vehicle.tax_due_date == date_type(2026, 9, 1)
        assert vehicle.mot_expiry_date == date_type(2026, 9, 20)
        assert vehicle.dvla_checked_at is not None
        assert vehicle.dvla_retry_count == 0

    def test_unhappy_alertable_returns_true(self, db_test_customer, db_session):
        from db_models import Vehicle
        from dvla_compliance import refresh_vehicle_dvla
        vehicle = Vehicle(
            customer_id=db_test_customer.id, registration="ALERT1",
            make="X", colour="Y",
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        resp = _mock_sync_response(200, {"taxStatus": "Untaxed", "motStatus": "Valid"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            alertable = refresh_vehicle_dvla(
                db_session, vehicle, api_key="k", is_production=False,
            )
        db_session.refresh(vehicle)
        assert alertable is True
        assert vehicle.tax_status == "Untaxed"

    def test_edge_timeout_marks_could_not_verify_and_increments_retry(
        self, db_test_customer, db_session
    ):
        import httpx
        from db_models import Vehicle
        from dvla_compliance import refresh_vehicle_dvla, COULD_NOT_VERIFY
        vehicle = Vehicle(
            customer_id=db_test_customer.id, registration="TIMEOUT1",
            make="X", colour="Y", dvla_retry_count=0,
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        with patch(
            "dvla_compliance.httpx.Client",
            return_value=_patch_sync_httpx(raise_exc=httpx.TimeoutException("t")),
        ):
            alertable = refresh_vehicle_dvla(
                db_session, vehicle, api_key="k", is_production=False,
            )
        db_session.refresh(vehicle)
        assert alertable is False  # never alert on Could-not-verify
        assert vehicle.tax_status == COULD_NOT_VERIFY
        assert vehicle.mot_status == COULD_NOT_VERIFY
        assert vehicle.dvla_retry_count == 1

    def test_edge_404_clears_status_and_does_not_increment_retry(
        self, db_test_customer, db_session
    ):
        from datetime import date as date_type
        from db_models import Vehicle
        from dvla_compliance import refresh_vehicle_dvla
        # Seed prior compliance state INCLUDING expiry dates — verify all
        # four DVLA fields get cleared together when DVLA returns 404
        # (re-registration / wrong reg case; old data is now stale).
        vehicle = Vehicle(
            customer_id=db_test_customer.id, registration="NOTFOUND",
            make="X", colour="Y",
            tax_status="Taxed", mot_status="Valid",
            tax_due_date=date_type(2026, 9, 1),
            mot_expiry_date=date_type(2026, 9, 20),
            dvla_retry_count=0,
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        resp = _mock_sync_response(404, {})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            alertable = refresh_vehicle_dvla(
                db_session, vehicle, api_key="k", is_production=False,
            )
        db_session.refresh(vehicle)
        assert alertable is False
        assert vehicle.tax_status is None
        assert vehicle.mot_status is None
        assert vehicle.tax_due_date is None
        assert vehicle.mot_expiry_date is None
        assert vehicle.dvla_retry_count == 0  # NOT incremented (permanent fail)

    def test_boundary_frozen_at_retry_3_skips_dvla(
        self, db_test_customer, db_session
    ):
        from db_models import Vehicle
        from dvla_compliance import refresh_vehicle_dvla, COULD_NOT_VERIFY
        vehicle = Vehicle(
            customer_id=db_test_customer.id, registration="FROZEN",
            make="X", colour="Y",
            tax_status=COULD_NOT_VERIFY, mot_status=COULD_NOT_VERIFY,
            dvla_retry_count=3,
        )
        db_session.add(vehicle)
        db_session.commit()
        db_session.refresh(vehicle)

        # If DVLA were called this would raise — proving the freeze short-circuits
        with patch("dvla_compliance.httpx.Client", side_effect=AssertionError("DVLA called!")):
            alertable = refresh_vehicle_dvla(
                db_session, vehicle, api_key="k", is_production=False,
            )
        assert alertable is False
        db_session.refresh(vehicle)
        assert vehicle.dvla_retry_count == 3  # unchanged


# =============================================================================
# Layer 6 — Phase C: send_vehicle_compliance_alert env guard + dispatch
# =============================================================================

@pytest.fixture
def fake_settings_factory():
    def _make(env="production"):
        s = MagicMock()
        s.environment = env
        return s
    return _make


class TestSendVehicleComplianceAlert:
    """Email guard: staging never reaches Kristian."""

    def test_happy_production_calls_sendgrid(self, fake_settings_factory):
        from email_service import send_vehicle_compliance_alert
        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email", return_value=True) as mock_send:
                ok = send_vehicle_compliance_alert(
                    booking_reference="BR-X",
                    customer_name="Joe Bloggs",
                    registration="HT14NAO",
                    dropoff_date="03/05/2026",
                    dropoff_time="14:00",
                    tax_status="Untaxed",
                    mot_status="Valid",
                )
        assert ok is True
        mock_send.assert_called_once()
        # Subject + recipient sanity
        call_kwargs = mock_send.call_args
        args = call_kwargs.args
        assert args[0] == "kristian@tagparking.co.uk"  # FOUNDER_EMAIL
        assert "BR-X" in args[1]  # subject

    def test_unhappy_staging_blocks_send(self, fake_settings_factory):
        from email_service import send_vehicle_compliance_alert
        with patch("config.get_settings", return_value=fake_settings_factory("staging")):
            with patch("email_service.send_email") as mock_send:
                ok = send_vehicle_compliance_alert(
                    booking_reference="BR-X", customer_name="J B",
                    registration="HT14NAO", dropoff_date="03/05/2026",
                    dropoff_time="14:00",
                    tax_status="Untaxed", mot_status="Valid",
                )
        assert ok is False
        mock_send.assert_not_called()

    def test_edge_development_blocks_send(self, fake_settings_factory):
        from email_service import send_vehicle_compliance_alert
        with patch("config.get_settings", return_value=fake_settings_factory("development")):
            with patch("email_service.send_email") as mock_send:
                ok = send_vehicle_compliance_alert(
                    booking_reference="BR-X", customer_name="J B",
                    registration="X", dropoff_date="01/01/2026", dropoff_time="00:00",
                    tax_status="SORN", mot_status="Not valid",
                )
        assert ok is False
        mock_send.assert_not_called()

    def test_boundary_only_string_production_unlocks(self, fake_settings_factory):
        # "PRODUCTION" upper-case should NOT match — guard is exact equality.
        from email_service import send_vehicle_compliance_alert
        with patch("config.get_settings", return_value=fake_settings_factory("PRODUCTION")):
            with patch("email_service.send_email") as mock_send:
                send_vehicle_compliance_alert(
                    booking_reference="BR-X", customer_name="J B",
                    registration="X", dropoff_date="01/01/2026", dropoff_time="00:00",
                    tax_status="Untaxed", mot_status="Valid",
                )
        mock_send.assert_not_called()


# =============================================================================
# Layer 7 — Phase C: check_and_alert_for_booking dedup + lookup
# =============================================================================

@pytest.fixture
def db_test_booking(db_session, db_test_customer):
    """Throwaway booking + vehicle for compliance hook tests."""
    import pytz
    from db_models import Vehicle, Booking, BookingStatus
    from datetime import time, timedelta

    # Use UK-tz tomorrow (matches the scheduler's "tomorrow" calc, so the
    # date filter aligns even when the machine clock is ahead/behind UK).
    uk_tz = pytz.timezone("Europe/London")
    now_uk = datetime.now(uk_tz)
    dropoff = (now_uk + timedelta(days=1)).date()
    pickup = (now_uk + timedelta(days=8)).date()

    vehicle = Vehicle(
        customer_id=db_test_customer.id, registration="HOOK01",
        make="Test", colour="Black",
        tax_status="Untaxed", mot_status="Valid",  # alertable
    )
    db_session.add(vehicle)
    db_session.flush()
    booking = Booking(
        reference=f"TAG-HOOK-{vehicle.id}",
        customer_id=db_test_customer.id,
        vehicle_id=vehicle.id,
        customer_first_name="Test",
        customer_last_name="Hook",
        dropoff_date=dropoff,
        dropoff_time=time(10, 0),
        pickup_date=pickup,
        pickup_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        booking_source="manual",
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    yield booking
    db_session.delete(booking)
    db_session.commit()


class TestCheckAndAlertForBooking:
    """At-creation hook: alert + dedup logic."""

    def test_happy_alertable_sends_and_marks_dedup(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        from dvla_compliance import check_and_alert_for_booking
        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email", return_value=True) as mock_send:
                sent = check_and_alert_for_booking(db_session, db_test_booking)
        assert sent is True
        assert mock_send.called
        db_session.refresh(db_test_booking)
        assert db_test_booking.last_compliance_alert_sent_at is not None

    def test_unhappy_not_alertable_no_email(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        from dvla_compliance import check_and_alert_for_booking
        db_test_booking.vehicle.tax_status = "Taxed"
        db_test_booking.vehicle.mot_status = "Valid"
        db_session.commit()
        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email") as mock_send:
                sent = check_and_alert_for_booking(db_session, db_test_booking)
        assert sent is False
        mock_send.assert_not_called()

    def test_edge_already_alerted_today_skips(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        import pytz
        from dvla_compliance import check_and_alert_for_booking
        # Mark as already alerted 30 minutes ago
        uk_tz = pytz.timezone("Europe/London")
        db_test_booking.last_compliance_alert_sent_at = datetime.now(uk_tz) - timedelta(minutes=30)
        db_session.commit()

        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email") as mock_send:
                sent = check_and_alert_for_booking(db_session, db_test_booking)
        assert sent is False  # dedup'd
        mock_send.assert_not_called()

    def test_boundary_yesterday_alert_does_not_dedup(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        import pytz
        from dvla_compliance import check_and_alert_for_booking
        uk_tz = pytz.timezone("Europe/London")
        # Yesterday at 23:00 UK
        yesterday = datetime.now(uk_tz) - timedelta(days=1)
        db_test_booking.last_compliance_alert_sent_at = yesterday
        db_session.commit()

        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email", return_value=True) as mock_send:
                sent = check_and_alert_for_booking(db_session, db_test_booking)
        assert sent is True
        assert mock_send.called


# =============================================================================
# Layer 8 — Phase C: process_pending_dvla_rechecks (the daily scheduler job)
# =============================================================================

class TestProcessPendingDvlaRechecks:
    """24h-before scheduler scope + dedup."""

    def test_happy_tomorrow_confirmed_alertable_emails(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        from email_scheduler import process_pending_dvla_rechecks
        # Vehicle dvla_checked_at is None so it'll be refreshed via DVLA
        resp = _mock_sync_response(200, {"taxStatus": "Untaxed", "motStatus": "Valid"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            with patch("config.get_settings", return_value=fake_settings_factory("production")):
                with patch("email_service.send_email", return_value=True) as mock_send:
                    process_pending_dvla_rechecks(db_session)
        assert mock_send.called
        db_session.refresh(db_test_booking)
        assert db_test_booking.last_compliance_alert_sent_at is not None

    def test_unhappy_today_drop_off_not_in_scope(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        import pytz
        from email_scheduler import process_pending_dvla_rechecks
        # Move booking dropoff to today (UK-tz) instead of tomorrow
        uk_tz = pytz.timezone("Europe/London")
        db_test_booking.dropoff_date = datetime.now(uk_tz).date()
        db_session.commit()

        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email") as mock_send:
                with patch("dvla_compliance.httpx.Client") as mock_http:
                    process_pending_dvla_rechecks(db_session)
        mock_send.assert_not_called()
        mock_http.assert_not_called()  # never even reached DVLA

    def test_edge_cancelled_status_skipped(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        from db_models import BookingStatus
        from email_scheduler import process_pending_dvla_rechecks
        db_test_booking.status = BookingStatus.CANCELLED
        db_session.commit()

        with patch("config.get_settings", return_value=fake_settings_factory("production")):
            with patch("email_service.send_email") as mock_send:
                process_pending_dvla_rechecks(db_session)
        mock_send.assert_not_called()

    def test_edge_refunded_status_in_scope(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        from db_models import BookingStatus
        from email_scheduler import process_pending_dvla_rechecks
        db_test_booking.status = BookingStatus.REFUNDED
        db_session.commit()

        resp = _mock_sync_response(200, {"taxStatus": "Untaxed", "motStatus": "Valid"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            with patch("config.get_settings", return_value=fake_settings_factory("production")):
                with patch("email_service.send_email", return_value=True) as mock_send:
                    process_pending_dvla_rechecks(db_session)
        assert mock_send.called  # REFUNDED still gets the alert

    def test_boundary_already_alerted_today_no_second_email(
        self, db_test_booking, db_session, fake_settings_factory
    ):
        import pytz
        from email_scheduler import process_pending_dvla_rechecks
        uk_tz = pytz.timezone("Europe/London")
        db_test_booking.last_compliance_alert_sent_at = datetime.now(uk_tz)
        db_session.commit()

        resp = _mock_sync_response(200, {"taxStatus": "Untaxed", "motStatus": "Valid"})
        with patch("dvla_compliance.httpx.Client", return_value=_patch_sync_httpx(resp)):
            with patch("config.get_settings", return_value=fake_settings_factory("production")):
                with patch("email_service.send_email") as mock_send:
                    process_pending_dvla_rechecks(db_session)
        mock_send.assert_not_called()
