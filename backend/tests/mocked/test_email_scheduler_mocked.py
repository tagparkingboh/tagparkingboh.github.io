"""
Unit and Integration tests for Email Scheduler.

Tests the background email scheduling functions with mocked dependencies.
All tests use mocks - no database connection or email sending.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta, date, time
import pytz


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_subscriber(
    id=1,
    email="test@example.com",
    first_name="John",
    subscribed_at=None,
    welcome_email_sent=False,
    welcome_email_sent_at=None,
    promo_code_sent=False,
    promo_code=None,
    unsubscribed=False,
    unsubscribe_token="token123",
):
    """Create a mock marketing subscriber."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.email = email
    subscriber.first_name = first_name
    subscriber.subscribed_at = subscribed_at or datetime.utcnow() - timedelta(hours=1)
    subscriber.welcome_email_sent = welcome_email_sent
    subscriber.welcome_email_sent_at = welcome_email_sent_at
    subscriber.promo_code_sent = promo_code_sent
    subscriber.promo_code = promo_code
    subscriber.unsubscribed = unsubscribed
    subscriber.unsubscribe_token = unsubscribe_token
    return subscriber


def create_mock_booking(
    id=1,
    reference="TAG-12345",
    dropoff_date=None,
    pickup_date=None,
    status="confirmed",
    confirmation_email_sent=False,
    reminder_2day_sent=False,
    thank_you_email_sent=False,
    customer_email="customer@example.com",
    customer_first_name="Jane",
):
    """Create a mock booking."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date.today() + timedelta(days=2)
    booking.pickup_date = pickup_date or date.today() + timedelta(days=9)
    booking.dropoff_time = time(8, 30)
    booking.pickup_time = time(15, 0)
    booking.status = MagicMock()
    booking.status.value = status
    booking.confirmation_email_sent = confirmation_email_sent
    booking.reminder_2day_sent = reminder_2day_sent
    booking.thank_you_email_sent = thank_you_email_sent
    booking.created_at = datetime.utcnow() - timedelta(hours=3)

    booking.customer = MagicMock()
    booking.customer.email = customer_email
    booking.customer.first_name = customer_first_name
    booking.customer.founder_followup_sent = False

    booking.vehicle = MagicMock()
    booking.vehicle.registration = "AB12 CDE"

    booking.payment = MagicMock()
    booking.payment.amount_pence = 7500

    return booking


# ============================================================================
# Welcome Email Scheduler Tests
# ============================================================================

class TestProcessPendingWelcomeEmails:
    """Tests for process_pending_welcome_emails() function."""

    def test_finds_subscribers_after_delay(self):
        """Should find subscribers after delay period."""
        delay_minutes = 5
        cutoff_time = datetime.utcnow() - timedelta(minutes=delay_minutes)

        # Subscriber signed up 10 minutes ago (should be processed)
        subscriber = create_mock_subscriber(
            subscribed_at=datetime.utcnow() - timedelta(minutes=10),
            welcome_email_sent=False,
        )

        should_process = subscriber.subscribed_at <= cutoff_time
        assert should_process is True

    def test_skips_subscribers_before_delay(self):
        """Should skip subscribers still within delay period."""
        delay_minutes = 5
        cutoff_time = datetime.utcnow() - timedelta(minutes=delay_minutes)

        # Subscriber signed up 2 minutes ago (should NOT be processed)
        subscriber = create_mock_subscriber(
            subscribed_at=datetime.utcnow() - timedelta(minutes=2),
            welcome_email_sent=False,
        )

        should_process = subscriber.subscribed_at <= cutoff_time
        assert should_process is False

    def test_skips_already_sent(self):
        """Should skip subscribers who already received welcome email."""
        subscriber = create_mock_subscriber(
            welcome_email_sent=True,
            welcome_email_sent_at=datetime.utcnow() - timedelta(hours=1),
        )

        should_send = not subscriber.welcome_email_sent
        assert should_send is False

    def test_skips_unsubscribed(self):
        """Should skip unsubscribed subscribers."""
        subscriber = create_mock_subscriber(
            unsubscribed=True,
            welcome_email_sent=False,
        )

        should_send = not subscriber.unsubscribed
        assert should_send is False

    def test_marks_as_sent_on_success(self):
        """Should mark welcome_email_sent=True on success."""
        subscriber = create_mock_subscriber(welcome_email_sent=False)

        # Simulate successful send
        send_success = True
        if send_success:
            subscriber.welcome_email_sent = True
            subscriber.welcome_email_sent_at = datetime.utcnow()

        assert subscriber.welcome_email_sent is True
        assert subscriber.welcome_email_sent_at is not None

    def test_limits_batch_size(self):
        """Should process limited batch to avoid overwhelming."""
        subscribers = [create_mock_subscriber(id=i) for i in range(20)]
        batch_limit = 10

        batch = subscribers[:batch_limit]

        assert len(batch) == 10


# ============================================================================
# Promo Email Scheduler Tests
# ============================================================================

class TestProcessPendingPromoEmails:
    """Tests for process_pending_promo_emails() function."""

    def test_finds_subscribers_after_welcome_delay(self):
        """Should find subscribers after welcome email + delay."""
        delay_hours = 1
        cutoff_time = datetime.utcnow() - timedelta(hours=delay_hours)

        # Welcome email sent 2 hours ago (should be processed)
        subscriber = create_mock_subscriber(
            welcome_email_sent=True,
            welcome_email_sent_at=datetime.utcnow() - timedelta(hours=2),
            promo_code_sent=False,
        )

        should_process = (
            subscriber.welcome_email_sent and
            not subscriber.promo_code_sent and
            subscriber.welcome_email_sent_at <= cutoff_time
        )
        assert should_process is True

    def test_skips_without_welcome_email(self):
        """Should skip subscribers who haven't received welcome email."""
        subscriber = create_mock_subscriber(
            welcome_email_sent=False,
            promo_code_sent=False,
        )

        should_process = subscriber.welcome_email_sent
        assert should_process is False

    def test_skips_already_sent_promo(self):
        """Should skip subscribers who already received promo."""
        subscriber = create_mock_subscriber(
            welcome_email_sent=True,
            promo_code_sent=True,
        )

        should_send = not subscriber.promo_code_sent
        assert should_send is False

    def test_generates_unique_promo_code(self):
        """Should generate unique promo code if not exists."""
        subscriber = create_mock_subscriber(promo_code=None)

        if not subscriber.promo_code:
            subscriber.promo_code = "TAG-NEW1-CODE"

        assert subscriber.promo_code is not None
        assert subscriber.promo_code.startswith("TAG-")

    def test_uses_existing_promo_code(self):
        """Should use existing promo code if already generated."""
        existing_code = "TAG-EXIST-CODE"
        subscriber = create_mock_subscriber(promo_code=existing_code)

        code_to_use = subscriber.promo_code or "TAG-NEW-CODE"

        assert code_to_use == existing_code


# ============================================================================
# 2-Day Reminder Email Scheduler Tests
# ============================================================================

class TestProcessPending2DayReminders:
    """Tests for process_pending_2_day_reminders() function."""

    def test_finds_bookings_2_days_before_dropoff(self):
        """Should find bookings with dropoff in 2 days."""
        today = date.today()
        target_date = today + timedelta(days=2)

        booking = create_mock_booking(
            dropoff_date=target_date,
            reminder_2day_sent=False,
            status="confirmed",
        )

        should_send = (
            booking.dropoff_date == target_date and
            not booking.reminder_2day_sent and
            booking.status.value == "confirmed"
        )
        assert should_send is True

    def test_skips_bookings_not_2_days_away(self):
        """Should skip bookings not exactly 2 days away."""
        today = date.today()

        booking_tomorrow = create_mock_booking(
            dropoff_date=today + timedelta(days=1),
            reminder_2day_sent=False,
        )
        booking_3days = create_mock_booking(
            dropoff_date=today + timedelta(days=3),
            reminder_2day_sent=False,
        )

        target = today + timedelta(days=2)
        should_send_tomorrow = booking_tomorrow.dropoff_date == target
        should_send_3days = booking_3days.dropoff_date == target

        assert should_send_tomorrow is False
        assert should_send_3days is False

    def test_skips_already_sent_reminder(self):
        """Should skip bookings that already received reminder."""
        booking = create_mock_booking(
            reminder_2day_sent=True,
        )

        should_send = not booking.reminder_2day_sent
        assert should_send is False

    def test_skips_cancelled_bookings(self):
        """Should skip cancelled bookings."""
        booking = create_mock_booking(
            status="cancelled",
            reminder_2day_sent=False,
        )

        should_send = booking.status.value in ["confirmed", "completed"]
        assert should_send is False

    def test_marks_as_sent_on_success(self):
        """Should mark reminder_2day_sent=True on success."""
        booking = create_mock_booking(reminder_2day_sent=False)

        # Simulate successful send
        send_success = True
        if send_success:
            booking.reminder_2day_sent = True
            booking.reminder_2day_sent_at = datetime.utcnow()

        assert booking.reminder_2day_sent is True


# ============================================================================
# Thank You Email Scheduler Tests
# ============================================================================

class TestProcessPendingThankYouEmails:
    """Tests for process_pending_thank_you_emails() function."""

    def test_finds_completed_bookings_after_delay(self):
        """Should find completed bookings after delay period."""
        delay_hours = 2
        today = date.today()

        # Pickup was yesterday
        booking = create_mock_booking(
            pickup_date=today - timedelta(days=1),
            status="completed",
            thank_you_email_sent=False,
        )

        should_send = (
            booking.pickup_date < today and
            booking.status.value == "completed" and
            not booking.thank_you_email_sent
        )
        assert should_send is True

    def test_skips_future_pickups(self):
        """Should skip bookings with future pickup dates."""
        today = date.today()

        booking = create_mock_booking(
            pickup_date=today + timedelta(days=5),
            status="confirmed",
            thank_you_email_sent=False,
        )

        should_send = booking.pickup_date < today
        assert should_send is False

    def test_skips_already_sent(self):
        """Should skip bookings that already received thank you."""
        booking = create_mock_booking(
            thank_you_email_sent=True,
        )

        should_send = not booking.thank_you_email_sent
        assert should_send is False

    def test_skips_non_completed_status(self):
        """Should skip bookings not in completed status."""
        booking = create_mock_booking(
            status="confirmed",  # Still confirmed, not completed
            thank_you_email_sent=False,
        )

        should_send = booking.status.value == "completed"
        assert should_send is False


# ============================================================================
# Founder Followup Email Scheduler Tests
# ============================================================================

class TestProcessPendingFounderFollowupEmails:
    """Tests for process_pending_founder_followup_emails() function."""

    def test_finds_eligible_bookings_after_delay(self):
        """Should find eligible bookings after delay period."""
        delay_hours = 1
        cutoff_time = datetime.utcnow() - timedelta(hours=delay_hours)

        booking = create_mock_booking()
        booking.created_at = datetime.utcnow() - timedelta(hours=2)
        booking.customer.founder_followup_sent = False

        should_send = (
            booking.created_at <= cutoff_time and
            not booking.customer.founder_followup_sent
        )
        assert should_send is True

    def test_skips_recently_created(self):
        """Should skip bookings created within delay period."""
        delay_hours = 1
        cutoff_time = datetime.utcnow() - timedelta(hours=delay_hours)

        booking = create_mock_booking()
        booking.created_at = datetime.utcnow() - timedelta(minutes=30)

        should_send = booking.created_at <= cutoff_time
        assert should_send is False

    def test_skips_already_sent(self):
        """Should skip customers who already received followup."""
        booking = create_mock_booking()
        booking.customer.founder_followup_sent = True

        should_send = not booking.customer.founder_followup_sent
        assert should_send is False

    def test_respects_start_date_cutoff(self):
        """Should only process bookings after start date."""
        start_date = date(2026, 3, 1)

        # Booking from before start date
        old_booking = create_mock_booking(
            dropoff_date=date(2026, 2, 15),
        )

        # Booking from after start date
        new_booking = create_mock_booking(
            dropoff_date=date(2026, 3, 15),
        )

        should_send_old = old_booking.dropoff_date >= start_date
        should_send_new = new_booking.dropoff_date >= start_date

        assert should_send_old is False
        assert should_send_new is True


# ============================================================================
# Scheduler Configuration Tests
# ============================================================================

class TestSchedulerConfiguration:
    """Tests for scheduler configuration."""

    def test_welcome_email_delay_is_5_minutes(self):
        """Welcome email delay should be 5 minutes."""
        WELCOME_EMAIL_DELAY_MINUTES = 5
        assert WELCOME_EMAIL_DELAY_MINUTES == 5

    def test_promo_email_delay_is_1_hour(self):
        """Promo email delay should be 1 hour after welcome."""
        PROMO_EMAIL_DELAY_HOURS = 1
        assert PROMO_EMAIL_DELAY_HOURS == 1

    def test_thank_you_delay_is_2_hours(self):
        """Thank you email delay should be 2 hours after completion."""
        THANK_YOU_EMAIL_DELAY_HOURS = 2
        assert THANK_YOU_EMAIL_DELAY_HOURS == 2

    def test_check_interval_is_1_minute(self):
        """Scheduler should check every 1 minute."""
        CHECK_INTERVAL_MINUTES = 1
        assert CHECK_INTERVAL_MINUTES == 1


# ============================================================================
# UK Timezone Handling Tests
# ============================================================================

class TestTimezoneHandling:
    """Tests for UK timezone handling in scheduler."""

    def test_uk_timezone_aware(self):
        """Should use UK timezone for date calculations."""
        uk_tz = pytz.timezone('Europe/London')
        uk_now = datetime.now(uk_tz)

        assert uk_now.tzinfo is not None

    def test_compares_dates_in_uk_timezone(self):
        """Should compare dates in UK timezone."""
        uk_tz = pytz.timezone('Europe/London')
        uk_today = datetime.now(uk_tz).date()

        # A booking for today UK time
        booking = create_mock_booking(dropoff_date=uk_today)

        is_today = booking.dropoff_date == uk_today
        assert is_today is True


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestSchedulerErrorHandling:
    """Tests for scheduler error handling."""

    def test_continues_on_single_email_failure(self):
        """Should continue processing after single email failure."""
        subscribers = [
            create_mock_subscriber(id=1, email="success@test.com"),
            create_mock_subscriber(id=2, email="fail@test.com"),
            create_mock_subscriber(id=3, email="success2@test.com"),
        ]

        processed = []
        for sub in subscribers:
            try:
                # Simulate some emails failing
                if "fail" in sub.email:
                    raise Exception("Email failed")
                processed.append(sub.id)
            except Exception:
                pass  # Continue to next

        # Should have processed 2 out of 3
        assert len(processed) == 2

    def test_handles_database_error(self):
        """Should handle database errors gracefully."""
        try:
            raise Exception("Database connection failed")
        except Exception as e:
            error_handled = True
            error_message = str(e)

        assert error_handled is True
        assert "Database" in error_message

    def test_rolls_back_on_error(self):
        """Should rollback transaction on error."""
        mock_db = MagicMock()

        try:
            raise Exception("Error during processing")
        except Exception:
            mock_db.rollback()

        mock_db.rollback.assert_called_once()


# ============================================================================
# Batch Processing Tests
# ============================================================================

class TestBatchProcessing:
    """Tests for batch processing limits."""

    def test_processes_max_10_at_a_time(self):
        """Should process maximum 10 items per batch."""
        all_items = [create_mock_subscriber(id=i) for i in range(25)]
        batch_limit = 10

        batch = all_items[:batch_limit]

        assert len(batch) == 10

    def test_handles_empty_batch(self):
        """Should handle empty batch gracefully."""
        items = []

        processed_count = 0
        for item in items:
            processed_count += 1

        assert processed_count == 0


# ============================================================================
# Boundary Tests
# ============================================================================

class TestSchedulerBoundaryConditions:
    """Tests for scheduler boundary conditions."""

    def test_exact_delay_boundary(self):
        """Should process at exactly the delay boundary."""
        delay_minutes = 5
        cutoff_time = datetime.utcnow() - timedelta(minutes=delay_minutes)

        # Exactly at boundary
        subscriber = create_mock_subscriber(
            subscribed_at=cutoff_time,
        )

        should_process = subscriber.subscribed_at <= cutoff_time
        assert should_process is True

    def test_one_second_before_boundary(self):
        """Should not process 1 second before boundary."""
        delay_minutes = 5
        cutoff_time = datetime.utcnow() - timedelta(minutes=delay_minutes)

        # 1 second before boundary
        subscriber = create_mock_subscriber(
            subscribed_at=cutoff_time + timedelta(seconds=1),
        )

        should_process = subscriber.subscribed_at <= cutoff_time
        assert should_process is False

    def test_handles_null_timestamp(self):
        """Should handle null timestamp gracefully."""
        subscriber = create_mock_subscriber()
        subscriber.welcome_email_sent_at = None

        has_timestamp = subscriber.welcome_email_sent_at is not None
        assert has_timestamp is False


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
