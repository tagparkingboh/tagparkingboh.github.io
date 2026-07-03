"""
Database service layer for CRUD operations.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import date, time, datetime, timezone, timedelta
from typing import Optional, List, Union
from zoneinfo import ZoneInfo
import logging
import os
import random
import string

from db_models import (
    Customer, Vehicle, Booking, Payment, FlightDeparture, FlightArrival,
    FlightDepartureHistory, FlightArrivalHistory,
    BookingStatus, PaymentStatus, ServiceType, ParkingCapacitySetting
)

logger = logging.getLogger(__name__)

E2E_CAPACITY_EXCLUDED_EMAILS = (
    "qa.orca.contact@gmail.com",
    "qa.orca.contact+referral-friend1@gmail.com",
    "qa.orca.contact+referral-friend2@gmail.com",
)

UK_TIMEZONE = ZoneInfo("Europe/London")
LEGACY_CAPACITY_EFFECTIVE_FROM = datetime(1970, 1, 1, 0, 0, tzinfo=UK_TIMEZONE)
CURRENT_CAPACITY_EFFECTIVE_FROM = datetime(2026, 6, 11, 0, 0, tzinfo=UK_TIMEZONE)
LEGACY_TOTAL_SPACES = 70
LEGACY_ONLINE_SPACES = 64
CURRENT_TOTAL_SPACES = 75
CURRENT_ONLINE_SPACES = 73

DEFAULT_CAPACITY_SCHEDULE = (
    {
        "id": None,
        "effective_from": LEGACY_CAPACITY_EFFECTIVE_FROM,
        "total_spaces": LEGACY_TOTAL_SPACES,
        "online_spaces": LEGACY_ONLINE_SPACES,
        "manual_spaces": LEGACY_TOTAL_SPACES - LEGACY_ONLINE_SPACES,
        "updated_at": None,
        "updated_by": "fallback",
    },
    {
        "id": None,
        "effective_from": CURRENT_CAPACITY_EFFECTIVE_FROM,
        "total_spaces": CURRENT_TOTAL_SPACES,
        "online_spaces": CURRENT_ONLINE_SPACES,
        "manual_spaces": CURRENT_TOTAL_SPACES - CURRENT_ONLINE_SPACES,
        "updated_at": None,
        "updated_by": "fallback",
    },
)


def should_exclude_staging_e2e_capacity_bookings() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() == "staging"


def exclude_staging_e2e_capacity_bookings(query, booking_model=Booking):
    """In staging, keep scheduled e2e bookings from consuming public capacity."""
    if not should_exclude_staging_e2e_capacity_bookings():
        return query
    query_module = query.__class__.__module__
    if query_module.startswith("unittest.mock") or not hasattr(query, "join"):
        return query
    return query.join(booking_model.customer).filter(
        func.lower(Customer.email).notin_(E2E_CAPACITY_EXCLUDED_EMAILS)
    )


# ============== PARKING CAPACITY SETTINGS ==============

def _capacity_row_to_dict(row) -> dict:
    """Normalize a DB row or dict into the API/helper shape."""
    if isinstance(row, dict):
        effective_from = normalize_capacity_effective_from(row["effective_from"])
        total_spaces = int(row["total_spaces"])
        online_spaces = int(row["online_spaces"])
        return {
            "id": row.get("id"),
            "effective_from": effective_from,
            "total_spaces": total_spaces,
            "online_spaces": online_spaces,
            "manual_spaces": total_spaces - online_spaces,
            "updated_at": row.get("updated_at"),
            "updated_by": row.get("updated_by"),
        }

    total_spaces = int(row.total_spaces)
    online_spaces = int(row.online_spaces)
    return {
        "id": row.id,
        "effective_from": normalize_capacity_effective_from(row.effective_from),
        "total_spaces": total_spaces,
        "online_spaces": online_spaces,
        "manual_spaces": total_spaces - online_spaces,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


def _fallback_capacity_schedule() -> list[dict]:
    return [_capacity_row_to_dict(row) for row in DEFAULT_CAPACITY_SCHEDULE]


def validate_capacity_values(total_spaces: int, online_spaces: int) -> None:
    if total_spaces is None or online_spaces is None:
        raise ValueError("total_spaces and online_spaces are required")
    if int(total_spaces) < 1:
        raise ValueError("total_spaces must be at least 1")
    if int(online_spaces) < 1:
        raise ValueError("online_spaces must be at least 1")
    if int(online_spaces) > int(total_spaces):
        raise ValueError("online_spaces cannot exceed total_spaces")


def normalize_capacity_effective_from(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time(0, 0))
    elif isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    else:
        raise ValueError("effective_from must be a datetime")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UK_TIMEZONE)
    return dt.astimezone(UK_TIMEZONE)


def _capacity_lookup_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return normalize_capacity_effective_from(value)
    if isinstance(value, date):
        return datetime.combine(value, time(23, 59, 59), tzinfo=UK_TIMEZONE)
    raise ValueError("capacity lookup value must be a date or datetime")


def get_parking_capacity_schedule(db: Session) -> list[dict]:
    """Return the date-effective capacity schedule, oldest first.

    During deploys where the migration has not populated the table yet,
    fall back to the known legacy/current schedule so capacity decisions remain
    deterministic.
    """
    try:
        rows = (
            db.query(ParkingCapacitySetting)
            .order_by(ParkingCapacitySetting.effective_from.asc())
            .all()
        )
    except Exception:
        logger.exception("Failed to load parking capacity settings; using fallback capacity schedule")
        # On Postgres a failed statement aborts the whole transaction; without
        # this rollback every later query in the same request dies with
        # "current transaction is aborted" (seen in staging 2026-06-11 when
        # the table did not exist yet), defeating the fallback entirely.
        try:
            db.rollback()
        except Exception:
            logger.exception("Rollback after capacity settings read failure also failed")
        rows = []

    if not rows:
        return _fallback_capacity_schedule()

    return [_capacity_row_to_dict(row) for row in rows]


def capacity_for_date_from_schedule(schedule: list[dict], target_date: Union[date, datetime]) -> dict:
    """Pick the latest capacity row whose effective_from <= target date/time."""
    if not schedule:
        schedule = _fallback_capacity_schedule()
    target_dt = _capacity_lookup_datetime(target_date)
    selected = None
    for row in sorted(schedule, key=lambda item: item["effective_from"]):
        if row["effective_from"] <= target_dt:
            selected = row
        else:
            break
    if selected is None:
        selected = sorted(schedule, key=lambda item: item["effective_from"])[0]
    return _capacity_row_to_dict(selected)


def get_parking_capacity_for_date(db: Session, target_date: Union[date, datetime]) -> dict:
    return capacity_for_date_from_schedule(get_parking_capacity_schedule(db), target_date)


def get_parking_capacity_for_range(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict[str, dict]:
    schedule = get_parking_capacity_schedule(db)
    current = start_date
    by_date: dict[str, dict] = {}
    while current <= end_date:
        capacity = capacity_for_date_from_schedule(schedule, current)
        by_date[current.isoformat()] = {
            "total_spaces": capacity["total_spaces"],
            "online_spaces": capacity["online_spaces"],
            "manual_spaces": capacity["manual_spaces"],
        }
        current += timedelta(days=1)
    return by_date


def upsert_parking_capacity_setting(
    db: Session,
    effective_from: datetime,
    total_spaces: int,
    online_spaces: int,
    updated_by: str = None,
) -> ParkingCapacitySetting:
    validate_capacity_values(total_spaces, online_spaces)
    effective_from = normalize_capacity_effective_from(effective_from)

    setting = (
        db.query(ParkingCapacitySetting)
        .filter(ParkingCapacitySetting.effective_from == effective_from)
        .first()
    )
    if setting:
        setting.total_spaces = int(total_spaces)
        setting.online_spaces = int(online_spaces)
        setting.updated_at = datetime.now(timezone.utc)
        setting.updated_by = updated_by
    else:
        setting = ParkingCapacitySetting(
            effective_from=effective_from,
            total_spaces=int(total_spaces),
            online_spaces=int(online_spaces),
            updated_by=updated_by,
        )
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting


def serialize_capacity_setting(row: dict) -> dict:
    payload = _capacity_row_to_dict(row)
    effective_from = payload["effective_from"].astimezone(UK_TIMEZONE)
    payload["effective_from"] = effective_from.isoformat()
    payload["effective_from_display"] = effective_from.strftime("%d/%m/%Y %H:%M")
    if payload["updated_at"] is not None:
        payload["updated_at"] = payload["updated_at"].isoformat()
    return payload


# ============== SECONDARY CAR PARK ==============

SECONDARY_CARPARK_DEFAULT_WINDOW_START = time(9, 0)
SECONDARY_CARPARK_DEFAULT_WINDOW_END = time(21, 0)
SECONDARY_CARPARK_DEFAULT_CAPACITY = 20


def _env_time(name: str, default: time) -> time:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        hours, minutes = raw.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        logger.warning("Invalid %s=%r; using default %s", name, raw, default.strftime("%H:%M"))
        return default


def get_secondary_carpark_settings() -> dict:
    """Secondary car park qualification window + capacity. Env-configured on
    Railway (SECONDARY_CARPARK_WINDOW_START / _WINDOW_END as HH:MM, and
    SECONDARY_CARPARK_CAPACITY) so ops can change them without a deploy;
    defaults are the 2026-06 business rule: 09:00-21:00 inclusive, 20 spaces.
    """
    raw_capacity = os.environ.get("SECONDARY_CARPARK_CAPACITY", "").strip()
    capacity = SECONDARY_CARPARK_DEFAULT_CAPACITY
    if raw_capacity:
        try:
            capacity = max(0, int(raw_capacity))
        except ValueError:
            logger.warning(
                "Invalid SECONDARY_CARPARK_CAPACITY=%r; using default %s",
                raw_capacity, SECONDARY_CARPARK_DEFAULT_CAPACITY,
            )
    return {
        "window_start": _env_time(
            "SECONDARY_CARPARK_WINDOW_START", SECONDARY_CARPARK_DEFAULT_WINDOW_START
        ),
        "window_end": _env_time(
            "SECONDARY_CARPARK_WINDOW_END", SECONDARY_CARPARK_DEFAULT_WINDOW_END
        ),
        "capacity": capacity,
    }


def booking_qualifies_for_secondary_carpark(booking, settings: Optional[dict] = None) -> bool:
    """Business rule (2026-06): a booking qualifies for the secondary car
    park when BOTH its drop-off and pickup handoff times fall inside the
    operating window, boundaries inclusive. Bookings missing either time
    never qualify (they follow the existing main-park process)."""
    s = settings or get_secondary_carpark_settings()
    dropoff_time = getattr(booking, "dropoff_time", None)
    pickup_time = getattr(booking, "pickup_time", None)
    if not dropoff_time or not pickup_time:
        return False
    return (
        s["window_start"] <= dropoff_time <= s["window_end"]
        and s["window_start"] <= pickup_time <= s["window_end"]
    )


def secondary_carpark_info(booking, settings: Optional[dict] = None) -> dict:
    """Routing payload for booking detail views: assigned car park, whether
    the window rule qualified it, and a human-readable reason."""
    s = settings or get_secondary_carpark_settings()
    window = f"{s['window_start'].strftime('%H:%M')}-{s['window_end'].strftime('%H:%M')}"
    dropoff_time = getattr(booking, "dropoff_time", None)
    pickup_time = getattr(booking, "pickup_time", None)

    failures = []
    if not dropoff_time or not pickup_time:
        failures.append("booking is missing a drop-off or pickup time")
    else:
        if not (s["window_start"] <= dropoff_time <= s["window_end"]):
            failures.append(f"drop-off {dropoff_time.strftime('%H:%M')} outside {window}")
        if not (s["window_start"] <= pickup_time <= s["window_end"]):
            failures.append(f"pickup {pickup_time.strftime('%H:%M')} outside {window}")

    qualifies = not failures
    return {
        "qualifies": qualifies,
        "assigned_carpark": "secondary" if qualifies else "main",
        "reason": (
            f"drop-off and pickup within {window}" if qualifies else "; ".join(failures)
        ),
        "window": window,
    }


def generate_booking_reference() -> str:
    """Generate a unique booking reference like TAG-ABC12345."""
    chars = ''.join(random.choices(string.ascii_uppercase, k=3))
    nums = ''.join(random.choices(string.digits, k=5))
    return f"TAG-{chars}{nums}"


# ============== CUSTOMER OPERATIONS ==============

def get_customer_by_email(db: Session, email: str) -> Optional[Customer]:
    """Get customer by email address (case-insensitive)."""
    if not email:
        return None
    return db.query(Customer).filter(
        func.lower(Customer.email) == email.lower().strip()
    ).first()


def normalize_name(name: str) -> str:
    """Normalize a name for comparison (lowercase, strip whitespace)."""
    return name.strip().lower() if name else ""


def normalize_postcode(postcode: str) -> str:
    """Normalize a postcode for comparison (uppercase, no spaces)."""
    return postcode.replace(" ", "").upper() if postcode else ""


def find_potential_duplicate_customer(
    db: Session,
    first_name: str,
    last_name: str,
    postcode: str,
    exclude_email: str = None,
) -> Optional[Customer]:
    """
    Find a potential duplicate customer by name and postcode.

    This is used to flag possible duplicates when someone books with
    a different email but same name/postcode combination.

    Args:
        db: Database session
        first_name: Customer's first name
        last_name: Customer's last name
        postcode: Customer's billing postcode
        exclude_email: Email to exclude from search (the current customer's email)

    Returns:
        Customer if a potential duplicate is found, None otherwise
    """
    if not postcode or not first_name or not last_name:
        return None

    # Normalize for comparison
    norm_first = normalize_name(first_name)
    norm_last = normalize_name(last_name)
    norm_postcode = normalize_postcode(postcode)

    # Query customers with matching postcode (case-insensitive)
    query = db.query(Customer).filter(
        Customer.billing_postcode.isnot(None)
    )

    if exclude_email:
        query = query.filter(Customer.email != exclude_email)

    candidates = query.all()

    # Check for name + postcode match
    for customer in candidates:
        cust_postcode = normalize_postcode(customer.billing_postcode or "")
        cust_first = normalize_name(customer.first_name or "")
        cust_last = normalize_name(customer.last_name or "")

        if (cust_postcode == norm_postcode and
            cust_first == norm_first and
            cust_last == norm_last):
            return customer

    return None


def get_customer_by_id(db: Session, customer_id: int) -> Optional[Customer]:
    """Get customer by ID."""
    return db.query(Customer).filter(Customer.id == customer_id).first()


def create_customer(
    db: Session,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    billing_address1: str = None,
    billing_address2: str = None,
    billing_city: str = None,
    billing_county: str = None,
    billing_postcode: str = None,
    billing_country: str = "United Kingdom"
) -> tuple[Customer, bool]:
    """
    Create a new customer or return existing one if email matches.

    Returns:
        tuple: (Customer object, is_new: bool) - is_new is True if newly created
    """
    # Check if customer already exists
    existing = get_customer_by_email(db, email)
    if existing:
        # Update existing customer's details
        existing.first_name = first_name
        existing.last_name = last_name
        existing.phone = phone
        existing.billing_address1 = billing_address1
        existing.billing_address2 = billing_address2
        existing.billing_city = billing_city
        existing.billing_county = billing_county
        existing.billing_postcode = billing_postcode
        existing.billing_country = billing_country
        db.commit()
        db.refresh(existing)
        return existing, False  # Existing customer updated

    # Create new customer
    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        billing_address1=billing_address1,
        billing_address2=billing_address2,
        billing_city=billing_city,
        billing_county=billing_county,
        billing_postcode=billing_postcode,
        billing_country=billing_country
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer, True  # New customer created


def get_all_customers(db: Session, skip: int = 0, limit: int = 100) -> List[Customer]:
    """Get all customers with pagination."""
    return db.query(Customer).offset(skip).limit(limit).all()


# ============== VEHICLE OPERATIONS ==============

def get_vehicle_by_registration(db: Session, registration: str, customer_id: int) -> Optional[Vehicle]:
    """Get vehicle by registration for a specific customer."""
    return db.query(Vehicle).filter(
        and_(
            Vehicle.registration == registration.upper(),
            Vehicle.customer_id == customer_id
        )
    ).first()


def create_vehicle(
    db: Session,
    customer_id: int,
    registration: str,
    make: str,
    colour: str,
    model: str = None,  # Deprecated - DVLA API doesn't provide model
    tax_status: Optional[str] = None,
    mot_status: Optional[str] = None,
    tax_due_date: Optional[date] = None,
    mot_expiry_date: Optional[date] = None,
) -> tuple[Vehicle, bool]:
    """
    Create a new vehicle or return existing one.

    Returns:
        tuple: (Vehicle object, is_new: bool) - is_new is True if newly created
    """
    registration = registration.upper()
    has_dvla = (
        tax_status is not None or mot_status is not None
        or tax_due_date is not None or mot_expiry_date is not None
    )

    # Check if vehicle already exists for this customer
    existing = get_vehicle_by_registration(db, registration, customer_id)
    if existing:
        # Update details
        existing.make = make
        existing.model = model
        existing.colour = colour
        if has_dvla:
            existing.tax_status = tax_status
            existing.mot_status = mot_status
            existing.tax_due_date = tax_due_date
            existing.mot_expiry_date = mot_expiry_date
            existing.dvla_checked_at = datetime.now(timezone.utc)
            existing.dvla_retry_count = 0
        db.commit()
        db.refresh(existing)
        return existing, False  # Existing vehicle updated

    # Create new vehicle
    vehicle = Vehicle(
        customer_id=customer_id,
        registration=registration,
        make=make,
        model=model,
        colour=colour,
        tax_status=tax_status,
        mot_status=mot_status,
        tax_due_date=tax_due_date,
        mot_expiry_date=mot_expiry_date,
        dvla_checked_at=datetime.now(timezone.utc) if has_dvla else None,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle, True  # New vehicle created


# ============== BOOKING OPERATIONS ==============

def get_booking_by_reference(db: Session, reference: str) -> Optional[Booking]:
    """Get booking by reference."""
    return db.query(Booking).filter(Booking.reference == reference).first()


def get_booking_by_id(db: Session, booking_id: int) -> Optional[Booking]:
    """Get booking by ID."""
    return db.query(Booking).filter(Booking.id == booking_id).first()


def get_pending_booking_by_session(db: Session, session_id: str) -> Optional[Booking]:
    """Get existing PENDING booking for a session (to prevent duplicates)."""
    if not session_id:
        return None
    return db.query(Booking).filter(
        Booking.session_id == session_id,
        Booking.status == BookingStatus.PENDING
    ).first()


def create_booking(
    db: Session,
    customer_id: int,
    vehicle_id: int,
    package: str,
    dropoff_date: date,
    dropoff_time: time,
    pickup_date: date,
    dropoff_flight_number: str = None,
    dropoff_destination: str = None,
    pickup_time: time = None,
    pickup_flight_number: str = None,
    pickup_origin: str = None,
    notes: str = None,
    departure_id: int = None,
    dropoff_slot: str = None,
    arrival_id: int = None,
    session_id: str = None,
    # Customer-provided time override fields
    dropoff_time_override: bool = False,
    dropoff_scheduled_time: time = None,
    dropoff_manual_entry: bool = False,
    dropoff_airline_code: str = None,
    dropoff_airline_name: str = None,
    pickup_time_override: bool = False,
    pickup_scheduled_time: time = None,
    pickup_manual_entry: bool = False,
    pickup_airline_code: str = None,
    pickup_airline_name: str = None,
    # Actual flight times
    flight_departure_time: time = None,
    flight_arrival_time: time = None,
    flight_arrival_date: date = None,
    # Service variant (Park & Ride sets these; M&G omits and DB defaults apply)
    service_type: ServiceType = ServiceType.MEET_GREET,
    traveller_count: int = None,
) -> Booking:
    """Create a new booking."""
    # Generate unique reference
    reference = generate_booking_reference()
    while get_booking_by_reference(db, reference):
        reference = generate_booking_reference()

    # Fetch customer to snapshot their name at time of booking
    customer = get_customer_by_id(db, customer_id)

    booking = Booking(
        reference=reference,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        customer_first_name=customer.first_name if customer else None,
        customer_last_name=customer.last_name if customer else None,
        package=package,
        status=BookingStatus.PENDING,
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        dropoff_flight_number=dropoff_flight_number,
        dropoff_destination=dropoff_destination,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
        pickup_flight_number=pickup_flight_number,
        pickup_origin=pickup_origin,
        notes=notes,
        departure_id=departure_id,
        dropoff_slot=dropoff_slot,
        arrival_id=arrival_id,
        session_id=session_id,
        # Customer-provided time override fields
        dropoff_time_override=dropoff_time_override,
        dropoff_scheduled_time=dropoff_scheduled_time,
        dropoff_manual_entry=dropoff_manual_entry,
        dropoff_airline_code=dropoff_airline_code,
        dropoff_airline_name=dropoff_airline_name,
        pickup_time_override=pickup_time_override,
        pickup_scheduled_time=pickup_scheduled_time,
        pickup_manual_entry=pickup_manual_entry,
        pickup_airline_code=pickup_airline_code,
        pickup_airline_name=pickup_airline_name,
        # Actual flight times
        flight_departure_time=flight_departure_time,
        flight_arrival_time=flight_arrival_time,
        flight_arrival_date=flight_arrival_date,
        # Service variant
        service_type=service_type,
        traveller_count=traveller_count,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def update_booking_status(db: Session, booking_id: int, status: BookingStatus) -> Optional[Booking]:
    """Update booking status."""
    booking = get_booking_by_id(db, booking_id)
    if booking:
        booking.status = status
        db.commit()
        db.refresh(booking)
    return booking


def get_bookings_by_customer(db: Session, customer_id: int) -> List[Booking]:
    """Get all bookings for a customer."""
    return db.query(Booking).filter(Booking.customer_id == customer_id).all()


def get_bookings_by_date_range(
    db: Session,
    start_date: date,
    end_date: date,
    status: BookingStatus = None
) -> List[Booking]:
    """Get bookings within a date range."""
    query = db.query(Booking).filter(
        and_(
            Booking.dropoff_date >= start_date,
            Booking.dropoff_date <= end_date
        )
    )
    if status:
        query = query.filter(Booking.status == status)
    return query.all()


def get_all_bookings(db: Session, skip: int = 0, limit: int = 100) -> List[Booking]:
    """Get all bookings with pagination."""
    return db.query(Booking).order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()


# ============== PAYMENT OPERATIONS ==============

def get_payment_by_intent_id(db: Session, stripe_payment_intent_id: str) -> Optional[Payment]:
    """Get payment by Stripe payment intent ID."""
    return db.query(Payment).filter(
        Payment.stripe_payment_intent_id == stripe_payment_intent_id
    ).first()


def get_payment_by_booking_id(db: Session, booking_id: int) -> Optional[Payment]:
    """Get payment for a booking."""
    return db.query(Payment).filter(Payment.booking_id == booking_id).first()


def create_payment(
    db: Session,
    booking_id: int,
    stripe_payment_intent_id: str,
    amount_pence: int,
    currency: str = "gbp",
    stripe_customer_id: str = None
) -> Payment:
    """Create a new payment record."""
    payment = Payment(
        booking_id=booking_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        stripe_customer_id=stripe_customer_id,
        amount_pence=amount_pence,
        currency=currency,
        status=PaymentStatus.PENDING
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def update_payment_status(
    db: Session,
    stripe_payment_intent_id: str,
    status: PaymentStatus,
    paid_at: datetime = None
) -> tuple[Optional[Payment], bool]:
    """
    Update payment status.

    Returns:
        tuple of (Payment or None, was_already_processed: bool)
        was_already_processed is True if payment was already in SUCCEEDED status
    """
    payment = get_payment_by_intent_id(db, stripe_payment_intent_id)
    if payment:
        # Refresh against the DB before reading status. SQLAlchemy's session
        # cache returns the same object reference on a second .first() lookup
        # within the same transaction — so if a CONCURRENT duplicate webhook
        # already flipped this payment to SUCCEEDED (and committed under the
        # caller's advisory lock), our cached payment.status is still PENDING
        # until this refresh. Without it, was_already_processed is False and
        # we'd redo the payment + booking writes plus all downstream
        # idempotency-gated tasks (planner fire, dvla check, promo mark,
        # slot booking) a second time.
        db.refresh(payment)

        # Check if already processed (idempotency for duplicate webhooks)
        was_already_processed = payment.status == PaymentStatus.SUCCEEDED

        if not was_already_processed:
            payment.status = status
            if paid_at:
                payment.paid_at = paid_at

            # Also update booking status if payment succeeded. Both writes
            # commit together in ONE trailing commit so:
            #   1. The caller's transaction-scoped advisory lock (held for
            #      the capacity-race recheck in the webhook handler) stays
            #      held across BOTH writes — pre-2026-05-29 this used two
            #      commits and released the lock between payment-flip and
            #      booking-flip, re-opening the oversell window.
            #   2. A crash between the writes can no longer leave a
            #      SUCCEEDED payment paired with a PENDING booking.
            if status == PaymentStatus.SUCCEEDED:
                booking = get_booking_by_id(db, payment.booking_id)
                if booking:
                    booking.status = BookingStatus.CONFIRMED

            db.commit()
            db.refresh(payment)

        return payment, was_already_processed

    return None, False


def record_refund(
    db: Session,
    stripe_payment_intent_id: str,
    refund_id: str,
    refund_amount_pence: int,
    refund_reason: str = None
) -> Optional[Payment]:
    """Record a refund on a payment."""
    payment = get_payment_by_intent_id(db, stripe_payment_intent_id)
    if payment:
        payment.refund_id = refund_id
        payment.refund_amount_pence = refund_amount_pence
        payment.refund_reason = refund_reason
        payment.refunded_at = datetime.utcnow()

        if refund_amount_pence >= payment.amount_pence:
            payment.status = PaymentStatus.REFUNDED
            # Update booking status
            booking = get_booking_by_id(db, payment.booking_id)
            if booking:
                booking.status = BookingStatus.REFUNDED
                try:
                    from referral_service import disqualify_referral_for_booking

                    disqualify_referral_for_booking(db, booking)
                except Exception as referral_error:
                    print(
                        "[referrals] Failed to disqualify refunded referral "
                        f"for booking {booking.id}: {referral_error}"
                    )
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED

        db.commit()
        db.refresh(payment)

    return payment


# ============== FLIGHT DEPARTURE OPERATIONS ==============

def get_departures_by_date(db: Session, flight_date: date) -> List[FlightDeparture]:
    """Get all departure flights for a specific date."""
    return db.query(FlightDeparture).filter(
        FlightDeparture.date == flight_date
    ).order_by(FlightDeparture.departure_time).all()


def get_departure_by_number_and_date(
    db: Session, flight_number: str, flight_date: date
) -> Optional[FlightDeparture]:
    """Get a specific departure flight by number and date."""
    return db.query(FlightDeparture).filter(
        and_(
            FlightDeparture.flight_number == flight_number,
            FlightDeparture.date == flight_date
        )
    ).first()


def book_departure_slot(db: Session, flight_id: int, slot_type: str) -> dict:
    """
    Book a slot on a departure flight.

    Args:
        db: Database session
        flight_id: The departure flight ID
        slot_type: 'early' (2½ hours before), 'standard' (2 hours before), or 'late' (1½ hours before)

    Returns:
        dict with 'success' (bool), 'message' (str), and optionally 'slots_remaining' (int)
    """
    flight = db.query(FlightDeparture).filter(FlightDeparture.id == flight_id).first()
    if not flight:
        return {"success": False, "message": "Flight not found"}

    # Check if this is a "Call Us only" flight (capacity_tier = 0)
    if flight.capacity_tier == 0:
        return {"success": False, "message": "This flight requires calling to book", "call_us": True}

    max_per_slot = flight.max_slots_per_time

    if slot_type == 'early':
        if flight.slots_booked_early >= max_per_slot:
            return {"success": False, "message": "No early slots available", "slots_remaining": 0}
        flight.slots_booked_early += 1
        slots_remaining = max_per_slot - flight.slots_booked_early
    elif slot_type == 'late':
        if flight.slots_booked_late >= max_per_slot:
            return {"success": False, "message": "No late slots available", "slots_remaining": 0}
        flight.slots_booked_late += 1
        slots_remaining = max_per_slot - flight.slots_booked_late
    else:
        return {"success": False, "message": "Invalid slot type. Use 'early' or 'late'"}

    # Record history snapshot after slot booking
    record_departure_history(db, flight, 'updated', 'system')

    db.commit()
    return {
        "success": True,
        "message": f"Slot booked successfully",
        "slots_remaining": slots_remaining
    }


def release_departure_slot(db: Session, flight_id: int, slot_type: str) -> dict:
    """
    Release a previously booked slot on a departure flight.

    Args:
        db: Database session
        flight_id: The departure flight ID
        slot_type: 'early' (2½ hours before), 'standard' (2 hours before), or 'late' (1½ hours before)

    Returns:
        dict with 'success' (bool) and 'message' (str)
    """
    flight = db.query(FlightDeparture).filter(FlightDeparture.id == flight_id).first()
    if not flight:
        return {"success": False, "message": "Flight not found"}

    if slot_type == 'early':
        if flight.slots_booked_early > 0:
            flight.slots_booked_early -= 1
        else:
            return {"success": False, "message": "No early slots to release"}
    elif slot_type == 'late':
        if flight.slots_booked_late > 0:
            flight.slots_booked_late -= 1
        else:
            return {"success": False, "message": "No late slots to release"}
    else:
        return {"success": False, "message": "Invalid slot type. Use 'early' or 'late'"}

    # Record history snapshot after slot release
    record_departure_history(db, flight, 'updated', 'system')

    db.commit()
    return {"success": True, "message": "Slot released successfully"}


# ============== FLIGHT ARRIVAL OPERATIONS ==============

def get_arrivals_by_date(db: Session, flight_date: date) -> List[FlightArrival]:
    """Get all arrival flights for a specific date."""
    return db.query(FlightArrival).filter(
        FlightArrival.date == flight_date
    ).order_by(FlightArrival.arrival_time).all()


def get_arrival_by_number_and_date(
    db: Session, flight_number: str, flight_date: date
) -> Optional[FlightArrival]:
    """Get a specific arrival flight by number and date."""
    return db.query(FlightArrival).filter(
        and_(
            FlightArrival.flight_number == flight_number,
            FlightArrival.date == flight_date
        )
    ).first()


# ============== FLIGHT HISTORY ==============

def record_departure_history(
    db: Session,
    flight: FlightDeparture,
    change_type: str,
    changed_by: str = None
) -> FlightDepartureHistory:
    """Record a snapshot of a flight departure for audit history."""
    history = FlightDepartureHistory(
        flight_id=flight.id,
        date=flight.date,
        flight_number=flight.flight_number,
        airline_code=flight.airline_code,
        airline_name=flight.airline_name,
        departure_time=flight.departure_time,
        destination_code=flight.destination_code,
        destination_name=flight.destination_name,
        capacity_tier=flight.capacity_tier,
        slots_booked_early=flight.slots_booked_early,
        slots_booked_late=flight.slots_booked_late,
        change_type=change_type,
        changed_by=changed_by
    )
    db.add(history)
    db.flush()
    return history


def record_arrival_history(
    db: Session,
    flight: FlightArrival,
    change_type: str,
    changed_by: str = None
) -> FlightArrivalHistory:
    """Record a snapshot of a flight arrival for audit history."""
    history = FlightArrivalHistory(
        flight_id=flight.id,
        date=flight.date,
        flight_number=flight.flight_number,
        airline_code=flight.airline_code,
        airline_name=flight.airline_name,
        departure_time=flight.departure_time,
        arrival_time=flight.arrival_time,
        origin_code=flight.origin_code,
        origin_name=flight.origin_name,
        change_type=change_type,
        changed_by=changed_by
    )
    db.add(history)
    db.flush()
    return history


def get_departure_history(db: Session, flight_id: int) -> List[FlightDepartureHistory]:
    """Get all history records for a departure flight."""
    return db.query(FlightDepartureHistory).filter(
        FlightDepartureHistory.flight_id == flight_id
    ).order_by(FlightDepartureHistory.changed_at.desc()).all()


def get_arrival_history(db: Session, flight_id: int) -> List[FlightArrivalHistory]:
    """Get all history records for an arrival flight."""
    return db.query(FlightArrivalHistory).filter(
        FlightArrivalHistory.flight_id == flight_id
    ).order_by(FlightArrivalHistory.changed_at.desc()).all()


# ============== COMBINED BOOKING FLOW ==============

def create_full_booking(
    db: Session,
    # Customer details
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    # Billing address
    billing_address1: str,
    billing_city: str,
    billing_postcode: str,
    billing_country: str,
    # Vehicle details
    registration: str,
    make: str,
    colour: str,
    # Booking details
    package: str,
    dropoff_date: date,
    dropoff_time: time,
    pickup_date: date,
    # Optional fields
    model: str = None,  # Deprecated - DVLA API doesn't provide model
    billing_address2: str = None,
    billing_county: str = None,
    dropoff_flight_number: str = None,
    dropoff_destination: str = None,
    pickup_time: time = None,
    pickup_flight_number: str = None,
    pickup_origin: str = None,
    # Payment details
    stripe_payment_intent_id: str = None,
    amount_pence: int = None,
    # Flight slot details
    departure_id: int = None,
    dropoff_slot: str = None,
    arrival_id: int = None,
    # Session tracking
    session_id: str = None,
    # Customer-provided time override fields
    dropoff_time_override: bool = False,
    dropoff_scheduled_time: time = None,
    dropoff_manual_entry: bool = False,
    dropoff_airline_code: str = None,
    dropoff_airline_name: str = None,
    pickup_time_override: bool = False,
    pickup_scheduled_time: time = None,
    pickup_manual_entry: bool = False,
    pickup_airline_code: str = None,
    pickup_airline_name: str = None,
    # Actual flight times
    flight_departure_time: time = None,
    flight_arrival_time: time = None,
    flight_arrival_date: date = None,
) -> dict:
    """
    Create a complete booking with customer, vehicle, booking, and payment records.
    Returns dict with all created objects.
    """
    # 1. Create or update customer
    customer, _is_new_customer = create_customer(
        db=db,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        billing_address1=billing_address1,
        billing_address2=billing_address2,
        billing_city=billing_city,
        billing_county=billing_county,
        billing_postcode=billing_postcode,
        billing_country=billing_country
    )

    # 2. Create or update vehicle
    vehicle, _is_new_vehicle = create_vehicle(
        db=db,
        customer_id=customer.id,
        registration=registration,
        make=make,
        model=model,
        colour=colour
    )

    # 3. Create booking
    booking = create_booking(
        db=db,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        package=package,
        dropoff_date=dropoff_date,
        dropoff_time=dropoff_time,
        pickup_date=pickup_date,
        dropoff_flight_number=dropoff_flight_number,
        dropoff_destination=dropoff_destination,
        pickup_time=pickup_time,
        pickup_flight_number=pickup_flight_number,
        pickup_origin=pickup_origin,
        departure_id=departure_id,
        dropoff_slot=dropoff_slot,
        arrival_id=arrival_id,
        session_id=session_id,
        # Customer-provided time override fields
        dropoff_time_override=dropoff_time_override,
        dropoff_scheduled_time=dropoff_scheduled_time,
        dropoff_manual_entry=dropoff_manual_entry,
        dropoff_airline_code=dropoff_airline_code,
        dropoff_airline_name=dropoff_airline_name,
        pickup_time_override=pickup_time_override,
        pickup_scheduled_time=pickup_scheduled_time,
        pickup_manual_entry=pickup_manual_entry,
        pickup_airline_code=pickup_airline_code,
        pickup_airline_name=pickup_airline_name,
        # Actual flight times
        flight_departure_time=flight_departure_time,
        flight_arrival_time=flight_arrival_time,
        flight_arrival_date=flight_arrival_date,
    )

    # 4. Create payment record if stripe details provided
    payment = None
    if stripe_payment_intent_id and amount_pence:
        payment = create_payment(
            db=db,
            booking_id=booking.id,
            stripe_payment_intent_id=stripe_payment_intent_id,
            amount_pence=amount_pence
        )

    return {
        "customer": customer,
        "vehicle": vehicle,
        "booking": booking,
        "payment": payment
    }


# ============== CAPACITY GATE ==============

def find_overcapacity_day_in_stay(
    db: Session,
    dropoff_date: date,
    pickup_date: date,
    cap: int = None,
    cap_by_date: Optional[dict] = None,
    cap_field: str = "online_spaces",
    exclude_booking_id: Optional[int] = None,
) -> Optional[tuple]:
    """Walk every day in [dropoff_date, pickup_date] and return (day, count)
    for the first day where existing occupancy + this booking would push
    over capacity. None if all days fit.

    `cap` is kept for legacy callers/tests. New production paths pass
    `cap_by_date` from parking_capacity_settings:
      - cap_field='online_spaces' for customer checkout
      - cap_field='total_spaces' for admin/manual bookings

    Counts CONFIRMED + COMPLETED only — PENDING (in-checkout carts) are
    excluded after the 2026-05-21 review: mid-flow carts inflated the
    count against real customers trying to book real spots. Two customers
    racing for the same last slot is handled first-come-first-served at
    this gate: whoever calls /api/payments/create-intent and commits a
    CONFIRMED row first wins; the second customer hits this check and
    gets 400 "Sorry, we're full" with phone routing.

    `exclude_booking_id` is retained for safety on the few legacy paths
    that pass it (e.g. resubmitting an existing PENDING). Now that
    PENDING is universally excluded the practical effect is no-op for
    that case, but keeping the param avoids a wider call-site cleanup.

    Returns (offending_date, current_count, cap) — count is the number of
    bookings already on that day (excluding the optional excluded one),
    so the calling endpoint can render an informative error.
    """
    from datetime import timedelta as _td  # local import to keep top-of-file tidy

    q = db.query(Booking).filter(
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
        Booking.dropoff_date <= pickup_date,
        Booking.pickup_date >= dropoff_date,
    )
    if exclude_booking_id is not None:
        q = q.filter(Booking.id != exclude_booking_id)
    q = exclude_staging_e2e_capacity_bookings(q)
    overlapping = q.all()

    cursor = dropoff_date
    while cursor <= pickup_date:
        count = sum(1 for b in overlapping if b.dropoff_date <= cursor <= b.pickup_date)
        date_cap = cap
        if cap_by_date is not None:
            date_capacity = cap_by_date.get(cursor.isoformat(), {})
            date_cap = date_capacity.get(cap_field)
        if date_cap is None:
            date_cap = CURRENT_ONLINE_SPACES if cap_field == "online_spaces" else CURRENT_TOTAL_SPACES
        if count + 1 > date_cap:
            if cap_by_date is None:
                return (cursor, count)
            return (cursor, count, int(date_cap))
        cursor = cursor + _td(days=1)
    return None


def find_overcapacity_day_in_stay_locked(
    db: Session,
    dropoff_date: date,
    pickup_date: date,
    cap: int = None,
    cap_by_date: Optional[dict] = None,
    cap_field: str = "online_spaces",
    exclude_booking_id: Optional[int] = None,
) -> Optional[tuple]:
    """find_overcapacity_day_in_stay() preceded by per-date advisory locks.

    Acquires SELECT pg_advisory_xact_lock(hashtext('booking_capacity:DATE'))
    for each date in [dropoff_date, pickup_date], then runs the bare
    capacity check under those locks. Legacy cap callers get
    (offending_date, current_count); dynamic capacity callers get
    (offending_date, current_count, cap).

    Closes the check-then-write race: a second request racing for the
    same date BLOCKS at lock acquisition until the first request's
    transaction commits or rolls back (xact-scoped locks release at tx
    end), so the second request's recount sees the first's CONFIRMED row.

    Lock iteration walks the CLOSED range [dropoff_date, pickup_date]
    (inclusive on both ends) in ascending date order — so two
    concurrent requests with overlapping date sets always queue FIFO
    on the same lock keys (June 1 always before June 2) rather than
    cross-deadlocking on e.g. {Jun 1, Jun 2} vs {Jun 2, Jun 1}.

    Precondition: dropoff_date <= pickup_date (caller-validated
    upstream). If reversed, the iteration is a silent no-op and the
    bare find_overcapacity_day_in_stay() returns None — matches the
    bare function's own behaviour on reversed input. This helper
    intentionally does NOT defensively swap, to keep its contract
    identical to the bare function and avoid masking upstream
    validation bugs.

    Used when confirming customer-paid bookings so concurrent requests
    cannot oversell the date-effective online cap. Manual/admin booking
    paths use the same date-effective capacity schedule with
    cap_field='total_spaces'.

    Must be called inside an active SQLAlchemy transaction (the default
    for the FastAPI get_db dependency). No other code path in this
    codebase uses pg_advisory_xact_lock, so the hashtext key space has
    no collision risk.
    """
    from datetime import timedelta as _td
    from sqlalchemy import text as _sql_text

    cursor = dropoff_date
    while cursor <= pickup_date:
        db.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"booking_capacity:{cursor.isoformat()}"},
        )
        cursor = cursor + _td(days=1)

    return find_overcapacity_day_in_stay(
        db,
        dropoff_date=dropoff_date,
        pickup_date=pickup_date,
        cap=cap,
        cap_by_date=cap_by_date,
        cap_field=cap_field,
        exclude_booking_id=exclude_booking_id,
    )


# ---- Time-aware capacity (peak concurrency) --------------------------------
#
# The per-day gates above count any booking TOUCHING a date as +1, which
# overcounts on turnover days: on 2026-07-04 prod had 80 bookings touching
# the day but only 68 cars present at once (10 picked up / 9 dropped off
# that day). The helpers below sweep event boundaries inside the customer's
# stay window and gate on peak CONCURRENT cars instead.

CAPACITY_GATE_TIME_AWARE_ENV = "CAPACITY_GATE_TIME_AWARE"

# A refunded booking's car is still on site until its pickup date, so it
# occupies a space even though the money came back.
TIME_AWARE_OCCUPYING_STATUSES = (
    BookingStatus.CONFIRMED,
    BookingStatus.COMPLETED,
    BookingStatus.REFUNDED,
)


def is_capacity_gate_time_aware() -> bool:
    raw = os.environ.get(CAPACITY_GATE_TIME_AWARE_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def fetch_bookings_overlapping_window(
    db: Session,
    start_date: date,
    end_date: date,
    statuses,
    exclude_booking_id: Optional[int] = None,
) -> list:
    """Booking rows whose stay touches [start_date, end_date]. Split out of
    _stay_sweep_events so batched callers (check-slots) can fetch once and
    sweep several candidate windows over the same rows."""
    q = db.query(Booking).filter(
        Booking.status.in_(list(statuses)),
        Booking.dropoff_date <= end_date,
        Booking.pickup_date >= start_date,
    )
    if exclude_booking_id is not None:
        q = q.filter(Booking.id != exclude_booking_id)
    q = exclude_staging_e2e_capacity_bookings(q)
    return q.all()


def _events_from_bookings(
    bookings,
    window_start: datetime,
    window_end: datetime,
    arrivals_first_at_ties: bool = False,
) -> list:
    """(datetime, delta) events for pre-fetched bookings, truncated to the
    window. Bookings missing a time are worst-cased: drop-off at 00:00,
    pickup at 23:59.

    Default sort: departures (-1) before probes (0) before arrivals (+1)
    at the same instant — a pickup at T frees the space for a drop-off at
    T. `arrivals_first_at_ties=True` restores the legacy check-slot order
    (a back-to-back swap counts as a transient collision), kept for the
    flag-off path only.
    """
    events = []
    for b in bookings:
        b_drop = datetime.combine(b.dropoff_date, b.dropoff_time or time(0, 0))
        b_pick = datetime.combine(b.pickup_date, b.pickup_time or time(23, 59))
        enter = max(b_drop, window_start)
        leave = min(b_pick, window_end)
        if enter < leave:
            events.append((enter, +1))
            events.append((leave, -1))
    tie = (lambda d: -d) if arrivals_first_at_ties else (lambda d: d)
    events.sort(key=lambda e: (e[0], tie(e[1])))
    return events


def _stay_sweep_events(
    db: Session,
    window_start: datetime,
    window_end: datetime,
    statuses,
    exclude_booking_id: Optional[int] = None,
    arrivals_first_at_ties: bool = False,
) -> list:
    """Fetch + build in one step; see the two helpers above."""
    rows = fetch_bookings_overlapping_window(
        db, window_start.date(), window_end.date(), statuses, exclude_booking_id,
    )
    return _events_from_bookings(
        rows, window_start, window_end, arrivals_first_at_ties=arrivals_first_at_ties,
    )


def peak_concurrent_occupancy(
    db: Session,
    window_start: datetime,
    window_end: datetime,
    statuses=TIME_AWARE_OCCUPYING_STATUSES,
    exclude_booking_id: Optional[int] = None,
    arrivals_first_at_ties: bool = False,
) -> int:
    """Peak concurrent car count over [window_start, window_end]."""
    rows = fetch_bookings_overlapping_window(
        db, window_start.date(), window_end.date(), statuses, exclude_booking_id,
    )
    return peak_concurrent_from_bookings(
        rows, window_start, window_end, arrivals_first_at_ties=arrivals_first_at_ties,
    )


def peak_concurrent_from_bookings(
    bookings,
    window_start: datetime,
    window_end: datetime,
    arrivals_first_at_ties: bool = False,
) -> int:
    """Peak concurrent car count over the window, from pre-fetched rows —
    lets the batched check-slots endpoint sweep each candidate drop-off
    time without re-querying."""
    peak = 0
    current = 0
    for _, delta in _events_from_bookings(
        bookings, window_start, window_end,
        arrivals_first_at_ties=arrivals_first_at_ties,
    ):
        current += delta
        if current > peak:
            peak = current
    return peak


def _cap_for_day(day: date, cap, cap_by_date, cap_field: str):
    if cap_by_date is not None:
        date_cap = cap_by_date.get(day.isoformat(), {}).get(cap_field)
        if date_cap is not None:
            return date_cap
    if cap is not None:
        return cap
    return CURRENT_ONLINE_SPACES if cap_field == "online_spaces" else CURRENT_TOTAL_SPACES


def find_overcapacity_moment_in_stay(
    db: Session,
    dropoff_date: date,
    pickup_date: date,
    dropoff_time: Optional[time] = None,
    pickup_time: Optional[time] = None,
    cap: int = None,
    cap_by_date: Optional[dict] = None,
    cap_field: str = "online_spaces",
    exclude_booking_id: Optional[int] = None,
) -> Optional[tuple]:
    """Time-aware twin of find_overcapacity_day_in_stay: gate on peak
    CONCURRENT cars during the customer's stay window instead of bookings
    touching each day. Same return contract — (day, count) for legacy `cap`
    callers, (day, count, cap) with `cap_by_date` — so
    unpack_capacity_offending works on either gate's result.

    Missing times are worst-cased (drop 00:00 / pick 23:59), so a
    dates-only call degrades to the conservative per-day behaviour rather
    than under-counting. Counts CONFIRMED + COMPLETED + REFUNDED — PENDING
    stays excluded exactly as in the per-day gate (2026-05-21 review), and
    REFUNDED is added because the car is still physically on site.
    """
    window_start = datetime.combine(dropoff_date, dropoff_time or time(0, 0))
    window_end = datetime.combine(pickup_date, pickup_time or time(23, 59))
    if window_end <= window_start:
        # Inverted/zero-length window: never treat as "fits". A booking
        # confirmed with exit <= entry would also be invisible to every
        # future sweep (its own enter < leave never holds), so fail CLOSED
        # with the same offending contract as an over-cap day.
        if cap_by_date is None:
            return (dropoff_date, 0)
        return (dropoff_date, 0, int(_cap_for_day(dropoff_date, cap, cap_by_date, cap_field)))

    def cap_for(day: date):
        return _cap_for_day(day, cap, cap_by_date, cap_field)

    events = _stay_sweep_events(
        db, window_start, window_end,
        TIME_AWARE_OCCUPYING_STATUSES, exclude_booking_id,
    )
    # Zero-delta probes at the window start and at each midnight inside the
    # window: concurrency is constant between events, but the date-effective
    # cap can change at a day boundary with no event on it.
    probes = [(window_start, 0)]
    cursor = dropoff_date + timedelta(days=1)
    while cursor <= pickup_date:
        probe = datetime.combine(cursor, time(0, 0))
        if window_start < probe < window_end:
            probes.append((probe, 0))
        cursor = cursor + timedelta(days=1)
    events = sorted(events + probes, key=lambda e: (e[0], e[1]))

    current = 0
    for moment, delta in events:
        current += delta
        date_cap = cap_for(moment.date())
        if current + 1 > date_cap:
            if cap_by_date is None:
                return (moment.date(), current)
            return (moment.date(), current, int(date_cap))
    return None


def find_overcapacity_moment_in_stay_locked(
    db: Session,
    dropoff_date: date,
    pickup_date: date,
    dropoff_time: Optional[time] = None,
    pickup_time: Optional[time] = None,
    cap: int = None,
    cap_by_date: Optional[dict] = None,
    cap_field: str = "online_spaces",
    exclude_booking_id: Optional[int] = None,
) -> Optional[tuple]:
    """find_overcapacity_moment_in_stay() behind the same per-date advisory
    locks as find_overcapacity_day_in_stay_locked — identical key space and
    ascending-date order, so time-aware and per-day writers queue on the
    same locks during a flag rollout window.

    Inverted/zero-length windows are rejected up front (fail closed, same
    contract as the bare function) without acquiring any locks.
    """
    from sqlalchemy import text as _sql_text

    window_start = datetime.combine(dropoff_date, dropoff_time or time(0, 0))
    window_end = datetime.combine(pickup_date, pickup_time or time(23, 59))
    if window_end <= window_start:
        if cap_by_date is None:
            return (dropoff_date, 0)
        return (dropoff_date, 0, int(_cap_for_day(dropoff_date, cap, cap_by_date, cap_field)))

    cursor = dropoff_date
    while cursor <= pickup_date:
        db.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"booking_capacity:{cursor.isoformat()}"},
        )
        cursor = cursor + timedelta(days=1)

    return find_overcapacity_moment_in_stay(
        db,
        dropoff_date=dropoff_date,
        pickup_date=pickup_date,
        dropoff_time=dropoff_time,
        pickup_time=pickup_time,
        cap=cap,
        cap_by_date=cap_by_date,
        cap_field=cap_field,
        exclude_booking_id=exclude_booking_id,
    )
