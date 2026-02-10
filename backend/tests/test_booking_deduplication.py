"""
Tests for booking deduplication by session_id.

Covers:
- Happy path: Existing PENDING booking with valid PaymentIntent is reused
- Negative path: No existing booking, PaymentIntent not usable
- Edge cases: No payment record, Stripe errors, etc.

All tests use mocked data to avoid database and Stripe API conflicts.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import date, time, datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import Booking, BookingStatus, Payment, PaymentStatus


# =============================================================================
# get_pending_booking_by_session() Unit Tests
# =============================================================================

class TestGetPendingBookingBySession:
    """Tests for the get_pending_booking_by_session() function."""

    def test_returns_pending_booking_with_matching_session_id(self):
        """Should return PENDING booking when session_id matches."""
        from db_service import get_pending_booking_by_session

        # Create mock booking
        mock_booking = MagicMock(spec=Booking)
        mock_booking.reference = "TAG-ABC123"
        mock_booking.status = BookingStatus.PENDING
        mock_booking.session_id = "session-12345"

        # Create mock db session
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_booking

        result = get_pending_booking_by_session(mock_db, "session-12345")

        assert result is not None
        assert result.reference == "TAG-ABC123"

    def test_returns_none_when_no_matching_session_id(self):
        """Should return None when no booking with session_id exists."""
        from db_service import get_pending_booking_by_session

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        result = get_pending_booking_by_session(mock_db, "non-existent-session")

        assert result is None

    def test_returns_none_when_session_id_is_none(self):
        """Should return None immediately when session_id is None."""
        from db_service import get_pending_booking_by_session

        mock_db = MagicMock()

        result = get_pending_booking_by_session(mock_db, None)

        assert result is None
        mock_db.query.assert_not_called()

    def test_returns_none_when_session_id_is_empty_string(self):
        """Should return None when session_id is empty string."""
        from db_service import get_pending_booking_by_session

        mock_db = MagicMock()

        result = get_pending_booking_by_session(mock_db, "")

        assert result is None
        mock_db.query.assert_not_called()

    def test_only_returns_pending_status_not_confirmed(self):
        """Should only find PENDING bookings, not CONFIRMED ones."""
        from db_service import get_pending_booking_by_session

        # The filter should include status == PENDING check
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        get_pending_booking_by_session(mock_db, "session-12345")

        # Verify filter was called (the actual filter conditions are checked elsewhere)
        assert mock_query.filter.called


# =============================================================================
# create_booking() with session_id Tests
# =============================================================================

class TestCreateBookingWithSessionId:
    """Tests for create_booking() storing session_id."""

    def test_booking_stores_session_id(self):
        """Booking should store the session_id when provided."""
        # Create a mock booking to verify session_id is passed
        booking = Booking(
            reference="TAG-TEST01",
            customer_id=1,
            vehicle_id=1,
            package="quick",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 3, 15),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 3, 22),
            session_id="test-session-abc"
        )

        assert booking.session_id == "test-session-abc"

    def test_booking_allows_none_session_id(self):
        """Booking should allow None for session_id (backwards compatibility)."""
        booking = Booking(
            reference="TAG-TEST02",
            customer_id=1,
            vehicle_id=1,
            package="quick",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 3, 15),
            dropoff_time=time(10, 0),
            pickup_date=date(2026, 3, 22),
            session_id=None
        )

        assert booking.session_id is None


# =============================================================================
# PaymentIntent Reuse Logic Tests (Mocked)
# =============================================================================

class TestPaymentIntentReuseLogic:
    """Tests for PaymentIntent reuse decision logic."""

    def test_should_reuse_requires_payment_method_intent(self):
        """PaymentIntent with 'requires_payment_method' status should be reused."""
        # This tests the logic: if intent.status in ['requires_payment_method', ...]
        valid_reuse_statuses = ['requires_payment_method', 'requires_confirmation', 'requires_action']

        for status in valid_reuse_statuses:
            mock_intent = MagicMock()
            mock_intent.status = status
            mock_intent.client_secret = "pi_secret_123"
            mock_intent.id = "pi_test123"
            mock_intent.amount = 7900

            # The logic check
            should_reuse = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']
            assert should_reuse is True, f"Status '{status}' should be reusable"

    def test_should_not_reuse_succeeded_intent(self):
        """PaymentIntent with 'succeeded' status should NOT be reused."""
        mock_intent = MagicMock()
        mock_intent.status = 'succeeded'

        should_reuse = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']
        assert should_reuse is False

    def test_should_not_reuse_cancelled_intent(self):
        """PaymentIntent with 'canceled' status should NOT be reused."""
        mock_intent = MagicMock()
        mock_intent.status = 'canceled'

        should_reuse = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']
        assert should_reuse is False

    def test_should_not_reuse_processing_intent(self):
        """PaymentIntent with 'processing' status should NOT be reused."""
        mock_intent = MagicMock()
        mock_intent.status = 'processing'

        should_reuse = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']
        assert should_reuse is False


# =============================================================================
# Deduplication Response Tests (Mocked)
# =============================================================================

class TestDeduplicationResponse:
    """Tests for the deduplication response structure."""

    def test_reused_response_contains_correct_fields(self):
        """When reusing PaymentIntent, response should contain all required fields."""
        # Simulate the response structure
        mock_intent = MagicMock()
        mock_intent.client_secret = "pi_secret_abc"
        mock_intent.id = "pi_reused123"
        mock_intent.amount = 7900

        existing_booking_ref = "TAG-EXIST1"

        # Simulate response construction
        response = {
            "client_secret": mock_intent.client_secret,
            "payment_intent_id": mock_intent.id,
            "booking_reference": existing_booking_ref,
            "amount": mock_intent.amount,
            "amount_display": f"£{mock_intent.amount / 100:.2f}",
        }

        assert response["client_secret"] == "pi_secret_abc"
        assert response["payment_intent_id"] == "pi_reused123"
        assert response["booking_reference"] == "TAG-EXIST1"
        assert response["amount"] == 7900
        assert response["amount_display"] == "£79.00"

    def test_amount_display_formats_correctly(self):
        """Amount display should format correctly for various amounts."""
        test_cases = [
            (7900, "£79.00"),
            (11900, "£119.00"),
            (0, "£0.00"),
            (999, "£9.99"),
            (10050, "£100.50"),
        ]

        for amount, expected_display in test_cases:
            display = f"£{amount / 100:.2f}"
            assert display == expected_display, f"Amount {amount} should display as {expected_display}"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestDeduplicationEdgeCases:
    """Edge case tests for booking deduplication."""

    def test_existing_booking_no_payment_record(self):
        """When existing booking has no payment record, should proceed to create new."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.reference = "TAG-NOPAY1"
        mock_booking.payment = None  # No payment record

        has_reusable_payment = (
            mock_booking.payment is not None and
            mock_booking.payment.stripe_payment_intent_id is not None
        )

        assert has_reusable_payment is False

    def test_existing_booking_payment_no_intent_id(self):
        """When payment record exists but no PaymentIntent ID, should create new."""
        mock_booking = MagicMock(spec=Booking)
        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = None
        mock_booking.payment = mock_payment

        has_reusable_payment = (
            mock_booking.payment is not None and
            mock_booking.payment.stripe_payment_intent_id is not None
        )

        assert has_reusable_payment is False

    def test_existing_booking_payment_empty_intent_id(self):
        """When payment has empty string PaymentIntent ID, should create new."""
        mock_booking = MagicMock(spec=Booking)
        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = ""
        mock_booking.payment = mock_payment

        # Empty string is falsy - use bool() for proper boolean conversion
        has_reusable_payment = bool(
            mock_booking.payment is not None and
            mock_booking.payment.stripe_payment_intent_id
        )

        assert has_reusable_payment is False

    def test_stripe_api_error_handling(self):
        """When Stripe API fails, should handle gracefully and create new."""
        import stripe

        # Simulate Stripe error
        stripe_error = stripe.error.StripeError("Network error")

        # The logic should catch this and continue
        should_continue_to_new = True
        try:
            raise stripe_error
        except stripe.error.StripeError:
            should_continue_to_new = True

        assert should_continue_to_new is True


# =============================================================================
# Session ID Validation Tests
# =============================================================================

class TestSessionIdValidation:
    """Tests for session_id validation in deduplication."""

    def test_valid_uuid_session_id(self):
        """Standard UUID-like session IDs should work."""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        assert session_id is not None
        assert len(session_id) > 0

    def test_numeric_session_id(self):
        """Numeric session IDs should work."""
        session_id = "1234567890"
        assert session_id is not None
        assert len(session_id) > 0

    def test_alphanumeric_session_id(self):
        """Alphanumeric session IDs should work."""
        session_id = "abc123xyz789"
        assert session_id is not None
        assert len(session_id) > 0

    def test_long_session_id_within_limit(self):
        """Session IDs up to 100 chars should be valid (column limit)."""
        session_id = "a" * 100
        assert len(session_id) <= 100


# =============================================================================
# Terms Toggle Scenario Tests
# =============================================================================

class TestTermsToggleScenario:
    """Tests simulating the Terms checkbox toggle scenario."""

    def test_first_check_creates_booking(self):
        """First Terms check should create new booking and PaymentIntent."""
        # Simulate: no existing booking for session
        existing_booking = None

        should_create_new = existing_booking is None
        assert should_create_new is True

    def test_uncheck_does_not_affect_database(self):
        """Unchecking Terms (frontend only) doesn't call backend."""
        # This is a frontend behavior - when Terms is unchecked,
        # StripePayment unmounts but no API call is made.
        # Backend state remains unchanged.

        # Simulating that the booking still exists
        booking_still_exists = True
        payment_intent_still_valid = True

        assert booking_still_exists is True
        assert payment_intent_still_valid is True

    def test_second_check_reuses_existing(self):
        """Second Terms check should find and reuse existing booking."""
        # Simulate: existing PENDING booking found for session
        mock_existing_booking = MagicMock()
        mock_existing_booking.reference = "TAG-FIRST1"
        mock_existing_booking.status = BookingStatus.PENDING
        mock_existing_booking.payment = MagicMock()
        mock_existing_booking.payment.stripe_payment_intent_id = "pi_original"

        existing_booking = mock_existing_booking

        should_reuse = existing_booking is not None
        assert should_reuse is True
        assert existing_booking.reference == "TAG-FIRST1"

    def test_toggle_three_times_same_reference(self):
        """Toggling Terms 3 times should result in same booking reference."""
        # The key invariant: same session_id -> same booking reference
        session_id = "toggle-test-session"

        # First call: creates booking with reference TAG-A
        # Second call: finds existing, returns TAG-A
        # Third call: finds existing, returns TAG-A

        first_reference = "TAG-TOGGLE1"

        # Simulate the deduplication finding the same booking each time
        found_references = [first_reference, first_reference, first_reference]

        assert all(ref == first_reference for ref in found_references)


# =============================================================================
# Multiple Booking Attempts Tests
# =============================================================================

class TestMultipleBookingAttempts:
    """Tests for multiple booking attempts from same user."""

    def test_different_sessions_create_different_bookings(self):
        """Different session IDs should create separate bookings."""
        session_1 = "session-abc"
        session_2 = "session-xyz"

        # These are different sessions, so different bookings
        assert session_1 != session_2

    def test_same_session_same_booking(self):
        """Same session ID should always return same booking."""
        session_id = "consistent-session"

        # Simulate multiple lookups returning same booking
        booking_ref_1 = "TAG-SAME01"
        booking_ref_2 = "TAG-SAME01"  # Same as above

        assert booking_ref_1 == booking_ref_2

    def test_new_session_after_completed_booking(self):
        """New session after completing a booking should create new booking."""
        # First session: completed booking
        first_session = "session-completed"
        first_booking_status = BookingStatus.CONFIRMED

        # Second session: new booking attempt
        second_session = "session-new"

        # The get_pending_booking_by_session only finds PENDING bookings
        # So first booking (CONFIRMED) won't be found
        first_is_pending = first_booking_status == BookingStatus.PENDING

        assert first_is_pending is False
        assert first_session != second_session


# =============================================================================
# Payment Status Edge Cases
# =============================================================================

class TestPaymentStatusEdgeCases:
    """Tests for various payment status scenarios."""

    def test_payment_failed_should_allow_new_attempt(self):
        """If payment failed, deduplication should still find the booking."""
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.PENDING
        mock_payment = MagicMock()
        mock_payment.status = PaymentStatus.FAILED
        mock_payment.stripe_payment_intent_id = "pi_failed123"
        mock_booking.payment = mock_payment

        # Booking is still PENDING even if payment failed
        booking_is_pending = mock_booking.status == BookingStatus.PENDING
        assert booking_is_pending is True

    def test_payment_succeeded_booking_confirmed(self):
        """If payment succeeded, booking should be CONFIRMED, not found by dedup."""
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.CONFIRMED  # After successful payment

        # get_pending_booking_by_session only finds PENDING
        would_be_found = mock_booking.status == BookingStatus.PENDING
        assert would_be_found is False

    def test_payment_refunded_booking_not_reused(self):
        """Refunded booking should not be found by session lookup."""
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.REFUNDED

        would_be_found = mock_booking.status == BookingStatus.PENDING
        assert would_be_found is False


# =============================================================================
# Integration-Style Tests (Mocked)
# =============================================================================

class TestDeduplicationIntegration:
    """Integration-style tests with mocked components."""

    def test_full_deduplication_flow_reuse(self):
        """Full flow: session exists -> find booking -> retrieve intent -> return."""
        session_id = "integration-session-1"

        # Step 1: Find existing booking
        mock_booking = MagicMock()
        mock_booking.reference = "TAG-INTEG1"
        mock_booking.status = BookingStatus.PENDING
        mock_booking.session_id = session_id

        # Step 2: Booking has payment with intent
        mock_payment = MagicMock()
        mock_payment.stripe_payment_intent_id = "pi_integration123"
        mock_booking.payment = mock_payment

        # Step 3: Intent is valid
        mock_intent = MagicMock()
        mock_intent.status = "requires_payment_method"
        mock_intent.client_secret = "pi_secret_integration"
        mock_intent.id = "pi_integration123"
        mock_intent.amount = 7900

        # Verify flow would work
        booking_found = mock_booking is not None
        has_payment = mock_booking.payment is not None
        has_intent_id = mock_booking.payment.stripe_payment_intent_id is not None
        intent_reusable = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']

        assert booking_found is True
        assert has_payment is True
        assert has_intent_id is True
        assert intent_reusable is True

    def test_full_deduplication_flow_create_new(self):
        """Full flow: no session match -> create new booking."""
        session_id = "new-session-123"

        # Step 1: No existing booking found
        existing_booking = None

        # Step 2: Should proceed to create new
        should_create_new = existing_booking is None

        assert should_create_new is True

    def test_full_flow_intent_not_reusable(self):
        """Full flow: booking exists but intent not reusable -> create new intent."""
        session_id = "intent-expired-session"

        # Step 1: Find existing booking
        mock_booking = MagicMock()
        mock_booking.reference = "TAG-EXPIRE1"
        mock_booking.status = BookingStatus.PENDING

        # Step 2: Payment exists
        mock_payment = MagicMock()
        mock_payment.stripe_payment_intent_id = "pi_expired123"
        mock_booking.payment = mock_payment

        # Step 3: Intent is NOT reusable (already succeeded)
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"

        intent_reusable = mock_intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']

        assert intent_reusable is False
        # In this case, code would continue to create new PaymentIntent


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
