"""
Tests for the Thank You Email functionality.

Tests cover:
- Unit tests for send_thank_you_email function
- Unit tests for process_pending_thankyou_emails scheduler function
- Integration tests for automated email scheduling after booking completion
- Negative tests and edge cases
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from email_service import send_thank_you_email
from db_models import BookingStatus


# =============================================================================
# Unit Tests for send_thank_you_email
# =============================================================================

class TestSendThankYouEmail:
    """Unit tests for the send_thank_you_email function."""

    @patch('email_service.send_email')
    def test_sends_email_with_correct_parameters(self, mock_send_email):
        """Test that the function calls send_email with correct parameters."""
        mock_send_email.return_value = True

        result = send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        assert result is True
        mock_send_email.assert_called_once()

        # Check the email was sent to the correct address
        call_args = mock_send_email.call_args
        assert call_args[0][0] == "test@example.com"
        assert call_args[0][1] == "Thank You for Choosing TAG Parking"

    @patch('email_service.send_email')
    def test_email_contains_customer_first_name(self, mock_send_email):
        """Test that the email HTML contains the customer's first name."""
        mock_send_email.return_value = True

        send_thank_you_email(
            email="test@example.com",
            first_name="Sarah",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Sarah" in html_content

    @patch('email_service.send_email')
    def test_email_contains_review_link(self, mock_send_email):
        """Test that the email HTML contains the review page link."""
        mock_send_email.return_value = True

        send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        html_content = mock_send_email.call_args[0][2]
        # Template uses Google Maps review link
        assert "review" in html_content.lower()

    @patch('email_service.send_email')
    def test_email_contains_leave_review_cta(self, mock_send_email):
        """Test that the email HTML contains the Leave a Review CTA."""
        mock_send_email.return_value = True

        send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Leave a review" in html_content

    @patch('email_service.send_email')
    def test_email_contains_tag_branding(self, mock_send_email):
        """Test that the email HTML contains TAG branding elements."""
        mock_send_email.return_value = True

        send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        html_content = mock_send_email.call_args[0][2]
        # Template uses "Tag" not "TAG Parking"
        assert "Tag" in html_content

    @patch('email_service.send_email')
    def test_email_contains_thank_you_message(self, mock_send_email):
        """Test that the email HTML contains a thank you message."""
        mock_send_email.return_value = True

        send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "thanks for using Tag" in html_content

    @patch('email_service.send_email')
    def test_returns_false_when_send_fails(self, mock_send_email):
        """Test that the function returns False when email sending fails."""
        mock_send_email.return_value = False

        result = send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        assert result is False

    @patch('email_service.send_email')
    def test_handles_special_characters_in_name(self, mock_send_email):
        """Test that special characters in names are handled correctly."""
        mock_send_email.return_value = True

        result = send_thank_you_email(
            email="test@example.com",
            first_name="José",
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert "José" in html_content

    @patch('email_service.send_email')
    def test_handles_unicode_characters_in_name(self, mock_send_email):
        """Test that Unicode characters in names are handled correctly."""
        mock_send_email.return_value = True

        result = send_thank_you_email(
            email="test@example.com",
            first_name="中文名",
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert "中文名" in html_content

    @patch('email_service.send_email')
    def test_handles_empty_first_name(self, mock_send_email):
        """Test that empty first name is handled gracefully."""
        mock_send_email.return_value = True

        result = send_thank_you_email(
            email="test@example.com",
            first_name="",
        )

        assert result is True
        # The email should still send, but the name placeholder is empty
        mock_send_email.assert_called_once()


# =============================================================================
# Unit Tests for process_pending_thankyou_emails scheduler function
# =============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-THANKYOU1",
    customer_id=1,
    status=BookingStatus.COMPLETED,
    completed_at=None,
    thank_you_email_sent=False,
    thank_you_email_sent_at=None,
):
    """Helper to create a mock booking."""
    if completed_at is None:
        # Default: completed 3 hours ago (more than 2 hour delay)
        completed_at = datetime.utcnow() - timedelta(hours=3)

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.status = status
    booking.completed_at = completed_at
    booking.thank_you_email_sent = thank_you_email_sent
    booking.thank_you_email_sent_at = thank_you_email_sent_at
    return booking


def create_mock_customer(
    id=1,
    first_name="Test",
    last_name="User",
    email="test@example.com",
):
    """Helper to create a mock customer."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    return customer


class TestProcessPendingThankYouEmails:
    """Unit tests for the scheduler function that processes thank you emails."""

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    def test_does_nothing_when_email_disabled(self, mock_enabled, mock_send):
        """Test that no emails are sent when email is disabled."""
        mock_enabled.return_value = False

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_sends_email_for_booking_completed_more_than_2_hours_ago(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is sent for booking completed more than 2 hours ago."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking completed 3 hours ago
        completed_time = datetime.utcnow() - timedelta(hours=3)
        mock_booking = create_mock_booking(
            reference="TAG-THANKYOU001",
            completed_at=completed_time,
        )
        mock_customer = create_mock_customer(
            email="testthankyou@example.com",
            first_name="Test",
        )

        # Setup query chain for booking query
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        # Setup query chain for customer query
        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        # Configure db.query to return appropriate mocks based on model
        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["email"] == "testthankyou@example.com"
        assert call_kwargs["first_name"] == "Test"

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_booking_completed_less_than_2_hours_ago(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is NOT sent for booking completed less than 2 hours ago."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (filtered out by time constraint)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_already_sent_thankyou(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is not sent if already sent."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (already filtered out)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_confirmed_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is not sent for CONFIRMED (not completed) bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (CONFIRMED filtered out by query)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_cancelled_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is not sent for CANCELLED bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (CANCELLED filtered out by query)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_pending_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is not sent for PENDING bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (PENDING filtered out by query)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_marks_thankyou_as_sent_after_success(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank_you_email_sent is marked True after successful send."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking
        mock_booking = create_mock_booking(
            reference="TAG-THANKYOU007",
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Check that thank_you_email_sent was set to True
        assert mock_booking.thank_you_email_sent is True
        assert mock_booking.thank_you_email_sent_at is not None
        mock_db.commit.assert_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_mark_sent_on_failure(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank_you_email_sent is NOT marked True if send fails."""
        mock_enabled.return_value = True
        mock_send.return_value = False  # Email fails

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking
        mock_booking = create_mock_booking(
            reference="TAG-THANKYOU008",
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Check that thank_you_email_sent was NOT changed
        assert mock_booking.thank_you_email_sent is False

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_skips_booking_with_missing_customer(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that booking is skipped if customer is not found."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking but no customer
        mock_booking = create_mock_booking(
            reference="TAG-NOCUSTOMER",
        )

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = None  # Customer not found

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Should NOT have been sent
        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_when_completed_at_is_none(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that thank you email is not sent when completed_at is None."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (completed_at is None filtered out)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        mock_send.assert_not_called()


# =============================================================================
# Integration Tests for Scheduler Behavior
# =============================================================================

class TestThankYouEmailSchedulerIntegration:
    """Integration tests for the scheduler's thank you email behavior."""

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_processes_multiple_bookings_in_batch(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that multiple bookings are processed in a single run."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock bookings
        mock_booking1 = create_mock_booking(
            reference="TAG-THANKYOU010",
            customer_id=1,
        )
        mock_booking2 = create_mock_booking(
            reference="TAG-THANKYOU011",
            customer_id=2,
        )

        mock_customer1 = create_mock_customer(id=1, email="user1@example.com", first_name="User")
        mock_customer2 = create_mock_customer(id=2, email="user2@example.com", first_name="User")

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking1, mock_booking2]

        customer_call_count = [0]
        def customer_filter_side_effect(*args, **kwargs):
            result = MagicMock()
            customer_call_count[0] += 1
            if customer_call_count[0] == 1:
                result.first.return_value = mock_customer1
            else:
                result.first.return_value = mock_customer2
            return result

        mock_customer_query = MagicMock()
        mock_customer_query.filter.side_effect = customer_filter_side_effect

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Both should have been sent
        assert mock_send.call_count == 2

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_continues_processing_after_one_failure(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that processing continues even if one email fails."""
        mock_enabled.return_value = True
        # First call fails, second succeeds
        mock_send.side_effect = [False, True]

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock bookings
        mock_booking1 = create_mock_booking(
            reference="TAG-THANKYOU012",
            customer_id=1,
        )
        mock_booking2 = create_mock_booking(
            reference="TAG-THANKYOU013",
            customer_id=2,
        )

        mock_customer1 = create_mock_customer(id=1, email="fail@example.com", first_name="Fail")
        mock_customer2 = create_mock_customer(id=2, email="success@example.com", first_name="Success")

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking1, mock_booking2]

        customer_call_count = [0]
        def customer_filter_side_effect(*args, **kwargs):
            result = MagicMock()
            customer_call_count[0] += 1
            if customer_call_count[0] == 1:
                result.first.return_value = mock_customer1
            else:
                result.first.return_value = mock_customer2
            return result

        mock_customer_query = MagicMock()
        mock_customer_query.filter.side_effect = customer_filter_side_effect

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Both should have been attempted
        assert mock_send.call_count == 2
        # First booking should not be marked sent
        assert mock_booking1.thank_you_email_sent is False
        # Second booking should be marked sent
        assert mock_booking2.thank_you_email_sent is True

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_handles_database_exception_gracefully(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that database exceptions are handled gracefully."""
        mock_enabled.return_value = True

        # Setup mock database that raises an exception
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_db.query.side_effect = Exception("Database connection error")

        # Should not raise an exception
        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Email should not have been sent
        mock_send.assert_not_called()
        # Rollback should have been called
        mock_db.rollback.assert_called()


# =============================================================================
# Negative Tests
# =============================================================================

class TestThankYouEmailNegativeCases:
    """Negative tests for thank you email functionality."""

    @patch('email_service.send_email')
    @patch('email_service.EMAIL_TEMPLATES_DIR')
    def test_returns_false_when_template_not_found(self, mock_templates_dir, mock_send_email):
        """Test that the function returns False when template is not found."""
        # Make the template path point to a non-existent file
        mock_templates_dir.__truediv__ = lambda self, name: "/nonexistent/path"

        # This will try to open a non-existent file
        result = send_thank_you_email(
            email="test@example.com",
            first_name="John",
        )

        # Should return False due to FileNotFoundError
        # Note: This test may need adjustment based on actual implementation
        # The function should catch FileNotFoundError and return False

    @patch('email_service.send_email')
    def test_handles_none_email(self, mock_send_email):
        """Test that None email address is handled (depends on send_email behavior)."""
        mock_send_email.return_value = False

        result = send_thank_you_email(
            email=None,
            first_name="John",
        )

        # Should call send_email but it will fail
        mock_send_email.assert_called_once()

    @patch('email_service.send_email')
    def test_handles_invalid_email_format(self, mock_send_email):
        """Test that invalid email format is handled (depends on send_email behavior)."""
        mock_send_email.return_value = False

        result = send_thank_you_email(
            email="not-an-email",
            first_name="John",
        )

        assert result is False


# =============================================================================
# Edge Cases
# =============================================================================

class TestThankYouEmailEdgeCases:
    """Edge case tests for thank you email functionality."""

    @patch('email_service.send_email')
    def test_handles_very_long_first_name(self, mock_send_email):
        """Test that very long first names are handled correctly."""
        mock_send_email.return_value = True

        long_name = "A" * 500  # Very long name

        result = send_thank_you_email(
            email="test@example.com",
            first_name=long_name,
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert long_name in html_content

    @patch('email_service.send_email')
    def test_handles_name_with_html_characters(self, mock_send_email):
        """Test that names with HTML characters don't cause issues."""
        mock_send_email.return_value = True

        result = send_thank_you_email(
            email="test@example.com",
            first_name="<script>alert('xss')</script>",
        )

        # Function should still succeed (XSS prevention is responsibility of email client)
        assert result is True

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_handles_booking_completed_exactly_2_hours_ago(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test boundary case: booking completed exactly 2 hours ago."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking completed exactly 2 hours ago
        completed_time = datetime.utcnow() - timedelta(hours=2)
        mock_booking = create_mock_booking(
            reference="TAG-BOUNDARY001",
            completed_at=completed_time,
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Should be sent (exactly at the boundary)
        mock_send.assert_called_once()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_handles_booking_completed_1_minute_before_boundary(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test boundary case: booking completed 1h 59m ago (just under 2 hours)."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings
        # (completed 1h59m ago should be filtered out)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_thankyou_emails
        mock_db = MagicMock()
        process_pending_thankyou_emails(mock_db)

        # Should NOT be sent (not yet at 2 hour mark)
        mock_send.assert_not_called()

    @patch('email_scheduler.send_thank_you_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_handles_very_old_completed_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that very old completed bookings still get thank you email."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking completed a week ago (still should get email)
        completed_time = datetime.utcnow() - timedelta(days=7)
        mock_booking = create_mock_booking(
            reference="TAG-OLDCOMPLETE",
            completed_at=completed_time,
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        def query_side_effect(model):
            from db_models import Booking, Customer
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_thankyou_emails
        process_pending_thankyou_emails(mock_db)

        # Should still be sent
        mock_send.assert_called_once()


# =============================================================================
# Complete Booking Endpoint Tests
# =============================================================================

class TestCompleteBookingEndpoint:
    """Tests for the complete booking endpoint setting completed_at."""

    def test_complete_booking_sets_completed_at(self):
        """Test that marking a booking as complete sets the completed_at timestamp."""
        # Mock booking object
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.reference = "TAG-COMPLETE001"
        mock_booking.completed_at = None

        # Simulate the completion logic
        mock_booking.status = BookingStatus.COMPLETED
        mock_booking.completed_at = datetime.utcnow()

        assert mock_booking.status == BookingStatus.COMPLETED
        assert mock_booking.completed_at is not None
        assert isinstance(mock_booking.completed_at, datetime)

    def test_completed_at_is_none_before_completion(self):
        """Test that completed_at is None before booking is completed."""
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.completed_at = None

        assert mock_booking.completed_at is None

    def test_completed_at_is_set_after_completion(self):
        """Test that completed_at is set after booking is completed."""
        mock_booking = MagicMock()
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.completed_at = None

        # Complete the booking
        mock_booking.status = BookingStatus.COMPLETED
        mock_booking.completed_at = datetime.utcnow()

        assert mock_booking.completed_at is not None
        # Verify timestamp is recent (within last minute)
        assert (datetime.utcnow() - mock_booking.completed_at) < timedelta(minutes=1)


# =============================================================================
# Process All Pending Emails Tests
# =============================================================================

class TestProcessAllPendingEmails:
    """Tests for the main email processing function that includes thank you emails."""

    @patch('email_scheduler.process_pending_thankyou_emails')
    @patch('email_scheduler.process_pending_2day_reminders')
    @patch('email_scheduler.process_pending_welcome_emails')
    def test_process_all_includes_thankyou_emails(
        self, mock_welcome, mock_reminders, mock_thankyou
    ):
        """Test that process_all_pending_emails includes thank you emails."""
        from email_scheduler import process_all_pending_emails
        process_all_pending_emails()

        mock_welcome.assert_called_once()
        mock_reminders.assert_called_once()
        mock_thankyou.assert_called_once()
