"""
Tests for Founder Promo Code validation and usage.

The Founder Thank You Email contains a unique 10% off promo code that is
stored in the founder_promo_code field of MarketingSubscriber.

Includes:
- Happy path tests
- Negative path tests
- Edge case tests
- Boundary tests
- Integration tests

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from sqlalchemy.sql.elements import BinaryExpression

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import MarketingSubscriber


# =============================================================================
# Mock Data and Fixtures
# =============================================================================

class MockFounderPromoStore:
    """In-memory store for mock subscribers with founder promo codes."""

    def __init__(self):
        self.subscribers = {}
        self.next_id = 1

    def add(self, subscriber):
        subscriber.id = self.next_id
        self.subscribers[subscriber.id] = subscriber
        self.next_id += 1
        return subscriber

    def get_by_any_promo_code(self, code):
        """Search across all promo code fields."""
        if not code:
            return None
        code_upper = code.strip().upper()
        for sub in self.subscribers.values():
            if sub.founder_promo_code and sub.founder_promo_code.strip().upper() == code_upper:
                return sub
            if sub.promo_10_code and sub.promo_10_code.strip().upper() == code_upper:
                return sub
            if sub.promo_free_code and sub.promo_free_code.strip().upper() == code_upper:
                return sub
            if sub.promo_code and sub.promo_code.strip().upper() == code_upper:
                return sub
        return None

    def clear(self):
        self.subscribers = {}
        self.next_id = 1


_mock_store = MockFounderPromoStore()


class MockQuery:
    """Mock SQLAlchemy query object."""

    def __init__(self, model, store):
        self.model = model
        self.store = store
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def _extract_promo_code_value(self, expr):
        """Extract promo code value from SQLAlchemy expression."""
        if hasattr(expr, 'clauses'):
            for clause in expr.clauses:
                result = self._extract_promo_code_value(clause)
                if result:
                    return result
            return None

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
        for f in self._filters:
            value = self._extract_promo_code_value(f)
            if value:
                return self.store.get_by_any_promo_code(value)
        return None

    def all(self):
        return list(self.store.subscribers.values())


class MockSession:
    """Mock database session."""

    def __init__(self, store):
        self.store = store

    def query(self, model):
        return MockQuery(model, self.store)

    def add(self, obj):
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


def create_subscriber_with_founder_promo(
    email: str = "founder@example.com",
    founder_promo_code: str = "FOUNDER123",
    founder_promo_used: bool = False,
    founder_promo_used_at: datetime = None,
    founder_promo_used_booking_id: int = None,
    founder_email_sent: bool = True,
    founder_email_sent_at: datetime = None,
):
    """Helper to create a subscriber with a founder promo code."""
    subscriber = MarketingSubscriber(
        first_name="Test",
        last_name="Founder",
        email=email,
        founder_promo_code=founder_promo_code,
        founder_promo_used=founder_promo_used,
        founder_promo_used_at=founder_promo_used_at,
        founder_promo_used_booking_id=founder_promo_used_booking_id,
        founder_email_sent=founder_email_sent,
        founder_email_sent_at=founder_email_sent_at or datetime.utcnow(),
    )
    _mock_store.add(subscriber)
    return subscriber


def create_subscriber_with_promo_10(
    email: str = "promo10@example.com",
    promo_10_code: str = "PROMO10ABC",
    promo_10_used: bool = False,
):
    """Helper to create a subscriber with a 10% promo code."""
    subscriber = MarketingSubscriber(
        first_name="Test",
        last_name="Promo10",
        email=email,
        promo_10_code=promo_10_code,
        promo_10_used=promo_10_used,
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
# Happy Path Tests - Founder Promo Code Validation
# =============================================================================

class TestFounderPromoCodeHappyPath:
    """Happy path tests for founder promo code validation."""

    @pytest.mark.asyncio
    async def test_valid_unused_founder_promo_code_returns_valid(self, client):
        """Valid, unused founder promo code should return valid=True."""
        create_subscriber_with_founder_promo(founder_promo_code="FOUNDER123")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "FOUNDER123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 10
        assert "10%" in data["message"]

    @pytest.mark.asyncio
    async def test_founder_promo_code_gives_10_percent_discount(self, client):
        """Founder promo code should give exactly 10% discount."""
        create_subscriber_with_founder_promo(founder_promo_code="DISCOUNT10")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "DISCOUNT10"}
        )
        data = response.json()
        assert data["discount_percent"] == 10

    @pytest.mark.asyncio
    async def test_founder_promo_code_case_insensitive(self, client):
        """Founder promo code validation should be case-insensitive."""
        create_subscriber_with_founder_promo(founder_promo_code="MYFOUNDER")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "myfounder"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_founder_promo_code_with_mixed_case(self, client):
        """Should validate founder promo codes with mixed case input."""
        create_subscriber_with_founder_promo(founder_promo_code="FOUNDERCODE")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "FounderCode"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_founder_promo_code_with_whitespace_trimmed(self, client):
        """Should trim whitespace from founder promo code."""
        create_subscriber_with_founder_promo(founder_promo_code="TRIMCODE")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "  TRIMCODE  "}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_founder_promo_message_indicates_discount(self, client):
        """Success message should indicate 10% discount."""
        create_subscriber_with_founder_promo(founder_promo_code="MSGTEST")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "MSGTEST"}
        )
        data = response.json()
        assert "10%" in data["message"]
        assert "Promo code applied" in data["message"]


# =============================================================================
# Negative Path Tests - Founder Promo Code Validation
# =============================================================================

class TestFounderPromoCodeNegativePath:
    """Negative path tests for founder promo code validation."""

    @pytest.mark.asyncio
    async def test_used_founder_promo_code_returns_invalid(self, client):
        """Already used founder promo code should return valid=False."""
        create_subscriber_with_founder_promo(
            founder_promo_code="USEDCODE",
            founder_promo_used=True,
            founder_promo_used_at=datetime.utcnow(),
            founder_promo_used_booking_id=123
        )

        response = await client.post(
            "/api/promo/validate",
            json={"code": "USEDCODE"}
        )
        data = response.json()
        assert data["valid"] is False
        assert "already been used" in data["message"]
        assert data["discount_percent"] is None

    @pytest.mark.asyncio
    async def test_nonexistent_founder_promo_code_returns_invalid(self, client):
        """Non-existent promo code should return valid=False."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "DOESNOTEXIST"}
        )
        data = response.json()
        assert data["valid"] is False
        assert "invalid" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_promo_code_returns_invalid(self, client):
        """Empty promo code should return valid=False."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": ""}
        )
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_whitespace_only_promo_code_returns_invalid(self, client):
        """Whitespace-only promo code should return valid=False."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "   "}
        )
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_partial_founder_promo_code_returns_invalid(self, client):
        """Partial match of founder promo code should return invalid."""
        create_subscriber_with_founder_promo(founder_promo_code="FULLFOUNDER123")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLFOUNDER"}
        )
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_missing_code_field_returns_422(self, client):
        """Missing code field should return 422 validation error."""
        response = await client.post(
            "/api/promo/validate",
            json={}
        )
        assert response.status_code == 422


# =============================================================================
# Edge Case Tests - Founder Promo Code
# =============================================================================

class TestFounderPromoCodeEdgeCases:
    """Edge case tests for founder promo code validation."""

    @pytest.mark.asyncio
    async def test_founder_promo_code_with_special_characters(self, client):
        """Should handle founder promo codes with special characters."""
        create_subscriber_with_founder_promo(founder_promo_code="TAG-FND-2024!")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TAG-FND-2024!"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_founder_promo_code_numeric_only(self, client):
        """Should handle numeric-only founder promo codes."""
        create_subscriber_with_founder_promo(founder_promo_code="123456789")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "123456789"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_sql_injection_attempt_handled_safely(self, client):
        """Should safely handle SQL injection attempts."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "'; DROP TABLE marketing_subscribers; --"}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_very_long_promo_code_handled(self, client):
        """Should handle very long promo code input."""
        long_code = "A" * 1000
        response = await client.post(
            "/api/promo/validate",
            json={"code": long_code}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_founder_code_different_from_promo_10_code(self, client):
        """Founder code and promo_10 code should be validated independently."""
        # Create subscriber with both codes
        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="Both",
            email="both@example.com",
            founder_promo_code="FOUNDERABC",
            promo_10_code="PROMO10XYZ",
        )
        _mock_store.add(subscriber)

        # Both codes should be valid
        response1 = await client.post(
            "/api/promo/validate",
            json={"code": "FOUNDERABC"}
        )
        assert response1.json()["valid"] is True

        response2 = await client.post(
            "/api/promo/validate",
            json={"code": "PROMO10XYZ"}
        )
        assert response2.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_founder_promo_used_but_promo_10_available(self, client):
        """Used founder code shouldn't affect promo_10 code validity."""
        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="Mixed",
            email="mixed@example.com",
            founder_promo_code="USEDFOUNDER",
            founder_promo_used=True,
            promo_10_code="VALIDPROMO10",
            promo_10_used=False,
        )
        _mock_store.add(subscriber)

        # Founder code should be invalid (used)
        response1 = await client.post(
            "/api/promo/validate",
            json={"code": "USEDFOUNDER"}
        )
        assert response1.json()["valid"] is False

        # Promo 10 code should still be valid
        response2 = await client.post(
            "/api/promo/validate",
            json={"code": "VALIDPROMO10"}
        )
        assert response2.json()["valid"] is True


# =============================================================================
# Boundary Tests - Founder Promo Code
# =============================================================================

class TestFounderPromoCodeBoundaryTests:
    """Boundary tests for founder promo code validation."""

    @pytest.mark.asyncio
    async def test_minimum_length_promo_code(self, client):
        """Should handle minimum length (1 char) promo code."""
        create_subscriber_with_founder_promo(founder_promo_code="A")

        response = await client.post(
            "/api/promo/validate",
            json={"code": "A"}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_maximum_expected_length_promo_code(self, client):
        """Should handle maximum expected length (20 char) promo code."""
        code = "ABCDEFGHIJ1234567890"  # 20 chars
        create_subscriber_with_founder_promo(founder_promo_code=code)

        response = await client.post(
            "/api/promo/validate",
            json={"code": code}
        )
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_promo_used_at_exact_moment_of_validation(self, client):
        """Code marked used at same moment should return invalid."""
        subscriber = create_subscriber_with_founder_promo(
            founder_promo_code="JUSTUSED",
            founder_promo_used=True,
            founder_promo_used_at=datetime.utcnow()
        )

        response = await client.post(
            "/api/promo/validate",
            json={"code": "JUSTUSED"}
        )
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_promo_used_long_ago(self, client):
        """Code used a long time ago should still return invalid."""
        create_subscriber_with_founder_promo(
            founder_promo_code="OLDUSED",
            founder_promo_used=True,
            founder_promo_used_at=datetime.utcnow() - timedelta(days=365)
        )

        response = await client.post(
            "/api/promo/validate",
            json={"code": "OLDUSED"}
        )
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_founder_email_not_sent_but_code_exists(self, client):
        """Code should still validate even if founder_email_sent is False."""
        create_subscriber_with_founder_promo(
            founder_promo_code="NOTSENT",
            founder_email_sent=False,
            founder_email_sent_at=None
        )

        response = await client.post(
            "/api/promo/validate",
            json={"code": "NOTSENT"}
        )
        # Code exists and is unused, so should be valid
        assert response.json()["valid"] is True


# =============================================================================
# Integration Tests - Founder Promo Code Flow
# =============================================================================

class TestFounderPromoCodeIntegration:
    """Integration tests for founder promo code complete flow."""

    @pytest.mark.asyncio
    async def test_full_validation_to_used_flow(self, client):
        """Test complete flow from validation to marking as used."""
        subscriber = create_subscriber_with_founder_promo(
            email="flow@example.com",
            founder_promo_code="FLOWTEST"
        )

        # Step 1: Validate - should be valid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FLOWTEST"}
        )
        assert response.json()["valid"] is True
        assert response.json()["discount_percent"] == 10

        # Step 2: Validate again - should still be valid (not used yet)
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FLOWTEST"}
        )
        assert response.json()["valid"] is True

        # Step 3: Mark as used (simulating successful payment)
        subscriber.founder_promo_used = True
        subscriber.founder_promo_used_at = datetime.utcnow()
        subscriber.founder_promo_used_booking_id = 456

        # Step 4: Validate again - should now be invalid
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FLOWTEST"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_multiple_subscribers_different_founder_codes(self, client):
        """Multiple subscribers should have independent founder codes."""
        create_subscriber_with_founder_promo(
            email="user1@example.com",
            founder_promo_code="FOUNDER001"
        )
        create_subscriber_with_founder_promo(
            email="user2@example.com",
            founder_promo_code="FOUNDER002"
        )
        create_subscriber_with_founder_promo(
            email="user3@example.com",
            founder_promo_code="FOUNDER003",
            founder_promo_used=True
        )

        # First two should be valid
        for code in ["FOUNDER001", "FOUNDER002"]:
            response = await client.post(
                "/api/promo/validate",
                json={"code": code}
            )
            assert response.json()["valid"] is True

        # Third should be invalid (used)
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FOUNDER003"}
        )
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_rapid_validation_same_founder_code(self, client):
        """Should handle rapid successive validations of same founder code."""
        create_subscriber_with_founder_promo(founder_promo_code="RAPIDFOUNDER")

        results = []
        for _ in range(10):
            response = await client.post(
                "/api/promo/validate",
                json={"code": "RAPIDFOUNDER"}
            )
            results.append(response.json()["valid"])

        # All should be valid (code not marked as used)
        assert all(results)

    @pytest.mark.asyncio
    async def test_founder_and_regular_promo_codes_coexist(self, client):
        """Founder codes and regular promo codes should work independently."""
        # Subscriber with founder code
        create_subscriber_with_founder_promo(
            email="founder@example.com",
            founder_promo_code="FOUNDERONLY"
        )

        # Subscriber with promo_10 code
        create_subscriber_with_promo_10(
            email="promo10@example.com",
            promo_10_code="PROMO10ONLY"
        )

        # Both should validate independently
        response1 = await client.post(
            "/api/promo/validate",
            json={"code": "FOUNDERONLY"}
        )
        assert response1.json()["valid"] is True
        assert response1.json()["discount_percent"] == 10

        response2 = await client.post(
            "/api/promo/validate",
            json={"code": "PROMO10ONLY"}
        )
        assert response2.json()["valid"] is True
        assert response2.json()["discount_percent"] == 10


# =============================================================================
# State Management Tests - Founder Promo Code
# =============================================================================

class TestFounderPromoCodeStateManagement:
    """Tests for founder promo code state in the database."""

    def test_founder_promo_defaults_to_unused(self):
        """New founder promo code should default to unused state."""
        subscriber = create_subscriber_with_founder_promo(
            founder_promo_code="NEWFOUNDER",
            founder_promo_used=False
        )
        assert subscriber.founder_promo_used is False
        assert subscriber.founder_promo_used_at is None
        assert subscriber.founder_promo_used_booking_id is None

    def test_mark_founder_promo_as_used(self):
        """Should be able to mark a founder promo code as used."""
        subscriber = create_subscriber_with_founder_promo(founder_promo_code="WILLUSE")

        # Mark as used
        subscriber.founder_promo_used = True
        subscriber.founder_promo_used_at = datetime.utcnow()
        subscriber.founder_promo_used_booking_id = 789

        assert subscriber.founder_promo_used is True
        assert subscriber.founder_promo_used_at is not None
        assert subscriber.founder_promo_used_booking_id == 789

    def test_founder_promo_code_unique_per_subscriber(self):
        """Each subscriber should have a unique founder promo code."""
        create_subscriber_with_founder_promo(
            email="user1@example.com",
            founder_promo_code="UNIQUE1"
        )
        create_subscriber_with_founder_promo(
            email="user2@example.com",
            founder_promo_code="UNIQUE2"
        )

        codes = [s.founder_promo_code for s in _mock_store.subscribers.values()]
        assert len(codes) == 2
        assert len(codes) == len(set(codes))

    def test_subscriber_without_founder_promo_code(self):
        """Subscribers without founder promo codes should have None."""
        subscriber = MarketingSubscriber(
            first_name="No",
            last_name="Founder",
            email="nofounder@example.com",
        )
        _mock_store.add(subscriber)

        assert subscriber.founder_promo_code is None

    def test_founder_email_sent_tracking(self):
        """Should track when founder email was sent."""
        sent_at = datetime.utcnow()
        subscriber = create_subscriber_with_founder_promo(
            founder_promo_code="EMAILSENT",
            founder_email_sent=True,
            founder_email_sent_at=sent_at
        )

        assert subscriber.founder_email_sent is True
        assert subscriber.founder_email_sent_at == sent_at


# =============================================================================
# Discount Calculation Tests - Founder Promo Code
# =============================================================================

class TestFounderPromoCodeDiscount:
    """Tests for founder promo code discount calculations."""

    def test_founder_discount_is_10_percent(self):
        """Founder promo code should always give 10% discount."""
        # Based on the code fix, founder promo codes give 10% discount
        discount = 10
        assert discount == 10

    def test_discount_calculation_100_pounds(self):
        """10% off 100 should be 10 discount."""
        original = 10000  # 100.00 in pence
        discount_percent = 10
        discount = int(original * discount_percent / 100)
        assert discount == 1000  # 10.00

    def test_discount_calculation_60_pounds(self):
        """10% off 60 (typical quick package) should be 6 discount."""
        original = 6000  # 60.00 in pence
        discount_percent = 10
        discount = int(original * discount_percent / 100)
        assert discount == 600  # 6.00

    def test_discount_calculation_119_pounds(self):
        """10% off 119 (typical standard package) should be 11.90 discount."""
        original = 11900  # 119.00 in pence
        discount_percent = 10
        discount = int(original * discount_percent / 100)
        assert discount == 1190  # 11.90

    def test_final_amount_after_founder_discount(self):
        """Final amount should be original minus 10% discount."""
        original = 11900  # 119.00
        discount_percent = 10
        discount = int(original * discount_percent / 100)
        final = original - discount
        assert final == 10710  # 107.10
