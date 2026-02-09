"""
Booking service for TAG parking system.

Manages time slot availability, booking creation, and slot visibility.
When a slot is booked, it becomes hidden/unavailable for other users.
"""
import json
import os
import uuid
from datetime import date, time, datetime
from decimal import Decimal
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


def get_pricing_from_db() -> dict:
    """
    Fetch pricing settings from database.

    Returns:
        Dictionary with all duration-based prices and tier_increment.
        Returns defaults if database is unavailable or no settings exist.
    """
    defaults = {
        "days_1_4_price": 60.0,
        "days_5_6_price": 72.0,
        "week1_base_price": 79.0,   # 7 days
        "days_8_9_price": 99.0,
        "days_10_11_price": 119.0,
        "days_12_13_price": 130.0,
        "week2_base_price": 140.0,  # 14 days
        "tier_increment": 10.0,
    }

    try:
        import psycopg2
        database_url = os.getenv("DATABASE_URL")

        if not database_url:
            return defaults

        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT days_1_4_price, days_5_6_price, week1_base_price,
                   days_8_9_price, days_10_11_price, days_12_13_price,
                   week2_base_price, tier_increment
            FROM pricing_settings LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return {
                "days_1_4_price": float(row[0]) if row[0] else defaults["days_1_4_price"],
                "days_5_6_price": float(row[1]) if row[1] else defaults["days_5_6_price"],
                "week1_base_price": float(row[2]) if row[2] else defaults["week1_base_price"],
                "days_8_9_price": float(row[3]) if row[3] else defaults["days_8_9_price"],
                "days_10_11_price": float(row[4]) if row[4] else defaults["days_10_11_price"],
                "days_12_13_price": float(row[5]) if row[5] else defaults["days_12_13_price"],
                "week2_base_price": float(row[6]) if row[6] else defaults["week2_base_price"],
                "tier_increment": float(row[7]) if row[7] else defaults["tier_increment"],
            }
        return defaults
    except Exception:
        # If anything fails, use defaults
        return defaults


def get_duration_tier(duration_days: int) -> str:
    """
    Get the duration tier key based on number of days.

    Args:
        duration_days: Number of days for the trip (1-14)

    Returns:
        Duration tier key: "1_4", "5_6", "7", "8_9", "10_11", "12_13", or "14"
    """
    if duration_days <= 4:
        return "1_4"
    elif duration_days <= 6:
        return "5_6"
    elif duration_days == 7:
        return "7"
    elif duration_days <= 9:
        return "8_9"
    elif duration_days <= 11:
        return "10_11"
    elif duration_days <= 13:
        return "12_13"
    else:
        return "14"


def get_base_price_for_duration(duration_days: int, pricing: dict = None) -> float:
    """
    Get the base (early tier) price for a given duration.

    Args:
        duration_days: Number of days for the trip (1-14)
        pricing: Optional pricing dict, fetched from DB if not provided

    Returns:
        Base price in pounds for the early booking tier
    """
    if pricing is None:
        pricing = get_pricing_from_db()

    tier = get_duration_tier(duration_days)

    # Map duration tier to pricing field
    price_map = {
        "1_4": pricing["days_1_4_price"],
        "5_6": pricing["days_5_6_price"],
        "7": pricing["week1_base_price"],
        "8_9": pricing["days_8_9_price"],
        "10_11": pricing["days_10_11_price"],
        "12_13": pricing["days_12_13_price"],
        "14": pricing["week2_base_price"],
    }

    return price_map.get(tier, pricing["week2_base_price"])


# Cache for pricing settings (refreshed every request in production)
_cached_pricing: Optional[dict] = None

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

    # Package durations (in days)
    PACKAGE_DURATIONS = {
        "quick": 7,    # 1 week
        "longer": 14,  # 2 weeks
    }

    @classmethod
    def get_all_duration_prices(cls) -> dict:
        """
        Get current pricing for all duration tiers from database.

        Returns:
            Dict with prices for each duration tier and advance tier
        """
        pricing = get_pricing_from_db()
        increment = pricing["tier_increment"]

        return {
            "1_4": {
                "early": pricing["days_1_4_price"],
                "standard": pricing["days_1_4_price"] + increment,
                "late": pricing["days_1_4_price"] + (increment * 2),
            },
            "5_6": {
                "early": pricing["days_5_6_price"],
                "standard": pricing["days_5_6_price"] + increment,
                "late": pricing["days_5_6_price"] + (increment * 2),
            },
            "7": {
                "early": pricing["week1_base_price"],
                "standard": pricing["week1_base_price"] + increment,
                "late": pricing["week1_base_price"] + (increment * 2),
            },
            "8_9": {
                "early": pricing["days_8_9_price"],
                "standard": pricing["days_8_9_price"] + increment,
                "late": pricing["days_8_9_price"] + (increment * 2),
            },
            "10_11": {
                "early": pricing["days_10_11_price"],
                "standard": pricing["days_10_11_price"] + increment,
                "late": pricing["days_10_11_price"] + (increment * 2),
            },
            "12_13": {
                "early": pricing["days_12_13_price"],
                "standard": pricing["days_12_13_price"] + increment,
                "late": pricing["days_12_13_price"] + (increment * 2),
            },
            "14": {
                "early": pricing["week2_base_price"],
                "standard": pricing["week2_base_price"] + increment,
                "late": pricing["week2_base_price"] + (increment * 2),
            },
        }

    @classmethod
    def get_package_prices(cls) -> dict:
        """
        Get current pricing from database for legacy "quick"/"longer" packages.
        For backwards compatibility with existing code.

        Returns:
            Dict with package prices for each tier
        """
        pricing = get_pricing_from_db()

        week1_base = pricing["week1_base_price"]
        week2_base = pricing["week2_base_price"]
        increment = pricing["tier_increment"]

        return {
            "quick": {
                "early": week1_base,
                "standard": week1_base + increment,
                "late": week1_base + (increment * 2),
            },
            "longer": {
                "early": week2_base,
                "standard": week2_base + increment,
                "late": week2_base + (increment * 2),
            },
        }

    @classmethod
    def get_advance_tier(cls, drop_off_date: date) -> str:
        """
        Determine the pricing tier based on how far in advance the booking is.

        Args:
            drop_off_date: The date of drop-off

        Returns:
            "early" if >=14 days, "standard" if 7-13 days, "late" if <7 days
        """
        today = date.today()
        days_in_advance = (drop_off_date - today).days

        if days_in_advance >= 14:
            return "early"
        elif days_in_advance >= 7:
            return "standard"
        else:
            return "late"

    @classmethod
    def calculate_price_for_duration(cls, duration_days: int, drop_off_date: date) -> float:
        """
        Calculate the price based on trip duration and advance booking tier.

        Args:
            duration_days: Number of days for the trip (1-14)
            drop_off_date: The date of drop-off

        Returns:
            The price in pounds
        """
        advance_tier = cls.get_advance_tier(drop_off_date)
        duration_tier = get_duration_tier(duration_days)
        all_prices = cls.get_all_duration_prices()
        return all_prices[duration_tier][advance_tier]

    @classmethod
    def calculate_price(cls, package: str, drop_off_date: date) -> float:
        """
        Calculate the price based on package and advance booking tier.
        Legacy method for backwards compatibility.

        Args:
            package: "quick" (1 week) or "longer" (2 weeks)
            drop_off_date: The date of drop-off

        Returns:
            The price in pounds
        """
        tier = cls.get_advance_tier(drop_off_date)
        prices = cls.get_package_prices()
        return prices[package][tier]

    @classmethod
    def get_duration_days(cls, drop_off_date: date, pickup_date: date) -> int:
        """
        Calculate the number of days between drop-off and pickup.

        Args:
            drop_off_date: The date of drop-off
            pickup_date: The date of pickup

        Returns:
            Number of days
        """
        return (pickup_date - drop_off_date).days

    @classmethod
    def get_package_for_duration(cls, drop_off_date: date, pickup_date: date) -> str:
        """
        Determine the package based on the duration between drop-off and pickup.
        Maps to "quick" (1-7 days) or "longer" (8-14 days) for backwards compatibility.

        Args:
            drop_off_date: The date of drop-off
            pickup_date: The date of pickup

        Returns:
            "quick" for 1-7 days, "longer" for 8-14 days

        Raises:
            ValueError: If duration is less than 1 or more than 14 days
        """
        duration = (pickup_date - drop_off_date).days

        if duration < 1:
            raise ValueError(f"Invalid duration: {duration} days. Must be at least 1 day.")
        elif duration > 14:
            raise ValueError(f"Invalid duration: {duration} days. Maximum is 14 days.")
        elif duration <= 7:
            return "quick"
        else:
            return "longer"

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

        # Calculate price based on package and advance booking tier
        price = self.calculate_price(request.package, drop_off_date)

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

        # Calculate price (use custom price if provided, otherwise use tiered pricing)
        if request.custom_price is not None:
            price = request.custom_price
        else:
            price = self.calculate_price(request.package, request.drop_off_date)

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
