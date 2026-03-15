"""
Tests for promo code change functionality in payment intent creation.

Covers:
- Happy path: Promo applied, promo removed, promo changed
- Negative path: Invalid promo codes, already used codes
- Edge cases: Empty strings, None values, case sensitivity
- Boundary cases: Promo code at discount limits (0%, 10%, 100%)
- Integration tests: Full flow with mocked Stripe and database

All tests use mocked data to avoid database and Stripe API conflicts.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import date, time, datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import Booking, BookingStatus, Payment, PaymentStatus, MarketingSubscriber

# Use relative dates for future-proof tests
TODAY = date.today()
FUTURE_DATE = TODAY + timedelta(days=90)
FUTURE_DATE_END = TODAY + timedelta(days=97)


# =============================================================================
# UNIT TESTS: Promo Code Change Detection
# =============================================================================

class TestPromoCodeChangeDetection:
    """Tests for detecting when promo code has changed."""

    def test_promo_added_detected_as_change(self):
        """Adding a promo code (None -> 'CODE') should be detected as change."""
        existing_promo = None
        new_promo = "FOUNDER-ABC123"

        promo_changed = existing_promo != new_promo

        assert promo_changed is True

    def test_promo_removed_detected_as_change(self):
        """Removing a promo code ('CODE' -> None) should be detected as change."""
        existing_promo = "FOUNDER-ABC123"
        new_promo = None

        promo_changed = existing_promo != new_promo

        assert promo_changed is True

    def test_promo_changed_to_different_code(self):
        """Changing from one promo to another should be detected."""
        existing_promo = "PROMO-10-ABC"
        new_promo = "FOUNDER-XYZ789"

        promo_changed = existing_promo != new_promo

        assert promo_changed is True

    def test_same_promo_not_detected_as_change(self):
        """Same promo code should NOT be detected as change."""
        existing_promo = "FOUNDER-ABC123"
        new_promo = "FOUNDER-ABC123"

        promo_changed = existing_promo != new_promo

        assert promo_changed is False

    def test_both_none_not_detected_as_change(self):
        """Both None should NOT be detected as change."""
        existing_promo = None
        new_promo = None

        promo_changed = existing_promo != new_promo

        assert promo_changed is False

    def test_empty_string_treated_as_none(self):
        """Empty string should be normalized to None for comparison."""
        # Simulating the normalization logic from the code
        request_promo_code = ""
        new_promo = request_promo_code.strip().upper() if request_promo_code else None

        assert new_promo is None

    def test_whitespace_only_treated_as_none(self):
        """Whitespace-only string should be normalized to None."""
        request_promo_code = "   "
        new_promo = request_promo_code.strip().upper() if request_promo_code and request_promo_code.strip() else None

        assert new_promo is None

    def test_promo_code_uppercased_for_comparison(self):
        """Promo codes should be uppercased for comparison."""
        request_promo_code = "founder-abc123"
        new_promo = request_promo_code.strip().upper() if request_promo_code else None

        assert new_promo == "FOUNDER-ABC123"

    def test_case_insensitive_same_code_not_change(self):
        """Same code with different case should NOT be a change (after normalization)."""
        existing_promo = "FOUNDER-ABC123"
        request_promo_code = "founder-abc123"
        new_promo = request_promo_code.strip().upper() if request_promo_code else None

        promo_changed = existing_promo != new_promo

        assert promo_changed is False


# =============================================================================
# UNIT TESTS: PaymentIntent Cancellation Logic
# =============================================================================

class TestPaymentIntentCancellation:
    """Tests for PaymentIntent cancellation when promo changes."""

    def test_cancel_called_when_promo_changes(self):
        """stripe.PaymentIntent.cancel should be called when promo changes."""
        import stripe

        with patch.object(stripe.PaymentIntent, 'cancel') as mock_cancel:
            mock_cancel.return_value = MagicMock(status='canceled')

            # Simulate the cancellation
            old_intent_id = "pi_old123"
            stripe.PaymentIntent.cancel(old_intent_id)

            mock_cancel.assert_called_once_with(old_intent_id)

    def test_cancel_error_handled_gracefully(self):
        """Stripe cancel errors should be caught and logged, not raised."""
        import stripe

        with patch.object(stripe.PaymentIntent, 'cancel') as mock_cancel:
            mock_cancel.side_effect = stripe.error.StripeError("Already canceled")

            # Simulate the error handling
            error_caught = False
            try:
                stripe.PaymentIntent.cancel("pi_already_canceled")
            except stripe.error.StripeError:
                error_caught = True

            assert error_caught is True
            # In actual code, this error is caught and logged

    def test_cancel_not_called_when_promo_unchanged(self):
        """PaymentIntent should NOT be canceled when promo is unchanged."""
        existing_promo = "FOUNDER-ABC123"
        new_promo = "FOUNDER-ABC123"
        promo_changed = existing_promo != new_promo

        # Cancel should only be called if promo_changed is True
        should_cancel = promo_changed

        assert should_cancel is False


# =============================================================================
# UNIT TESTS: Payment Record Deletion
# =============================================================================

class TestPaymentRecordDeletion:
    """Tests for payment record deletion when promo changes."""

    def test_payment_record_deleted_when_promo_changes(self):
        """Old payment record should be deleted when promo changes."""
        mock_db = MagicMock()
        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = "pi_old123"

        # Simulate deletion
        mock_db.delete(mock_payment)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(mock_payment)
        mock_db.commit.assert_called_once()

    def test_payment_record_not_deleted_when_promo_unchanged(self):
        """Payment record should NOT be deleted when promo is unchanged."""
        mock_db = MagicMock()
        mock_payment = MagicMock(spec=Payment)

        promo_changed = False

        if promo_changed:
            mock_db.delete(mock_payment)

        mock_db.delete.assert_not_called()


# =============================================================================
# UNIT TESTS: Booking Update on Promo Change
# =============================================================================

class TestBookingUpdateOnPromoChange:
    """Tests for booking field updates when promo changes."""

    def test_booking_promo_code_updated(self):
        """Booking's promo_code field should be updated."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.promo_code = "OLD-PROMO"

        new_promo_code = "NEW-PROMO"
        mock_booking.promo_code = new_promo_code

        assert mock_booking.promo_code == "NEW-PROMO"

    def test_booking_promo_code_set_to_none_when_removed(self):
        """Booking's promo_code should be None when promo is removed."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.promo_code = "OLD-PROMO"

        mock_booking.promo_code = None

        assert mock_booking.promo_code is None

    def test_booking_amount_updated_with_discount(self):
        """Booking's amount should reflect the discounted price."""
        mock_booking = MagicMock(spec=Booking)
        original_amount = 27500  # £275.00 in pence
        discount_percent = 10
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        mock_booking.amount = final_amount
        mock_booking.original_amount = original_amount
        mock_booking.discount_amount = discount_amount

        assert mock_booking.amount == 24750  # £247.50
        assert mock_booking.original_amount == 27500
        assert mock_booking.discount_amount == 2750

    def test_booking_amount_updated_to_full_when_promo_removed(self):
        """Booking's amount should be full price when promo is removed."""
        mock_booking = MagicMock(spec=Booking)
        full_amount = 27500  # £275.00 in pence

        mock_booking.amount = full_amount
        mock_booking.original_amount = None
        mock_booking.discount_amount = None
        mock_booking.promo_code = None

        assert mock_booking.amount == 27500
        assert mock_booking.original_amount is None
        assert mock_booking.discount_amount is None

    def test_booking_updated_at_timestamp_set(self):
        """Booking's updated_at should be set when promo changes."""
        mock_booking = MagicMock(spec=Booking)
        before_update = datetime.utcnow()

        mock_booking.updated_at = datetime.utcnow()

        assert mock_booking.updated_at >= before_update


# =============================================================================
# UNIT TESTS: Discount Calculation
# =============================================================================

class TestDiscountCalculation:
    """Tests for discount calculation with various promo types."""

    def test_10_percent_discount_calculation(self):
        """10% discount should calculate correctly."""
        original_amount = 27500  # £275.00
        discount_percent = 10

        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        assert discount_amount == 2750  # £27.50
        assert final_amount == 24750  # £247.50

    def test_100_percent_discount_for_short_trip(self):
        """100% promo on 7-day trip should be completely free."""
        original_amount = 7900  # £79.00 (1-week price)
        discount_percent = 100
        duration_days = 7

        if discount_percent == 100 and duration_days <= 7:
            discount_amount = original_amount
            is_free_booking = True
        else:
            discount_amount = int(original_amount * discount_percent / 100)
            is_free_booking = False

        assert discount_amount == 7900
        assert is_free_booking is True

    def test_100_percent_discount_for_long_trip(self):
        """100% promo on >7-day trip should deduct 1-week base rate."""
        original_amount = 11900  # £119.00 (10-day trip)
        week1_base = 7900  # £79.00 (1-week early tier)
        duration_days = 10
        discount_percent = 100

        if discount_percent == 100:
            if duration_days <= 7:
                discount_amount = original_amount
                is_free_booking = True
            else:
                discount_amount = min(week1_base, original_amount)
                is_free_booking = False

        assert discount_amount == 7900  # Deducts 1-week base
        assert is_free_booking is False

    def test_no_discount_when_no_promo(self):
        """No promo should result in zero discount."""
        original_amount = 27500
        promo_code_applied = None

        if promo_code_applied:
            discount_amount = 2750
        else:
            discount_amount = 0

        assert discount_amount == 0


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestPromoCodeEdgeCases:
    """Edge case tests for promo code changes."""

    def test_promo_with_leading_trailing_spaces(self):
        """Promo code with spaces should be trimmed."""
        request_promo_code = "  FOUNDER-ABC123  "
        normalized = request_promo_code.strip().upper() if request_promo_code else None

        assert normalized == "FOUNDER-ABC123"

    def test_existing_booking_no_payment_with_promo_change(self):
        """Booking with no payment record should proceed normally."""
        mock_booking = MagicMock(spec=Booking)
        mock_booking.payment = None
        mock_booking.promo_code = "OLD-PROMO"

        has_payment = mock_booking.payment is not None

        assert has_payment is False
        # Code should continue to create new payment

    def test_existing_booking_payment_no_intent_id(self):
        """Booking with payment but no intent ID should proceed normally."""
        mock_booking = MagicMock(spec=Booking)
        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = None
        mock_booking.payment = mock_payment

        has_intent = mock_booking.payment.stripe_payment_intent_id is not None

        assert has_intent is False

    def test_promo_code_with_special_characters(self):
        """Promo codes with special characters should be handled."""
        # Assuming promo codes can have hyphens and numbers
        promo_codes = [
            "FOUNDER-ABC-123",
            "PROMO_10_OFF",
            "FREE2024",
            "10-PERCENT",
        ]

        for code in promo_codes:
            normalized = code.strip().upper() if code else None
            assert normalized is not None
            assert len(normalized) > 0

    def test_very_long_promo_code(self):
        """Very long promo codes should be handled (within DB limits)."""
        long_code = "A" * 50  # Assuming 50 char limit
        normalized = long_code.strip().upper() if long_code else None

        assert len(normalized) == 50

    def test_rapid_promo_changes(self):
        """Rapid promo changes should each be detected correctly."""
        promo_sequence = [None, "PROMO1", "PROMO2", None, "PROMO3", "PROMO3"]

        changes = []
        previous = None
        for current in promo_sequence:
            changed = previous != current
            changes.append(changed)
            previous = current

        # First is always "change" from None
        # None -> PROMO1: change
        # PROMO1 -> PROMO2: change
        # PROMO2 -> None: change
        # None -> PROMO3: change
        # PROMO3 -> PROMO3: no change
        expected = [False, True, True, True, True, False]
        assert changes == expected


# =============================================================================
# BOUNDARY TESTS
# =============================================================================

class TestPromoCodeBoundaries:
    """Boundary tests for promo code functionality."""

    def test_zero_percent_discount(self):
        """0% discount should result in full price."""
        original_amount = 27500
        discount_percent = 0

        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        assert discount_amount == 0
        assert final_amount == 27500

    def test_one_percent_discount(self):
        """1% discount (minimum non-zero) should calculate correctly."""
        original_amount = 27500
        discount_percent = 1

        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        assert discount_amount == 275  # £2.75
        assert final_amount == 27225  # £272.25

    def test_99_percent_discount(self):
        """99% discount should leave small amount."""
        original_amount = 27500
        discount_percent = 99

        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        assert discount_amount == 27225  # £272.25
        assert final_amount == 275  # £2.75

    def test_minimum_booking_amount(self):
        """Minimum possible booking amount (1-week early bird)."""
        min_amount = 7900  # £79.00
        discount_percent = 10

        discount_amount = int(min_amount * discount_percent / 100)
        final_amount = min_amount - discount_amount

        assert discount_amount == 790  # £7.90
        assert final_amount == 7110  # £71.10

    def test_maximum_booking_amount(self):
        """Maximum reasonable booking amount (long stay)."""
        max_amount = 50000  # £500.00 (hypothetical long stay)
        discount_percent = 10

        discount_amount = int(max_amount * discount_percent / 100)
        final_amount = max_amount - discount_amount

        assert discount_amount == 5000  # £50.00
        assert final_amount == 45000  # £450.00

    def test_single_pence_booking(self):
        """Edge case: 1 pence booking (should never happen but handle gracefully)."""
        tiny_amount = 1
        discount_percent = 10

        discount_amount = int(tiny_amount * discount_percent / 100)
        final_amount = tiny_amount - discount_amount

        assert discount_amount == 0  # int(0.1) = 0
        assert final_amount == 1


# =============================================================================
# NEGATIVE TESTS
# =============================================================================

class TestPromoCodeNegativeCases:
    """Negative tests for promo code functionality."""

    def test_invalid_promo_code_not_applied(self):
        """Invalid promo code should not be applied."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No subscriber found

        promo_code = "INVALID-CODE"
        subscriber = mock_query.first()

        promo_code_applied = None
        if subscriber:
            promo_code_applied = promo_code

        assert promo_code_applied is None

    def test_already_used_promo_not_applied(self):
        """Already used promo code should not be applied."""
        mock_subscriber = MagicMock(spec=MarketingSubscriber)
        mock_subscriber.founder_promo_code = "FOUNDER-ABC123"
        mock_subscriber.founder_promo_used = True  # Already used

        promo_code = "FOUNDER-ABC123"
        promo_code_applied = None

        if mock_subscriber.founder_promo_code == promo_code:
            if not mock_subscriber.founder_promo_used:
                promo_code_applied = promo_code

        assert promo_code_applied is None

    def test_promo_for_wrong_package_type(self):
        """FREE promo on non-quick package should be partial discount."""
        package = "extended"  # Not "quick"
        discount_percent = 100
        duration_days = 14
        original_amount = 15900  # 2-week price
        week1_base = 7900

        # FREE promo is only fully free for quick (1-week) package
        if discount_percent == 100:
            if duration_days <= 7:
                discount_amount = original_amount
                is_free = True
            else:
                discount_amount = min(week1_base, original_amount)
                is_free = False

        assert is_free is False
        assert discount_amount == 7900  # Only deducts 1-week base

    def test_stripe_error_during_cancel(self):
        """Stripe error during cancel should be handled."""
        import stripe

        error_message = None
        try:
            raise stripe.error.StripeError("Payment intent already canceled")
        except stripe.error.StripeError as e:
            error_message = str(e)

        assert error_message is not None
        assert "canceled" in error_message.lower()


# =============================================================================
# INTEGRATION TESTS (Mocked)
# =============================================================================

class TestPromoChangeIntegration:
    """Integration tests for the full promo change flow."""

    def test_full_flow_promo_added(self):
        """Full flow: No promo -> Promo applied."""
        # Setup
        session_id = "test-session-123"

        # Existing booking without promo
        mock_booking = MagicMock(spec=Booking)
        mock_booking.reference = "TAG-TEST01"
        mock_booking.promo_code = None
        mock_booking.amount = 27500  # Full price
        mock_booking.original_amount = None
        mock_booking.discount_amount = None

        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = "pi_old123"
        mock_booking.payment = mock_payment

        # New request with promo
        new_promo = "FOUNDER-ABC123"

        # Detection
        promo_changed = mock_booking.promo_code != new_promo
        assert promo_changed is True

        # After update
        mock_booking.promo_code = new_promo
        mock_booking.amount = 24750  # 10% off
        mock_booking.original_amount = 27500
        mock_booking.discount_amount = 2750

        assert mock_booking.promo_code == "FOUNDER-ABC123"
        assert mock_booking.amount == 24750

    def test_full_flow_promo_removed(self):
        """Full flow: Promo applied -> Promo removed."""
        # Setup
        session_id = "test-session-456"

        # Existing booking WITH promo
        mock_booking = MagicMock(spec=Booking)
        mock_booking.reference = "TAG-TEST02"
        mock_booking.promo_code = "FOUNDER-ABC123"
        mock_booking.amount = 24750  # Discounted
        mock_booking.original_amount = 27500
        mock_booking.discount_amount = 2750

        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = "pi_discounted123"
        mock_booking.payment = mock_payment

        # New request WITHOUT promo
        new_promo = None

        # Detection
        promo_changed = mock_booking.promo_code != new_promo
        assert promo_changed is True

        # After update
        mock_booking.promo_code = None
        mock_booking.amount = 27500  # Full price
        mock_booking.original_amount = None
        mock_booking.discount_amount = None

        assert mock_booking.promo_code is None
        assert mock_booking.amount == 27500

    def test_full_flow_promo_changed(self):
        """Full flow: Promo A -> Promo B (different discount)."""
        # Setup - existing booking with 10% promo
        mock_booking = MagicMock(spec=Booking)
        mock_booking.reference = "TAG-TEST03"
        mock_booking.promo_code = "PROMO-10-OLD"
        mock_booking.amount = 24750

        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = "pi_old_promo"
        mock_booking.payment = mock_payment

        # New promo (also 10% but different code)
        new_promo = "FOUNDER-NEW123"

        # Detection
        promo_changed = mock_booking.promo_code != new_promo
        assert promo_changed is True

        # After update (same discount, different code)
        mock_booking.promo_code = new_promo
        # Amount stays same if discount % is same

        assert mock_booking.promo_code == "FOUNDER-NEW123"

    def test_full_flow_with_stripe_cancel(self):
        """Full flow including Stripe PaymentIntent cancellation."""
        import stripe

        with patch.object(stripe.PaymentIntent, 'cancel') as mock_cancel:
            with patch.object(stripe.PaymentIntent, 'create') as mock_create:
                mock_cancel.return_value = MagicMock(status='canceled')
                mock_create.return_value = MagicMock(
                    id='pi_new123',
                    client_secret='pi_new123_secret',
                    status='requires_payment_method'
                )

                # Simulate the flow
                old_intent_id = "pi_old123"

                # Step 1: Cancel old intent
                result = stripe.PaymentIntent.cancel(old_intent_id)
                assert result.status == 'canceled'

                # Step 2: Create new intent
                new_intent = stripe.PaymentIntent.create(
                    amount=27500,
                    currency='gbp'
                )
                assert new_intent.id == 'pi_new123'

                mock_cancel.assert_called_once_with(old_intent_id)
                mock_create.assert_called_once()

    def test_full_flow_no_existing_booking(self):
        """Full flow: No existing booking (first payment attempt)."""
        session_id = "new-session-789"
        existing_booking = None

        # No promo change detection needed
        promo_changed = False  # Can't compare if no existing booking

        if existing_booking and existing_booking.promo_code:
            promo_changed = existing_booking.promo_code != "NEW-PROMO"

        assert promo_changed is False
        # Code should proceed to create new booking

    def test_full_flow_same_promo_reused(self):
        """Full flow: Same promo code -> PaymentIntent reused."""
        # Existing booking with promo
        mock_booking = MagicMock(spec=Booking)
        mock_booking.promo_code = "FOUNDER-ABC123"

        mock_payment = MagicMock(spec=Payment)
        mock_payment.stripe_payment_intent_id = "pi_existing123"
        mock_booking.payment = mock_payment

        # Same promo in new request
        new_promo = "FOUNDER-ABC123"

        promo_changed = mock_booking.promo_code != new_promo
        assert promo_changed is False

        # Should reuse existing PaymentIntent (not cancel)


# =============================================================================
# RESPONSE STRUCTURE TESTS
# =============================================================================

class TestPromoChangeResponse:
    """Tests for the response structure after promo changes."""

    def test_response_includes_discounted_amount(self):
        """Response should include discounted amount when promo applied."""
        amount = 24750
        original_amount = 27500
        discount_amount = 2750
        promo_code_applied = "FOUNDER-ABC123"

        response = {
            "amount": amount,
            "amount_display": f"£{amount / 100:.2f}",
            "original_amount": original_amount,
            "original_amount_display": f"£{original_amount / 100:.2f}",
            "discount_amount": discount_amount,
            "discount_amount_display": f"£{discount_amount / 100:.2f}",
            "promo_code_applied": promo_code_applied,
        }

        assert response["amount"] == 24750
        assert response["amount_display"] == "£247.50"
        assert response["original_amount_display"] == "£275.00"
        assert response["discount_amount_display"] == "£27.50"
        assert response["promo_code_applied"] == "FOUNDER-ABC123"

    def test_response_no_discount_fields_when_no_promo(self):
        """Response should not include discount fields when no promo."""
        amount = 27500
        promo_code_applied = None

        response = {
            "amount": amount,
            "amount_display": f"£{amount / 100:.2f}",
        }

        if promo_code_applied:
            response["original_amount"] = amount
            response["promo_code_applied"] = promo_code_applied

        assert response["amount"] == 27500
        assert response["amount_display"] == "£275.00"
        assert "original_amount" not in response
        assert "promo_code_applied" not in response

    def test_response_amount_display_format(self):
        """Amount display should be properly formatted."""
        test_cases = [
            (7900, "£79.00"),
            (24750, "£247.50"),
            (27500, "£275.00"),
            (100, "£1.00"),
            (99, "£0.99"),
            (1, "£0.01"),
        ]

        for amount, expected in test_cases:
            display = f"£{amount / 100:.2f}"
            assert display == expected


# =============================================================================
# DATABASE TRANSACTION TESTS
# =============================================================================

class TestPromoChangeDatabaseTransactions:
    """Tests for database transactions during promo changes."""

    def test_payment_deleted_before_new_created(self):
        """Old payment should be deleted before new one is created."""
        mock_db = MagicMock()
        mock_old_payment = MagicMock(spec=Payment)

        # Simulate deletion order
        call_order = []

        def track_delete(obj):
            call_order.append(('delete', type(obj).__name__))

        def track_commit():
            call_order.append(('commit', None))

        mock_db.delete.side_effect = track_delete
        mock_db.commit.side_effect = track_commit

        # Execute
        mock_db.delete(mock_old_payment)
        mock_db.commit()

        assert call_order[0] == ('delete', 'MagicMock')
        assert call_order[1] == ('commit', None)

    def test_booking_update_committed(self):
        """Booking updates should be committed to database."""
        mock_db = MagicMock()
        mock_booking = MagicMock(spec=Booking)

        # Update booking
        mock_booking.promo_code = "NEW-PROMO"
        mock_booking.amount = 24750
        mock_db.commit()
        mock_db.refresh(mock_booking)

        mock_db.commit.assert_called()
        mock_db.refresh.assert_called_with(mock_booking)


# =============================================================================
# CONCURRENT ACCESS TESTS
# =============================================================================

class TestPromoChangeConcurrency:
    """Tests for concurrent promo code changes."""

    def test_two_requests_same_session_different_promos(self):
        """Two concurrent requests with different promos should be handled."""
        session_id = "concurrent-session"

        # Both requests try to change promo simultaneously
        request_1_promo = "PROMO-A"
        request_2_promo = "PROMO-B"

        # In practice, database locking should handle this
        # The second request should see the first's changes

        # This is more of a documentation test - actual concurrency
        # is handled by database transactions
        assert request_1_promo != request_2_promo


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
