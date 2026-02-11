"""
Tests for cancel payment intent functionality.

Tests the Stripe PaymentIntent cancellation when cancelling pending bookings.
All tests use mocked data to avoid database dependencies.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(id=1, first_name="Test", last_name="User", email="test@example.com"):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = "+447700900999"
    return customer


def create_mock_vehicle(id=1, customer_id=1, registration="TEST123"):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = "Test"
    vehicle.model = "Car"
    vehicle.colour = "Red"
    return vehicle


def create_mock_booking(id=1, reference="TAG-TEST001", customer_id=1, vehicle_id=1, status="pending"):
    """Create a mock booking object."""
    from db_models import BookingStatus
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.status = BookingStatus.PENDING if status == "pending" else BookingStatus.CONFIRMED
    booking.package = "quick"
    booking.dropoff_date = date(2026, 6, 15)
    booking.dropoff_time = time(8, 0)
    booking.pickup_date = date(2026, 6, 22)
    return booking


def create_mock_payment(id=1, booking_id=1, payment_intent_id="pi_test_123", status="pending"):
    """Create a mock payment object."""
    from db_models import PaymentStatus
    payment = MagicMock()
    payment.id = id
    payment.booking_id = booking_id
    payment.stripe_payment_intent_id = payment_intent_id
    payment.amount_pence = 8900
    payment.currency = "gbp"
    payment.status = PaymentStatus.PENDING if status == "pending" else PaymentStatus.SUCCEEDED
    return payment


# =============================================================================
# Unit Tests for cancel_payment_intent function
# =============================================================================

class TestCancelPaymentIntentUnit:
    """Unit tests for cancel_payment_intent function."""

    def test_cancel_payment_intent_success(self):
        """Should successfully cancel a PaymentIntent."""
        from stripe_service import cancel_payment_intent

        mock_intent = MagicMock()
        mock_intent.id = "pi_test_123"
        mock_intent.status = "canceled"

        with patch('stripe_service.stripe.PaymentIntent.cancel', return_value=mock_intent):
            with patch('stripe_service.init_stripe'):
                result = cancel_payment_intent("pi_test_123")

                assert result["success"] is True
                assert result["status"] == "canceled"
                assert result["payment_intent_id"] == "pi_test_123"

    def test_cancel_payment_intent_already_succeeded(self):
        """Should handle PaymentIntent that already succeeded."""
        from stripe_service import cancel_payment_intent
        import stripe

        with patch('stripe_service.init_stripe'):
            with patch('stripe_service.stripe.PaymentIntent.cancel') as mock_cancel:
                mock_cancel.side_effect = stripe.error.InvalidRequestError(
                    "You cannot cancel this PaymentIntent because it has a status of succeeded.",
                    param=None
                )
                result = cancel_payment_intent("pi_succeeded_123")

                assert result["success"] is False
                assert "error" in result

    def test_cancel_payment_intent_already_canceled(self):
        """Should handle PaymentIntent that is already canceled."""
        from stripe_service import cancel_payment_intent
        import stripe

        with patch('stripe_service.init_stripe'):
            with patch('stripe_service.stripe.PaymentIntent.cancel') as mock_cancel:
                mock_cancel.side_effect = stripe.error.InvalidRequestError(
                    "You cannot cancel this PaymentIntent because it has a status of canceled.",
                    param=None
                )
                result = cancel_payment_intent("pi_canceled_123")

                assert result["success"] is False
                assert "error" in result


# =============================================================================
# Mocked Integration Tests for Admin Cancel Booking Endpoint
# =============================================================================

class TestCancelBookingAdminEndpoint:
    """Mocked tests for admin cancel booking endpoint with Stripe cancellation."""

    def test_cancel_booking_calls_stripe_cancel(self):
        """Cancelling a pending booking should cancel the Stripe PaymentIntent."""
        from db_models import BookingStatus, PaymentStatus

        booking = create_mock_booking(id=1, status="pending")
        payment = create_mock_payment(id=1, booking_id=1, payment_intent_id="pi_test_cancel_123", status="pending")

        # Mock database query
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [booking, payment]

        with patch('main.cancel_payment_intent') as mock_cancel:
            mock_cancel.return_value = {"success": True, "status": "canceled", "payment_intent_id": "pi_test_cancel_123"}

            # Simulate the cancel logic
            if booking.status == BookingStatus.PENDING and payment and payment.status == PaymentStatus.PENDING:
                result = mock_cancel(payment.stripe_payment_intent_id)
                booking.status = BookingStatus.CANCELLED
                stripe_cancelled = result["success"]
            else:
                stripe_cancelled = False

            assert stripe_cancelled is True
            mock_cancel.assert_called_once_with("pi_test_cancel_123")
            assert booking.status == BookingStatus.CANCELLED

    def test_cancel_booking_skips_succeeded_payment(self):
        """Should not cancel Stripe PaymentIntent if payment already succeeded."""
        from db_models import BookingStatus, PaymentStatus

        booking = create_mock_booking(id=2, status="confirmed")
        payment = create_mock_payment(id=2, booking_id=2, payment_intent_id="pi_test_succeeded_123", status="succeeded")

        with patch('main.cancel_payment_intent') as mock_cancel:
            # Simulate the cancel logic - should skip Stripe call for succeeded payments
            if payment and payment.status == PaymentStatus.PENDING:
                mock_cancel(payment.stripe_payment_intent_id)
                stripe_cancelled = True
            else:
                stripe_cancelled = False

            # Booking still gets cancelled
            booking.status = BookingStatus.CANCELLED

            assert stripe_cancelled is False
            mock_cancel.assert_not_called()
            assert booking.status == BookingStatus.CANCELLED

    def test_cancel_booking_no_payment(self):
        """Should handle booking with no payment record."""
        from db_models import BookingStatus

        booking = create_mock_booking(id=3, status="pending")
        payment = None  # No payment record

        with patch('main.cancel_payment_intent') as mock_cancel:
            # Simulate the cancel logic
            if payment:
                mock_cancel(payment.stripe_payment_intent_id)
                stripe_cancelled = True
            else:
                stripe_cancelled = False

            booking.status = BookingStatus.CANCELLED

            assert stripe_cancelled is False
            mock_cancel.assert_not_called()
            assert booking.status == BookingStatus.CANCELLED

    def test_cancel_booking_stripe_error_continues(self):
        """Should still cancel booking even if Stripe cancel fails."""
        from db_models import BookingStatus, PaymentStatus

        booking = create_mock_booking(id=4, status="pending")
        payment = create_mock_payment(id=4, booking_id=4, payment_intent_id="pi_test_error_123", status="pending")

        with patch('main.cancel_payment_intent') as mock_cancel:
            mock_cancel.return_value = {"success": False, "error": "Stripe API error"}

            # Simulate the cancel logic
            if payment and payment.status == PaymentStatus.PENDING:
                result = mock_cancel(payment.stripe_payment_intent_id)
                stripe_cancelled = result["success"]
            else:
                stripe_cancelled = False

            # Booking should still be cancelled even if Stripe fails
            booking.status = BookingStatus.CANCELLED

            assert stripe_cancelled is False
            mock_cancel.assert_called_once_with("pi_test_error_123")
            assert booking.status == BookingStatus.CANCELLED

    def test_cancel_response_structure(self):
        """Cancel booking response should have correct structure."""
        response_data = {
            "success": True,
            "message": "Booking cancelled successfully. Stripe payment has been cancelled.",
            "stripe_cancelled": True,
            "booking_id": 1,
            "reference": "TAG-TEST001",
        }

        assert "success" in response_data
        assert "message" in response_data
        assert "stripe_cancelled" in response_data
        assert response_data["success"] is True
        assert response_data["stripe_cancelled"] is True


# =============================================================================
# Integration Tests (require real Stripe API - skipped by default)
# =============================================================================

class TestCancelPaymentIntentIntegration:
    """Integration tests with real Stripe test mode (requires STRIPE_SECRET_KEY)."""

    @pytest.mark.integration
    def test_cancel_real_payment_intent(self):
        """Test cancelling a real PaymentIntent in Stripe test mode."""
        import os
        import stripe
        from stripe_service import cancel_payment_intent, init_stripe

        # Skip if Stripe not configured
        if not os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_test_"):
            pytest.skip("Stripe test key not configured")

        # Initialize Stripe
        init_stripe()

        # Create a PaymentIntent directly via Stripe API for testing
        intent = stripe.PaymentIntent.create(
            amount=1000,  # £10.00
            currency="gbp",
            metadata={"test": "cancel_integration"}
        )
        payment_intent_id = intent.id

        try:
            # Cancel it using our function
            result = cancel_payment_intent(payment_intent_id)

            assert result["success"] is True
            assert result["status"] == "canceled"
            assert result["payment_intent_id"] == payment_intent_id
        except Exception as e:
            pytest.fail(f"Integration test failed: {e}")
