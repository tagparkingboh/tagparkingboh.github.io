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
        """Quick package booked 14+ days in advance should be £89.00 = 8900 pence."""
        from datetime import date, timedelta
        early_date = date.today() + timedelta(days=20)
        assert calculate_price_in_pence("quick", drop_off_date=early_date) == 8900

    def test_quick_package_standard_price(self):
        """Quick package booked 7-13 days in advance should be £99.00 = 9900 pence."""
        from datetime import date, timedelta
        standard_date = date.today() + timedelta(days=10)
        assert calculate_price_in_pence("quick", drop_off_date=standard_date) == 9900

    def test_quick_package_late_price(self):
        """Quick package booked <7 days in advance should be £109.00 = 10900 pence."""
        from datetime import date, timedelta
        late_date = date.today() + timedelta(days=3)
        assert calculate_price_in_pence("quick", drop_off_date=late_date) == 10900

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
        # Without date, fallback to late tier: quick = £109, longer = £160
        assert calculate_price_in_pence("quick") == 10900
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
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_test_secret_123"
        mock_intent.payment_intent_id = "pi_test_123"
        mock_intent.amount = 9900
        mock_intent.currency = "gbp"
        mock_intent.status = "requires_payment_method"

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
                            "package": "quick",
                            "flight_number": "FR5523",
                            "flight_date": "2026-02-10",
                            "drop_off_date": "2026-02-10",
                            "pickup_date": "2026-02-17",
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
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "amount": 9900,
                    "metadata": {
                        "booking_reference": "TAG-ABC12345",
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
                assert data["booking_reference"] == "TAG-ABC12345"

    @pytest.mark.asyncio
    async def test_webhook_payment_failed(self, client):
        """Should handle payment_intent.payment_failed event."""
        mock_event = {
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_123",
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
                data = response.json()
                assert data["status"] == "failed"
                assert data["error"] == "Card declined"


class TestAdminRefund:
    """Tests for admin refund endpoint."""

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
            "amount": 9900,
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
