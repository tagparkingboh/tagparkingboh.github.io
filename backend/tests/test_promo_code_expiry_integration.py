"""
Integration tests for Promo Code Expiry functionality.

Tests the full flow including:
- Admin API endpoints for setting/editing expiry
- Promo code list with expiry status
- Full booking flow with expiring promo codes

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
import pytz

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import PromoCode, Promotion, User


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockIntegrationStore:
    """In-memory store for integration tests."""

    def __init__(self):
        self.promo_codes = {}
        self.promotions = {}
        self.users = {}
        self.next_id = 1

    def add_promotion(self, name: str = "Test Promo", discount_percent: int = 10):
        promo = MagicMock(spec=Promotion)
        promo.id = self.next_id
        promo.name = name
        promo.discount_percent = discount_percent
        promo.code_prefix = "TAG"
        promo.total_codes = 0
        promo.codes_sent = 0
        promo.codes_used = 0
        promo.description = None
        promo.created_by = "admin@test.com"
        promo.created_at = datetime.utcnow()
        self.promotions[promo.id] = promo
        self.next_id += 1
        return promo

    def add_promo_code(
        self,
        code: str,
        promotion_id: int,
        is_used: bool = False,
        expires_at: datetime = None,
    ):
        pc = MagicMock(spec=PromoCode)
        pc.id = self.next_id
        pc.code = code
        pc.promotion_id = promotion_id
        pc.is_used = is_used
        pc.used_at = None
        pc.expires_at = expires_at
        pc.email_sent = False
        pc.email_sent_at = None
        pc.recipient_email = None
        pc.recipient_first_name = None
        pc.recipient_last_name = None
        pc.customer_id = None
        pc.subscriber_id = None
        pc.shared_on_socials = False
        pc.shared_on_socials_at = None
        pc.shared_privately = False
        pc.shared_privately_at = None
        pc.booking_id = None
        pc.created_at = datetime.utcnow()
        self.promo_codes[pc.id] = pc
        self.next_id += 1
        return pc

    def add_admin_user(self, email: str = "admin@test.com"):
        user = MagicMock(spec=User)
        user.id = self.next_id
        user.email = email
        user.role = "admin"
        user.is_active = True
        self.users[user.id] = user
        self.next_id += 1
        return user

    def get_promo_code_by_code(self, code: str):
        code_upper = code.strip().upper()
        for pc in self.promo_codes.values():
            if pc.code == code_upper:
                return pc
        return None

    def get_promo_code_by_id(self, id: int):
        return self.promo_codes.get(id)

    def get_promotion_by_id(self, id: int):
        return self.promotions.get(id)

    def clear(self):
        self.promo_codes = {}
        self.promotions = {}
        self.users = {}
        self.next_id = 1


_mock_store = MockIntegrationStore()


class MockQuery:
    def __init__(self, model, store):
        self.model = model
        self.store = store
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def order_by(self, *args):
        return self

    def first(self):
        if self.model == PromoCode or (hasattr(self.model, '__name__') and 'PromoCode' in str(self.model)):
            for f in self._filters:
                if hasattr(f, 'right') and hasattr(f.right, 'value'):
                    value = f.right.value
                    if isinstance(value, str):
                        return self.store.get_promo_code_by_code(value)
                    elif isinstance(value, int):
                        return self.store.get_promo_code_by_id(value)
            return None

        if self.model == Promotion or (hasattr(self.model, '__name__') and 'Promotion' in str(self.model)):
            for f in self._filters:
                if hasattr(f, 'right') and hasattr(f.right, 'value'):
                    value = f.right.value
                    if isinstance(value, int):
                        return self.store.get_promotion_by_id(value)
            return None

        return None

    def all(self):
        if self.model == PromoCode:
            # Filter by promotion_id if present
            for f in self._filters:
                if hasattr(f, 'right') and hasattr(f.right, 'value'):
                    promo_id = f.right.value
                    if isinstance(promo_id, int):
                        return [pc for pc in self.store.promo_codes.values() if pc.promotion_id == promo_id]
            return list(self.store.promo_codes.values())
        if self.model == Promotion:
            return list(self.store.promotions.values())
        return []

    def count(self):
        return len(self.all())


class MockSession:
    def __init__(self, store):
        self.store = store

    def query(self, model):
        return MockQuery(model, self.store)

    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def get_mock_db():
    db = MockSession(_mock_store)
    try:
        yield db
    finally:
        db.close()


def get_uk_now() -> datetime:
    """Get current time in UK timezone - matches main.py implementation."""
    uk_tz = pytz.timezone("Europe/London")
    return datetime.now(uk_tz)


# Mock admin authentication
def mock_require_admin():
    user = MagicMock()
    user.email = "admin@test.com"
    user.role = "admin"
    return user


@pytest.fixture(autouse=True)
def reset_mock_store():
    _mock_store.clear()
    yield
    _mock_store.clear()


@pytest.fixture(autouse=True)
def override_dependencies():
    from main import require_admin
    app.dependency_overrides[get_db] = get_mock_db
    app.dependency_overrides[require_admin] = mock_require_admin
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Integration Tests - Full Booking Flow with Expiring Promo Code
# =============================================================================

class TestBookingFlowWithExpiringPromoCode:
    """Integration tests for booking flow with expiring promo codes."""

    @pytest.mark.asyncio
    async def test_booking_flow_valid_expiring_promo(self, client):
        """Full booking flow with valid (not yet expired) promo code."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        future = get_uk_now() + timedelta(days=1)
        _mock_store.add_promo_code("TAG-BOOK-0001", promotion.id, expires_at=future)

        # Step 1: Validate promo code
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-BOOK-0001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 10

    @pytest.mark.asyncio
    async def test_booking_flow_expired_promo_rejected(self, client):
        """Booking flow should reject expired promo code with clear error."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(hours=1)
        _mock_store.add_promo_code("TAG-EXPB-0002", promotion.id, expires_at=expired)

        # Validate promo code - should fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXPB-0002"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()
        assert data["discount_percent"] is None


# =============================================================================
# Integration Tests - Admin API Set Expiry
# =============================================================================

class TestAdminSetPromoCodeExpiry:
    """Integration tests for admin setting promo code expiry."""

    @pytest.mark.asyncio
    async def test_admin_set_expiry_valid_date_time(self, client):
        """Admin can set expiry with valid DD/MM/YYYY and HH:MM format."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-ADEX-0003", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "25/12/2024",
                "expiry_time": "14:30"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["code"] == "TAG-ADEX-0003"
        assert "expires_at" in data
        assert "25/12/2024" in data["message"]
        assert "14:30" in data["message"]

    @pytest.mark.asyncio
    async def test_admin_remove_expiry(self, client):
        """Admin can remove expiry by setting both to null."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        pc = _mock_store.add_promo_code("TAG-RMEX-0004", promotion.id, expires_at=expired)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": None,
                "expiry_time": None
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["expires_at"] is None
        assert data["is_expired"] is False
        assert "never expire" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_admin_set_expiry_invalid_date_format(self, client):
        """Admin gets error for invalid date format."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-INVD-0005", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "2024-12-25",  # Wrong format (should be DD/MM/YYYY)
                "expiry_time": "14:30"
            }
        )
        assert response.status_code == 400
        assert "DD/MM/YYYY" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_set_expiry_invalid_time_format(self, client):
        """Admin gets error for invalid time format."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-INVT-0006", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "25/12/2024",
                "expiry_time": "2:30pm"  # Wrong format (should be HH:MM)
            }
        )
        assert response.status_code == 400
        assert "HH:MM" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_set_expiry_date_without_time(self, client):
        """Admin gets error when only date is provided without time."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-NOTIME-0007", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "25/12/2024",
                "expiry_time": None
            }
        )
        assert response.status_code == 400
        assert "together" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_set_expiry_time_without_date(self, client):
        """Admin gets error when only time is provided without date."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-NODATE-0008", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": None,
                "expiry_time": "14:30"
            }
        )
        assert response.status_code == 400
        assert "together" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_set_expiry_nonexistent_code(self, client):
        """Admin gets 404 for non-existent promo code."""
        response = await client.patch(
            "/api/admin/promo-codes/99999/expiry",
            json={
                "expiry_date": "25/12/2024",
                "expiry_time": "14:30"
            }
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_set_expiry_past_date_shows_already_expired(self, client):
        """Setting expiry to past date shows 'already expired' message."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-PAST-0009", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "01/01/2020",  # Past date
                "expiry_time": "12:00"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["is_expired"] is True
        assert "already expired" in data["message"].lower()


# =============================================================================
# Integration Tests - Admin Promo Codes List with Expiry
# =============================================================================

class TestAdminPromoCodesListExpiry:
    """Integration tests for promo codes list showing expiry status."""

    @pytest.mark.asyncio
    async def test_promo_codes_list_shows_expires_at(self, client):
        """Promo codes list should include expires_at field."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        uk_tz = pytz.timezone("Europe/London")
        expiry = uk_tz.localize(datetime(2024, 12, 25, 14, 30, 0))
        _mock_store.add_promo_code("TAG-LIST-0010", promotion.id, expires_at=expiry)
        _mock_store.add_promo_code("TAG-LIST-0011", promotion.id, expires_at=None)

        response = await client.get(f"/api/admin/promotions/{promotion.id}")
        assert response.status_code == 200
        data = response.json()

        codes = data["codes"]
        assert len(codes) == 2

        # Find the code with expiry
        code_with_expiry = next(c for c in codes if c["code"] == "TAG-LIST-0010")
        assert code_with_expiry["expires_at"] is not None
        assert "is_expired" in code_with_expiry

        # Find the code without expiry
        code_without_expiry = next(c for c in codes if c["code"] == "TAG-LIST-0011")
        assert code_without_expiry["expires_at"] is None
        assert code_without_expiry["is_expired"] is False

    @pytest.mark.asyncio
    async def test_promo_codes_list_shows_is_expired_flag(self, client):
        """Promo codes list should show is_expired=True for expired codes."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        valid = get_uk_now() + timedelta(days=1)

        _mock_store.add_promo_code("TAG-EXPD-0012", promotion.id, expires_at=expired)
        _mock_store.add_promo_code("TAG-VALD-0013", promotion.id, expires_at=valid)

        response = await client.get(f"/api/admin/promotions/{promotion.id}")
        assert response.status_code == 200
        data = response.json()

        codes = data["codes"]

        expired_code = next(c for c in codes if c["code"] == "TAG-EXPD-0012")
        assert expired_code["is_expired"] is True

        valid_code = next(c for c in codes if c["code"] == "TAG-VALD-0013")
        assert valid_code["is_expired"] is False


# =============================================================================
# Integration Tests - Admin Edit Expired Code Expiry
# =============================================================================

class TestAdminEditExpiredCodeExpiry:
    """Integration tests for admin editing expired promo codes."""

    @pytest.mark.asyncio
    async def test_admin_extend_expired_code_makes_valid(self, client):
        """Admin extending expired code should make it valid again."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        pc = _mock_store.add_promo_code("TAG-REVA-0014", promotion.id, expires_at=expired)

        # First verify code is expired via validation
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-REVA-0014"}
        )
        assert response.json()["valid"] is False
        assert "expired" in response.json()["message"].lower()

        # Admin extends expiry
        future_date = (get_uk_now() + timedelta(days=7))
        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": future_date.strftime("%d/%m/%Y"),
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 200
        assert response.json()["is_expired"] is False

        # Update the mock's expires_at to simulate DB update
        uk_tz = pytz.timezone("Europe/London")
        pc.expires_at = uk_tz.localize(datetime(
            future_date.year, future_date.month, future_date.day, 23, 59, 0
        ))

        # Now validate again - should be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-REVA-0014"}
        )
        assert response.json()["valid"] is True


# =============================================================================
# Integration Tests - Validation Endpoint Returns Expiry Info
# =============================================================================

class TestValidationEndpointExpiryInfo:
    """Tests for validation endpoint returning expiry-related info."""

    @pytest.mark.asyncio
    async def test_validation_expired_code_clear_message(self, client):
        """Validation of expired code should return clear expiry message."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(hours=2)
        _mock_store.add_promo_code("TAG-CLMG-0015", promotion.id, expires_at=expired)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-CLMG-0015"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()
        assert data["discount_percent"] is None


# =============================================================================
# Integration Tests - Multiple Codes with Different Expiry States
# =============================================================================

class TestMultipleCodesExpiryStates:
    """Tests for handling multiple codes with different expiry states."""

    @pytest.mark.asyncio
    async def test_multiple_codes_different_expiry_states(self, client):
        """Test promotion with codes in various expiry states."""
        promotion = _mock_store.add_promotion(discount_percent=15)

        # Create codes with different states
        now = get_uk_now()
        _mock_store.add_promo_code("TAG-MC01-0016", promotion.id, expires_at=None)  # Never expires
        _mock_store.add_promo_code("TAG-MC02-0017", promotion.id, expires_at=now + timedelta(days=7))  # Future
        _mock_store.add_promo_code("TAG-MC03-0018", promotion.id, expires_at=now - timedelta(days=1))  # Expired
        _mock_store.add_promo_code("TAG-MC04-0019", promotion.id, is_used=True, expires_at=now + timedelta(days=7))  # Used

        # Validate each code
        # Code 1: Never expires - should work
        response = await client.post("/api/promo/validate", json={"code": "TAG-MC01-0016"})
        assert response.json()["valid"] is True

        # Code 2: Future expiry - should work
        response = await client.post("/api/promo/validate", json={"code": "TAG-MC02-0017"})
        assert response.json()["valid"] is True

        # Code 3: Expired - should fail
        response = await client.post("/api/promo/validate", json={"code": "TAG-MC03-0018"})
        assert response.json()["valid"] is False
        assert "expired" in response.json()["message"].lower()

        # Code 4: Used - should fail with "used" message
        response = await client.post("/api/promo/validate", json={"code": "TAG-MC04-0019"})
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"].lower()


# =============================================================================
# Integration Tests - Bulk Expiry Update
# =============================================================================

class TestBulkExpiryUpdate:
    """Integration tests for bulk updating promo code expiry."""

    @pytest.mark.asyncio
    async def test_bulk_set_expiry_multiple_codes(self, client):
        """Admin can set expiry for multiple codes at once."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc1 = _mock_store.add_promo_code("TAG-BLK1-0020", promotion.id)
        pc2 = _mock_store.add_promo_code("TAG-BLK2-0021", promotion.id)
        pc3 = _mock_store.add_promo_code("TAG-BLK3-0022", promotion.id)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc1.id, pc2.id, pc3.id],
                "expiry_date": "31/12/2025",
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated_count"] == 3
        assert len(data["codes"]) == 3
        assert "31/12/2025" in data["message"]
        assert "23:59" in data["message"]

    @pytest.mark.asyncio
    async def test_bulk_remove_expiry_multiple_codes(self, client):
        """Admin can remove expiry from multiple codes at once."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        pc1 = _mock_store.add_promo_code("TAG-BRM1-0023", promotion.id, expires_at=expired)
        pc2 = _mock_store.add_promo_code("TAG-BRM2-0024", promotion.id, expires_at=expired)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc1.id, pc2.id],
                "expiry_date": None,
                "expiry_time": None
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated_count"] == 2
        # All codes should have null expires_at
        for code in data["codes"]:
            assert code["expires_at"] is None
            assert code["is_expired"] is False

    @pytest.mark.asyncio
    async def test_bulk_expiry_empty_code_ids(self, client):
        """Bulk expiry with empty code_ids should return error."""
        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [],
                "expiry_date": "31/12/2025",
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 400
        assert "no code ids" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_bulk_expiry_invalid_date_format(self, client):
        """Bulk expiry with invalid date format should return error."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-BINV-0025", promotion.id)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc.id],
                "expiry_date": "2025-12-31",  # Wrong format
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 400
        assert "DD/MM/YYYY" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_bulk_expiry_date_without_time(self, client):
        """Bulk expiry with date but no time should return error."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-BDT1-0026", promotion.id)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc.id],
                "expiry_date": "31/12/2025",
                "expiry_time": None
            }
        )
        assert response.status_code == 400
        assert "together" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_bulk_expiry_nonexistent_code(self, client):
        """Bulk expiry with non-existent code ID should return error."""
        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [99999],
                "expiry_date": "31/12/2025",
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_bulk_expiry_mixed_valid_invalid_codes(self, client):
        """Bulk expiry with some valid and some invalid codes should fail."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-BMIX-0027", promotion.id)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc.id, 99999],  # One valid, one invalid
                "expiry_date": "31/12/2025",
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_expiry_single_code(self, client):
        """Bulk expiry endpoint works for single code too."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-BSNG-0028", promotion.id)

        response = await client.patch(
            "/api/admin/promo-codes/bulk-expiry",
            json={
                "code_ids": [pc.id],
                "expiry_date": "15/06/2025",
                "expiry_time": "12:00"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 1
        assert "1 codes" in data["message"] or "1 code" in data["message"]


# =============================================================================
# Integration Tests - Flash Sale Scenario
# =============================================================================

class TestFlashSaleScenario:
    """Integration tests for flash sale scenarios with short expiry windows."""

    @pytest.mark.asyncio
    async def test_flash_sale_24_hour_window(self, client):
        """Test promo code valid for exactly 24 hours."""
        promotion = _mock_store.add_promotion(discount_percent=50)
        now = get_uk_now()
        expires_24h = now + timedelta(hours=24)
        _mock_store.add_promo_code("TAG-FLASH24", promotion.id, expires_at=expires_24h)

        # Should be valid now
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FLASH24"}
        )
        assert response.json()["valid"] is True
        assert response.json()["discount_percent"] == 50

    @pytest.mark.asyncio
    async def test_flash_sale_1_hour_window(self, client):
        """Test promo code valid for just 1 hour."""
        promotion = _mock_store.add_promotion(discount_percent=75)
        now = get_uk_now()
        expires_1h = now + timedelta(hours=1)
        _mock_store.add_promo_code("TAG-FLASH1H", promotion.id, expires_at=expires_1h)

        # Should be valid now
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FLASH1H"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_flash_sale_expired_1_minute_ago(self, client):
        """Test promo code that just expired (1 minute ago)."""
        promotion = _mock_store.add_promotion(discount_percent=50)
        now = get_uk_now()
        expired_1m = now - timedelta(minutes=1)
        _mock_store.add_promo_code("TAG-FLASHEXP", promotion.id, expires_at=expired_1m)

        # Should be expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FLASHEXP"}
        )
        assert response.json()["valid"] is False
        assert "expired" in response.json()["message"].lower()


# =============================================================================
# Integration Tests - Concurrent Validation and Expiry
# =============================================================================

class TestConcurrentValidationExpiry:
    """Tests for edge cases around concurrent validation and expiry transitions."""

    @pytest.mark.asyncio
    async def test_code_expiring_between_validation_and_use(self, client):
        """
        Test scenario where code expires between validation and actual use.
        This simulates race condition where code is valid at start but expires mid-checkout.
        """
        promotion = _mock_store.add_promotion(discount_percent=20)
        now = get_uk_now()

        # Code expires in 5 seconds
        expires_soon = now + timedelta(seconds=5)
        pc = _mock_store.add_promo_code("TAG-RACE01", promotion.id, expires_at=expires_soon)

        # First validation - should be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-RACE01"}
        )
        assert response.json()["valid"] is True

        # Simulate time passing - code now expired
        pc.expires_at = now - timedelta(seconds=1)

        # Second validation - should be expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-RACE01"}
        )
        assert response.json()["valid"] is False


# =============================================================================
# Unit Tests - Additional Edge Cases for Expiry Parsing
# =============================================================================

class TestExpiryDateParsing:
    """Tests for edge cases in date/time parsing for expiry."""

    @pytest.mark.asyncio
    async def test_set_expiry_midnight(self, client):
        """Setting expiry to midnight (00:00) should work."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-MDNT-0029", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "01/01/2026",
                "expiry_time": "00:00"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_set_expiry_23_59(self, client):
        """Setting expiry to 23:59 (end of day) should work."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-2359-0030", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "31/12/2025",
                "expiry_time": "23:59"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_set_expiry_single_digit_day_month(self, client):
        """Setting expiry with single digit day/month should work (with leading zero)."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-SDIG-0031", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "01/01/2026",
                "expiry_time": "09:05"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_set_expiry_leap_year_feb_29(self, client):
        """Setting expiry on Feb 29 in leap year should work."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-LEAP-0032", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "29/02/2028",  # 2028 is a leap year
                "expiry_time": "12:00"
            }
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_set_expiry_non_leap_year_feb_29_fails(self, client):
        """Setting expiry on Feb 29 in non-leap year should fail."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-NLEP-0033", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "29/02/2025",  # 2025 is not a leap year
                "expiry_time": "12:00"
            }
        )
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_set_expiry_invalid_hour_24(self, client):
        """Setting expiry with hour 24 should fail."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-H24-0034", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "01/01/2026",
                "expiry_time": "24:00"  # Invalid - should be 00:00
            }
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_set_expiry_invalid_minute_60(self, client):
        """Setting expiry with minute 60 should fail."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        pc = _mock_store.add_promo_code("TAG-M60-0035", promotion.id)

        response = await client.patch(
            f"/api/admin/promo-codes/{pc.id}/expiry",
            json={
                "expiry_date": "01/01/2026",
                "expiry_time": "12:60"  # Invalid minute
            }
        )
        assert response.status_code == 400


# =============================================================================
# Integration Tests - Expiry Coexistence with Other States
# =============================================================================

class TestExpiryCoexistenceWithOtherStates:
    """Tests for expiry interacting with other promo code states."""

    @pytest.mark.asyncio
    async def test_shared_on_socials_code_with_expiry(self, client):
        """Code shared on socials with expiry should respect expiry."""
        promotion = _mock_store.add_promotion(discount_percent=15)
        future = get_uk_now() + timedelta(days=1)
        pc = _mock_store.add_promo_code("TAG-SOCS-0036", promotion.id, expires_at=future)
        pc.shared_on_socials = True
        pc.shared_on_socials_at = get_uk_now()

        # Should be valid (not expired, not used)
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-SOCS-0036"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_emailed_code_with_expiry(self, client):
        """Emailed code with expiry should respect expiry."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(hours=1)
        pc = _mock_store.add_promo_code("TAG-EMEX-0037", promotion.id, expires_at=expired)
        pc.email_sent = True
        pc.email_sent_at = get_uk_now() - timedelta(days=2)
        pc.recipient_email = "customer@test.com"

        # Should be expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EMEX-0037"}
        )
        assert response.json()["valid"] is False
        assert "expired" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_privately_shared_code_with_expiry(self, client):
        """Privately shared code with expiry should respect expiry."""
        promotion = _mock_store.add_promotion(discount_percent=20)
        future = get_uk_now() + timedelta(days=7)
        pc = _mock_store.add_promo_code("TAG-PRIV-0038", promotion.id, expires_at=future)
        pc.shared_privately = True
        pc.shared_privately_at = get_uk_now()

        # Should be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-PRIV-0038"}
        )
        assert response.json()["valid"] is True
