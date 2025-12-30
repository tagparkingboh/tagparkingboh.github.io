"""
FastAPI application for TAG booking system.

Stripe webhook configured for payment confirmations.

Provides REST API endpoints for the frontend to:
- Get available time slots for flights
- Create bookings (which hides the booked slot)
- Check parking capacity
- Manage bookings
- Process Stripe payments
"""
import uuid
import secrets
from datetime import date, time, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from models import (
    BookingRequest,
    AdminBookingRequest,
    Booking,
    SlotType,
    AvailableSlotsResponse,
)
from booking_service import get_booking_service, BookingService
from time_slots import get_drop_off_summary, get_pickup_summary
from config import get_settings, is_stripe_configured
import httpx
import os
import re
from stripe_service import (
    PaymentIntentRequest,
    PaymentIntentResponse,
    create_payment_intent,
    get_payment_status,
    verify_webhook_signature,
    refund_payment,
    calculate_price_in_pence,
)

# Database imports
from database import get_db, init_db
from db_models import BookingStatus, PaymentStatus, FlightDeparture, FlightArrival, AuditLog, AuditLogEvent, ErrorLog, ErrorSeverity, MarketingSubscriber, Booking as DbBooking, Vehicle as DbVehicle, User, LoginCode, Session as DbSession
import db_service
import json
import traceback

# Email scheduler
from email_scheduler import start_scheduler, stop_scheduler

# Email service
from email_service import send_booking_confirmation_email, send_login_code_email


# Initialize FastAPI app
app = FastAPI(
    title="TAG Parking Booking API",
    description="Backend API for TAG airport parking booking system",
    version="1.0.0",
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite dev server (alternate port)
        "http://localhost:3000",
        "https://tagparkingboh.github.io",  # GitHub Pages
        "https://tagparking.co.uk",  # Production domain
        "https://www.tagparking.co.uk",  # Production domain with www
        "https://staging.tagparking.co.uk",  # Staging environment
        "https://tagparkingbohgithubio-staging.up.railway.app",  # Railway staging
        "https://staging-tagparking.netlify.app",  # Netlify staging frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_migrations():
    """Run database migrations on startup."""
    from sqlalchemy import text
    from database import SessionLocal

    db = SessionLocal()
    try:
        # Migration 1: Add confirmation_email_sent columns to bookings
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'bookings'
            AND column_name = 'confirmation_email_sent'
        """))

        if not result.fetchone():
            print("Running migration: Adding confirmation_email_sent columns...")
            db.execute(text("""
                ALTER TABLE bookings
                ADD COLUMN confirmation_email_sent BOOLEAN DEFAULT FALSE
            """))
            db.execute(text("""
                ALTER TABLE bookings
                ADD COLUMN confirmation_email_sent_at TIMESTAMP WITH TIME ZONE
            """))
            db.commit()
            print("Migration completed: confirmation_email_sent columns added")
        else:
            print("Migration check: confirmation_email_sent columns already exist")

        # Migration 2: Add discount_percent column to marketing_subscribers
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'marketing_subscribers'
            AND column_name = 'discount_percent'
        """))

        if not result.fetchone():
            print("Running migration: Adding discount_percent column to marketing_subscribers...")
            db.execute(text("""
                ALTER TABLE marketing_subscribers
                ADD COLUMN discount_percent INTEGER DEFAULT 10
            """))
            db.commit()
            print("Migration completed: discount_percent column added")
        else:
            print("Migration check: discount_percent column already exists")

    except Exception as e:
        print(f"Migration error (non-fatal): {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    """Initialize database and start background scheduler on startup."""
    init_db()
    run_migrations()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background scheduler on shutdown."""
    stop_scheduler()


# Path to flight schedule
FLIGHTS_DATA_PATH = Path(__file__).parent.parent / "tag-website" / "src" / "data" / "flightSchedule.json"


def get_service() -> BookingService:
    """Get the booking service instance."""
    path = str(FLIGHTS_DATA_PATH) if FLIGHTS_DATA_PATH.exists() else None
    return get_booking_service(path)


# ============================================================================
# LOGGING HELPERS
# ============================================================================

def log_audit_event(
    db: Session,
    event: AuditLogEvent,
    request: Request = None,
    session_id: str = None,
    booking_reference: str = None,
    event_data: dict = None,
):
    """
    Log a booking audit event to the database.

    Args:
        db: Database session
        event: The type of event (from AuditLogEvent enum)
        request: FastAPI request object (for IP/user agent)
        session_id: Frontend session ID for tracking incomplete bookings
        booking_reference: Booking reference if available
        event_data: Dictionary of event-specific data (will be JSON serialized)
    """
    try:
        ip_address = None
        user_agent = None

        if request:
            # Get client IP (handle proxies)
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
            else:
                ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "")[:500]

        audit_log = AuditLog(
            session_id=session_id,
            booking_reference=booking_reference,
            event=event,
            event_data=json.dumps(event_data) if event_data else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        # Don't let logging failures break the main flow
        print(f"Failed to log audit event: {e}")
        db.rollback()


def log_error(
    db: Session,
    error_type: str,
    message: str,
    request: Request = None,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    error_code: str = None,
    stack_trace: str = None,
    request_data: dict = None,
    booking_reference: str = None,
    session_id: str = None,
):
    """
    Log an error to the database.

    Args:
        db: Database session
        error_type: Category of error (e.g., "dvla_api", "stripe", "validation")
        message: Human-readable error message
        request: FastAPI request object (for endpoint/IP/user agent)
        severity: Error severity level
        error_code: HTTP status or custom error code
        stack_trace: Full stack trace if available
        request_data: Sanitized request data (remove sensitive info)
        booking_reference: Associated booking reference if known
        session_id: Frontend session ID if known
    """
    try:
        ip_address = None
        user_agent = None
        endpoint = None

        if request:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
            else:
                ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "")[:500]
            endpoint = f"{request.method} {request.url.path}"

        # Sanitize request_data to remove sensitive fields
        if request_data:
            sanitized = {k: v for k, v in request_data.items()
                        if k.lower() not in ('password', 'card', 'cvv', 'cvc', 'secret', 'token')}
        else:
            sanitized = None

        error_log = ErrorLog(
            severity=severity,
            error_type=error_type,
            error_code=error_code,
            message=message,
            stack_trace=stack_trace,
            request_data=json.dumps(sanitized) if sanitized else None,
            endpoint=endpoint,
            booking_reference=booking_reference,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(error_log)
        db.commit()
    except Exception as e:
        # Don't let logging failures break the main flow
        print(f"Failed to log error: {e}")
        db.rollback()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

# Request/Response models for API
class SlotAvailabilityRequest(BaseModel):
    flight_date: date
    flight_time: str  # "HH:MM"
    flight_number: str
    airline_code: str


class DropOffSummaryRequest(BaseModel):
    flight_date: date
    flight_time: str  # "HH:MM"
    slot_type: SlotType


class PickupSummaryRequest(BaseModel):
    arrival_date: date
    arrival_time: str  # "HH:MM"


class CapacityCheckRequest(BaseModel):
    start_date: date
    end_date: date


class BookingResponse(BaseModel):
    success: bool
    booking_id: Optional[str] = None
    message: str
    booking: Optional[Booking] = None


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "TAG Parking Booking API"}


@app.post("/api/slots/available", response_model=AvailableSlotsResponse)
async def get_available_slots(request: SlotAvailabilityRequest):
    """
    Get available time slots for a specific flight.

    Booked slots are automatically hidden from the response.
    The frontend should only display slots returned by this endpoint.
    """
    service = get_service()

    # Parse the time
    time_parts = request.flight_time.split(':')
    flight_time = time(int(time_parts[0]), int(time_parts[1]))

    return service.get_available_slots_for_flight(
        flight_date=request.flight_date,
        flight_time=flight_time,
        flight_number=request.flight_number,
        airline_code=request.airline_code,
    )


@app.post("/api/slots/summary")
async def get_drop_off_info(request: DropOffSummaryRequest):
    """
    Get detailed drop-off information for a selected slot.

    This includes handling of overnight scenarios where the
    drop-off occurs on the day before the flight.
    """
    # Parse the time
    time_parts = request.flight_time.split(':')
    flight_time = time(int(time_parts[0]), int(time_parts[1]))

    return get_drop_off_summary(
        flight_date=request.flight_date,
        flight_time=flight_time,
        slot_type=request.slot_type,
    )


@app.post("/api/pickup/summary")
async def get_pickup_info(request: PickupSummaryRequest):
    """
    Get detailed pickup information for a return flight.

    This includes the 35-minute buffer for passengers to clear
    security/immigration after landing, and handles overnight
    scenarios where late arrivals (e.g., 23:55) result in pickup
    after midnight.
    """
    # Parse the time
    time_parts = request.arrival_time.split(':')
    arrival_time = time(int(time_parts[0]), int(time_parts[1]))

    return get_pickup_summary(
        arrival_date=request.arrival_date,
        arrival_time=arrival_time,
    )


@app.post("/api/capacity/check")
async def check_capacity(request: CapacityCheckRequest):
    """
    Check parking capacity for a date range.

    Returns availability for each day in the range.
    """
    service = get_service()
    return service.check_capacity_for_date_range(
        start_date=request.start_date,
        end_date=request.end_date,
    )


# ==================== PRICING ====================

class PriceCalculationRequest(BaseModel):
    """Request to calculate booking price."""
    drop_off_date: date
    pickup_date: date


class PriceCalculationResponse(BaseModel):
    """Response with calculated price and package info."""
    package: str  # "quick" or "longer"
    package_name: str  # "1 Week" or "2 Weeks"
    duration_days: int
    advance_tier: str  # "early", "standard", or "late"
    days_in_advance: int
    price: float
    price_pence: int
    all_prices: dict  # Show all tier prices for reference


@app.post("/api/pricing/calculate", response_model=PriceCalculationResponse)
async def calculate_price(request: PriceCalculationRequest):
    """
    Calculate booking price based on dates.

    Pricing tiers:
    - Early (>=14 days in advance): 1 week £99, 2 weeks £150
    - Standard (7-13 days in advance): 1 week £109, 2 weeks £160
    - Late (<7 days in advance): 1 week £119, 2 weeks £170

    Duration must be exactly 7 or 14 days.
    """
    from booking_service import BookingService

    duration = (request.pickup_date - request.drop_off_date).days

    # Validate duration
    if duration not in [7, 14]:
        raise HTTPException(
            status_code=400,
            detail=f"Duration must be exactly 7 or 14 days. Got {duration} days."
        )

    # Determine package
    package = BookingService.get_package_for_duration(request.drop_off_date, request.pickup_date)
    package_name = "1 Week" if package == "quick" else "2 Weeks"

    # Calculate advance booking tier
    today = date.today()
    days_in_advance = (request.drop_off_date - today).days
    advance_tier = BookingService.get_advance_tier(request.drop_off_date)

    # Calculate price
    price = BookingService.calculate_price(package, request.drop_off_date)

    return PriceCalculationResponse(
        package=package,
        package_name=package_name,
        duration_days=duration,
        advance_tier=advance_tier,
        days_in_advance=days_in_advance,
        price=price,
        price_pence=int(price * 100),
        all_prices={
            "early": BookingService.PACKAGE_PRICES[package]["early"],
            "standard": BookingService.PACKAGE_PRICES[package]["standard"],
            "late": BookingService.PACKAGE_PRICES[package]["late"],
        }
    )


@app.get("/api/pricing/tiers")
async def get_pricing_tiers():
    """
    Get all pricing tiers for display on the frontend.
    """
    from booking_service import BookingService

    return {
        "packages": {
            "quick": {
                "name": "1 Week",
                "duration_days": 7,
                "prices": BookingService.PACKAGE_PRICES["quick"],
            },
            "longer": {
                "name": "2 Weeks",
                "duration_days": 14,
                "prices": BookingService.PACKAGE_PRICES["longer"],
            },
        },
        "tiers": {
            "early": {"label": "14+ days in advance", "min_days": 14},
            "standard": {"label": "7-13 days in advance", "min_days": 7, "max_days": 13},
            "late": {"label": "Less than 7 days", "max_days": 6},
        }
    }


# =============================================================================
# Promo Code Endpoints
# =============================================================================

# Promo code discount: 10% off any booking
PROMO_DISCOUNT_PERCENT = 10


class PromoCodeValidateRequest(BaseModel):
    """Request to validate a promo code."""
    code: str


class PromoCodeValidateResponse(BaseModel):
    """Response from promo code validation."""
    valid: bool
    message: str
    discount_percent: Optional[int] = None


@app.post("/api/promo/validate", response_model=PromoCodeValidateResponse)
async def validate_promo_code(
    request: PromoCodeValidateRequest,
    db: Session = Depends(get_db),
):
    """
    Validate a promo code and return discount information.

    Promo codes are generated for marketing subscribers and can be used once.
    Currently offers 10% off any booking.
    """
    code = request.code.strip().upper()

    if not code:
        return PromoCodeValidateResponse(
            valid=False,
            message="Please enter a promo code",
        )

    # Look up the promo code in marketing subscribers
    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_code == code
    ).first()

    if not subscriber:
        return PromoCodeValidateResponse(
            valid=False,
            message="Invalid promo code",
        )

    if subscriber.promo_code_used:
        return PromoCodeValidateResponse(
            valid=False,
            message="This promo code has already been used",
        )

    # Valid and unused - use per-code discount percent (default to 10% if not set)
    discount = subscriber.discount_percent if subscriber.discount_percent is not None else PROMO_DISCOUNT_PERCENT
    if discount == 100:
        message = "Promo code applied! 100% off - FREE parking!"
    else:
        message = f"Promo code applied! {discount}% off"
    return PromoCodeValidateResponse(
        valid=True,
        message=message,
        discount_percent=discount,
    )


@app.post("/api/bookings", response_model=BookingResponse)
async def create_booking(request: BookingRequest):
    """
    Create a new booking.

    This will:
    1. Reserve the selected time slot (hiding it from other users)
    2. Update parking capacity for the date range
    3. Return the confirmed booking details
    """
    service = get_service()

    try:
        booking = service.create_booking(request)
        return BookingResponse(
            success=True,
            booking_id=booking.booking_id,
            message="Booking confirmed successfully",
            booking=booking,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: str):
    """
    Retrieve a booking by ID.
    """
    service = get_service()
    booking = service.get_booking(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return BookingResponse(
        success=True,
        booking_id=booking.booking_id,
        message="Booking found",
        booking=booking,
    )


@app.delete("/api/bookings/{booking_id}", response_model=BookingResponse)
async def cancel_booking(booking_id: str):
    """
    Cancel a booking.

    This releases the time slot, making it available for other users.
    """
    service = get_service()

    if service.cancel_booking(booking_id):
        return BookingResponse(
            success=True,
            booking_id=booking_id,
            message="Booking cancelled successfully",
        )
    else:
        raise HTTPException(status_code=404, detail="Booking not found")


@app.get("/api/bookings/email/{email}")
async def get_bookings_by_email(email: str):
    """
    Get all bookings for an email address.
    """
    service = get_service()
    bookings = service.get_bookings_by_email(email)

    return {
        "email": email,
        "count": len(bookings),
        "bookings": bookings,
    }


@app.get("/api/admin/bookings")
async def get_all_bookings(
    date_filter: Optional[date] = Query(None, description="Filter by parking date"),
    include_cancelled: bool = Query(True, description="Include cancelled bookings"),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Get all bookings from database.

    Returns bookings with full details including:
    - Customer info (name, email, phone)
    - Vehicle info (registration, make, model, colour)
    - Booking dates and times
    - Payment info (status, amount, stripe_payment_intent_id)
    """
    from db_models import Booking, Customer, Vehicle, Payment, BookingStatus

    query = db.query(Booking).options(
        joinedload(Booking.customer),
        joinedload(Booking.vehicle),
        joinedload(Booking.payment),
        joinedload(Booking.departure),
    )

    if date_filter:
        # Filter bookings that overlap with the given date
        query = query.filter(
            Booking.dropoff_date <= date_filter,
            Booking.pickup_date >= date_filter,
        )

    if not include_cancelled:
        query = query.filter(Booking.status != BookingStatus.CANCELLED)

    bookings = query.order_by(Booking.dropoff_date.asc()).all()

    # Format bookings for frontend
    result = []
    for b in bookings:
        result.append({
            "id": b.id,
            "reference": b.reference,
            "status": b.status.value if b.status else None,
            "package": b.package,
            "dropoff_date": b.dropoff_date.isoformat() if b.dropoff_date else None,
            "dropoff_time": b.dropoff_time.strftime("%H:%M") if b.dropoff_time else None,
            "dropoff_flight_number": b.dropoff_flight_number,
            "dropoff_airline_name": b.departure.airline_name if b.departure else None,
            "dropoff_destination": b.dropoff_destination,
            "pickup_date": b.pickup_date.isoformat() if b.pickup_date else None,
            "pickup_time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            # Calculate pickup collection time (45 min after landing)
            "pickup_collection_time": (lambda t: f"{((t.hour * 60 + t.minute + 45) // 60) % 24:02d}:{(t.hour * 60 + t.minute + 45) % 60:02d}")(b.pickup_time) if b.pickup_time else None,
            "pickup_time_from": b.pickup_time_from.strftime("%H:%M") if b.pickup_time_from else None,
            "pickup_time_to": b.pickup_time_to.strftime("%H:%M") if b.pickup_time_to else None,
            "pickup_flight_number": b.pickup_flight_number,
            "pickup_origin": b.pickup_origin,
            "notes": b.notes,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "customer": {
                "id": b.customer.id,
                "first_name": b.customer.first_name,
                "last_name": b.customer.last_name,
                "email": b.customer.email,
                "phone": b.customer.phone,
            } if b.customer else None,
            "vehicle": {
                "id": b.vehicle.id,
                "registration": b.vehicle.registration,
                "make": b.vehicle.make,
                "model": b.vehicle.model,
                "colour": b.vehicle.colour,
            } if b.vehicle else None,
            "payment": {
                "id": b.payment.id,
                "status": b.payment.status.value if b.payment.status else None,
                "amount_pence": b.payment.amount_pence,
                "currency": b.payment.currency,
                "stripe_payment_intent_id": b.payment.stripe_payment_intent_id,
                "stripe_customer_id": b.payment.stripe_customer_id,
                "paid_at": b.payment.paid_at.isoformat() if b.payment.paid_at else None,
                "refund_id": b.payment.refund_id,
                "refund_amount_pence": b.payment.refund_amount_pence,
                "refunded_at": b.payment.refunded_at.isoformat() if b.payment.refunded_at else None,
            } if b.payment else None,
        })

    return {
        "count": len(result),
        "date_filter": date_filter.isoformat() if date_filter else None,
        "bookings": result,
    }


@app.get("/api/admin/occupancy/{target_date}")
async def get_daily_occupancy(target_date: date):
    """
    Admin endpoint: Get occupancy count for a specific date.
    """
    service = get_service()
    bookings = service.get_bookings_for_date(target_date)

    return {
        "date": target_date.isoformat(),
        "occupied": len(bookings),
        "available": service.MAX_PARKING_SPOTS - len(bookings),
        "max_capacity": service.MAX_PARKING_SPOTS,
    }


@app.post("/api/admin/bookings", response_model=BookingResponse)
async def create_admin_booking(request: AdminBookingRequest):
    """
    Admin endpoint: Create a booking manually.

    This simplified booking form allows admins to:
    - Set custom drop-off times (not restricted to slots)
    - Override pricing if needed
    - Book for phone/walk-in customers
    - Add bookings even when regular slots are full

    Use this when customers contact you because all slots are booked.
    """
    service = get_service()

    try:
        booking = service.create_admin_booking(request)
        return BookingResponse(
            success=True,
            booking_id=booking.booking_id,
            message=f"Admin booking created successfully (source: {request.booking_source})",
            booking=booking,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/bookings/{booking_id}/cancel")
async def cancel_booking_admin(
    booking_id: int,
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Cancel a booking.

    Sets the booking status to CANCELLED and releases the flight slot
    so it becomes available for other bookings.
    Note: This does NOT automatically refund the payment -
    use the Stripe dashboard for refunds.
    """
    from db_models import Booking, BookingStatus

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    if booking.status == BookingStatus.REFUNDED:
        raise HTTPException(status_code=400, detail="Cannot cancel a refunded booking")

    # Release the flight slot using stored departure_id and dropoff_slot
    slot_released = False
    if booking.departure_id and booking.dropoff_slot:
        result = db_service.release_departure_slot(db, booking.departure_id, booking.dropoff_slot)
        slot_released = result.get("success", False)

    # Update booking status
    booking.status = BookingStatus.CANCELLED
    db.commit()

    message = f"Booking {booking.reference} has been cancelled"
    if slot_released:
        message += " and the flight slot has been released"

    return {
        "success": True,
        "message": message,
        "reference": booking.reference,
        "slot_released": slot_released,
    }


@app.post("/api/admin/bookings/{booking_id}/resend-email")
async def resend_booking_confirmation_email(
    booking_id: int,
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Resend booking confirmation email.

    Sends the confirmation email again for a specific booking.
    Useful when the original email failed or customer didn't receive it.
    """
    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Calculate pickup time (45 min after landing) - format as "From HH:MM onwards"
    pickup_time_str = ""
    if booking.pickup_time:
        landing_minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
        pickup_mins = landing_minutes + 45
        if pickup_mins >= 24 * 60:
            pickup_mins -= 24 * 60
        pickup_time_str = f"From {pickup_mins // 60:02d}:{pickup_mins % 60:02d} onwards"

    # Format dates
    dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
    pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
    dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else ""

    # Format flight info
    departure_flight = f"{booking.dropoff_flight_number} to {booking.dropoff_destination or 'destination'}"
    return_flight = f"{booking.pickup_flight_number or 'N/A'} from {booking.pickup_origin or 'origin'}"

    # Package name
    package_name = "1 Week" if booking.package == "quick" else "2 Weeks"

    # Get payment amount
    amount_paid = "£0.00"
    if booking.payment and booking.payment.amount_pence:
        amount_paid = f"£{booking.payment.amount_pence / 100:.2f}"

    # Send the email
    email_sent = send_booking_confirmation_email(
        email=booking.customer.email,
        first_name=booking.customer.first_name,
        booking_reference=booking.reference,
        dropoff_date=dropoff_date_str,
        dropoff_time=dropoff_time_str,
        pickup_date=pickup_date_str,
        pickup_time=pickup_time_str,
        departure_flight=departure_flight,
        return_flight=return_flight,
        vehicle_make=booking.vehicle.make,
        vehicle_model=booking.vehicle.model,
        vehicle_colour=booking.vehicle.colour,
        vehicle_registration=booking.vehicle.registration,
        package_name=package_name,
        amount_paid=amount_paid,
    )

    if email_sent:
        # Update email sent tracking
        booking.confirmation_email_sent = True
        booking.confirmation_email_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Confirmation email sent to {booking.customer.email}",
            "reference": booking.reference,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send confirmation email. Check SendGrid configuration."
        )


@app.post("/api/admin/bookings/{booking_id}/send-cancellation-email")
async def send_cancellation_email_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Send cancellation email to customer.

    Sends the cancellation notification email for a cancelled booking.
    """
    from db_models import BookingStatus
    from email_service import send_cancellation_email

    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking must be cancelled before sending cancellation email")

    # Format dates
    dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")

    # Send the email
    email_sent = send_cancellation_email(
        email=booking.customer.email,
        first_name=booking.customer.first_name,
        booking_reference=booking.reference,
        dropoff_date=dropoff_date_str,
    )

    if email_sent:
        # Update email sent tracking
        booking.cancellation_email_sent = True
        booking.cancellation_email_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Cancellation email sent to {booking.customer.email}",
            "reference": booking.reference,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send cancellation email. Check SendGrid configuration."
        )


@app.post("/api/admin/bookings/{booking_id}/send-refund-email")
async def send_refund_email_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Send refund confirmation email to customer.

    Sends the refund notification email for a refunded booking.
    """
    from db_models import BookingStatus
    from email_service import send_refund_email

    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking must be cancelled before sending refund email")

    # Get refund amount
    refund_amount = "£0.00"
    if booking.payment and booking.payment.refund_amount_pence:
        refund_amount = f"£{booking.payment.refund_amount_pence / 100:.2f}"
    elif booking.payment and booking.payment.amount_pence:
        # Fall back to original amount if no specific refund amount
        refund_amount = f"£{booking.payment.amount_pence / 100:.2f}"

    # Send the email
    email_sent = send_refund_email(
        email=booking.customer.email,
        first_name=booking.customer.first_name,
        booking_reference=booking.reference,
        refund_amount=refund_amount,
    )

    if email_sent:
        # Update email sent tracking
        booking.refund_email_sent = True
        booking.refund_email_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Refund email sent to {booking.customer.email}",
            "reference": booking.reference,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send refund email. Check SendGrid configuration."
        )


# =============================================================================
# Flight Schedule Endpoints (from database)
# =============================================================================

@app.get("/api/flights/departures/{flight_date}")
async def get_departures_for_date(flight_date: date, db: Session = Depends(get_db)):
    """
    Get all departure flights for a specific date.

    Returns flights in a format compatible with the frontend:
    - date, type, time, airlineCode, airlineName, destinationCode, destinationName, flightNumber
    - Capacity info: capacity_tier, early_slots_available, late_slots_available, is_call_us_only
    """
    departures = db.query(FlightDeparture).filter(
        FlightDeparture.date == flight_date
    ).order_by(FlightDeparture.departure_time).all()

    return [
        {
            "id": d.id,
            "date": d.date.isoformat(),
            "type": "departure",
            "time": d.departure_time.strftime("%H:%M"),
            "airlineCode": d.airline_code,
            "airlineName": d.airline_name,
            "destinationCode": d.destination_code,
            "destinationName": d.destination_name,
            "flightNumber": d.flight_number,
            # Capacity-based fields
            "capacity_tier": d.capacity_tier,
            "max_slots_per_time": d.max_slots_per_time,
            "early_slots_available": d.early_slots_available,
            "late_slots_available": d.late_slots_available,
            "is_call_us_only": d.is_call_us_only,
            "all_slots_booked": d.all_slots_booked,
            # Last slot indicators
            "total_slots_available": d.total_slots_available,
            "is_last_slot": d.is_last_slot,
            "early_is_last_slot": d.early_is_last_slot,
            "late_is_last_slot": d.late_is_last_slot,
        }
        for d in departures
    ]


@app.get("/api/flights/arrivals/{flight_date}")
async def get_arrivals_for_date(flight_date: date, db: Session = Depends(get_db)):
    """
    Get all arrival flights for a specific date.

    Returns flights in a format compatible with the frontend:
    - date, type, time, airlineCode, airlineName, originCode, originName, flightNumber, departureTime
    """
    arrivals = db.query(FlightArrival).filter(
        FlightArrival.date == flight_date
    ).order_by(FlightArrival.arrival_time).all()

    return [
        {
            "id": a.id,
            "date": a.date.isoformat(),
            "type": "arrival",
            "time": a.arrival_time.strftime("%H:%M"),
            "airlineCode": a.airline_code,
            "airlineName": a.airline_name,
            "originCode": a.origin_code,
            "originName": a.origin_name,
            "flightNumber": a.flight_number,
            "departureTime": a.departure_time.strftime("%H:%M") if a.departure_time else None,
        }
        for a in arrivals
    ]


@app.get("/api/flights/schedule/{flight_date}")
async def get_schedule_for_date(flight_date: date, db: Session = Depends(get_db)):
    """
    Get combined flight schedule (departures + arrivals) for a date.

    This matches the format of the original flightSchedule.json file.
    """
    departures = db.query(FlightDeparture).filter(
        FlightDeparture.date == flight_date
    ).order_by(FlightDeparture.departure_time).all()

    arrivals = db.query(FlightArrival).filter(
        FlightArrival.date == flight_date
    ).order_by(FlightArrival.arrival_time).all()

    schedule = []

    for d in departures:
        schedule.append({
            "id": d.id,
            "date": d.date.isoformat(),
            "type": "departure",
            "time": d.departure_time.strftime("%H:%M"),
            "airlineCode": d.airline_code,
            "airlineName": d.airline_name,
            "destinationCode": d.destination_code,
            "destinationName": d.destination_name,
            "flightNumber": d.flight_number,
            "capacity_tier": d.capacity_tier,
            "max_slots_per_time": d.max_slots_per_time,
            "early_slots_available": d.early_slots_available,
            "late_slots_available": d.late_slots_available,
            "is_call_us_only": d.is_call_us_only,
            "all_slots_booked": d.all_slots_booked,
            # Last slot indicators
            "total_slots_available": d.total_slots_available,
            "is_last_slot": d.is_last_slot,
            "early_is_last_slot": d.early_is_last_slot,
            "late_is_last_slot": d.late_is_last_slot,
        })

    for a in arrivals:
        schedule.append({
            "id": a.id,
            "date": a.date.isoformat(),
            "type": "arrival",
            "time": a.arrival_time.strftime("%H:%M"),
            "airlineCode": a.airline_code,
            "airlineName": a.airline_name,
            "originCode": a.origin_code,
            "originName": a.origin_name,
            "flightNumber": a.flight_number,
            "departureTime": a.departure_time.strftime("%H:%M") if a.departure_time else None,
        })

    return schedule


@app.post("/api/flights/departures/{departure_id}/book-slot")
async def book_departure_slot(
    departure_id: int,
    slot_id: str = Query(..., description="Slot ID: '165' for early slot (2¾h before), '120' for late slot (2h before)"),
    db: Session = Depends(get_db)
):
    """
    Book a slot on a departure flight.

    Slot types (based on time before departure):
    - '165' (early): 2¾ hours before departure
    - '120' (late): 2 hours before departure

    Returns success status and remaining slots available.
    """
    # Convert slot_id to slot_type
    slot_type = 'early' if slot_id == "165" else 'late' if slot_id == "120" else None
    if slot_type is None:
        raise HTTPException(status_code=400, detail="Invalid slot ID. Use '165' (early) or '120' (late)")

    result = db_service.book_departure_slot(db, departure_id, slot_type)

    if not result["success"]:
        # Check if this is a "Call Us" situation
        if result.get("call_us"):
            raise HTTPException(status_code=400, detail="This flight requires calling to book")
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@app.get("/api/flights/dates")
async def get_available_dates(db: Session = Depends(get_db)):
    """
    Get all dates that have departure flights available.

    Useful for the date picker to show which dates have flights.
    """
    dates = db.query(FlightDeparture.date).distinct().order_by(FlightDeparture.date).all()
    return [d[0].isoformat() for d in dates]


# =============================================================================
# Incremental Save Endpoints (for booking flow)
# =============================================================================

class CreateCustomerRequest(BaseModel):
    """Request to create/update customer from Step 1."""
    first_name: str
    last_name: str
    email: str
    phone: str
    session_id: Optional[str] = None


class UpdateCustomerBillingRequest(BaseModel):
    """Request to update customer billing address from Step 5."""
    billing_address1: str
    billing_address2: Optional[str] = None
    billing_city: str
    billing_county: Optional[str] = None
    billing_postcode: str
    billing_country: str = "United Kingdom"
    session_id: Optional[str] = None


class CreateVehicleRequest(BaseModel):
    """Request to create/update vehicle from Step 3."""
    customer_id: int
    registration: str
    make: str
    model: str
    colour: str
    session_id: Optional[str] = None


@app.post("/api/customers")
async def create_or_update_customer(
    request: CreateCustomerRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Create or update a customer (Step 1: Contact Details).

    If a customer with this email exists, updates their details.
    Returns the customer ID for use in subsequent steps.
    """
    try:
        customer, is_new_customer = db_service.create_customer(
            db=db,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
        )

        # Log audit event for customer entry
        log_audit_event(
            db=db,
            event=AuditLogEvent.CUSTOMER_ENTERED,
            request=http_request,
            session_id=request.session_id,
            event_data={
                "customer_id": customer.id,
                "email": request.email,
                "is_new_customer": is_new_customer,
            },
        )

        return {
            "success": True,
            "customer_id": customer.id,
            "is_new_customer": is_new_customer,
            "message": "Customer saved successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/customers/{customer_id}/billing")
async def update_customer_billing(
    customer_id: int,
    request: UpdateCustomerBillingRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Update customer billing address (Step 5: Billing Address).
    """
    customer = db_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        customer.billing_address1 = request.billing_address1
        customer.billing_address2 = request.billing_address2
        customer.billing_city = request.billing_city
        customer.billing_county = request.billing_county
        customer.billing_postcode = request.billing_postcode
        customer.billing_country = request.billing_country
        db.commit()
        db.refresh(customer)

        # Check for potential duplicate (same name + postcode, different email)
        potential_duplicate = db_service.find_potential_duplicate_customer(
            db=db,
            first_name=customer.first_name,
            last_name=customer.last_name,
            postcode=request.billing_postcode,
            exclude_email=customer.email,
        )

        # Build event data for audit log
        event_data = {
            "customer_id": customer.id,
            "billing_city": request.billing_city,
            "billing_country": request.billing_country,
        }

        # Add potential duplicate info if found
        if potential_duplicate:
            event_data["potential_duplicate_of"] = potential_duplicate.id
            event_data["potential_duplicate_email"] = potential_duplicate.email
            event_data["match_reason"] = "name_and_postcode"

        # Log audit event for billing address entry
        log_audit_event(
            db=db,
            event=AuditLogEvent.BILLING_ENTERED,
            request=http_request,
            session_id=request.session_id,
            event_data=event_data,
        )

        response_data = {
            "success": True,
            "customer_id": customer.id,
            "message": "Billing address saved successfully",
        }

        # Include potential duplicate warning in response (for admin visibility)
        if potential_duplicate:
            response_data["potential_duplicate"] = {
                "customer_id": potential_duplicate.id,
                "email": potential_duplicate.email,
                "match_reason": "name_and_postcode",
            }

        return response_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/vehicles")
async def create_or_update_vehicle(
    request: CreateVehicleRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Create or update a vehicle (Step 3: Vehicle Details).

    If a vehicle with this registration exists for the customer, updates it.
    Returns the vehicle ID for use in the booking.
    """
    # Validate customer exists
    customer = db_service.get_customer_by_id(db, request.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        vehicle, is_new_vehicle = db_service.create_vehicle(
            db=db,
            customer_id=request.customer_id,
            registration=request.registration,
            make=request.make,
            model=request.model,
            colour=request.colour,
        )

        # Log audit event for vehicle entry
        log_audit_event(
            db=db,
            event=AuditLogEvent.VEHICLE_ENTERED,
            request=http_request,
            session_id=request.session_id,
            event_data={
                "vehicle_id": vehicle.id,
                "customer_id": request.customer_id,
                "registration": request.registration,
                "make": request.make,
                "is_new_vehicle": is_new_vehicle,
            },
        )

        return {
            "success": True,
            "vehicle_id": vehicle.id,
            "is_new_vehicle": is_new_vehicle,
            "message": "Vehicle saved successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# DVLA Vehicle Lookup Endpoint
# =============================================================================

class VehicleLookupRequest(BaseModel):
    """Request to lookup vehicle by registration number."""
    registration: str


class VehicleLookupResponse(BaseModel):
    """Response with vehicle make and colour from DVLA."""
    success: bool
    registration: str
    make: Optional[str] = None
    colour: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/vehicles/dvla-lookup", response_model=VehicleLookupResponse)
async def lookup_vehicle(
    request: VehicleLookupRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Lookup vehicle make and colour from DVLA Vehicle Enquiry Service.

    Takes a UK registration number and returns the make and colour.
    Spaces and special characters are automatically stripped from the registration.
    """
    # Clean the registration number - remove spaces and non-alphanumeric chars
    clean_reg = re.sub(r'[^A-Za-z0-9]', '', request.registration.upper())

    if not clean_reg:
        return VehicleLookupResponse(
            success=False,
            registration=request.registration,
            error="Invalid registration number"
        )

    # Get the appropriate API key based on environment
    settings = get_settings()
    if settings.environment == "production":
        api_key = settings.dvla_api_key_prod
    else:
        api_key = settings.dvla_api_key_test

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="DVLA API is not configured"
        )

    # Call DVLA API - use UAT endpoint for test, production endpoint for live
    if settings.environment == "production":
        dvla_url = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
    else:
        dvla_url = "https://uat.driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                dvla_url,
                json={"registrationNumber": clean_reg},
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                return VehicleLookupResponse(
                    success=True,
                    registration=clean_reg,
                    make=data.get("make"),
                    colour=data.get("colour"),
                )
            elif response.status_code == 404:
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error="Vehicle not found"
                )
            elif response.status_code == 400:
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error="Invalid registration format"
                )
            elif response.status_code == 403:
                log_error(
                    db=db,
                    error_type="dvla_api",
                    message="DVLA API access denied",
                    request=http_request,
                    error_code="403",
                    request_data={"registration": clean_reg},
                )
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error="DVLA API access denied - check API key"
                )
            else:
                log_error(
                    db=db,
                    error_type="dvla_api",
                    message=f"DVLA API error: {response.status_code}",
                    request=http_request,
                    error_code=str(response.status_code),
                    request_data={"registration": clean_reg},
                )
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error=f"DVLA error ({response.status_code})"
                )

    except httpx.TimeoutException:
        log_error(
            db=db,
            error_type="dvla_api",
            message="DVLA API timeout",
            request=http_request,
            severity=ErrorSeverity.WARNING,
            request_data={"registration": clean_reg},
        )
        return VehicleLookupResponse(
            success=False,
            registration=clean_reg,
            error="DVLA service timeout"
        )
    except Exception as e:
        log_error(
            db=db,
            error_type="dvla_api",
            message=str(e),
            request=http_request,
            stack_trace=traceback.format_exc(),
            request_data={"registration": clean_reg},
        )
        return VehicleLookupResponse(
            success=False,
            registration=clean_reg,
            error="Unable to lookup vehicle"
        )


# =============================================================================
# OS Places API - Address Lookup
# =============================================================================

class AddressLookupRequest(BaseModel):
    """Request to lookup addresses by postcode."""
    postcode: str


class Address(BaseModel):
    """A single address from OS Places API."""
    uprn: str
    address: str
    building_name: Optional[str] = None
    building_number: Optional[str] = None
    thoroughfare: Optional[str] = None
    dependent_locality: Optional[str] = None
    post_town: str
    postcode: str
    county: Optional[str] = None


# County lookup by post town (for common Dorset/Hampshire area towns)
POST_TOWN_TO_COUNTY = {
    "BOURNEMOUTH": "Dorset",
    "POOLE": "Dorset",
    "CHRISTCHURCH": "Dorset",
    "WIMBORNE": "Dorset",
    "FERNDOWN": "Dorset",
    "RINGWOOD": "Hampshire",
    "VERWOOD": "Dorset",
    "WAREHAM": "Dorset",
    "SWANAGE": "Dorset",
    "DORCHESTER": "Dorset",
    "WEYMOUTH": "Dorset",
    "BLANDFORD FORUM": "Dorset",
    "SHAFTESBURY": "Dorset",
    "SHERBORNE": "Dorset",
    "BRIDPORT": "Dorset",
    "LYME REGIS": "Dorset",
    "SOUTHAMPTON": "Hampshire",
    "PORTSMOUTH": "Hampshire",
    "WINCHESTER": "Hampshire",
    "BASINGSTOKE": "Hampshire",
    "EASTLEIGH": "Hampshire",
    "FAREHAM": "Hampshire",
    "GOSPORT": "Hampshire",
    "ANDOVER": "Hampshire",
    "ROMSEY": "Hampshire",
    "LYMINGTON": "Hampshire",
    "NEW MILTON": "Hampshire",
    "LONDON": "London",
}


class AddressLookupResponse(BaseModel):
    """Response from address lookup."""
    success: bool
    postcode: Optional[str] = None
    addresses: list[Address] = []
    total_results: int = 0
    error: Optional[str] = None


@app.post("/api/address/postcode-lookup", response_model=AddressLookupResponse)
async def lookup_address(
    request: AddressLookupRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Lookup addresses by postcode using OS Places API.

    Returns a list of addresses at the given postcode for the user to select from.
    """
    # Clean postcode - remove spaces and uppercase
    clean_postcode = request.postcode.strip().upper().replace(" ", "")

    if not clean_postcode:
        return AddressLookupResponse(
            success=False,
            error="Please enter a postcode"
        )

    # Basic UK postcode validation (2-4 chars, then 1-2 digits, then space area)
    if len(clean_postcode) < 5 or len(clean_postcode) > 8:
        return AddressLookupResponse(
            success=False,
            postcode=clean_postcode,
            error="Invalid postcode format"
        )

    settings = get_settings()
    api_key = settings.os_places_api_key

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Address lookup service is not configured"
        )

    # Call OS Places API
    os_url = f"https://api.os.uk/search/places/v1/postcode?postcode={clean_postcode}&key={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(os_url, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                addresses = []
                for result in results:
                    dpa = result.get("DPA", {})
                    post_town = dpa.get("POST_TOWN", "")
                    # Look up county from post town
                    county = POST_TOWN_TO_COUNTY.get(post_town.upper())
                    addresses.append(Address(
                        uprn=dpa.get("UPRN", ""),
                        address=dpa.get("ADDRESS", ""),
                        building_name=dpa.get("BUILDING_NAME"),
                        building_number=dpa.get("BUILDING_NUMBER"),
                        thoroughfare=dpa.get("THOROUGHFARE_NAME") or dpa.get("DEPENDENT_THOROUGHFARE_NAME"),
                        dependent_locality=dpa.get("DEPENDENT_LOCALITY"),
                        post_town=post_town,
                        postcode=dpa.get("POSTCODE", ""),
                        county=county,
                    ))

                # Format postcode with space for display
                formatted_postcode = clean_postcode
                if len(clean_postcode) > 3:
                    formatted_postcode = f"{clean_postcode[:-3]} {clean_postcode[-3:]}"

                return AddressLookupResponse(
                    success=True,
                    postcode=formatted_postcode,
                    addresses=addresses,
                    total_results=data.get("header", {}).get("totalresults", len(addresses))
                )
            elif response.status_code == 400:
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error="Invalid postcode"
                )
            elif response.status_code == 401:
                log_error(
                    db=db,
                    error_type="os_places_api",
                    message="OS Places API authentication failed",
                    request=http_request,
                    error_code="401",
                    request_data={"postcode": clean_postcode},
                )
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error="Address service authentication failed"
                )
            else:
                log_error(
                    db=db,
                    error_type="os_places_api",
                    message=f"OS Places API error: {response.status_code}",
                    request=http_request,
                    error_code=str(response.status_code),
                    request_data={"postcode": clean_postcode},
                )
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error=f"Address lookup failed ({response.status_code})"
                )

    except httpx.TimeoutException:
        log_error(
            db=db,
            error_type="os_places_api",
            message="OS Places API timeout",
            request=http_request,
            severity=ErrorSeverity.WARNING,
            request_data={"postcode": clean_postcode},
        )
        return AddressLookupResponse(
            success=False,
            postcode=clean_postcode,
            error="Address service timeout"
        )
    except Exception as e:
        log_error(
            db=db,
            error_type="os_places_api",
            message=str(e),
            request=http_request,
            stack_trace=traceback.format_exc(),
            request_data={"postcode": clean_postcode},
        )
        return AddressLookupResponse(
            success=False,
            postcode=clean_postcode,
            error="Unable to lookup address"
        )


# =============================================================================
# Marketing Subscriber Endpoint
# =============================================================================

class MarketingSubscribeRequest(BaseModel):
    """Request to subscribe to marketing emails."""
    first_name: str
    last_name: str
    email: str
    source: Optional[str] = "website"


class MarketingSubscribeResponse(BaseModel):
    """Response from marketing subscription."""
    success: bool
    message: str
    is_new_subscriber: bool = True


@app.post("/api/marketing/subscribe", response_model=MarketingSubscribeResponse)
async def subscribe_to_marketing(
    request: MarketingSubscribeRequest,
    db: Session = Depends(get_db),
):
    """
    Subscribe to marketing emails (waitlist/newsletter).

    If the email already exists and is not unsubscribed, returns success with is_new_subscriber=False.
    If the email exists but was unsubscribed, re-subscribes them.
    """
    # Check if subscriber already exists
    existing = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.email == request.email.lower().strip()
    ).first()

    if existing:
        # If they previously unsubscribed, allow them to re-subscribe
        if existing.unsubscribed:
            existing.unsubscribed = False
            existing.unsubscribed_at = None
            existing.first_name = request.first_name.strip()
            existing.last_name = request.last_name.strip()
            existing.welcome_email_sent = False
            existing.welcome_email_sent_at = None
            # Generate new unsubscribe token for security
            existing.unsubscribe_token = secrets.token_urlsafe(32)
            db.commit()
            return MarketingSubscribeResponse(
                success=True,
                message="Welcome back! You've been re-subscribed.",
                is_new_subscriber=True,  # Treat as new for welcome email purposes
            )

        return MarketingSubscribeResponse(
            success=True,
            message="You're already on the list!",
            is_new_subscriber=False,
        )

    try:
        # Generate a secure unsubscribe token
        unsubscribe_token = secrets.token_urlsafe(32)

        subscriber = MarketingSubscriber(
            first_name=request.first_name.strip(),
            last_name=request.last_name.strip(),
            email=request.email.lower().strip(),
            source=request.source,
            unsubscribe_token=unsubscribe_token,
        )
        db.add(subscriber)
        db.commit()

        return MarketingSubscribeResponse(
            success=True,
            message="Thanks for signing up!",
            is_new_subscriber=True,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to subscribe: {str(e)}")


@app.get("/api/marketing/unsubscribe/{token}")
async def unsubscribe_confirmation_page(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Show unsubscribe confirmation page (step 1).

    Returns an HTML page asking user to confirm unsubscription.
    """
    from fastapi.responses import HTMLResponse

    # Find subscriber by token
    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.unsubscribe_token == token
    ).first()

    if not subscriber:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Unsubscribe - TAG Parking</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }
                .container { max-width: 500px; margin: 0 auto; }
                h1 { color: #D9FF00; }
                p { color: #ccc; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Invalid Link</h1>
                <p>This unsubscribe link is not valid or has expired.</p>
                <p>If you need help, contact us at <a href="mailto:support@tagparking.co.uk" style="color: #D9FF00;">support@tagparking.co.uk</a></p>
            </div>
        </body>
        </html>
        """, status_code=404)

    if subscriber.unsubscribed:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Already Unsubscribed - TAG Parking</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }}
                .container {{ max-width: 500px; margin: 0 auto; }}
                h1 {{ color: #D9FF00; }}
                p {{ color: #ccc; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Already Unsubscribed</h1>
                <p>You have already been unsubscribed from TAG Parking emails.</p>
                <p>Email: {subscriber.email}</p>
            </div>
        </body>
        </html>
        """)

    # Show confirmation page
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unsubscribe - TAG Parking</title>
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }}
            .container {{ max-width: 500px; margin: 0 auto; }}
            h1 {{ color: #D9FF00; }}
            p {{ color: #ccc; }}
            .btn {{
                display: inline-block;
                background: #D9FF00;
                color: #1a1a1a;
                padding: 15px 40px;
                text-decoration: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 16px;
                border: none;
                cursor: pointer;
                margin-top: 20px;
            }}
            .btn:hover {{ background: #c4e600; }}
            .email {{ color: #D9FF00; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Unsubscribe</h1>
            <p>Are you sure you want to unsubscribe from TAG Parking marketing emails?</p>
            <p>Email: <span class="email">{subscriber.email}</span></p>
            <form method="POST" action="/api/marketing/unsubscribe/{token}">
                <button type="submit" class="btn">Yes, I'm sure!</button>
            </form>
        </div>
    </body>
    </html>
    """)


@app.post("/api/marketing/unsubscribe/{token}")
async def unsubscribe_from_marketing(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Actually unsubscribe from marketing emails (step 2).

    Returns an HTML page confirming the unsubscription.
    """
    from fastapi.responses import HTMLResponse

    # Find subscriber by token
    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.unsubscribe_token == token
    ).first()

    if not subscriber:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Unsubscribe - TAG Parking</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }
                .container { max-width: 500px; margin: 0 auto; }
                h1 { color: #D9FF00; }
                p { color: #ccc; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Invalid Link</h1>
                <p>This unsubscribe link is not valid or has expired.</p>
                <p>If you need help, contact us at <a href="mailto:support@tagparking.co.uk" style="color: #D9FF00;">support@tagparking.co.uk</a></p>
            </div>
        </body>
        </html>
        """, status_code=404)

    if subscriber.unsubscribed:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Already Unsubscribed - TAG Parking</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }}
                .container {{ max-width: 500px; margin: 0 auto; }}
                h1 {{ color: #D9FF00; }}
                p {{ color: #ccc; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Already Unsubscribed</h1>
                <p>You have already been unsubscribed from TAG Parking emails.</p>
                <p>Email: {subscriber.email}</p>
            </div>
        </body>
        </html>
        """)

    # Mark as unsubscribed
    subscriber.unsubscribed = True
    subscriber.unsubscribed_at = datetime.utcnow()
    db.commit()

    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unsubscribed - TAG Parking</title>
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1a1a1a; color: white; }}
            .container {{ max-width: 500px; margin: 0 auto; }}
            h1 {{ color: #D9FF00; }}
            p {{ color: #ccc; }}
            .success {{ color: #4CAF50; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Unsubscribed Successfully</h1>
            <p class="success">You have been unsubscribed from TAG Parking marketing emails.</p>
            <p>Email: {subscriber.email}</p>
            <p>We're sorry to see you go! If you change your mind, you can sign up again at <a href="https://tagparking.co.uk" style="color: #D9FF00;">tagparking.co.uk</a></p>
        </div>
    </body>
    </html>
    """)


# =============================================================================
# Stripe Payment Endpoints
# =============================================================================

class CreatePaymentRequest(BaseModel):
    """Request to create a payment intent for a booking."""
    # IDs from previous steps (incremental save)
    customer_id: Optional[int] = None
    vehicle_id: Optional[int] = None

    # Customer details (used if customer_id not provided)
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None

    # Billing address
    billing_address1: Optional[str] = None
    billing_address2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_county: Optional[str] = None
    billing_postcode: Optional[str] = None
    billing_country: Optional[str] = "United Kingdom"

    # Vehicle details (used if vehicle_id not provided)
    registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    colour: Optional[str] = None

    # Package selection
    package: str  # "quick" or "longer"

    # Flight details for reference
    flight_number: str
    flight_date: str
    drop_off_date: str
    pickup_date: str
    drop_off_time: Optional[str] = None
    drop_off_slot: Optional[str] = None  # "165" or "120" (minutes before flight)
    departure_id: Optional[int] = None  # ID of the flight departure to book slot on

    # Return flight details (destination/origin names are looked up from flight tables)
    pickup_flight_time: Optional[str] = None  # Landing time "HH:MM"
    pickup_flight_number: Optional[str] = None

    # Session tracking
    session_id: Optional[str] = None

    # Promo code
    promo_code: Optional[str] = None


class CreatePaymentResponse(BaseModel):
    """Response with payment intent details for frontend."""
    client_secret: Optional[str] = None  # None for free bookings (100% off)
    payment_intent_id: Optional[str] = None  # None for free bookings (100% off)
    booking_reference: str
    amount: int
    amount_display: str  # e.g., "£99.00"
    publishable_key: str
    is_free_booking: bool = False  # True when promo code gives 100% off
    # Discount info (optional)
    original_amount: Optional[int] = None
    original_amount_display: Optional[str] = None
    discount_amount: Optional[int] = None
    discount_amount_display: Optional[str] = None
    promo_code_applied: Optional[str] = None


@app.get("/api/stripe/config")
async def get_stripe_config():
    """
    Get Stripe publishable key for frontend initialization.

    The frontend needs the publishable key to initialize Stripe.js.
    """
    settings = get_settings()

    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    return {
        "publishable_key": settings.stripe_publishable_key,
        "is_configured": True,
    }


@app.post("/api/payments/create-intent", response_model=CreatePaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a Stripe PaymentIntent for a booking.

    This is called when the user proceeds to payment. The returned
    client_secret is used by the frontend to complete the payment
    with Stripe Elements.

    Flow:
    1. Frontend collects booking details
    2. Frontend calls this endpoint
    3. Backend creates booking record in PENDING state
    4. Backend creates PaymentIntent with Stripe
    5. Frontend uses client_secret with Stripe Elements
    6. User enters card details and confirms
    7. Stripe webhook confirms payment
    8. Backend updates booking to CONFIRMED
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    try:
        # Debug: log incoming promo code
        print(f"[PROMO] Received request with promo_code: {request.promo_code}")

        # Parse dates first (needed for dynamic pricing)
        dropoff_date = datetime.strptime(request.drop_off_date, "%Y-%m-%d").date()

        # Calculate base amount in pence (using dynamic pricing based on drop-off date)
        original_amount = calculate_price_in_pence(request.package, drop_off_date=dropoff_date)
        pickup_date = datetime.strptime(request.pickup_date, "%Y-%m-%d").date()

        # Check for promo code and apply discount if valid
        discount_amount = 0
        discount_percent = 0
        promo_code_applied = None
        is_free_booking = False
        if request.promo_code:
            promo_code = request.promo_code.strip().upper()
            print(f"[PROMO] Looking up promo code: {promo_code}")
            subscriber = db.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == promo_code
            ).first()
            if subscriber:
                print(f"[PROMO] Found subscriber: {subscriber.email}, used: {subscriber.promo_code_used}")
                if not subscriber.promo_code_used:
                    # Valid promo code - use per-code discount (default 10%)
                    discount_percent = subscriber.discount_percent if subscriber.discount_percent is not None else PROMO_DISCOUNT_PERCENT
                    discount_amount = int(original_amount * discount_percent / 100)
                    promo_code_applied = promo_code
                    is_free_booking = (discount_percent == 100)
                    print(f"[PROMO] Discount applied: {discount_percent}% = {discount_amount} pence (free: {is_free_booking})")
                else:
                    print(f"[PROMO] Code already used!")
            else:
                print(f"[PROMO] No subscriber found with this code")

        # Final amount after discount
        amount = original_amount - discount_amount

        # Calculate drop-off time from slot and flight departure
        dropoff_time = time(12, 0)  # Default to noon
        if request.drop_off_time:
            # Explicit time provided (e.g., from admin)
            time_parts = request.drop_off_time.split(":")
            dropoff_time = time(int(time_parts[0]), int(time_parts[1]))
        elif request.departure_id and request.drop_off_slot:
            # Calculate from flight departure time minus slot minutes
            departure = db.query(FlightDeparture).filter(FlightDeparture.id == request.departure_id).first()
            if departure:
                # Slot is minutes before departure (165 = 2¾h, 120 = 2h)
                slot_minutes = int(request.drop_off_slot)
                dep_hour = departure.departure_time.hour
                dep_min = departure.departure_time.minute
                total_minutes = dep_hour * 60 + dep_min - slot_minutes
                # Handle overnight (negative minutes)
                if total_minutes < 0:
                    total_minutes += 24 * 60
                dropoff_time = time(total_minutes // 60, total_minutes % 60)

        # Parse pickup/landing time and calculate pickup time range (35-60 min after landing)
        pickup_time = None
        pickup_time_from = None
        pickup_time_to = None
        if request.pickup_flight_time:
            time_parts = request.pickup_flight_time.split(":")
            landing_hour = int(time_parts[0])
            landing_min = int(time_parts[1])
            pickup_time = time(landing_hour, landing_min)  # Landing time

            # Calculate pickup window (35-60 minutes after landing)
            total_minutes_from = landing_hour * 60 + landing_min + 35
            total_minutes_to = landing_hour * 60 + landing_min + 60

            # Handle overnight (e.g., 23:30 landing + 60 min = 00:30 next day)
            pickup_time_from = time(
                (total_minutes_from // 60) % 24,
                total_minutes_from % 60
            )
            pickup_time_to = time(
                (total_minutes_to // 60) % 24,
                total_minutes_to % 60
            )

        # Check if we have existing customer/vehicle from incremental saves
        if request.customer_id and request.vehicle_id:
            # Use existing customer and vehicle - just create the booking
            customer = db_service.get_customer_by_id(db, request.customer_id)
            if not customer:
                raise ValueError("Customer not found")

            # Determine slot type from drop_off_slot ("165" = early, "120" = late)
            slot_type = None
            if request.drop_off_slot:
                slot_type = 'early' if request.drop_off_slot == "165" else 'late'

            # Look up destination name from departure table (more reliable than frontend)
            dropoff_destination = None
            if request.departure_id:
                departure = db.query(FlightDeparture).filter(
                    FlightDeparture.id == request.departure_id
                ).first()
                if departure and departure.destination_name:
                    # Extract city name from "City, CountryCode" format
                    parts = departure.destination_name.split(', ')
                    dropoff_destination = parts[0] if parts else departure.destination_name
                    # Shorten Tenerife-Reinasofia to Tenerife
                    if dropoff_destination == 'Tenerife-Reinasofia':
                        dropoff_destination = 'Tenerife'

            # Look up origin name from arrival table
            pickup_origin = None
            if request.pickup_flight_number and pickup_date:
                arrival = db.query(FlightArrival).filter(
                    FlightArrival.date == pickup_date,
                    FlightArrival.flight_number == request.pickup_flight_number
                ).first()
                if arrival and arrival.origin_name:
                    # Extract city name from "City, CountryCode" format
                    parts = arrival.origin_name.split(', ')
                    pickup_origin = parts[0] if parts else arrival.origin_name
                    # Shorten Tenerife-Reinasofia to Tenerife
                    if pickup_origin == 'Tenerife-Reinasofia':
                        pickup_origin = 'Tenerife'

            # Create booking with existing IDs
            booking = db_service.create_booking(
                db=db,
                customer_id=request.customer_id,
                vehicle_id=request.vehicle_id,
                package=request.package,
                dropoff_date=dropoff_date,
                dropoff_time=dropoff_time,
                pickup_date=pickup_date,
                dropoff_flight_number=request.flight_number,
                dropoff_destination=dropoff_destination,
                pickup_time=pickup_time,
                pickup_time_from=pickup_time_from,
                pickup_time_to=pickup_time_to,
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=pickup_origin,
                departure_id=request.departure_id,
                dropoff_slot=slot_type,
            )
            booking_reference = booking.reference
            booking_id = booking.id
        else:
            # Fallback: Create everything from scratch (backwards compatible)
            # Determine slot type from drop_off_slot ("165" = early, "120" = late)
            slot_type = None
            if request.drop_off_slot:
                slot_type = 'early' if request.drop_off_slot == "165" else 'late'

            # Look up destination name from departure table (more reliable than frontend)
            dropoff_destination = None
            if request.departure_id:
                departure = db.query(FlightDeparture).filter(
                    FlightDeparture.id == request.departure_id
                ).first()
                if departure and departure.destination_name:
                    # Extract city name from "City, CountryCode" format
                    parts = departure.destination_name.split(', ')
                    dropoff_destination = parts[0] if parts else departure.destination_name
                    # Shorten Tenerife-Reinasofia to Tenerife
                    if dropoff_destination == 'Tenerife-Reinasofia':
                        dropoff_destination = 'Tenerife'

            # Look up origin name from arrival table
            pickup_origin = None
            if request.pickup_flight_number and pickup_date:
                arrival = db.query(FlightArrival).filter(
                    FlightArrival.date == pickup_date,
                    FlightArrival.flight_number == request.pickup_flight_number
                ).first()
                if arrival and arrival.origin_name:
                    # Extract city name from "City, CountryCode" format
                    parts = arrival.origin_name.split(', ')
                    pickup_origin = parts[0] if parts else arrival.origin_name
                    # Shorten Tenerife-Reinasofia to Tenerife
                    if pickup_origin == 'Tenerife-Reinasofia':
                        pickup_origin = 'Tenerife'

            booking_data = db_service.create_full_booking(
                db=db,
                # Customer
                first_name=request.first_name,
                last_name=request.last_name,
                email=request.email,
                phone=request.phone or "",
                # Billing
                billing_address1=request.billing_address1 or "",
                billing_address2=request.billing_address2,
                billing_city=request.billing_city or "",
                billing_postcode=request.billing_postcode or "",
                billing_country=request.billing_country or "United Kingdom",
                billing_county=request.billing_county,
                # Vehicle
                registration=request.registration or "TBC",
                make=request.make or "TBC",
                model=request.model or "TBC",
                colour=request.colour or "TBC",
                # Booking
                package=request.package,
                dropoff_date=dropoff_date,
                dropoff_time=dropoff_time,
                pickup_date=pickup_date,
                dropoff_flight_number=request.flight_number,
                dropoff_destination=dropoff_destination,
                pickup_time=pickup_time,
                pickup_time_from=pickup_time_from,
                pickup_time_to=pickup_time_to,
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=pickup_origin,
                # Flight slot
                departure_id=request.departure_id,
                dropoff_slot=slot_type,
            )
            booking_reference = booking_data["booking"].reference
            booking_id = booking_data["booking"].id
            customer = booking_data["customer"]

        # Validate slot availability (but don't book yet - that happens after payment)
        if request.departure_id and request.drop_off_slot:
            departure = db.query(FlightDeparture).filter(
                FlightDeparture.id == request.departure_id
            ).first()
            if departure:
                # Check if this is a "Call Us only" flight (capacity_tier = 0)
                if departure.is_call_us_only:
                    raise HTTPException(
                        status_code=400,
                        detail="This flight requires calling to book. Please contact us directly."
                    )

                # Check if all slots are booked
                if departure.all_slots_booked:
                    raise HTTPException(
                        status_code=400,
                        detail="This flight is fully booked. Please contact us directly to arrange an alternative."
                    )

                # Slot "165" = early (2¾ hours before)
                # Slot "120" = late (2 hours before)
                if request.drop_off_slot == "165" and departure.early_slots_available <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="This slot is fully booked. Please select the other available slot or contact us directly."
                    )
                elif request.drop_off_slot == "120" and departure.late_slots_available <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="This slot is fully booked. Please select the other available slot or contact us directly."
                    )
                # Note: Slot is NOT booked here - it will be booked after payment succeeds via webhook

        settings = get_settings()

        # Handle FREE bookings (100% off promo code) - skip Stripe entirely
        if is_free_booking:
            print(f"[FREE BOOKING] Processing free booking for {booking_reference}")

            # Mark booking as confirmed immediately (no payment needed)
            booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()
            if booking:
                booking.status = BookingStatus.CONFIRMED
                booking.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(booking)

            # Create payment record with £0 amount and mark as SUCCEEDED
            payment = db_service.create_payment(
                db=db,
                booking_id=booking_id,
                stripe_payment_intent_id=f"free_{booking_reference}",  # Pseudo-ID for free bookings
                amount_pence=0,
            )
            # Update payment status to SUCCEEDED (it's created as PENDING by default)
            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = datetime.utcnow()
            db.commit()

            # Mark promo code as used
            if promo_code_applied:
                subscriber = db.query(MarketingSubscriber).filter(
                    MarketingSubscriber.promo_code == promo_code_applied
                ).first()
                if subscriber:
                    subscriber.promo_code_used = True
                    subscriber.promo_code_used_booking_id = booking_id
                    subscriber.promo_code_used_at = datetime.utcnow()
                    db.commit()

            # Book the slot immediately for free bookings
            if request.departure_id and request.drop_off_slot:
                slot_type = 'early' if request.drop_off_slot == "165" else 'late'
                db_service.book_departure_slot(db, request.departure_id, slot_type)

            # Log payment success
            log_audit_event(
                db=db,
                event=AuditLogEvent.PAYMENT_SUCCEEDED,
                request=http_request,
                session_id=request.session_id,
                booking_reference=booking_reference,
                event_data={
                    "payment_intent_id": f"free_{booking_reference}",
                    "amount_pence": 0,
                    "is_free_booking": True,
                    "promo_code": promo_code_applied,
                },
            )

            # Log booking confirmed
            log_audit_event(
                db=db,
                event=AuditLogEvent.BOOKING_CONFIRMED,
                request=http_request,
                session_id=request.session_id,
                booking_reference=booking_reference,
                event_data={
                    "package": request.package,
                    "email": request.email,
                    "flight_number": request.flight_number,
                    "drop_off_date": request.drop_off_date,
                    "pickup_date": request.pickup_date,
                    "departure_id": request.departure_id,
                    "drop_off_slot": request.drop_off_slot,
                },
            )

            # Send confirmation email for free booking
            try:
                # Format dates nicely for email
                dropoff_date_str = dropoff_date.strftime("%A, %d %B %Y")
                pickup_date_str = pickup_date.strftime("%A, %d %B %Y")
                dropoff_time_str = dropoff_time.strftime("%H:%M") if dropoff_time else "TBC"

                # Calculate pickup time (45 mins after scheduled arrival) - format as "From HH:MM onwards"
                pickup_time_str = ""
                if pickup_time:
                    # pickup_time is the landing time, add 45 mins
                    landing_mins = pickup_time.hour * 60 + pickup_time.minute
                    pickup_mins = landing_mins + 45
                    if pickup_mins >= 24 * 60:
                        pickup_mins -= 24 * 60
                    pickup_time_str = f"From {pickup_mins // 60:02d}:{pickup_mins % 60:02d} onwards"

                # Package name
                package_name = "1 Week" if request.package == "quick" else "2 Weeks"

                # Get vehicle info (use request data or booking data)
                vehicle_make = request.make if request.make and request.make != "Other" else (request.customMake if hasattr(request, 'customMake') else "TBC")
                vehicle_model = request.model if request.model and request.model != "Other" else (request.customModel if hasattr(request, 'customModel') else "TBC")
                vehicle_colour = request.colour or "TBC"
                vehicle_registration = request.registration or "TBC"

                # If we have vehicle_id, get from database for accuracy
                if request.vehicle_id:
                    vehicle = db.query(DbVehicle).filter(DbVehicle.id == request.vehicle_id).first()
                    if vehicle:
                        vehicle_make = vehicle.make
                        vehicle_model = vehicle.model
                        vehicle_colour = vehicle.colour
                        vehicle_registration = vehicle.registration

                email_sent = send_booking_confirmation_email(
                    email=request.email,
                    first_name=request.first_name,
                    booking_reference=booking_reference,
                    dropoff_date=dropoff_date_str,
                    dropoff_time=dropoff_time_str,
                    pickup_date=pickup_date_str,
                    pickup_time=pickup_time_str,
                    departure_flight=f"{request.flight_number}",
                    return_flight=f"{request.pickup_flight_number or 'TBC'} from {request.pickup_origin or 'TBC'}",
                    vehicle_make=vehicle_make,
                    vehicle_model=vehicle_model,
                    vehicle_colour=vehicle_colour,
                    vehicle_registration=vehicle_registration,
                    package_name=package_name,
                    amount_paid="£0.00",
                    promo_code=promo_code_applied,
                    discount_amount=f"£{original_amount / 100:.2f}",
                )

                # Update booking with email sent status
                if email_sent and booking:
                    booking.confirmation_email_sent = True
                    booking.confirmation_email_sent_at = datetime.utcnow()
                    db.commit()
                    print(f"[FREE BOOKING] Confirmation email sent to {request.email}")

            except Exception as email_error:
                print(f"[FREE BOOKING] Failed to send confirmation email: {email_error}")
                traceback.print_exc()

            # Return response for free booking
            response = CreatePaymentResponse(
                client_secret=None,  # No Stripe payment needed
                payment_intent_id=f"free_{booking_reference}",
                booking_reference=booking_reference,
                amount=0,
                amount_display="£0.00",
                publishable_key=settings.stripe_publishable_key,
                is_free_booking=True,
                original_amount=original_amount,
                original_amount_display=f"£{original_amount / 100:.2f}",
                discount_amount=discount_amount,
                discount_amount_display=f"£{discount_amount / 100:.2f}",
                promo_code_applied=promo_code_applied,
            )
            return response

        # Regular paid booking - Create Stripe PaymentIntent
        intent_request = PaymentIntentRequest(
            amount=amount,
            currency="gbp",
            customer_email=request.email,
            customer_name=f"{request.first_name} {request.last_name}",
            booking_reference=booking_reference,
            flight_number=request.flight_number,
            flight_date=request.flight_date,
            drop_off_date=request.drop_off_date,
            pickup_date=request.pickup_date,
            departure_id=request.departure_id,
            drop_off_slot=request.drop_off_slot,
            promo_code=promo_code_applied,
        )

        intent = create_payment_intent(intent_request)

        # Create payment record linked to booking
        db_service.create_payment(
            db=db,
            booking_id=booking_id,
            stripe_payment_intent_id=intent.payment_intent_id,
            amount_pence=amount,
        )

        # Log the payment initiation
        log_audit_event(
            db=db,
            event=AuditLogEvent.PAYMENT_INITIATED,
            request=http_request,
            session_id=request.session_id,
            booking_reference=booking_reference,
            event_data={
                "payment_intent_id": intent.payment_intent_id,
                "amount_pence": amount,
                "package": request.package,
                "email": request.email,
                "flight_number": request.flight_number,
                "drop_off_date": request.drop_off_date,
                "pickup_date": request.pickup_date,
            },
        )

        # Build response with discount info if applicable
        response = CreatePaymentResponse(
            client_secret=intent.client_secret,
            payment_intent_id=intent.payment_intent_id,
            booking_reference=booking_reference,
            amount=amount,
            amount_display=f"£{amount / 100:.2f}",
            publishable_key=settings.stripe_publishable_key,
        )

        # Add discount info if promo code was applied
        if promo_code_applied:
            response.original_amount = original_amount
            response.original_amount_display = f"£{original_amount / 100:.2f}"
            response.discount_amount = discount_amount
            response.discount_amount_display = f"£{discount_amount / 100:.2f}"
            response.promo_code_applied = promo_code_applied

        return response

    except Exception as e:
        # Log the error
        log_error(
            db=db,
            error_type="payment_creation",
            message=str(e),
            request=http_request,
            stack_trace=traceback.format_exc(),
            session_id=request.session_id,
            request_data={
                "email": request.email,
                "package": request.package,
                "flight_number": request.flight_number,
            },
        )
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/payments/{payment_intent_id}/status")
async def check_payment_status(payment_intent_id: str):
    """
    Check the status of a payment.

    Useful for the frontend to verify payment succeeded.
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    try:
        status = get_payment_status(payment_intent_id)
        return {
            "payment_intent_id": status.payment_intent_id,
            "status": status.status,
            "amount": status.amount,
            "amount_display": f"£{status.amount / 100:.2f}",
            "paid": status.status == "succeeded",
            "booking_reference": status.booking_reference,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    """
    Handle Stripe webhook events.

    This endpoint receives events from Stripe when:
    - Payment succeeds (payment_intent.succeeded)
    - Payment fails (payment_intent.payment_failed)
    - Refund is processed (charge.refunded)

    The webhook secret verifies the request is from Stripe.
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    # Get the raw body
    payload = await request.body()

    try:
        event = verify_webhook_signature(payload, stripe_signature)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")

    # Handle the event
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "payment_intent.succeeded":
        # Payment was successful - update database
        payment_intent_id = data["id"]
        metadata = data.get("metadata", {})
        booking_reference = metadata.get("booking_reference")
        departure_id = metadata.get("departure_id")
        drop_off_slot = metadata.get("drop_off_slot")
        promo_code = metadata.get("promo_code")

        # Update payment status in database (this also updates booking to CONFIRMED)
        try:
            payment = db_service.update_payment_status(
                db=db,
                stripe_payment_intent_id=payment_intent_id,
                status=PaymentStatus.SUCCEEDED,
                paid_at=datetime.utcnow(),
            )
            if not payment:
                # Payment not found in database - log but continue
                log_error(
                    db=db,
                    error_type="webhook_payment_not_found",
                    message=f"Payment record not found for intent: {payment_intent_id}",
                    request=request,
                    booking_reference=booking_reference,
                )
        except Exception as e:
            log_error(
                db=db,
                error_type="webhook_payment_update",
                message=f"Failed to update payment status: {str(e)}",
                request=request,
                booking_reference=booking_reference,
                stack_trace=traceback.format_exc(),
            )

        # Log payment success
        try:
            log_audit_event(
                db=db,
                event=AuditLogEvent.PAYMENT_SUCCEEDED,
                request=request,
                booking_reference=booking_reference,
                event_data={
                    "payment_intent_id": payment_intent_id,
                    "amount_pence": data.get("amount"),
                },
            )
        except Exception as e:
            print(f"[WEBHOOK] Failed to log audit event PAYMENT_SUCCEEDED: {e}")

        # Log booking confirmed
        try:
            log_audit_event(
                db=db,
                event=AuditLogEvent.BOOKING_CONFIRMED,
                request=request,
                booking_reference=booking_reference,
                event_data={
                    "departure_id": departure_id,
                    "drop_off_slot": drop_off_slot,
                },
            )
        except Exception as e:
            print(f"[WEBHOOK] Failed to log audit event BOOKING_CONFIRMED: {e}")

        # Book the slot on the departure flight (now that payment succeeded)
        if departure_id and drop_off_slot:
            try:
                slot_type = 'early' if drop_off_slot == "165" else 'late'
                db_service.book_departure_slot(db, int(departure_id), slot_type)
            except Exception as e:
                log_error(
                    db=db,
                    error_type="slot_booking",
                    message=f"Failed to book slot after payment: {str(e)}",
                    request=request,
                    booking_reference=booking_reference,
                    stack_trace=traceback.format_exc(),
                )

        # Mark promo code as used (if one was applied)
        if promo_code:
            try:
                # Get booking ID from reference
                booking = db_service.get_booking_by_reference(db, booking_reference)
                subscriber = db.query(MarketingSubscriber).filter(
                    MarketingSubscriber.promo_code == promo_code
                ).first()
                if subscriber:
                    subscriber.promo_code_used = True
                    subscriber.promo_code_used_booking_id = booking.id if booking else None
                    subscriber.promo_code_used_at = datetime.utcnow()
                    db.commit()
            except Exception as e:
                log_error(
                    db=db,
                    error_type="promo_code_marking",
                    message=f"Failed to mark promo code as used: {str(e)}",
                    request=request,
                    booking_reference=booking_reference,
                    stack_trace=traceback.format_exc(),
                )

        # Send booking confirmation email
        print(f"[EMAIL] Starting to send confirmation email for booking: {booking_reference}")
        try:
            booking = db_service.get_booking_by_reference(db, booking_reference)
            print(f"[EMAIL] Booking found: {booking is not None}")
            if booking:
                print(f"[EMAIL] Customer email: {booking.customer.email}, name: {booking.customer.first_name}")
                # Calculate pickup time (45 min after landing) - format as "From HH:MM onwards"
                pickup_time_str = ""
                if booking.pickup_time:
                    landing_minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
                    pickup_mins = landing_minutes + 45
                    # Handle overnight
                    if pickup_mins >= 24 * 60:
                        pickup_mins -= 24 * 60
                    pickup_time_str = f"From {pickup_mins // 60:02d}:{pickup_mins % 60:02d} onwards"

                # Format dates nicely
                dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
                pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
                dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else ""

                # Format flight info
                departure_flight = f"{booking.dropoff_flight_number} to {booking.dropoff_destination or 'destination'}"
                return_flight = f"{booking.pickup_flight_number or 'N/A'} from {booking.pickup_origin or 'origin'}"

                # Package name
                package_name = "1 Week" if booking.package == "quick" else "2 Weeks"

                # Amount paid
                amount_pence = data.get("amount", 0)
                amount_paid = f"£{amount_pence / 100:.2f}"

                # Calculate discount if promo code was used
                discount_amount = None
                if promo_code:
                    # 10% discount
                    original_amount = amount_pence / 0.9  # Work backwards from discounted amount
                    discount_amount = f"£{(original_amount - amount_pence) / 100:.2f}"

                print(f"[EMAIL] Calling send_booking_confirmation_email...")
                email_sent = send_booking_confirmation_email(
                    email=booking.customer.email,
                    first_name=booking.customer.first_name,
                    booking_reference=booking_reference,
                    dropoff_date=dropoff_date_str,
                    dropoff_time=dropoff_time_str,
                    pickup_date=pickup_date_str,
                    pickup_time=pickup_time_str,
                    departure_flight=departure_flight,
                    return_flight=return_flight,
                    vehicle_make=booking.vehicle.make,
                    vehicle_model=booking.vehicle.model,
                    vehicle_colour=booking.vehicle.colour,
                    vehicle_registration=booking.vehicle.registration,
                    package_name=package_name,
                    amount_paid=amount_paid,
                    promo_code=promo_code if promo_code else None,
                    discount_amount=discount_amount,
                )
                print(f"[EMAIL] send_booking_confirmation_email returned: {email_sent}")

                # Update booking with email sent status
                if email_sent:
                    booking.confirmation_email_sent = True
                    booking.confirmation_email_sent_at = datetime.utcnow()
                    db.commit()
        except Exception as e:
            # Log error but don't fail the webhook - payment was successful
            log_error(
                db=db,
                error_type="confirmation_email",
                message=f"Failed to send confirmation email: {str(e)}",
                request=request,
                booking_reference=booking_reference,
                stack_trace=traceback.format_exc(),
            )

        return {"status": "success", "booking_reference": booking_reference}

    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data["id"]
        metadata = data.get("metadata", {})
        booking_reference = metadata.get("booking_reference")
        error_message = data.get("last_payment_error", {}).get("message", "Unknown error")

        # Update payment status to failed
        db_service.update_payment_status(
            db=db,
            stripe_payment_intent_id=payment_intent_id,
            status=PaymentStatus.FAILED,
        )

        # Log payment failure as audit event
        log_audit_event(
            db=db,
            event=AuditLogEvent.PAYMENT_FAILED,
            request=request,
            booking_reference=booking_reference,
            event_data={
                "payment_intent_id": payment_intent_id,
                "error_message": error_message,
            },
        )

        # Also log as error for error tracking
        log_error(
            db=db,
            error_type="stripe_payment",
            message=f"Payment failed: {error_message}",
            request=request,
            severity=ErrorSeverity.WARNING,
            booking_reference=booking_reference,
        )

        return {"status": "failed", "error": error_message}

    elif event_type == "charge.refunded":
        charge_id = data["id"]
        refund_amount = data.get("amount_refunded", 0)
        metadata = data.get("metadata", {})
        booking_reference = metadata.get("booking_reference")

        # Log refund
        log_audit_event(
            db=db,
            event=AuditLogEvent.BOOKING_REFUNDED,
            request=request,
            booking_reference=booking_reference,
            event_data={
                "charge_id": charge_id,
                "refund_amount_pence": refund_amount,
            },
        )

        return {"status": "refunded"}

    # Return success for other event types (we don't need to handle them)
    return {"status": "received", "type": event_type}


@app.post("/api/admin/refund/{payment_intent_id}")
async def admin_refund_payment(
    payment_intent_id: str,
    reason: str = Query("requested_by_customer", description="Refund reason"),
):
    """
    Admin endpoint: Refund a payment.

    Reasons:
    - requested_by_customer: Customer requested cancellation
    - duplicate: Duplicate payment
    - fraudulent: Fraudulent transaction
    """
    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured"
        )

    try:
        result = refund_payment(payment_intent_id, reason)
        return {
            "success": True,
            "refund_id": result["refund_id"],
            "status": result["status"],
            "amount_refunded": f"£{result['amount'] / 100:.2f}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Admin: Seed Flight Data
# =============================================================================

FLIGHT_SCHEDULE_DATA = None  # Will be loaded from JSON

def load_flight_schedule_json():
    """Load flight schedule from embedded JSON or file."""
    global FLIGHT_SCHEDULE_DATA
    if FLIGHT_SCHEDULE_DATA is not None:
        return FLIGHT_SCHEDULE_DATA

    # Try to load from file (for local dev)
    import json
    from pathlib import Path

    possible_paths = [
        Path(__file__).parent.parent / "tag-website" / "src" / "data" / "flightSchedule.json",
        Path(__file__).parent / "flightSchedule.json",
    ]

    for path in possible_paths:
        if path.exists():
            with open(path, "r") as f:
                FLIGHT_SCHEDULE_DATA = json.load(f)
                return FLIGHT_SCHEDULE_DATA

    return None


@app.post("/api/admin/seed-flights")
async def seed_flights(
    secret: str = Query(..., description="Admin secret key"),
    clear_existing: bool = Query(True, description="Clear existing flight data"),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint: Seed the database with flight schedule data.

    Requires ADMIN_SECRET environment variable to be set and passed as query param.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "tag-admin-2024")

    if secret != admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    flights = load_flight_schedule_json()
    if not flights:
        raise HTTPException(status_code=500, detail="Could not load flight schedule JSON")

    try:
        if clear_existing:
            db.query(FlightDeparture).delete()
            db.query(FlightArrival).delete()
            db.commit()

        departures_count = 0
        arrivals_count = 0

        for flight in flights:
            flight_date = datetime.strptime(flight["date"], "%Y-%m-%d").date()

            if flight["type"] == "departure":
                departure = FlightDeparture(
                    date=flight_date,
                    flight_number=flight["flightNumber"],
                    airline_code=flight["airlineCode"],
                    airline_name=flight["airlineName"],
                    departure_time=datetime.strptime(flight["time"], "%H:%M").time(),
                    destination_code=flight["destinationCode"],
                    destination_name=flight.get("destinationName"),
                    capacity_tier=flight.get("capacity_tier", 2),  # Default to 2 slots for legacy data
                    slots_booked_early=0,
                    slots_booked_late=0,
                )
                db.add(departure)
                departures_count += 1

            elif flight["type"] == "arrival":
                departure_time_val = None
                if flight.get("departureTime"):
                    departure_time_val = datetime.strptime(flight["departureTime"], "%H:%M").time()

                arrival = FlightArrival(
                    date=flight_date,
                    flight_number=flight["flightNumber"],
                    airline_code=flight["airlineCode"],
                    airline_name=flight["airlineName"],
                    arrival_time=datetime.strptime(flight["time"], "%H:%M").time(),
                    departure_time=departure_time_val,
                    origin_code=flight["originCode"],
                    origin_name=flight.get("originName"),
                )
                db.add(arrival)
                arrivals_count += 1

        db.commit()

        return {
            "success": True,
            "departures": departures_count,
            "arrivals": arrivals_count,
            "total": departures_count + arrivals_count
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error seeding flights: {str(e)}")


class ImportDeparturesRequest(BaseModel):
    """Request body for importing departures with capacity tiers."""
    tsv_data: str  # Tab-separated data
    clear_existing: bool = True


@app.post("/api/admin/import-departures")
async def import_departures_with_capacity(
    request: ImportDeparturesRequest,
    secret: str = Query(..., description="Admin secret key"),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint: Import departures with capacity tiers from TSV data.

    Expected TSV format (tab-separated):
    Date, Day, Op Al, Dest, Flight, Dep Time, Forming Service Arr Time, 0 Spaces, 2 Spaces, 4 Spaces, 6 Spaces, 8 Spaces

    Each row should have exactly one TRUE in the capacity columns.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "tag-admin-2024")

    if secret != admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    try:
        from import_departures_capacity import import_from_tsv_string
        result = import_from_tsv_string(request.tsv_data, request.clear_existing)

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Import module not found: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing departures: {str(e)}")


# =============================================================================
# Authentication Endpoints (Passwordless)
# =============================================================================

class CreateUserRequest(BaseModel):
    """Request to create a new user."""
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    is_admin: bool = False


@app.post("/api/admin/users")
async def create_user(
    request: CreateUserRequest,
    secret: str = Query(..., description="Admin secret key"),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: Create a new user.
    Requires ADMIN_SECRET query parameter.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "tag-admin-2024")

    if secret != admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    email = request.email.strip().lower()

    # Check if user already exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    # Create user
    user = User(
        email=email,
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        phone=request.phone.strip() if request.phone else None,
        is_admin=request.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user.is_admin,
        }
    }


@app.get("/api/admin/users")
async def list_users(
    secret: str = Query(..., description="Admin secret key"),
    db: Session = Depends(get_db),
):
    """
    Admin endpoint: List all users.
    Requires ADMIN_SECRET query parameter.
    """
    admin_secret = os.getenv("ADMIN_SECRET", "tag-admin-2024")

    if secret != admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    users = db.query(User).all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ]
    }


class AuthRequestCodeRequest(BaseModel):
    """Request to send a login code."""
    email: str


class AuthRequestCodeResponse(BaseModel):
    """Response from request-code endpoint."""
    success: bool
    message: str


class AuthVerifyCodeRequest(BaseModel):
    """Request to verify a login code."""
    email: str
    code: str


class AuthVerifyCodeResponse(BaseModel):
    """Response from verify-code endpoint."""
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[dict] = None


class AuthMeResponse(BaseModel):
    """Response from me endpoint."""
    id: int
    email: str
    first_name: str
    last_name: str
    is_admin: bool


@app.post("/api/auth/request-code", response_model=AuthRequestCodeResponse)
async def auth_request_code(
    request: AuthRequestCodeRequest,
    db: Session = Depends(get_db),
):
    """
    Request a 6-digit login code via email.

    The code expires after 10 minutes.
    Only active users can request codes.
    """
    from datetime import timedelta

    email = request.email.strip().lower()

    # Find the user
    user = db.query(User).filter(
        User.email == email,
        User.is_active == True
    ).first()

    if not user:
        # Don't reveal whether email exists
        return AuthRequestCodeResponse(
            success=True,
            message="If your email is registered, you will receive a login code shortly."
        )

    # Generate cryptographically secure 6-digit code
    code = str(secrets.randbelow(900000) + 100000)

    # Code expires in 10 minutes
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Invalidate any existing unused codes for this user
    db.query(LoginCode).filter(
        LoginCode.user_id == user.id,
        LoginCode.used == False
    ).update({"used": True})

    # Create new login code
    login_code = LoginCode(
        user_id=user.id,
        code=code,
        expires_at=expires_at,
    )
    db.add(login_code)
    db.commit()

    # Send email with code
    email_sent = send_login_code_email(
        email=user.email,
        first_name=user.first_name,
        code=code
    )

    if not email_sent:
        print(f"WARNING: Failed to send login code email to {user.email}")

    return AuthRequestCodeResponse(
        success=True,
        message="If your email is registered, you will receive a login code shortly."
    )


@app.post("/api/auth/verify-code", response_model=AuthVerifyCodeResponse)
async def auth_verify_code(
    request: AuthVerifyCodeRequest,
    db: Session = Depends(get_db),
):
    """
    Verify a 6-digit login code and create a session.

    Sessions expire after 8 hours.
    """
    from datetime import timedelta

    email = request.email.strip().lower()
    code = request.code.strip()

    # Find the user
    user = db.query(User).filter(
        User.email == email,
        User.is_active == True
    ).first()

    if not user:
        return AuthVerifyCodeResponse(
            success=False,
            message="Invalid email or code."
        )

    # Find valid login code
    login_code = db.query(LoginCode).filter(
        LoginCode.user_id == user.id,
        LoginCode.code == code,
        LoginCode.used == False,
        LoginCode.expires_at > datetime.utcnow()
    ).first()

    if not login_code:
        return AuthVerifyCodeResponse(
            success=False,
            message="Invalid or expired code."
        )

    # Mark code as used
    login_code.used = True

    # Generate session token (64-char hex string)
    token = secrets.token_hex(32)

    # Session expires in 8 hours
    expires_at = datetime.utcnow() + timedelta(hours=8)

    # Create session
    session = DbSession(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(session)

    # Update user's last login
    user.last_login = datetime.utcnow()

    db.commit()

    return AuthVerifyCodeResponse(
        success=True,
        message="Login successful.",
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user.is_admin,
        }
    )


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency to get the current authenticated user from session token.

    Expects header: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = parts[1]

    # Find valid session
    session = db.query(DbSession).filter(
        DbSession.token == token,
        DbSession.expires_at > datetime.utcnow()
    ).first()

    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Get user
    user = db.query(User).filter(
        User.id == session.user_id,
        User.is_active == True
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


@app.post("/api/auth/logout")
async def auth_logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Logout the current user by invalidating their session.
    """
    if not authorization:
        return {"success": True, "message": "Logged out"}

    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
        # Delete the session
        db.query(DbSession).filter(DbSession.token == token).delete()
        db.commit()

    return {"success": True, "message": "Logged out"}


@app.get("/api/auth/me", response_model=AuthMeResponse)
async def auth_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get the current authenticated user's information.
    """
    return AuthMeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        is_admin=current_user.is_admin,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
