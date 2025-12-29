"""
SQLAlchemy database models for TAG booking system.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Time,
    ForeignKey, Enum, Boolean, Text
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

    # Relationships
    vehicles = relationship("Vehicle", back_populates="customer")
    bookings = relationship("Booking", back_populates="customer")

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

    # Package type: 'quick' (1 week) or 'longer' (2 weeks)
    package = Column(String(20), nullable=False)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)

    # Drop-off details
    dropoff_date = Column(Date, nullable=False)
    dropoff_time = Column(Time, nullable=False)
    dropoff_flight_number = Column(String(20))
    dropoff_destination = Column(String(100))

    # Flight slot booking (for slot release on cancellation)
    departure_id = Column(Integer, ForeignKey("flight_departures.id"), nullable=True)
    dropoff_slot = Column(String(10), nullable=True)  # "early" or "late"

    # Pick-up details
    pickup_date = Column(Date, nullable=False)
    pickup_time = Column(Time)  # Arrival/landing time of return flight
    pickup_time_from = Column(Time)  # 35 min after landing
    pickup_time_to = Column(Time)  # 60 min after landing
    pickup_flight_number = Column(String(20))
    pickup_origin = Column(String(100))

    # Admin notes
    notes = Column(Text)

    # Email tracking
    confirmation_email_sent = Column(Boolean, default=False)
    confirmation_email_sent_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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

    def __repr__(self):
        return f"<FlightArrival {self.flight_number} on {self.date} at {self.arrival_time}>"


class AuditLogEvent(enum.Enum):
    """Types of booking audit events."""
    # Booking flow events
    BOOKING_STARTED = "booking_started"
    FLIGHT_SELECTED = "flight_selected"
    SLOT_SELECTED = "slot_selected"
    VEHICLE_ENTERED = "vehicle_entered"
    CUSTOMER_ENTERED = "customer_entered"
    BILLING_ENTERED = "billing_entered"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
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
    event = Column(Enum(AuditLogEvent), nullable=False, index=True)
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
    promo_code_sent = Column(Boolean, default=False)

    # Promo code tracking
    promo_code = Column(String(20), unique=True, index=True)  # Unique code like "TAG-XXXX-XXXX"
    promo_code_used = Column(Boolean, default=False)
    promo_code_used_booking_id = Column(Integer, ForeignKey("bookings.id"))  # Which booking used it
    promo_code_used_at = Column(DateTime(timezone=True))
    discount_percent = Column(Integer, default=10)  # Discount percentage (default 10%, can be up to 100%)

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
    promo_code_sent_at = Column(DateTime(timezone=True))

    # Relationship to booking (optional)
    used_booking = relationship("Booking", foreign_keys=[promo_code_used_booking_id])

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
