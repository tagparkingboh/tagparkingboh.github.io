"""
Tests for the Promo Code API endpoint and functionality.

Includes both unit tests and integration tests for:
- POST /api/promo/validate
- Promo code discount application in payment intent
- Promo code marking as used after payment
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, PROMO_DISCOUNT_PERCENT
from database import Base, get_db
from db_models import MarketingSubscriber, Booking


# =============================================================================
# Test Database Setup
# =============================================================================

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_promo_code.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def create_subscriber_with_promo(
    db,
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
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return subscriber


# =============================================================================
# Unit Tests - Promo Code Validation Endpoint
# =============================================================================

class TestPromoCodeValidation:
    """Tests for POST /api/promo/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_valid_unused_promo_code(self, client):
        """Should return valid=True for a valid, unused promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="VALID123")
        finally:
            db.close()

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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(
                db,
                promo_code="USEDCODE",
                promo_code_used=True
            )
        finally:
            db.close()

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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="MYCODE")
        finally:
            db.close()

        # Test lowercase
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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="PROMOCODE")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "PromoCode"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_with_leading_whitespace(self, client):
        """Should trim leading whitespace from promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="TRIMME")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "   TRIMME"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_with_trailing_whitespace(self, client):
        """Should trim trailing whitespace from promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="TRIMME")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "TRIMME   "}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_promo_code_with_surrounding_whitespace(self, client):
        """Should trim whitespace from both ends of promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="TRIMME")
        finally:
            db.close()

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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="FULLCODE123")
        finally:
            db.close()

        # Only first part of code
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLCODE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_promo_code_with_extra_chars(self, client):
        """Should return invalid when extra characters are added."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="CODE")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "CODE123"}
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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="TAG-2024!")
        finally:
            db.close()

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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="123456")
        finally:
            db.close()

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
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(db, promo_code="NEWCODE")
            assert subscriber.promo_code_used is False
            assert subscriber.promo_code_used_at is None
            assert subscriber.promo_code_used_booking_id is None
        finally:
            db.close()

    def test_mark_promo_code_as_used(self):
        """Should be able to mark a promo code as used."""
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(db, promo_code="WILLUSE")

            # Mark as used
            subscriber.promo_code_used = True
            subscriber.promo_code_used_at = datetime.utcnow()
            subscriber.promo_code_used_booking_id = 123
            db.commit()
            db.refresh(subscriber)

            assert subscriber.promo_code_used is True
            assert subscriber.promo_code_used_at is not None
            assert subscriber.promo_code_used_booking_id == 123
        finally:
            db.close()

    def test_promo_code_unique_per_subscriber(self):
        """Each subscriber should have a unique promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(
                db, email="user1@example.com", promo_code="UNIQUE1"
            )
            create_subscriber_with_promo(
                db, email="user2@example.com", promo_code="UNIQUE2"
            )

            subscribers = db.query(MarketingSubscriber).all()
            promo_codes = [s.promo_code for s in subscribers]
            assert len(promo_codes) == len(set(promo_codes))
        finally:
            db.close()

    def test_subscriber_without_promo_code(self):
        """Subscribers without promo codes should have None."""
        db = TestingSessionLocal()
        try:
            subscriber = MarketingSubscriber(
                first_name="No",
                last_name="Promo",
                email="nopromo@example.com",
            )
            db.add(subscriber)
            db.commit()
            db.refresh(subscriber)

            assert subscriber.promo_code is None
        finally:
            db.close()


# =============================================================================
# Integration Tests - Multiple Promo Codes
# =============================================================================

class TestMultiplePromoCodes:
    """Tests for handling multiple promo codes in the system."""

    @pytest.mark.asyncio
    async def test_multiple_valid_codes_different_users(self, client):
        """Should validate correct code from multiple users."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(
                db, email="user1@example.com", promo_code="CODE1"
            )
            create_subscriber_with_promo(
                db, email="user2@example.com", promo_code="CODE2"
            )
            create_subscriber_with_promo(
                db, email="user3@example.com", promo_code="CODE3"
            )
        finally:
            db.close()

        # Validate each code
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
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(
                db, email="user1@example.com", promo_code="USED", promo_code_used=True
            )
            create_subscriber_with_promo(
                db, email="user2@example.com", promo_code="VALID1"
            )
            create_subscriber_with_promo(
                db, email="user3@example.com", promo_code="VALID2"
            )
        finally:
            db.close()

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
            json={"code": "CÓDIGO🎉"}
        )
        assert response.status_code == 200
        # Should be invalid (no such code exists)
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_newline_in_promo_code(self, client):
        """Should handle newline characters in promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="VALIDCODE")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "VALID\nCODE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_tab_in_promo_code(self, client):
        """Should handle tab characters in promo code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="VALIDCODE")
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "VALID\tCODE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_null_byte_in_promo_code(self, client):
        """Should handle null bytes in promo code."""
        response = await client.post(
            "/api/promo/validate",
            json={"code": "CODE\x00INJECTION"}
        )
        # Should either reject or treat as invalid
        assert response.status_code in [200, 422]
        if response.status_code == 200:
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
        """10% off £100 should be £10 discount."""
        original = 10000  # £100.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1000  # £10.00

    def test_discount_calculation_99_pounds(self):
        """10% off £99 should be £9.90 discount."""
        original = 9900  # £99.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 990  # £9.90

    def test_discount_calculation_119_pounds(self):
        """10% off £119 should be £11.90 discount."""
        original = 11900  # £119.00 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1190  # £11.90

    def test_discount_calculation_odd_amount(self):
        """10% off £123.45 should be £12.34 discount (truncated)."""
        original = 12345  # £123.45 in pence
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        assert discount == 1234  # £12.34 (truncated from 1234.5)

    def test_final_amount_after_discount(self):
        """Final amount should be original minus discount."""
        original = 11900  # £119.00
        discount = int(original * PROMO_DISCOUNT_PERCENT / 100)
        final = original - discount
        assert final == 10710  # £107.10


# =============================================================================
# Concurrent Access Tests
# =============================================================================

class TestPromoCodeConcurrency:
    """Tests for concurrent promo code validation."""

    @pytest.mark.asyncio
    async def test_rapid_validation_same_code(self, client):
        """Should handle rapid successive validations of same code."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="RAPIDTEST")
        finally:
            db.close()

        # Validate same code multiple times rapidly
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
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(db, promo_code="WILLBEUSED")

            # First validation should succeed
            response = await client.post(
                "/api/promo/validate",
                json={"code": "WILLBEUSED"}
            )
            assert response.json()["valid"] is True

            # Mark as used
            subscriber.promo_code_used = True
            db.commit()
        finally:
            db.close()

        # Second validation should fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "WILLBEUSED"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]


# =============================================================================
# Integration Tests - Payment Intent with Promo Code
# =============================================================================

class TestPromoCodePaymentIntegration:
    """Integration tests for promo code with payment intent creation."""

    def _get_payment_request(self, promo_code: str = None):
        """Helper to create a standard payment request."""
        request = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "+441onal234567890",
            "billing_address1": "123 Test Street",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom",
            "registration": "AB12CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "flight_number": "FR5523",
            "flight_date": "2026-02-10",
            "drop_off_date": "2026-02-10",
            "pickup_date": "2026-02-17",
        }
        if promo_code:
            request["promo_code"] = promo_code
        return request

    @pytest.mark.asyncio
    async def test_payment_intent_without_promo_code(self, client):
        """Payment without promo code should charge full price."""
        # Note: 2026-02-10 is 14+ days away = early bird pricing (£99)
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 9900  # £99.00 (early bird tier)
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent) as mock_create:
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request()
                    )

                    assert response.status_code == 200
                    data = response.json()
                    # No discount applied - full early bird price
                    assert data["amount"] == 9900
                    assert data["amount_display"] == "£99.00"

    @pytest.mark.asyncio
    async def test_payment_intent_with_valid_promo_code(self, client):
        """Payment with valid promo code should apply 10% discount."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="SAVE10")
        finally:
            db.close()

        # 10% off £99 (early bird) = £89.10
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 8910  # £89.10
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent) as mock_create:
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request(promo_code="SAVE10")
                    )

                    assert response.status_code == 200
                    data = response.json()
                    # 10% discount applied to early bird price
                    assert data["amount"] == 8910
                    assert data["amount_display"] == "£89.10"

                    # Verify promo code was passed to create_payment_intent
                    call_args = mock_create.call_args
                    assert call_args[0][0].promo_code == "SAVE10"

    @pytest.mark.asyncio
    async def test_payment_intent_with_invalid_promo_code(self, client):
        """Payment with invalid promo code should charge full price."""
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 9900  # Full early bird price
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent):
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request(promo_code="INVALIDCODE")
                    )

                    assert response.status_code == 200
                    data = response.json()
                    # No discount - invalid code ignored
                    assert data["amount"] == 9900

    @pytest.mark.asyncio
    async def test_payment_intent_with_used_promo_code(self, client):
        """Payment with already used promo code should charge full price."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(
                db, promo_code="USEDCODE", promo_code_used=True
            )
        finally:
            db.close()

        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 9900  # Full early bird price
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent):
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request(promo_code="USEDCODE")
                    )

                    assert response.status_code == 200
                    data = response.json()
                    # No discount - code already used
                    assert data["amount"] == 9900

    @pytest.mark.asyncio
    async def test_payment_intent_promo_code_case_insensitive(self, client):
        """Promo code should work regardless of case."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="MYCODE")
        finally:
            db.close()

        # 10% off £99 = £89.10
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 8910  # Discounted
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent) as mock_create:
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    # Use lowercase
                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request(promo_code="mycode")
                    )

                    assert response.status_code == 200
                    # Discount should be applied
                    assert response.json()["amount"] == 8910

    @pytest.mark.asyncio
    async def test_payment_intent_promo_code_whitespace_trimmed(self, client):
        """Promo code with whitespace should be trimmed."""
        db = TestingSessionLocal()
        try:
            create_subscriber_with_promo(db, promo_code="TRIMCODE")
        finally:
            db.close()

        # 10% off £99 = £89.10
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 8910
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent):
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json=self._get_payment_request(promo_code="  TRIMCODE  ")
                    )

                    assert response.status_code == 200
                    assert response.json()["amount"] == 8910


# =============================================================================
# Integration Tests - Webhook Promo Code Marking
# =============================================================================

class TestPromoCodeWebhookIntegration:
    """Integration tests for promo code marking via Stripe webhook."""

    @pytest.mark.asyncio
    async def test_webhook_marks_promo_code_as_used(self, client):
        """Successful payment webhook should mark promo code as used."""
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(db, promo_code="WEBHOOKTEST")
            subscriber_id = subscriber.id

            # Verify not used initially
            assert subscriber.promo_code_used is False
        finally:
            db.close()

        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 10710,
                    "metadata": {
                        "booking_reference": "TAG-WEBHOOK123",
                        "promo_code": "WEBHOOKTEST",
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )

                assert response.status_code == 200

        # Verify promo code was marked as used
        db = TestingSessionLocal()
        try:
            subscriber = db.query(MarketingSubscriber).filter(
                MarketingSubscriber.id == subscriber_id
            ).first()
            assert subscriber.promo_code_used is True
            assert subscriber.promo_code_used_at is not None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_webhook_without_promo_code_metadata(self, client):
        """Webhook without promo code in metadata should not error."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 11900,
                    "metadata": {
                        "booking_reference": "TAG-NOPROMO123",
                        # No promo_code in metadata
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_with_empty_promo_code_metadata(self, client):
        """Webhook with empty promo code should not error."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 11900,
                    "metadata": {
                        "booking_reference": "TAG-EMPTY123",
                        "promo_code": "",  # Empty string
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )

                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_with_nonexistent_promo_code(self, client):
        """Webhook with non-existent promo code should not error."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 11900,
                    "metadata": {
                        "booking_reference": "TAG-NOTFOUND123",
                        "promo_code": "DOESNOTEXIST",
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )

                # Should not fail - just logs error
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_failed_payment_does_not_mark_promo_used(self, client):
        """Failed payment should NOT mark promo code as used."""
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(db, promo_code="FAILEDPAY")
            subscriber_id = subscriber.id
        finally:
            db.close()

        mock_event = {
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "metadata": {
                        "booking_reference": "TAG-FAILED123",
                        "promo_code": "FAILEDPAY",
                    },
                    "last_payment_error": {
                        "message": "Card declined"
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )

                assert response.status_code == 200

        # Verify promo code is still unused
        db = TestingSessionLocal()
        try:
            subscriber = db.query(MarketingSubscriber).filter(
                MarketingSubscriber.id == subscriber_id
            ).first()
            assert subscriber.promo_code_used is False
            assert subscriber.promo_code_used_at is None
        finally:
            db.close()


# =============================================================================
# End-to-End Flow Tests
# =============================================================================

class TestPromoCodeEndToEndFlow:
    """End-to-end flow tests for promo code usage."""

    @pytest.mark.asyncio
    async def test_full_promo_code_flow(self, client):
        """Test complete flow: validate -> payment -> webhook -> code used."""
        # Step 1: Create a promo code
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(
                db, email="flow@example.com", promo_code="FULLFLOW"
            )
            subscriber_id = subscriber.id
        finally:
            db.close()

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

        # Step 4: Simulate successful payment webhook
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_flow_123",
                    "amount": 10710,
                    "metadata": {
                        "booking_reference": "TAG-FLOW123",
                        "promo_code": "FULLFLOW",
                    }
                }
            }
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.verify_webhook_signature', return_value=mock_event):
                response = await client.post(
                    "/api/webhooks/stripe",
                    content=b'{}',
                    headers={"Stripe-Signature": "test_sig"},
                )
                assert response.status_code == 200

        # Step 5: Promo code should now be invalid (used)
        response = await client.post(
            "/api/promo/validate",
            json={"code": "FULLFLOW"}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]

        # Step 6: Verify database state
        db = TestingSessionLocal()
        try:
            subscriber = db.query(MarketingSubscriber).filter(
                MarketingSubscriber.id == subscriber_id
            ).first()
            assert subscriber.promo_code_used is True
            assert subscriber.promo_code_used_at is not None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_promo_code_reuse_attempt_blocked(self, client):
        """Test that a used promo code cannot be reused."""
        # Create and immediately mark as used
        db = TestingSessionLocal()
        try:
            subscriber = create_subscriber_with_promo(
                db, promo_code="ALREADYUSED"
            )
            subscriber.promo_code_used = True
            subscriber.promo_code_used_at = datetime.utcnow()
            subscriber.promo_code_used_booking_id = 999
            db.commit()
        finally:
            db.close()

        # Attempt to validate - should fail
        response = await client.post(
            "/api/promo/validate",
            json={"code": "ALREADYUSED"}
        )
        assert response.json()["valid"] is False
        assert "already been used" in response.json()["message"]

        # Attempt to use in payment - should not apply discount
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret"
        mock_intent.payment_intent_id = "pi_test"
        mock_intent.amount = 9900  # Full early bird price
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.create_payment_intent', return_value=mock_intent):
                with patch('main.get_settings') as mock_settings:
                    mock_settings.return_value.stripe_publishable_key = "pk_test"

                    response = await client.post(
                        "/api/payments/create-intent",
                        json={
                            "first_name": "Test",
                            "last_name": "User",
                            "email": "test@example.com",
                            "package": "quick",
                            "flight_number": "FR123",
                            "flight_date": "2026-02-10",
                            "drop_off_date": "2026-02-10",
                            "pickup_date": "2026-02-17",
                            "promo_code": "ALREADYUSED",
                        }
                    )

                    # Full early bird price charged - no discount
                    assert response.json()["amount"] == 9900
