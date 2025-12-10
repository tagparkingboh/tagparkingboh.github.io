"""
Tests for Stripe payment integration.

Note: These tests mock the Stripe API to avoid actual charges.
For integration tests with Stripe's test mode, use the sandbox keys.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from stripe_service import calculate_price_in_pence


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCalculatePriceInPence:
    """Tests for price calculation."""

    def test_quick_package_price(self):
        """Quick package should be £99.00 = 9900 pence."""
        assert calculate_price_in_pence("quick") == 9900

    def test_longer_package_price(self):
        """Longer package should be £135.00 = 13500 pence."""
        assert calculate_price_in_pence("longer") == 13500

    def test_custom_price_override(self):
        """Custom price should override package price."""
        assert calculate_price_in_pence("quick", custom_price=75.00) == 7500
        assert calculate_price_in_pence("longer", custom_price=50.50) == 5050

    def test_unknown_package_defaults_to_quick(self):
        """Unknown package should default to quick price."""
        assert calculate_price_in_pence("unknown") == 9900


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
                    assert data["amount"] == 9900
                    assert data["amount_display"] == "£99.00"
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
            amount=9900,
            amount_received=9900,
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
                assert data["amount_display"] == "£99.00"
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
                assert data["amount_refunded"] == "£99.00"
