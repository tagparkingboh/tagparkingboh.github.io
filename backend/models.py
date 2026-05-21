"""
Data models for the TAG booking system.
"""
from datetime import date as date_type, time, datetime
from typing import Optional, Literal, List, Union, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class SlotType(str, Enum):
    """Drop-off time slot types."""
    EARLY = "165"     # 2.75 hours (2¾h) before departure
    STANDARD = "120"  # 2 hours before departure
    LATE = "90"       # 1.5 hours (1½h) before departure


class FlightType(str, Enum):
    """Flight direction."""
    DEPARTURE = "departure"
    ARRIVAL = "arrival"


class TimeSlot(BaseModel):
    """Represents a bookable time slot for drop-off."""
    slot_id: str
    slot_type: SlotType
    drop_off_date: date_type
    drop_off_time: time
    flight_date: date_type
    flight_time: time
    flight_number: str
    airline_code: str
    label: str  # e.g., "2¾ hours before" or "2 hours before"
    is_available: bool = True
    booking_id: Optional[str] = None


class Flight(BaseModel):
    """Represents a flight from the schedule."""
    date: date_type
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
    drop_off_date: date_type
    drop_off_slot_type: SlotType
    flight_date: date_type
    flight_time: str  # "HH:MM"
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    # Return trip
    pickup_date: date_type
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

    drop_off_date: date_type
    drop_off_time: time  # Calculated from slot
    drop_off_slot_type: SlotType
    flight_date: date_type
    flight_time: time
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    pickup_date: date_type
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
    flight_date: date_type
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
    drop_off_date: date_type
    drop_off_time: str  # "HH:MM" - admin can set any time
    flight_date: date_type
    flight_time: str  # "HH:MM"
    flight_number: str
    airline_code: str
    airline_name: str
    destination_code: str
    destination_name: str

    # Return trip
    pickup_date: date_type
    flight_arrival_date: Optional[date_type] = None  # Canonical landing date (pickup_date may roll past midnight)
    return_flight_time: str
    return_flight_number: str

    # Vehicle details
    registration: str
    make: str
    model: Optional[str] = None  # Deprecated - DVLA API doesn't provide model
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
    model: Optional[str] = None  # Deprecated - DVLA API doesn't provide model
    colour: str
    tax_status: Optional[str] = None
    mot_status: Optional[str] = None
    tax_due_date: Optional[date_type] = None
    mot_expiry_date: Optional[date_type] = None

    # Trip details
    dropoff_date: date_type
    dropoff_time: str  # "HH:MM"
    pickup_date: date_type
    pickup_time: str  # "HH:MM"
    flight_arrival_date: Optional[date_type] = None  # Canonical landing date (pickup_date may roll past midnight)

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


# ============================================================================
# Promotion Models (Promo Code Generation System)
# ============================================================================

class PromotionCreate(BaseModel):
    """Request to create a new promotion campaign."""
    name: str
    description: Optional[str] = None
    discount_percent: int  # 10, 20, 100
    total_codes: int  # Number of codes to generate


class PromotionResponse(BaseModel):
    """Response model for a promotion."""
    id: int
    name: str
    description: Optional[str] = None
    discount_percent: int
    total_codes: int
    codes_sent: int
    codes_used: int
    codes_available: int  # Computed: total_codes - codes_sent
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromoCodeResponse(BaseModel):
    """Response model for an individual promo code."""
    id: int
    code: str
    promotion_id: int
    discount_percent: int  # From parent promotion

    # Recipient info
    recipient_email: Optional[str] = None
    recipient_first_name: Optional[str] = None
    recipient_last_name: Optional[str] = None
    customer_id: Optional[int] = None
    subscriber_id: Optional[int] = None

    # Status
    email_sent: bool
    email_sent_at: Optional[datetime] = None
    is_used: bool
    used_at: Optional[datetime] = None
    booking_id: Optional[int] = None
    booking_reference: Optional[str] = None  # For display

    # Social media tracking
    shared_on_socials: bool = False
    shared_on_socials_at: Optional[datetime] = None

    # Expiry - if set, code is only valid before this date/time (UK timezone)
    expires_at: Optional[datetime] = None
    is_expired: bool = False  # Computed field for convenience

    created_at: datetime

    class Config:
        from_attributes = True


class PromoRecipient(BaseModel):
    """A recipient for promo code email."""
    email: str
    first_name: str
    last_name: Optional[str] = None
    customer_id: Optional[int] = None
    subscriber_id: Optional[int] = None
    source: str = "new"  # "customer", "subscriber", "new"


class SendPromoEmailsRequest(BaseModel):
    """Request to send promo emails to selected recipients."""
    promotion_id: int
    recipients: List[PromoRecipient]
    email_subject: str  # Can contain {{FIRST_NAME}}
    email_body: str  # HTML body with {{FIRST_NAME}}, {{PROMO_CODE}} placeholders


class SendPromoEmailsResponse(BaseModel):
    """Response after sending promo emails."""
    success: bool
    total_sent: int
    total_failed: int
    errors: List[str] = []


# ============================================================================
# Roster & Staff Management Models
# ============================================================================

class ShiftTypeEnum(str, Enum):
    """Type of roster shift - based on time slots throughout the day."""
    # Part-time shift slots
    EARLY_MORNING = "early_morning"    # ~03:50 - 07:00
    MORNING = "morning"                 # ~07:00 - 11:00
    MIDDAY = "midday"                   # ~11:00 - 14:00
    AFTERNOON = "afternoon"             # ~14:00 - 17:30
    LATE_AFTERNOON = "late_afternoon"   # ~17:30 - 21:00
    EVENING = "evening"                 # ~21:00 - 01:20
    # Full-time shift slots
    FULL_MORNING = "full_morning"       # ~03:50 - 14:00
    FULL_AFTERNOON = "full_afternoon"   # ~11:00 - 21:00
    FULL_EVENING = "full_evening"       # ~17:30 - 01:20


class ShiftStatusEnum(str, Enum):
    """Status of a roster shift."""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class EmployeeCreate(BaseModel):
    """Request to create a new employee."""
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    email: str
    phone: str


class EmployeeUpdate(BaseModel):
    """Request to update an employee."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[str] = None
    phone: Optional[str] = None


class EmployeeResponse(BaseModel):
    """Response model for an employee."""
    id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    is_admin: bool
    is_active: bool
    auto_assign_excluded: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class RosterShiftCreate(BaseModel):
    """Request to create a roster shift."""
    staff_id: Optional[int] = None  # Nullable = unassigned
    booking_id: Optional[int] = None  # DEPRECATED - use booking_ids
    booking_ids: Optional[List[int]] = None  # Multiple bookings per shift
    date: date_type  # Start date
    end_date: Optional[date_type] = None  # End date (for overnight shifts, defaults to date)
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    shift_type: ShiftTypeEnum
    status: ShiftStatusEnum = ShiftStatusEnum.SCHEDULED
    notes: Optional[str] = None
    # Driver-type targeting for unassigned shifts. Defaults to 'jockey' for
    # back-compat. Admin sets to 'fleet' when creating fleet-only shifts.
    # When staff_id is set, the assigned user's driver_type is the source of
    # truth at filter time — this field is informational for `?` shifts.
    intended_driver_type: Literal["jockey", "fleet"] = "jockey"


class RosterShiftUpdate(BaseModel):
    """Request to update a roster shift."""
    # Use special marker to distinguish "not provided" from "explicitly set to null"
    # When staff_id is explicitly set to null in JSON, we want to unassign the shift
    staff_id: Optional[int] = None
    staff_id_provided: bool = False  # Set to True when staff_id is explicitly in the request
    booking_id: Optional[int] = None  # DEPRECATED - use booking_ids
    booking_ids: Optional[List[int]] = None  # Multiple bookings per shift
    date: Optional[date_type] = None  # Start date
    end_date: Optional[date_type] = None  # End date (for overnight shifts)
    start_time: Optional[str] = None  # "HH:MM"
    end_time: Optional[str] = None  # "HH:MM"
    shift_type: Optional[ShiftTypeEnum] = None
    status: Optional[ShiftStatusEnum] = None
    notes: Optional[str] = None
    intended_driver_type: Optional[Literal["jockey", "fleet"]] = None

    @model_validator(mode='before')
    @classmethod
    def check_staff_id_provided(cls, data):
        """Track if staff_id was explicitly provided in the request."""
        if isinstance(data, dict) and 'staff_id' in data:
            data['staff_id_provided'] = True
        return data


class RosterShiftDuplicateRequest(BaseModel):
    """Body for POST /api/roster/{id}/duplicate (Roster Planner v3 Phase 2).

    Modes:
      - date copy: only `target_date` set → 1 copy on the target date,
        same staff/time, `created_source='manual'`, bookings re-linked by
        event-time membership.
      - staff fanout: only `staff_ids` (+ optional unassigned flags) set →
        N copies on the source's date, one per target staff.
      - both set → bulk staff-add (deferred per spec; endpoint returns 422).
    """
    target_date: Optional[date_type] = None
    staff_ids: Optional[List[int]] = None
    add_unassigned_jockey: bool = False
    add_unassigned_fleet: bool = False


class RosterShiftMergeRequest(BaseModel):
    """Body for POST /api/roster/{id}/merge.

    Adjacent same-day (allowing overnight wrap), same staff or one
    unassigned. Combines into a single row spanning the union of the two
    windows; loser row is deleted; booking links union into the survivor.
    """
    other_shift_id: int


class RosterShiftSplitRequest(BaseModel):
    """Body for POST /api/roster/{id}/split.

    `split_at_time` must be strictly inside (start_time, end_time). Bookings
    are re-distributed by event_time using right-inclusive semantics — an
    event at exactly `split_at_time` goes to the second half.
    """
    split_at_time: str  # "HH:MM"


class LinkedBookingInfo(BaseModel):
    """Info about a booking linked to a shift."""
    id: int
    reference: str
    type: str  # "dropoff" or "pickup"
    customer_name: str
    time: Optional[str] = None  # The dropoff/pickup time
    flight_number: Optional[str] = None
    destination: Optional[str] = None  # destination for dropoff, origin for pickup


class RosterShiftResponse(BaseModel):
    """Response model for a roster shift."""
    id: int
    staff_id: Optional[int] = None
    staff_first_name: Optional[str] = None
    staff_last_name: Optional[str] = None
    staff_initials: Optional[str] = None
    # DEPRECATED single booking fields - kept for backwards compatibility
    booking_id: Optional[int] = None
    booking_reference: Optional[str] = None
    booking_type: Optional[str] = None  # "dropoff" or "pickup"
    booking_customer_name: Optional[str] = None
    booking_time: Optional[str] = None  # The dropoff/pickup time
    booking_flight_number: Optional[str] = None
    booking_destination: Optional[str] = None  # destination for dropoff, origin for pickup
    # New: multiple bookings per shift
    bookings: List[LinkedBookingInfo] = []
    date: date_type  # Start date
    end_date: Optional[date_type] = None  # End date (for overnight shifts)
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    shift_type: str
    status: str
    notes: Optional[str] = None
    intended_driver_type: str = "jockey"  # 'jockey' | 'fleet'
    # Surfaced so the v3 admin Calendar can colour / sort badges differently
    # when toggle = 'All' (mixing auto + manual on the same day cell).
    created_source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutoAssignRequest(BaseModel):
    """Request to auto-generate shifts from bookings."""
    date_from: date_type
    date_to: date_type
    clear_existing: bool = False  # If True, delete scheduled shifts first


class AutoAssignResponse(BaseModel):
    """Response after auto-generating shifts."""
    success: bool
    shifts_created: int
    shifts_deleted: int = 0
    shifts: List[RosterShiftResponse] = []


class OperationalWarning(BaseModel):
    """Warning for operational rule violations."""
    shift_id: Optional[int] = None
    rule: str
    message: str
    severity: str = "warning"  # "warning" or "error"


class TeamShiftResponse(BaseModel):
    """View-only response for teammates' shifts on the Employee calendar.

    Deliberately stripped: no shift id, no staff_id, no shift_type, no notes,
    no booking refs. Initials render in the grid; full name + phone show in
    the per-shift popover for coworker coordination.
    """
    initials: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    date: date_type
    end_date: date_type
    start_time: str  # HH:MM
    end_time: str    # HH:MM


# =====================================================================================
# Roster Planner — Phase 1 (read-only preview)
# Rules locked 2026-04-24, see backend/docs/SPEC.md § Roster Planner.
# =====================================================================================

class RosterPlannerStaffingThreshold(BaseModel):
    """One bucket of the staffing curve. The engine picks the first bucket whose
    max_peak is >= the peak concurrent event count in any 15-min window."""
    max_peak: int = Field(..., ge=1)
    staff: int = Field(..., ge=1)


class RosterPlannerSettingsResponse(BaseModel):
    """Read-only snapshot of current planner settings."""
    # Optional / 0 → no upper bound on the planning window (locked
    # 2026-05-05). Engine considers every CONFIRMED booking from today
    # onwards regardless of how far ahead the trip date is.
    window_days: Optional[int] = None
    gap_max_minutes: int
    mixed_gap_max_minutes: int
    start_buffer_minutes: int
    end_buffer_minutes: int
    staffing_thresholds: List[RosterPlannerStaffingThreshold]
    max_hours_per_week: int
    min_rest_hours: int
    untouchable_hours: int
    preview_enabled: bool
    commit_enabled: bool


class RosterPlannerSettingsUpdate(BaseModel):
    """Partial update for planner settings. Unset fields are not modified.

    Uses Pydantic's default `exclude_unset` semantics via `model_dump(exclude_unset=True)`
    at the endpoint — so a PATCH with only `{max_hours_per_week: 45}` leaves every
    other setting untouched (per SPEC.md 2026-04-06 null-vs-not-provided rule).
    """
    # `window_days` upper bound was 90 days under the v1 cap. Now nullable
    # (locked 2026-05-05): pass null or 0 to remove the planning window cap;
    # any positive int still bounds the engine to that many days.
    window_days: Optional[int] = Field(default=None, ge=0, le=3650)
    gap_max_minutes: Optional[int] = Field(default=None, ge=0, le=480)
    mixed_gap_max_minutes: Optional[int] = Field(default=None, ge=0, le=720)
    start_buffer_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    end_buffer_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    staffing_thresholds: Optional[List[RosterPlannerStaffingThreshold]] = None
    max_hours_per_week: Optional[int] = Field(default=None, ge=1, le=168)
    min_rest_hours: Optional[int] = Field(default=None, ge=0, le=48)
    untouchable_hours: Optional[int] = Field(default=None, ge=0, le=168)
    preview_enabled: Optional[bool] = None
    commit_enabled: Optional[bool] = None


class ProposedEvent(BaseModel):
    """A single drop-off or pick-up covered by a proposed shift."""
    booking_id: int
    booking_reference: str
    event_type: Literal["drop_off", "pick_up"]
    event_time: datetime  # Europe/London aware
    customer_name: Optional[str] = None
    flight_number: Optional[str] = None
    destination: Optional[str] = None
    # booking.status at the time the proposal was rendered. Mostly 'confirmed'
    # (engine only plans for those), but untouched_for_reason cards surface
    # whatever's actually linked to the saved shift — including 'refunded'
    # so the planner UI can render the REFUNDED indicator.
    status: Optional[str] = None


class ProposedShift(BaseModel):
    """A shift the engine proposes to create or extend.

    `kind`:
      - `new`: create a brand-new shift.
      - `extend`: extend an existing `shift_id` (update its start/end and add links).
      - `untouched_for_reason`: an existing shift the engine reports but won't modify.
    """
    kind: Literal["new", "extend", "untouched_for_reason"]
    shift_id: Optional[int] = None  # set for extend / untouched_for_reason
    date: date_type
    end_date: Optional[date_type] = None  # for overnight shifts
    start_time: time
    end_time: time
    shift_type: ShiftTypeEnum
    is_custom_range: bool = False  # True when times don't match a canonical ShiftType window
    staff_id: Optional[int] = None  # None = unassigned (?)
    staff_initials: Optional[str] = None  # e.g. "KA"
    events: List[ProposedEvent]
    peak_concurrent_count: int
    required_staff_count: int
    reason: str  # human-readable rationale, e.g. "3 drop-offs within 45 min"
    untouched_reason: Optional[str] = None  # set when kind=untouched_for_reason
    # Provenance of an existing saved shift (kind=untouched_for_reason only):
    # 'manual' = admin created via Calendar; 'planner' = engine commit.
    created_source: Optional[str] = None
    planner_run_id: Optional[str] = None


class RosterProposalWarning(BaseModel):
    """A concern raised by the engine — coverage gap, constraint collision, etc."""
    rule: str  # e.g. "max_hours_per_week", "unmanned", "preference_violation"
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    booking_references: List[str] = Field(default_factory=list)
    staff_id: Optional[int] = None
    # Per-jockey reason for being filtered out of this shift. Only populated
    # for `rule="unmanned"` warnings — see explain_unmanned() in the engine.
    exclusions: List[dict] = Field(default_factory=list)


class RosterProposalResponse(BaseModel):
    """Full JSON result of `POST /api/admin/qa/roster-planner/propose`.

    Deterministic: same DB state + same `now` produces the same output.
    """
    run_id: str  # UUID for audit / replay / undo
    generated_at: datetime
    window_start: date_type
    # window_end may carry the sentinel date(9999, 12, 31) when the engine
    # is configured with no upper bound (window_days = None / 0). Frontends
    # can detect that case and render "no upper bound".
    window_end: date_type
    settings_snapshot: RosterPlannerSettingsResponse
    proposed_shifts: List[ProposedShift]
    warnings: List[RosterProposalWarning]
    summary: dict  # counts: { new_shifts, extended_shifts, untouched_shifts, unmanned_events, staff_hit_max_hours }
    # Snapshot of jockey preferences + in-window holidays — rendered in
    # the QA panel so admins can sanity-check assignments. Each jockey
    # entry also carries `predicted_hours_by_week` + `predicted_hours_total`
    # computed from the engine's in-run accumulator (purely from this
    # proposal — saved roster_shifts hours are not counted).
    jockeys: List[dict] = Field(default_factory=list)
    # Pulled out alongside jockeys for the UI's at-cap highlighting;
    # mirrors settings_snapshot.max_hours_per_week.
    max_hours_per_week: Optional[int] = None


class PlannerRunListItem(BaseModel):
    """One row in `GET /runs` — slim list view for the QA history strip."""
    run_id: str
    triggered_at: datetime
    trigger_event: str
    trigger_ref: Optional[str] = None
    window_start: date_type
    # window_end may carry the sentinel date(9999, 12, 31) when the engine
    # is configured with no upper bound (window_days = None / 0). Frontends
    # can detect that case and render "no upper bound".
    window_end: date_type
    duration_ms: Optional[int] = None
    has_error: bool = False
    summary: Optional[dict] = None  # counts pulled from proposal_json so the strip shows volume at a glance


class CommittedShiftSnapshot(BaseModel):
    """Live state of a committed roster_shift, for the planner detail UI.

    Represents what's actually on disk *now* for a proposal that the admin
    committed via /api/admin/qa/roster-planner/commit. Reflects post-commit
    overrides (unassign → staff_id=None) AND any subsequent claims/edits
    (jockey claimed an unassigned shift → staff_id=that jockey).
    """
    shift_id: int
    staff_id: Optional[int] = None
    staff_initials: Optional[str] = None
    status: str  # 'scheduled' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled'
    intended_driver_type: Optional[str] = None


class PlannerRunDetail(BaseModel):
    """Full row body for `GET /runs/{run_id}` — the proposal as recorded.

    `proposal_json` and `diff_vs_current_json` are returned as already-parsed
    objects so the QA UI can render directly without a second JSON.parse step.

    `committed_indexes` lists the proposed_shifts positions that currently
    have at least one matching scheduled row in roster_shifts (matched by
    date + start_time + end_time on rows where planner_run_id == this run).
    Survives undo (drops back to empty) and re-commit (refills). FE uses it
    to hide the commit checkbox on already-committed proposals so admins
    can't accidentally re-tick and hit a 409 overlap.

    `committed_shifts_by_index` maps each committed proposal index to the
    list of live roster_shifts that index produced. Lets the FE render the
    *current* state (unassigned `?`, claimed by X, duplicated to N drivers)
    instead of the engine's original suggestion. List-per-index because a
    duplicate override yields one proposal → N shifts.
    """
    run_id: str
    triggered_at: datetime
    trigger_event: str
    trigger_ref: Optional[str] = None
    window_start: date_type
    # window_end may carry the sentinel date(9999, 12, 31) when the engine
    # is configured with no upper bound (window_days = None / 0). Frontends
    # can detect that case and render "no upper bound".
    window_end: date_type
    proposal: Optional[dict] = None
    diff_vs_current: Optional[dict] = None
    warnings: List[dict] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    error_text: Optional[str] = None
    committed_indexes: List[int] = Field(default_factory=list)
    committed_shifts_by_index: Dict[int, List[CommittedShiftSnapshot]] = Field(
        default_factory=dict
    )


class ProposalOverride(BaseModel):
    """Per-proposal commit-time override.

    Mirrors the action-button shapes admins use in the planner UI. Sent on
    POST /commit alongside proposal_indexes so the admin's "what I'd do
    differently" choice actually reaches the roster.

    Phase 3.5 honours: 'unassign', 'delete', 'duplicate'. Phase 3.6 will add
    'merge' and 'split' (those need multi-proposal coordination).
    """
    action: Literal["unassign", "delete", "duplicate", "merge", "split"]
    # duplicate
    target_staff_ids: Optional[List[int]] = None
    # duplicate — extra unassigned copies tagged for jockey/fleet so admins
    # can fan out a shift into "+1 unassigned jockey slot" without picking
    # a specific person upfront.
    add_unassigned_jockey: bool = False
    add_unassigned_fleet: bool = False
    # merge (Phase 3.6)
    merge_with_index: Optional[int] = None
    merged_staff_id: Optional[int] = None
    # split (Phase 3.6)
    split_at_time: Optional[time] = None
    first_half_staff_id: Optional[int] = None
    second_half_staff_id: Optional[int] = None


class PlannerCommitRequest(BaseModel):
    """Body of POST /api/admin/qa/roster-planner/commit.

    `proposal_indexes` references entries in the run's `proposed_shifts` list
    (by position). Phase 3 commits only `kind == 'new'` proposals on empty
    slots; any proposal whose [start, end] overlaps an existing shift for the
    same staff_id is rejected with the whole transaction aborted (atomic).

    `overrides` (optional) maps proposal_index → ProposalOverride for shifts
    the admin wants to modify before commit (unassign / delete / duplicate /
    merge / split). An override applies only if its index is also in
    proposal_indexes; an override on an unticked index is ignored.
    """
    run_id: str
    proposal_indexes: List[int]
    overrides: Dict[int, ProposalOverride] = Field(default_factory=dict)


class PlannerCommitResponse(BaseModel):
    """Response from POST /api/admin/qa/roster-planner/commit."""
    run_id: str
    shifts_created: int
    shift_ids: List[int]


class PlannerUndoResponse(BaseModel):
    """Response from DELETE /api/admin/qa/roster-planner/runs/{run_id}.

    Idempotent — undoing a run with no remaining engine-created scheduled
    shifts returns shifts_deleted=0, no error.
    """
    run_id: str
    shifts_deleted: int


class PlannerRunFeedbackOverride(BaseModel):
    """Structured "what I would have done" capture from the edit modal
    and the per-card action buttons (Duplicate / Merge / Split / Delete).

    All fields optional — admin captures only what they want to change.
    Engine never consumes this; it's QA-side review data sitting next to
    the free-text comment.

    Field set by action:
      - (no action set) → free edit (staff_id / start_time / end_time)
      - action='delete' → no extra fields
      - action='duplicate' → target_staff_ids list
      - action='merge' → merge_direction ('left' or 'right')
      - action='split' → split_at_time + first_half_staff_id + second_half_staff_id
    """
    # Existing free-edit fields (no `action` set)
    staff_id: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None

    # Action button fields
    action: Optional[Literal["delete", "duplicate", "merge", "split", "unassign"]] = None

    # Duplicate
    target_staff_ids: Optional[List[int]] = None

    # Merge
    merge_direction: Optional[Literal["left", "right"]] = None
    merged_staff_id: Optional[int] = None  # staff for the resulting merged shift

    # Split
    split_at_time: Optional[time] = None
    first_half_start_time: Optional[time] = None  # extends BEFORE source.start_time
    first_half_staff_id: Optional[int] = None
    second_half_end_time: Optional[time] = None   # extends AFTER  source.end_time
    second_half_staff_id: Optional[int] = None


class PlannerRunFeedbackCreate(BaseModel):
    """Body of POST /api/admin/qa/roster-planner/runs/{run_id}/feedback.

    Captures one QA review of an engine assignment decision. The shift
    fingerprint (date + start/end + staff_id) is denormalised onto the row
    so it survives the parent run being pruned and supports cross-run
    pattern queries (see PlannerRunFeedback model docstring).
    """
    shift_date: date_type
    shift_start_time: Optional[time] = None
    shift_end_time: Optional[time] = None
    shift_staff_id: Optional[int] = None
    proposed_shift_index: Optional[int] = None
    severity: Literal["blocker", "issue", "note"]
    comment: str = Field(min_length=1, max_length=4000)
    override: Optional[PlannerRunFeedbackOverride] = None


class PlannerRunFeedbackResponse(BaseModel):
    """One feedback row, suitable for the modal's prior-feedback list."""
    id: int
    run_id: str
    shift_date: date_type
    shift_start_time: Optional[time] = None
    shift_end_time: Optional[time] = None
    shift_staff_id: Optional[int] = None
    proposed_shift_index: Optional[int] = None
    severity: str
    comment: str
    override: Optional[PlannerRunFeedbackOverride] = None
    submitted_by: Optional[int] = None
    submitted_at: datetime
