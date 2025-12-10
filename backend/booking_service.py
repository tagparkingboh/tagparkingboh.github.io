"""
Booking service for TAG parking system.

Manages time slot availability, booking creation, and slot visibility.
When a slot is booked, it becomes hidden/unavailable for other users.
"""
import json
import uuid
from datetime import date, time, datetime
from pathlib import Path
from typing import Optional
from models import (
    Booking,
    BookingRequest,
    AdminBookingRequest,
    Flight,
    FlightType,
    SlotType,
    TimeSlot,
    AvailableSlotsResponse,
)
from time_slots import calculate_drop_off_datetime, calculate_all_slots, SLOT_LABELS

# Contact message when all slots are booked
NO_SLOTS_CONTACT_MESSAGE = (
    "All available time slots for this flight have been booked. "
    "Please contact us directly and we'll do our best to accommodate you. "
    "Call: 01onal number | Email: bookings@tagparking.com"
)


class BookingService:
    """
    Service for managing bookings and time slot availability.

    In production, this would use a database. For now, we use
    in-memory storage with optional file persistence.
    """

    # Maximum concurrent bookings (parking spots)
    MAX_PARKING_SPOTS = 60

    # Package prices
    PACKAGE_PRICES = {
        "quick": 99.0,   # 1 week
        "longer": 135.0,  # 2 weeks
    }

    def __init__(self, flights_data_path: Optional[str] = None):
        """
        Initialize the booking service.

        Args:
            flights_data_path: Path to the flight schedule JSON file
        """
        # In-memory storage for bookings
        self._bookings: dict[str, Booking] = {}

        # Track booked slots: slot_id -> booking_id
        self._booked_slots: dict[str, str] = {}

        # Track daily parking occupancy: date_str -> count
        self._daily_occupancy: dict[str, int] = {}

        # Load flight schedule if path provided
        self._flights: list[Flight] = []
        if flights_data_path:
            self._load_flights(flights_data_path)

    def _load_flights(self, path: str) -> None:
        """Load flight schedule from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
            self._flights = [Flight.model_validate(flight) for flight in data]

    def get_flights_for_date(
        self,
        flight_date: date,
        flight_type: FlightType = FlightType.DEPARTURE
    ) -> list[Flight]:
        """
        Get all flights for a specific date and type.

        Args:
            flight_date: The date to query
            flight_type: departure or arrival

        Returns:
            List of flights matching the criteria
        """
        return [
            f for f in self._flights
            if f.date == flight_date and f.type == flight_type
        ]

    def get_available_slots_for_flight(
        self,
        flight_date: date,
        flight_time: time,
        flight_number: str,
        airline_code: str
    ) -> AvailableSlotsResponse:
        """
        Get available (unbooked) time slots for a specific flight.

        Booked slots are hidden from the response - they simply
        don't appear in the returned list.

        Args:
            flight_date: Date of the flight
            flight_time: Time of the flight
            flight_number: Flight number
            airline_code: Airline code

        Returns:
            Response containing only available slots
        """
        all_slots = calculate_all_slots(
            flight_date, flight_time, flight_number, airline_code
        )

        # Filter out booked slots - they should be hidden
        available_slots = [
            slot for slot in all_slots
            if slot.slot_id not in self._booked_slots
        ]

        # Check if all slots are booked
        all_slots_booked = len(available_slots) == 0 and len(all_slots) > 0
        contact_message = NO_SLOTS_CONTACT_MESSAGE if all_slots_booked else None

        return AvailableSlotsResponse(
            flight_date=flight_date,
            flight_time=flight_time.strftime("%H:%M"),
            flight_number=f"{airline_code}{flight_number}",
            slots=available_slots,
            all_slots_booked=all_slots_booked,
            contact_message=contact_message
        )

    def is_slot_available(self, slot_id: str) -> bool:
        """
        Check if a specific slot is available for booking.

        Args:
            slot_id: The unique slot identifier

        Returns:
            True if the slot is available, False if booked
        """
        return slot_id not in self._booked_slots

    def check_capacity_for_date_range(
        self,
        start_date: date,
        end_date: date
    ) -> dict:
        """
        Check parking capacity for a date range.

        Args:
            start_date: Start of the parking period (drop-off date)
            end_date: End of the parking period (pickup date)

        Returns:
            Dictionary with availability information
        """
        current = start_date
        daily_availability = {}
        all_available = True

        while current <= end_date:
            date_str = current.isoformat()
            occupied = self._daily_occupancy.get(date_str, 0)
            available = self.MAX_PARKING_SPOTS - occupied

            daily_availability[date_str] = {
                "occupied": occupied,
                "available": available,
                "is_available": available > 0
            }

            if available <= 0:
                all_available = False

            current += datetime.timedelta(days=1) if hasattr(datetime, 'timedelta') else __import__('datetime').timedelta(days=1)

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "all_available": all_available,
            "daily_breakdown": daily_availability,
            "max_capacity": self.MAX_PARKING_SPOTS
        }

    def _update_occupancy(
        self,
        start_date: date,
        end_date: date,
        delta: int
    ) -> None:
        """
        Update daily occupancy counts for a date range.

        Args:
            start_date: Start date
            end_date: End date
            delta: +1 for booking, -1 for cancellation
        """
        from datetime import timedelta
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            self._daily_occupancy[date_str] = self._daily_occupancy.get(date_str, 0) + delta
            current += timedelta(days=1)

    def create_booking(self, request: BookingRequest) -> Booking:
        """
        Create a new booking and mark the slot as unavailable.

        Args:
            request: The booking request with all details

        Returns:
            The created Booking object

        Raises:
            ValueError: If the slot is already booked or capacity exceeded
        """
        # Parse flight time
        flight_time_parts = request.flight_time.split(':')
        flight_time = time(int(flight_time_parts[0]), int(flight_time_parts[1]))

        # Calculate the drop-off datetime
        drop_off_date, drop_off_time = calculate_drop_off_datetime(
            request.flight_date,
            flight_time,
            request.drop_off_slot_type
        )

        # Generate slot ID
        slot_id = (
            f"{drop_off_date.isoformat()}_"
            f"{drop_off_time.strftime('%H%M')}_"
            f"{request.airline_code}{request.flight_number}_"
            f"{request.drop_off_slot_type.value}"
        )

        # Check if slot is available
        if not self.is_slot_available(slot_id):
            raise ValueError(f"Time slot {slot_id} is already booked")

        # Check capacity for the parking period
        capacity_check = self.check_capacity_for_date_range(
            drop_off_date, request.pickup_date
        )
        if not capacity_check["all_available"]:
            raise ValueError("Insufficient parking capacity for the selected dates")

        # Generate booking ID
        booking_id = str(uuid.uuid4())

        # Parse return flight time
        return_time_parts = request.return_flight_time.split(':')
        return_flight_time = time(int(return_time_parts[0]), int(return_time_parts[1]))

        # Calculate price
        price = self.PACKAGE_PRICES[request.package]

        # Create the booking
        booking = Booking(
            booking_id=booking_id,
            created_at=datetime.now(),
            status="confirmed",
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            drop_off_date=drop_off_date,
            drop_off_time=drop_off_time,
            drop_off_slot_type=request.drop_off_slot_type,
            flight_date=request.flight_date,
            flight_time=flight_time,
            flight_number=request.flight_number,
            airline_code=request.airline_code,
            airline_name=request.airline_name,
            destination_code=request.destination_code,
            destination_name=request.destination_name,
            pickup_date=request.pickup_date,
            return_flight_time=return_flight_time,
            return_flight_number=request.return_flight_number,
            registration=request.registration,
            make=request.make,
            model=request.model,
            colour=request.colour,
            package=request.package,
            price=price,
            billing_address1=request.billing_address1,
            billing_address2=request.billing_address2,
            billing_city=request.billing_city,
            billing_county=request.billing_county,
            billing_postcode=request.billing_postcode,
            billing_country=request.billing_country,
        )

        # Store the booking
        self._bookings[booking_id] = booking

        # Mark slot as booked (this hides it from other users)
        self._booked_slots[slot_id] = booking_id

        # Update occupancy
        self._update_occupancy(drop_off_date, request.pickup_date, +1)

        return booking

    def cancel_booking(self, booking_id: str) -> bool:
        """
        Cancel a booking and release the slot.

        Args:
            booking_id: The booking ID to cancel

        Returns:
            True if cancelled successfully, False if booking not found
        """
        if booking_id not in self._bookings:
            return False

        booking = self._bookings[booking_id]

        # Find and remove the slot reservation
        slot_to_remove = None
        for slot_id, bid in self._booked_slots.items():
            if bid == booking_id:
                slot_to_remove = slot_id
                break

        if slot_to_remove:
            del self._booked_slots[slot_to_remove]

        # Update occupancy
        self._update_occupancy(
            booking.drop_off_date,
            booking.pickup_date,
            -1
        )

        # Update booking status
        booking.status = "cancelled"

        return True

    def get_booking(self, booking_id: str) -> Optional[Booking]:
        """
        Retrieve a booking by ID.

        Args:
            booking_id: The booking ID

        Returns:
            The Booking object or None if not found
        """
        return self._bookings.get(booking_id)

    def get_bookings_by_email(self, email: str) -> list[Booking]:
        """
        Get all bookings for a specific email address.

        Args:
            email: The customer's email address

        Returns:
            List of bookings matching the email
        """
        return [
            b for b in self._bookings.values()
            if b.email.lower() == email.lower() and b.status != "cancelled"
        ]

    def get_all_active_bookings(self) -> list[Booking]:
        """
        Get all active (non-cancelled) bookings.

        Returns:
            List of active bookings
        """
        return [
            b for b in self._bookings.values()
            if b.status != "cancelled"
        ]

    def get_bookings_for_date(self, target_date: date) -> list[Booking]:
        """
        Get all bookings where the vehicle will be parked on a specific date.

        Args:
            target_date: The date to check

        Returns:
            List of bookings active on that date
        """
        return [
            b for b in self._bookings.values()
            if b.status != "cancelled"
            and b.drop_off_date <= target_date <= b.pickup_date
        ]

    def create_admin_booking(self, request: AdminBookingRequest) -> Booking:
        """
        Create a booking via admin interface.

        This bypasses the normal slot restrictions, allowing admins to:
        - Set custom drop-off times
        - Override pricing
        - Book even when slots appear full
        - Add bookings from phone/walk-in customers

        Args:
            request: The admin booking request

        Returns:
            The created Booking object

        Raises:
            ValueError: If capacity is exceeded
        """
        # Parse times
        drop_off_time_parts = request.drop_off_time.split(':')
        drop_off_time = time(int(drop_off_time_parts[0]), int(drop_off_time_parts[1]))

        flight_time_parts = request.flight_time.split(':')
        flight_time = time(int(flight_time_parts[0]), int(flight_time_parts[1]))

        return_time_parts = request.return_flight_time.split(':')
        return_flight_time = time(int(return_time_parts[0]), int(return_time_parts[1]))

        # Check capacity (admin bookings still respect parking limits)
        capacity_check = self.check_capacity_for_date_range(
            request.drop_off_date, request.pickup_date
        )
        if not capacity_check["all_available"]:
            raise ValueError("Insufficient parking capacity for the selected dates")

        # Generate booking ID
        booking_id = str(uuid.uuid4())

        # Calculate price (use custom price if provided, otherwise standard)
        if request.custom_price is not None:
            price = request.custom_price
        else:
            price = self.PACKAGE_PRICES[request.package]

        # For admin bookings, we use a dummy slot type since they set exact time
        # Default to EARLY but it doesn't affect the actual drop-off time
        slot_type = SlotType.EARLY

        # Create the booking
        booking = Booking(
            booking_id=booking_id,
            created_at=datetime.now(),
            status="confirmed",
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            drop_off_date=request.drop_off_date,
            drop_off_time=drop_off_time,  # Admin-specified time
            drop_off_slot_type=slot_type,
            flight_date=request.flight_date,
            flight_time=flight_time,
            flight_number=request.flight_number,
            airline_code=request.airline_code,
            airline_name=request.airline_name,
            destination_code=request.destination_code,
            destination_name=request.destination_name,
            pickup_date=request.pickup_date,
            return_flight_time=return_flight_time,
            return_flight_number=request.return_flight_number,
            registration=request.registration,
            make=request.make,
            model=request.model,
            colour=request.colour,
            package=request.package,
            price=price,
            billing_address1=request.billing_address1 or "",
            billing_address2=None,
            billing_city=request.billing_city or "",
            billing_county=None,
            billing_postcode=request.billing_postcode or "",
            billing_country=request.billing_country,
        )

        # Store the booking
        self._bookings[booking_id] = booking

        # Generate a unique admin slot ID (won't conflict with regular slots)
        admin_slot_id = f"admin_{booking_id}"
        self._booked_slots[admin_slot_id] = booking_id

        # Update occupancy
        self._update_occupancy(request.drop_off_date, request.pickup_date, +1)

        return booking


# Singleton instance for the application
_booking_service: Optional[BookingService] = None


def get_booking_service(flights_data_path: Optional[str] = None) -> BookingService:
    """
    Get or create the booking service singleton.

    Args:
        flights_data_path: Path to flight schedule (only used on first call)

    Returns:
        The BookingService instance
    """
    global _booking_service
    if _booking_service is None:
        _booking_service = BookingService(flights_data_path)
    return _booking_service
