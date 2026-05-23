"""
Booking service for TAG parking system.

Manages time slot availability, booking creation, and slot visibility.
When a slot is booked, it becomes hidden/unavailable for other users.
"""
import json
import os
import uuid
from datetime import date, time, datetime, timedelta
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
        Dictionary with anchor prices, daily_increment, and tier_increment.
        Returns defaults if database is unavailable or no settings exist.
    """
    defaults = {
        "days_1_4_price": 65.0,      # 1-4 days anchor
        "week1_base_price": 85.0,    # 7 days anchor
        "week2_base_price": 150.0,   # 14 days anchor
        "daily_increment": 8.0,      # Per-day increment between anchors
        "tier_increment": 5.0,       # Early -> Standard -> Late increment
        "peak_day_increment": 0.0,   # Added for peak day bookings (Fri/Sat drop-off, Sun/Mon/Tue pickup)
        "show_price_range": False,   # False = "From £X", True = "£X-£Y" range
    }

    try:
        import psycopg2
        database_url = os.getenv("DATABASE_URL")

        if not database_url:
            return defaults

        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT days_1_4_price, week1_base_price, week2_base_price,
                   daily_increment, tier_increment, peak_day_increment, show_price_range
            FROM pricing_settings LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return {
                "days_1_4_price": float(row[0]) if row[0] else defaults["days_1_4_price"],
                "week1_base_price": float(row[1]) if row[1] else defaults["week1_base_price"],
                "week2_base_price": float(row[2]) if row[2] else defaults["week2_base_price"],
                "daily_increment": float(row[3]) if row[3] is not None else defaults["daily_increment"],
                "tier_increment": float(row[4]) if row[4] is not None else defaults["tier_increment"],
                "peak_day_increment": float(row[5]) if row[5] is not None else defaults["peak_day_increment"],
                "show_price_range": bool(row[6]) if row[6] is not None else defaults["show_price_range"],
            }
        return defaults
    except Exception:
        # If anything fails, use defaults
        return defaults


def get_base_price_for_duration(duration_days: int, pricing: dict = None) -> float:
    """
    Get the base (early tier) price for a given duration using anchor pricing.

    Anchor prices: 1-4 days, 7 days (1 week), 14 days (2 weeks)
    In-between days use the previous anchor + daily increments.

    Pricing logic:
    - Days 1-4: Base 1-4 days price
    - Days 5-6: Base 1-4 + (days - 4) * daily_increment
    - Day 7: Base 1 week price
    - Days 8-13: Base 1 week + (days - 7) * daily_increment
    - Day 14: Base 2 weeks price
    - Days 15+: Base 2 weeks + (days - 14) * daily_increment

    Args:
        duration_days: Number of days for the trip (1+)
        pricing: Optional pricing dict, fetched from DB if not provided

    Returns:
        Base price in pounds for the early booking tier
    """
    if pricing is None:
        pricing = get_pricing_from_db()

    daily_inc = pricing["daily_increment"]

    if duration_days <= 4:
        # 1-4 days: use anchor price
        return pricing["days_1_4_price"]
    elif duration_days <= 6:
        # 5-6 days: 1-4 anchor + increments
        extra_days = duration_days - 4
        return pricing["days_1_4_price"] + (extra_days * daily_inc)
    elif duration_days == 7:
        # 7 days: use 1 week anchor price
        return pricing["week1_base_price"]
    elif duration_days <= 13:
        # 8-13 days: 1 week anchor + increments
        extra_days = duration_days - 7
        return pricing["week1_base_price"] + (extra_days * daily_inc)
    elif duration_days == 14:
        # 14 days: use 2 weeks anchor price
        return pricing["week2_base_price"]
    else:
        # 15+ days: 2 weeks anchor + increments
        extra_days = duration_days - 14
        return pricing["week2_base_price"] + (extra_days * daily_inc)


def is_peak_day_booking(drop_off_date: date, pickup_date: date) -> bool:
    """
    Check if a booking qualifies for peak day pricing.

    Peak day criteria (either condition triggers peak pricing):
    - Drop-off is on Friday (4) or Saturday (5)
    - OR Pickup is on Sunday (6), Monday (0), or Tuesday (1)

    Args:
        drop_off_date: The date of drop-off
        pickup_date: The date of pickup

    Returns:
        True if booking qualifies for peak day increment
    """
    # weekday() returns 0=Monday, 1=Tuesday, ..., 4=Friday, 5=Saturday, 6=Sunday
    drop_off_day = drop_off_date.weekday()
    pickup_day = pickup_date.weekday()

    # Drop-off on Friday (4) or Saturday (5)
    is_peak_dropoff = drop_off_day in (4, 5)

    # Pickup on Sunday (6), Monday (0), or Tuesday (1)
    is_peak_pickup = pickup_day in (6, 0, 1)

    return is_peak_dropoff or is_peak_pickup


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

    # Maximum concurrent bookings (parking spots). Increased 60 → 64 on
    # 2026-05-23 to match the frontend cap. When any day in a customer's
    # requested [drop-off, pick-up] range hits this number, new bookings
    # are rejected at booking_service.create_booking — pick-ups are never
    # blocked because they don't add occupancy.
    MAX_PARKING_SPOTS = 64

    # Package durations (in days)
    PACKAGE_DURATIONS = {
        "quick": 7,    # 1 week
        "longer": 14,  # 2 weeks
    }

    @classmethod
    def get_all_duration_prices(cls) -> dict:
        """
        Get current pricing for all durations using anchor pricing with daily increments.

        Returns:
            Dict with prices for each day (1-21+) with early/standard/late tiers
        """
        pricing = get_pricing_from_db()
        tier_inc = pricing["tier_increment"]

        result = {}

        # Generate prices for days 1-21 (and beyond can be calculated on demand)
        for days in range(1, 22):
            base_price = get_base_price_for_duration(days, pricing)
            result[str(days)] = {
                "early": base_price,
                "standard": base_price + tier_inc,
                "late": base_price + (tier_inc * 2),
            }

        return result

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
    def calculate_price_for_duration(cls, duration_days: int, drop_off_date: date, pickup_date: date = None) -> float:
        """
        Calculate the price based on trip duration and advance booking tier.

        Uses anchor pricing with daily increments:
        - 1-4 days: Base price
        - 5-6 days: 1-4 base + daily increments
        - 7 days: 1 week base
        - 8-13 days: 1 week base + daily increments
        - 14 days: 2 weeks base
        - 15+ days: 2 weeks base + daily increments

        Also applies peak day increment when:
        - Drop-off is on Friday or Saturday
        - Pickup is on Sunday, Monday, or Tuesday

        Args:
            duration_days: Number of days for the trip (1+)
            drop_off_date: The date of drop-off
            pickup_date: The date of pickup (optional, calculated from duration if not provided)

        Returns:
            The price in pounds
        """
        advance_tier = cls.get_advance_tier(drop_off_date)
        pricing = get_pricing_from_db()
        tier_inc = pricing["tier_increment"]
        peak_inc = pricing["peak_day_increment"]

        # Get base price using anchor pricing
        base_price = get_base_price_for_duration(duration_days, pricing)

        # Apply tier increment based on advance booking
        if advance_tier == "early":
            price = base_price
        elif advance_tier == "standard":
            price = base_price + tier_inc
        else:  # late
            price = base_price + (tier_inc * 2)

        # Apply peak day increment if applicable
        if pickup_date is None:
            # Calculate pickup_date from drop_off_date and duration
            pickup_date = drop_off_date + timedelta(days=duration_days)

        if peak_inc > 0 and is_peak_day_booking(drop_off_date, pickup_date):
            price += peak_inc

        return price

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

    EARLY_ARRIVAL_CUTOFF_HHMM = (2, 0)

    @classmethod
    def billing_pickup_date(cls, pickup_date: date, flight_arrival_time: Optional[str]) -> date:
        """Apply the early-morning arrival rule for billing.

        Keyed off the flight arrival time, not the customer-meet time. A flight
        landing in [00:00, 02:00) means the parking effectively ended the night
        before, so we bill as the previous day. Late-evening arrivals (e.g. 23:30,
        23:59) leave billing at the calendar pickup_date — the customer-meet may
        wrap past midnight, but the trip itself ended on pickup_date.

        Args:
            pickup_date: The booked return date (= flight arrival date).
            flight_arrival_time: HH:MM string for the flight arrival time. May be
                None / malformed — in which case no adjustment is made.

        Returns:
            Effective billing pickup date.
        """
        if not flight_arrival_time:
            return pickup_date
        try:
            h, m = map(int, flight_arrival_time.split(":")[:2])
        except (ValueError, AttributeError):
            return pickup_date
        if not (0 <= h < 24 and 0 <= m < 60):
            return pickup_date
        if (h, m) < cls.EARLY_ARRIVAL_CUTOFF_HHMM:
            return pickup_date - timedelta(days=1)
        return pickup_date

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
        Maps to "quick" (1-7 days) or "longer" (8-60 days) for backwards compatibility.

        Args:
            drop_off_date: The date of drop-off
            pickup_date: The date of pickup

        Returns:
            "quick" for 1-7 days, "longer" for 8-60 days

        Raises:
            ValueError: If duration is less than 1 or more than 60 days
        """
        duration = (pickup_date - drop_off_date).days

        if duration < 1:
            raise ValueError(f"Invalid duration: {duration} days. Must be at least 1 day.")
        elif duration > 60:
            raise ValueError(f"Invalid duration: {duration} days. Maximum is 60 days.")
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
