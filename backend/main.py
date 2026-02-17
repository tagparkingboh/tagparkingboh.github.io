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
from datetime import date, time, datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from models import (
    BookingRequest,
    AdminBookingRequest,
    ManualBookingRequest,
    Booking,
    SlotType,
    AvailableSlotsResponse,
)
from booking_service import get_booking_service, BookingService, get_base_price_for_duration
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
    cancel_payment_intent,
    calculate_price_in_pence,
)

# Database imports
from database import get_db, init_db
from db_models import BookingStatus, PaymentStatus, FlightDeparture, FlightArrival, AuditLog, AuditLogEvent, ErrorLog, ErrorSeverity, MarketingSubscriber, Booking as DbBooking, Vehicle as DbVehicle, User, LoginCode, Session as DbSession, VehicleInspection, InspectionType
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
        "https://tagparking.co.uk",  # Production domain (root)
        "https://www.tagparking.co.uk",  # Production domain (www)
        "https://staging.tagparking.co.uk",  # Staging environment
        "https://tagparkingbohgithubio-staging.up.railway.app",  # Railway staging
        "https://staging-tagparking.netlify.app",  # Netlify staging frontend
        "https://prod-frontend-production.up.railway.app",  # Railway production frontend
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

        # Migration 2: Make inspector_id nullable on vehicle_inspections (allow user deletion)
        try:
            db.execute(text("""
                ALTER TABLE vehicle_inspections ALTER COLUMN inspector_id DROP NOT NULL
            """))
            db.commit()
            print("Migration completed: inspector_id is now nullable")
        except Exception:
            db.rollback()  # Already nullable or table doesn't exist

        # Migration 3: Add discount_percent column to marketing_subscribers
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
            event=event.value,
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
            severity=severity.value,
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


class UpdateBookingRequest(BaseModel):
    """Request to update booking details (admin only)."""
    # Pickup/collection details - for fixing overnight arrival issues
    pickup_date: Optional[date] = None
    pickup_time: Optional[str] = None  # HH:MM format (arrival/landing time)
    pickup_flight_number: Optional[str] = None
    pickup_origin: Optional[str] = None
    arrival_id: Optional[int] = None

    # Dropoff details
    dropoff_date: Optional[date] = None
    dropoff_time: Optional[str] = None  # HH:MM format
    dropoff_flight_number: Optional[str] = None
    dropoff_destination: Optional[str] = None


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
    week1_price: float  # 1-week base rate price (early tier, used for free parking promo)
    all_prices: dict  # Show all tier prices for reference


@app.post("/api/pricing/calculate", response_model=PriceCalculationResponse)
async def calculate_price(request: PriceCalculationRequest):
    """
    Calculate booking price based on dates.

    Supports flexible durations from 1-14 days with tiered pricing:
    - 1-4 days, 5-6 days, 7 days, 8-9 days, 10-11 days, 12-13 days, 14 days

    Advance booking tiers:
    - Early (>=14 days in advance): base price
    - Standard (7-13 days in advance): base + increment
    - Late (<7 days in advance): base + 2x increment
    """
    from booking_service import BookingService, get_duration_tier

    duration = (request.pickup_date - request.drop_off_date).days

    # Validate duration (1-14 days supported)
    if duration < 1 or duration > 14:
        raise HTTPException(
            status_code=400,
            detail=f"Duration must be between 1 and 14 days. Got {duration} days."
        )

    # Determine package (for legacy compatibility)
    package = BookingService.get_package_for_duration(request.drop_off_date, request.pickup_date)

    # Get duration tier name for display
    duration_tier = get_duration_tier(duration)
    duration_labels = {
        "1_4": "1-4 Days",
        "5_6": "5-6 Days",
        "7": "1 Week Trip",
        "8_9": "8-9 Days",
        "10_11": "10-11 Days",
        "12_13": "12-13 Days",
        "14": "2 Week Trip",
    }
    package_name = duration_labels.get(duration_tier, f"{duration} Days")

    # Calculate advance booking tier
    today = date.today()
    days_in_advance = (request.drop_off_date - today).days
    advance_tier = BookingService.get_advance_tier(request.drop_off_date)

    # Calculate price using flexible duration pricing
    price = BookingService.calculate_price_for_duration(duration, request.drop_off_date)

    # Get all prices for this duration tier
    all_duration_prices = BookingService.get_all_duration_prices()
    tier_prices = all_duration_prices.get(duration_tier, {})

    # 1-week base rate price (early tier) used for free parking promo discount
    week1_price = all_duration_prices.get("7", {}).get("early", 79.0)

    return PriceCalculationResponse(
        package=package,
        package_name=package_name,
        duration_days=duration,
        advance_tier=advance_tier,
        days_in_advance=days_in_advance,
        price=price,
        price_pence=int(price * 100),
        week1_price=week1_price,
        all_prices={
            "early": tier_prices.get("early", price),
            "standard": tier_prices.get("standard", price),
            "late": tier_prices.get("late", price),
        }
    )


@app.get("/api/pricing/tiers")
async def get_pricing_tiers():
    """
    Get all pricing tiers for display on the frontend.
    """
    from booking_service import BookingService

    prices = BookingService.get_package_prices()
    return {
        "packages": {
            "quick": {
                "name": "1 Week",
                "duration_days": 7,
                "prices": prices["quick"],
            },
            "longer": {
                "name": "2 Weeks",
                "duration_days": 14,
                "prices": prices["longer"],
            },
        },
        "tiers": {
            "early": {"label": "14+ days in advance", "min_days": 14},
            "standard": {"label": "7-13 days in advance", "min_days": 7, "max_days": 13},
            "late": {"label": "Less than 7 days", "max_days": 6},
        }
    }


@app.get("/api/prices/durations")
async def get_duration_prices():
    """
    Get all flexible duration prices for display on frontend.

    Returns pricing for all duration tiers (1-4, 5-6, 7, 8-9, 10-11, 12-13, 14 days)
    combined with all advance booking tiers (early, standard, late).
    """
    from booking_service import BookingService

    prices = BookingService.get_all_duration_prices()
    return prices


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

    # Look up the promo code across all code fields (legacy, 10%, and free)
    subscriber = db.query(MarketingSubscriber).filter(
        (MarketingSubscriber.promo_code == code) |
        (MarketingSubscriber.promo_10_code == code) |
        (MarketingSubscriber.promo_free_code == code)
    ).first()

    if not subscriber:
        return PromoCodeValidateResponse(
            valid=False,
            message="Invalid promo code",
        )

    # Determine which promo type this code belongs to and check if used
    if subscriber.promo_10_code and subscriber.promo_10_code == code:
        if subscriber.promo_10_used:
            return PromoCodeValidateResponse(
                valid=False,
                message="This promo code has already been used",
            )
        discount = 10
    elif subscriber.promo_free_code and subscriber.promo_free_code == code:
        if subscriber.promo_free_used:
            return PromoCodeValidateResponse(
                valid=False,
                message="This promo code has already been used",
            )
        discount = 100
    elif subscriber.promo_code and subscriber.promo_code == code:
        # Legacy field
        if subscriber.promo_code_used:
            return PromoCodeValidateResponse(
                valid=False,
                message="This promo code has already been used",
            )
        discount = subscriber.discount_percent if subscriber.discount_percent is not None else PROMO_DISCOUNT_PERCENT
    else:
        return PromoCodeValidateResponse(
            valid=False,
            message="Invalid promo code",
        )

    if discount == 100:
        message = "Promo code applied! 1 week free parking!"
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


# =============================================================================
# Admin Authentication Dependencies
# =============================================================================

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


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require admin privileges.

    Use this for admin-only endpoints like:
    - Managing bookings
    - Viewing customer data
    - Sending promo codes
    - Refunds and payments
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return current_user


# =============================================================================
# Admin Endpoints
# =============================================================================

@app.get("/api/admin/bookings")
async def get_all_bookings(
    date_filter: Optional[date] = Query(None, description="Filter by parking date"),
    include_cancelled: bool = Query(True, description="Include cancelled bookings"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
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
            "booking_source": b.booking_source,
            "package": b.package if b.package else (
                f"{(b.pickup_date - b.dropoff_date).days} Day{'s' if (b.pickup_date - b.dropoff_date).days != 1 else ''}"
                if b.dropoff_date and b.pickup_date else None
            ),
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
                # Use snapshot name if available, fall back to current customer name
                "first_name": b.customer_first_name or b.customer.first_name,
                "last_name": b.customer_last_name or b.customer.last_name,
                "email": b.customer.email,
                "phone": b.customer.phone,
                # Billing address
                "billing_address1": b.customer.billing_address1,
                "billing_address2": b.customer.billing_address2,
                "billing_city": b.customer.billing_city,
                "billing_county": b.customer.billing_county,
                "billing_postcode": b.customer.billing_postcode,
                "billing_country": b.customer.billing_country,
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
async def get_daily_occupancy(
    target_date: date,
    current_user: User = Depends(require_admin),
):
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
async def create_admin_booking(
    request: AdminBookingRequest,
    current_user: User = Depends(require_admin),
):
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


@app.post("/api/admin/manual-booking")
async def create_manual_booking(
    request: ManualBookingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Create a manual booking and send payment link email.

    This creates a pending booking record and sends an email to the customer
    with the booking summary and Stripe payment link. The booking is NOT
    confirmed until the customer pays via the link.

    Use this for phone/email enquiries where you create a Stripe payment link
    in the Stripe dashboard and send it to the customer.
    """
    from email_service import send_manual_booking_payment_email
    from db_models import Customer, Vehicle, Booking, BookingStatus, Payment, PaymentStatus
    from datetime import datetime

    # Validate: stripe_payment_link is required for paid bookings
    is_free = request.is_free_booking and request.amount_pence == 0
    if not is_free and not request.stripe_payment_link:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "stripe_payment_link"], "msg": "Field required for paid bookings", "type": "value_error.missing"}]
        )

    try:
        # Create or find customer
        customer = db.query(Customer).filter(Customer.email == request.email).first()
        if not customer:
            customer = Customer(
                first_name=request.first_name,
                last_name=request.last_name,
                email=request.email,
                phone=request.phone or "",  # Phone is required in DB
                billing_address1=request.billing_address1,
                billing_address2=request.billing_address2,
                billing_city=request.billing_city,
                billing_county=request.billing_county,
                billing_postcode=request.billing_postcode,
                billing_country=request.billing_country,
            )
            db.add(customer)
            db.flush()
        else:
            # Update customer details
            customer.first_name = request.first_name
            customer.last_name = request.last_name
            customer.phone = request.phone or customer.phone
            customer.billing_address1 = request.billing_address1
            customer.billing_address2 = request.billing_address2
            customer.billing_city = request.billing_city
            customer.billing_county = request.billing_county
            customer.billing_postcode = request.billing_postcode
            customer.billing_country = request.billing_country

        # Create or find vehicle
        vehicle = db.query(Vehicle).filter(
            Vehicle.registration == request.registration.upper()
        ).first()
        if not vehicle:
            vehicle = Vehicle(
                customer_id=customer.id,
                registration=request.registration.upper(),
                make=request.make,
                model=request.model,
                colour=request.colour,
            )
            db.add(vehicle)
            db.flush()

        # If departure_id and dropoff_slot provided, validate slot availability
        from db_models import FlightDeparture
        departure_flight = None
        if request.departure_id and request.dropoff_slot:
            departure_flight = db.query(FlightDeparture).filter(
                FlightDeparture.id == request.departure_id
            ).first()
            if not departure_flight:
                raise HTTPException(status_code=400, detail="Invalid departure flight")

            # Check if this is a "Call Us only" flight (capacity_tier = 0)
            if departure_flight.capacity_tier == 0:
                raise HTTPException(status_code=400, detail="This flight requires calling to book")

            # Check slot availability using same formula as online booking system
            # max_slots_per_time = capacity_tier // 2 (e.g., capacity_tier=4 means 2 early + 2 late)
            max_per_slot = departure_flight.capacity_tier // 2

            if request.dropoff_slot in ("165", "early"):  # Early slot
                if departure_flight.slots_booked_early >= max_per_slot:
                    raise HTTPException(status_code=400, detail="Early slot is fully booked")
            elif request.dropoff_slot in ("120", "late"):  # Late slot
                if departure_flight.slots_booked_late >= max_per_slot:
                    raise HTTPException(status_code=400, detail="Late slot is fully booked")

        # Generate booking reference
        import random
        import string
        reference = "TAG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        # Look up destination name from departure flight
        dropoff_destination = None
        if departure_flight and departure_flight.destination_name:
            # Extract city name from "City, CountryCode" format
            parts = departure_flight.destination_name.split(', ')
            dropoff_destination = parts[0] if parts else departure_flight.destination_name
            # Shorten Tenerife-Reinasofia to Tenerife
            if dropoff_destination == 'Tenerife-Reinasofia':
                dropoff_destination = 'Tenerife'

        # Look up origin name and arrival_id from arrival flight
        from db_models import FlightArrival
        pickup_origin = None
        arrival_id = None
        if request.return_flight_number and request.pickup_date:
            arrival = db.query(FlightArrival).filter(
                FlightArrival.flight_number == request.return_flight_number,
                FlightArrival.date == request.pickup_date
            ).first()
            if arrival:
                arrival_id = arrival.id
                if arrival.origin_name:
                    # Extract city name from "City, CountryCode" format
                    parts = arrival.origin_name.split(', ')
                    pickup_origin = parts[0] if parts else arrival.origin_name
                    # Shorten Tenerife-Reinasofia to Tenerife
                    if pickup_origin == 'Tenerife-Reinasofia':
                        pickup_origin = 'Tenerife'

        # Determine booking status based on whether it's a free booking
        booking_status = BookingStatus.CONFIRMED if is_free else BookingStatus.PENDING

        # Create booking
        booking = Booking(
            reference=reference,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            customer_first_name=request.first_name,
            customer_last_name=request.last_name,
            dropoff_date=request.dropoff_date,
            dropoff_time=datetime.strptime(request.dropoff_time, "%H:%M").time(),
            pickup_date=request.pickup_date,
            pickup_time=datetime.strptime(request.pickup_time, "%H:%M").time(),
            status=booking_status,
            booking_source="manual",
            admin_notes=request.notes,
            # Flight integration fields
            departure_id=request.departure_id,
            dropoff_slot=request.dropoff_slot,
            dropoff_flight_number=request.departure_flight_number,
            dropoff_destination=dropoff_destination,
            pickup_flight_number=request.return_flight_number,
            pickup_origin=pickup_origin,
            arrival_id=arrival_id,
        )
        db.add(booking)
        db.flush()

        # Create payment record
        payment = Payment(
            booking_id=booking.id,
            amount_pence=request.amount_pence,
            currency="gbp",
            status=PaymentStatus.SUCCEEDED if is_free else PaymentStatus.PENDING,
            stripe_payment_link=request.stripe_payment_link or "",
        )
        db.add(payment)

        # For free bookings with promo code, mark promo as used
        if is_free and request.promo_code:
            promo_code = request.promo_code.strip().upper()
            subscriber = db.query(MarketingSubscriber).filter(
                (MarketingSubscriber.promo_free_code == promo_code)
            ).first()
            if subscriber and not subscriber.promo_free_used:
                subscriber.promo_free_used = True
                subscriber.promo_free_used_at = datetime.utcnow()
                subscriber.promo_free_used_booking_id = booking.id

        # For free bookings with flight selection, increment slot counts
        if is_free and request.departure_id and request.dropoff_slot:
            departure = db.query(FlightDeparture).filter(FlightDeparture.id == request.departure_id).first()
            if departure:
                if request.dropoff_slot == "165":
                    departure.slots_booked_early = (departure.slots_booked_early or 0) + 1
                elif request.dropoff_slot == "120":
                    departure.slots_booked_late = (departure.slots_booked_late or 0) + 1

        # Format dates for email
        dropoff_date_formatted = request.dropoff_date.strftime("%A, %d %B %Y")
        pickup_date_formatted = request.pickup_date.strftime("%A, %d %B %Y")
        amount_formatted = f"£{request.amount_pence / 100:.2f}"

        if is_free:
            # Build flight info for email
            departure_flight_str = request.departure_flight_number or "N/A"
            if departure_flight and departure_flight.destination_name:
                departure_flight_str = f"{departure_flight.flight_number} to {dropoff_destination or departure_flight.destination_name}"

            return_flight_str = request.return_flight_number or "N/A"
            if pickup_origin:
                return_flight_str = f"{request.return_flight_number} from {pickup_origin}"

            # Calculate duration for package name
            duration_days = (request.pickup_date - request.dropoff_date).days
            package_name = f"{duration_days} day{'s' if duration_days != 1 else ''}"

            # Send confirmation email for free booking BEFORE commit
            # If email fails, the transaction will be rolled back
            email_sent = send_booking_confirmation_email(
                email=request.email,
                first_name=request.first_name,
                booking_reference=reference,
                dropoff_date=dropoff_date_formatted,
                dropoff_time=request.dropoff_time,
                pickup_date=pickup_date_formatted,
                pickup_time=request.pickup_time,
                departure_flight=departure_flight_str,
                return_flight=return_flight_str,
                vehicle_registration=request.registration.upper(),
                vehicle_make=request.make,
                vehicle_model=request.model,
                vehicle_colour=request.colour,
                package_name=package_name,
                amount_paid="£0.00 (FREE with promo code)",
            )

            # Commit only after email succeeds
            db.commit()

            return {
                "success": True,
                "message": "Free booking confirmed and confirmation email sent" if email_sent else "Free booking confirmed but email failed to send",
                "booking_reference": reference,
                "email_sent": email_sent,
                "is_free_booking": True,
            }
        else:
            # Send payment link email for paid booking BEFORE commit
            # If email fails, the transaction will be rolled back
            email_sent = send_manual_booking_payment_email(
                email=request.email,
                first_name=request.first_name,
                dropoff_date=dropoff_date_formatted,
                dropoff_time=request.dropoff_time,
                pickup_date=pickup_date_formatted,
                pickup_time=request.pickup_time,
                vehicle_make=request.make,
                vehicle_model=request.model,
                vehicle_colour=request.colour,
                vehicle_registration=request.registration.upper(),
                amount=amount_formatted,
                payment_link=request.stripe_payment_link,
            )

            # Commit only after email succeeds
            db.commit()

            return {
                "success": True,
                "message": "Manual booking created and payment link email sent" if email_sent else "Manual booking created but email failed to send",
                "booking_reference": reference,
                "email_sent": email_sent,
                "is_free_booking": False,
            }

    except HTTPException:
        # Re-raise HTTPExceptions as-is (e.g., slot validation errors)
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/bookings/{booking_id}/mark-paid")
async def mark_booking_paid(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Mark a manual booking as paid (confirmed).

    Updates booking status to CONFIRMED and payment status to PAID.
    Sends booking confirmation email to customer.
    Use this after verifying payment was received via Stripe Payment Link.
    """
    from db_models import Booking, Payment, BookingStatus, PaymentStatus, FlightDeparture
    from email_service import send_booking_confirmation_email

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status == BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Booking is already confirmed")

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Cannot confirm a cancelled booking")

    if booking.status == BookingStatus.REFUNDED:
        raise HTTPException(status_code=400, detail="Cannot confirm a refunded booking")

    # If booking has departure_id and dropoff_slot, increment the slot count
    if booking.departure_id and booking.dropoff_slot:
        departure_flight = db.query(FlightDeparture).filter(
            FlightDeparture.id == booking.departure_id
        ).first()
        if departure_flight:
            # Use same formula as online booking system: max_per_slot = capacity_tier // 2
            max_per_slot = departure_flight.capacity_tier // 2

            # Check slot availability before booking
            if booking.dropoff_slot in ("165", "early"):  # Early slot
                if departure_flight.slots_booked_early >= max_per_slot:
                    raise HTTPException(status_code=400, detail="Early slot is now fully booked")
                departure_flight.slots_booked_early += 1
            elif booking.dropoff_slot in ("120", "late"):  # Late slot
                if departure_flight.slots_booked_late >= max_per_slot:
                    raise HTTPException(status_code=400, detail="Late slot is now fully booked")
                departure_flight.slots_booked_late += 1

    # Update booking status
    booking.status = BookingStatus.CONFIRMED

    # Update payment status if exists
    payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if payment:
        payment.status = PaymentStatus.SUCCEEDED

    db.commit()

    # Send confirmation email
    email_sent = False
    try:
        # Format dates
        dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
        dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else "TBC"
        pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
        pickup_time_str = booking.pickup_time.strftime("%H:%M") if booking.pickup_time else "TBC"

        # Package name based on duration
        if booking.package == "daily":
            package_name = "Short Stay"
        elif booking.package == "quick":
            package_name = "1 Week"
        else:
            package_name = "2 Weeks"

        # Amount paid
        payment_pence = payment.amount_pence if payment else 0
        amount_paid = f"£{payment_pence / 100:.2f}" if payment else "N/A"

        # Use flight numbers if available, otherwise show as not applicable
        departure_flight = booking.dropoff_flight_number or "-"
        return_flight = booking.pickup_flight_number or "-"

        # Look up promo code used for this booking
        promo_code_display = None
        discount_display = None
        original_display = None
        subscriber = db.query(MarketingSubscriber).filter(
            (MarketingSubscriber.promo_10_used_booking_id == booking_id) |
            (MarketingSubscriber.promo_free_used_booking_id == booking_id) |
            (MarketingSubscriber.promo_code_used_booking_id == booking_id)
        ).first()
        if subscriber:
            if subscriber.promo_10_used_booking_id == booking_id:
                promo_code_display = subscriber.promo_10_code
            elif subscriber.promo_free_used_booking_id == booking_id:
                promo_code_display = subscriber.promo_free_code
            elif subscriber.promo_code_used_booking_id == booking_id:
                promo_code_display = subscriber.promo_code

            if promo_code_display:
                orig_pence = calculate_price_in_pence(booking.package, drop_off_date=booking.dropoff_date)
                disc_pence = orig_pence - payment_pence
                if disc_pence > 0:
                    original_display = f"£{orig_pence / 100:.2f}"
                    discount_display = f"£{disc_pence / 100:.2f}"

        email_sent = send_booking_confirmation_email(
            email=booking.customer.email,
            first_name=booking.customer_first_name or booking.customer.first_name,
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
            promo_code=promo_code_display,
            discount_amount=discount_display,
            original_amount=original_display,
        )

        if email_sent:
            booking.confirmation_email_sent = True
            booking.confirmation_email_sent_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        print(f"Error sending confirmation email: {e}")

    return {
        "success": True,
        "message": "Booking confirmed and confirmation email sent" if email_sent else "Booking confirmed but email failed to send",
        "reference": booking.reference,
        "email_sent": email_sent,
    }


@app.post("/api/admin/bookings/{booking_id}/cancel")
async def cancel_booking_admin(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Cancel a booking.

    Sets the booking status to CANCELLED and releases the flight slot
    so it becomes available for other bookings.
    Note: This does NOT automatically refund the payment -
    use the Stripe dashboard for refunds.
    """
    from db_models import Booking, BookingStatus, Payment

    booking = db.query(Booking).options(joinedload(Booking.payment)).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    if booking.status == BookingStatus.REFUNDED:
        raise HTTPException(status_code=400, detail="Cannot cancel a refunded booking")

    # Release the flight slot using stored departure_id and dropoff_slot
    slot_released = False
    if booking.departure_id and booking.dropoff_slot:
        # Normalize dropoff_slot to "early"/"late" (handle both old "165"/"120" and new "early"/"late" formats)
        slot_type = "early" if booking.dropoff_slot in ("165", "early") else "late"
        result = db_service.release_departure_slot(db, booking.departure_id, slot_type)
        slot_released = result.get("success", False)

    # Cancel the Stripe PaymentIntent if payment exists and is not completed
    stripe_cancelled = False
    if booking.payment and booking.payment.stripe_payment_intent_id:
        # Only cancel if payment is not already succeeded
        if booking.payment.status != PaymentStatus.SUCCEEDED:
            cancel_result = cancel_payment_intent(booking.payment.stripe_payment_intent_id)
            stripe_cancelled = cancel_result.get("success", False)

    # Update booking status
    booking.status = BookingStatus.CANCELLED
    db.commit()

    message = f"Booking {booking.reference} has been cancelled"
    if slot_released:
        message += " and the flight slot has been released"
    if stripe_cancelled:
        message += " and the Stripe payment has been cancelled"

    return {
        "success": True,
        "message": message,
        "reference": booking.reference,
        "slot_released": slot_released,
        "stripe_cancelled": stripe_cancelled,
    }


@app.delete("/api/admin/bookings/{booking_id}")
async def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Permanently delete a pending or cancelled booking.

    This completely removes the booking from the database.
    Only works for bookings with PENDING or CANCELLED status.
    Releases the flight slot if one was reserved.
    """
    from db_models import Booking, BookingStatus, Payment

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status not in (BookingStatus.PENDING, BookingStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Can only delete pending or cancelled bookings. This booking has status: {booking.status.value}"
        )

    reference = booking.reference

    # Release the flight slot if one was reserved
    slot_released = False
    if booking.departure_id and booking.dropoff_slot:
        slot_type = "early" if booking.dropoff_slot in ("165", "early") else "late"
        result = db_service.release_departure_slot(db, booking.departure_id, slot_type)
        slot_released = result.get("success", False)

    # Delete associated payment record if exists (Payment references booking via booking_id)
    payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if payment:
        db.delete(payment)

    # Clear any promo code references to this booking
    from db_models import MarketingSubscriber
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_code_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_code_used_booking_id: None}, synchronize_session=False)
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_10_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_10_used_booking_id: None}, synchronize_session=False)
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_free_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_free_used_booking_id: None}, synchronize_session=False)

    # Delete the booking
    db.delete(booking)
    db.commit()

    message = f"Booking {reference} has been permanently deleted"
    if slot_released:
        message += " and the flight slot has been released"

    return {
        "success": True,
        "message": message,
        "reference": reference,
        "slot_released": slot_released,
    }


@app.put("/api/admin/bookings/{booking_id}")
async def update_booking(
    booking_id: int,
    request: UpdateBookingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Update booking details.

    Use this to fix booking information such as:
    - Pickup date/time (e.g., for overnight arrival corrections)
    - Dropoff date/time
    - Flight numbers and destinations/origins

    The pickup_time_from and pickup_time_to fields are automatically
    recalculated when pickup_time is updated (35 and 60 min buffers).
    """
    from db_models import Booking as DbBookingModel
    from datetime import time as dt_time, timedelta

    booking = db.query(DbBookingModel).filter(DbBookingModel.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    updates_made = []

    # Update pickup details
    if request.pickup_date is not None:
        booking.pickup_date = request.pickup_date
        updates_made.append("pickup_date")

    if request.pickup_time is not None:
        # Parse time string HH:MM
        parts = request.pickup_time.split(':')
        new_pickup_time = dt_time(int(parts[0]), int(parts[1]))
        booking.pickup_time = new_pickup_time

        # Recalculate pickup_time_from (35 min after landing) and pickup_time_to (60 min after landing)
        arrival_datetime = datetime.combine(datetime.today(), new_pickup_time)
        booking.pickup_time_from = (arrival_datetime + timedelta(minutes=35)).time()
        booking.pickup_time_to = (arrival_datetime + timedelta(minutes=60)).time()
        updates_made.append("pickup_time")

    if request.pickup_flight_number is not None:
        booking.pickup_flight_number = request.pickup_flight_number
        updates_made.append("pickup_flight_number")

    if request.pickup_origin is not None:
        booking.pickup_origin = request.pickup_origin
        updates_made.append("pickup_origin")

    if request.arrival_id is not None:
        booking.arrival_id = request.arrival_id
        updates_made.append("arrival_id")

    # Update dropoff details
    if request.dropoff_date is not None:
        booking.dropoff_date = request.dropoff_date
        updates_made.append("dropoff_date")

    if request.dropoff_time is not None:
        parts = request.dropoff_time.split(':')
        booking.dropoff_time = dt_time(int(parts[0]), int(parts[1]))
        updates_made.append("dropoff_time")

    if request.dropoff_flight_number is not None:
        booking.dropoff_flight_number = request.dropoff_flight_number
        updates_made.append("dropoff_flight_number")

    if request.dropoff_destination is not None:
        booking.dropoff_destination = request.dropoff_destination
        updates_made.append("dropoff_destination")

    if not updates_made:
        raise HTTPException(status_code=400, detail="No fields to update")

    db.commit()
    db.refresh(booking)

    return {
        "success": True,
        "message": f"Booking {booking.reference} updated successfully",
        "fields_updated": updates_made,
        "booking": {
            "id": booking.id,
            "reference": booking.reference,
            "pickup_date": booking.pickup_date.isoformat() if booking.pickup_date else None,
            "pickup_time": booking.pickup_time.strftime("%H:%M") if booking.pickup_time else None,
            "pickup_time_from": booking.pickup_time_from.strftime("%H:%M") if booking.pickup_time_from else None,
            "pickup_time_to": booking.pickup_time_to.strftime("%H:%M") if booking.pickup_time_to else None,
            "pickup_flight_number": booking.pickup_flight_number,
            "pickup_origin": booking.pickup_origin,
            "dropoff_date": booking.dropoff_date.isoformat() if booking.dropoff_date else None,
            "dropoff_time": booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else None,
            "dropoff_flight_number": booking.dropoff_flight_number,
            "dropoff_destination": booking.dropoff_destination,
        }
    }


@app.post("/api/admin/fix-overnight-arrivals")
async def fix_overnight_arrivals_endpoint(
    dry_run: bool = Query(True, description="If true, only report issues without fixing"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Fix bookings with incorrect overnight arrival dates.

    For flights that depart late evening and arrive after midnight,
    the pickup_date should be the arrival date (next day), not departure date.

    Use dry_run=true (default) to see what would be fixed.
    Use dry_run=false to actually apply the fixes.
    """
    from db_models import Booking as DbBookingModel, FlightArrival
    from datetime import timedelta

    def is_overnight(dep_time, arr_time):
        if not dep_time or not arr_time:
            return False
        return arr_time.hour < 6 and dep_time.hour >= 18

    results = {
        "dry_run": dry_run,
        "bookings_checked": 0,
        "overnight_found": 0,
        "bookings_fixed": 0,
        "details": []
    }

    # Get all bookings with linked arrival flights
    bookings = db.query(DbBookingModel).filter(
        DbBookingModel.arrival_id.isnot(None)
    ).all()

    results["bookings_checked"] = len(bookings)

    for booking in bookings:
        arrival = db.query(FlightArrival).filter(
            FlightArrival.id == booking.arrival_id
        ).first()

        if not arrival:
            continue

        if is_overnight(arrival.departure_time, arrival.arrival_time):
            results["overnight_found"] += 1

            # For overnight flights, pickup should be arrival date
            # Check if the arrival date in DB is correct (should already be next day after import fix)
            # But booking's pickup_date might still be wrong

            # Calculate what the correct pickup date should be
            # If arrival time is after midnight, pickup_date should match arrival.date
            correct_pickup_date = arrival.date

            if booking.pickup_date != correct_pickup_date:
                detail = {
                    "booking_id": booking.id,
                    "reference": booking.reference,
                    "flight_number": booking.pickup_flight_number,
                    "arrival_time": arrival.arrival_time.strftime("%H:%M") if arrival.arrival_time else None,
                    "current_pickup_date": booking.pickup_date.isoformat(),
                    "correct_pickup_date": correct_pickup_date.isoformat(),
                }
                results["details"].append(detail)

                if not dry_run:
                    booking.pickup_date = correct_pickup_date
                    results["bookings_fixed"] += 1

    if not dry_run and results["bookings_fixed"] > 0:
        db.commit()

    return results


@app.post("/api/admin/bookings/{booking_id}/resend-email")
async def resend_booking_confirmation_email(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
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
    payment_pence = 0
    if booking.payment and booking.payment.amount_pence:
        payment_pence = booking.payment.amount_pence
        amount_paid = f"£{payment_pence / 100:.2f}"

    # Look up promo code used for this booking
    promo_code_display = None
    discount_display = None
    original_display = None
    subscriber = db.query(MarketingSubscriber).filter(
        (MarketingSubscriber.promo_10_used_booking_id == booking_id) |
        (MarketingSubscriber.promo_free_used_booking_id == booking_id) |
        (MarketingSubscriber.promo_code_used_booking_id == booking_id)
    ).first()
    if subscriber:
        # Determine which promo code was used
        if subscriber.promo_10_used_booking_id == booking_id:
            promo_code_display = subscriber.promo_10_code
        elif subscriber.promo_free_used_booking_id == booking_id:
            promo_code_display = subscriber.promo_free_code
        elif subscriber.promo_code_used_booking_id == booking_id:
            promo_code_display = subscriber.promo_code

        if promo_code_display:
            # Calculate original price from booking date and package
            orig_pence = calculate_price_in_pence(booking.package, drop_off_date=booking.dropoff_date)
            disc_pence = orig_pence - payment_pence
            if disc_pence > 0:
                original_display = f"£{orig_pence / 100:.2f}"
                discount_display = f"£{disc_pence / 100:.2f}"

    # Send the email
    email_sent = send_booking_confirmation_email(
        email=booking.customer.email,
        first_name=booking.customer_first_name or booking.customer.first_name,
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
        promo_code=promo_code_display,
        discount_amount=discount_display,
        original_amount=original_display,
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
    current_user: User = Depends(require_admin),
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
        first_name=booking.customer_first_name or booking.customer.first_name,
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
    current_user: User = Depends(require_admin),
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
        first_name=booking.customer_first_name or booking.customer.first_name,
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
# Marketing Subscribers Admin Endpoints
# =============================================================================

@app.get("/api/admin/marketing-subscribers")
async def get_marketing_subscribers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all marketing subscribers for admin management.
    """
    subscribers = db.query(MarketingSubscriber).order_by(
        MarketingSubscriber.subscribed_at.desc()
    ).all()

    return {
        "count": len(subscribers),
        "subscribers": [
            {
                "id": s.id,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "email": s.email,
                "subscribed_at": s.subscribed_at.isoformat() if s.subscribed_at else None,
                "welcome_email_sent": s.welcome_email_sent,
                "welcome_email_sent_at": s.welcome_email_sent_at.isoformat() if s.welcome_email_sent_at else None,
                # Legacy promo fields (kept for backwards compatibility)
                "promo_code": s.promo_code,
                "promo_code_sent": s.promo_code_sent,
                "promo_code_sent_at": s.promo_code_sent_at.isoformat() if s.promo_code_sent_at else None,
                "discount_percent": s.discount_percent,
                "promo_code_used": s.promo_code_used,
                "promo_code_used_at": s.promo_code_used_at.isoformat() if s.promo_code_used_at else None,
                "promo_code_used_booking_id": s.promo_code_used_booking_id,
                # 10% OFF promo (separate)
                "promo_10_code": s.promo_10_code,
                "promo_10_sent": s.promo_10_sent,
                "promo_10_sent_at": s.promo_10_sent_at.isoformat() if s.promo_10_sent_at else None,
                "promo_10_used": s.promo_10_used,
                "promo_10_used_at": s.promo_10_used_at.isoformat() if s.promo_10_used_at else None,
                # FREE promo (separate)
                "promo_free_code": s.promo_free_code,
                "promo_free_sent": s.promo_free_sent,
                "promo_free_sent_at": s.promo_free_sent_at.isoformat() if s.promo_free_sent_at else None,
                "promo_free_used": s.promo_free_used,
                "promo_free_used_at": s.promo_free_used_at.isoformat() if s.promo_free_used_at else None,
                # Unsubscribe
                "unsubscribed": s.unsubscribed,
                "unsubscribed_at": s.unsubscribed_at.isoformat() if s.unsubscribed_at else None,
            }
            for s in subscribers
        ],
    }


@app.get("/api/admin/abandoned-leads")
async def get_abandoned_leads(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # Requires admin auth
):
    """
    Get customers who started the booking flow but didn't complete.
    These are customers with no confirmed bookings.
    """
    from db_models import Customer, Booking, BookingStatus

    # Subquery to find customers with at least one confirmed booking
    confirmed_booking_exists = (
        db.query(Booking.customer_id)
        .filter(Booking.status == BookingStatus.CONFIRMED)
        .subquery()
    )

    # Get customers who have NO confirmed bookings
    abandoned_leads = (
        db.query(Customer)
        .filter(~Customer.id.in_(db.query(confirmed_booking_exists.c.customer_id)))
        .order_by(Customer.created_at.desc())
        .all()
    )

    # For each lead, get their booking attempts (if any)
    leads_data = []
    for customer in abandoned_leads:
        # Get any bookings they might have (pending, failed, etc.)
        bookings = db.query(Booking).filter(Booking.customer_id == customer.id).all()

        leads_data.append({
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "billing_address1": customer.billing_address1,
            "billing_city": customer.billing_city,
            "billing_postcode": customer.billing_postcode,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "booking_attempts": len(bookings),
            "last_booking_status": bookings[0].status.value if bookings else None,
        })

    return {
        "count": len(leads_data),
        "leads": leads_data,
    }


@app.get("/api/admin/reports/booking-locations")
async def get_booking_locations(
    map_type: str = Query("bookings", description="Map type: 'bookings' for confirmed bookings, 'origins' for all leads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get locations for map visualization.

    map_type='bookings': Returns confirmed bookings with geocoded billing postcodes.
    map_type='origins': Returns all customers (leads) from booking flow Page 1 with geocoded billing postcodes.
    """
    from db_models import Booking, Customer

    if map_type == "origins":
        # Query customers with billing postcodes created after the feature launch
        # Only show leads from when the Journey Origins feature was deployed
        from datetime import datetime
        feature_launch_date = datetime(2026, 2, 16, 20, 0, 0)  # Feature deployment cutoff

        customers = (
            db.query(Customer)
            .filter(Customer.billing_postcode.isnot(None))
            .filter(Customer.billing_postcode != "")
            .filter(Customer.created_at >= feature_launch_date)
            .order_by(Customer.created_at.desc())
            .all()
        )

        # Extract unique postcodes
        postcode_to_customers = {}
        for c in customers:
            postcode = c.billing_postcode.strip().upper()
            if postcode:
                if postcode not in postcode_to_customers:
                    postcode_to_customers[postcode] = []
                postcode_to_customers[postcode].append(c)

        if not postcode_to_customers:
            return {"count": 0, "locations": [], "map_type": map_type}

        # Bulk geocode postcodes via postcodes.io
        postcodes_list = list(postcode_to_customers.keys())
        coordinates = {}

        try:
            async with httpx.AsyncClient() as client:
                for i in range(0, len(postcodes_list), 100):
                    batch = postcodes_list[i:i + 100]
                    response = await client.post(
                        "https://api.postcodes.io/postcodes",
                        json={"postcodes": batch},
                        timeout=10.0,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        for item in data.get("result", []):
                            if item.get("result"):
                                pc = item["query"].upper()
                                coordinates[pc] = {
                                    "lat": item["result"]["latitude"],
                                    "lng": item["result"]["longitude"],
                                    "admin_district": item["result"].get("admin_district"),
                                }
        except Exception as e:
            log_error(db=db, error_type="geocoding_error", message=str(e))

        # Build response with customer details
        locations = []
        skipped = []
        for c in customers:
            postcode = c.billing_postcode.strip().upper()
            if postcode not in coordinates:
                skipped.append({"customer_id": c.id, "reason": f"Postcode '{postcode}' not found"})
                continue

            # Check if this customer has any confirmed bookings
            has_booking = any(b.status.value in ["confirmed", "completed"] for b in c.bookings) if c.bookings else False

            coord = coordinates[postcode]
            locations.append({
                "id": c.id,
                "customer_name": f"{c.first_name} {c.last_name}",
                "phone": c.phone,
                "email": c.email,
                "address": f"{c.billing_address1 or ''}, {c.billing_city or ''}".strip(", "),
                "postcode": postcode,
                "city": c.billing_city,
                "lat": coord["lat"],
                "lng": coord["lng"],
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "has_booking": has_booking,
            })

        return {
            "count": len(locations),
            "total_customers": len(customers),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "locations": locations,
            "map_type": map_type,
        }

    # Default: map_type="bookings" - Query confirmed/completed bookings
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.customer))
        .filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]))
        .order_by(Booking.dropoff_date.desc())
        .all()
    )

    # Extract unique postcodes
    postcode_to_bookings = {}
    for b in bookings:
        if b.customer and b.customer.billing_postcode:
            postcode = b.customer.billing_postcode.strip().upper()
            if postcode:
                if postcode not in postcode_to_bookings:
                    postcode_to_bookings[postcode] = []
                postcode_to_bookings[postcode].append(b)

    if not postcode_to_bookings:
        return {"count": 0, "total_bookings": 0, "skipped_count": 0, "skipped": [], "locations": [], "map_type": map_type}

    # Bulk geocode postcodes via postcodes.io
    postcodes_list = list(postcode_to_bookings.keys())
    coordinates = {}

    try:
        async with httpx.AsyncClient() as client:
            # postcodes.io supports bulk lookup (max 100 per request)
            for i in range(0, len(postcodes_list), 100):
                batch = postcodes_list[i:i + 100]
                response = await client.post(
                    "https://api.postcodes.io/postcodes",
                    json={"postcodes": batch},
                    timeout=10.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("result", []):
                        if item.get("result"):
                            pc = item["query"].upper()
                            coordinates[pc] = {
                                "lat": item["result"]["latitude"],
                                "lng": item["result"]["longitude"],
                                "admin_district": item["result"].get("admin_district"),
                            }
    except Exception as e:
        # Log error but continue with whatever we have
        log_error(db=db, error_type="geocoding_error", message=str(e))

    # Build response with booking details
    locations = []
    skipped = []
    for b in bookings:
        if not b.customer:
            skipped.append({"reference": b.reference, "reason": "No customer"})
            continue
        if not b.customer.billing_postcode:
            skipped.append({"reference": b.reference, "reason": "No postcode"})
            continue
        postcode = b.customer.billing_postcode.strip().upper()
        if postcode not in coordinates:
            skipped.append({"reference": b.reference, "reason": f"Postcode '{postcode}' not found"})
            continue
        coord = coordinates[postcode]
        locations.append({
            "id": b.id,
            "reference": b.reference,
            "customer_name": f"{b.customer_first_name or b.customer.first_name} {b.customer_last_name or b.customer.last_name}",
            "postcode": postcode,
            "city": b.customer.billing_city,
            "lat": coord["lat"],
            "lng": coord["lng"],
            "dropoff_date": b.dropoff_date.isoformat() if b.dropoff_date else None,
            "status": b.status.value if b.status else None,
        })

    return {
        "count": len(locations),
        "total_bookings": len(bookings),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "locations": locations,
        "map_type": map_type,
    }


@app.post("/api/admin/marketing-subscribers/{subscriber_id}/send-promo")
async def send_promo_email_to_subscriber(
    subscriber_id: int,
    discount_percent: int = Query(10, description="Discount percentage (10 or 100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate a unique promo code and send promo email to a subscriber.

    Supports SEPARATE 10% and FREE promos - a subscriber can receive both:
    - 10% off promo (discount_percent=10) -> stored in promo_10_* fields
    - FREE parking promo (discount_percent=100) -> stored in promo_free_* fields
    """
    from email_service import generate_promo_code, send_promo_code_email

    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.id == subscriber_id
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    if subscriber.unsubscribed:
        raise HTTPException(status_code=400, detail="Subscriber has unsubscribed")

    # Validate discount percent
    if discount_percent not in [10, 100]:
        raise HTTPException(status_code=400, detail="Discount must be 10 or 100 percent")

    # Check if THIS specific promo type has already been used
    if discount_percent == 10 and subscriber.promo_10_used:
        raise HTTPException(status_code=400, detail="10% promo code has already been used")
    if discount_percent == 100 and subscriber.promo_free_used:
        raise HTTPException(status_code=400, detail="FREE promo code has already been used")

    # Generate unique promo code for this specific promo type
    if discount_percent == 10:
        # 10% OFF promo
        if not subscriber.promo_10_code:
            for _ in range(10):
                new_code = generate_promo_code()
                # Check uniqueness across both promo code fields
                existing = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_10_code == new_code) |
                    (MarketingSubscriber.promo_free_code == new_code) |
                    (MarketingSubscriber.promo_code == new_code)
                ).first()
                if not existing:
                    subscriber.promo_10_code = new_code
                    break
            else:
                raise HTTPException(status_code=500, detail="Failed to generate unique promo code")
        promo_code = subscriber.promo_10_code
    else:
        # FREE parking promo (100% off)
        if not subscriber.promo_free_code:
            for _ in range(10):
                new_code = generate_promo_code()
                existing = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_10_code == new_code) |
                    (MarketingSubscriber.promo_free_code == new_code) |
                    (MarketingSubscriber.promo_code == new_code)
                ).first()
                if not existing:
                    subscriber.promo_free_code = new_code
                    break
            else:
                raise HTTPException(status_code=500, detail="Failed to generate unique promo code")
        promo_code = subscriber.promo_free_code

    db.commit()

    # Send the email
    if discount_percent == 100:
        email_sent = send_free_parking_promo_email(
            first_name=subscriber.first_name,
            email=subscriber.email,
            promo_code=promo_code,
        )
    else:
        email_sent = send_promo_code_email(
            first_name=subscriber.first_name,
            email=subscriber.email,
            promo_code=promo_code,
        )

    if email_sent:
        # Update the appropriate promo tracking fields
        if discount_percent == 10:
            subscriber.promo_10_sent = True
            subscriber.promo_10_sent_at = datetime.utcnow()
        else:
            subscriber.promo_free_sent = True
            subscriber.promo_free_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Promo code email ({discount_percent}% off) sent to {subscriber.email}",
            "promo_code": promo_code,
            "discount_percent": discount_percent,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send promo email. Check SendGrid configuration."
        )


def send_free_parking_promo_email(first_name: str, email: str, promo_code: str) -> bool:
    """Send 100% off (FREE parking) promo code email."""
    from email_service import send_email
    from pathlib import Path
    import logging

    logger = logging.getLogger(__name__)
    subject = f"{first_name}, you've won FREE airport parking!"

    # Load the HTML template
    template_path = Path(__file__).parent / "email_templates" / "free_parking_promo_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{PROMO_CODE}}", promo_code)
    except FileNotFoundError:
        logger.error(f"Free parking promo email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading free parking promo email template: {e}")
        return False

    return send_email(email, subject, html_content)


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


@app.patch("/api/customers/{customer_id}")
async def update_customer(
    customer_id: int,
    request: CreateCustomerRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Update existing customer contact information.
    Used when user goes back and edits their details.
    """
    customer = db_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        customer.first_name = request.first_name
        customer.last_name = request.last_name
        customer.email = request.email
        customer.phone = request.phone
        db.commit()
        db.refresh(customer)

        return {
            "success": True,
            "customer_id": customer.id,
            "message": "Customer updated successfully",
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


@app.patch("/api/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: int,
    request: CreateVehicleRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Update existing vehicle information.
    Used when user goes back and edits their vehicle details.
    """
    from db_models import Vehicle

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    try:
        vehicle.registration = request.registration.upper()
        vehicle.make = request.make
        vehicle.model = request.model
        vehicle.colour = request.colour
        db.commit()
        db.refresh(vehicle)

        return {
            "success": True,
            "vehicle_id": vehicle.id,
            "message": "Vehicle updated successfully",
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

    # Return flight details
    arrival_id: Optional[int] = None  # ID of the flight arrival
    pickup_flight_time: Optional[str] = None  # Landing time "HH:MM"
    pickup_flight_number: Optional[str] = None
    pickup_origin: Optional[str] = None  # Origin airport name

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
        # Validate billing address is provided
        if not request.billing_address1 or not request.billing_address1.strip():
            raise HTTPException(status_code=400, detail="Billing address is required")
        if not request.billing_city or not request.billing_city.strip():
            raise HTTPException(status_code=400, detail="Billing city is required")
        if not request.billing_postcode or not request.billing_postcode.strip():
            raise HTTPException(status_code=400, detail="Billing postcode is required")

        # Check for existing PENDING booking with same session_id (prevent duplicates from Terms toggle)
        if request.session_id:
            existing_booking = db_service.get_pending_booking_by_session(db, request.session_id)
            if existing_booking:
                print(f"[DEDUP] Found existing PENDING booking {existing_booking.reference} for session {request.session_id}")
                # Check if there's an existing payment record with a valid PaymentIntent
                existing_payment = existing_booking.payment
                if existing_payment and existing_payment.stripe_payment_intent_id:
                    try:
                        # Retrieve the existing PaymentIntent from Stripe
                        intent = stripe.PaymentIntent.retrieve(existing_payment.stripe_payment_intent_id)
                        if intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']:
                            # PaymentIntent is still usable - return it
                            print(f"[DEDUP] Reusing existing PaymentIntent {intent.id} (status: {intent.status})")
                            settings = get_settings()
                            return CreatePaymentResponse(
                                client_secret=intent.client_secret,
                                payment_intent_id=intent.id,
                                booking_reference=existing_booking.reference,
                                amount=intent.amount,
                                amount_display=f"£{intent.amount / 100:.2f}",
                                publishable_key=settings.stripe_publishable_key,
                            )
                        else:
                            print(f"[DEDUP] Existing PaymentIntent {intent.id} not usable (status: {intent.status})")
                    except stripe.error.StripeError as e:
                        print(f"[DEDUP] Could not retrieve PaymentIntent: {e}")
                # If we get here, existing payment isn't usable - continue to create new one
                # But we'll still use the existing booking reference

        # Debug: log incoming promo code
        print(f"[PROMO] Received request with promo_code: {request.promo_code}")

        # Parse dates first (needed for dynamic pricing)
        print(f"[DEBUG] Received drop_off_date string: {request.drop_off_date}")
        dropoff_date = datetime.strptime(request.drop_off_date, "%Y-%m-%d").date()
        pickup_date = datetime.strptime(request.pickup_date, "%Y-%m-%d").date()
        print(f"[DEBUG] Parsed dropoff_date: {dropoff_date}, pickup_date: {pickup_date}")

        # Calculate duration for flexible pricing
        duration_days = (pickup_date - dropoff_date).days
        print(f"[DEBUG] Trip duration: {duration_days} days")

        # Calculate base amount in pence (using flexible duration pricing)
        original_amount = calculate_price_in_pence(
            package=request.package,
            drop_off_date=dropoff_date,
            duration_days=duration_days
        )

        # Check for promo code and apply discount if valid
        discount_amount = 0
        discount_percent = 0
        promo_code_applied = None
        is_free_booking = False
        if request.promo_code:
            promo_code = request.promo_code.strip().upper()
            print(f"[PROMO] Looking up promo code: {promo_code}")
            subscriber = db.query(MarketingSubscriber).filter(
                (MarketingSubscriber.promo_code == promo_code) |
                (MarketingSubscriber.promo_10_code == promo_code) |
                (MarketingSubscriber.promo_free_code == promo_code)
            ).first()
            if subscriber:
                # Determine which promo type this code belongs to
                promo_used = False
                if subscriber.promo_10_code and subscriber.promo_10_code == promo_code:
                    promo_used = subscriber.promo_10_used
                    discount_percent = 10
                elif subscriber.promo_free_code and subscriber.promo_free_code == promo_code:
                    promo_used = subscriber.promo_free_used
                    discount_percent = 100
                elif subscriber.promo_code and subscriber.promo_code == promo_code:
                    promo_used = subscriber.promo_code_used
                    discount_percent = subscriber.discount_percent if subscriber.discount_percent is not None else PROMO_DISCOUNT_PERCENT

                print(f"[PROMO] Found subscriber: {subscriber.email}, used: {promo_used}")
                if not promo_used:
                    if discount_percent == 100:
                        # FREE promo: based on trip duration (not package)
                        if duration_days <= 7:
                            # Trips up to 7 days: completely free
                            discount_amount = original_amount
                            is_free_booking = True
                        else:
                            # Trips 8-14 days: deduct the 1-week base rate (7-day early tier)
                            # e.g. 10-day trip £119 - 7-day base £79 = customer pays £40
                            week1_base_pence = int(get_base_price_for_duration(7) * 100)
                            discount_amount = min(week1_base_pence, original_amount)
                            is_free_booking = False
                    else:
                        # Percentage-based discount (10% or custom)
                        discount_amount = int(original_amount * discount_percent / 100)
                        is_free_booking = False
                    promo_code_applied = promo_code
                    print(f"[PROMO] Discount applied: {discount_percent}% = {discount_amount} pence, duration: {duration_days} days (free: {is_free_booking})")
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

            # Handle overnight (e.g., 23:30 landing + 35 min = 00:05 next day)
            # If pickup time crosses midnight, adjust pickup_date to next day
            if total_minutes_from >= 24 * 60:
                pickup_date = pickup_date + timedelta(days=1)

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

            # Use arrival_id and pickup_origin from request if provided
            arrival_id = request.arrival_id
            pickup_origin = None

            if request.pickup_origin:
                # Format origin name (extract city from "City, CountryCode" format)
                parts = request.pickup_origin.split(', ')
                pickup_origin = parts[0] if parts else request.pickup_origin
                # Shorten Tenerife-Reinasofia to Tenerife
                if pickup_origin == 'Tenerife-Reinasofia':
                    pickup_origin = 'Tenerife'
            elif arrival_id:
                # Fallback: look up from arrival record
                arrival = db.query(FlightArrival).filter(FlightArrival.id == arrival_id).first()
                if arrival and arrival.origin_name:
                    parts = arrival.origin_name.split(', ')
                    pickup_origin = parts[0] if parts else arrival.origin_name
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
                arrival_id=arrival_id,
                session_id=request.session_id,
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

            # Use arrival_id and pickup_origin from request if provided
            arrival_id = request.arrival_id
            pickup_origin = None

            if request.pickup_origin:
                # Format origin name (extract city from "City, CountryCode" format)
                parts = request.pickup_origin.split(', ')
                pickup_origin = parts[0] if parts else request.pickup_origin
                # Shorten Tenerife-Reinasofia to Tenerife
                if pickup_origin == 'Tenerife-Reinasofia':
                    pickup_origin = 'Tenerife'
            elif arrival_id:
                # Fallback: look up from arrival record
                arrival = db.query(FlightArrival).filter(FlightArrival.id == arrival_id).first()
                if arrival and arrival.origin_name:
                    parts = arrival.origin_name.split(', ')
                    pickup_origin = parts[0] if parts else arrival.origin_name
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
                arrival_id=arrival_id,
                # Session tracking
                session_id=request.session_id,
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

            # Mark promo code as used (search across all code fields)
            if promo_code_applied:
                subscriber = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_code == promo_code_applied) |
                    (MarketingSubscriber.promo_10_code == promo_code_applied) |
                    (MarketingSubscriber.promo_free_code == promo_code_applied)
                ).first()
                if subscriber:
                    now = datetime.utcnow()
                    if subscriber.promo_10_code and subscriber.promo_10_code == promo_code_applied:
                        subscriber.promo_10_used = True
                        subscriber.promo_10_used_at = now
                        subscriber.promo_10_used_booking_id = booking_id
                    elif subscriber.promo_free_code and subscriber.promo_free_code == promo_code_applied:
                        subscriber.promo_free_used = True
                        subscriber.promo_free_used_at = now
                        subscriber.promo_free_used_booking_id = booking_id
                    elif subscriber.promo_code and subscriber.promo_code == promo_code_applied:
                        subscriber.promo_code_used = True
                        subscriber.promo_code_used_at = now
                        subscriber.promo_code_used_booking_id = booking_id
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
                    return_flight=f"{request.pickup_flight_number or 'TBC'} from {pickup_origin or 'TBC'}",
                    vehicle_make=vehicle_make,
                    vehicle_model=vehicle_model,
                    vehicle_colour=vehicle_colour,
                    vehicle_registration=vehicle_registration,
                    package_name=package_name,
                    amount_paid="£0.00",
                    promo_code=promo_code_applied,
                    discount_amount=f"£{discount_amount / 100:.2f}",
                    original_amount=f"£{original_amount / 100:.2f}",
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
            original_amount=original_amount if promo_code_applied else None,
            discount_amount=discount_amount if promo_code_applied else None,
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
        meta_original_amount = metadata.get("original_amount")  # pence, as string
        meta_discount_amount = metadata.get("discount_amount")  # pence, as string

        # Update payment status in database (this also updates booking to CONFIRMED)
        # Returns (payment, was_already_processed) for idempotency
        was_already_processed = False
        try:
            payment, was_already_processed = db_service.update_payment_status(
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
            elif was_already_processed:
                print(f"[WEBHOOK] Duplicate webhook - already processed for {booking_reference}")
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
        # Skip if this webhook was already processed (idempotency for duplicate webhooks)
        if departure_id and drop_off_slot and payment and not was_already_processed:
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
        # Skip if this webhook was already processed
        if promo_code and not was_already_processed:
            try:
                # Get booking ID from reference
                booking = db_service.get_booking_by_reference(db, booking_reference)
                bid = booking.id if booking else None
                subscriber = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_code == promo_code) |
                    (MarketingSubscriber.promo_10_code == promo_code) |
                    (MarketingSubscriber.promo_free_code == promo_code)
                ).first()
                if subscriber:
                    now = datetime.utcnow()
                    if subscriber.promo_10_code and subscriber.promo_10_code == promo_code:
                        subscriber.promo_10_used = True
                        subscriber.promo_10_used_at = now
                        subscriber.promo_10_used_booking_id = bid
                    elif subscriber.promo_free_code and subscriber.promo_free_code == promo_code:
                        subscriber.promo_free_used = True
                        subscriber.promo_free_used_at = now
                        subscriber.promo_free_used_booking_id = bid
                    elif subscriber.promo_code and subscriber.promo_code == promo_code:
                        subscriber.promo_code_used = True
                        subscriber.promo_code_used_at = now
                        subscriber.promo_code_used_booking_id = bid
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

                # Calculate discount from Stripe metadata (original_amount & discount_amount in pence)
                discount_display = None
                original_display = None
                if promo_code and meta_original_amount and meta_discount_amount:
                    try:
                        orig_pence = int(meta_original_amount)
                        disc_pence = int(meta_discount_amount)
                        original_display = f"£{orig_pence / 100:.2f}"
                        discount_display = f"£{disc_pence / 100:.2f}"
                    except (ValueError, TypeError):
                        pass
                elif promo_code:
                    # Fallback for older payment intents without metadata
                    original_amount_calc = amount_pence / 0.9
                    discount_display = f"£{(original_amount_calc - amount_pence) / 100:.2f}"

                print(f"[EMAIL] Calling send_booking_confirmation_email...")
                email_sent = send_booking_confirmation_email(
                    email=booking.customer.email,
                    first_name=booking.customer_first_name or booking.customer.first_name,
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
                    discount_amount=discount_display,
                    original_amount=original_display,
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
    current_user: User = Depends(require_admin),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Seed the database with flight schedule data.

    Requires admin authentication AND ADMIN_SECRET for extra security.
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
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


class UpdateUserRequest(BaseModel):
    """Request to update a user."""
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@app.post("/api/admin/users")
async def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin endpoint: Create a new user."""
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
            "phone": user.phone,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        }
    }


@app.get("/api/admin/users")
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin endpoint: List all users."""
    users = db.query(User).all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "phone": u.phone,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ]
    }


@app.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin endpoint: Update a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Can't remove your own admin privileges
    if user.id == current_user.id and request.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin privileges")

    # Can't deactivate yourself
    if user.id == current_user.id and request.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    if request.email is not None:
        email = request.email.strip().lower()
        existing = db.query(User).filter(User.email == email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        user.email = email
    if request.first_name is not None:
        user.first_name = request.first_name.strip()
    if request.last_name is not None:
        user.last_name = request.last_name.strip()
    if request.phone is not None:
        user.phone = request.phone.strip() if request.phone else None
    if request.is_admin is not None:
        user.is_admin = request.is_admin
    if request.is_active is not None:
        user.is_active = request.is_active

    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        }
    }


@app.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin endpoint: Delete a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Clean up related records (foreign key constraints)
    db.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    db.query(DbSession).filter(DbSession.user_id == user.id).delete()

    # Nullify vehicle_inspections.inspector_id references
    db.query(VehicleInspection).filter(VehicleInspection.inspector_id == user.id).update({"inspector_id": None})

    # Nullify pricing_settings.updated_by references
    from db_models import PricingSettings
    db.query(PricingSettings).filter(PricingSettings.updated_by == user.id).update({"updated_by": None})

    db.delete(user)
    db.commit()

    return {"success": True, "message": f"User {user.email} deleted"}


# ============================================================================
# VEHICLE INSPECTION ENDPOINTS (Employee + Admin)
# ============================================================================


class CreateInspectionRequest(BaseModel):
    booking_id: int
    inspection_type: str  # "dropoff" or "pickup"
    notes: Optional[str] = None
    photos: Optional[dict] = None  # { "front": "base64...", "rear": "base64...", ... }
    customer_name: Optional[str] = None
    signed_date: Optional[str] = None  # ISO date string YYYY-MM-DD
    signature: Optional[str] = None  # Base64-encoded signature image
    vehicle_inspection_read: Optional[bool] = False  # Confirmed they read the T&C


class UpdateInspectionRequest(BaseModel):
    notes: Optional[str] = None
    photos: Optional[dict] = None
    customer_name: Optional[str] = None
    signed_date: Optional[str] = None
    signature: Optional[str] = None
    vehicle_inspection_read: Optional[bool] = None


@app.get("/api/employee/bookings")
async def get_employee_bookings(
    include_cancelled: bool = Query(False, description="Include cancelled bookings"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Employee endpoint: Get all bookings for the calendar view."""
    from db_models import Booking, Customer, Vehicle, Payment, BookingStatus

    query = db.query(Booking).options(
        joinedload(Booking.customer),
        joinedload(Booking.vehicle),
        joinedload(Booking.payment),
        joinedload(Booking.departure),
    )

    if not include_cancelled:
        query = query.filter(Booking.status != BookingStatus.CANCELLED)

    bookings = query.order_by(Booking.dropoff_date.asc()).all()

    result = []
    for b in bookings:
        result.append({
            "id": b.id,
            "reference": b.reference,
            "status": b.status.value if b.status else None,
            "dropoff_date": b.dropoff_date.isoformat() if b.dropoff_date else None,
            "dropoff_time": b.dropoff_time.strftime("%H:%M") if b.dropoff_time else None,
            "dropoff_destination": b.dropoff_destination,
            "pickup_date": b.pickup_date.isoformat() if b.pickup_date else None,
            "pickup_time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            "pickup_time_from": b.pickup_time_from.strftime("%H:%M") if b.pickup_time_from else None,
            "pickup_time_to": b.pickup_time_to.strftime("%H:%M") if b.pickup_time_to else None,
            "pickup_origin": b.pickup_origin,
            "notes": b.notes,
            "customer": {
                "first_name": b.customer_first_name or b.customer.first_name,
                "last_name": b.customer_last_name or b.customer.last_name,
                "phone": b.customer.phone,
            } if b.customer else None,
            "vehicle": {
                "registration": b.vehicle.registration,
                "make": b.vehicle.make,
                "model": b.vehicle.model,
                "colour": b.vehicle.colour,
            } if b.vehicle else None,
        })

    return {
        "count": len(result),
        "bookings": result,
    }


@app.post("/api/employee/inspections")
async def create_inspection(
    request: CreateInspectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a vehicle inspection (drop-off or pick-up)."""
    # Validate inspection type
    try:
        insp_type = InspectionType(request.inspection_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid inspection type. Must be 'dropoff' or 'pickup'")

    # Check booking exists
    booking = db.query(DbBooking).filter(DbBooking.id == request.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Check for existing inspection of this type
    existing = db.query(VehicleInspection).filter(
        VehicleInspection.booking_id == request.booking_id,
        VehicleInspection.inspection_type == insp_type,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{request.inspection_type} inspection already exists for this booking")

    from datetime import date as date_type
    signed_date = None
    if request.signed_date:
        try:
            signed_date = date_type.fromisoformat(request.signed_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid signed_date format. Use YYYY-MM-DD")

    inspection = VehicleInspection(
        booking_id=request.booking_id,
        inspection_type=insp_type,
        notes=request.notes,
        photos=json.dumps(request.photos) if request.photos else None,
        customer_name=request.customer_name,
        signed_date=signed_date,
        signature=request.signature,
        vehicle_inspection_read=request.vehicle_inspection_read or False,
        inspector_id=current_user.id,
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    return {
        "success": True,
        "inspection": {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "notes": inspection.notes,
            "photos": json.loads(inspection.photos) if inspection.photos else {},
            "customer_name": inspection.customer_name,
            "signed_date": inspection.signed_date.isoformat() if inspection.signed_date else None,
            "signature": inspection.signature,
            "vehicle_inspection_read": inspection.vehicle_inspection_read,
            "inspector_id": inspection.inspector_id,
            "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
        }
    }


@app.get("/api/employee/inspections/{booking_id}")
async def get_inspections(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all inspections for a booking."""
    inspections = db.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking_id
    ).all()

    return {
        "inspections": [
            {
                "id": i.id,
                "booking_id": i.booking_id,
                "inspection_type": i.inspection_type.value,
                "notes": i.notes,
                "photos": json.loads(i.photos) if i.photos else {},
                "customer_name": i.customer_name,
                "signed_date": i.signed_date.isoformat() if i.signed_date else None,
                "signature": i.signature,
                "vehicle_inspection_read": i.vehicle_inspection_read,
                "inspector_id": i.inspector_id,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "updated_at": i.updated_at.isoformat() if i.updated_at else None,
            }
            for i in inspections
        ]
    }


@app.put("/api/employee/inspections/{inspection_id}")
async def update_inspection(
    inspection_id: int,
    request: UpdateInspectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a vehicle inspection."""
    inspection = db.query(VehicleInspection).filter(VehicleInspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    if request.notes is not None:
        inspection.notes = request.notes
    if request.photos is not None:
        inspection.photos = json.dumps(request.photos)
    if request.customer_name is not None:
        inspection.customer_name = request.customer_name
    if request.signed_date is not None:
        from datetime import date as date_type
        try:
            inspection.signed_date = date_type.fromisoformat(request.signed_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid signed_date format. Use YYYY-MM-DD")
    if request.signature is not None:
        inspection.signature = request.signature
    if request.vehicle_inspection_read is not None:
        inspection.vehicle_inspection_read = request.vehicle_inspection_read

    db.commit()
    db.refresh(inspection)

    return {
        "success": True,
        "inspection": {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "notes": inspection.notes,
            "photos": json.loads(inspection.photos) if inspection.photos else {},
            "customer_name": inspection.customer_name,
            "signed_date": inspection.signed_date.isoformat() if inspection.signed_date else None,
            "signature": inspection.signature,
            "vehicle_inspection_read": inspection.vehicle_inspection_read,
            "inspector_id": inspection.inspector_id,
            "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
            "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else None,
        }
    }


@app.post("/api/employee/bookings/{booking_id}/complete")
async def mark_booking_completed(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a booking as completed."""
    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail=f"Booking must be confirmed to complete. Current status: {booking.status.value}")

    booking.status = BookingStatus.COMPLETED
    db.commit()

    return {"success": True, "message": f"Booking {booking.reference} marked as completed"}



# ============================================================================
# PRICING SETTINGS ENDPOINTS
# ============================================================================


class PricingSettingsResponse(BaseModel):
    """Response model for pricing settings with all duration tiers."""
    days_1_4_price: float
    days_5_6_price: float
    week1_base_price: float    # 7 days
    days_8_9_price: float
    days_10_11_price: float
    days_12_13_price: float
    week2_base_price: float    # 14 days
    tier_increment: float
    updated_at: Optional[str] = None


class PricingSettingsUpdate(BaseModel):
    """Request model for updating pricing settings with all duration tiers."""
    days_1_4_price: float
    days_5_6_price: float
    week1_base_price: float    # 7 days
    days_8_9_price: float
    days_10_11_price: float
    days_12_13_price: float
    week2_base_price: float    # 14 days
    tier_increment: float


@app.get("/api/pricing")
async def get_pricing():
    """
    Public endpoint: Get current pricing settings.
    Used by HomePage to display dynamic prices.
    Uses get_pricing_from_db() for consistency with other pricing logic.
    """
    from booking_service import get_pricing_from_db

    return get_pricing_from_db()


@app.get("/api/admin/pricing")
async def get_admin_pricing(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Get current pricing settings with metadata.
    """
    from db_models import PricingSettings

    settings = db.query(PricingSettings).first()

    if not settings:
        return {
            "days_1_4_price": 60.0,
            "days_5_6_price": 72.0,
            "week1_base_price": 79.0,
            "days_8_9_price": 99.0,
            "days_10_11_price": 119.0,
            "days_12_13_price": 130.0,
            "week2_base_price": 140.0,
            "tier_increment": 10.0,
            "updated_at": None,
            "updated_by": None,
        }

    return {
        "days_1_4_price": float(settings.days_1_4_price) if settings.days_1_4_price else 60.0,
        "days_5_6_price": float(settings.days_5_6_price) if settings.days_5_6_price else 72.0,
        "week1_base_price": float(settings.week1_base_price) if settings.week1_base_price else 79.0,
        "days_8_9_price": float(settings.days_8_9_price) if settings.days_8_9_price else 99.0,
        "days_10_11_price": float(settings.days_10_11_price) if settings.days_10_11_price else 119.0,
        "days_12_13_price": float(settings.days_12_13_price) if settings.days_12_13_price else 130.0,
        "week2_base_price": float(settings.week2_base_price) if settings.week2_base_price else 140.0,
        "tier_increment": float(settings.tier_increment) if settings.tier_increment else 10.0,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
        "updated_by": settings.updater.first_name if settings.updater else None,
    }


@app.put("/api/admin/pricing")
async def update_pricing(
    update: PricingSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Update pricing settings for all duration tiers.
    """
    from db_models import PricingSettings
    from decimal import Decimal

    settings = db.query(PricingSettings).first()

    if not settings:
        # Create new settings
        settings = PricingSettings(
            days_1_4_price=Decimal(str(update.days_1_4_price)),
            days_5_6_price=Decimal(str(update.days_5_6_price)),
            week1_base_price=Decimal(str(update.week1_base_price)),
            days_8_9_price=Decimal(str(update.days_8_9_price)),
            days_10_11_price=Decimal(str(update.days_10_11_price)),
            days_12_13_price=Decimal(str(update.days_12_13_price)),
            week2_base_price=Decimal(str(update.week2_base_price)),
            tier_increment=Decimal(str(update.tier_increment)),
            updated_by=current_user.id,
        )
        db.add(settings)
    else:
        # Update existing
        settings.days_1_4_price = Decimal(str(update.days_1_4_price))
        settings.days_5_6_price = Decimal(str(update.days_5_6_price))
        settings.week1_base_price = Decimal(str(update.week1_base_price))
        settings.days_8_9_price = Decimal(str(update.days_8_9_price))
        settings.days_10_11_price = Decimal(str(update.days_10_11_price))
        settings.days_12_13_price = Decimal(str(update.days_12_13_price))
        settings.week2_base_price = Decimal(str(update.week2_base_price))
        settings.tier_increment = Decimal(str(update.tier_increment))
        settings.updated_by = current_user.id

    db.commit()
    db.refresh(settings)

    return {
        "success": True,
        "message": "Pricing updated successfully",
        "pricing": {
            "days_1_4_price": float(settings.days_1_4_price),
            "days_5_6_price": float(settings.days_5_6_price),
            "week1_base_price": float(settings.week1_base_price),
            "days_8_9_price": float(settings.days_8_9_price),
            "days_10_11_price": float(settings.days_10_11_price),
            "days_12_13_price": float(settings.days_12_13_price),
            "week2_base_price": float(settings.week2_base_price),
            "tier_increment": float(settings.tier_increment),
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
        }
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

    # Session expires in 12 hours
    expires_at = datetime.utcnow() + timedelta(hours=12)

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


# =============================================================================
# Admin Flights Management Endpoints
# =============================================================================

class UpdateDepartureRequest(BaseModel):
    """Request model for updating a flight departure."""
    date: Optional[str] = None  # ISO format: YYYY-MM-DD
    flight_number: Optional[str] = None
    airline_code: Optional[str] = None
    airline_name: Optional[str] = None
    departure_time: Optional[str] = None  # HH:MM format
    destination_code: Optional[str] = None
    destination_name: Optional[str] = None
    capacity_tier: Optional[int] = None
    slots_booked_early: Optional[int] = None
    slots_booked_late: Optional[int] = None


class UpdateArrivalRequest(BaseModel):
    """Request model for updating a flight arrival."""
    date: Optional[str] = None  # ISO format: YYYY-MM-DD
    flight_number: Optional[str] = None
    airline_code: Optional[str] = None
    airline_name: Optional[str] = None
    departure_time: Optional[str] = None  # HH:MM format
    arrival_time: Optional[str] = None  # HH:MM format
    origin_code: Optional[str] = None
    origin_name: Optional[str] = None


@app.get("/api/admin/flights/departures")
async def get_admin_departures(
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    destination: Optional[str] = None,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all departure flights with optional filters.
    Sorted by date (ASC by default, DESC optional).
    """
    query = db.query(FlightDeparture)

    # Apply filters
    if flight_number:
        query = query.filter(FlightDeparture.flight_number.ilike(f"%{flight_number}%"))

    if destination:
        query = query.filter(
            (FlightDeparture.destination_code.ilike(f"%{destination}%")) |
            (FlightDeparture.destination_name.ilike(f"%{destination}%"))
        )

    if airline:
        query = query.filter(
            (FlightDeparture.airline_code.ilike(f"%{airline}%")) |
            (FlightDeparture.airline_name.ilike(f"%{airline}%"))
        )

    if month:
        from sqlalchemy import extract
        query = query.filter(extract('month', FlightDeparture.date) == month)

    if year:
        from sqlalchemy import extract
        query = query.filter(extract('year', FlightDeparture.date) == year)

    # Apply sorting
    if sort_order == "desc":
        query = query.order_by(FlightDeparture.date.desc(), FlightDeparture.departure_time.desc())
    else:
        query = query.order_by(FlightDeparture.date.asc(), FlightDeparture.departure_time.asc())

    departures = query.all()

    return {
        "departures": [
            {
                "id": d.id,
                "date": d.date.isoformat(),
                "flight_number": d.flight_number,
                "airline_code": d.airline_code,
                "airline_name": d.airline_name,
                "departure_time": d.departure_time.strftime("%H:%M") if d.departure_time else None,
                "destination_code": d.destination_code,
                "destination_name": d.destination_name,
                "capacity_tier": d.capacity_tier,
                "slots_booked_early": d.slots_booked_early,
                "slots_booked_late": d.slots_booked_late,
                "max_slots_per_time": d.max_slots_per_time,
                "early_slots_available": d.early_slots_available,
                "late_slots_available": d.late_slots_available,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "updated_by": d.updated_by,
            }
            for d in departures
        ],
        "total": len(departures),
    }


@app.get("/api/admin/flights/arrivals")
async def get_admin_arrivals(
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    origin: Optional[str] = None,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all arrival flights with optional filters.
    Sorted by date (ASC by default, DESC optional).
    """
    query = db.query(FlightArrival)

    # Apply filters
    if flight_number:
        query = query.filter(FlightArrival.flight_number.ilike(f"%{flight_number}%"))

    if origin:
        query = query.filter(
            (FlightArrival.origin_code.ilike(f"%{origin}%")) |
            (FlightArrival.origin_name.ilike(f"%{origin}%"))
        )

    if airline:
        query = query.filter(
            (FlightArrival.airline_code.ilike(f"%{airline}%")) |
            (FlightArrival.airline_name.ilike(f"%{airline}%"))
        )

    if month:
        from sqlalchemy import extract
        query = query.filter(extract('month', FlightArrival.date) == month)

    if year:
        from sqlalchemy import extract
        query = query.filter(extract('year', FlightArrival.date) == year)

    # Apply sorting
    if sort_order == "desc":
        query = query.order_by(FlightArrival.date.desc(), FlightArrival.arrival_time.desc())
    else:
        query = query.order_by(FlightArrival.date.asc(), FlightArrival.arrival_time.asc())

    arrivals = query.all()

    return {
        "arrivals": [
            {
                "id": a.id,
                "date": a.date.isoformat(),
                "flight_number": a.flight_number,
                "airline_code": a.airline_code,
                "airline_name": a.airline_name,
                "departure_time": a.departure_time.strftime("%H:%M") if a.departure_time else None,
                "arrival_time": a.arrival_time.strftime("%H:%M") if a.arrival_time else None,
                "origin_code": a.origin_code,
                "origin_name": a.origin_name,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                "updated_by": a.updated_by,
            }
            for a in arrivals
        ],
        "total": len(arrivals),
    }


@app.get("/api/admin/flights/filters")
async def get_admin_flight_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get unique filter options for flights (airlines, destinations, origins, months).
    """
    from sqlalchemy import distinct, extract

    # Get unique airlines from both departures and arrivals
    departure_airlines = db.query(
        distinct(FlightDeparture.airline_code),
        FlightDeparture.airline_name
    ).all()
    arrival_airlines = db.query(
        distinct(FlightArrival.airline_code),
        FlightArrival.airline_name
    ).all()

    # Combine and deduplicate airlines
    airlines_dict = {}
    for code, name in departure_airlines + arrival_airlines:
        if code not in airlines_dict:
            airlines_dict[code] = name
    airlines = [{"code": code, "name": name} for code, name in sorted(airlines_dict.items())]

    # Get unique destinations (departures only)
    destinations = db.query(
        distinct(FlightDeparture.destination_code),
        FlightDeparture.destination_name
    ).all()
    destinations = [{"code": code, "name": name} for code, name in sorted(destinations)]

    # Get unique origins (arrivals only)
    origins = db.query(
        distinct(FlightArrival.origin_code),
        FlightArrival.origin_name
    ).all()
    origins = [{"code": code, "name": name} for code, name in sorted(origins)]

    # Get months with data
    departure_months = db.query(
        distinct(extract('month', FlightDeparture.date)),
        extract('year', FlightDeparture.date)
    ).all()
    arrival_months = db.query(
        distinct(extract('month', FlightArrival.date)),
        extract('year', FlightArrival.date)
    ).all()

    # Combine and format months
    months_set = set()
    for month, year in departure_months + arrival_months:
        if month and year:
            months_set.add((int(year), int(month)))

    months = [
        {"year": year, "month": month, "label": f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} {year}"}
        for year, month in sorted(months_set)
    ]

    return {
        "airlines": airlines,
        "destinations": destinations,
        "origins": origins,
        "months": months,
    }


@app.get("/api/admin/flights/export")
async def export_admin_flights(
    flight_type: str = Query("all", regex="^(all|departures|arrivals)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Export all flight data to JSON for backup/snapshot.
    """
    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "exported_by": current_user.email,
    }

    if flight_type in ["all", "departures"]:
        departures = db.query(FlightDeparture).order_by(FlightDeparture.date, FlightDeparture.departure_time).all()
        export_data["departures"] = [
            {
                "id": d.id,
                "date": d.date.isoformat(),
                "flight_number": d.flight_number,
                "airline_code": d.airline_code,
                "airline_name": d.airline_name,
                "departure_time": d.departure_time.strftime("%H:%M") if d.departure_time else None,
                "destination_code": d.destination_code,
                "destination_name": d.destination_name,
                "capacity_tier": d.capacity_tier,
                "slots_booked_early": d.slots_booked_early,
                "slots_booked_late": d.slots_booked_late,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "updated_by": d.updated_by,
            }
            for d in departures
        ]

    if flight_type in ["all", "arrivals"]:
        arrivals = db.query(FlightArrival).order_by(FlightArrival.date, FlightArrival.arrival_time).all()
        export_data["arrivals"] = [
            {
                "id": a.id,
                "date": a.date.isoformat(),
                "flight_number": a.flight_number,
                "airline_code": a.airline_code,
                "airline_name": a.airline_name,
                "departure_time": a.departure_time.strftime("%H:%M") if a.departure_time else None,
                "arrival_time": a.arrival_time.strftime("%H:%M") if a.arrival_time else None,
                "origin_code": a.origin_code,
                "origin_name": a.origin_name,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                "updated_by": a.updated_by,
            }
            for a in arrivals
        ]

    return export_data


@app.put("/api/admin/flights/departures/{departure_id}")
async def update_admin_departure(
    departure_id: int,
    update: UpdateDepartureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update a departure flight.
    Returns warning if capacity is reduced below current bookings.
    """
    print(f"[FLIGHT UPDATE] Updating departure {departure_id}")
    print(f"[FLIGHT UPDATE] Request: {update.model_dump()}")

    departure = db.query(FlightDeparture).filter(FlightDeparture.id == departure_id).first()

    if not departure:
        raise HTTPException(status_code=404, detail="Departure not found")

    warnings = []

    # Check capacity reduction warning
    if update.capacity_tier is not None:
        new_max_per_time = update.capacity_tier // 2
        current_early = departure.slots_booked_early
        current_late = departure.slots_booked_late

        if new_max_per_time < current_early or new_max_per_time < current_late:
            warnings.append(
                f"Warning: Reducing capacity to {update.capacity_tier} "
                f"(max {new_max_per_time} per slot) but there are "
                f"{current_early} early and {current_late} late bookings"
            )

    # Track if departure time is changing
    old_departure_time = departure.departure_time
    new_departure_time = None
    if update.departure_time:
        new_departure_time = time.fromisoformat(update.departure_time)

    # Apply updates with type conversion
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'date' and value:
            value = date.fromisoformat(value)
        elif field == 'departure_time' and value:
            value = time.fromisoformat(value)
        setattr(departure, field, value)

    # Set audit fields
    departure.updated_at = datetime.utcnow()
    departure.updated_by = current_user.email

    # Recalculate booking drop-off times if departure time changed
    bookings_updated = 0
    if new_departure_time and new_departure_time != old_departure_time:
        # Find all bookings linked to this departure
        linked_bookings = db.query(DbBooking).filter(DbBooking.departure_id == departure_id).all()

        for booking in linked_bookings:
            # Calculate new drop-off time based on slot
            # Early slot (165 min = 2h 45m before), Late slot (120 min = 2h before)
            if booking.dropoff_slot in ("165", "early"):
                minutes_before = 165
            elif booking.dropoff_slot in ("120", "late"):
                minutes_before = 120
            else:
                continue  # Skip if no valid slot

            # Calculate new drop-off time
            departure_datetime = datetime.combine(datetime.today(), new_departure_time)
            new_dropoff_datetime = departure_datetime - timedelta(minutes=minutes_before)
            booking.dropoff_time = new_dropoff_datetime.time()
            bookings_updated += 1

        if bookings_updated > 0:
            warnings.append(f"Updated drop-off times for {bookings_updated} booking(s)")

    db.commit()
    db.refresh(departure)
    print(f"[FLIGHT UPDATE] Successfully updated departure {departure_id}")

    return {
        "success": True,
        "warnings": warnings,
        "departure": {
            "id": departure.id,
            "date": departure.date.isoformat(),
            "flight_number": departure.flight_number,
            "airline_code": departure.airline_code,
            "airline_name": departure.airline_name,
            "departure_time": departure.departure_time.strftime("%H:%M") if departure.departure_time else None,
            "destination_code": departure.destination_code,
            "destination_name": departure.destination_name,
            "capacity_tier": departure.capacity_tier,
            "slots_booked_early": departure.slots_booked_early,
            "slots_booked_late": departure.slots_booked_late,
            "max_slots_per_time": departure.max_slots_per_time,
            "early_slots_available": departure.early_slots_available,
            "late_slots_available": departure.late_slots_available,
            "updated_at": departure.updated_at.isoformat() if departure.updated_at else None,
            "updated_by": departure.updated_by,
        }
    }


@app.put("/api/admin/flights/arrivals/{arrival_id}")
async def update_admin_arrival(
    arrival_id: int,
    update: UpdateArrivalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update an arrival flight.
    Returns warning if pickup times are recalculated for linked bookings.
    """
    arrival = db.query(FlightArrival).filter(FlightArrival.id == arrival_id).first()

    if not arrival:
        raise HTTPException(status_code=404, detail="Arrival not found")

    warnings = []

    # Track if arrival time is changing
    old_arrival_time = arrival.arrival_time
    new_arrival_time = None
    if update.arrival_time:
        new_arrival_time = time.fromisoformat(update.arrival_time)

    # Apply updates with type conversion
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'date' and value:
            value = date.fromisoformat(value)
        elif field in ('departure_time', 'arrival_time') and value:
            value = time.fromisoformat(value)
        setattr(arrival, field, value)

    # Set audit fields
    arrival.updated_at = datetime.utcnow()
    arrival.updated_by = current_user.email

    # Recalculate booking pickup times if arrival time changed
    bookings_updated = 0
    if new_arrival_time and new_arrival_time != old_arrival_time:
        # Find all bookings linked to this arrival
        linked_bookings = db.query(DbBooking).filter(DbBooking.arrival_id == arrival_id).all()

        for booking in linked_bookings:
            # Calculate new pickup times based on arrival time
            # pickup_time = landing time
            # pickup_time_from = landing + 35 min
            # pickup_time_to = landing + 60 min
            arrival_datetime = datetime.combine(datetime.today(), new_arrival_time)

            booking.pickup_time = new_arrival_time
            booking.pickup_time_from = (arrival_datetime + timedelta(minutes=35)).time()
            booking.pickup_time_to = (arrival_datetime + timedelta(minutes=60)).time()
            bookings_updated += 1

        if bookings_updated > 0:
            warnings.append(f"Updated pickup times for {bookings_updated} booking(s)")

    db.commit()
    db.refresh(arrival)

    return {
        "success": True,
        "warnings": warnings,
        "arrival": {
            "id": arrival.id,
            "date": arrival.date.isoformat(),
            "flight_number": arrival.flight_number,
            "airline_code": arrival.airline_code,
            "airline_name": arrival.airline_name,
            "departure_time": arrival.departure_time.strftime("%H:%M") if arrival.departure_time else None,
            "arrival_time": arrival.arrival_time.strftime("%H:%M") if arrival.arrival_time else None,
            "origin_code": arrival.origin_code,
            "origin_name": arrival.origin_name,
            "updated_at": arrival.updated_at.isoformat() if arrival.updated_at else None,
            "updated_by": arrival.updated_by,
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
