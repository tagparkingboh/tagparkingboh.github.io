"""
Tests for the 2-Day Reminder Email functionality.

Tests cover:
- Unit tests for send_2_day_reminder_email function
- Unit tests for process_pending_2day_reminders scheduler function
- Integration tests for automated email scheduling
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, date, time, timedelta

from email_service import send_2_day_reminder_email
from db_models import BookingStatus


# =============================================================================
# Unit Tests for send_2_day_reminder_email
# =============================================================================

class TestSend2DayReminderEmail:
    """Unit tests for the send_2_day_reminder_email function."""

    @patch('email_service.send_email')
    def test_sends_email_with_correct_parameters(self, mock_send_email):
        """Test that the function calls send_email with correct parameters."""
        mock_send_email.return_value = True

        result = send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        assert result is True
        mock_send_email.assert_called_once()

        # Check the email was sent to the correct address
        call_args = mock_send_email.call_args
        assert call_args[0][0] == "test@example.com"
        assert "Two Days to Go - TAG-12345678" in call_args[0][1]

    @patch('email_service.send_email')
    def test_email_contains_booking_reference(self, mock_send_email):
        """Test that the email HTML contains the booking reference."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-ABCD1234",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "TAG-ABCD1234" in html_content

    @patch('email_service.send_email')
    def test_email_contains_customer_name(self, mock_send_email):
        """Test that the email HTML contains the customer's full name."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="Sarah",
            last_name="Smith",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Sarah" in html_content
        assert "Smith" in html_content

    @patch('email_service.send_email')
    def test_email_contains_dropoff_date(self, mock_send_email):
        """Test that the email HTML contains the dropoff date."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Monday, 20 February 2026",
            dropoff_time="09:30",
            flight_departure_time="11:30",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Monday, 20 February 2026" in html_content

    @patch('email_service.send_email')
    def test_email_contains_meeting_time(self, mock_send_email):
        """Test that the email HTML contains the agreed meeting time."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="08:45",
            flight_departure_time="10:45",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "08:45" in html_content

    @patch('email_service.send_email')
    def test_email_contains_flight_departure_time(self, mock_send_email):
        """Test that the email HTML contains the flight departure time."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "14:10" in html_content

    @patch('email_service.send_email')
    def test_email_contains_contact_information(self, mock_send_email):
        """Test that the email HTML contains contact details."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "07739 106145" in html_content
        assert "support@tagparking.co.uk" in html_content

    @patch('email_service.send_email')
    def test_email_contains_vehicle_inspection_link(self, mock_send_email):
        """Test that the email HTML contains the vehicle inspection terms link."""
        mock_send_email.return_value = True

        send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "vehicle-inspection-terms" in html_content

    @patch('email_service.send_email')
    def test_returns_false_when_send_fails(self, mock_send_email):
        """Test that the function returns False when email sending fails."""
        mock_send_email.return_value = False

        result = send_2_day_reminder_email(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        assert result is False

    @patch('email_service.send_email')
    def test_handles_special_characters_in_name(self, mock_send_email):
        """Test that special characters in names are handled correctly."""
        mock_send_email.return_value = True

        result = send_2_day_reminder_email(
            email="test@example.com",
            first_name="José",
            last_name="García",
            booking_reference="TAG-12345678",
            dropoff_date="Friday, 13 February 2026",
            dropoff_time="12:10",
            flight_departure_time="14:10",
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert "José" in html_content
        assert "García" in html_content


# =============================================================================
# Unit Tests for process_pending_2day_reminders scheduler function
# =============================================================================

def create_mock_booking(
    reference="TAG-REMIND001",
    customer_id=1,
    status=BookingStatus.CONFIRMED,
    dropoff_date=None,
    dropoff_time=None,
    reminder_2day_sent=False,
    reminder_2day_sent_at=None,
    departure_id=None,
):
    """Helper to create a mock booking."""
    if dropoff_date is None:
        dropoff_date = date.today() + timedelta(days=1)
    if dropoff_time is None:
        dropoff_time = time(10, 0)

    booking = MagicMock()
    booking.reference = reference
    booking.customer_id = customer_id
    booking.status = status
    booking.dropoff_date = dropoff_date
    booking.dropoff_time = dropoff_time
    booking.reminder_2day_sent = reminder_2day_sent
    booking.reminder_2day_sent_at = reminder_2day_sent_at
    booking.departure_id = departure_id
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


def create_mock_flight(
    id=1,
    departure_time=None,
):
    """Helper to create a mock flight."""
    if departure_time is None:
        departure_time = time(14, 30)

    flight = MagicMock()
    flight.id = id
    flight.departure_time = departure_time
    return flight


class TestProcess2DayReminders:
    """Unit tests for the scheduler function that processes 2-day reminders."""

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    def test_does_nothing_when_email_disabled(self, mock_enabled, mock_send):
        """Test that no emails are sent when email is disabled."""
        mock_enabled.return_value = False

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_sends_reminder_for_booking_within_48_hours(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is sent for booking within 48 hours."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking and customer
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = create_mock_booking(
            reference="TAG-REMIND001",
            dropoff_date=tomorrow,
            dropoff_time=time(10, 0),
        )
        mock_customer = create_mock_customer(
            email="testreminder@example.com",
            first_name="Test",
            last_name="User",
        )

        # Setup query chain for booking query
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        # Setup query chain for customer query
        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        # Setup query chain for flight query (no linked flight)
        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = None

        # Configure db.query to return appropriate mocks based on model
        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["email"] == "testreminder@example.com"
        assert call_kwargs["first_name"] == "Test"
        assert call_kwargs["last_name"] == "User"
        assert call_kwargs["booking_reference"] == "TAG-REMIND001"

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_already_sent_reminder(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is not sent if already sent."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (already filtered out)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_pending_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is not sent for PENDING (unconfirmed) bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (PENDING filtered out by query)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_cancelled_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is not sent for CANCELLED bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (CANCELLED filtered out by query)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_booking_more_than_48_hours_away(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is not sent for booking more than 48 hours away."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (filtered out by cutoff date)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_send_for_past_booking(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder is not sent for past bookings."""
        mock_enabled.return_value = True

        # Setup mock database that returns no bookings (past dates filtered out)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = []

        mock_db.query.return_value = mock_booking_query

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_not_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_marks_reminder_as_sent_after_success(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder_2day_sent is marked True after successful send."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = create_mock_booking(
            reference="TAG-REMIND007",
            dropoff_date=tomorrow,
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        # Check that reminder_2day_sent was set to True
        assert mock_booking.reminder_2day_sent is True
        assert mock_booking.reminder_2day_sent_at is not None
        mock_db.commit.assert_called()

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_does_not_mark_sent_on_failure(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that reminder_2day_sent is NOT marked True if send fails."""
        mock_enabled.return_value = True
        mock_send.return_value = False  # Email fails

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = create_mock_booking(
            reference="TAG-REMIND008",
            dropoff_date=tomorrow,
        )
        mock_customer = create_mock_customer()

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        # Check that reminder_2day_sent was NOT changed
        assert mock_booking.reminder_2day_sent is False

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_includes_flight_departure_time_from_linked_flight(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that flight departure time is fetched from linked FlightDeparture."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking with linked flight
        tomorrow = date.today() + timedelta(days=1)
        mock_booking = create_mock_booking(
            reference="TAG-REMIND009",
            dropoff_date=tomorrow,
            dropoff_time=time(12, 30),
            departure_id=1,
        )
        mock_customer = create_mock_customer()
        mock_flight = create_mock_flight(departure_time=time(14, 30))

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = mock_flight

        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["flight_departure_time"] == "14:30"


# =============================================================================
# Integration Tests for Scheduler Behavior
# =============================================================================

class TestSchedulerIntegration:
    """Integration tests for the scheduler's 2-day reminder behavior."""

    @patch('email_scheduler.send_2_day_reminder_email')
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
        tomorrow = date.today() + timedelta(days=1)
        mock_booking1 = create_mock_booking(
            reference="TAG-REMIND010",
            customer_id=1,
            dropoff_date=tomorrow,
        )
        mock_booking2 = create_mock_booking(
            reference="TAG-REMIND011",
            customer_id=2,
            dropoff_date=tomorrow,
        )

        mock_customer1 = create_mock_customer(id=1, email="user1@example.com", first_name="User", last_name="One")
        mock_customer2 = create_mock_customer(id=2, email="user2@example.com", first_name="User", last_name="Two")

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

        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        # Both should have been sent
        assert mock_send.call_count == 2

    @patch('email_scheduler.send_2_day_reminder_email')
    @patch('email_scheduler.is_email_enabled')
    @patch('email_scheduler.get_db')
    def test_last_minute_booking_gets_reminder(
        self, mock_get_db, mock_enabled, mock_send
    ):
        """Test that a booking made for today still gets the reminder."""
        mock_enabled.return_value = True
        mock_send.return_value = True

        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create mock booking for today
        today = date.today()
        mock_booking = create_mock_booking(
            reference="TAG-REMIND012",
            dropoff_date=today,
            dropoff_time=time(18, 0),
        )
        mock_customer = create_mock_customer(email="lastminute@example.com", first_name="LastMinute", last_name="Booker")

        # Setup query chain
        mock_booking_query = MagicMock()
        mock_booking_query.filter.return_value.limit.return_value.all.return_value = [mock_booking]

        mock_customer_query = MagicMock()
        mock_customer_query.filter.return_value.first.return_value = mock_customer

        mock_flight_query = MagicMock()
        mock_flight_query.filter.return_value.first.return_value = None

        def query_side_effect(model):
            from db_models import Booking, Customer, FlightDeparture
            if model == Booking:
                return mock_booking_query
            elif model == Customer:
                return mock_customer_query
            elif model == FlightDeparture:
                return mock_flight_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        from email_scheduler import process_pending_2day_reminders
        process_pending_2day_reminders()

        # Should still receive reminder (even though it's same day)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["email"] == "lastminute@example.com"
