"""
Tests for the Promo Code API endpoint and functionality.

Includes unit tests for:
- POST /api/promo/validate
- Promo code state management
- Discount calculations

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime
from sqlalchemy.sql.elements import BinaryExpression
from functools import lru_cache

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, PROMO_DISCOUNT_PERCENT
from database import get_db
from db_models import MarketingSubscriber


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockPromoStore:
    """In-memory store for mock subscribers with promo codes."""

    def __init__(self):
        self.subscribers = {}
        self.next_id = 1

    def add(self, subscriber):
        subscriber.id = self.next_id
        self.subscribers[subscriber.id] = subscriber
        self.next_id += 1
        return subscriber

    def get_by_promo_code(self, code):
        if not code:
            return None
        code_upper = code.strip().upper()
        for sub in self.subscribers.values():
            if sub.promo_code and sub.promo_code.strip().upper() == code_upper:
                return sub
        return None

    def get_by_id(self, id):
        return self.subscribers.get(id)

    def clear(self):
        self.subscribers = {}
        self.next_id = 1


# Global mock store
_mock_store = MockPromoStore()


class MockQuery:
    """Mock SQLAlchemy query object for promo codes."""

    def __init__(self, model, store):
        self.model = model
        self.store = store
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def _extract_promo_code_value(self, expr):
        """Recursively extract promo code value from SQLAlchemy expression."""
        # Handle OR expressions (BooleanClauseList)
        if hasattr(expr, 'clauses'):
            for clause in expr.clauses:
                result = self._extract_promo_code_value(clause)
                if result:
                    return result
            return None

        # Handle binary expressions (column == value)
        if isinstance(expr, BinaryExpression):
            try:
                col_name = expr.left.key if hasattr(expr.left, 'key') else str(expr.left)
                if hasattr(expr.right, 'value'):
                    value = expr.right.value
                elif hasattr(expr.right, 'effective_value'):
                    value = expr.right.effective_value
                else:
                    value = str(expr.right)

                if 'promo' in col_name.lower() and 'code' in col_name.lower():
                    return value
            except Exception:
                pass
        return None

    def first(self):
        # Try to extract promo code from filter expressions
        for f in self._filters:
            value = self._extract_promo_code_value(f)
            if value:
                return self.store.get_by_promo_code(value)
        return None

    def all(self):
        return list(self.store.subscribers.values())

    def count(self):
        return len(self.store.subscribers)


class MockSession:
    """Mock database session for promo code tests."""

    def __init__(self, store):
        self.store = store
        self._added = []

    def query(self, model):
        return MockQuery(model, self.store)

    def add(self, obj):
        self._added.append(obj)
        if isinstance(obj, MarketingSubscriber):
            self.store.add(obj)

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


def create_subscriber_with_promo(
    email: str = "test@example.com",
    promo_code: str = "TESTCODE",
    promo_code_used: bool = False,
):
    """Helper to create a subscriber with a promo code."""
    subscriber = MarketingSubscriber(
        first_name="Test",
        last_name="User",
        email=email,
        promo_code=promo_code,
        promo_code_used=promo_code_used,
    )
    _mock_store.add(subscriber)
    return subscriber


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


# =============================================================================
# Unit Tests - Promo Code Validation Endpoint
# =============================================================================

class TestPromoCodeValidation:
    """Tests for POST /api/promo/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_valid_unused_promo_code(self, client):
        """Should return valid=True for a valid, unused promo code."""
        create_subscriber_with_promo(promo_code="VALID123")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "VALID123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == PROMO_DISCOUNT_PERCENT
        assert "10%" in data["message"]

    @pytest.mark.asyncio
    async def test_validate_invalid_promo_code(self, client):
        """Should return valid=False for a non-existent promo code."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "DOESNOTEXIST"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "Invalid" in data["message"]
        assert data["discount_percent"] is None

    @pytest.mark.asyncio
    async def test_validate_used_promo_code(self, client):
        """Should return valid=False for an already used promo code."""
        create_subscriber_with_promo(promo_code="USEDCODE", promo_code_used=True)

        response = await client.post(
            "/api/promo/validate",
            json={"code": "USEDCODE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "already been used" in data["message"]
        assert data["discount_percent"] is None

    @pytest.mark.asyncio
    async def test_validate_promo_code_case_insensitive(self, client):
        """Should validate promo codes case-insensitively."""
        create_subscriber_with_promo(promo_code="MYCODE")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "mycode"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_mixed_case(self, client):
        """Should validate promo codes with mixed case input."""
        create_subscriber_with_promo(promo_code="PROMOCODE")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "PromoCode"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_with_whitespace(self, client):
        """Should trim whitespace from promo code."""
        create_subscriber_with_promo(promo_code="TRIMME")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "  TRIMME  "}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_empty_promo_code(self, client):
        """Should return invalid for empty promo code."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": ""}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_whitespace_only_promo_code(self, client):
        """Should return invalid for whitespace-only promo code."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "   "}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_partial_promo_code(self, client):
        """Should return invalid for partial match of promo code."""
        create_subscriber_with_promo(promo_code="FULLCODE123")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLCODE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_missing_code_field(self, client):
        """Should return 422 for missing code field."""
        response = await client.post(
            "/api/promo/validate",
            json={}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_promo_code_special_characters(self, client):
        """Should handle promo codes with special characters."""
        create_subscriber_with_promo(promo_code="TAG-2024!")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-2024!"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_numeric(self, client):
        """Should handle numeric-only promo codes."""
        create_subscriber_with_promo(promo_code="123456")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "123456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


# =============================================================================
# Unit Tests - Promo Code State Management
# =============================================================================

class TestPromoCodeStateManagement:
    """Tests for promo code state in the database."""

    def test_promo_code_defaults_to_unused(self):
        """New promo codes should default to unused state."""
        subscriber = create_subscriber_with_promo(promo_code="NEWCODE")
        assert subscriber.promo_code_used is False
        assert subscriber.promo_code_used_at is None
        assert subscriber.promo_code_used_booking_id is None

    def test_mark_promo_code_as_used(self):
        """Should be able to mark a promo code as used."""
        subscriber = create_subscriber_with_promo(promo_code="WILLUSE")

        # Mark as used
        subscriber.promo_code_used = True
        subscriber.promo_code_used_at = datetime.utcnow()
        subscriber.promo_code_used_booking_id = 123

        assert subscriber.promo_code_used is True
        assert subscriber.promo_code_used_at is not None
        assert subscriber.promo_code_used_booking_id == 123

    def test_promo_code_unique_per_subscriber(self):
        """Each subscriber should have a unique promo code."""
        create_subscriber_with_promo(email="user1@example.com", promo_code="UNIQUE1")
        create_subscriber_with_promo(email="user2@example.com", promo_code="UNIQUE2")

        promo_codes = [s.promo_code for s in _mock_store.subscribers.values()]
        assert len(promo_codes) == 2
        assert len(promo_codes) == len(set(promo_codes))

    def test_subscriber_without_promo_code(self):
        """Subscribers without promo codes should have None."""
        subscriber = MarketingSubscriber(
            first_name="No",
            last_name="Promo",
            email="nopromo@example.com",
        )
        _mock_store.add(subscriber)

        assert subscriber.promo_code is None


# =============================================================================
# Unit Tests - Multiple Promo Codes
# =============================================================================

class TestMultiplePromoCodes:
    """Tests for handling multiple promo codes in the system."""

    @pytest.mark.asyncio
    async def test_multiple_valid_codes_different_users(self, client):
        """Should validate correct code from multiple users."""
        create_subscriber_with_promo(email="user1@example.com", promo_code="CODE1")
        create_subscriber_with_promo(email="user2@example.com", promo_code="CODE2")
        create_subscriber_with_promo(email="user3@example.com", promo_code="CODE3")

        for code in ["CODE1", "CODE2", "CODE3"]:
            response = await client.post(
                "/api/promo/validate",
                json={"code": code}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_one_used_others_valid(self, client):
        """Should correctly identify used vs unused codes."""
        create_subscriber_with_promo(email="user1@example.com", promo_code="USED", promo_code_used=True)
        create_subscriber_with_promo(email="user2@example.com", promo_code="VALID1")
        create_subscriber_with_promo(email="user3@example.com", promo_code="VALID2")

        # Used code should be invalid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "USED"}
        )
        assert response.json()["valid"] is False

        # Other codes should be valid
        for code in ["VALID1", "VALID2"]:
            response = await client.post(
                "/api/promo/validate",
                json={"code": code}
            )
            assert response.json()["valid"] is True


# =============================================================================
# Edge Cases and Security Tests
# =============================================================================

class TestPromoCodeEdgeCases:
    """Edge cases and security tests for promo codes."""

    @pytest.mark.asyncio
    async def test_sql_injection_attempt(self, client):
        """Should safely handle SQL injection attempts."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "'; DROP TABLE marketing_subscribers; --"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_very_long_promo_code(self, client):
        """Should handle very long promo code input."""
        long_code = "A" * 1000
        response = await client.post(
            "/api/promo/validate",
            json={"code": long_code}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_unicode_promo_code(self, client):
        """Should handle unicode characters in promo code."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "CODIGO"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False


# =============================================================================
# Discount Calculation Tests
# =============================================================================

class TestPromoCodeDiscount:
    """Tests for promo code discount calculations."""

    def test_discount_percent_constant(self):
        """Verify the discount percent constant is set correctly."""
        assert PROMO_DISCOUNT_PERCENT == 10

    def test_discount_calculation_100_pounds(self):
        """10% off 100 should be 10 discount."""
        original = 10000  # 100.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1000  # 10.00

    def test_discount_calculation_99_pounds(self):
        """10% off 99 should be 9.90 discount."""
        original = 9900  # 99.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 990  # 9.90

    def test_discount_calculation_119_pounds(self):
        """10% off 119 should be 11.90 discount."""
        original = 11900  # 119.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1190  # 11.90

    def test_discount_calculation_odd_amount(self):
        """10% off 123.45 should be 12.34 discount (truncated)."""
        original = 12345  # 123.45 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1234  # 12.34 (truncated from 1234.5)

    def test_final_amount_after_discount(self):
        """Final amount should be original minus discount."""
        original = 11900  # 119.00
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        final = original - discount
        assert final == 10710  # 107.10


# =============================================================================
# Concurrent Validation Tests
# =============================================================================

class TestPromoCodeConcurrency:
    """Tests for concurrent promo code validation."""

    @pytest.mark.asyncio
    async def test_rapid_validation_same_code(self, client):
        """Should handle rapid successive validations of same code."""
        create_subscriber_with_promo(promo_code="RAPIDTEST")

        results = []
        for _ in range(10):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "RAPIDTEST"}
            )
            results.append(response.json()["valid"])

        # All should be valid (code not marked as used yet)
        assert all(results)

    @pytest.mark.asyncio
    async def test_validation_after_marking_used(self, client):
        """Should return invalid immediately after code is marked used."""
        subscriber = create_subscriber_with_promo(promo_code="WILLBEUSED")

        # First validation should succeed
        response = await client.post(
            "/api/promo/validate",
            json={"code": "WILLBEUSED"}
        )
        assert response.json()["valid"] is True

        # Mark as used
        subscriber.promo_code_used = True

        # Second validation should fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "WILLBEUSED"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]


# =============================================================================
# End-to-End Flow Tests (Mocked)
# =============================================================================

class TestPromoCodeEndToEndFlow:
    """End-to-end flow tests for promo code usage."""

    @pytest.mark.asyncio
    async def test_promo_code_reuse_attempt_blocked(self, client):
        """Test that a used promo code cannot be reused."""
        # Create and immediately mark as used
        subscriber = create_subscriber_with_promo(promo_code="ALREADYUSED")
        subscriber.promo_code_used = True
        subscriber.promo_code_used_at = datetime.utcnow()
        subscriber.promo_code_used_booking_id = 999

        # Attempt to validate - should fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "ALREADYUSED"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_full_promo_code_validation_flow(self, client):
        """Test complete validation flow."""
        # Step 1: Create a promo code
        subscriber = create_subscriber_with_promo(email="flow@example.com", promo_code="FULLFLOW")

        # Step 2: Validate the promo code
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLFLOW"}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True
        assert response.json()["discount_percent"] == 10

        # Step 3: Code should still be usable (not used yet)
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLFLOW"}
        )
        assert response.json()["valid"] is True

        # Step 4: Mark code as used
        subscriber.promo_code_used = True
        subscriber.promo_code_used_at = datetime.utcnow()

        # Step 5: Validation should now fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLFLOW"}
        )
        assert response.json()["valid"] is False
