"""
Database service layer for CRUD operations.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, time, datetime
from typing import Optional, List
import random
import string

from db_models import (
    Customer, Vehicle, Booking, Payment, FlightDeparture, FlightArrival,
    BookingStatus, PaymentStatus
)


def generate_booking_reference() -> str:
    """Generate a unique booking reference like TAG-ABC12345."""
    chars = ''.join(random.choices(string.ascii_uppercase, k=3))
    nums = ''.join(random.choices(string.digits, k=5))
    return f"TAG-{chars}{nums}"


# ============== CUSTOMER OPERATIONS ==============

def get_customer_by_email(db: Session, email: str) -> Optional[Customer]:
    """Get customer by email address."""
    return db.query(Customer).filter(Customer.email == email).first()


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
    model: str,
    colour: str
) -> tuple[Vehicle, bool]:
    """
    Create a new vehicle or return existing one.

    Returns:
        tuple: (Vehicle object, is_new: bool) - is_new is True if newly created
    """
    registration = registration.upper()

    # Check if vehicle already exists for this customer
    existing = get_vehicle_by_registration(db, registration, customer_id)
    if existing:
        # Update details
        existing.make = make
        existing.model = model
        existing.colour = colour
        db.commit()
        db.refresh(existing)
        return existing, False  # Existing vehicle updated

    # Create new vehicle
    vehicle = Vehicle(
        customer_id=customer_id,
        registration=registration,
        make=make,
        model=model,
        colour=colour
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
    pickup_time_from: time = None,
    pickup_time_to: time = None,
    pickup_flight_number: str = None,
    pickup_origin: str = None,
    notes: str = None,
    departure_id: int = None,
    dropoff_slot: str = None,
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
        pickup_time_from=pickup_time_from,
        pickup_time_to=pickup_time_to,
        pickup_flight_number=pickup_flight_number,
        pickup_origin=pickup_origin,
        notes=notes,
        departure_id=departure_id,
        dropoff_slot=dropoff_slot,
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
        # Check if already processed (idempotency for duplicate webhooks)
        was_already_processed = payment.status == PaymentStatus.SUCCEEDED

        if not was_already_processed:
            payment.status = status
            if paid_at:
                payment.paid_at = paid_at
            db.commit()
            db.refresh(payment)

            # Also update booking status if payment succeeded
            if status == PaymentStatus.SUCCEEDED:
                booking = get_booking_by_id(db, payment.booking_id)
                if booking:
                    booking.status = BookingStatus.CONFIRMED
                    db.commit()

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
        slot_type: 'early' (2¾ hours before) or 'late' (2 hours before)

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
        slot_type: 'early' (2¾ hours before) or 'late' (2 hours before)

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
    model: str,
    colour: str,
    # Booking details
    package: str,
    dropoff_date: date,
    dropoff_time: time,
    pickup_date: date,
    # Optional fields
    billing_address2: str = None,
    billing_county: str = None,
    dropoff_flight_number: str = None,
    dropoff_destination: str = None,
    pickup_time: time = None,
    pickup_time_from: time = None,
    pickup_time_to: time = None,
    pickup_flight_number: str = None,
    pickup_origin: str = None,
    # Payment details
    stripe_payment_intent_id: str = None,
    amount_pence: int = None,
    # Flight slot details
    departure_id: int = None,
    dropoff_slot: str = None,
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
        pickup_time_from=pickup_time_from,
        pickup_time_to=pickup_time_to,
        pickup_flight_number=pickup_flight_number,
        pickup_origin=pickup_origin,
        departure_id=departure_id,
        dropoff_slot=dropoff_slot,
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
