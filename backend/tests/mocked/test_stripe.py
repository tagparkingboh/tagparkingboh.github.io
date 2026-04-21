"""
Tests for Stripe payment integration.

Note: These tests mock the Stripe API to avoid actual charges.
For integration tests with Stripe's test mode, use the sandbox keys.
"""
import pytest
import pytest_asyncio
import os
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stripe_service import calculate_price_in_pence
from database import get_db
from booking_service import BookingService

# Default pricing configuration for tests
DEFAULT_TEST_PRICING = {
    "days_1_4_price": 60.0,
    "days_5_6_price": 69.0,
    "week1_base_price": 79.0,
    "days_8_9_price": 99.0,
    "days_10_11_price": 119.0,
    "days_12_13_price": 130.0,
    "week2_base_price": 140.0,
    "tier_increment": 10.0,
    "peak_day_increment": 0.0,
    "daily_increment": 8.0,
}


class MockSession:
    """Mock database session that does nothing."""

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def options(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, n):
        return self

    def offset(self, n):
        return self

    def count(self):
        return 0

    def first(self):
        return None

    def all(self):
        return []

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

    def execute(self, *args):
        return MagicMock()


def get_mock_db():
    """Override for get_db dependency."""
    db = MockSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_service():
    """Reset the booking service before each test."""
    import booking_service
    booking_service._booking_service = BookingService()
    yield
    booking_service._booking_service = None


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Override the database dependency for all tests."""
    from main import app
    app.dependency_overrides[get_db] = get_mock_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_pricing():
    """Mock pricing from database for all tests."""
    with patch("booking_service.get_pricing_from_db", return_value=DEFAULT_TEST_PRICING):
        yield


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCalculatePriceInPence:
    """Tests for price calculation."""

    def test_quick_package_early_bird_price(self):
        """Quick package booked 14+ days in advance should be £79.00 = 7900 pence."""
        from datetime import date, timedelta
        early_date = date.today() + timedelta(days=20)
        assert calculate_price_in_pence("quick", drop_off_date=early_date) == 7900

    def test_quick_package_standard_price(self):
        """Quick package booked 7-13 days in advance should be £89.00 = 8900 pence."""
        from datetime import date, timedelta
        standard_date = date.today() + timedelta(days=10)
        assert calculate_price_in_pence("quick", drop_off_date=standard_date) == 8900

    def test_quick_package_late_price(self):
        """Quick package booked <7 days in advance should be £99.00 = 9900 pence."""
        from datetime import date, timedelta
        late_date = date.today() + timedelta(days=3)
        assert calculate_price_in_pence("quick", drop_off_date=late_date) == 9900

    def test_longer_package_early_bird_price(self):
        """Longer package booked 14+ days in advance should be £140.00 = 14000 pence."""
        from datetime import date, timedelta
        early_date = date.today() + timedelta(days=20)
        assert calculate_price_in_pence("longer", drop_off_date=early_date) == 14000

    def test_longer_package_late_price(self):
        """Longer package booked <7 days in advance should be £160.00 = 16000 pence."""
        from datetime import date, timedelta
        late_date = date.today() + timedelta(days=3)
        assert calculate_price_in_pence("longer", drop_off_date=late_date) == 16000

    def test_custom_price_override(self):
        """Custom price should override package price regardless of date."""
        from datetime import date, timedelta
        any_date = date.today() + timedelta(days=5)
        assert calculate_price_in_pence("quick", drop_off_date=any_date, custom_price=75.00) == 7500
        assert calculate_price_in_pence("longer", drop_off_date=any_date, custom_price=50.50) == 5050

    def test_no_date_defaults_to_late_tier(self):
        """Without drop_off_date, should default to late tier price."""
        # Without date, fallback to late tier: quick = £99, longer = £160
        assert calculate_price_in_pence("quick") == 9900
        assert calculate_price_in_pence("longer") == 16000


class TestStripeConfigEndpoint:
    """Tests for Stripe configuration endpoint."""

    @pytest.mark.asyncio
    async def test_stripe_config_not_configured(self, client):
        """Should return 503 when Stripe is not configured."""
        with patch('main.is_stripe_configured', return_value=False):
            response = await client.get("/api/stripe/config")
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_stripe_config_when_configured(self, client):
        """Should return publishable key when configured."""
        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.get_settings') as mock_settings:
                mock_settings.return_value.stripe_publishable_key = "pk_test_123"
                response = await client.get("/api/stripe/config")
                assert response.status_code == 200
                data = response.json()
                assert data["publishable_key"] == "pk_test_123"
                assert data["is_configured"] is True


class TestCreatePaymentIntent:
    """Tests for payment intent creation."""

    @pytest.mark.asyncio
    async def test_create_payment_not_configured(self, client):
        """Should return 503 when Stripe is not configured."""
        with patch('main.is_stripe_configured', return_value=False):
            response = await client.post(
                "/api/payments/create-intent",
                json={
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "package": "quick",
                    "flight_number": "FR5523",
                    "flight_date": "2026-02-10",
                    "drop_off_date": "2026-02-10",
                    "pickup_date": "2026-02-17",
                }
            )
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_create_payment_success(self, client):
        """Should create payment intent successfully."""
        from datetime import date, timedelta
        # Use dates in the future - 10 days ahead for standard tier (£89)
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()

        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 8900
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

        with patch("booking_service.get_pricing_from_db", return_value=DEFAULT_TEST_PRICING):
            with patch('main.is_stripe_configured', return_value=True):
                with patch('main.create_payment_intent', return_value=mock_intent):
                    with patch('main.get_settings') as mock_settings:
                        mock_settings.return_value.stripe_publishable_key = "pk_test_123"

                        response = await client.post(
                            "/api/payments/create-intent",
                            json={
                                "first_name": "John",
                                "last_name": "Doe",
                                "email": "john@example.com",
                                "billing_address1": "123 Test Street",
                                "billing_city": "Bournemouth",
                                "billing_postcode": "BH1 1AA",
                                "billing_country": "United Kingdom",
                                "package": "quick",
                                "flight_number": "FR5523",
                                "flight_date": drop_off,
                                "drop_off_date": drop_off,
                                "pickup_date": pickup,
                            }
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["client_secret"] == "pi_test_secret_123"
                        assert data["amount"] == 8900
                        assert data["amount_display"] == "£89.00"
                        assert data["booking_reference"].startswith("TAG-")
                        assert data["publishable_key"] == "pk_test_123"


class TestPaymentStatus:
    """Tests for payment status endpoint."""

    @pytest.mark.asyncio
    async def test_payment_status_not_configured(self, client):
        """Should return 503 when Stripe is not configured."""
        with patch('main.is_stripe_configured', return_value=False):
            response = await client.get("/api/payments/pi_test_123/status")
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_payment_status_success(self, client):
        """Should return payment status."""
        from stripe_service import PaymentStatus

        mock_status = PaymentStatus(
            payment_intent_id="pi_test_123",
            status="succeeded",
            amount=8900,
            amount_received=8900,
            currency="gbp",
            customer_email="john@example.com",
            booking_reference="TAG-ABC12345",
        )

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.get_payment_status', return_value=mock_status):
                response = await client.get("/api/payments/pi_test_123/status")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "succeeded"
                assert data["paid"] is True
                assert data["amount_display"] == "£89.00"
                assert data["booking_reference"] == "TAG-ABC12345"


class TestStripeWebhook:
    """Tests for Stripe webhook endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_missing_signature(self, client):
        """Should return 400 when signature is missing."""
        with patch('main.is_stripe_configured', return_value=True):
            response = await client.post(
                "/api/webhooks/stripe",
                content=b'{"type": "test"}',
            )
            assert response.status_code == 400
            assert "Missing Stripe signature" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_webhook_payment_succeeded(self, client):
        """Should handle payment_intent.succeeded event."""
        # Create mock StripeObject-like payment intent
        mock_payment_intent = MagicMock()
        mock_payment_intent.id = "pi_test_123"
        mock_payment_intent.amount = 9900
        mock_payment_intent.metadata = {"booking_reference": "TAG-ABC12345"}

        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": mock_payment_intent
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
                assert data["booking_reference"] == "TAG-ABC12345"

    @pytest.mark.asyncio
    async def test_webhook_payment_failed(self, client):
        """Should handle payment_intent.payment_failed event."""
        # Create mock StripeObject-like payment intent
        mock_error = MagicMock()
        mock_error.message = "Card declined"

        mock_payment_intent = MagicMock()
        mock_payment_intent.id = "pi_test_123"
        mock_payment_intent.last_payment_error = mock_error
        mock_payment_intent.metadata = {}

        mock_event = {
            "type": "payment_intent.payment_failed",
            "data": {
                "object": mock_payment_intent
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
                assert data["status"] == "failed"
                assert data["error"] == "Card declined"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test requiring real database - see test_stripe_integration.py")
    async def test_webhook_marks_promo_code_as_used(self, client):
        """
        CRITICAL TEST: Webhook should mark promo code as used when payment succeeds.

        This test verifies that:
        1. Promo code from metadata is normalized to uppercase
        2. Promo code is found in promo_codes table
        3. is_used is set to True
        4. booking_id is set
        5. promotion.codes_used is incremented

        Note: This test uses the staging database to test real integration.
        It creates test data, runs the webhook, and verifies the result.
        """
        from db_models import Promotion as DbPromotion, PromoCode as DbPromoCode
        from database import SessionLocal
        from sqlalchemy.orm import Session
        import os

        # Use a unique code to avoid conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8].upper()
        test_code_value = f"TAG-WHTEST-{unique_id}"

        # Create test promo data in database using SessionLocal directly
        # This ensures we're using the same connection pool as the webhook
        db: Session = SessionLocal()
        try:
            # Create a test promotion
            test_promotion = DbPromotion(
                name=f"Webhook Test Promo {unique_id}",
                discount_percent=10,
                total_codes=1,
                codes_sent=1,
                codes_used=0,
            )
            db.add(test_promotion)
            db.flush()

            # Create a test promo code - note: stored as UPPERCASE
            test_code = DbPromoCode(
                promotion_id=test_promotion.id,
                code=test_code_value,
                email_sent=True,
                is_used=False,
            )
            db.add(test_code)
            db.commit()

            promo_code_id = test_code.id
            promotion_id = test_promotion.id

            # Close this session so the webhook can see the committed data
            db.close()

            # Simulate webhook event with promo code in metadata (lowercase to test normalization)
            mock_event = {
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": f"pi_webhook_test_{unique_id}",
                        "amount": 9000,
                        "metadata": {
                            "booking_reference": f"TAG-WHTEST-{unique_id}",
                            "promo_code": test_code_value.lower(),  # lowercase to test normalization!
                        }
                    }
                }
            }

            # Create a real test booking in the database to avoid foreign key issues
            from db_models import Booking, Customer, Vehicle, BookingStatus
            from datetime import date, time

            db = SessionLocal()

            # First create a customer for the booking
            test_customer = Customer(
                email=f"webhook_test_{unique_id}@example.com",
                first_name="Webhook",
                last_name="Test",
                phone="07777777777"
            )
            db.add(test_customer)
            db.flush()
            customer_id = test_customer.id

            # Create a vehicle (required by booking)
            test_vehicle = Vehicle(
                customer_id=customer_id,
                registration="TEST123",
                make="Test",
                model="Car",
                colour="Black"
            )
            db.add(test_vehicle)
            db.flush()
            vehicle_id = test_vehicle.id

            # Create a test booking with all required fields
            test_booking = Booking(
                reference=f"TAG-WHTEST-{unique_id}",
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                status=BookingStatus.PENDING,
                dropoff_date=date(2026, 4, 1),
                dropoff_time=time(10, 0),
                pickup_date=date(2026, 4, 8),
            )
            db.add(test_booking)
            db.commit()
            test_booking_id = test_booking.id
            db.close()

            # Mock db_service to avoid needing real payment records
            with patch('main.is_stripe_configured', return_value=True):
                with patch('main.verify_webhook_signature', return_value=mock_event):
                    with patch('main.db_service.update_payment_status', return_value=(MagicMock(), False)):
                        with patch('main.db_service.get_booking_by_reference') as mock_get_booking:
                            mock_booking = MagicMock()
                            mock_booking.id = test_booking_id  # Use real booking ID
                            mock_get_booking.return_value = mock_booking

                            response = await client.post(
                                "/api/webhooks/stripe",
                                content=b'{}',
                                headers={"Stripe-Signature": "test_sig"},
                            )

                            assert response.status_code == 200

            # Open a new session to verify the changes
            from sqlalchemy import text
            verify_db: Session = SessionLocal()
            try:
                # Force fresh read from database (bypass any caching)
                verify_db.execute(text("SELECT 1"))  # Force connection
                updated_code = verify_db.query(DbPromoCode).filter(DbPromoCode.id == promo_code_id).first()
                verify_db.refresh(updated_code)  # Force refresh from DB
                updated_promotion = verify_db.query(DbPromotion).filter(DbPromotion.id == promotion_id).first()
                verify_db.refresh(updated_promotion)

                assert updated_code is not None, "Promo code should exist"
                assert updated_code.is_used is True, f"Promo code should be marked as used, got is_used={updated_code.is_used}"
                assert updated_code.booking_id == test_booking_id, f"Promo code should have booking_id={test_booking_id}, got {updated_code.booking_id}"
                assert updated_code.used_at is not None, "Promo code should have used_at timestamp"
                assert updated_promotion.codes_used == 1, f"Promotion codes_used should be 1, got {updated_promotion.codes_used}"
            finally:
                verify_db.close()

        finally:
            # Cleanup test data
            cleanup_db: Session = SessionLocal()
            try:
                # Delete in correct order to respect foreign keys
                cleanup_db.query(DbPromoCode).filter(DbPromoCode.code == test_code_value).delete()
                cleanup_db.query(DbPromotion).filter(DbPromotion.name == f"Webhook Test Promo {unique_id}").delete()
                cleanup_db.query(Booking).filter(Booking.reference == f"TAG-WHTEST-{unique_id}").delete()
                cleanup_db.query(Vehicle).filter(Vehicle.registration == "TEST123").delete()
                cleanup_db.query(Customer).filter(Customer.email == f"webhook_test_{unique_id}@example.com").delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


class TestAdminRefund:
    """Tests for admin refund endpoint."""

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        user = MagicMock()
        user.id = 1
        user.email = "admin@tagparking.co.uk"
        user.role = "admin"
        user.is_active = True
        return user

    @pytest.fixture(autouse=True)
    def override_admin_dependency(self, mock_admin_user):
        """Override require_admin dependency for all tests in this class."""
        from main import app, require_admin
        app.dependency_overrides[require_admin] = lambda: mock_admin_user
        yield
        app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.asyncio
    async def test_refund_not_configured(self, client):
        """Should return 503 when Stripe is not configured."""
        with patch('main.is_stripe_configured', return_value=False):
            response = await client.post("/api/admin/refund/pi_test_123")
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_refund_success(self, client):
        """Should process refund successfully."""
        mock_refund = {
            "refund_id": "re_test_123",
            "status": "succeeded",
            "amount": 8900,
        }

        with patch('main.is_stripe_configured', return_value=True):
            with patch('main.refund_payment', return_value=mock_refund):
                response = await client.post(
                    "/api/admin/refund/pi_test_123?reason=requested_by_customer"
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["refund_id"] == "re_test_123"
                assert data["amount_refunded"] == "£89.00"


class TestUpdatePaymentStatusIdempotency:
    """Tests for update_payment_status idempotency."""

    def test_update_payment_status_returns_tuple(self):
        """update_payment_status should return (payment, was_already_processed) tuple."""
        from db_service import update_payment_status
        from db_models import PaymentStatus
        from unittest.mock import MagicMock

        # Create mock session and payment
        mock_db = MagicMock()
        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.PENDING

        with patch('db_service.get_payment_by_intent_id', return_value=mock_payment):
            with patch('db_service.get_booking_by_id', return_value=MagicMock()):
                result = update_payment_status(
                    mock_db,
                    "pi_test_123",
                    PaymentStatus.SUCCEEDED
                )

                assert isinstance(result, tuple)
                assert len(result) == 2
                payment, was_already_processed = result
                assert payment == mock_payment
                assert was_already_processed is False

    def test_update_payment_status_detects_duplicate(self):
        """update_payment_status should detect already processed payments."""
        from db_service import update_payment_status
        from db_models import PaymentStatus
        from unittest.mock import MagicMock

        # Create mock session and payment that's already SUCCEEDED
        mock_db = MagicMock()
        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.SUCCEEDED  # Already processed

        with patch('db_service.get_payment_by_intent_id', return_value=mock_payment):
            result = update_payment_status(
                mock_db,
                "pi_test_123",
                PaymentStatus.SUCCEEDED
            )

            payment, was_already_processed = result
            assert payment == mock_payment
            assert was_already_processed is True
            # Should NOT have called commit (no changes made)
            mock_db.commit.assert_not_called()

    def test_update_payment_status_returns_none_for_missing(self):
        """update_payment_status should return (None, False) for missing payment."""
        from db_service import update_payment_status
        from db_models import PaymentStatus
        from unittest.mock import MagicMock

        mock_db = MagicMock()

        with patch('db_service.get_payment_by_intent_id', return_value=None):
            result = update_payment_status(
                mock_db,
                "pi_nonexistent",
                PaymentStatus.SUCCEEDED
            )

            payment, was_already_processed = result
            assert payment is None
            assert was_already_processed is False
