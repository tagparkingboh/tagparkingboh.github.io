"""
SQLAlchemy database models for TAG booking system.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Time,
    ForeignKey, Enum, Boolean, Text, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class BookingStatus(enum.Enum):
    """Status of a booking."""
    PENDING = "pending"           # Created, awaiting payment
    CONFIRMED = "confirmed"       # Payment received
    CANCELLED = "cancelled"       # Cancelled by customer or admin
    COMPLETED = "completed"       # Service delivered
    REFUNDED = "refunded"         # Payment refunded


class ShiftType(enum.Enum):
    """Type of roster shift - based on time slots throughout the day.

    Operating hours: 03:50 - 01:20 (21.5 hours)
    Part-time: ~3-4 hour blocks
    Full-time: ~7 hour blocks
    """
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


class ShiftStatus(enum.Enum):
    """Status of a roster shift."""
    SCHEDULED = "scheduled"       # Shift created, not yet confirmed
    CONFIRMED = "confirmed"       # Staff confirmed availability
    IN_PROGRESS = "in_progress"   # Shift currently active
    COMPLETED = "completed"       # Shift finished
    CANCELLED = "cancelled"       # Shift cancelled
    NO_SHOW = "no_show"           # Staff did not show up


class PaymentStatus(enum.Enum):
    """Status of a payment."""
    PENDING = "pending"           # Payment intent created
    PROCESSING = "processing"     # Payment in progress
    SUCCEEDED = "succeeded"       # Payment successful
    FAILED = "failed"             # Payment failed
    REFUNDED = "refunded"         # Payment refunded
    PARTIALLY_REFUNDED = "partially_refunded"


class Customer(Base):
    """Customer contact and billing information."""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)

    # Billing address
    billing_address1 = Column(String(255))
    billing_address2 = Column(String(255))
    billing_city = Column(String(100))
    billing_county = Column(String(100))
    billing_postcode = Column(String(20))
    billing_country = Column(String(100), default="United Kingdom")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    billing_updated_at = Column(DateTime(timezone=True))  # Set when billing info is saved/updated

    # Founder follow-up email tracking (for abandoned leads)
    founder_followup_sent = Column(Boolean, default=False)
    founder_followup_sent_at = Column(DateTime(timezone=True))

    # Marketing attribution ("Where did you hear about us?")
    has_answered_heard_about_us = Column(Boolean, default=False)

    # Relationships
    vehicles = relationship("Vehicle", back_populates="customer")
    bookings = relationship("Booking", back_populates="customer")
    marketing_source = relationship("MarketingSource", back_populates="customer", uselist=False)

    def __repr__(self):
        return f"<Customer {self.first_name} {self.last_name} ({self.email})>"


class Vehicle(Base):
    """Customer vehicle information."""
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    registration = Column(String(20), nullable=False, index=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    colour = Column(String(50), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="vehicles")
    bookings = relationship("Booking", back_populates="vehicle")

    def __repr__(self):
        return f"<Vehicle {self.registration} - {self.make} {self.model}>"


class Booking(Base):
    """Core booking record."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(20), unique=True, nullable=False, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)

    # Snapshot of customer name at time of booking
    # (prevents shared email addresses from overwriting historical booking names)
    customer_first_name = Column(String(100), nullable=True)
    customer_last_name = Column(String(100), nullable=True)

    # Package type: 'daily', 'quick' (1 week), or 'longer' (2 weeks)
    # Nullable for manual bookings where price is set via Stripe link
    package = Column(String(20), nullable=True)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)

    # Drop-off details
    dropoff_date = Column(Date, nullable=False)
    dropoff_time = Column(Time, nullable=False)
    dropoff_flight_number = Column(String(20))
    dropoff_destination = Column(String(100))

    # Flight slot booking (for slot release on cancellation)
    departure_id = Column(Integer, ForeignKey("flight_departures.id"), nullable=True)
    dropoff_slot = Column(String(10), nullable=True)  # "early" or "late"

    # Customer-provided departure time override (when flight time has changed)
    dropoff_time_override = Column(Boolean, default=False)  # True if customer edited time
    dropoff_scheduled_time = Column(Time, nullable=True)  # Original scheduled time from flight table

    # Manual departure entry (when flight not in system - e.g., TUI, new routes)
    dropoff_manual_entry = Column(Boolean, default=False)  # True if fully manual entry
    dropoff_airline_code = Column(String(10), nullable=True)  # e.g., "BY" for TUI
    dropoff_airline_name = Column(String(100), nullable=True)  # e.g., "TUI"

    # Actual flight times (always stored, used for emails and display)
    flight_departure_time = Column(Time, nullable=True)  # Actual flight departure time
    flight_arrival_time = Column(Time, nullable=True)  # Actual flight arrival time

    # Pick-up details
    pickup_date = Column(Date, nullable=False)
    pickup_time = Column(Time)  # Collection time (flight_arrival_time + 30 min)
    pickup_time_from = Column(Time)  # DEPRECATED - to be removed
    pickup_time_to = Column(Time)  # DEPRECATED - to be removed
    pickup_flight_number = Column(String(20))
    pickup_origin = Column(String(100))

    # Flight arrival link (for pickup time recalculation when arrival time changes)
    arrival_id = Column(Integer, ForeignKey("flight_arrivals.id"), nullable=True)

    # Customer-provided arrival time override (when return flight time has changed)
    pickup_time_override = Column(Boolean, default=False)  # True if customer edited time
    pickup_scheduled_time = Column(Time, nullable=True)  # Original scheduled time from flight table

    # Manual arrival entry (when return flight not in system)
    pickup_manual_entry = Column(Boolean, default=False)  # True if fully manual entry
    pickup_airline_code = Column(String(10), nullable=True)
    pickup_airline_name = Column(String(100), nullable=True)

    # Admin notes
    notes = Column(Text)
    admin_notes = Column(Text)  # Internal notes from admin

    # Booking source (online, manual, admin, phone)
    booking_source = Column(String(20), default="online")

    # Frontend session ID (for deduplicating repeated payment intents)
    session_id = Column(String(100), index=True)

    # Email tracking
    confirmation_email_sent = Column(Boolean, default=False)
    confirmation_email_sent_at = Column(DateTime(timezone=True))
    cancellation_email_sent = Column(Boolean, default=False)
    cancellation_email_sent_at = Column(DateTime(timezone=True))
    refund_email_sent = Column(Boolean, default=False)
    refund_email_sent_at = Column(DateTime(timezone=True))
    reminder_2day_sent = Column(Boolean, default=False)
    reminder_2day_sent_at = Column(DateTime(timezone=True))
    thank_you_email_sent = Column(Boolean, default=False)
    thank_you_email_sent_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))  # When booking was marked complete

    # Financial overrides (for manual adjustment of gross/discount values)
    override_gross_pence = Column(Integer, nullable=True)  # Original price before discount
    override_discount_pence = Column(Integer, nullable=True)  # Discount amount

    # Relationships
    customer = relationship("Customer", back_populates="bookings")
    vehicle = relationship("Vehicle", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)
    departure = relationship("FlightDeparture")

    def __repr__(self):
        return f"<Booking {self.reference} - {self.status.value}>"


class Payment(Base):
    """Payment record linked to Stripe."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)

    # Stripe identifiers
    stripe_payment_intent_id = Column(String(255), unique=True, index=True)
    stripe_customer_id = Column(String(255))

    # Payment details
    amount_pence = Column(Integer, nullable=False)  # Amount in pence
    currency = Column(String(3), default="gbp")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)

    # Manual booking payment link (for admin-created bookings)
    stripe_payment_link = Column(String(500))

    # Refund tracking
    refund_id = Column(String(255))
    refund_amount_pence = Column(Integer)
    refund_reason = Column(String(255))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True))
    refunded_at = Column(DateTime(timezone=True))

    # Relationship
    booking = relationship("Booking", back_populates="payment")

    def __repr__(self):
        return f"<Payment {self.stripe_payment_intent_id} - {self.status.value}>"


class FlightDeparture(Base):
    """Departure flights - used for drop-off scheduling."""
    __tablename__ = "flight_departures"

    id = Column(Integer, primary_key=True, index=True)

    date = Column(Date, nullable=False, index=True)
    flight_number = Column(String(20), nullable=False)
    airline_code = Column(String(10), nullable=False)
    airline_name = Column(String(100), nullable=False)

    departure_time = Column(Time, nullable=False)

    # Destination info
    destination_code = Column(String(10), nullable=False)
    destination_name = Column(String(100))

    # Capacity tier: 0, 2, 4, 6, or 8 (determines max slots available)
    # 0 = Call Us only, 2 = 1+1, 4 = 2+2, 6 = 3+3, 8 = 4+4
    capacity_tier = Column(Integer, default=0, nullable=False)

    # Slot booking counters (how many booked at each time)
    # Early slot: 2¾ hours (165 min) before departure
    # Late slot: 2 hours (120 min) before departure
    slots_booked_early = Column(Integer, default=0, nullable=False)
    slots_booked_late = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(100), nullable=True)  # Admin email who made the change

    def __repr__(self):
        return f"<FlightDeparture {self.flight_number} on {self.date} at {self.departure_time}>"

    @property
    def max_slots_per_time(self):
        """Max slots available at each time (early/late)."""
        return self.capacity_tier // 2

    @property
    def early_slots_available(self):
        """Number of early slots still available."""
        return max(0, self.max_slots_per_time - self.slots_booked_early)

    @property
    def late_slots_available(self):
        """Number of late slots still available."""
        return max(0, self.max_slots_per_time - self.slots_booked_late)

    @property
    def is_call_us_only(self):
        """True if this flight has 0 capacity (Call Us only)."""
        return self.capacity_tier == 0

    @property
    def all_slots_booked(self):
        """Check if all slots are booked."""
        return self.early_slots_available == 0 and self.late_slots_available == 0

    @property
    def total_slots_available(self):
        """Total slots available across both times."""
        return self.early_slots_available + self.late_slots_available

    @property
    def is_last_slot(self):
        """True if only 1 slot remains (either early or late)."""
        return self.total_slots_available == 1

    @property
    def early_is_last_slot(self):
        """True if the early slot is the last one available."""
        return self.early_slots_available == 1 and self.late_slots_available == 0

    @property
    def late_is_last_slot(self):
        """True if the late slot is the last one available."""
        return self.late_slots_available == 1 and self.early_slots_available == 0


class FlightArrival(Base):
    """Arrival flights - used for pickup scheduling."""
    __tablename__ = "flight_arrivals"

    id = Column(Integer, primary_key=True, index=True)

    date = Column(Date, nullable=False, index=True)
    flight_number = Column(String(20), nullable=False)
    airline_code = Column(String(10), nullable=False)
    airline_name = Column(String(100), nullable=False)

    # Departure from origin
    departure_time = Column(Time)  # When it leaves the origin

    # Arrival at Bournemouth
    arrival_time = Column(Time, nullable=False)

    # Origin info
    origin_code = Column(String(10), nullable=False)
    origin_name = Column(String(100))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(100), nullable=True)  # Admin email who made the change

    def __repr__(self):
        return f"<FlightArrival {self.flight_number} on {self.date} at {self.arrival_time}>"


class FlightDepartureHistory(Base):
    """History/audit table for flight departure changes."""
    __tablename__ = "flight_departure_history"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flight_departures.id"), nullable=False, index=True)

    # Snapshot of flight data at time of change
    date = Column(Date, nullable=False)
    flight_number = Column(String(20), nullable=False)
    airline_code = Column(String(10), nullable=False)
    airline_name = Column(String(100), nullable=False)
    departure_time = Column(Time, nullable=False)
    destination_code = Column(String(10), nullable=False)
    destination_name = Column(String(100))
    capacity_tier = Column(Integer, nullable=False)
    slots_booked_early = Column(Integer, nullable=False)
    slots_booked_late = Column(Integer, nullable=False)

    # Change metadata
    change_type = Column(String(20), nullable=False)  # 'created', 'updated', 'deleted'
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=True)  # Admin email or 'system'

    def __repr__(self):
        return f"<FlightDepartureHistory {self.flight_id} {self.change_type} at {self.changed_at}>"


class FlightArrivalHistory(Base):
    """History/audit table for flight arrival changes."""
    __tablename__ = "flight_arrival_history"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flight_arrivals.id"), nullable=False, index=True)

    # Snapshot of flight data at time of change
    date = Column(Date, nullable=False)
    flight_number = Column(String(20), nullable=False)
    airline_code = Column(String(10), nullable=False)
    airline_name = Column(String(100), nullable=False)
    departure_time = Column(Time, nullable=True)
    arrival_time = Column(Time, nullable=False)
    origin_code = Column(String(10), nullable=False)
    origin_name = Column(String(100))

    # Change metadata
    change_type = Column(String(20), nullable=False)  # 'created', 'updated', 'deleted'
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=True)  # Admin email or 'system'

    def __repr__(self):
        return f"<FlightArrivalHistory {self.flight_id} {self.change_type} at {self.changed_at}>"


class AuditLogEvent(enum.Enum):
    """Types of booking audit events."""
    # Booking flow events
    BOOKING_STARTED = "booking_started"
    DATES_SELECTED = "dates_selected"  # User selected drop-off and pick-up dates
    FLIGHT_SELECTED = "flight_selected"
    SLOT_SELECTED = "slot_selected"
    VEHICLE_ENTERED = "vehicle_entered"
    CUSTOMER_ENTERED = "customer_entered"
    BILLING_ENTERED = "billing_entered"
    TNC_ACCEPTED = "tnc_accepted"  # T&C checkbox checked
    CHECKOUT_LOADED = "checkout_loaded"  # Stripe checkout page loaded
    STRIPE_FORM_READY = "stripe_form_ready"  # Stripe PaymentElement rendered
    STRIPE_FORM_ERROR = "stripe_form_error"  # Stripe PaymentElement failed to render
    PAYMENT_INITIATED = "payment_initiated"  # User clicked Pay button
    PAYMENT_PROCESSING = "payment_processing"  # stripe.confirmPayment called
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REQUIRES_ACTION = "payment_requires_action"  # 3D Secure or redirect needed
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_ABANDONED = "booking_abandoned"
    # Admin events
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_REFUNDED = "booking_refunded"
    BOOKING_UPDATED = "booking_updated"


class AuditLog(Base):
    """Audit trail for booking events - tracks every step of the booking process."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Session tracking (for incomplete bookings)
    session_id = Column(String(100), index=True)

    # Booking reference (may be null for early-stage abandoned bookings)
    booking_reference = Column(String(20), index=True)

    # Event details
    # Use values_callable to send enum values (lowercase) instead of names (uppercase) to PostgreSQL
    event = Column(
        Enum(AuditLogEvent, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    event_data = Column(Text)  # JSON blob with event-specific data

    # User context
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(String(500))

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<AuditLog {self.event.value} - {self.booking_reference or self.session_id}>"


class ErrorSeverity(enum.Enum):
    """Severity levels for error logs."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MarketingSubscriber(Base):
    """Marketing subscribers from waitlist/newsletter signups."""
    __tablename__ = "marketing_subscribers"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Email tracking
    welcome_email_sent = Column(Boolean, default=False)
    promo_code_sent = Column(Boolean, default=False)  # Legacy - kept for backwards compatibility

    # Legacy promo code tracking (kept for backwards compatibility)
    promo_code = Column(String(20), unique=True, index=True)  # Unique code like "TAG-XXXX-XXXX"
    promo_code_used = Column(Boolean, default=False)
    promo_code_used_booking_id = Column(Integer, ForeignKey("bookings.id"))  # Which booking used it
    promo_code_used_at = Column(DateTime(timezone=True))
    discount_percent = Column(Integer, default=10)  # Discount percentage (default 10%, can be up to 100%)

    # 10% OFF Promo - separate tracking
    promo_10_code = Column(String(20), unique=True, index=True)  # 10% off promo code
    promo_10_sent = Column(Boolean, default=False)
    promo_10_sent_at = Column(DateTime(timezone=True))
    promo_10_used = Column(Boolean, default=False)
    promo_10_used_at = Column(DateTime(timezone=True))
    promo_10_used_booking_id = Column(Integer, ForeignKey("bookings.id"))
    promo_10_reminder_sent = Column(Boolean, default=False)
    promo_10_reminder_sent_at = Column(DateTime(timezone=True))

    # FREE Parking Promo (100% off) - separate tracking
    promo_free_code = Column(String(20), unique=True, index=True)  # Free parking promo code
    promo_free_sent = Column(Boolean, default=False)
    promo_free_sent_at = Column(DateTime(timezone=True))
    promo_free_used = Column(Boolean, default=False)
    promo_free_used_at = Column(DateTime(timezone=True))
    promo_free_used_booking_id = Column(Integer, ForeignKey("bookings.id"))
    promo_free_reminder_sent = Column(Boolean, default=False)
    promo_free_reminder_sent_at = Column(DateTime(timezone=True))

    # Founder Thank You Email - personalized email from Kristian with 10% promo
    founder_promo_code = Column(String(20), unique=True, index=True)  # Founder's 10% off promo code
    founder_email_sent = Column(Boolean, default=False)
    founder_email_sent_at = Column(DateTime(timezone=True))
    founder_promo_used = Column(Boolean, default=False)
    founder_promo_used_at = Column(DateTime(timezone=True))
    founder_promo_used_booking_id = Column(Integer, ForeignKey("bookings.id"))

    # Source tracking
    source = Column(String(50), default="landing_page")  # landing_page, homepage, etc.
    hubspot_contact_id = Column(String(100))  # For HubSpot integration

    # Unsubscribe tracking
    unsubscribe_token = Column(String(64), unique=True, index=True)  # Secure token for unsubscribe link
    unsubscribed = Column(Boolean, default=False)
    unsubscribed_at = Column(DateTime(timezone=True))

    # Timestamps
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    welcome_email_sent_at = Column(DateTime(timezone=True))
    promo_code_sent_at = Column(DateTime(timezone=True))  # Legacy

    # Relationships to bookings
    used_booking = relationship("Booking", foreign_keys=[promo_code_used_booking_id])
    promo_10_booking = relationship("Booking", foreign_keys=[promo_10_used_booking_id])
    promo_free_booking = relationship("Booking", foreign_keys=[promo_free_used_booking_id])

    def __repr__(self):
        return f"<MarketingSubscriber {self.first_name} {self.last_name} ({self.email})>"


class ErrorLog(Base):
    """Error log for API and service errors."""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Error classification
    severity = Column(Enum(ErrorSeverity), default=ErrorSeverity.ERROR, nullable=False, index=True)
    error_type = Column(String(100), nullable=False, index=True)  # e.g., "dvla_api", "stripe", "validation"
    error_code = Column(String(50))  # HTTP status or custom code

    # Error details
    message = Column(Text, nullable=False)
    stack_trace = Column(Text)
    request_data = Column(Text)  # JSON blob with sanitized request data

    # Context
    endpoint = Column(String(200), index=True)
    booking_reference = Column(String(20), index=True)
    session_id = Column(String(100))
    ip_address = Column(String(45))
    user_agent = Column(String(500))

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<ErrorLog {self.severity.value} - {self.error_type}: {self.message[:50]}>"


class User(Base):
    """Employee/Admin users for internal access."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(255), unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20))

    # Role
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))

    def __repr__(self):
        role = "Admin" if self.is_admin else "Employee"
        return f"<User {self.first_name} {self.last_name} ({role})>"


class LoginCode(Base):
    """6-digit login codes sent via email."""
    __tablename__ = "login_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")

    def __repr__(self):
        return f"<LoginCode {self.code} for user {self.user_id}>"


class Session(Base):
    """User sessions - expire after 8 hours."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")

    def __repr__(self):
        return f"<Session for user {self.user_id}>"


class InspectionType(enum.Enum):
    """Type of vehicle inspection."""
    DROPOFF = "dropoff"      # When customer drops car off
    PICKUP = "pickup"        # When customer picks car up


class VehicleInspection(Base):
    """Vehicle inspection record - one per type per booking."""
    __tablename__ = "vehicle_inspections"
    __table_args__ = (
        UniqueConstraint('booking_id', 'inspection_type', name='uq_inspection_booking_type'),
    )

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    inspection_type = Column(Enum(InspectionType), nullable=False)

    notes = Column(Text)
    photos = Column(Text)  # JSON array of base64-encoded images

    # Customer acknowledgement
    customer_name = Column(String(200))  # Customer types their name to agree
    signed_date = Column(Date)  # Date of acknowledgement
    signature = Column(Text)  # Base64-encoded signature image
    vehicle_inspection_read = Column(Boolean, default=False)  # Confirmed they read T&C (drop-off only)
    acknowledgement_confirmed = Column(Boolean, default=False)  # Confirmed acknowledgement (return only)

    # Vehicle mileage at inspection
    mileage = Column(Integer, nullable=True)

    # Customer declined inspection (for pickup/return only - allows completing booking)
    declined = Column(Boolean, default=False)

    inspector_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    booking = relationship("Booking")
    inspector = relationship("User")

    def __repr__(self):
        return f"<VehicleInspection {self.inspection_type.value} for booking {self.booking_id}>"


class PricingSettings(Base):
    """Dynamic pricing configuration for booking packages with simplified anchor pricing."""
    __tablename__ = "pricing_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Anchor base prices for early booking tier
    # These are the "early" tier prices - standard adds tier_increment, late adds 2x tier_increment
    days_1_4_price = Column(Numeric(10, 2), nullable=False, default=65.00)    # 1-4 days anchor
    week1_base_price = Column(Numeric(10, 2), nullable=False, default=85.00)  # 7 days anchor
    week2_base_price = Column(Numeric(10, 2), nullable=False, default=150.00) # 14 days anchor

    # Daily increment for days between anchors (5-6, 8-13, 15+)
    daily_increment = Column(Numeric(10, 2), nullable=False, default=8.00)

    # Price increment per booking tier (early -> standard -> late)
    tier_increment = Column(Numeric(10, 2), nullable=False, default=5.00)

    # Legacy columns - kept for migration compatibility, will be removed later
    days_5_6_price = Column(Numeric(10, 2), nullable=True)
    days_8_9_price = Column(Numeric(10, 2), nullable=True)
    days_10_11_price = Column(Numeric(10, 2), nullable=True)
    days_12_13_price = Column(Numeric(10, 2), nullable=True)

    # Audit fields
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"))

    updater = relationship("User")

    def __repr__(self):
        return f"<PricingSettings 1-4d={self.days_1_4_price} 7d={self.week1_base_price} 14d={self.week2_base_price} daily_inc={self.daily_increment} tier_inc={self.tier_increment}>"


class TestRunStatus(enum.Enum):
    """Status of a test run."""
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class TestRun(Base):
    """Automated test run results for QA Dashboard."""
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)

    # Test run info
    environment = Column(String(20), nullable=False, default="staging")  # staging, production
    run_type = Column(String(30), nullable=False, default="scheduled")  # scheduled, manual, pr_check
    status = Column(Enum(TestRunStatus), default=TestRunStatus.RUNNING, nullable=False)

    # Results
    tests_passed = Column(Integer, default=0, nullable=False)
    tests_failed = Column(Integer, default=0, nullable=False)
    tests_skipped = Column(Integer, default=0, nullable=False)
    tests_total = Column(Integer, default=0, nullable=False)

    # Coverage
    coverage_percent = Column(Numeric(5, 2), nullable=True)  # e.g., 78.50

    # Timing
    duration_seconds = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Git info
    commit_sha = Column(String(40), nullable=True)
    branch = Column(String(100), nullable=True)

    # Links/artifacts
    logs_url = Column(String(500), nullable=True)  # Link to CI logs
    report_json = Column(Text, nullable=True)  # JSON with detailed test results

    # Trigger info
    triggered_by = Column(String(100), nullable=True)  # "github_actions", "manual", "cron"

    def __repr__(self):
        return f"<TestRun {self.id} {self.environment} {self.status.value} - {self.tests_passed}/{self.tests_total}>"

    @property
    def pass_rate(self):
        """Calculate pass rate percentage."""
        if self.tests_total == 0:
            return 0
        return round((self.tests_passed / self.tests_total) * 100, 1)


class TestimonialStatus(enum.Enum):
    """Status of a testimonial."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class Testimonial(Base):
    """Customer testimonials/reviews."""
    __tablename__ = "testimonials"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False)
    review_text = Column(Text, nullable=False)
    star_rating = Column(Integer, nullable=True)  # 1-5, or NULL for unrated (LinkedIn, FB, etc.)
    date_of_travel = Column(Date, nullable=True)
    date_added = Column(DateTime(timezone=True), server_default=func.now())
    # Use values_callable to send enum values (lowercase) instead of names (uppercase) to PostgreSQL
    status = Column(
        Enum(TestimonialStatus, values_callable=lambda x: [e.value for e in x]),
        default=TestimonialStatus.INACTIVE,
        nullable=False
    )
    is_featured = Column(Boolean, default=False, nullable=False)
    source = Column(String(50), nullable=True)  # e.g. Google, TrustPilot, Direct

    def __repr__(self):
        return f"<Testimonial {self.id} - {self.customer_name} ({self.star_rating}★)>"


class PromoModalStatus(enum.Enum):
    """Status of a promo modal."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SCHEDULED = "scheduled"


class PromoModal(Base):
    """Promotional modals/popups for the homepage."""
    __tablename__ = "promo_modals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)  # e.g. "Spring Sale!"
    message = Column(Text, nullable=False)  # Main promotional message
    button_text = Column(String(50), default="Subscribe")  # CTA button text
    button_action = Column(String(50), default="subscribe")  # subscribe, link, close
    button_link = Column(String(500), nullable=True)  # If button_action is "link"

    # Date range when promo is valid
    start_date = Column(Date, nullable=True)  # If null, starts immediately when active
    end_date = Column(Date, nullable=True)  # If null, runs indefinitely when active

    # Styling
    background_color = Column(String(20), default="#1e3a5f")  # Dark blue default
    text_color = Column(String(20), default="#ffffff")
    button_color = Column(String(20), default="#22c55e")  # Green default
    button_text_color = Column(String(20), default="#ffffff")  # White default

    # Status
    status = Column(
        Enum(PromoModalStatus, values_callable=lambda x: [e.value for e in x]),
        default=PromoModalStatus.INACTIVE,
        nullable=False
    )

    # Subscriber limit (auto-deactivate after X new subscribers)
    max_subscribers = Column(Integer, nullable=True)  # null = unlimited
    subscribers_at_activation = Column(Integer, nullable=True)  # Count when activated

    # Promo code tracking (auto-deactivate when this promo code is used on a confirmed booking)
    promo_code = Column(String(50), nullable=True)  # The promo code displayed in the modal

    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    view_count = Column(Integer, default=0)  # How many times shown
    click_count = Column(Integer, default=0)  # How many times CTA clicked

    def __repr__(self):
        return f"<PromoModal {self.id} - {self.title} ({self.status.value})>"


class MarketingSource(Base):
    """Marketing attribution - where customers heard about TAG Parking."""
    __tablename__ = "marketing_sources"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True)

    # Source dropdown value: newspaper, google, facebook, instagram, linkedin, afc_bournemouth, other
    source = Column(String(50), nullable=False)
    # Free-text detail (only populated when source = 'other')
    source_detail = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    customer = relationship("Customer", back_populates="marketing_source")

    def __repr__(self):
        return f"<MarketingSource {self.id} - {self.source} (customer_id={self.customer_id})>"


class MarketingSourceMonthlyTotal(Base):
    """Pre-aggregated monthly counts per marketing source for admin reports."""
    __tablename__ = "marketing_source_monthly_totals"

    id = Column(Integer, primary_key=True, index=True)
    year_month = Column(String(7), nullable=False, index=True)  # YYYY-MM format
    source = Column(String(50), nullable=False)
    count = Column(Integer, nullable=False, default=0)

    # Unique constraint on year_month + source
    __table_args__ = (
        UniqueConstraint('year_month', 'source', name='uq_year_month_source'),
    )

    def __repr__(self):
        return f"<MarketingSourceMonthlyTotal {self.year_month} - {self.source}: {self.count}>"


class Promotion(Base):
    """Promo code campaign - a batch of codes with the same discount."""
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Spring 2024 Friends & Family"
    description = Column(Text, nullable=True)

    # Discount settings
    discount_percent = Column(Integer, nullable=False)  # 10, 20, 100
    code_prefix = Column(String(10), nullable=False, default="TAG")  # Prefix for promo codes

    # Code generation stats
    total_codes = Column(Integer, nullable=False, default=0)
    codes_sent = Column(Integer, nullable=False, default=0)
    codes_used = Column(Integer, nullable=False, default=0)

    # Admin tracking
    created_by = Column(String(255), nullable=True)  # Admin email
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    promo_codes = relationship("PromoCode", back_populates="promotion")

    def __repr__(self):
        return f"<Promotion {self.id} - {self.name} ({self.discount_percent}% off)>"


class PromoCode(Base):
    """Individual promo code - single use, unique."""
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False)
    code = Column(String(20), unique=True, nullable=False, index=True)  # TAG-XXXX-XXXX

    # Recipient - can be customer, subscriber, or just an email for new contacts
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    subscriber_id = Column(Integer, ForeignKey("marketing_subscribers.id"), nullable=True)
    recipient_email = Column(String(255), nullable=True)  # Always store the email sent to
    recipient_first_name = Column(String(100), nullable=True)
    recipient_last_name = Column(String(100), nullable=True)

    # Email tracking
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_subject = Column(String(255), nullable=True)

    # Social media tracking (for codes shared on socials without email)
    shared_on_socials = Column(Boolean, default=False)
    shared_on_socials_at = Column(DateTime(timezone=True), nullable=True)

    # Private sharing tracking (for codes shared privately via text/friends)
    shared_privately = Column(Boolean, default=False)
    shared_privately_at = Column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    is_used = Column(Boolean, default=False, index=True)  # True if code has reached max uses
    used_at = Column(DateTime(timezone=True), nullable=True)  # Last usage timestamp
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)  # Last booking that used it

    # Multi-use support
    # max_uses = NULL means single-use (default, backwards compatible)
    # max_uses = 0 means unlimited uses
    # max_uses = N means can be used N times
    max_uses = Column(Integer, nullable=True, default=None)
    use_count = Column(Integer, nullable=False, default=0)  # How many times this code has been used

    # Expiry - if set, code is only valid before this date/time (UK timezone)
    # NULL means never expires (backwards compatible)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    promotion = relationship("Promotion", back_populates="promo_codes")
    customer = relationship("Customer", foreign_keys=[customer_id])
    subscriber = relationship("MarketingSubscriber", foreign_keys=[subscriber_id])
    booking = relationship("Booking", foreign_keys=[booking_id])

    def __repr__(self):
        status = "used" if self.is_used else ("sent" if self.email_sent else "unsent")
        return f"<PromoCode {self.code} - {status}>"

    @property
    def is_multi_use(self):
        """Check if this is a multi-use code (max_uses is set)."""
        return self.max_uses is not None

    @property
    def is_unlimited(self):
        """Check if this is an unlimited-use code (max_uses = 0)."""
        return self.max_uses == 0

    @property
    def uses_remaining(self):
        """Get number of uses remaining (None for unlimited, 0 for exhausted)."""
        if self.max_uses is None:
            # Single-use code
            return 0 if self.is_used else 1
        if self.max_uses == 0:
            # Unlimited
            return None
        return max(0, self.max_uses - self.use_count)

    @property
    def can_be_used(self):
        """Check if this code can still be used."""
        if self.max_uses is None:
            # Single-use: check is_used flag
            return not self.is_used
        if self.max_uses == 0:
            # Unlimited: always can be used (unless expired - checked elsewhere)
            return True
        # Multi-use: check if under limit
        return self.use_count < self.max_uses


class PromoCodeUsage(Base):
    """Tracks each usage of a promo code - especially for multi-use codes."""
    __tablename__ = "promo_code_usages"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)

    # Discount applied for this specific usage
    discount_percent = Column(Integer, nullable=False)
    discount_amount_pence = Column(Integer, nullable=True)  # Actual discount in pence

    # Timestamps
    used_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    promo_code = relationship("PromoCode", backref="usages")
    booking = relationship("Booking")

    def __repr__(self):
        return f"<PromoCodeUsage code_id={self.promo_code_id} booking_id={self.booking_id}>"


class ShiftBookingLink(Base):
    """Association table for many-to-many relationship between shifts and bookings."""
    __tablename__ = "shift_booking_links"

    id = Column(Integer, primary_key=True, index=True)
    shift_id = Column(Integer, ForeignKey("roster_shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Unique constraint to prevent duplicate links
    __table_args__ = (
        UniqueConstraint('shift_id', 'booking_id', name='uq_shift_booking'),
    )


class RosterShift(Base):
    """Roster shift for staff scheduling."""
    __tablename__ = "roster_shifts"

    id = Column(Integer, primary_key=True, index=True)

    # Staff assignment (nullable = unassigned shift)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # DEPRECATED: Single booking link - use bookings relationship instead
    # Kept for backwards compatibility during migration
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)

    # Shift timing
    date = Column(Date, nullable=False, index=True)  # Start date
    end_date = Column(Date, nullable=True, index=True)  # End date (for overnight shifts, defaults to date)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Shift classification
    shift_type = Column(
        Enum(ShiftType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    status = Column(
        Enum(ShiftStatus, values_callable=lambda x: [e.value for e in x]),
        default=ShiftStatus.SCHEDULED,
        nullable=False
    )

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    staff = relationship("User", foreign_keys=[staff_id])
    booking = relationship("Booking", foreign_keys=[booking_id])  # DEPRECATED - use bookings

    # Many-to-many relationship with bookings
    bookings = relationship(
        "Booking",
        secondary="shift_booking_links",
        backref="shifts",
        lazy="selectin"
    )

    def __repr__(self):
        staff_name = f"{self.staff.first_name} {self.staff.last_name}" if self.staff else "Unassigned"
        return f"<RosterShift {self.id} - {self.shift_type.value} on {self.date} ({staff_name})>"

    @property
    def staff_initials(self):
        """Get staff initials (e.g., 'JC' for James Carter)."""
        if self.staff:
            return f"{self.staff.first_name[0]}{self.staff.last_name[0]}".upper()
        return None

    @property
    def is_overnight(self):
        """Check if shift crosses midnight (end_time < start_time)."""
        return self.end_time < self.start_time

    @property
    def duration_minutes(self):
        """Calculate shift duration in minutes."""
        start_mins = self.start_time.hour * 60 + self.start_time.minute
        end_mins = self.end_time.hour * 60 + self.end_time.minute

        if self.is_overnight:
            # Add 24 hours worth of minutes for overnight shifts
            return (24 * 60 - start_mins) + end_mins
        return end_mins - start_mins


class BlockedDate(Base):
    """Blocked dates - prevents bookings on specific dates.

    Used to block off days when the service is not available
    (e.g., holidays, maintenance, staff unavailability).
    All dates are stored and interpreted in UK timezone (Europe/London).
    """
    __tablename__ = "blocked_dates"

    id = Column(Integer, primary_key=True, index=True)

    # Date range (inclusive) - stored in UK timezone
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)

    # What is blocked
    block_dropoffs = Column(Boolean, default=True, nullable=False)  # Block drop-offs on this date
    block_pickups = Column(Boolean, default=True, nullable=False)   # Block pick-ups on this date

    # Reason/description (shown to admins)
    reason = Column(String(255), nullable=True)

    # Admin tracking
    created_by = Column(String(255), nullable=True)  # Admin email
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to time slots
    time_slots = relationship("BlockedTimeSlot", back_populates="blocked_date", cascade="all, delete-orphan")

    def __repr__(self):
        block_type = []
        if self.block_dropoffs:
            block_type.append("dropoffs")
        if self.block_pickups:
            block_type.append("pickups")
        return f"<BlockedDate {self.start_date} to {self.end_date} ({', '.join(block_type)})>"


class BlockedTimeSlot(Base):
    """Blocked time slots - allows partial day blocking.

    Child of BlockedDate. When a BlockedDate has time slots, only those
    specific time periods are blocked (not the entire day).
    If no time slots exist, the entire day is blocked based on BlockedDate settings.
    """
    __tablename__ = "blocked_time_slots"

    id = Column(Integer, primary_key=True, index=True)

    # Parent blocked date
    blocked_date_id = Column(Integer, ForeignKey("blocked_dates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Time range (UK timezone)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # What is blocked during this time slot
    block_dropoffs = Column(Boolean, default=True, nullable=False)
    block_pickups = Column(Boolean, default=True, nullable=False)

    # Reason for this specific time slot
    reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to parent
    blocked_date = relationship("BlockedDate", back_populates="time_slots")

    def __repr__(self):
        block_type = []
        if self.block_dropoffs:
            block_type.append("dropoffs")
        if self.block_pickups:
            block_type.append("pickups")
        return f"<BlockedTimeSlot {self.start_time}-{self.end_time} ({', '.join(block_type)})>"
