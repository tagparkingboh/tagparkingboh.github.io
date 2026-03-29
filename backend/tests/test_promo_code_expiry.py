"""
Tests for Promo Code Expiry functionality.

Includes unit tests for:
- Promo code validation with expiry dates
- Admin API for setting/editing expiry
- Edge cases around expiry boundaries and BST/GMT transitions

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
import pytz

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import PromoCode, Promotion


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockPromoCodeStore:
    """In-memory store for mock promo codes and promotions."""

    def __init__(self):
        self.promo_codes = {}
        self.promotions = {}
        self.next_promo_code_id = 1
        self.next_promotion_id = 1

    def add_promotion(self, name: str = "Test Promo", discount_percent: int = 10):
        """Create a mock promotion."""
        promo = MagicMock(spec=Promotion)
        promo.id = self.next_promotion_id
        promo.name = name
        promo.discount_percent = discount_percent
        promo.code_prefix = "TAG"
        promo.total_codes = 0
        promo.codes_sent = 0
        promo.codes_used = 0
        self.promotions[promo.id] = promo
        self.next_promotion_id += 1
        return promo

    def add_promo_code(
        self,
        code: str,
        promotion_id: int,
        is_used: bool = False,
        expires_at: datetime = None,
    ):
        """Create a mock promo code."""
        pc = MagicMock(spec=PromoCode)
        pc.id = self.next_promo_code_id
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
        pc.shared_privately = False
        pc.booking_id = None
        pc.created_at = datetime.utcnow()
        self.promo_codes[pc.id] = pc
        self.next_promo_code_id += 1
        return pc

    def get_promo_code_by_code(self, code: str):
        """Get promo code by code string."""
        code_upper = code.strip().upper()
        for pc in self.promo_codes.values():
            if pc.code == code_upper:
                return pc
        return None

    def get_promo_code_by_id(self, id: int):
        """Get promo code by ID."""
        return self.promo_codes.get(id)

    def get_promotion_by_id(self, id: int):
        """Get promotion by ID."""
        return self.promotions.get(id)

    def clear(self):
        self.promo_codes = {}
        self.promotions = {}
        self.next_promo_code_id = 1
        self.next_promotion_id = 1


# Global mock store
_mock_store = MockPromoCodeStore()


class MockQuery:
    """Mock SQLAlchemy query object."""

    def __init__(self, model, store):
        self.model = model
        self.store = store
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def first(self):
        # Handle PromoCode queries
        if self.model == PromoCode or (hasattr(self.model, '__name__') and self.model.__name__ == 'PromoCode'):
            for f in self._filters:
                # Check for code filter
                if hasattr(f, 'right') and hasattr(f.right, 'value'):
                    value = f.right.value
                    if isinstance(value, str):
                        return self.store.get_promo_code_by_code(value)
                    elif isinstance(value, int):
                        return self.store.get_promo_code_by_id(value)
            return None

        # Handle Promotion queries
        if self.model == Promotion or (hasattr(self.model, '__name__') and self.model.__name__ == 'Promotion'):
            for f in self._filters:
                if hasattr(f, 'right') and hasattr(f.right, 'value'):
                    value = f.right.value
                    if isinstance(value, int):
                        return self.store.get_promotion_by_id(value)
            return None

        return None

    def all(self):
        if self.model == PromoCode:
            return list(self.store.promo_codes.values())
        if self.model == Promotion:
            return list(self.store.promotions.values())
        return []

    def count(self):
        if self.model == PromoCode:
            return len(self.store.promo_codes)
        if self.model == Promotion:
            return len(self.store.promotions)
        return 0


class MockSession:
    """Mock database session."""

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
    """Override for get_db dependency."""
    db = MockSession(_mock_store)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_mock_store():
    """Reset the mock store before each test."""
    _mock_store.clear()
    yield
    _mock_store.clear()


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Override the database dependency for all tests."""
    app.dependency_overrides[get_db] = get_mock_db
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def get_uk_now() -> datetime:
    """Get current time in UK timezone - matches main.py implementation."""
    uk_tz = pytz.timezone("Europe/London")
    return datetime.now(uk_tz)


# =============================================================================
# Unit Tests - Happy Path
# =============================================================================

class TestPromoCodeExpiryHappyPath:
    """Happy path tests for promo code expiry."""

    @pytest.mark.asyncio
    async def test_validate_code_with_no_expiry(self, client):
        """Valid code with no expiry (NULL) should work - backwards compatible."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        _mock_store.add_promo_code("TAG-NOEXP-1234", promotion.id, expires_at=None)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-NOEXP-1234"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 10

    @pytest.mark.asyncio
    async def test_validate_code_expiring_tomorrow(self, client):
        """Code expiring tomorrow should be valid."""
        promotion = _mock_store.add_promotion(discount_percent=20)
        tomorrow = get_uk_now() + timedelta(days=1)
        _mock_store.add_promo_code("TAG-TOMR-5678", promotion.id, expires_at=tomorrow)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-TOMR-5678"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 20

    @pytest.mark.asyncio
    async def test_validate_code_expiring_in_1_minute(self, client):
        """Code expiring in 1 minute should still be valid."""
        promotion = _mock_store.add_promotion(discount_percent=15)
        in_1_minute = get_uk_now() + timedelta(minutes=1)
        _mock_store.add_promo_code("TAG-1MIN-9999", promotion.id, expires_at=in_1_minute)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-1MIN-9999"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


# =============================================================================
# Unit Tests - Negative Testing
# =============================================================================

class TestPromoCodeExpiryNegative:
    """Negative tests for promo code expiry."""

    @pytest.mark.asyncio
    async def test_validate_expired_code_1_minute_ago(self, client):
        """Code expired 1 minute ago should be rejected."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired_1_min = get_uk_now() - timedelta(minutes=1)
        _mock_store.add_promo_code("TAG-EXP1-0001", promotion.id, expires_at=expired_1_min)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXP1-0001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_expired_code_1_hour_ago(self, client):
        """Code expired 1 hour ago should be rejected."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired_1_hour = get_uk_now() - timedelta(hours=1)
        _mock_store.add_promo_code("TAG-EXP2-0002", promotion.id, expires_at=expired_1_hour)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXP2-0002"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_expired_code_1_day_ago(self, client):
        """Code expired 1 day ago should be rejected."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired_1_day = get_uk_now() - timedelta(days=1)
        _mock_store.add_promo_code("TAG-EXP3-0003", promotion.id, expires_at=expired_1_day)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXP3-0003"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_used_code_even_if_not_expired(self, client):
        """Already used code should be rejected regardless of expiry."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        future = get_uk_now() + timedelta(days=7)
        _mock_store.add_promo_code("TAG-USED-0004", promotion.id, is_used=True, expires_at=future)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-USED-0004"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "already been used" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_used_takes_precedence_over_expired(self, client):
        """Used code message should take precedence over expired message."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        _mock_store.add_promo_code("TAG-BOTH-0005", promotion.id, is_used=True, expires_at=expired)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-BOTH-0005"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        # Used message should come first since it's checked first
        assert "already been used" in data["message"].lower()


# =============================================================================
# Unit Tests - Edge Cases
# =============================================================================

class TestPromoCodeExpiryEdgeCases:
    """Edge case tests for promo code expiry."""

    @pytest.mark.asyncio
    async def test_code_expires_exactly_now(self, client):
        """Code that expires exactly now should be rejected (>= comparison)."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        # Set expiry to "now" - should be considered expired
        now = get_uk_now()
        _mock_store.add_promo_code("TAG-NOW0-0006", promotion.id, expires_at=now)

        # Mock get_uk_now to return the exact same time
        with patch('main.get_uk_now', return_value=now):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "TAG-NOW0-0006"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_code_expires_in_1_second(self, client):
        """Code expiring in 1 second should still be valid."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        in_1_second = get_uk_now() + timedelta(seconds=1)
        _mock_store.add_promo_code("TAG-1SEC-0007", promotion.id, expires_at=in_1_second)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-1SEC-0007"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


# =============================================================================
# Unit Tests - BST/GMT Transitions
# =============================================================================

class TestPromoCodeExpiryTimezoneTransitions:
    """Tests for BST/GMT timezone transitions."""

    @pytest.mark.asyncio
    async def test_bst_to_gmt_clocks_go_back(self, client):
        """
        Test code expiring during BST->GMT transition (last Sunday of October).
        Clocks go back at 2am BST -> 1am GMT, so 1:30am happens twice.
        """
        promotion = _mock_store.add_promotion(discount_percent=10)
        uk_tz = pytz.timezone("Europe/London")

        # Create expiry at 1:30am UK time on the day clocks change (e.g., Oct 27, 2024)
        # This is during the "ambiguous" hour
        expiry = uk_tz.localize(datetime(2024, 10, 27, 1, 30, 0), is_dst=True)  # BST
        _mock_store.add_promo_code("TAG-BSTG-0008", promotion.id, expires_at=expiry)

        # Mock current time to be before expiry (still BST)
        current = uk_tz.localize(datetime(2024, 10, 27, 1, 0, 0), is_dst=True)
        with patch('main.get_uk_now', return_value=current):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "TAG-BSTG-0008"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_gmt_to_bst_clocks_go_forward(self, client):
        """
        Test code expiring during GMT->BST transition (last Sunday of March).
        Clocks go forward at 1am GMT -> 2am BST, so 1:30am doesn't exist.
        """
        promotion = _mock_store.add_promotion(discount_percent=10)
        uk_tz = pytz.timezone("Europe/London")

        # Create expiry at 2:30am UK time on the day clocks change (e.g., Mar 31, 2024)
        # 1:30am doesn't exist, but 2:30am BST does
        expiry = uk_tz.localize(datetime(2024, 3, 31, 2, 30, 0))  # BST
        _mock_store.add_promo_code("TAG-GMTB-0009", promotion.id, expires_at=expiry)

        # Mock current time to be before expiry (12:30am GMT = before transition)
        current = uk_tz.localize(datetime(2024, 3, 31, 0, 30, 0))  # GMT
        with patch('main.get_uk_now', return_value=current):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "TAG-GMTB-0009"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


# =============================================================================
# Unit Tests - Boundary Testing
# =============================================================================

class TestPromoCodeExpiryBoundaries:
    """Boundary tests for promo code expiry."""

    @pytest.mark.asyncio
    async def test_validate_at_23_59_59_expiry_midnight(self, client):
        """Validate at 23:59:59 when expiry is 00:00:00 next day - should work."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        uk_tz = pytz.timezone("Europe/London")

        # Expiry at midnight next day
        expiry = uk_tz.localize(datetime(2024, 6, 15, 0, 0, 0))
        _mock_store.add_promo_code("TAG-2359-0010", promotion.id, expires_at=expiry)

        # Current time at 23:59:59 the day before
        current = uk_tz.localize(datetime(2024, 6, 14, 23, 59, 59))
        with patch('main.get_uk_now', return_value=current):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "TAG-2359-0010"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_at_midnight_expiry_23_59_59_previous_day(self, client):
        """Validate at 00:00:00 when expiry was 23:59:59 previous day - should fail."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        uk_tz = pytz.timezone("Europe/London")

        # Expiry at 23:59:59 previous day
        expiry = uk_tz.localize(datetime(2024, 6, 14, 23, 59, 59))
        _mock_store.add_promo_code("TAG-MDNT-0011", promotion.id, expires_at=expiry)

        # Current time at midnight (00:00:00)
        current = uk_tz.localize(datetime(2024, 6, 15, 0, 0, 0))
        with patch('main.get_uk_now', return_value=current):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "TAG-MDNT-0011"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()


# =============================================================================
# Unit Tests - Admin Edit Expiry
# =============================================================================

class TestPromoCodeAdminEditExpiry:
    """Tests for admin editing promo code expiry."""

    @pytest.mark.asyncio
    async def test_edit_expired_code_to_extend_expiry(self, client):
        """Editing an expired code to extend expiry should make it valid again."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        pc = _mock_store.add_promo_code("TAG-EXTD-0012", promotion.id, expires_at=expired)

        # First verify it's expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXTD-0012"}
        )
        assert response.json()["valid"] is False

        # Now simulate admin extending the expiry
        future = get_uk_now() + timedelta(days=7)
        pc.expires_at = future

        # Should now be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-EXTD-0012"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_edit_valid_code_to_expire_in_past(self, client):
        """Editing a valid code to set expiry in past should make it expired."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        future = get_uk_now() + timedelta(days=7)
        pc = _mock_store.add_promo_code("TAG-PAST-0013", promotion.id, expires_at=future)

        # First verify it's valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-PAST-0013"}
        )
        assert response.json()["valid"] is True

        # Now simulate admin setting expiry to past
        past = get_uk_now() - timedelta(hours=1)
        pc.expires_at = past

        # Should now be expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-PAST-0013"}
        )
        assert response.json()["valid"] is False
        assert "expired" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_edit_code_to_remove_expiry(self, client):
        """Editing code to remove expiry (NULL) should make it permanently valid."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        expired = get_uk_now() - timedelta(days=1)
        pc = _mock_store.add_promo_code("TAG-RMEX-0014", promotion.id, expires_at=expired)

        # First verify it's expired
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-RMEX-0014"}
        )
        assert response.json()["valid"] is False

        # Now simulate admin removing expiry
        pc.expires_at = None

        # Should now be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-RMEX-0014"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_edit_used_code_expiry_still_rejected(self, client):
        """Editing a used code's expiry should be allowed but code still rejected."""
        promotion = _mock_store.add_promotion(discount_percent=10)
        future = get_uk_now() + timedelta(days=7)
        pc = _mock_store.add_promo_code("TAG-USEQ-0015", promotion.id, is_used=True, expires_at=future)

        # Should be rejected because it's used
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-USEQ-0015"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"].lower()

        # Extend expiry
        pc.expires_at = get_uk_now() + timedelta(days=30)

        # Should still be rejected because it's used
        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-USEQ-0015"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"].lower()


# =============================================================================
# Unit Tests - 100% Discount Codes with Expiry
# =============================================================================

class TestPromoCodeExpiry100PercentDiscount:
    """Tests for 100% discount codes with expiry."""

    @pytest.mark.asyncio
    async def test_100_percent_code_valid_not_expired(self, client):
        """100% discount code should work when not expired."""
        promotion = _mock_store.add_promotion(discount_percent=100)
        future = get_uk_now() + timedelta(days=1)
        _mock_store.add_promo_code("TAG-FREE-0016", promotion.id, expires_at=future)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FREE-0016"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 100

    @pytest.mark.asyncio
    async def test_100_percent_code_expired(self, client):
        """100% discount code should be rejected when expired."""
        promotion = _mock_store.add_promotion(discount_percent=100)
        expired = get_uk_now() - timedelta(hours=1)
        _mock_store.add_promo_code("TAG-FREX-0017", promotion.id, expires_at=expired)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FREX-0017"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "expired" in data["message"].lower()
