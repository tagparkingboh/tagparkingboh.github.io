"""
Tests for cancel payment intent functionality.

Tests the Stripe PaymentIntent cancellation when cancelling pending bookings.
Uses staging database and Stripe test mode.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, get_current_user


def mock_admin_user():
    """Return a mock admin user for testing."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client():
    """Create an async test client with admin auth mocked."""
    app.dependency_overrides[get_current_user] = mock_admin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


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


class TestCancelBookingAdminEndpoint:
    """Integration tests for admin cancel booking endpoint with Stripe cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_booking_calls_stripe_cancel(self, admin_client, db_session):
        """Cancelling a pending booking should cancel the Stripe PaymentIntent."""
        from db_models import Booking, Payment, Customer, Vehicle, BookingStatus, PaymentStatus
        from datetime import date, time
        import uuid

        # Use unique identifiers to avoid conflicts with staging data
        unique_id = uuid.uuid4().hex[:8]

        # Create test data
        customer = Customer(
            first_name="Test",
            last_name="CancelStripe",
            email=f"test.cancelstripe.{unique_id}@example.com",
            phone="+447700900999"
        )
        db_session.add(customer)
        db_session.flush()

        vehicle = Vehicle(
            customer_id=customer.id,
            registration=f"CAN{unique_id[:4]}",
            make="Test",
            model="Cancel",
            colour="Red"
        )
        db_session.add(vehicle)
        db_session.flush()

        booking = Booking(
            reference=f"TAG-CAN{unique_id[:5]}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status=BookingStatus.PENDING,
            package="quick",
            dropoff_date=date(2026, 6, 15),
            dropoff_time=time(8, 0),
            pickup_date=date(2026, 6, 22),
        )
        db_session.add(booking)
        db_session.flush()

        payment = Payment(
            booking_id=booking.id,
            stripe_payment_intent_id=f"pi_test_cancel_{unique_id}",
            amount_pence=8900,
            currency="gbp",
            status=PaymentStatus.PENDING,
        )
        db_session.add(payment)
        db_session.commit()

        booking_id = booking.id
        vehicle_id = vehicle.id
        customer_id = customer.id

        try:
            # Mock the cancel_payment_intent call
            with patch('main.cancel_payment_intent') as mock_cancel:
                mock_cancel.return_value = {"success": True, "status": "canceled", "payment_intent_id": f"pi_test_cancel_{unique_id}"}

                response = await admin_client.post(f"/api/admin/bookings/{booking_id}/cancel")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["stripe_cancelled"] is True
                assert "Stripe payment has been cancelled" in data["message"]

                # Verify cancel_payment_intent was called with correct ID
                mock_cancel.assert_called_once_with(f"pi_test_cancel_{unique_id}")

        finally:
            # Cleanup test data
            db_session.query(Payment).filter(Payment.booking_id == booking_id).delete()
            db_session.query(Booking).filter(Booking.id == booking_id).delete()
            db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).delete()
            db_session.query(Customer).filter(Customer.id == customer_id).delete()
            db_session.commit()

    @pytest.mark.asyncio
    async def test_cancel_booking_skips_succeeded_payment(self, admin_client, db_session):
        """Should not cancel Stripe PaymentIntent if payment already succeeded."""
        from db_models import Booking, Payment, Customer, Vehicle, BookingStatus, PaymentStatus
        from datetime import date, time
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create test data with SUCCEEDED payment
        customer = Customer(
            first_name="Test",
            last_name="SucceededPay",
            email=f"test.succeededpay.{unique_id}@example.com",
            phone="+447700900998"
        )
        db_session.add(customer)
        db_session.flush()

        vehicle = Vehicle(
            customer_id=customer.id,
            registration=f"SUC{unique_id[:4]}",
            make="Test",
            model="Succeeded",
            colour="Blue"
        )
        db_session.add(vehicle)
        db_session.flush()

        booking = Booking(
            reference=f"TAG-SUC{unique_id[:5]}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status=BookingStatus.CONFIRMED,
            package="quick",
            dropoff_date=date(2026, 6, 16),
            dropoff_time=time(9, 0),
            pickup_date=date(2026, 6, 23),
        )
        db_session.add(booking)
        db_session.flush()

        payment = Payment(
            booking_id=booking.id,
            stripe_payment_intent_id=f"pi_test_succeeded_{unique_id}",
            amount_pence=8900,
            currency="gbp",
            status=PaymentStatus.SUCCEEDED,  # Already succeeded
        )
        db_session.add(payment)
        db_session.commit()

        booking_id = booking.id
        vehicle_id = vehicle.id
        customer_id = customer.id

        try:
            with patch('main.cancel_payment_intent') as mock_cancel:
                response = await admin_client.post(f"/api/admin/bookings/{booking_id}/cancel")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["stripe_cancelled"] is False

                # Verify cancel_payment_intent was NOT called
                mock_cancel.assert_not_called()

        finally:
            # Cleanup test data
            db_session.query(Payment).filter(Payment.booking_id == booking_id).delete()
            db_session.query(Booking).filter(Booking.id == booking_id).delete()
            db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).delete()
            db_session.query(Customer).filter(Customer.id == customer_id).delete()
            db_session.commit()

    @pytest.mark.asyncio
    async def test_cancel_booking_no_payment(self, admin_client, db_session):
        """Should handle booking with no payment record."""
        from db_models import Booking, Customer, Vehicle, BookingStatus
        from datetime import date, time
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create test data without payment
        customer = Customer(
            first_name="Test",
            last_name="NoPay",
            email=f"test.nopay.{unique_id}@example.com",
            phone="+447700900997"
        )
        db_session.add(customer)
        db_session.flush()

        vehicle = Vehicle(
            customer_id=customer.id,
            registration=f"NOP{unique_id[:4]}",
            make="Test",
            model="NoPay",
            colour="Green"
        )
        db_session.add(vehicle)
        db_session.flush()

        booking = Booking(
            reference=f"TAG-NOP{unique_id[:5]}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status=BookingStatus.PENDING,
            package="quick",
            dropoff_date=date(2026, 6, 17),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 6, 24),
        )
        db_session.add(booking)
        db_session.commit()

        booking_id = booking.id
        vehicle_id = vehicle.id
        customer_id = customer.id

        try:
            with patch('main.cancel_payment_intent') as mock_cancel:
                response = await admin_client.post(f"/api/admin/bookings/{booking_id}/cancel")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["stripe_cancelled"] is False

                # Verify cancel_payment_intent was NOT called (no payment)
                mock_cancel.assert_not_called()

        finally:
            # Cleanup test data
            db_session.query(Booking).filter(Booking.id == booking_id).delete()
            db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).delete()
            db_session.query(Customer).filter(Customer.id == customer_id).delete()
            db_session.commit()

    @pytest.mark.asyncio
    async def test_cancel_booking_stripe_error_continues(self, admin_client, db_session):
        """Should still cancel booking even if Stripe cancel fails."""
        from db_models import Booking, Payment, Customer, Vehicle, BookingStatus, PaymentStatus
        from datetime import date, time
        import uuid

        unique_id = uuid.uuid4().hex[:8]

        # Create test data
        customer = Customer(
            first_name="Test",
            last_name="StripeErr",
            email=f"test.stripeerr.{unique_id}@example.com",
            phone="+447700900996"
        )
        db_session.add(customer)
        db_session.flush()

        vehicle = Vehicle(
            customer_id=customer.id,
            registration=f"SER{unique_id[:4]}",
            make="Test",
            model="StripeErr",
            colour="Yellow"
        )
        db_session.add(vehicle)
        db_session.flush()

        booking = Booking(
            reference=f"TAG-SER{unique_id[:5]}",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            status=BookingStatus.PENDING,
            package="quick",
            dropoff_date=date(2026, 6, 18),
            dropoff_time=time(11, 0),
            pickup_date=date(2026, 6, 25),
        )
        db_session.add(booking)
        db_session.flush()

        payment = Payment(
            booking_id=booking.id,
            stripe_payment_intent_id=f"pi_test_error_{unique_id}",
            amount_pence=8900,
            currency="gbp",
            status=PaymentStatus.PENDING,
        )
        db_session.add(payment)
        db_session.commit()

        booking_id = booking.id
        vehicle_id = vehicle.id
        customer_id = customer.id

        try:
            # Mock Stripe cancel to fail
            with patch('main.cancel_payment_intent') as mock_cancel:
                mock_cancel.return_value = {"success": False, "error": "Stripe API error"}

                response = await admin_client.post(f"/api/admin/bookings/{booking_id}/cancel")

                # Booking should still be cancelled
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["stripe_cancelled"] is False  # Failed but booking still cancelled

                # Verify booking status was updated
                db_session.refresh(booking)
                assert booking.status == BookingStatus.CANCELLED

        finally:
            # Cleanup test data
            db_session.query(Payment).filter(Payment.booking_id == booking_id).delete()
            db_session.query(Booking).filter(Booking.id == booking_id).delete()
            db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).delete()
            db_session.query(Customer).filter(Customer.id == customer_id).delete()
            db_session.commit()


class TestCancelPaymentIntentIntegration:
    """Integration tests with real Stripe test mode (requires STRIPE_SECRET_KEY)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cancel_real_payment_intent(self):
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
            # If the test fails, try to clean up
            pytest.fail(f"Integration test failed: {e}")
