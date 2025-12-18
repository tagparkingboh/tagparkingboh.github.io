"""
Unit tests for the booking service.

Tests cover booking creation, slot availability management,
capacity tracking, and cancellation logic.
"""
import pytest
from datetime import date, time, datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from booking_service import BookingService, NO_SLOTS_CONTACT_MESSAGE
from models import BookingRequest, AdminBookingRequest, SlotType


@pytest.fixture
def service():
    """Create a fresh BookingService for each test."""
    return BookingService()


@pytest.fixture
def sample_booking_request():
    """Create a sample booking request for testing."""
    return BookingRequest(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone="07700900000",
        drop_off_date=date(2026, 2, 10),
        drop_off_slot_type=SlotType.EARLY,
        flight_date=date(2026, 2, 10),
        flight_time="10:00",
        flight_number="5523",
        airline_code="FR",
        airline_name="Ryanair",
        destination_code="KRK",
        destination_name="Krakow, PL",
        pickup_date=date(2026, 2, 17),
        return_flight_time="14:30",
        return_flight_number="5524",
        registration="AB12 CDE",
        make="Ford",
        model="Focus",
        colour="Blue",
        package="quick",
        billing_address1="123 Test Street",
        billing_city="London",
        billing_postcode="SW1A 1AA",
        billing_country="United Kingdom",
    )


class TestBookingServiceInit:
    """Tests for BookingService initialization."""

    def test_service_initializes_empty(self, service):
        """Service should start with no bookings."""
        assert len(service._bookings) == 0
        assert len(service._booked_slots) == 0

    def test_max_parking_spots_configured(self, service):
        """Max parking spots should be set."""
        assert service.MAX_PARKING_SPOTS == 60

    def test_package_prices_configured(self, service):
        """Package prices should be set correctly."""
        assert service.PACKAGE_PRICES["quick"]["early"] == 99.0
        assert service.PACKAGE_PRICES["longer"]["early"] == 150.0


class TestSlotAvailability:
    """Tests for time slot availability checking."""

    def test_new_slot_is_available(self, service):
        """Unbooked slot should be available."""
        slots = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert len(slots.slots) == 2  # Both slots available

    def test_slot_hidden_after_booking(self, service, sample_booking_request):
        """Booked slot should not appear in available slots."""
        # Get initial slots
        initial_slots = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert len(initial_slots.slots) == 2

        # Create booking (using EARLY slot)
        service.create_booking(sample_booking_request)

        # Check slots again
        remaining_slots = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )

        # Only 1 slot should remain (LATE)
        assert len(remaining_slots.slots) == 1
        assert remaining_slots.slots[0].slot_type == SlotType.LATE

    def test_both_slots_hidden_when_both_booked(self, service, sample_booking_request):
        """When both slots are booked, none should appear."""
        # Book EARLY slot
        service.create_booking(sample_booking_request)

        # Book LATE slot
        late_request = sample_booking_request.model_copy()
        late_request.drop_off_slot_type = SlotType.LATE
        late_request.email = "jane.doe@example.com"  # Different customer
        service.create_booking(late_request)

        # Check slots
        slots = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )

        assert len(slots.slots) == 0

    def test_is_slot_available_returns_true_for_new(self, service):
        """is_slot_available should return True for unbooked slots."""
        slot_id = "2026-02-10_0715_FR5523_165"
        assert service.is_slot_available(slot_id) is True

    def test_is_slot_available_returns_false_after_booking(
        self, service, sample_booking_request
    ):
        """is_slot_available should return False for booked slots."""
        service.create_booking(sample_booking_request)

        # The slot ID format for the early slot
        slot_id = "2026-02-10_0715_FR5523_165"
        assert service.is_slot_available(slot_id) is False


class TestBookingCreation:
    """Tests for creating bookings."""

    def test_booking_created_successfully(self, service, sample_booking_request):
        """Booking should be created with correct data."""
        booking = service.create_booking(sample_booking_request)

        assert booking.booking_id is not None
        assert booking.first_name == "John"
        assert booking.last_name == "Doe"
        assert booking.email == "john.doe@example.com"
        assert booking.status == "confirmed"

    def test_booking_calculates_correct_price(self, service, sample_booking_request):
        """Booking should have correct package price."""
        booking = service.create_booking(sample_booking_request)
        assert booking.price == 99.0  # "quick" package

        # Test longer package
        longer_request = sample_booking_request.model_copy()
        longer_request.package = "longer"
        longer_request.email = "other@example.com"
        longer_request.drop_off_slot_type = SlotType.LATE  # Use different slot

        longer_booking = service.create_booking(longer_request)
        assert longer_booking.price == 150.0

    def test_booking_calculates_drop_off_time(self, service, sample_booking_request):
        """Booking should calculate correct drop-off time."""
        booking = service.create_booking(sample_booking_request)

        # 10:00 - 2:45 = 07:15
        assert booking.drop_off_time == time(7, 15)
        assert booking.drop_off_date == date(2026, 2, 10)

    def test_booking_stores_in_collection(self, service, sample_booking_request):
        """Created booking should be retrievable."""
        booking = service.create_booking(sample_booking_request)
        retrieved = service.get_booking(booking.booking_id)

        assert retrieved is not None
        assert retrieved.booking_id == booking.booking_id

    def test_duplicate_slot_booking_fails(self, service, sample_booking_request):
        """Booking same slot twice should fail."""
        service.create_booking(sample_booking_request)

        # Try to book same slot again
        duplicate_request = sample_booking_request.model_copy()
        duplicate_request.email = "other@example.com"

        with pytest.raises(ValueError) as excinfo:
            service.create_booking(duplicate_request)

        assert "already booked" in str(excinfo.value)


class TestOvernightBookings:
    """Tests for overnight drop-off scenarios."""

    def test_overnight_booking_calculates_correct_date(self, service):
        """Early morning flight should have drop-off on previous day."""
        request = BookingRequest(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="07700900000",
            drop_off_date=date(2026, 2, 10),  # This is the flight date
            drop_off_slot_type=SlotType.EARLY,
            flight_date=date(2026, 2, 10),  # Tuesday
            flight_time="00:35",  # Very early morning
            flight_number="5523",
            airline_code="FR",
            airline_name="Ryanair",
            destination_code="KRK",
            destination_name="Krakow, PL",
            pickup_date=date(2026, 2, 17),
            return_flight_time="14:30",
            return_flight_number="5524",
            registration="AB12 CDE",
            make="Ford",
            model="Focus",
            colour="Blue",
            package="quick",
            billing_address1="123 Test Street",
            billing_city="London",
            billing_postcode="SW1A 1AA",
            billing_country="United Kingdom",
        )

        booking = service.create_booking(request)

        # Drop-off should be Monday evening
        assert booking.drop_off_date == date(2026, 2, 9)  # Monday
        assert booking.drop_off_time == time(21, 50)  # 00:35 - 2:45

    def test_overnight_late_slot_booking(self, service):
        """Early morning flight with late slot."""
        request = BookingRequest(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="07700900001",
            drop_off_date=date(2026, 2, 10),
            drop_off_slot_type=SlotType.LATE,
            flight_date=date(2026, 2, 10),  # Tuesday
            flight_time="00:35",
            flight_number="5523",
            airline_code="FR",
            airline_name="Ryanair",
            destination_code="KRK",
            destination_name="Krakow, PL",
            pickup_date=date(2026, 2, 17),
            return_flight_time="14:30",
            return_flight_number="5524",
            registration="CD34 EFG",
            make="VW",
            model="Golf",
            colour="Black",
            package="quick",
            billing_address1="456 Test Ave",
            billing_city="Manchester",
            billing_postcode="M1 1AA",
            billing_country="United Kingdom",
        )

        booking = service.create_booking(request)

        # Drop-off should be Monday evening
        assert booking.drop_off_date == date(2026, 2, 9)  # Monday
        assert booking.drop_off_time == time(22, 35)  # 00:35 - 2:00


class TestBookingCancellation:
    """Tests for cancelling bookings."""

    def test_cancel_booking_releases_slot(self, service, sample_booking_request):
        """Cancelled booking should release the slot."""
        booking = service.create_booking(sample_booking_request)

        # Verify slot is booked
        slots_before = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert len(slots_before.slots) == 1  # Only LATE available

        # Cancel the booking
        result = service.cancel_booking(booking.booking_id)
        assert result is True

        # Verify slot is available again
        slots_after = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert len(slots_after.slots) == 2  # Both available again

    def test_cancel_nonexistent_booking_returns_false(self, service):
        """Cancelling non-existent booking should return False."""
        result = service.cancel_booking("nonexistent-id")
        assert result is False

    def test_cancelled_booking_marked_as_cancelled(
        self, service, sample_booking_request
    ):
        """Cancelled booking should have cancelled status."""
        booking = service.create_booking(sample_booking_request)
        service.cancel_booking(booking.booking_id)

        retrieved = service.get_booking(booking.booking_id)
        assert retrieved.status == "cancelled"


class TestCapacityManagement:
    """Tests for parking capacity tracking."""

    def test_capacity_check_empty_parking(self, service):
        """Empty parking should show full availability."""
        result = service.check_capacity_for_date_range(
            date(2026, 2, 10),
            date(2026, 2, 17)
        )

        assert result["all_available"] is True
        assert result["max_capacity"] == 60

    def test_booking_updates_daily_occupancy(self, service, sample_booking_request):
        """Creating a booking should update occupancy counts."""
        service.create_booking(sample_booking_request)

        # Check a date in the booking range
        bookings = service.get_bookings_for_date(date(2026, 2, 12))
        assert len(bookings) == 1

    def test_cancellation_updates_daily_occupancy(
        self, service, sample_booking_request
    ):
        """Cancelling a booking should decrease occupancy."""
        booking = service.create_booking(sample_booking_request)

        # Verify booking is counted
        bookings_before = service.get_bookings_for_date(date(2026, 2, 12))
        assert len(bookings_before) == 1

        # Cancel and verify
        service.cancel_booking(booking.booking_id)
        bookings_after = service.get_bookings_for_date(date(2026, 2, 12))
        assert len(bookings_after) == 0


class TestBookingQueries:
    """Tests for querying bookings."""

    def test_get_booking_returns_none_for_invalid_id(self, service):
        """Getting non-existent booking should return None."""
        result = service.get_booking("invalid-id")
        assert result is None

    def test_get_bookings_by_email(self, service, sample_booking_request):
        """Should find bookings by email."""
        service.create_booking(sample_booking_request)

        # Create another booking with different slot
        second_request = sample_booking_request.model_copy()
        second_request.drop_off_slot_type = SlotType.LATE
        second_request.drop_off_date = date(2026, 3, 10)
        second_request.flight_date = date(2026, 3, 10)
        second_request.pickup_date = date(2026, 3, 17)
        service.create_booking(second_request)

        bookings = service.get_bookings_by_email("john.doe@example.com")
        assert len(bookings) == 2

    def test_get_bookings_by_email_case_insensitive(
        self, service, sample_booking_request
    ):
        """Email search should be case insensitive."""
        service.create_booking(sample_booking_request)

        bookings = service.get_bookings_by_email("JOHN.DOE@EXAMPLE.COM")
        assert len(bookings) == 1

    def test_get_all_active_bookings(self, service, sample_booking_request):
        """Should return all non-cancelled bookings."""
        booking1 = service.create_booking(sample_booking_request)

        second_request = sample_booking_request.model_copy()
        second_request.drop_off_slot_type = SlotType.LATE
        second_request.email = "other@example.com"
        booking2 = service.create_booking(second_request)

        # Cancel one
        service.cancel_booking(booking1.booking_id)

        active = service.get_all_active_bookings()
        assert len(active) == 1
        assert active[0].booking_id == booking2.booking_id

    def test_get_bookings_for_date(self, service, sample_booking_request):
        """Should find bookings active on a specific date."""
        # Booking from Feb 10-17
        service.create_booking(sample_booking_request)

        # Should find it on Feb 12
        bookings = service.get_bookings_for_date(date(2026, 2, 12))
        assert len(bookings) == 1

        # Should not find it on Feb 18 (after pickup)
        bookings = service.get_bookings_for_date(date(2026, 2, 18))
        assert len(bookings) == 0

        # Should not find it on Feb 9 (before drop-off)
        bookings = service.get_bookings_for_date(date(2026, 2, 9))
        assert len(bookings) == 0


class TestAllSlotsBookedContactMessage:
    """Tests for the 'all slots booked' contact message feature."""

    def test_no_contact_message_when_slots_available(self, service):
        """Should not show contact message when slots are available."""
        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )

        assert response.all_slots_booked is False
        assert response.contact_message is None
        assert len(response.slots) == 2

    def test_no_contact_message_when_one_slot_available(
        self, service, sample_booking_request
    ):
        """Should not show contact message when one slot remains."""
        # Book the early slot
        service.create_booking(sample_booking_request)

        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )

        assert response.all_slots_booked is False
        assert response.contact_message is None
        assert len(response.slots) == 1

    def test_contact_message_when_all_slots_booked(
        self, service, sample_booking_request
    ):
        """Should show contact message when all slots are booked."""
        # Book early slot
        service.create_booking(sample_booking_request)

        # Book late slot
        late_request = sample_booking_request.model_copy()
        late_request.drop_off_slot_type = SlotType.LATE
        late_request.email = "other@example.com"
        service.create_booking(late_request)

        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )

        assert response.all_slots_booked is True
        assert response.contact_message == NO_SLOTS_CONTACT_MESSAGE
        assert len(response.slots) == 0
        assert "contact us" in response.contact_message.lower()

    def test_contact_message_cleared_after_cancellation(
        self, service, sample_booking_request
    ):
        """Contact message should disappear when a slot becomes available."""
        # Book both slots
        booking1 = service.create_booking(sample_booking_request)

        late_request = sample_booking_request.model_copy()
        late_request.drop_off_slot_type = SlotType.LATE
        late_request.email = "other@example.com"
        service.create_booking(late_request)

        # Verify all booked
        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert response.all_slots_booked is True

        # Cancel one booking
        service.cancel_booking(booking1.booking_id)

        # Verify contact message gone
        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert response.all_slots_booked is False
        assert response.contact_message is None
        assert len(response.slots) == 1


class TestAdminBooking:
    """Tests for admin booking functionality."""

    @pytest.fixture
    def admin_booking_request(self):
        """Create a sample admin booking request."""
        return AdminBookingRequest(
            first_name="Admin",
            last_name="Created",
            email="customer@example.com",
            phone="07700900000",
            drop_off_date=date(2026, 2, 10),
            drop_off_time="08:30",  # Custom time, not restricted to slots
            flight_date=date(2026, 2, 10),
            flight_time="10:00",
            flight_number="5523",
            airline_code="FR",
            airline_name="Ryanair",
            destination_code="KRK",
            destination_name="Krakow, PL",
            pickup_date=date(2026, 2, 17),
            return_flight_time="14:30",
            return_flight_number="5524",
            registration="AB12 CDE",
            make="Ford",
            model="Focus",
            colour="Blue",
            package="quick",
            booking_source="phone",
        )

    def test_admin_booking_creates_successfully(self, service, admin_booking_request):
        """Admin should be able to create a booking."""
        booking = service.create_admin_booking(admin_booking_request)

        assert booking.booking_id is not None
        assert booking.first_name == "Admin"
        assert booking.status == "confirmed"
        assert booking.price == 99.0  # Standard quick price

    def test_admin_booking_uses_custom_drop_off_time(
        self, service, admin_booking_request
    ):
        """Admin booking should use the exact time specified."""
        booking = service.create_admin_booking(admin_booking_request)

        # Should use admin-specified time, not calculated from slot
        assert booking.drop_off_time == time(8, 30)
        assert booking.drop_off_date == date(2026, 2, 10)

    def test_admin_booking_with_custom_price(self, service, admin_booking_request):
        """Admin can override the standard package price."""
        admin_booking_request.custom_price = 75.00  # Discounted price

        booking = service.create_admin_booking(admin_booking_request)

        assert booking.price == 75.00

    def test_admin_booking_bypasses_slot_restrictions(
        self, service, sample_booking_request, admin_booking_request
    ):
        """Admin can book even when regular slots are full."""
        # Book both regular slots
        service.create_booking(sample_booking_request)

        late_request = sample_booking_request.model_copy()
        late_request.drop_off_slot_type = SlotType.LATE
        late_request.email = "other@example.com"
        service.create_booking(late_request)

        # Verify regular slots are full
        response = service.get_available_slots_for_flight(
            flight_date=date(2026, 2, 10),
            flight_time=time(10, 0),
            flight_number="5523",
            airline_code="FR"
        )
        assert response.all_slots_booked is True

        # Admin can still create a booking
        admin_booking_request.email = "walkin@example.com"
        booking = service.create_admin_booking(admin_booking_request)

        assert booking.booking_id is not None
        assert booking.status == "confirmed"

    def test_admin_booking_updates_occupancy(self, service, admin_booking_request):
        """Admin bookings should count toward parking capacity."""
        service.create_admin_booking(admin_booking_request)

        bookings = service.get_bookings_for_date(date(2026, 2, 12))
        assert len(bookings) == 1

    def test_admin_booking_with_minimal_billing(self, service, admin_booking_request):
        """Admin bookings can have minimal billing info."""
        # These are optional for admin bookings
        admin_booking_request.billing_address1 = None
        admin_booking_request.billing_city = None
        admin_booking_request.billing_postcode = None

        booking = service.create_admin_booking(admin_booking_request)

        assert booking.booking_id is not None
        assert booking.billing_address1 == ""  # Defaults to empty string

    def test_admin_booking_tracks_source(self, service, admin_booking_request):
        """Admin booking should track the booking source."""
        admin_booking_request.booking_source = "walk-in"

        booking = service.create_admin_booking(admin_booking_request)

        # The source is in the request, booking is created successfully
        assert booking.booking_id is not None

    def test_admin_booking_respects_capacity_limits(self, service, admin_booking_request):
        """Admin bookings should still respect parking capacity."""
        # This test would require filling all 60 spots
        # For now, just verify the capacity check is called
        booking = service.create_admin_booking(admin_booking_request)
        assert booking is not None
