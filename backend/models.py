"""
Data models for the TAG booking system.
"""
from datetime import date, time, datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class SlotType(str, Enum):
    """Drop-off time slot types."""
    EARLY = "165"  # 2 hours 45 minutes before departure
    LATE = "120"   # 2 hours before departure


class FlightType(str, Enum):
    """Flight direction."""
    DEPARTURE = "departure"
    ARRIVAL = "arrival"


class TimeSlot(BaseModel):
    """Represents a bookable time slot for drop-off."""
    slot_id: str
    slot_type: SlotType
    drop_off_date: date
    drop_off_time: time
    flight_date: date
    flight_time: time
    flight_number: str
    airline_code: str
    label: str  # e.g., "2¾ hours before" or "2 hours before"
    is_available: bool = True
    booking_id: Optional[str] = None


class Flight(BaseModel):
    """Represents a flight from the schedule."""
    date: date
    type: FlightType
    time: time
    airline_code: str = Field(alias="airlineCode")
    airline_name: str = Field(alias="airlineName")
    flight_number: str = Field(alias="flightNumber")
    # For departures
    destination_code: Optional[str] = Field(default=None, alias="destinationCode")
    destination_name: Optional[str] = Field(default=None, alias="destinationName")
    # For arrivals
    origin_code: Optional[str] = Field(default=None, alias="originCode")
    origin_name: Optional[str] = Field(default=None, alias="originName")
    departure_time: Optional[time] = Field(default=None, alias="departureTime")

    class Config:
        populate_by_name = True

    @field_validator('time', 'departure_time', mode='before')
    @classmethod
    def parse_time(cls, v):
        if v is None:
            return None
        if isinstance(v, time):
            return v
        if isinstance(v, str):
            parts = v.split(':')
            return time(int(parts[0]), int(parts[1]))
        return v

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return datetime.strptime(v, '%Y-%m-%d').date()
        return v


class BookingRequest(BaseModel):
    """Request to create a booking."""
    # Contact details
    first_name: str
    last_name: str
    email: str
    phone: str

    # Trip details
    drop_off_date: date
    drop_off_slot_type: SlotType
    flight_date: date
    flight_time: str  # "HH:MM"
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    # Return trip
    pickup_date: date
    return_flight_time: str
    return_flight_number: str

    # Vehicle details
    registration: str
    make: str
    model: str
    colour: str

    # Package
    package: Literal["quick", "longer"]

    # Billing
    billing_address1: str
    billing_address2: Optional[str] = None
    billing_city: str
    billing_county: Optional[str] = None
    billing_postcode: str
    billing_country: str = "United Kingdom"

    # Customer-provided departure time override (optional)
    # When True, customer has corrected the flight time from the schedule
    dropoff_time_override: bool = False
    dropoff_scheduled_time: Optional[str] = None  # Original time from flight table "HH:MM"

    # Manual departure entry (optional)
    # When True, customer entered flight details manually (flight not in system)
    dropoff_manual_entry: bool = False

    # Customer-provided arrival time override (optional)
    pickup_time_override: bool = False
    pickup_scheduled_time: Optional[str] = None  # Original time from flight table "HH:MM"

    # Manual arrival entry (optional)
    pickup_manual_entry: bool = False
    pickup_origin_code: Optional[str] = None  # For manual entries
    pickup_origin_name: Optional[str] = None  # For manual entries


class Booking(BaseModel):
    """A confirmed booking."""
    booking_id: str
    created_at: datetime
    status: Literal["confirmed", "cancelled", "completed"] = "confirmed"

    # All fields from BookingRequest
    first_name: str
    last_name: str
    email: str
    phone: str

    drop_off_date: date
    drop_off_time: time  # Calculated from slot
    drop_off_slot_type: SlotType
    flight_date: date
    flight_time: time
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    pickup_date: date
    return_flight_time: time
    return_flight_number: str

    registration: str
    make: str
    model: str
    colour: str

    package: Literal["quick", "longer"]
    price: float

    billing_address1: str
    billing_address2: Optional[str] = None
    billing_city: str
    billing_county: Optional[str] = None
    billing_postcode: str
    billing_country: str


class AvailableSlotsResponse(BaseModel):
    """Response containing available time slots for a flight."""
    flight_date: date
    flight_time: str
    flight_number: str
    slots: list[TimeSlot]
    all_slots_booked: bool = False
    contact_message: Optional[str] = None


class AdminBookingRequest(BaseModel):
    """
    Simplified booking request for admin use.
    Allows manual booking without slot restrictions.
    """
    # Contact details
    first_name: str
    last_name: str
    email: str
    phone: str

    # Trip details - admin specifies exact drop-off time
    drop_off_date: date
    drop_off_time: str  # "HH:MM" - admin can set any time
    flight_date: date
    flight_time: str  # "HH:MM"
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    # Return trip
    pickup_date: date
    return_flight_time: str
    return_flight_number: str

    # Vehicle details
    registration: str
    make: str
    model: str
    colour: str

    # Package and pricing
    package: Literal["quick", "longer"]
    custom_price: Optional[float] = None  # Admin can override price

    # Optional billing (admin bookings may not need full billing)
    billing_address1: Optional[str] = None
    billing_city: Optional[str] = None
    billing_postcode: Optional[str] = None
    billing_country: str = "United Kingdom"

    # Admin notes
    admin_notes: Optional[str] = None
    booking_source: str = "admin"  # "admin", "phone", "walk-in"


class ManualBookingRequest(BaseModel):
    """
    Request to create a manual booking with payment link.
    Used when admin creates a booking and sends payment link to customer.
    Booking is NOT confirmed until customer pays via the link.
    """
    # Customer details
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None

    # Billing address
    billing_address1: str
    billing_address2: Optional[str] = None
    billing_city: str
    billing_county: Optional[str] = None
    billing_postcode: str
    billing_country: str = "United Kingdom"

    # Vehicle details
    registration: str
    make: str
    model: str
    colour: str

    # Trip details
    dropoff_date: date
    dropoff_time: str  # "HH:MM"
    pickup_date: date
    pickup_time: str  # "HH:MM"

    # Flight/slot details (optional - for slot availability tracking)
    departure_id: Optional[int] = None
    dropoff_slot: Optional[str] = None  # "early" or "late"

    # Departure flight details
    dropoff_airline_name: Optional[str] = None
    dropoff_destination: Optional[str] = None
    dropoff_flight_number: Optional[str] = None
    # Legacy field name (kept for backwards compatibility)
    departure_flight_number: Optional[str] = None

    # Return flight details
    pickup_airline_name: Optional[str] = None
    pickup_origin: Optional[str] = None
    pickup_flight_number: Optional[str] = None
    # Legacy field name (kept for backwards compatibility)
    return_flight_number: Optional[str] = None

    # Actual flight times
    flight_departure_time: Optional[str] = None  # "HH:MM" - actual flight departure time
    flight_arrival_time: Optional[str] = None  # "HH:MM" - actual flight arrival time

    # Payment
    stripe_payment_link: Optional[str] = None  # Not required for free bookings
    amount_pence: int

    # Promo code (optional)
    promo_code: Optional[str] = None
    is_free_booking: bool = False

    # Notes
    notes: Optional[str] = None



# ============================================================================
# Test Run Models (QA Dashboard)
# ============================================================================

class TestRunCreate(BaseModel):
    """Request to create/update a test run."""
    environment: str = "staging"
    run_type: str = "scheduled"  # scheduled, manual, pr_check
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_total: int = 0
    coverage_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    logs_url: Optional[str] = None
    report_json: Optional[str] = None
    triggered_by: Optional[str] = None


class TestRunResponse(BaseModel):
    """Response model for a test run."""
    id: int
    environment: str
    run_type: str
    status: str
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    tests_total: int
    coverage_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    logs_url: Optional[str] = None
    triggered_by: Optional[str] = None
    pass_rate: float = 0

    class Config:
        from_attributes = True
